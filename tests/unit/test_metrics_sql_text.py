from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.sql.elements import TextClause

from app.api.deps import get_session
from app.api.v1.metrics import router


class FakeAsyncSession:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((query, params))

        class Result:
            def fetchall(self_inner):
                return []

        return Result()


def test_metrics_query_uses_text_clause_and_expanding():
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    fake_session = FakeAsyncSession()

    async def fake_dep():
        yield fake_session

    app.dependency_overrides[get_session] = fake_dep

    client = TestClient(app)
    resp = client.get(
        "/v1/metrics",
        params={"symbols": "AAPL", "from": "2024-01-01", "to": "2024-01-31"},
    )
    assert resp.status_code == 200
    assert fake_session.calls, "execute not called"
    query, params = fake_session.calls[0]
    assert isinstance(query, TextClause)
    assert isinstance(params["symbols"], tuple)
    assert len(params["symbols"]) == 1
