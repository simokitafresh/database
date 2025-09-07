from unittest.mock import AsyncMock
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import app.api.v1.prices as prices
from app.api.deps import get_session
from app.core.config import settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    async def override_get_session():
        # Create a mock session with proper context manager support
        session = AsyncMock()
        
        @asynccontextmanager
        async def begin():
            yield session
        
        session.begin = begin
        return session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_prices_rejects_too_many_symbols(client: TestClient) -> None:
    resp = client.get(
        "/v1/prices",
        params={"symbols": "A,B,C,D,E,F", "from": "2024-01-01", "to": "2024-01-02"},
    )
    assert resp.status_code == 422


def test_prices_returns_413_when_rows_exceed_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prices.queries, "ensure_coverage", AsyncMock(), raising=False)
    monkeypatch.setattr(
        prices.queries,
        "get_prices_resolved",
        AsyncMock(return_value=[{}, {}]),
        raising=False,
    )
    monkeypatch.setattr(settings, "API_MAX_ROWS", 1)

    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2024-01-01", "to": "2024-01-02"},
    )
    assert resp.status_code == 413


def test_prices_empty_symbols_returns_empty_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ec = AsyncMock()
    gr = AsyncMock()
    monkeypatch.setattr(prices.queries, "ensure_coverage", ec, raising=False)
    monkeypatch.setattr(prices.queries, "get_prices_resolved", gr, raising=False)

    resp = client.get(
        "/v1/prices",
        params={"symbols": "", "from": "2024-01-01", "to": "2024-01-02"},
    )
    assert resp.status_code == 200
    assert resp.json() == []
    ec.assert_not_called()
    gr.assert_not_called()


def test_prices_fallback_before_oldest_date(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that API naturally trims response when 'from' is before oldest available date."""
    
    # Disable auto registration to avoid database calls
    monkeypatch.setattr(settings, "ENABLE_AUTO_REGISTRATION", False)
    
    # Mock ensure_coverage to do nothing
    ensure_coverage_mock = AsyncMock()
    monkeypatch.setattr(prices.queries, "ensure_coverage", ensure_coverage_mock, raising=False)
    
    # Mock get_prices_resolved to return data from oldest date onwards
    mock_data = [
        {
            'symbol': 'AAPL',
            'date': '2020-01-02',  # Oldest available date
            'open': 100.0,
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': '2024-01-01T00:00:00Z',
            'source_symbol': 'AAPL'
        },
        {
            'symbol': 'AAPL',
            'date': '2020-01-03',
            'open': 103.0,
            'high': 107.0,
            'low': 102.0,
            'close': 106.0,
            'volume': 1100000,
            'source': 'yfinance',
            'last_updated': '2024-01-01T00:00:00Z',
            'source_symbol': 'AAPL'
        }
    ]
    
    get_prices_mock = AsyncMock(return_value=mock_data)
    monkeypatch.setattr(prices.queries, "get_prices_resolved", get_prices_mock, raising=False)
    
    # Request with from date before oldest available date
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2019-01-01", "to": "2021-12-31"},
    )
    
    assert resp.status_code == 200
    response_data = resp.json()
    
    # Verify response contains data from oldest date onwards
    assert len(response_data) == 2
    assert response_data[0]['date'] == '2020-01-02'  # Oldest available date
    assert response_data[1]['date'] == '2020-01-03'


def test_prices_empty_when_both_dates_before_oldest(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that API returns empty array when both from and to are before oldest date."""
    
    # Disable auto registration to avoid database calls
    monkeypatch.setattr(settings, "ENABLE_AUTO_REGISTRATION", False)
    
    # Mock ensure_coverage to do nothing
    ensure_coverage_mock = AsyncMock()
    monkeypatch.setattr(prices.queries, "ensure_coverage", ensure_coverage_mock, raising=False)
    
    # Mock get_prices_resolved to return empty array
    get_prices_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(prices.queries, "get_prices_resolved", get_prices_mock, raising=False)
    
    # Request with both dates before oldest available date
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2018-01-01", "to": "2019-12-31"},
    )
    
    assert resp.status_code == 200
    response_data = resp.json()
    
    # Verify empty response
    assert len(response_data) == 0
    assert response_data == []


