from __future__ import annotations

"""Dependency injection utilities for FastAPI routers."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.engine import create_engine_and_sessionmaker

# Initialize engine and session factory at import time using settings
settings = Settings()
_engine, SessionLocal = create_engine_and_sessionmaker(settings.DATABASE_URL)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` for request handlers.

    This function is intended to be used with ``Depends`` in FastAPI routes.
    It provides a SQLAlchemy ``AsyncSession`` bound to the application's
    engine and ensures proper cleanup after the request.
    """

    async with SessionLocal() as session:
        yield session


__all__ = ["get_session", "SessionLocal"]
