"""Price related database queries."""

from typing import List, Sequence
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

async def get_prices_resolved(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
) -> List[dict]:
    """Fetch price rows via direct SQL query for multiple symbols."""

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
