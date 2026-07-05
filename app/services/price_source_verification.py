"""Cross-source close price verification for scheduled price updates."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceClose:
    symbol: str
    source: str
    trade_date: date
    close: float | None
    status: str
    detail: str = ""


def configured_core_symbols() -> list[str]:
    return [s.strip().upper() for s in settings.PRICE_VERIFICATION_CORE_SYMBOLS.split(",") if s.strip()]


def previous_business_day(day: date) -> date:
    current = day - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def previous_month_last_business_day(day: date) -> date:
    return previous_business_day(day.replace(day=1))


def _eodhd_symbol(symbol: str) -> str:
    return "VIX.INDX" if symbol == "VIX" else f"{symbol}.US"


def _tiingo_symbol(symbol: str) -> str:
    return "^VIX" if symbol == "VIX" else symbol.lower()


async def send_ntfy_alert(message: str) -> dict[str, Any]:
    """Send a best-effort ntfy alert when a topic is configured."""

    if not settings.NTFY_TOPIC:
        logger.warning("NTFY_TOPIC not configured; alert not sent: %s", message)
        return {"sent": False, "reason": "NTFY_TOPIC not configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://ntfy.sh/{settings.NTFY_TOPIC}",
                content=message.encode("utf-8"),
            )
            response.raise_for_status()
        return {"sent": True, "topic": settings.NTFY_TOPIC}
    except Exception as exc:  # pragma: no cover - notification failures are reported in response
        logger.error("Failed to send ntfy alert: %s", exc)
        return {"sent": False, "reason": str(exc)}


async def fetch_eodhd_close(symbol: str, trade_date: date) -> SourceClose:
    if not settings.EODHD_API_TOKEN:
        return SourceClose(symbol, "eodhd", trade_date, None, "skipped", "EODHD_API_TOKEN not configured")

    params = {
        "api_token": settings.EODHD_API_TOKEN,
        "fmt": "json",
        "from": trade_date.isoformat(),
        "to": trade_date.isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"https://eodhd.com/api/eod/{_eodhd_symbol(symbol)}", params=params)
            response.raise_for_status()
            rows = response.json()
    except Exception as exc:
        return SourceClose(symbol, "eodhd", trade_date, None, "error", str(exc))

    if not rows:
        return SourceClose(symbol, "eodhd", trade_date, None, "missing", "no EODHD row returned")
    return SourceClose(symbol, "eodhd", trade_date, float(rows[0]["close"]), "ok")


async def fetch_tiingo_close(symbol: str, trade_date: date) -> SourceClose:
    if not settings.TIINGO_API_TOKEN:
        return SourceClose(symbol, "tiingo", trade_date, None, "skipped", "TIINGO_API_TOKEN not configured")

    params = {
        "token": settings.TIINGO_API_TOKEN,
        "startDate": trade_date.isoformat(),
        "endDate": trade_date.isoformat(),
        "format": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"https://api.tiingo.com/tiingo/daily/{_tiingo_symbol(symbol)}/prices", params=params)
            response.raise_for_status()
            rows = response.json()
    except Exception as exc:
        return SourceClose(symbol, "tiingo", trade_date, None, "error", str(exc))

    if not rows:
        return SourceClose(symbol, "tiingo", trade_date, None, "missing", "no Tiingo row returned")
    return SourceClose(symbol, "tiingo", trade_date, float(rows[0]["close"]), "ok")


async def verify_eodhd_tiingo_closes(
    trade_date: date,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Compare EODHD and Tiingo closes and alert when tolerance is exceeded."""

    symbols = symbols or configured_core_symbols()
    tolerance = settings.PRICE_VERIFICATION_TOLERANCE
    comparisons: list[dict[str, Any]] = []
    alert_reasons: list[str] = []

    for symbol in symbols:
        eodhd = await fetch_eodhd_close(symbol, trade_date)
        tiingo = await fetch_tiingo_close(symbol, trade_date)
        diff = None
        status = "ok"

        if eodhd.status != "ok" or tiingo.status != "ok":
            status = "unverified"
            alert_reasons.append(f"{symbol}: source unavailable eodhd={eodhd.status} tiingo={tiingo.status}")
        else:
            diff = abs((eodhd.close or 0.0) - (tiingo.close or 0.0))
            if diff > tolerance + 1e-9:
                status = "mismatch"
                alert_reasons.append(f"{symbol}: EODHD/Tiingo close diff {diff:.4f} > {tolerance:.4f}")

        comparisons.append(
            {
                "symbol": symbol,
                "date": trade_date.isoformat(),
                "eodhd_close": eodhd.close,
                "tiingo_close": tiingo.close,
                "diff": diff,
                "status": status,
                "eodhd_status": eodhd.status,
                "tiingo_status": tiingo.status,
            }
        )

    alert = None
    if alert_reasons:
        alert = await send_ntfy_alert("Price source verification failed: " + "; ".join(alert_reasons))

    return {
        "status": "success" if not alert_reasons else "alert",
        "trade_date": trade_date.isoformat(),
        "tolerance": tolerance,
        "symbols_checked": len(symbols),
        "comparisons": comparisons,
        "alert_reasons": alert_reasons,
        "alert": alert,
    }


async def confirm_previous_month_inputs(
    session: AsyncSession,
    today: date | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Confirm all core symbols have previous month-end rows in prices."""

    today = today or date.today()
    symbols = symbols or configured_core_symbols()
    target_date = previous_month_last_business_day(today)
    result = await session.execute(
        text(
            """
            SELECT symbol
            FROM prices
            WHERE date = :target_date
              AND symbol = ANY(:symbols)
            """
        ),
        {"target_date": target_date, "symbols": symbols},
    )
    present = sorted(row[0] for row in result.fetchall())
    missing = sorted(set(symbols) - set(present))
    status = "confirmed" if not missing else "pending"

    alert = None
    if missing:
        alert = await send_ntfy_alert(
            f"Monthly input confirmation pending: missing {target_date.isoformat()} rows for {', '.join(missing)}"
        )

    return {
        "status": status,
        "target_date": target_date.isoformat(),
        "symbols_expected": len(symbols),
        "symbols_present": len(present),
        "missing_symbols": missing,
        "alert": alert,
    }
