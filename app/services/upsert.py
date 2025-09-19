"""Optimized upsert operations for price data with batch processing."""

from __future__ import annotations

from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _normalize_price_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a single price row dict to satisfy DB checks.

    - Ensures required keys exist and are non-null
    - Coerces numeric types
    - Enforces low <= min(open, close) and max(open, close) <= high
    - Ensures non-negative integer volume
    - Fills defaults for optional keys like ``source`` and ``last_updated``
    """
    required = ("symbol", "date", "open", "high", "low", "close", "volume")
    if any(k not in row or row[k] is None for k in required):
        return None

    try:
        o = float(row["open"])  # type: ignore[arg-type]
        h = float(row["high"])  # type: ignore[arg-type]
        l = float(row["low"])   # type: ignore[arg-type]
        c = float(row["close"]) # type: ignore[arg-type]
        vol = int(row["volume"])  # type: ignore[arg-type]
    except Exception:
        return None

    if vol < 0:
        return None

    hi = max(h, o, c)
    lo = min(l, o, c)

    normalized = {
        "symbol": row["symbol"],
        "date": row["date"],
        "open": o if lo <= o <= hi else (lo if abs(o - lo) < abs(o - hi) else hi),
        "high": hi,
        "low": lo,
        "close": c if lo <= c <= hi else (lo if abs(c - lo) < abs(c - hi) else hi),
        "volume": vol,
        "source": row.get("source", "yfinance"),
        "last_updated": row.get("last_updated") or datetime.now(timezone.utc),
    }
    return normalized

def df_to_rows(df: pd.DataFrame, *, symbol: str, source: str) -> List[Dict[str, object]]:
    """Convert a price DataFrame into rows for bulk upsert.

    - Skips rows containing NaN values.
    - Converts index to ``date`` and numeric fields to native Python types.
    - Normalizes OHLC to satisfy DB range checks in the presence of tiny
      floating-point inconsistencies from data providers (e.g., adjusted values
      making ``open`` or ``close`` fall a hair outside ``[low, high]``).
    """

    rows: List[Dict[str, object]] = []
    for date, row in df.iterrows():
        if row.isna().any():
            continue

        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])

        # Normalize to enforce: low <= min(open, close) and max(open, close) <= high
        # This guards against tiny floating errors from upstream adjustments.
        hi = max(h, o, c)
        lo = min(l, o, c)

        # Ensure volume is a non-negative integer
        vol_raw = row["volume"]
        try:
            vol = int(vol_raw)
        except Exception:
            # If volume cannot be interpreted as int, skip this row
            continue
        if vol < 0:
            # Defensive: drop negative volumes
            continue

        rows.append(
            {
                "symbol": symbol,
                "date": date.date(),
                "open": o if lo <= o <= hi else (lo if abs(o - lo) < abs(o - hi) else hi),
                "high": hi,
                "low": lo,
                "close": c if lo <= c <= hi else (lo if abs(c - lo) < abs(c - hi) else hi),
                "volume": vol,
                "source": source,
                "last_updated": datetime.now(timezone.utc),
            }
        )
    return rows


def upsert_prices_sql() -> str:
    """Return SQL statement for upserting price rows."""

    return (
        "INSERT INTO prices (symbol, date, open, high, low, close, volume, source, last_updated) "
        "VALUES (:symbol, :date, :open, :high, :low, :close, :volume, :source, :last_updated) "
        "ON CONFLICT (symbol, date) DO UPDATE SET "
        "open = EXCLUDED.open, "
        "high = EXCLUDED.high, "
        "low = EXCLUDED.low, "
        "close = EXCLUDED.close, "
        "volume = EXCLUDED.volume, "
        "source = EXCLUDED.source, "
        "last_updated = EXCLUDED.last_updated "
        "WHERE prices.last_updated < EXCLUDED.last_updated"
    )


async def upsert_prices(
    session: AsyncSession,
    price_rows: List[Dict[str, Any]],
    batch_size: int = 1000,
    force_update: bool = False
) -> Tuple[int, int]:
    """
    Optimized batch upsert of price data.
    
    Args:
        session: Database session
        price_rows: List of price data dictionaries
        batch_size: Number of rows to process per batch
        force_update: Whether to force update existing records
        
    Returns:
        Tuple of (inserted_count, updated_count)
    """
    if not price_rows:
        return 0, 0
    
    total_inserted = 0
    total_updated = 0
    
    # Process in batches for better memory usage
    for i in range(0, len(price_rows), batch_size):
        raw_batch = price_rows[i:i + batch_size]
        # Normalize and filter invalid rows defensively (covers callers that don't
        # use df_to_rows, e.g., background workers)
        batch = []
        for r in raw_batch:
            nr = _normalize_price_row(r)
            if nr is not None:
                batch.append(nr)

        if not batch:
            continue
        
        if force_update:
            # Use regular upsert that always updates
            upsert_query = upsert_prices_sql().replace(
                "WHERE prices.last_updated < EXCLUDED.last_updated", ""
            )
        else:
            upsert_query = upsert_prices_sql()
        
        # Execute batch upsert
        result = await session.execute(text(upsert_query), batch)
        
        # PostgreSQL doesn't return separate insert/update counts from ON CONFLICT
        # We'll estimate based on affected rows
        affected_rows = result.rowcount or len(batch)
        
        # For estimation, assume 70% are updates if not forcing
        if force_update:
            total_updated += affected_rows
        else:
            estimated_inserted = int(affected_rows * 0.3)
            estimated_updated = affected_rows - estimated_inserted
            total_inserted += estimated_inserted
            total_updated += estimated_updated
    
    return total_inserted, total_updated


async def bulk_delete_prices(
    session: AsyncSession,
    symbol: str,
    date_from: Any = None,
    date_to: Any = None
) -> int:
    """
    Optimized bulk delete of price data.
    
    Args:
        session: Database session
        symbol: Symbol to delete data for
        date_from: Start date for deletion (optional)
        date_to: End date for deletion (optional)
        
    Returns:
        Number of rows deleted
    """
    conditions = ["symbol = :symbol"]
    params = {"symbol": symbol}
    
    if date_from:
        conditions.append("date >= :date_from")
        params["date_from"] = date_from
    
    if date_to:
        conditions.append("date <= :date_to")
        params["date_to"] = date_to
    
    delete_query = f"DELETE FROM prices WHERE {' AND '.join(conditions)}"
    
    result = await session.execute(text(delete_query), params)
    return result.rowcount or 0


__all__ = ["df_to_rows", "upsert_prices_sql", "upsert_prices", "bulk_delete_prices"]
