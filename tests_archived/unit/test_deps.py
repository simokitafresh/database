from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import deps


@pytest.mark.anyio
async def test_get_session_dependency(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def fake_sessionmaker_for(dsn: str):  # pragma: no cover - assertion ensures call
        assert dsn == "sqlite+aiosqlite:///:memory:"
        return session_factory

    monkeypatch.setattr(deps, "_sessionmaker_for", fake_sessionmaker_for)
    monkeypatch.setattr(deps.settings, "DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    app = FastAPI()

    @app.get("/uses-session")
    async def _endpoint(session: AsyncSession = Depends(deps.get_session)):
        return {"session": session.__class__.__name__}

    client = TestClient(app)
    res = client.get("/uses-session")
    assert res.status_code == 200
    assert res.json()["session"] == "AsyncSession"
