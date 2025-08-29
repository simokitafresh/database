"""Dependency injection utilities for FastAPI routers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


@lru_cache(maxsize=8)
def _sessionmaker_for(dsn: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(dsn, future=True, pool_pre_ping=True)
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` for request handlers.

    The sessionmaker is created lazily per DSN and cached so tests or runtime
    configuration can swap ``settings.DATABASE_URL``.
    """

    SessionLocal = _sessionmaker_for(settings.DATABASE_URL)
    async with SessionLocal() as session:
        yield session


__all__ = ["get_session", "_sessionmaker_for"]
