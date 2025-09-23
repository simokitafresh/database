from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.services.redis_utils import distributed_lock


@asynccontextmanager
async def advisory_lock(symbol: str) -> AsyncGenerator[None, None]:
    """Acquire a distributed lock for the given symbol using Redis.

    This replaces PostgreSQL advisory locks with Redis-based distributed locking
    for better concurrency across multiple application instances.

    Parameters
    ----------
    symbol : str
        Stock symbol to lock

    Yields
    ------
    None
        Lock is held during the context
    """
    lock_key = f"symbol_lock:{symbol.lower()}"

    async with distributed_lock(lock_key, timeout=30, blocking_timeout=10.0):
        yield
