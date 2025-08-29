from datetime import date
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_session
from app.core.config import settings


def _setup_session(rows: list) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute.return_value = result
    conn = AsyncMock()
    session.connection.return_value = conn
    return session


def test_symbol_limit_exceeded_returns_422_with_message(monkeypatch):
    session = _setup_session([])

    async def override_get_session():
        return session

    app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr(settings, "API_MAX_SYMBOLS", 1)

    client = TestClient(app)
    resp = client.get("/v1/prices?symbols=A,B&from=2023-01-01&to=2023-01-10")
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["message"] == "too many symbols requested"

    app.dependency_overrides.clear()


def test_row_limit_exceeded_returns_413_with_message(monkeypatch, mocker):
    row = {
        "symbol": "A",
        "date": date(2023, 1, 1),
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1,
        "source": "s",
        "last_updated": date(2023, 1, 1),
        "source_symbol": None,
    }

    session = _setup_session([row, row])

    async def override_get_session():
        return session

    app.dependency_overrides[get_session] = override_get_session

    mocker.patch("app.api.v1.prices.normalize.normalize_symbol", return_value="A")
    mocker.patch(
        "app.api.v1.prices.resolver.segments_for",
        return_value=[("A", date(2023, 1, 1), date(2023, 1, 2))],
    )
    mocker.patch("app.api.v1.prices.fetcher.fetch_prices", return_value=None)
    mocker.patch("app.api.v1.prices.upsert.df_to_rows", return_value=[])
    mocker.patch("app.api.v1.prices.upsert.upsert_prices_sql", return_value="")

    monkeypatch.setattr(settings, "API_MAX_ROWS", 1)

    client = TestClient(app)
    resp = client.get("/v1/prices?symbols=A&from=2023-01-01&to=2023-01-02")
    assert resp.status_code == 413
    data = resp.json()
    assert data["error"]["message"] == "result set too large"

    app.dependency_overrides.clear()
