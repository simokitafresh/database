"""Dependency injection utilities for FastAPI routers with optimized connection pooling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker

logger = logging.getLogger(__name__)

# Retry configuration for transient connection errors
MAX_SESSION_RETRIES = 3
RETRY_DELAY_SECONDS = 0.3


@lru_cache(maxsize=8)
def _sessionmaker_for(dsn: str) -> async_sessionmaker[AsyncSession]:
    """Create optimized sessionmaker with connection pool settings."""
    engine, sessionmaker = create_engine_and_sessionmaker(
        database_url=dsn,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        pool_recycle=settings.DB_POOL_RECYCLE,
        echo=settings.DB_ECHO
    )
    return sessionmaker


def _is_transient_error(error: Exception) -> bool:
    """Check if an error is a transient connection error that can be retried."""
    error_msg = str(error).lower()
    transient_patterns = [
        "connection was closed",
        "connection does not exist",
        "connection refused",
        "connection reset",
        "connection timed out",
        "server closed the connection",
        "pool timeout",
        "cannot acquire connection",
    ]
    return any(pattern in error_msg for pattern in transient_patterns)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` for request handlers with retry logic.

    The sessionmaker is created lazily per DSN and cached so tests or runtime
    configuration can swap ``settings.DATABASE_URL``.
    
    Includes retry logic for transient connection errors common with
    Supabase Pooler (PgBouncer) in NullPool mode.
    
    Automatically commits transactions on success or rollback on error.
    """
    SessionLocal = _sessionmaker_for(settings.DATABASE_URL)
    last_error: Exception | None = None
    
    for attempt in range(MAX_SESSION_RETRIES):
        try:
            async with SessionLocal() as session:
                try:
                    yield session
                    # Auto-commit the transaction after successful request processing
                    if session.in_transaction():
                        await session.commit()
                    return  # Success, exit the retry loop
                except Exception as e:
                    # Auto-rollback on any error
                    if session.in_transaction():
                        await session.rollback()
                    raise
        except SQLAlchemyError as e:
            last_error = e
            if _is_transient_error(e) and attempt < MAX_SESSION_RETRIES - 1:
                logger.warning(
                    f"Transient DB connection error (attempt {attempt + 1}/{MAX_SESSION_RETRIES}): {e}"
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            raise
        except Exception as e:
            # For non-SQLAlchemy errors, check if they're connection-related
            if _is_transient_error(e) and attempt < MAX_SESSION_RETRIES - 1:
                last_error = e
                logger.warning(
                    f"Transient connection error (attempt {attempt + 1}/{MAX_SESSION_RETRIES}): {e}"
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            raise
    
    # If we exhausted all retries
    if last_error:
        raise last_error


# Alias for FastAPI dependency injection compatibility
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Alias for get_session() for FastAPI dependency injection."""
    async for session in get_session():
        yield session


def get_settings():
    """Get application settings for dependency injection."""
    return settings


__all__ = ["get_session", "get_db", "get_settings", "_sessionmaker_for"]
