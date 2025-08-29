from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.api.deps import get_session
import app.api.v1.prices as prices


@pytest.fixture
def client() -> TestClient:
    async def override_get_session():
        return object()

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
    monkeypatch.setattr(prices.queries, "get_prices_resolved", AsyncMock(return_value=[{}, {}]), raising=False)
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

