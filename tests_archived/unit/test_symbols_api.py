from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.main import app


def test_symbols_active_param_is_boolean():
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = [SimpleNamespace(symbol="AAA")]
    session.execute.return_value = result

    async def override_get_session():
        return session

    app.dependency_overrides[get_session] = override_get_session

    client = TestClient(app)
    response = client.get("/v1/symbols?active=true")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "AAA"

    session.execute.assert_called_once()
    args, _ = session.execute.call_args
    assert args[1]["active"] is True

    app.dependency_overrides.clear()
