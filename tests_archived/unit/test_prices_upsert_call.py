import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

from app.api.deps import get_session
from app.api.v1.prices import router as prices_router
from app.db import queries
from app.services.upsert import df_to_rows, upsert_prices_sql


class FakeAsyncSession:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((query, params))

        class Result:
            def fetchall(self_inner):
                return []

        return Result()


def test_prices_endpoint_triggers_upsert(monkeypatch):
    app = FastAPI()
    app.include_router(prices_router, prefix="/v1")

    fake_session = FakeAsyncSession()

    async def fake_dep():
        yield fake_session

    app.dependency_overrides[get_session] = fake_dep

    async def fake_ensure_coverage(session, symbols, date_from, date_to, refetch_days):
        df = pd.DataFrame(
            {
                "open": [1.0],
                "high": [1.1],
                "low": [0.9],
                "close": [1.05],
                "volume": [100],
            },
            index=pd.to_datetime(["2024-01-01"]),
        )
        rows = df_to_rows(df, symbol=symbols[0], source="yfinance")
        sql = text(upsert_prices_sql())
        await session.execute(sql, rows)

    async def fake_get_prices_resolved(*args, **kwargs):
        return []

    monkeypatch.setattr(queries, "ensure_coverage", fake_ensure_coverage)
    monkeypatch.setattr(queries, "get_prices_resolved", fake_get_prices_resolved)

    client = TestClient(app)
    resp = client.get(
        "/v1/prices",
        params={"symbols": "AAPL", "from": "2024-01-01", "to": "2024-01-02"},
    )
    assert resp.status_code == 200
    assert fake_session.calls, "execute not called"
    query, params = fake_session.calls[0]
    assert isinstance(query, TextClause)
    assert isinstance(params, list) and isinstance(params[0], dict)
