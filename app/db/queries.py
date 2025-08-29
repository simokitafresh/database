from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    "get_prices_resolved",
    "list_symbols",
    "GET_PRICES_RESOLVED_SQL",
    "LIST_SYMBOLS_SQL",
]
