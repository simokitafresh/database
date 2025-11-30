"""Locking mechanisms for database operations."""

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.redis_utils import symbol_lock

async def with_symbol_lock(session: AsyncSession, symbol: str) -> None:
    """Acquire a distributed lock for the given symbol using Redis.

    This replaces PostgreSQL advisory locks with Redis-based distributed locking
    for better concurrency across multiple application instances.
    """
    async with symbol_lock(symbol):
        pass
