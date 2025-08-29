"""Ensure interior gaps trigger backfill even when tail is complete."""

from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.main import app


def test_interior_gap_triggers_fetch_even_when_tail_complete(mocker):
    """A missing weekday inside a segment should trigger a fetch."""

    mocker.patch(
        "app.api.v1.prices.resolver.segments_for",
        return_value=[("AAPL", date(2024, 1, 1), date(2024, 1, 10))],
    )

    calls = {"fetch": 0}

    def _fake_fetch(*args, **kwargs):
        calls["fetch"] += 1
        return pd.DataFrame(
            {"Adj Close": [100.0, 101.0, 102.0]},
            index=pd.to_datetime(["2024-01-02", "2024-01-09", "2024-01-10"]),
        )

    mocker.patch("app.api.v1.prices.fetcher.fetch_prices", side_effect=_fake_fetch)
    mocker.patch("app.api.v1.prices.upsert.df_to_rows", return_value=[("AAPL",)])
    mocker.patch("app.api.v1.prices.upsert.upsert_prices_sql", return_value="UPSERT")
    mocker.patch("app.api.v1.prices.advisory_lock", new=mocker.AsyncMock())

    class _MapWrap:
        def __init__(self, rows):
            self._rows = rows

        def first(self):
            return self._rows[0] if self._rows else None

        def all(self):  # pragma: no cover - unused helper
            return self._rows

    class FakeResult:
        def __init__(self, rows=None, scalar=None):
            self._rows = rows or []
            self._scalar = scalar

        def mappings(self):
            return _MapWrap(self._rows)

        def scalar_one_or_none(self):
            return self._scalar

        def fetchall(self):  # pragma: no cover - simple helper
            return self._rows

    class FakeSession:
        async def execute(self, sql, params=None):
            s = str(sql)
            if "min(date) AS first_date" in s:
                return FakeResult(
                    rows=[
                        {
                            "first_date": date(2024, 1, 1),
                            "last_date": date(2024, 1, 10),
                            "n_rows": 8,
                        }
                    ]
                )
            if "LEAD(date)" in s:
                return FakeResult(scalar=date(2024, 1, 2))
            if "get_prices_resolved" in s:
                rows = [
                    {
                        "symbol": "AAPL",
                        "date": pd.Timestamp("2024-01-10"),
                        "open": 102.0,
                        "high": 103.0,
                        "low": 99.0,
                        "close": 102.0,
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
            pass

    async def override_session():
        yield FakeSession()

    app.dependency_overrides[get_session] = override_session

    with TestClient(app) as client:
        r = client.get(
            "/v1/prices", params={"symbols": "AAPL", "from": "2024-01-01", "to": "2024-01-10"}
        )
        assert r.status_code == 200

    assert calls["fetch"] == 1
    app.dependency_overrides.clear()

