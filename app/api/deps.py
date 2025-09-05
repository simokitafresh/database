"""Dependency injection utilities for FastAPI routers with optimized connection pooling."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.engine import create_engine_and_sessionmaker


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


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` for request handlers with optimized settings.

    The sessionmaker is created lazily per DSN and cached so tests or runtime
    configuration can swap ``settings.DATABASE_URL``.
    
    Automatically commits transactions on success or rollback on error.
    """

    SessionLocal = _sessionmaker_for(settings.DATABASE_URL)
    async with SessionLocal() as session:
        try:
            yield session
            # Auto-commit the transaction after successful request processing
            if session.in_transaction():
                await session.commit()
        except Exception:
            # Auto-rollback on any error
            if session.in_transaction():
                await session.rollback()
            raise


# Alias for FastAPI dependency injection compatibility
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Alias for get_session() for FastAPI dependency injection."""
    async for session in get_session():
        yield session


def get_settings():
    """Get application settings for dependency injection."""
    return settings


__all__ = ["get_session", "get_db", "get_settings", "_sessionmaker_for"]
