"""Database access helpers for price coverage and retrieval."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, List, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.utils import advisory_lock
from app.services.fetcher import fetch_prices
from app.services.upsert import df_to_rows, upsert_prices_sql


async def fetch_prices_df(symbol: str, start: date, end: date):
    """Background wrapper around :func:`fetch_prices`.

    ``fetch_prices`` is synchronous; run it in a thread to avoid blocking.
    """

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: fetch_prices(symbol, start, end, settings=settings)
    )


async def _get_coverage(session: AsyncSession, symbol: str, date_from: date, date_to: date) -> dict:
    """Return coverage information for ``symbol`` between the given dates.

    The query also detects gaps using ``LEAD`` over existing price rows.
    """

    sql = text(
        """
        WITH rng AS (
            SELECT :date_from::date AS dfrom, :date_to::date AS dto
        ),
        cov AS (
            SELECT
              MIN(date) AS first_date,
              MAX(date) AS last_date,
              COUNT(*)  AS cnt
            FROM prices
            WHERE symbol = :symbol
              AND date BETWEEN (SELECT dfrom FROM rng) AND (SELECT dto FROM rng)
        ),
        gaps AS (
            SELECT p.date AS cur_date,
                   LEAD(p.date) OVER (ORDER BY p.date) AS next_date
            FROM prices p
            WHERE p.symbol = :symbol
              AND p.date BETWEEN (SELECT dfrom FROM rng) AND (SELECT dto FROM rng)
        )
        SELECT
            (SELECT first_date FROM cov) AS first_date,
            (SELECT last_date  FROM cov) AS last_date,
            (SELECT cnt        FROM cov) AS cnt,
            EXISTS (
              SELECT 1 FROM gaps g
              WHERE g.next_date IS NOT NULL
                AND g.next_date > g.cur_date + INTERVAL '1 day'
            ) AS has_gaps
        """
    )
    res = await session.execute(sql.bindparams(symbol=symbol, date_from=date_from, date_to=date_to))
    row = res.mappings().first() or {}
    return dict(row)


async def ensure_coverage(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> None:
    """Ensure price data coverage for symbols.

    For each symbol the function acquires an advisory lock, inspects existing
    rows to detect gaps and determine the refetch start, downloads the missing
    data including ``refetch_days`` worth of recent history and upserts the
    rows.
    """

    for symbol in symbols:
        async with session.begin():
            await advisory_lock(session, symbol)

            cov = await _get_coverage(session, symbol, date_from, date_to)

            last_date = cov.get("last_date")
            has_gaps = cov.get("has_gaps")
            first_date = cov.get("first_date")

            if not last_date or has_gaps or (first_date and first_date > date_from):
                start = date_from
            else:
                start = max(date_from, last_date - timedelta(days=refetch_days))

            df = await fetch_prices_df(symbol=symbol, start=start, end=date_to)
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


async def get_prices_resolved(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
) -> List[dict]:
    """Fetch price rows via the ``get_prices_resolved`` SQL function.

    The function accepts multiple symbols and returns a combined, sorted list
    of dictionaries.
    """

    out: List[dict] = []
    sql = text("SELECT * FROM get_prices_resolved(:symbol, :date_from, :date_to)")
    for s in symbols:
        res = await session.execute(sql.bindparams(symbol=s, date_from=date_from, date_to=date_to))
        out.extend([dict(m) for m in res.mappings().all()])
    out.sort(key=lambda r: (r["date"], r["symbol"]))
    return out


LIST_SYMBOLS_SQL = (
    "SELECT symbol, name, exchange, currency, is_active, first_date, last_date "
    "FROM symbols "
    "WHERE (:active::boolean IS NULL OR is_active = :active) "
    "ORDER BY symbol"
)


async def list_symbols(session: AsyncSession, active: bool | None = None) -> Sequence[Any]:
    """Return symbol metadata optionally filtered by activity."""

    result = await session.execute(text(LIST_SYMBOLS_SQL), {"active": active})
    return result.fetchall()


__all__ = [
    "ensure_coverage",
    "get_prices_resolved",
    "list_symbols",
    "LIST_SYMBOLS_SQL",
]