def test_prices_boundary_values_on_oldest_date(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test boundary value cases around the oldest available date."""
    
    # Disable auto registration to avoid database calls
    monkeypatch.setattr(settings, "ENABLE_AUTO_REGISTRATION", False)
    
    # Mock ensure_coverage to do nothing
    ensure_coverage_mock = AsyncMock()
    monkeypatch.setattr(prices.queries, "ensure_coverage", ensure_coverage_mock, raising=False)
    
    # Test Case 1: from=oldest_date, to=oldest_date (single day on oldest date)
    mock_data_single = [
        {
            'symbol': 'AAPL',
            'date': '2020-01-02',  # Oldest available date
            'open': 100.0,
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': '2024-01-01T00:00:00Z',
            'source_symbol': 'AAPL'
        }
    ]
    
    get_prices_mock = AsyncMock(return_value=mock_data_single)
    monkeypatch.setattr(prices.queries, "get_prices_resolved", get_prices_mock, raising=False)
    
    # Request for single day (oldest date)
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2020-01-02", "to": "2020-01-02"},
    )
    
    assert resp.status_code == 200
    response_data = resp.json()
    assert len(response_data) == 1
    assert response_data[0]['date'] == '2020-01-02'


def test_prices_boundary_day_before_oldest_to_oldest(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test from=oldest_date-1, to=oldest_date (spanning across oldest date boundary)."""
    
    # Disable auto registration to avoid database calls
    monkeypatch.setattr(settings, "ENABLE_AUTO_REGISTRATION", False)
    
    # Mock ensure_coverage to do nothing
    ensure_coverage_mock = AsyncMock()
    monkeypatch.setattr(prices.queries, "ensure_coverage", ensure_coverage_mock, raising=False)
    
    # Mock data: only oldest date available (2020-01-02)
    mock_data_oldest_only = [
        {
            'symbol': 'AAPL',
            'date': '2020-01-02',  # Oldest available date
            'open': 100.0,
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': '2024-01-01T00:00:00Z',
            'source_symbol': 'AAPL'
        }
    ]
    
    get_prices_mock = AsyncMock(return_value=mock_data_oldest_only)
    monkeypatch.setattr(prices.queries, "get_prices_resolved", get_prices_mock, raising=False)
    
    # Request from day before oldest to oldest date
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2020-01-01", "to": "2020-01-02"},
    )
    
    assert resp.status_code == 200
    response_data = resp.json()
    
    # Should return only oldest date data (2020-01-01 doesn't exist)
    assert len(response_data) == 1
    assert response_data[0]['date'] == '2020-01-02'


def test_prices_boundary_oldest_to_day_after(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test from=oldest_date, to=oldest_date+1 (starting from oldest date)."""
    
    # Disable auto registration to avoid database calls
    monkeypatch.setattr(settings, "ENABLE_AUTO_REGISTRATION", False)
    
    # Mock ensure_coverage to do nothing
    ensure_coverage_mock = AsyncMock()
    monkeypatch.setattr(prices.queries, "ensure_coverage", ensure_coverage_mock, raising=False)
    
    # Mock data: oldest date and next day
    mock_data_two_days = [
        {
            'symbol': 'AAPL',
            'date': '2020-01-02',  # Oldest available date
            'open': 100.0,
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': '2024-01-01T00:00:00Z',
            'source_symbol': 'AAPL'
        },
        {
            'symbol': 'AAPL',
            'date': '2020-01-03',  # Next day
            'open': 103.0,
            'high': 107.0,
            'low': 102.0,
            'close': 106.0,
            'volume': 1100000,
            'source': 'yfinance',
            'last_updated': '2024-01-01T00:00:00Z',
            'source_symbol': 'AAPL'
        }
    ]
    
    get_prices_mock = AsyncMock(return_value=mock_data_two_days)
    monkeypatch.setattr(prices.queries, "get_prices_resolved", get_prices_mock, raising=False)
    
    # Request from oldest date to next day
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2020-01-02", "to": "2020-01-03"},
    )
    
    assert resp.status_code == 200
    response_data = resp.json()
    
    # Should return both days
    assert len(response_data) == 2
    assert response_data[0]['date'] == '2020-01-02'
    assert response_data[1]['date'] == '2020-01-03'


def test_prices_boundary_weekend_handling(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test boundary behavior when oldest date falls on weekend or near weekend."""
    
    # Disable auto registration to avoid database calls
    monkeypatch.setattr(settings, "ENABLE_AUTO_REGISTRATION", False)
    
    # Mock ensure_coverage to do nothing
    ensure_coverage_mock = AsyncMock()
    monkeypatch.setattr(prices.queries, "ensure_coverage", ensure_coverage_mock, raising=False)
    
    # Mock data: oldest date is Monday (2020-01-06, assuming Friday 2020-01-03 was last trading day of previous week)
    mock_data_monday_start = [
        {
            'symbol': 'AAPL',
            'date': '2020-01-06',  # Monday (oldest available)
            'open': 100.0,
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': '2024-01-01T00:00:00Z',
            'source_symbol': 'AAPL'
        }
    ]
    
    get_prices_mock = AsyncMock(return_value=mock_data_monday_start)
    monkeypatch.setattr(prices.queries, "get_prices_resolved", get_prices_mock, raising=False)
    
    # Request spanning weekend before oldest date (Friday to Monday)
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2020-01-03", "to": "2020-01-06"},
    )
    
    assert resp.status_code == 200
    response_data = resp.json()
    
    # Should return only Monday data (weekend and previous days don't exist)
    assert len(response_data) == 1
    assert response_data[0]['date'] == '2020-01-06'
