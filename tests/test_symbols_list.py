from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.deps import get_session


@pytest.mark.asyncio
async def test_symbols_list_returns_serialized_data(async_client, fastapi_app, dummy_session, monkeypatch):
    sample_rows = [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "currency": "USD",
            "is_active": True,
            "first_date": date(2020, 1, 2),
            "last_date": date(2024, 9, 30),
            "created_at": datetime(2024, 9, 30, 12, 30, tzinfo=timezone.utc),
        }
    ]

    mocked_list_symbols = AsyncMock(return_value=sample_rows)
    monkeypatch.setattr("app.api.v1.symbols.db_list_symbols", mocked_list_symbols)

    async def override_session():
        yield dummy_session

    fastapi_app.dependency_overrides[get_session] = override_session

    response = await async_client.get("/v1/symbols")

    assert response.status_code == 200
    assert response.json() == [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "currency": "USD",
            "is_active": True,
            "first_date": "2020-01-02",
            "last_date": "2024-09-30",
            "created_at": "2024-09-30T12:30:00Z",
        }
    ]
    mocked_list_symbols.assert_awaited_once_with(dummy_session, None)
