from __future__ import annotations

from typing import Dict, List

import pandas as pd


def df_to_rows(df: pd.DataFrame, *, symbol: str, source: str) -> List[Dict[str, object]]:
    """Convert a price DataFrame into rows for bulk upsert.

    Rows containing NaN values are skipped. Dates are converted to ``date`` and
    numeric fields are cast to appropriate Python types for insertion.
    """

    rows: List[Dict[str, object]] = []
    for date, row in df.iterrows():
        if row.isna().any():
            continue
        rows.append(
            {
                "symbol": symbol,
                "date": date.date(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "source": source,
            }
        )
    return rows


def upsert_prices_sql() -> str:
    """Return SQL statement for upserting price rows."""

    return (
        "INSERT INTO prices (symbol, date, open, high, low, close, volume, source) "
        "VALUES (:symbol, :date, :open, :high, :low, :close, :volume, :source) "
        "ON CONFLICT (symbol, date) DO UPDATE SET "
        "open = EXCLUDED.open, "
        "high = EXCLUDED.high, "
        "low = EXCLUDED.low, "
        "close = EXCLUDED.close, "
        "volume = EXCLUDED.volume, "
        "source = EXCLUDED.source, "
        "last_updated = now();"
    )


__all__ = ["df_to_rows", "upsert_prices_sql"]
