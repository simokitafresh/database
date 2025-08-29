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
    monkeypatch.setattr(deps, "SessionLocal", session_factory)

    app = FastAPI()

    @app.get("/uses-session")
    async def _endpoint(session: AsyncSession = Depends(deps.get_session)):
        return {"session": session.__class__.__name__}

    client = TestClient(app)
    res = client.get("/uses-session")
    assert res.status_code == 200
    assert res.json()["session"] == "AsyncSession"
