from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import raw_price_pipeline as pipeline
from app.services.raw_price_pipeline import CorporateAction


class RecordingSession:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []
        self.params = []

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        self.params.append(params)
        result = self.results.pop(0) if self.results else []
        return SimpleNamespace(fetchall=lambda: result, rowcount=len(result))


@pytest.mark.asyncio
async def test_compute_consensus_close_confirms_two_of_three_within_tolerance():
    rows = [
        ("SPY", date(2026, 6, 30), "eodhd", 109.07),
        ("SPY", date(2026, 6, 30), "tiingo", 109.071),
        ("SPY", date(2026, 6, 30), "alpaca", 109.20),
    ]
    session = RecordingSession([rows, []])

    result = await pipeline.compute_consensus_close(
        session, ["SPY"], date(2026, 6, 30), date(2026, 6, 30), tolerance=0.01
    )

    assert len(result["confirmed"]) == 1
    assert result["alerts"] == []
    assert result["confirmed"][0]["consensus_close"] == 109.0705


@pytest.mark.asyncio
async def test_compute_consensus_close_alerts_when_no_two_sources_match():
    rows = [
        ("SPY", date(2026, 6, 30), "eodhd", 109.07),
        ("SPY", date(2026, 6, 30), "tiingo", 109.20),
        ("SPY", date(2026, 6, 30), "alpaca", 109.40),
    ]
    session = RecordingSession([rows])

    result = await pipeline.compute_consensus_close(
        session, ["SPY"], date(2026, 6, 30), date(2026, 6, 30), tolerance=0.01
    )

    assert result["confirmed"] == []
    assert result["alerts"][0]["symbol"] == "SPY"


@pytest.mark.asyncio
async def test_eodhd_events_only_confirm_ex_date_that_has_passed():
    payloads = [
        [
            {"date": "2026-06-01", "value": 0.25},
            {"date": "2026-08-01", "value": 0.30},
        ],
        [{"date": "2026-06-15", "split": 2.0}],
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            return FakeResponse(payloads.pop(0))

    with (
        patch.object(pipeline.settings, "EODHD_API_TOKEN", "token"),
        patch.object(pipeline.httpx, "AsyncClient", lambda timeout: FakeClient()),
    ):
        actions = await pipeline.fetch_eodhd_corporate_events(
            "SPY", date(2026, 1, 1), date(2026, 12, 31), today=date(2026, 7, 5)
        )

    assert [action.event_type for action in actions] == ["dividend", "split"]
    assert all(action.ex_date <= date(2026, 7, 5) for action in actions if action.ex_date)


@pytest.mark.asyncio
async def test_upsert_confirmed_events_sets_confirmed_metadata():
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(rowcount=1)

    count = await pipeline.upsert_confirmed_events(
        session,
        [
            CorporateAction(
                symbol="SPY",
                event_date=date(2026, 6, 1),
                event_type="dividend",
                dividend_amount=0.25,
                ex_date=date(2026, 6, 1),
            )
        ],
    )

    assert count == 1
    params = session.execute.call_args.args[1][0]
    assert params["status"] == "confirmed"
    assert params["confirmed_at"] is not None
    assert params["source_count"] == 1


@pytest.mark.asyncio
async def test_derive_adjusted_prices_writes_prices_api_compatible_rows():
    session = RecordingSession(
        [
            [("SPY", date(2026, 5, 31), 100.0, 1000)],
            [("SPY", "dividend", date(2026, 6, 1), 1.0, None)],
        ]
    )

    with patch.object(pipeline, "upsert_prices", AsyncMock(return_value=(1, 0))) as upsert:
        result = await pipeline.derive_adjusted_prices(
            session, ["SPY"], date(2026, 5, 1), date(2026, 6, 30)
        )

    assert result["rows_written"] == 1
    price_row = upsert.call_args.args[1][0]
    assert price_row["source"] == "raw_consensus_events"
    assert price_row["close"] == 99.0


def test_eodhd_adjusted_close_tolerance_helper():
    assert pipeline.eodhd_adjusted_close_within_tolerance(108.688, 108.689, tolerance=0.01)
    assert not pipeline.eodhd_adjusted_close_within_tolerance(108.688, 108.72, tolerance=0.01)


def test_month_end_dividend_is_applied_to_prior_dates_only():
    events = [
        {
            "event_type": "dividend",
            "ex_date": date(2026, 6, 30),
            "dividend_amount": 1.0,
        }
    ]

    assert pipeline._adjustment_factor("LQD", date(2026, 6, 29), 100.0, events) == 0.99
    assert pipeline._adjustment_factor("LQD", date(2026, 6, 30), 100.0, events) == 1.0


def test_next_month_dividend_is_not_applied_to_month_end_signal_date():
    events = [
        {
            "event_type": "dividend",
            "ex_date": date(2026, 7, 1),
            "dividend_amount": 1.0,
        }
    ]

    assert pipeline._adjustment_factor("LQD", date(2026, 6, 30), 100.0, events) == 0.99
    assert pipeline._adjustment_factor("LQD", date(2026, 7, 1), 100.0, events) == 1.0


def test_month_end_split_adjusts_prior_dates_only():
    events = [
        {
            "event_type": "split",
            "ex_date": date(2026, 6, 30),
            "split_ratio": 2.0,
        }
    ]

    assert pipeline._adjustment_factor("TECL", date(2026, 6, 29), 100.0, events) == 0.5
    assert pipeline._adjustment_factor("TECL", date(2026, 6, 30), 100.0, events) == 1.0


@pytest.mark.asyncio
async def test_derive_adjusted_prices_keeps_ieee_precision_without_six_decimal_rounding():
    session = RecordingSession(
        [
            [("SPY", date(2026, 5, 31), 1.0 / 3.0, 1000)],
            [("SPY", "dividend", date(2026, 6, 1), 0.01, None)],
        ]
    )

    with patch.object(pipeline, "upsert_prices", AsyncMock(return_value=(1, 0))) as upsert:
        await pipeline.derive_adjusted_prices(
            session, ["SPY"], date(2026, 5, 1), date(2026, 6, 30)
        )

    price_row = upsert.call_args.args[1][0]
    expected = (1.0 / 3.0) * (1.0 - 0.01 / (1.0 / 3.0))
    assert abs(price_row["close"] - expected) <= 1e-12


@pytest.mark.asyncio
async def test_derive_adjusted_prices_uses_previous_close_for_dividend_factor():
    session = RecordingSession(
        [
            [
                ("LQD", date(2026, 6, 29), 100.0, 1000),
                ("LQD", date(2026, 6, 30), 110.0, 1000),
            ],
            [("LQD", "dividend", date(2026, 6, 30), 1.0, None)],
        ]
    )

    with patch.object(pipeline, "upsert_prices", AsyncMock(return_value=(2, 0))) as upsert:
        await pipeline.derive_adjusted_prices(
            session, ["LQD"], date(2026, 6, 1), date(2026, 6, 30)
        )

    price_rows = upsert.call_args.args[1]
    assert price_rows[0]["close"] == 99.0
    assert price_rows[1]["close"] == 110.0
