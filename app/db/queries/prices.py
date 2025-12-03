"""Price related database queries."""

from typing import List, Sequence
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _has_symbol_changes(session: AsyncSession, symbols: Sequence[str]) -> bool:
    """Check if any symbol_changes exist for the given symbols (fast check)."""
    res = await session.execute(
        text("SELECT 1 FROM symbol_changes WHERE new_symbol = ANY(:symbols) LIMIT 1"),
        {"symbols": list(symbols)}
    )
    return res.first() is not None


async def get_prices_resolved(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
) -> List[dict]:
    """Fetch price rows via direct SQL query for multiple symbols.
    
    Optimized: Uses simple query when no symbol_changes exist (common case).
    """
    
    # Fast path: if no symbol_changes exist for these symbols, use simple query
    has_changes = await _has_symbol_changes(session, symbols)
    
    if not has_changes:
        # Simple query without UNION (much faster for common case)
        simple_sql = text("""
            SELECT
                symbol,
                date,
                open::double precision,
                high::double precision,
                low::double precision,
                close::double precision,
                volume,
                source,
                last_updated,
                NULL::text AS source_symbol
            FROM prices
            WHERE symbol = ANY(:symbols)
              AND date BETWEEN :date_from AND :date_to
            ORDER BY symbol, date
        """)
        res = await session.execute(simple_sql, {
            "symbols": list(symbols),
            "date_from": date_from,
            "date_to": date_to
        })
        return [dict(m) for m in res.mappings().all()]

    # Full query with UNION for symbol_changes support
    sql = text("""
        SELECT DISTINCT
            pr.symbol,
            pr.date,
            pr.open::double precision,
            pr.high::double precision,
            pr.low::double precision,
            pr.close::double precision,
            pr.volume,
            pr.source,
            pr.last_updated,
            pr.source_symbol
        FROM (
            SELECT p.symbol,
                   p.date,
                   p.open,
                   p.high,
                   p.low,
                   p.close,
                   p.volume,
                   p.source,
                   p.last_updated,
                   NULL::text AS source_symbol,
                   sc.old_symbol,
                   sc.new_symbol,
                   sc.change_date
              FROM prices p
         LEFT JOIN symbol_changes sc ON sc.new_symbol = p.symbol
             WHERE p.symbol = ANY(:symbols)
               AND p.date BETWEEN :date_from AND :date_to
               AND (sc.change_date IS NULL OR p.date >= sc.change_date)

            UNION ALL

            SELECT unnest(:symbols) AS symbol,
                   p.date,
                   p.open,
                   p.high,
                   p.low,
                   p.close,
                   p.volume,
                   p.source,
                   p.last_updated,
                   p.symbol AS source_symbol,
                   sc.old_symbol,
                   sc.new_symbol,
                   sc.change_date
              FROM prices p
              JOIN symbol_changes sc ON sc.old_symbol = p.symbol
             WHERE sc.new_symbol = ANY(:symbols)
               AND p.date BETWEEN :date_from AND :date_to
               AND p.date < sc.change_date
        ) pr
        ORDER BY pr.symbol, pr.date;
    """)
    
    res = await session.execute(sql, {"symbols": list(symbols), "date_from": date_from, "date_to": date_to})
    return [dict(m) for m in res.mappings().all()]


async def _symbol_has_any_prices(session: AsyncSession, symbol: str) -> bool:
    """Return True if any price rows exist for the symbol (any date)."""
    import inspect
    res = await session.execute(text("SELECT 1 FROM prices WHERE symbol = :symbol LIMIT 1"), {"symbol": symbol})
    first = getattr(res, "first", None)
    row = first() if callable(first) else None
    if inspect.isawaitable(row):
        row = await row
    return row is not None
