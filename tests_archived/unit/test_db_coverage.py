from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.db import queries


class _Tx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_ensure_coverage_refetch_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    session.begin = MagicMock(return_value=_Tx())
    session.execute = AsyncMock()

    cov = {"last_date": date(2024, 1, 10), "has_gaps": False, "first_date": date(2024, 1, 1)}
    monkeypatch.setattr(queries, "_get_coverage", AsyncMock(return_value=cov))
    monkeypatch.setattr(queries, "advisory_lock", AsyncMock())

    fetch_mock = AsyncMock(
        return_value=pd.DataFrame(
            {
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1],
            },
            index=[pd.Timestamp("2024-01-11")],
        )
    )
    monkeypatch.setattr(queries, "fetch_prices_df", fetch_mock)
    monkeypatch.setattr(
        queries,
        "df_to_rows",
        lambda df, symbol, source: [(symbol, date(2024, 1, 11), 1, 1, 1, 1, 1, source)],
    )
    monkeypatch.setattr(queries, "upsert_prices_sql", lambda: "UPSERT")

    await queries.ensure_coverage(
        session, ["AAA"], date(2024, 1, 1), date(2024, 1, 20), refetch_days=5
    )

    fetch_mock.assert_called_once()
    assert fetch_mock.call_args.kwargs["start"] == date(2024, 1, 5)


@pytest.mark.asyncio
async def test_ensure_coverage_gap_fetches_from_start(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    session.begin = MagicMock(return_value=_Tx())
    session.execute = AsyncMock()

    cov = {"last_date": date(2024, 1, 10), "has_gaps": True, "first_date": date(2024, 1, 1)}
    monkeypatch.setattr(queries, "_get_coverage", AsyncMock(return_value=cov))
    monkeypatch.setattr(queries, "advisory_lock", AsyncMock())

    fetch_mock = AsyncMock(
        return_value=pd.DataFrame(
            {
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1],
            },
            index=[pd.Timestamp("2024-01-11")],
        )
    )
    monkeypatch.setattr(queries, "fetch_prices_df", fetch_mock)
    monkeypatch.setattr(
        queries,
        "df_to_rows",
        lambda df, symbol, source: [(symbol, date(2024, 1, 11), 1, 1, 1, 1, 1, source)],
    )
    monkeypatch.setattr(queries, "upsert_prices_sql", lambda: "UPSERT")

    await queries.ensure_coverage(
        session, ["AAA"], date(2024, 1, 1), date(2024, 1, 20), refetch_days=5
    )

    fetch_mock.assert_called_once()
    assert fetch_mock.call_args.kwargs["start"] == date(2024, 1, 1)
