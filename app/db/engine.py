"""Database engine and session factory for async SQLAlchemy."""

from __future__ import annotations

from typing import Tuple
import uuid
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


def _normalize_asyncpg_dsn(dsn: str) -> tuple[str, bool]:
    """Normalize asyncpg DSN to avoid unsupported libpq flags.

    Maps sslmode=require -> ssl=true and removes sslmode for asyncpg URLs.
    """
    if not dsn.startswith("postgresql+asyncpg://"):
        return dsn, False
    parts = urlsplit(dsn)
    ssl_required = False
    if parts.query:
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        sslmode = params.pop("sslmode", None)
        if sslmode and sslmode.lower() != "disable":
            ssl_required = True
        new_query = urlencode(params)
    else:
        new_query = parts.query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)), ssl_required


def create_engine_and_sessionmaker(
    database_url: str,
    pool_size: int = 20,
    max_overflow: int = 10,
    pool_pre_ping: bool = True,
    pool_recycle: int = 3600,
    echo: bool = False
) -> Tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create async SQLAlchemy engine and session factory with optimized pool settings.

    Args:
        database_url: Database URL including asyncpg driver.
        pool_size: Number of connections to maintain in pool (default: 20)
        max_overflow: Maximum overflow connections (default: 10)
        pool_pre_ping: Enable connection health checks (default: True)
        pool_recycle: Connection recycle time in seconds (default: 3600)
        echo: Enable SQL query logging (default: False)

    Returns:
        Tuple of async engine and sessionmaker.
    """

    database_url, ssl_required = _normalize_asyncpg_dsn(database_url)
    connect_args = {}
    poolclass = None
    
    if database_url.startswith("postgresql+asyncpg://"):
        # PgBouncer 対策: asyncpg の statement_cache を無効化
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = (
            lambda: f"__asyncpg_{uuid.uuid4()}__"
        )
        if ssl_required:
            connect_args.setdefault("ssl", True)
        
        # Use default pool for better performance in production
        # Only use NullPool for development or with connection poolers like PgBouncer
        if "pgbouncer" in database_url.lower() or pool_size <= 1:
            poolclass = NullPool
        
    elif database_url.startswith("postgresql+psycopg://"):
        connect_args["sslmode"] = "disable"

    # Engine configuration with optimized pool settings
    engine_kwargs = {
        "connect_args": connect_args,
        "echo": echo,
        "pool_pre_ping": pool_pre_ping,
        "pool_recycle": pool_recycle,
    }
    
    # Add pool settings only if not using NullPool
    if poolclass != NullPool:
        engine_kwargs.update({
            "pool_size": pool_size,
            "max_overflow": max_overflow,
        })
    else:
        engine_kwargs["poolclass"] = poolclass

    engine = create_async_engine(database_url, **engine_kwargs)
    
    # Session factory with optimized settings
    session_factory = async_sessionmaker(
        engine, 
        expire_on_commit=False,
        autoflush=False,  # Better performance, explicit flushes
        autocommit=False
    )
    
    return engine, session_factory


__all__ = ["create_engine_and_sessionmaker"]
