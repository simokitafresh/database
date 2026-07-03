"""AC1 regression test for cmd_3685: coverage refetch must span the symbol's
known full period, not a YF_REFETCH_DAYS-bounded recent window.

A windowed refetch (last_date - refetch_days) leaves older rows with stale
split/dividend adjustment factors whenever a new corporate action arrives,
producing the frozen-adjustment "凍結ムラ" that triggered the TECL/XLU
reversal incident. Full-period refetch is the fix (cmd_3685 / cmd_3679-3683).
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from app.services import coverage_service


def _coverage(first_date, last_date):
    return {
        "first_date": first_date,
        "last_date": last_date,
        "has_weekday_gaps": False,
        "has_gaps": False,
        "first_missing_weekday": None,
    }


@pytest.mark.asyncio
async def test_ensure_coverage_refetches_full_known_period():
    """ensure_coverage() must start the refetch range at first_date, not
    last_date - refetch_days."""
    session = AsyncMock()
    symbol = "TECL"
    first_date = date(2010, 1, 1)
    last_date = date(2026, 7, 1)
    date_from = date(2010, 1, 1)
    date_to = date(2026, 7, 3)

    captured_ranges = []

    async def fake_fetch_prices_df(sym, start, end):
        captured_ranges.append((start, end))
        return pd.DataFrame()

    with patch.object(coverage_service, "with_symbol_lock", new=AsyncMock()), \
         patch.object(coverage_service, "_ensure_full_history_once", new=AsyncMock()), \
         patch.object(
             coverage_service,
             "_get_coverage",
             new=AsyncMock(return_value=_coverage(first_date, last_date)),
         ), \
         patch.object(coverage_service, "fetch_prices_df", new=fake_fetch_prices_df):

        await coverage_service.ensure_coverage(
            session=session,
            symbols=[symbol],
            date_from=date_from,
            date_to=date_to,
            refetch_days=7,
        )

    assert captured_ranges, "expected a refetch range to be scheduled"
    start, end = captured_ranges[0]
    assert start == first_date, (
        f"AC1 regression: refetch must start at the symbol's first_date "
        f"({first_date}), got {start}. A windowed start "
        f"(last_date - refetch_days) recreates the frozen-adjustment bug."
    )
    assert end == date_to


@pytest.mark.asyncio
async def test_ensure_coverage_parallel_refetches_full_known_period():
    """ensure_coverage_parallel() must apply the same full-period rule."""
    session = AsyncMock()
    symbol = "XLU"
    first_date = date(2000, 1, 1)
    last_date = date(2026, 7, 1)
    date_from = date(2000, 1, 1)
    date_to = date(2026, 7, 3)

    captured_ranges = []

    async def fake_fetch_prices_df(sym, start, end):
        captured_ranges.append((start, end))
        return pd.DataFrame()

    with patch.object(coverage_service, "_ensure_full_history_once", new=AsyncMock()), \
         patch.object(
             coverage_service,
             "_get_coverage",
             new=AsyncMock(return_value=_coverage(first_date, last_date)),
         ), \
         patch.object(coverage_service, "fetch_prices_df", new=fake_fetch_prices_df):

        await coverage_service.ensure_coverage_parallel(
            session=session,
            symbols=[symbol],
            date_from=date_from,
            date_to=date_to,
            refetch_days=7,
        )

    assert captured_ranges, "expected a refetch range to be scheduled"
    start, end = captured_ranges[0]
    assert start == first_date, (
        f"AC1 regression: parallel refetch must start at first_date "
        f"({first_date}), got {start}."
    )
    assert end == date_to
