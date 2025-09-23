# app/db/queries_optimized.py
"""Optimized database queries for better performance."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, Mapping, cast, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


async def get_coverage_optimized(
    session: AsyncSession,
    symbol: str,
    date_from: date,
    date_to: date,
) -> dict:
    """Optimized coverage calculation with simplified gap detection.

    This function provides the same functionality as _get_coverage but with
    improved performance by using simpler SQL queries.

    Parameters
    ----------
    session : AsyncSession
        Database session
    symbol : str
        Stock symbol
    date_from : date
        Start date
    date_to : date
        End date

    Returns
    -------
    dict
        Coverage information with first_date, last_date, cnt, has_weekday_gaps, first_missing_weekday
    """

    # Step 1: Get basic coverage statistics
    basic_sql = text("""
        SELECT
            MIN(date) AS first_date,
            MAX(date) AS last_date,
            COUNT(*) AS cnt
        FROM prices
        WHERE symbol = :symbol
          AND date BETWEEN :date_from AND :date_to
    """)

    res = await session.execute(basic_sql, {
        "symbol": symbol,
        "date_from": date_from,
        "date_to": date_to
    })

    row = res.first()
    if not row:
        # No data at all
        return {
            "first_date": None,
            "last_date": None,
            "cnt": 0,
            "has_weekday_gaps": False,
            "first_missing_weekday": None
        }

    first_date = row.first_date
    last_date = row.last_date
    cnt = row.cnt

    # Step 2: Check for weekday gaps using a simpler approach
    # Count expected weekdays vs actual data points
    gap_sql = text("""
        WITH date_range AS (
            SELECT
                generate_series(:date_from, :date_to, INTERVAL '1 day')::date AS d
        ),
        expected_weekdays AS (
            SELECT d
            FROM date_range
            WHERE EXTRACT(ISODOW FROM d) BETWEEN 1 AND 5  -- Monday to Friday
        ),
        actual_data AS (
            SELECT DISTINCT date
            FROM prices
            WHERE symbol = :symbol
              AND date BETWEEN :date_from AND :date_to
        )
        SELECT
            (SELECT COUNT(*) FROM expected_weekdays) AS expected_count,
            (SELECT COUNT(*) FROM actual_data) AS actual_count,
            (
                SELECT d
                FROM expected_weekdays ew
                WHERE NOT EXISTS (
                    SELECT 1 FROM actual_data ad WHERE ad.date = ew.d
                )
                ORDER BY d
                LIMIT 1
            ) AS first_missing
    """)

    gap_res = await session.execute(gap_sql, {
        "symbol": symbol,
        "date_from": date_from,
        "date_to": date_to
    })

    gap_row = gap_res.first()
    expected_count = gap_row.expected_count
    actual_count = gap_row.actual_count
    first_missing = gap_row.first_missing

    has_weekday_gaps = actual_count < expected_count

    return {
        "first_date": first_date,
        "last_date": last_date,
        "cnt": cnt,
        "has_weekday_gaps": has_weekday_gaps,
        "first_missing_weekday": first_missing
    }


async def get_coverage_stats_optimized(
    session: AsyncSession,
    symbols: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """Optimized version of coverage statistics for multiple symbols.

    Parameters
    ----------
    session : AsyncSession
        Database session
    symbols : list[str] | None
        List of symbols to check, None for all
    date_from : date | None
        Start date filter
    date_to : date | None
        End date filter

    Returns
    -------
    list[dict]
        List of coverage statistics for each symbol
    """

    # Build the query dynamically
    where_clauses = []
    params = {}

    if symbols:
        where_clauses.append("s.symbol = ANY(:symbols)")
        params["symbols"] = symbols

    if date_from:
        where_clauses.append("COALESCE(p.first_date, s.first_date) >= :date_from")
        params["date_from"] = date_from

    if date_to:
        where_clauses.append("COALESCE(p.last_date, s.last_date) <= :date_to")
        params["date_to"] = date_to

    where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

    sql = f"""
        SELECT
            s.symbol,
            s.name,
            s.exchange,
            s.currency,
            s.is_active,
            COALESCE(p.first_date, s.first_date) AS first_date,
            COALESCE(p.last_date, s.last_date) AS last_date,
            COALESCE(p.data_points, 0) AS data_points,
            s.created_at
        FROM symbols s
        LEFT JOIN (
            SELECT
                symbol,
                MIN(date) AS first_date,
                MAX(date) AS last_date,
                COUNT(*) AS data_points
            FROM prices
            GROUP BY symbol
        ) p ON s.symbol = p.symbol
        WHERE {where_clause}
        ORDER BY s.symbol
    """

    res = await session.execute(text(sql), params)
    return [dict(row) for row in res.mappings()]


__all__ = [
    "get_coverage_optimized",
    "get_coverage_stats_optimized",
]