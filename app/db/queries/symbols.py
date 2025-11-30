"""Symbol related database queries."""

from typing import Any, Sequence, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LIST_SYMBOLS_SQL = (
    "SELECT symbol, name, exchange, currency, is_active, first_date, last_date, created_at "
    "FROM symbols "
    "WHERE (:active IS NULL OR is_active = :active) "
    "ORDER BY symbol"
)


async def list_symbols(session: AsyncSession, active: bool | None = None) -> Sequence[Any]:
    """Return symbol metadata optionally filtered by activity."""

    if active is None:
        sql = "SELECT symbol, name, exchange, currency, is_active, first_date, last_date, created_at FROM symbols ORDER BY symbol"
        result = await session.execute(text(sql))
    else:
        sql = "SELECT symbol, name, exchange, currency, is_active, first_date, last_date, created_at FROM symbols WHERE is_active = :active ORDER BY symbol"
        result = await session.execute(text(sql), {"active": active})
    
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]
