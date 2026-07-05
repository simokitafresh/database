from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import price_source_verification as verification
from app.services.price_source_verification import SourceClose


@pytest.mark.asyncio
async def test_verify_eodhd_tiingo_closes_no_alert_when_within_tolerance():
    async def fake_eodhd(symbol, trade_date):
        return SourceClose(symbol, "eodhd", trade_date, 100.00, "ok")

    async def fake_tiingo(symbol, trade_date):
        return SourceClose(symbol, "tiingo", trade_date, 100.01, "ok")

    with patch.object(verification, "fetch_eodhd_close", fake_eodhd), \
         patch.object(verification, "fetch_tiingo_close", fake_tiingo), \
         patch.object(verification, "send_ntfy_alert", AsyncMock()) as alert:
        result = await verification.verify_eodhd_tiingo_closes(date(2026, 6, 30), ["SPY"])

    assert result["status"] == "success"
    assert result["comparisons"][0]["status"] == "ok"
    alert.assert_not_called()


@pytest.mark.asyncio
async def test_verify_eodhd_tiingo_closes_alerts_when_diff_exceeds_tolerance():
    async def fake_eodhd(symbol, trade_date):
        return SourceClose(symbol, "eodhd", trade_date, 100.00, "ok")

    async def fake_tiingo(symbol, trade_date):
        return SourceClose(symbol, "tiingo", trade_date, 100.02, "ok")

    with patch.object(verification, "fetch_eodhd_close", fake_eodhd), \
         patch.object(verification, "fetch_tiingo_close", fake_tiingo), \
         patch.object(verification, "send_ntfy_alert", AsyncMock(return_value={"sent": True})) as alert:
        result = await verification.verify_eodhd_tiingo_closes(date(2026, 6, 30), ["SPY"])

    assert result["status"] == "alert"
    assert result["comparisons"][0]["status"] == "mismatch"
    assert "SPY" in result["alert_reasons"][0]
    alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_previous_month_inputs_confirmed_when_all_rows_exist():
    session = AsyncMock()
    result = SimpleNamespace(fetchall=lambda: [("SPY",), ("QQQ",)])
    session.execute.return_value = result

    output = await verification.confirm_previous_month_inputs(
        session,
        today=date(2026, 7, 5),
        symbols=["SPY", "QQQ"],
    )

    assert output["status"] == "confirmed"
    assert output["target_date"] == "2026-06-30"
    assert output["missing_symbols"] == []


@pytest.mark.asyncio
async def test_confirm_previous_month_inputs_pending_and_alerts_when_rows_missing():
    session = AsyncMock()
    result = SimpleNamespace(fetchall=lambda: [("SPY",)])
    session.execute.return_value = result

    with patch.object(verification, "send_ntfy_alert", AsyncMock(return_value={"sent": True})) as alert:
        output = await verification.confirm_previous_month_inputs(
            session,
            today=date(2026, 7, 5),
            symbols=["SPY", "QQQ"],
        )

    assert output["status"] == "pending"
    assert output["target_date"] == "2026-06-30"
    assert output["missing_symbols"] == ["QQQ"]
    alert.assert_awaited_once()
