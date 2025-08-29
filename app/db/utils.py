from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def advisory_lock(conn: AsyncConnection, symbol: str) -> None:
    """Acquire an advisory lock for the given symbol within a transaction.

    Uses PostgreSQL's pg_advisory_xact_lock with hashtext(symbol) to ensure
    that only one transaction can operate on a specific symbol at a time.
    """
    await conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:symbol))"),
        {"symbol": symbol},
    )
