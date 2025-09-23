from unittest.mock import AsyncMock

import pytest

from app.api.deps import get_session


@pytest.mark.asyncio
async def test_coverage_invalid_sort_field_returns_400(async_client, fastapi_app, dummy_session, monkeypatch):
    mocked_get_coverage = AsyncMock()
    monkeypatch.setattr("app.api.v1.coverage.get_coverage_stats", mocked_get_coverage)

    async def override_session():
        yield dummy_session

    fastapi_app.dependency_overrides[get_session] = override_session

    response = await async_client.get("/v1/coverage", params={"sort_by": "invalid"})

    assert response.status_code == 400
    payload = response.json()
    error = payload.get("error", {})
    assert error.get("code") == "400"
    assert "INVALID_SORT_FIELD" in error.get("message", "")
    mocked_get_coverage.assert_not_awaited()
