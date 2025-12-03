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


def _count_weekdays(start: date, end: date) -> int:
    """Count weekdays (Mon-Fri) between two dates inclusive.
    
    Pure Python calculation - no database query needed.
    """
    if start > end:
        return 0
    
    total_days = (end - start).days + 1
    full_weeks = total_days // 7
    remaining_days = total_days % 7
    
    weekdays = full_weeks * 5
    
    # Count remaining days
    current = start + timedelta(days=full_weeks * 7)
    for _ in range(remaining_days):
        if current.weekday() < 5:  # Mon=0 to Fri=4
            weekdays += 1
        current += timedelta(days=1)
    
    return weekdays


async def get_coverage_optimized(
    session: AsyncSession,
    symbol: str,
    date_from: date,
    date_to: date,
) -> dict:
    """Optimized coverage calculation with simplified gap detection.

    This function provides the same functionality as _get_coverage but with
    improved performance by using simpler SQL queries.
    
    Optimization: Uses Python for weekday counting instead of generate_series.

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

    # Single optimized query - no generate_series, no NOT EXISTS
    sql = text("""
        SELECT
            MIN(date) AS first_date,
            MAX(date) AS last_date,
            COUNT(*) AS cnt
        FROM prices
        WHERE symbol = :symbol
          AND date BETWEEN :date_from AND :date_to
    """)

    res = await session.execute(sql, {
        "symbol": symbol,
        "date_from": date_from,
        "date_to": date_to
    })

    row = res.first()
    if not row or row.cnt == 0:
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

    # Calculate expected weekdays in Python (much faster than generate_series)
    expected_count = _count_weekdays(date_from, date_to)
    
    # Simple gap detection: if actual < expected, there are gaps
    # Note: This doesn't account for market holidays, but matches previous behavior
    has_weekday_gaps = cnt < expected_count
    
    # For first_missing_weekday, only query if gaps exist (lazy evaluation)
    first_missing = None
    if has_weekday_gaps:
        # Only fetch first missing date when needed
        missing_sql = text("""
            WITH actual_dates AS (
                SELECT DISTINCT date FROM prices
                WHERE symbol = :symbol AND date BETWEEN :date_from AND :date_to
            )
            SELECT d::date AS missing_date
            FROM generate_series(:date_from, :date_to, INTERVAL '1 day') AS d
            WHERE EXTRACT(ISODOW FROM d) BETWEEN 1 AND 5
              AND d::date NOT IN (SELECT date FROM actual_dates)
            ORDER BY d
            LIMIT 1
        """)
        missing_res = await session.execute(missing_sql, {
            "symbol": symbol,
            "date_from": date_from,
            "date_to": date_to
        })
        missing_row = missing_res.first()
        if missing_row:
            first_missing = missing_row.missing_date

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