"""Compare stored adjusted prices against EODHD adjusted_close.

Read-only verification for cmd_3691:
1. Fetch Stockdata API /v1/prices with auto_fetch=false.
2. Fetch EODHD EOD adjusted_close for the same symbols and date range.
3. Report absolute-difference distribution and month-end momentum rank reversals.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from math import ceil
from statistics import median
from typing import Any

import httpx

CORE_SYMBOLS = ["LQD", "TECL", "XLU", "QQQ", "GLD", "SPY", "TQQQ", "TMV", "GDX", "QLD", "TMF"]
DEFAULT_BASE_URL = "https://stockdata-api-6xok.onrender.com"


def eodhd_symbol(symbol: str) -> str:
    return "VIX.INDX" if symbol == "VIX" else f"{symbol}.US"


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, ceil((pct / 100.0) * len(ordered)) - 1)
    return ordered[index]


def month_end_dates(rows_by_symbol: dict[str, dict[date, float]]) -> list[date]:
    all_dates = sorted({d for rows in rows_by_symbol.values() for d in rows})
    latest_by_month: dict[tuple[int, int], date] = {}
    for d in all_dates:
        latest_by_month[(d.year, d.month)] = d
    return sorted(latest_by_month.values())


def shift_months(day: date, months: int) -> date:
    month = day.month - months
    year = day.year
    while month <= 0:
        month += 12
        year -= 1
    max_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
               31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, max_day))


def nearest_price(rows: dict[date, float], target: date) -> tuple[date, float] | None:
    candidates = [d for d in rows if d <= target]
    if not candidates:
        return None
    d = max(candidates)
    return d, rows[d]


def momentum_score(rows: dict[date, float], as_of: date, lookback_months: int) -> float | None:
    current = nearest_price(rows, as_of)
    past = nearest_price(rows, shift_months(as_of, lookback_months))
    if not current or not past or past[1] == 0:
        return None
    return current[1] / past[1] - 1.0


async def fetch_api_prices(
    client: httpx.AsyncClient,
    base_url: str,
    symbol: str,
    start: date,
    end: date,
) -> dict[date, float]:
    response = await client.get(
        f"{base_url.rstrip('/')}/v1/prices",
        params={
            "symbols": symbol,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "auto_fetch": "false",
        },
    )
    response.raise_for_status()
    rows = response.json()
    return {date.fromisoformat(row["date"]): float(row["close"]) for row in rows}


async def fetch_eodhd_adjusted(
    client: httpx.AsyncClient,
    token: str,
    symbol: str,
    start: date,
    end: date,
) -> dict[date, float]:
    response = await client.get(
        f"https://eodhd.com/api/eod/{eodhd_symbol(symbol)}",
        params={
            "api_token": token,
            "fmt": "json",
            "from": start.isoformat(),
            "to": end.isoformat(),
        },
    )
    response.raise_for_status()
    rows = response.json()
    out: dict[date, float] = {}
    for row in rows:
        adjusted = row.get("adjusted_close")
        if adjusted is None:
            continue
        out[date.fromisoformat(row["date"])] = float(adjusted)
    return out


def compare_rows(
    api_rows: dict[str, dict[date, float]],
    eodhd_rows: dict[str, dict[date, float]],
) -> tuple[list[dict[str, Any]], list[float]]:
    comparisons: list[dict[str, Any]] = []
    diffs: list[float] = []
    for symbol, rows in api_rows.items():
        for d, stored_close in rows.items():
            eodhd_close = eodhd_rows.get(symbol, {}).get(d)
            if eodhd_close is None:
                continue
            diff = abs(stored_close - eodhd_close)
            diffs.append(diff)
            comparisons.append(
                {
                    "symbol": symbol,
                    "date": d.isoformat(),
                    "stored_close": stored_close,
                    "eodhd_adjusted_close": eodhd_close,
                    "abs_diff": diff,
                }
            )
    return comparisons, diffs


def find_momentum_reversal_risk(
    api_rows: dict[str, dict[date, float]],
    eodhd_rows: dict[str, dict[date, float]],
    lookbacks: list[int],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for as_of in month_end_dates(eodhd_rows):
        for lookback in lookbacks:
            eodhd_scores: dict[str, float] = {}
            api_scores: dict[str, float] = {}
            for symbol in eodhd_rows:
                e_score = momentum_score(eodhd_rows[symbol], as_of, lookback)
                a_score = momentum_score(api_rows.get(symbol, {}), as_of, lookback)
                if e_score is not None and a_score is not None:
                    eodhd_scores[symbol] = e_score
                    api_scores[symbol] = a_score
            if len(eodhd_scores) < 2:
                continue
            e_ranked = sorted(eodhd_scores.items(), key=lambda item: item[1], reverse=True)
            a_ranked = sorted(api_scores.items(), key=lambda item: item[1], reverse=True)
            top_margin = e_ranked[0][1] - e_ranked[1][1]
            top_error = abs(api_scores[e_ranked[0][0]] - e_ranked[0][1])
            runner_error = abs(api_scores[e_ranked[1][0]] - e_ranked[1][1])
            if a_ranked[0][0] != e_ranked[0][0] or top_error + runner_error >= top_margin:
                risks.append(
                    {
                        "date": as_of.isoformat(),
                        "lookback_months": lookback,
                        "eodhd_top": e_ranked[0][0],
                        "api_top": a_ranked[0][0],
                        "eodhd_top_margin": top_margin,
                        "top_error_bound": top_error + runner_error,
                        "rank_reversed": a_ranked[0][0] != e_ranked[0][0],
                    }
                )
    return risks


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--symbols", default=",".join(CORE_SYMBOLS))
    parser.add_argument("--from", dest="start", default="2000-01-01")
    parser.add_argument("--to", dest="end", default=date.today().isoformat())
    parser.add_argument("--lookbacks", default="1,3,6,12")
    parser.add_argument("--output", default="reports/adjusted_close_eodhd_compare_cmd_3691.json")
    args = parser.parse_args()

    token = os.environ.get("EODHD_API_TOKEN")
    if not token:
        raise SystemExit("EODHD_API_TOKEN is required")

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    lookbacks = [int(x) for x in args.lookbacks.split(",") if x.strip()]

    async with httpx.AsyncClient(timeout=60.0) as client:
        api_rows = {
            symbol: await fetch_api_prices(client, args.base_url, symbol, start, end)
            for symbol in symbols
        }
        eodhd_rows = {
            symbol: await fetch_eodhd_adjusted(client, token, symbol, start, end)
            for symbol in symbols
        }

    comparisons, diffs = compare_rows(api_rows, eodhd_rows)
    by_symbol: dict[str, list[float]] = defaultdict(list)
    for row in comparisons:
        by_symbol[row["symbol"]].append(row["abs_diff"])

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "symbols": symbols,
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "matched_rows": len(comparisons),
        "missing_eodhd_rows": {
            symbol: len(set(api_rows.get(symbol, {})) - set(eodhd_rows.get(symbol, {})))
            for symbol in symbols
        },
        "diff_distribution": {
            "max": max(diffs) if diffs else None,
            "median": median(diffs) if diffs else None,
            "p99": percentile(diffs, 99),
        },
        "diff_by_symbol": {
            symbol: {
                "rows": len(values),
                "max": max(values) if values else None,
                "median": median(values) if values else None,
                "p99": percentile(values, 99),
            }
            for symbol, values in sorted(by_symbol.items())
        },
        "momentum_reversal_risks": find_momentum_reversal_risk(api_rows, eodhd_rows, lookbacks),
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
