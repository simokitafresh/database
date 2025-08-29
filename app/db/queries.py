"""Database access helpers for price coverage and retrieval."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, List, Mapping, Optional, Sequence, cast

import anyio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.utils import advisory_lock
from app.services.fetcher import fetch_prices
from app.services.upsert import df_to_rows, upsert_prices_sql

# Preserve legacy alias for tests and backward compatibility
with_symbol_lock = advisory_lock

_fetch_semaphore = anyio.Semaphore(settings.YF_REQ_CONCURRENCY)


async def fetch_prices_df(symbol: str, start: date, end: date):
    """Background wrapper around :func:`fetch_prices`.

    ``fetch_prices`` is synchronous; run it in a thread to avoid blocking.
    """

    async with _fetch_semaphore:
        return await run_in_threadpool(
            fetch_prices, symbol, start, end, settings=settings
        )


async def _get_coverage(session: AsyncSession, symbol: str, date_from: date, date_to: date) -> dict:
    """Return coverage information with weekday gap detection.

    Weekends (Saturday and Sunday) are ignored when detecting gaps. This
    function reports the first missing weekday if any. Exchange-specific
    holidays are not considered; a dedicated holiday table could be joined in
    the future to refine gap detection.
    """

    sql = text(
        """
        WITH rng AS (
            SELECT :date_from::date AS dfrom, :date_to::date AS dto
        ),
        cov AS (
            SELECT MIN(date) AS first_date,
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
        ),
        weekdays_between AS (
            SELECT g.cur_date, g.next_date, (gs.d)::date AS d
            FROM (
                -- LATERAL 実行前に NULL を除外しておく（NULL stop を防止）
                SELECT * FROM gaps WHERE next_date IS NOT NULL
            ) AS g
            JOIN LATERAL generate_series(
                g.cur_date + INTERVAL '1 day',
                g.next_date - INTERVAL '1 day',
                INTERVAL '1 day'
            ) AS gs(d) ON TRUE
            WHERE EXTRACT(ISODOW FROM gs.d) BETWEEN 1 AND 5
        ),
        weekday_gaps AS (
            SELECT cur_date, next_date, MIN(d)::date AS first_weekday_missing
            FROM weekdays_between
            GROUP BY cur_date, next_date
        )
        SELECT
            (SELECT first_date FROM cov) AS first_date,
            (SELECT last_date  FROM cov) AS last_date,
            (SELECT cnt        FROM cov) AS cnt,
            EXISTS (SELECT 1 FROM weekday_gaps) AS has_weekday_gaps,
            (SELECT MIN(first_weekday_missing) FROM weekday_gaps) AS first_missing_weekday
        """
    )
    res = await session.execute(sql.bindparams(symbol=symbol, date_from=date_from, date_to=date_to))
    row = cast(Mapping[str, Any], res.mappings().first() or {})
    return dict(row)


async def ensure_coverage(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> None:
    """Ensure price data coverage for symbols.

    For each symbol the function acquires an advisory lock, checks coverage
    with weekday-aware gap detection and fetches the minimal range required to
    bring the database up to date including ``refetch_days`` worth of recent
    history.
    """

    for symbol in symbols:
        async with session.begin():
            await advisory_lock(session, symbol)  # type: ignore[arg-type]

        cov = await _get_coverage(session, symbol, date_from, date_to)

        last_date: Optional[date] = cov.get("last_date")
        first_date: Optional[date] = cov.get("first_date")
        has_gaps: bool = bool(cov.get("has_weekday_gaps") or cov.get("has_gaps"))
        first_missing_weekday: Optional[date] = cov.get("first_missing_weekday")

        if last_date:
            c1 = max(date_from, last_date - timedelta(days=refetch_days))
        else:
            c1 = date_from

        if has_gaps:
            if first_missing_weekday:
                c2 = max(date_from, first_missing_weekday)
            else:
                c2 = date_from
        else:
            c2 = None

        c3 = date_from if (first_date and first_date > date_from) else None

        start = min([c for c in (c1, c2, c3) if c is not None])

        df = await fetch_prices_df(symbol=symbol, start=start, end=date_to)
        if df is None or df.empty:
            continue
        rows = df_to_rows(df, symbol=symbol, source="yfinance")
        if not rows:
            continue
        up_sql = text(upsert_prices_sql())
        await session.execute(up_sql, rows)


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
