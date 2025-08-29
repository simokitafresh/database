"""Database engine and session factory for async SQLAlchemy."""

from __future__ import annotations

from typing import Tuple

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine_and_sessionmaker(
    database_url: str,
) -> Tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create async SQLAlchemy engine and session factory.

    Args:
        database_url: Database URL including asyncpg driver.

    Returns:
        Tuple of async engine and sessionmaker.
    """

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


__all__ = ["create_engine_and_sessionmaker"]
