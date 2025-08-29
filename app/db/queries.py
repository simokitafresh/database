from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_coverage(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> None:
    """
    For each symbol:
      1) acquire an advisory lock within a transaction
      2) find the last existing date
      3) refetch starting from max(last_date - refetch_days, date_from)
      4) upsert fetched rows
    """

    import asyncio

    from app.db.utils import advisory_lock
    from app.services.fetcher import fetch_prices
    from app.services.upsert import df_to_rows, upsert_prices_sql
    from app.core.config import settings

    for symbol in symbols:
        async with session.begin():
            await advisory_lock(session, symbol)

            res = await session.execute(
                text("SELECT MAX(date) AS last_date FROM prices WHERE symbol = :s"),
                {"s": symbol},
            )
            last_date = res.scalar()

            if last_date:
                start = last_date - timedelta(days=refetch_days)
                if start < date_from:
                    start = date_from
            else:
                start = date_from

            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(
                None,
                lambda: fetch_prices(symbol, start, date_to, settings=settings),
            )
            if df is None or df.empty:
                continue

            rows = df_to_rows(df, symbol=symbol, source="yfinance")
            if not rows:
                continue

            up_sql = upsert_prices_sql()
            keys = [
                "symbol",
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "source",
            ]
            params = [dict(zip(keys, r)) for r in rows]
            await session.execute(text(up_sql), params)

# SQL fragments are kept as module-level constants so tests can assert on them
GET_PRICES_RESOLVED_SQL = (
    "SELECT symbol, date, open, high, low, close, volume, source, last_updated, source_symbol "
    "FROM get_prices_resolved(:symbol, :from, :to)"
)

LIST_SYMBOLS_SQL = (
    "SELECT symbol, name, exchange, currency, is_active, first_date, last_date "
    "FROM symbols "
    "WHERE (:active::boolean IS NULL OR is_active = :active) "
    "ORDER BY symbol"
)


async def get_prices_resolved(
    session: AsyncSession, symbol: str, from_: date, to: date
) -> Sequence[Any]:
    """Fetch rows from the get_prices_resolved function."""

    result = await session.execute(
        text(GET_PRICES_RESOLVED_SQL),
        {"symbol": symbol, "from": from_, "to": to},
    )
    return result.fetchall()


async def list_symbols(
    session: AsyncSession, active: bool | None = None
) -> Sequence[Any]:
    """Return symbol metadata optionally filtered by activity."""

    result = await session.execute(
        text(LIST_SYMBOLS_SQL), {"active": active}
    )
    return result.fetchall()


__all__ = [
    "ensure_coverage",
    "get_prices_resolved",
    "list_symbols",
    "GET_PRICES_RESOLVED_SQL",
    "LIST_SYMBOLS_SQL",
]
