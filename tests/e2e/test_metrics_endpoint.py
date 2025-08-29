from datetime import date

from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.main import app


class FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows


class FakeSession:
    async def execute(self, sql, params=None):
        rows = [
            {"symbol": "META", "date": date(2024, 1, 1), "close": 100.0},
            {"symbol": "META", "date": date(2024, 1, 2), "close": 110.0},
            {"symbol": "META", "date": date(2024, 1, 3), "close": 120.0},
        ]
        return FakeResult(rows)


async def override_get_session():
    return FakeSession()


def test_metrics_endpoint_returns_metrics(monkeypatch):
    app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr("app.api.v1.metrics.normalize.normalize_symbol", lambda s: s)

    with TestClient(app) as client:
        response = client.get(
            "/v1/metrics",
            params={"symbols": "META", "from": "2024-01-01", "to": "2024-01-03"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    item = data[0]
    assert item["symbol"] == "META"
    assert isinstance(item["cagr"], (int, float))
    assert isinstance(item["stdev"], (int, float))
    assert isinstance(item["max_drawdown"], (int, float))
    assert isinstance(item["n_days"], int)
