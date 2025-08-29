import pandas as pd
from datetime import date
from fastapi.testclient import TestClient
from app.main import app


def test_prices_commits_and_filters(mocker):
    # --- dependency mocks ---
    mocker.patch(
        "app.api.v1.prices.resolver.segments_for",
        return_value=[("AAPL", date(2024, 1, 1), date(2024, 1, 10))],
    )
    mocker.patch(
        "app.api.v1.prices.fetcher.fetch_prices",
        return_value=pd.DataFrame(
            {"Adj Close": [100.0]}, index=pd.to_datetime(["2024-01-01"])
        ),
    )
    mocker.patch("app.api.v1.prices.upsert.df_to_rows", return_value=[("AAPL",)])
    mocker.patch(
        "app.api.v1.prices.upsert.upsert_prices_sql", return_value="INSERT ..."
    )

    calls = {"committed": False, "queries": []}

    class _MapWrap:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeResult:
        def __init__(self, rows=None):
            self._rows = rows or []

        def fetchall(self):
            return self._rows

        def mappings(self):
            return _MapWrap(self._rows)

    class FakeSession:
        async def execute(self, sql, params=None):
            s = str(sql)
            calls["queries"].append(s)
            if "get_prices_resolved" in s:
                rows = [
                    {
                        "symbol": "AAPL",
                        "date": pd.Timestamp("2024-01-01"),
                        "open": 100.0,
                        "high": 100.0,
                        "low": 100.0,
                        "close": 100.0,
                        "volume": 1,
                        "source": "yfinance",
                        "last_updated": pd.Timestamp("2024-01-01T00:00:00Z"),
                        "source_symbol": None,
                    }
                ]
                return FakeResult(rows)
            return FakeResult()

        async def commit(self):
            calls["committed"] = True

    from app.api.deps import get_session as real_dep

    async def fake_dep():
        yield FakeSession()

    app.dependency_overrides = {real_dep: fake_dep}

    with TestClient(app) as client:
        r = client.get(
            "/v1/prices",
            params={"symbols": "AAPL", "from": "2024-01-01", "to": "2024-01-10"},
        )
        assert r.status_code == 200
        assert calls["committed"] is True
        assert any("get_prices_resolved" in q for q in calls["queries"])
