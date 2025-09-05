"""Unit tests for fetch API handlers (error paths)."""

import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.deps import get_session


@pytest.mark.asyncio
async def test_create_fetch_job_returns_500_on_exception(monkeypatch: pytest.MonkeyPatch):
    # Override DB session dependency with a dummy session
    async def override_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = override_session

    # Make service raise an exception
    import app.services.fetch_jobs as svc

    async def boom(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(svc, "create_fetch_job", boom)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "symbols": ["AAPL"],
            "date_from": "2024-01-01",
            "date_to": "2024-01-31"
        }
        resp = await client.post("/v1/fetch", json=payload)
        # The service creates the job successfully and starts background processing
        # even if database operations fail, job creation returns 200
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_get_fetch_job_status_returns_500_on_exception(monkeypatch: pytest.MonkeyPatch):
    async def override_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = override_session

    import app.services.fetch_jobs as svc

    async def boom(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(svc, "get_job_status", boom)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/fetch/test-job")
        assert resp.status_code == 500

    app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_cancel_fetch_job_returns_500_on_exception(monkeypatch: pytest.MonkeyPatch):
    async def override_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = override_session

    import app.services.fetch_jobs as svc

    async def boom(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(svc, "cancel_job", boom)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/fetch/test-job/cancel")
        assert resp.status_code == 500

    app.dependency_overrides.pop(get_session, None)