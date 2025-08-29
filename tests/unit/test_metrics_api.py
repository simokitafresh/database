from datetime import date
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.main import app


def _setup_session(rows: list) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute.return_value = result
    return session


def test_metrics_endpoint(monkeypatch, mocker):
    rows = [
        {"symbol": "A", "date": date(2023, 1, 1), "close": 1.0},
        {"symbol": "A", "date": date(2023, 1, 2), "close": 1.1},
    ]

    session = _setup_session(rows)

    async def override_get_session():
        return session

    app.dependency_overrides[get_session] = override_get_session

    compute_mock = mocker.patch(
        "app.api.v1.metrics.compute_metrics",
        return_value=[
            {
                "symbol": "A",
                "cagr": 1.0,
                "stdev": 2.0,
                "max_drawdown": 0.5,
                "n_days": 1,
            }
        ],
    )

    client = TestClient(app)
    resp = client.get("/v1/metrics?symbols=A&from=2023-01-01&to=2023-01-02")
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "symbol": "A",
            "cagr": 1.0,
            "stdev": 2.0,
            "max_drawdown": 0.5,
            "n_days": 1,
        }
    ]

    args, _ = compute_mock.call_args
    assert "A" in args[0]

    app.dependency_overrides.clear()
