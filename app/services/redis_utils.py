# app/services/redis_utils.py
"""Redis utilities for distributed locking and caching."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Any, AsyncGenerator

import redis.asyncio as redis
from redis.asyncio.lock import Lock as RedisLock

from app.core.config import settings

logger = logging.getLogger(__name__)

# Global Redis client instance
_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> redis.Redis:
    """Get or create Redis client instance."""
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            await _redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            _redis_client = None

    return _redis_client


async def close_redis_client():
    """Close Redis client connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


@asynccontextmanager
async def distributed_lock(
    lock_key: str,
    timeout: int = 30,
    blocking_timeout: float = 10.0,
) -> AsyncGenerator[RedisLock, None]:
    """Distributed lock context manager using Redis.

    Parameters
    ----------
    lock_key : str
        Unique key for the lock
    timeout : int
        Lock timeout in seconds (default: 30)
    blocking_timeout : float
        Maximum time to wait for lock acquisition (default: 10.0)

    Yields
    ------
    RedisLock
        Acquired lock object

    Raises
    ------
    RuntimeError
        If Redis is unavailable and fallback is disabled
    """
    client = await get_redis_client()

    if client is None:
        # Fallback to no locking if Redis is unavailable
        logger.warning(f"Redis unavailable, skipping lock for {lock_key}")

        class DummyLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        yield DummyLock()
        return

    lock = RedisLock(
        client,
        lock_key,
        timeout=timeout,
        blocking_timeout=blocking_timeout,
    )

    try:
        acquired = await lock.acquire()
        if acquired:
            logger.debug(f"Acquired distributed lock: {lock_key}")
            yield lock
        else:
            raise RuntimeError(f"Failed to acquire lock: {lock_key}")
    finally:
        try:
            await lock.release()
            logger.debug(f"Released distributed lock: {lock_key}")
        except Exception as e:
            logger.warning(f"Error releasing lock {lock_key}: {e}")


async def symbol_lock(symbol: str) -> RedisLock:
    """Get a distributed lock for a specific symbol.

    This replaces the PostgreSQL advisory lock with Redis-based distributed locking,
    allowing better concurrency across multiple application instances.

    Parameters
    ----------
    symbol : str
        Stock symbol to lock

    Returns
    -------
    RedisLock
        Distributed lock for the symbol
    """
    lock_key = f"symbol_lock:{symbol.lower()}"
    timeout = getattr(settings, 'REDIS_LOCK_TIMEOUT', 30)
    blocking_timeout = getattr(settings, 'REDIS_LOCK_BLOCKING_TIMEOUT', 10.0)

    async with distributed_lock(lock_key, timeout, blocking_timeout) as lock:
        yield lock


# Redis configuration defaults
class RedisSettings:
    """Redis configuration with defaults."""

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_LOCK_TIMEOUT: int = 30
    REDIS_LOCK_BLOCKING_TIMEOUT: float = 10.0


# Update settings with Redis defaults if not already present
for attr in dir(RedisSettings):
    if not attr.startswith('_') and not hasattr(settings, attr):
        setattr(settings, attr, getattr(RedisSettings, attr))


__all__ = [
    "get_redis_client",
    "close_redis_client",
    "distributed_lock",
    "symbol_lock",
]