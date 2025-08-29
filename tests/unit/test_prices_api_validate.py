from datetime import date
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_session
from app.core.config import settings


def _setup_session(rows: list):
    class _MapWrap:
        def __init__(self, rows):
            self._rows = rows

        def first(self):
            return self._rows[0] if self._rows else None

    class FakeResult:
        def __init__(self, rows=None, scalar=None):
            self._rows = rows or []
            self._scalar = scalar

        def mappings(self):
            return _MapWrap(self._rows)

        def scalar_one_or_none(self):
            return self._scalar

        def fetchall(self):
            return self._rows

    class FakeSession(AsyncMock):
        async def execute(self, sql, params=None):
            s = str(sql)
            if "min(date) AS first_date" in s:
                return FakeResult(rows=[{"first_date": None, "last_date": None, "n_rows": 0}])
            if "LEAD(date)" in s:
                return FakeResult(scalar=None)
            if "get_prices_resolved" in s:
                return FakeResult(rows=rows)
            return FakeResult()

        async def connection(self):
            return AsyncMock()

    return FakeSession()


def test_too_many_symbols(monkeypatch):
    session = _setup_session([])

    async def override_get_session():
        return session

    app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr(settings, "API_MAX_SYMBOLS", 1)

    client = TestClient(app)
    resp = client.get(
        "/v1/prices?symbols=A,B&from=2023-01-01&to=2023-01-10"
    )
    assert resp.status_code == 422

    app.dependency_overrides.clear()


def test_invalid_date_range():
    client = TestClient(app)
    resp = client.get(
        "/v1/prices?symbols=A&from=2023-01-10&to=2023-01-01"
    )
    assert resp.status_code == 422


def test_row_limit(monkeypatch, mocker):
    row = {
        "symbol": "A",
        "date": date(2023, 1, 1),
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1,
        "source": "s",
        "last_updated": date(2023, 1, 1),
        "source_symbol": None,
    }

    session = _setup_session([row, row])

    async def override_get_session():
        return session

    app.dependency_overrides[get_session] = override_get_session

    mocker.patch("app.api.v1.prices.normalize.normalize_symbol", return_value="A")
    mocker.patch(
        "app.api.v1.prices.resolver.segments_for",
        return_value=[("A", date(2023, 1, 1), date(2023, 1, 2))],
    )
    mocker.patch("app.api.v1.prices.fetcher.fetch_prices", return_value=None)
    mocker.patch(
        "app.api.v1.prices.upsert.df_to_rows", return_value=[]
    )
    mocker.patch(
        "app.api.v1.prices.upsert.upsert_prices_sql", return_value=""
    )

    monkeypatch.setattr(settings, "API_MAX_ROWS", 1)

    client = TestClient(app)
    resp = client.get("/v1/prices?symbols=A&from=2023-01-01&to=2023-01-02")
    assert resp.status_code == 413

    app.dependency_overrides.clear()


def test_service_call_order(monkeypatch, mocker):
    session = _setup_session([])

    async def override_get_session():
        return session

    app.dependency_overrides[get_session] = override_get_session

    calls: list[str] = []

    def _record(name):
        def _inner(*args, **kwargs):
            calls.append(name)
            if name == "normalize":
                return args[0]
            if name == "resolver":
                return [("A", date(2023, 1, 1), date(2023, 1, 2))]
            return None

        return _inner

    mocker.patch(
        "app.api.v1.prices.normalize.normalize_symbol", side_effect=_record("normalize")
    )
    mocker.patch(
        "app.api.v1.prices.resolver.segments_for", side_effect=_record("resolver")
    )
    mocker.patch(
        "app.api.v1.prices.fetcher.fetch_prices", side_effect=_record("fetcher")
    )
    mocker.patch(
        "app.api.v1.prices.upsert.df_to_rows", side_effect=_record("upsert")
    )
    mocker.patch(
        "app.api.v1.prices.upsert.upsert_prices_sql", return_value=""
    )
    mocker.patch(
        "app.api.v1.prices.advisory_lock", side_effect=_record("lock")
    )

    client = TestClient(app)
    resp = client.get("/v1/prices?symbols=A&from=2023-01-01&to=2023-01-02")
    assert resp.status_code == 200
    assert calls == [
        "normalize",
        "resolver",
        "lock",
        "fetcher",
        "upsert",
    ]

    app.dependency_overrides.clear()

