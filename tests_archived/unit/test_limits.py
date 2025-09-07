from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.core import config
from app.db import queries
from app.main import app


class FakeAsyncSession:
    async def execute(self, *args, **kwargs):  # pragma: no cover - minimal stub
        class Result:
            def fetchall(self_inner):
                return []

        return Result()


async def fake_session_dep():
    yield FakeAsyncSession()


def test_row_limit_exceeded(monkeypatch):
    app.dependency_overrides[get_session] = fake_session_dep
    monkeypatch.setattr(config.settings, "API_MAX_ROWS", 1)

    async def fake_ensure_coverage(*args, **kwargs):
        return None

    async def fake_get_prices_resolved(*args, **kwargs):
        return [
            {"symbol": "AAPL", "date": "2024-01-01"},
            {"symbol": "AAPL", "date": "2024-01-02"},
        ]

    monkeypatch.setattr(queries, "ensure_coverage", fake_ensure_coverage)
    monkeypatch.setattr(queries, "get_prices_resolved", fake_get_prices_resolved)

    client = TestClient(app)
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2024-01-01", "to": "2024-01-03"},
    )
    assert resp.status_code == 413
    app.dependency_overrides.clear()


def test_symbol_limit_exceeded(monkeypatch):
    monkeypatch.setattr(config.settings, "API_MAX_SYMBOLS", 1)
    client = TestClient(app)
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL,MSFT", "from": "2024-01-01", "to": "2024-01-02"},
    )
    assert resp.status_code == 422
