from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.main import app


def _setup_session(rows: list | None = None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows or []

    async def execute(sql, params=None):
        if sql == "UPSERT":
            return None
        return result

    session.execute.side_effect = execute
    conn = AsyncMock()
    session.connection.return_value = conn
    return session


def test_fetcher_called_once(monkeypatch, mocker):
    session = _setup_session()

    async def override_get_session():
        return session

    app.dependency_overrides[get_session] = override_get_session

    state = {"fetched": False}

    def resolver_side_effect(symbol, start, end, _):
        if state["fetched"]:
            return []
        return [(symbol, start, end)]

    def fetcher_side_effect(symbol, start, end, *, settings):
        state["fetched"] = True
        return None

    mocker.patch("app.api.v1.prices.normalize.normalize_symbol", return_value="A")
    mocker.patch(
        "app.api.v1.prices.resolver.segments_for", side_effect=resolver_side_effect
    )
    fetch_mock = mocker.patch(
        "app.api.v1.prices.fetcher.fetch_prices", side_effect=fetcher_side_effect
    )
    mocker.patch("app.api.v1.prices.upsert.df_to_rows", return_value=[])
    mocker.patch("app.api.v1.prices.upsert.upsert_prices_sql", return_value="UPSERT")
    mocker.patch("app.api.v1.prices.advisory_lock", new=AsyncMock())

    client = TestClient(app)
    url = "/v1/prices?symbols=A&from=2023-01-01&to=2023-01-02"
    r1 = client.get(url)
    r2 = client.get(url)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert fetch_mock.call_count == 1

    app.dependency_overrides.clear()

