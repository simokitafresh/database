"""Price retrieval endpoint implementation.

This module provides a minimal `/v1/prices` endpoint that orchestrates
symbol normalisation, symbol change resolution, data fetching and UPSERT
preparation.  The actual database queries and network access are expected to
be mocked in unit tests; this file only wires the components together and
performs input validation.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.utils import advisory_lock

from app.api.deps import get_session
from app.api.errors import raise_http_error
from app.core.config import settings
from app.schemas.prices import PriceRowOut
from app.services import fetcher, normalize, resolver, upsert


router = APIRouter()


def _as_mapping(row: object) -> dict:  # pragma: no cover - helper
    """Convert SQLAlchemy row/namespace/dict into a mapping."""

    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    if isinstance(row, dict):
        return row
    return {k: getattr(row, k) for k in row.__dict__}


@router.get("/prices", response_model=list[PriceRowOut])
async def get_prices(
    symbols: str = Query(..., description="Comma separated symbols"),
    from_: date = Query(..., alias="from"),
    to: date = Query(..., alias="to"),
    session: AsyncSession = Depends(get_session),
) -> List[PriceRowOut]:
    """Return price rows for the requested symbols and date range.

    The implementation purposely keeps the logic minimal; database and network
    operations are represented by calls to service functions which are mocked
    in tests.  Validation focuses on symbol count, date ordering and maximum
    number of returned rows.
    """

    if to < from_:
        raise_http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "'from' must be on or before 'to'",
        )

    symbol_list = [normalize.normalize_symbol(s) for s in symbols.split(",") if s]
    if len(symbol_list) > settings.API_MAX_SYMBOLS:
        raise_http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "too many symbols requested",
        )

    all_rows: List[PriceRowOut] = []
    start: date = from_
    end: date = to

    did_upsert = False
    for sym in symbol_list:
        # Resolve potential symbol changes into actual segments once
        pre_segments = resolver.segments_for(sym, start, end, [])
        if not pre_segments:
            continue
        # Serialise concurrent fetches per symbol
        conn = await session.connection()
        await advisory_lock(conn, sym)
        # After obtaining the lock, check existing DB coverage for each segment
        for actual, seg_from, seg_to in pre_segments:
            cov = await session.execute(
                text(
                    "SELECT min(date) AS first_date, max(date) AS last_date, count(*) AS n_rows "
                    "FROM prices WHERE symbol = :sym AND date BETWEEN :f AND :t"
                ),
                {"sym": actual, "f": seg_from, "t": seg_to},
            )
            cov_row = getattr(cov, "mappings", lambda: None)()
            cov_row = cov_row.first() if cov_row else None
            first_date = cov_row["first_date"] if cov_row else None
            last_date = cov_row["last_date"] if cov_row else None

            gap_q = text(
                """
                WITH seg AS (
                  SELECT date
                    FROM prices
                   WHERE symbol = :sym
                     AND date BETWEEN :f AND :t
                   ORDER BY date
                ),
                pairs AS (
                  SELECT
                    date                                  AS d1,
                    LEAD(date) OVER (ORDER BY date)       AS d2
                  FROM seg
                )
                SELECT MIN((d1 + INTERVAL '1 day')::date) AS missing_from
                  FROM pairs
                 WHERE d2 IS NOT NULL
                   AND (
                        (d2 - d1) = INTERVAL '2 day'
                     OR ((d2 - d1) = INTERVAL '3 day' AND EXTRACT(ISODOW FROM d1) <> 5)
                     OR  (d2 - d1) > INTERVAL '3 day'
                   )
                """
            )
            gap_res = await session.execute(gap_q, {"sym": actual, "f": seg_from, "t": seg_to})
            missing_from = getattr(gap_res, "scalar_one_or_none", lambda: None)()
            if not isinstance(missing_from, date):
                missing_from = None

            overlap = timedelta(days=getattr(settings, "YF_REFETCH_DAYS", 7))
            fetch_start: date | None = None

            if first_date is None:
                fetch_start = seg_from
            elif first_date > seg_from:
                fetch_start = seg_from
            elif missing_from is not None:
                fetch_start = max(seg_from, missing_from - overlap)
            elif last_date is None or last_date < seg_to:
                base = seg_from if last_date is None else max(seg_from, last_date - overlap)
                fetch_start = base
            else:
                fetch_start = None

            if fetch_start is None or fetch_start > seg_to:
                continue

            df = fetcher.fetch_prices(actual, fetch_start, seg_to, settings=settings)
            rows = upsert.df_to_rows(df, symbol=actual, source="yfinance")
            if rows:
                sql = upsert.upsert_prices_sql()
                await session.execute(sql, rows)
                did_upsert = True

    # Persist fetched rows when autocommit is disabled
    if did_upsert:
        await session.commit()

    if not symbol_list:
        return []
    params = {"from": start, "to": end}
    parts: list[str] = []
    for i, sym in enumerate(symbol_list):
        key = f"sym{i}"
        parts.append(
            "SELECT symbol, date, open, high, low, close, volume, source, last_updated, source_symbol "
            f"FROM get_prices_resolved(:{key}, :from, :to)"
        )
        params[key] = sym
    sql = " UNION ALL ".join(parts) + " ORDER BY symbol, date"
    result = await session.execute(text(sql), params)
    rows_list: List[object] = list(result.fetchall())

    if len(rows_list) > settings.API_MAX_ROWS:
        raise_http_error(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "result set too large"
        )

    return [PriceRowOut(**_as_mapping(r)) for r in rows_list]


__all__ = ["router", "get_prices"]
