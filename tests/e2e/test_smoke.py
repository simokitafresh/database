from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.main import app


class FakeAsyncSession:
    async def execute(self, *args, **kwargs):  # pragma: no cover - minimal stub
        class Result:
            def fetchall(self_inner):
                return []

        return Result()


async def fake_session_dep():
    yield FakeAsyncSession()


def test_health_and_symbols_smoke():
    app.dependency_overrides[get_session] = fake_session_dep
    client = TestClient(app)
    try:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        resp2 = client.get("/v1/symbols")
        assert resp2.status_code == 200
        assert resp2.json() == []
    finally:
        app.dependency_overrides.clear()
