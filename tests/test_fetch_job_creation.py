from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.api.deps import get_session


@pytest.mark.asyncio
async def test_fetch_job_creation_triggers_background(async_client, fastapi_app, dummy_session, monkeypatch):
    mocked_create_job = AsyncMock(return_value="job-123")
    mocked_process_job = AsyncMock()
    monkeypatch.setattr("app.api.v1.fetch.create_fetch_job", mocked_create_job)
    monkeypatch.setattr("app.api.v1.fetch.process_fetch_job", mocked_process_job)

    async def override_session():
        yield dummy_session

    fastapi_app.dependency_overrides[get_session] = override_session

    payload = {
        "symbols": ["AAPL", "MSFT"],
        "date_from": "2024-01-01",
        "date_to": "2024-06-01",
        "interval": "1d",
        "force": False,
        "priority": "normal"
    }

    response = await async_client.post("/v1/fetch", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "job-123"
    assert body["status"] == "pending"
    assert body["symbols_count"] == 2
    assert body["date_range"] == {"from": "2024-01-01", "to": "2024-06-01"}

    assert mocked_create_job.await_args.args[0] is dummy_session
    assert mocked_create_job.await_args.args[1].symbols == ["AAPL", "MSFT"]

    mocked_process_job.assert_awaited_once_with(
        job_id="job-123",
        symbols=["AAPL", "MSFT"],
        date_from=date(2024, 1, 1),
        date_to=date(2024, 6, 1),
        interval="1d",
        force=False,
        max_concurrency=2,
    )
