from datetime import date
import pytest

from app.db import queries as q


class DummyBeginCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummySession:
    def begin(self):
        return DummyBeginCtx()

    async def execute(self, *a, **k):
        class R:
            def scalar(self_inner):
                return None

            def mappings(self_inner):
                return []

            def all(self_inner):
                return []

        return R()


@pytest.mark.asyncio
async def test_weekend_gap_does_not_full_refetch(monkeypatch):
    calls = {}

    async def fake_get_cov(session, symbol, dfrom, dto):
        return {
            "first_date": date(2024, 7, 1),
            "last_date": date(2024, 9, 27),
            "cnt": 1,
            "has_weekday_gaps": False,
            "first_missing_weekday": None,
        }

    async def fake_lock(session, symbol):
        return None

    async def fake_fetch(symbol, start, end):
        calls["start"] = start
        calls["end"] = end
        import pandas as pd

        return pd.DataFrame([], columns=["open", "high", "low", "close", "volume"])

    def fake_df_to_rows(df, symbol, source):
        return []

    def fake_upsert_sql():
        return "SELECT 1"

    monkeypatch.setattr(q, "_get_coverage", fake_get_cov)
    monkeypatch.setattr(q, "with_symbol_lock", fake_lock)
    monkeypatch.setattr(q, "fetch_prices_df", fake_fetch)
    monkeypatch.setattr(q, "df_to_rows", fake_df_to_rows)
    monkeypatch.setattr(q, "upsert_prices_sql", fake_upsert_sql)

    sess = DummySession()
    await q.ensure_coverage(
        session=sess,
        symbols=["AAPL"],
        date_from=date(2024, 7, 1),
        date_to=date(2024, 10, 1),
        refetch_days=30,
    )

    assert calls["start"] == date(2024, 8, 28)


@pytest.mark.asyncio
async def test_weekday_gap_min_start(monkeypatch):
    calls = {}

    async def fake_get_cov(session, symbol, dfrom, dto):
        return {
            "first_date": date(2024, 7, 1),
            "last_date": date(2024, 9, 27),
            "cnt": 1,
            "has_weekday_gaps": True,
            "first_missing_weekday": date(2024, 9, 18),
        }

    async def fake_lock(session, symbol):
        return None

    async def fake_fetch(symbol, start, end):
        calls["start"] = start
        calls["end"] = end
        import pandas as pd

        return pd.DataFrame([], columns=["open", "high", "low", "close", "volume"])

    def fake_df_to_rows(df, symbol, source):
        return []

    def fake_upsert_sql():
        return "SELECT 1"

    monkeypatch.setattr(q, "_get_coverage", fake_get_cov)
    monkeypatch.setattr(q, "with_symbol_lock", fake_lock)
    monkeypatch.setattr(q, "fetch_prices_df", fake_fetch)
    monkeypatch.setattr(q, "df_to_rows", fake_df_to_rows)
    monkeypatch.setattr(q, "upsert_prices_sql", fake_upsert_sql)

    sess = DummySession()
    await q.ensure_coverage(
        session=sess,
        symbols=["AAPL"],
        date_from=date(2024, 7, 1),
        date_to=date(2024, 10, 1),
        refetch_days=30,
    )

    assert calls["start"] == date(2024, 8, 28)
