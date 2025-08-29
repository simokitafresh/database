from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_session


class FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows


class FakeSession:
    async def execute(self, sql, params=None):
        if "get_prices_resolved" in str(sql):
            rows = [
                {
                    "symbol": "META",
                    "date": date(2024, 1, 1),
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "volume": 1,
                    "source": "yfinance",
                    "last_updated": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    "source_symbol": "FB",
                },
                {
                    "symbol": "META",
                    "date": date(2024, 1, 2),
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "volume": 1,
                    "source": "yfinance",
                    "last_updated": datetime(2024, 1, 2, tzinfo=timezone.utc),
                    "source_symbol": None,
                },
            ]
            return FakeResult(rows)
        return FakeResult()

    async def commit(self):  # pragma: no cover - no-op
        return None

    async def connection(self):  # pragma: no cover - mocked lock
        return AsyncMock()


async def override_get_session():
    return FakeSession()


def test_prices_endpoint_returns_current_symbol(monkeypatch):
    app.dependency_overrides[get_session] = override_get_session

    monkeypatch.setattr(
        "app.api.v1.prices.normalize.normalize_symbol", lambda s: s
    )
    monkeypatch.setattr(
        "app.api.v1.prices.resolver.segments_for", lambda s, f, t, _: [(s, f, t)]
    )
    monkeypatch.setattr(
        "app.api.v1.prices.fetcher.fetch_prices", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "app.api.v1.prices.upsert.df_to_rows", lambda *a, **kw: []
    )
    monkeypatch.setattr(
        "app.api.v1.prices.upsert.upsert_prices_sql", lambda: "UPSERT"
    )
    monkeypatch.setattr(
        "app.api.v1.prices.advisory_lock", AsyncMock()
    )

    with TestClient(app) as client:
        r = client.get(
            "/v1/prices", params={"symbols": "META", "from": "2024-01-01", "to": "2024-01-02"}
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert all(row["symbol"] == "META" for row in data)
        assert data[0]["source_symbol"] == "FB"
        assert data[1]["source_symbol"] is None

    app.dependency_overrides.clear()
