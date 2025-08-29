"""Ensure DB coverage recheck avoids redundant fetches."""

from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.main import app


def test_two_requests_only_fetch_once_with_db_recheck(mocker):
    """Two sequential requests should trigger only one upstream fetch."""

    # Resolver always claims the same segment needs fetching
    mocker.patch(
        "app.api.v1.prices.resolver.segments_for",
        return_value=[("AAPL", date(2024, 1, 1), date(2024, 1, 10))],
    )

    # Count fetcher invocations
    fetch_calls = {"n": 0}

    def _fake_fetch(symbol, start, end, *, settings):
        fetch_calls["n"] += 1
        return pd.DataFrame(
            {"Adj Close": [100.0, 101.0]},
            index=pd.to_datetime(["2024-01-09", "2024-01-10"]),
        )

    mocker.patch("app.api.v1.prices.fetcher.fetch_prices", side_effect=_fake_fetch)
    mocker.patch("app.api.v1.prices.upsert.df_to_rows", return_value=[("AAPL",)])
    mocker.patch("app.api.v1.prices.upsert.upsert_prices_sql", return_value="UPSERT")
    mocker.patch("app.api.v1.prices.normalize.normalize_symbol", return_value="AAPL")
    mocker.patch("app.api.v1.prices.advisory_lock", new=mocker.AsyncMock())

    state = {"populated": False}

    class FakeResult:
        def __init__(self, scalar=None, rows=None):
            self._scalar = scalar
            self._rows = rows or []

        def scalar_one_or_none(self):
            return self._scalar

        def fetchall(self):  # pragma: no cover - simple helper
            return self._rows

    class FakeSession:
        async def execute(self, sql, params=None):
            s = str(sql)
            if "max(date) AS last_date" in s:
                if state["populated"]:
                    return FakeResult(scalar=date(2024, 1, 10))
                return FakeResult(scalar=None)
            if "get_prices_resolved" in s:
                rows = [
                    {
                        "symbol": "AAPL",
                        "date": pd.Timestamp("2024-01-10"),
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": 101.0,
                        "volume": 1,
                        "source": "yfinance",
                        "last_updated": pd.Timestamp("2024-01-10T00:00:00Z"),
                        "source_symbol": None,
                    }
                ]
                return FakeResult(rows=rows)
            if sql == "UPSERT":
                return None
            return FakeResult()

        async def connection(self):
            return object()

        async def commit(self):
            state["populated"] = True

    async def override_session():
        yield FakeSession()

    app.dependency_overrides[get_session] = override_session

    with TestClient(app) as client:
        url = "/v1/prices?symbols=AAPL&from=2024-01-01&to=2024-01-10"
        r1 = client.get(url)
        r2 = client.get(url)
        assert r1.status_code == 200
        assert r2.status_code == 200

    assert fetch_calls["n"] == 1
    app.dependency_overrides.clear()

