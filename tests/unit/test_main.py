from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.main import app
from app.api.deps import get_session


def test_main_routes(mocker):
    session = AsyncMock()
    exec_result = AsyncMock()
    exec_result.fetchall = mocker.MagicMock(return_value=[])
    session.execute.return_value = exec_result
    app.dependency_overrides[get_session] = lambda: session

    mocker.patch("app.api.v1.prices.resolver.segments_for", return_value=[])
    mocker.patch("app.api.v1.prices.normalize.normalize_symbol", side_effect=lambda s: s)
    mocker.patch("app.api.v1.metrics.normalize.normalize_symbol", side_effect=lambda s: s)
    mocker.patch("app.api.v1.metrics.compute_metrics", return_value=[])

    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    assert (
        client.get("/v1/prices", params={"symbols": "AAA", "from": "2024-01-01", "to": "2024-01-02"}).status_code
        == 200
    )
    assert (
        client.get("/v1/metrics", params={"symbols": "AAA", "from": "2024-01-01", "to": "2024-01-02"}).status_code
        == 200
    )
