"""Raw price ingestion and deterministic adjustment derivation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.price_source_verification import _eodhd_symbol, _tiingo_symbol
from app.services.upsert import upsert_prices

RAW_SOURCES = ("eodhd", "tiingo", "alpaca")


@dataclass(frozen=True)
class RawPriceRow:
    symbol: str
    date: date
    source: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class CorporateAction:
    symbol: str
    event_date: date
    event_type: str
    dividend_amount: float | None = None
    split_ratio: float | None = None
    ex_date: date | None = None
    record_date: date | None = None
    pay_date: date | None = None
    source: str = "eodhd"


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _parse_float(value: Any) -> float | None:
    if value in (None, "", "NA", "N/A"):
        return None
    return float(value)


def eodhd_adjusted_close_within_tolerance(
    derived_close: float,
    eodhd_adjusted_close: float,
    tolerance: float | None = None,
) -> bool:
    tolerance = settings.PRICE_VERIFICATION_TOLERANCE if tolerance is None else tolerance
    return abs(derived_close - eodhd_adjusted_close) <= tolerance + 1e-9


def _raw_symbol_supported(source: str, symbol: str) -> bool:
    return not (symbol == "VIX" and source in {"alpaca", "tiingo"})


async def fetch_eodhd_raw_prices(symbol: str, start: date, end: date) -> list[RawPriceRow]:
    if not settings.EODHD_API_TOKEN:
        return []
    params = {
        "api_token": settings.EODHD_API_TOKEN,
        "fmt": "json",
        "from": start.isoformat(),
        "to": end.isoformat(),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://eodhd.com/api/eod/{_eodhd_symbol(symbol)}", params=params
        )
        response.raise_for_status()
        payload = response.json()
    rows: list[RawPriceRow] = []
    for item in payload:
        rows.append(
            RawPriceRow(
                symbol=symbol,
                date=_parse_date(item["date"]),
                source="eodhd",
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=int(float(item.get("volume") or 0)),
            )
        )
    return rows


async def fetch_tiingo_raw_prices(symbol: str, start: date, end: date) -> list[RawPriceRow]:
    if not settings.TIINGO_API_TOKEN or not _raw_symbol_supported("tiingo", symbol):
        return []
    params = {
        "token": settings.TIINGO_API_TOKEN,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://api.tiingo.com/tiingo/daily/{_tiingo_symbol(symbol)}/prices", params=params
        )
        response.raise_for_status()
        payload = response.json()
    rows: list[RawPriceRow] = []
    for item in payload:
        rows.append(
            RawPriceRow(
                symbol=symbol,
                date=_parse_date(item["date"]),
                source="tiingo",
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=int(float(item.get("volume") or 0)),
            )
        )
    return rows


async def fetch_alpaca_raw_prices(symbol: str, start: date, end: date) -> list[RawPriceRow]:
    key = getattr(settings, "ALPACA_API_KEY_ID", None)
    secret = getattr(settings, "ALPACA_API_SECRET_KEY", None)
    if not key or not secret or not _raw_symbol_supported("alpaca", symbol):
        return []
    params = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timeframe": "1Day",
        "feed": "iex",
        "adjustment": "raw",
        "limit": 10000,
    }
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://data.alpaca.markets/v2/stocks/{symbol}/bars", params=params, headers=headers
        )
        response.raise_for_status()
        payload = response.json().get("bars") or []
    rows: list[RawPriceRow] = []
    for item in payload:
        rows.append(
            RawPriceRow(
                symbol=symbol,
                date=_parse_date(item["t"]),
                source="alpaca",
                open=float(item["o"]),
                high=float(item["h"]),
                low=float(item["l"]),
                close=float(item["c"]),
                volume=int(float(item.get("v") or 0)),
            )
        )
    return rows


async def fetch_raw_prices(symbol: str, start: date, end: date) -> list[RawPriceRow]:
    rows: list[RawPriceRow] = []
    rows.extend(await fetch_eodhd_raw_prices(symbol, start, end))
    rows.extend(await fetch_tiingo_raw_prices(symbol, start, end))
    rows.extend(await fetch_alpaca_raw_prices(symbol, start, end))
    return rows


async def upsert_prices_raw(session: AsyncSession, rows: list[RawPriceRow]) -> int:
    if not rows:
        return 0
    payload = [
        {
            "symbol": row.symbol,
            "date": row.date,
            "source": row.source,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
            "fetched_at": datetime.now(timezone.utc),
        }
        for row in rows
    ]
    result = await session.execute(
        text(
            """
            INSERT INTO prices_raw (
              symbol, date, source, open, high, low, close, volume, fetched_at
            )
            VALUES (:symbol, :date, :source, :open, :high, :low, :close, :volume, :fetched_at)
            ON CONFLICT (symbol, date, source) DO UPDATE SET
              open = EXCLUDED.open,
              high = EXCLUDED.high,
              low = EXCLUDED.low,
              close = EXCLUDED.close,
              volume = EXCLUDED.volume,
              fetched_at = EXCLUDED.fetched_at
            """
        ),
        payload,
    )
    return result.rowcount if result.rowcount and result.rowcount > 0 else len(rows)


async def compute_consensus_close(
    session: AsyncSession,
    symbols: list[str],
    start: date,
    end: date,
    tolerance: float | None = None,
) -> dict[str, Any]:
    tolerance = settings.PRICE_VERIFICATION_TOLERANCE if tolerance is None else tolerance
    result = await session.execute(
        text(
            """
            SELECT symbol, date, source, close
            FROM prices_raw
            WHERE symbol = ANY(:symbols)
              AND date BETWEEN :start AND :end
            ORDER BY symbol, date, source
            """
        ),
        {"symbols": symbols, "start": start, "end": end},
    )
    grouped: dict[tuple[str, date], list[tuple[str, float]]] = {}
    for symbol, trade_date, source, close in result.fetchall():
        grouped.setdefault((symbol, trade_date), []).append((source, float(close)))

    confirmed: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    for (symbol, trade_date), values in grouped.items():
        consensus = _majority_close(values, tolerance)
        if consensus is None:
            alerts.append({"symbol": symbol, "date": trade_date.isoformat(), "sources": values})
            continue
        await session.execute(
            text(
                """
                UPDATE prices_raw
                SET consensus_close = :consensus
                WHERE symbol = :symbol
                  AND date = :date
                """
            ),
            {"symbol": symbol, "date": trade_date, "consensus": consensus},
        )
        confirmed.append(
            {"symbol": symbol, "date": trade_date.isoformat(), "consensus_close": consensus}
        )

    return {"confirmed": confirmed, "alerts": alerts, "tolerance": tolerance}


def _majority_close(values: list[tuple[str, float]], tolerance: float) -> float | None:
    if len(values) < 2:
        return None
    for _, anchor in values:
        matches = [close for _, close in values if abs(close - anchor) <= tolerance + 1e-9]
        if len(matches) >= 2:
            return round(sum(matches) / len(matches), 6)
    return None


async def fetch_eodhd_corporate_events(
    symbol: str, start: date, end: date, today: date | None = None
) -> list[CorporateAction]:
    if not settings.EODHD_API_TOKEN:
        return []
    today = today or date.today()
    actions: list[CorporateAction] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for endpoint, event_type in (("div", "dividend"), ("splits", "split")):
            response = await client.get(
                f"https://eodhd.com/api/{endpoint}/{_eodhd_symbol(symbol)}",
                params={
                    "api_token": settings.EODHD_API_TOKEN,
                    "fmt": "json",
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                },
            )
            response.raise_for_status()
            payload = response.json()
            for item in payload:
                ex_date = _parse_date(item.get("ex_date") or item.get("date"))
                if ex_date > today:
                    continue
                if event_type == "dividend":
                    amount = _parse_float(item.get("value") or item.get("amount"))
                    if amount is None:
                        continue
                    actions.append(
                        CorporateAction(
                            symbol,
                            ex_date,
                            "dividend",
                            dividend_amount=amount,
                            ex_date=ex_date,
                            source="eodhd",
                        )
                    )
                else:
                    ratio = _parse_float(item.get("split") or item.get("ratio"))
                    if ratio is None:
                        continue
                    actions.append(
                        CorporateAction(
                            symbol,
                            ex_date,
                            "split",
                            split_ratio=ratio,
                            ex_date=ex_date,
                            source="eodhd",
                        )
                    )
    return actions


async def upsert_confirmed_events(session: AsyncSession, actions: list[CorporateAction]) -> int:
    if not actions:
        return 0
    payload = [
        {
            "symbol": action.symbol,
            "event_date": action.event_date,
            "event_type": action.event_type,
            "dividend_amount": action.dividend_amount,
            "split_ratio": action.split_ratio,
            "amount": action.dividend_amount,
            "ratio": action.split_ratio,
            "ex_date": action.ex_date or action.event_date,
            "record_date": action.record_date,
            "pay_date": action.pay_date,
            "confirmed_at": datetime.now(timezone.utc),
            "source_count": 1,
            "sources_json": [{"source": action.source}],
            "status": "confirmed",
        }
        for action in actions
    ]
    result = await session.execute(
        text(
            """
            INSERT INTO corporate_events (
              symbol, event_date, event_type, dividend_amount, split_ratio, amount, ratio,
              ex_date, record_date, pay_date, confirmed_at, source_count, sources_json, status
            )
            VALUES (
              :symbol, :event_date, :event_type, :dividend_amount, :split_ratio, :amount, :ratio,
              :ex_date, :record_date, :pay_date, :confirmed_at, :source_count,
              :sources_json, :status
            )
            ON CONFLICT ON CONSTRAINT uq_corp_event DO UPDATE SET
              dividend_amount = EXCLUDED.dividend_amount,
              split_ratio = EXCLUDED.split_ratio,
              amount = EXCLUDED.amount,
              ratio = EXCLUDED.ratio,
              ex_date = EXCLUDED.ex_date,
              record_date = EXCLUDED.record_date,
              pay_date = EXCLUDED.pay_date,
              confirmed_at = EXCLUDED.confirmed_at,
              source_count = EXCLUDED.source_count,
              sources_json = EXCLUDED.sources_json,
              status = EXCLUDED.status,
              updated_at = now()
            """
        ),
        payload,
    )
    return result.rowcount if result.rowcount and result.rowcount > 0 else len(actions)


async def derive_adjusted_prices(
    session: AsyncSession, symbols: list[str], start: date, end: date
) -> dict[str, Any]:
    raw_result = await session.execute(
        text(
            """
            SELECT symbol, date, MAX(consensus_close) AS consensus_close, MAX(volume) AS volume
            FROM prices_raw
            WHERE symbol = ANY(:symbols)
              AND date BETWEEN :start AND :end
              AND consensus_close IS NOT NULL
            GROUP BY symbol, date
            ORDER BY symbol, date
            """
        ),
        {"symbols": symbols, "start": start, "end": end},
    )
    raw_rows = raw_result.fetchall()
    events_result = await session.execute(
        text(
            """
            SELECT symbol, event_type, ex_date, dividend_amount, split_ratio
            FROM corporate_events
            WHERE symbol = ANY(:symbols)
              AND confirmed_at IS NOT NULL
              AND ex_date <= :end
            ORDER BY ex_date DESC
            """
        ),
        {"symbols": symbols, "end": end},
    )
    events_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol, event_type, ex_date, dividend_amount, split_ratio in events_result.fetchall():
        events_by_symbol.setdefault(symbol, []).append(
            {
                "event_type": event_type,
                "ex_date": ex_date,
                "dividend_amount": float(dividend_amount) if dividend_amount is not None else None,
                "split_ratio": float(split_ratio) if split_ratio is not None else None,
            }
        )

    price_rows: list[dict[str, Any]] = []
    for symbol, trade_date, consensus_close, volume in raw_rows:
        close = float(consensus_close)
        factor = _adjustment_factor(symbol, trade_date, close, events_by_symbol.get(symbol, []))
        adjusted_close = round(close * factor, 6)
        price_rows.append(
            {
                "symbol": symbol,
                "date": trade_date,
                "open": adjusted_close,
                "high": adjusted_close,
                "low": adjusted_close,
                "close": adjusted_close,
                "volume": int(volume or 0),
                "source": "raw_consensus_events",
                "last_updated": datetime.now(timezone.utc),
            }
        )
    inserted, updated = await upsert_prices(session, price_rows, force_update=True)
    return {"rows_written": len(price_rows), "inserted": inserted, "updated": updated}


def _adjustment_factor(
    symbol: str, trade_date: date, close: float, events: list[dict[str, Any]]
) -> float:
    factor = 1.0
    for event in events:
        ex_date = event["ex_date"]
        if trade_date >= ex_date:
            continue
        if event["event_type"] == "split" and event.get("split_ratio"):
            factor /= float(event["split_ratio"])
        elif event["event_type"] == "dividend" and event.get("dividend_amount"):
            factor *= max(0.0, 1.0 - float(event["dividend_amount"]) / close)
    return factor


async def run_raw_price_pipeline(
    session: AsyncSession, symbols: list[str], start: date, end: date
) -> dict[str, Any]:
    fetched = 0
    for symbol in symbols:
        rows = await fetch_raw_prices(symbol, start, end)
        fetched += await upsert_prices_raw(session, rows)
    consensus = await compute_consensus_close(session, symbols, start, end)
    events = []
    for symbol in symbols:
        events.extend(await fetch_eodhd_corporate_events(symbol, start, end))
    event_count = await upsert_confirmed_events(session, events)
    derived = await derive_adjusted_prices(session, symbols, start, end)
    return {"raw_rows": fetched, "consensus": consensus, "events": event_count, "derived": derived}
