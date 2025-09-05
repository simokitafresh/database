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
from sqlalchemy.pool import NullPool, StaticPool


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
    pool_size: int = 5,  # Reduced for cloud deployment
    max_overflow: int = 5,  # Reduced for cloud deployment
    pool_pre_ping: bool = True,
    pool_recycle: int = 1800,  # Reduced to 30 minutes for cloud
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
        
        # Supabase接続の最適化（基本設定のみ）
        # Note: command_timeout and server_lifetime are not supported by Supabase pooler
        
        if ssl_required:
            connect_args.setdefault("ssl", True)
        
        # Use NullPool for cloud deployment with connection poolers
        if "supabase.com" in database_url or "pgbouncer" in database_url.lower() or pool_size <= 1:
            poolclass = NullPool
        
    elif database_url.startswith("postgresql+psycopg://"):
        # psycopgドライバー（同期）の場合
        if "supabase.com" in database_url:
            connect_args["sslmode"] = "require"
        else:
            connect_args["sslmode"] = "disable"
    
    elif database_url.startswith("sqlite"):
        # SQLite doesn't support pool settings
        poolclass = None
        pool_size = None
        max_overflow = None

    # Engine configuration with optimized pool settings
    engine_kwargs = {
        "connect_args": connect_args,
        "echo": echo,
    }
    
    # Add pool settings only for databases that support them
    if not database_url.startswith("sqlite"):
        engine_kwargs.update({
            "pool_pre_ping": pool_pre_ping,
            "pool_recycle": pool_recycle,
        })
        
        # Add pool settings only if not using NullPool
        if poolclass != NullPool:
            engine_kwargs.update({
                "pool_size": pool_size,
                "max_overflow": max_overflow,
            })
        else:
            engine_kwargs["poolclass"] = poolclass
    else:
        # SQLite-specific settings
        engine_kwargs.update({
            "poolclass": StaticPool,
            "connect_args": {**connect_args, "check_same_thread": False}
        })

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
