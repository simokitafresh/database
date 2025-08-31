"""Dependency injection utilities for FastAPI routers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

import uuid
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _normalize_asyncpg_dsn(dsn: str) -> tuple[str, bool]:
    """Normalize asyncpg DSN parameters.

    - Translate/remove libpq-only options (e.g. sslmode) that asyncpg doesn't accept
    - Map sslmode=require -> ssl=true (asyncpg)
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


@lru_cache(maxsize=8)
def _sessionmaker_for(dsn: str) -> async_sessionmaker[AsyncSession]:
    # PgBouncer(transaction/statement) 環境で asyncpg を使う場合の対策:
    #  - prepared statement キャッシュ無効化: prepared_statement_cache_size=0
    #  - 競合回避のため動的名称: prepared_statement_name_func
    #  - アプリ側プール無効化（PgBouncer を前提）: NullPool
    dsn, ssl_required = _normalize_asyncpg_dsn(dsn)
    connect_args = {}
    poolclass = None
    if dsn.startswith("postgresql+asyncpg://"):
        # asyncpg 推奨: PgBouncer(transaction/statement) では statement_cache を無効化
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = (
            lambda: f"__asyncpg_{uuid.uuid4()}__"
        )
        if ssl_required:
            connect_args.setdefault("ssl", True)
        poolclass = NullPool

    engine = create_async_engine(
        dsn,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
        poolclass=poolclass or None,
    )
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
