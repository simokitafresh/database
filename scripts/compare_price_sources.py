#!/usr/bin/env python3
"""Compare month-end open/close prices across candidate data sources.

This script is intentionally read-only. It fetches recent month-end prices from
Alpaca, EODHD, Tiingo, and yfinance, then writes CSV/Markdown comparison
artifacts for manual source selection.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import yfinance as yf


CORE_SYMBOLS = ["LQD", "TECL", "XLU", "QQQ", "GLD", "SPY", "TQQQ", "TMV", "GDX", "QLD", "TMF", "VIX"]
MONTH_ENDS = [date(2026, 4, 30), date(2026, 5, 29), date(2026, 6, 30)]
RAW_SOURCES = ["alpaca", "eodhd", "tiingo"]
OUTPUT_DIR = Path("reports/price_source_comparison")
HTTP_TIMEOUT = 30.0
SECRET_QUERY_RE = re.compile(r"([?&](?:token|api_token)=)[^&'\\s]+", re.IGNORECASE)


@dataclass(frozen=True)
class PricePoint:
    symbol: str
    date: date
    source: str
    open: float | None
    close: float | None
    adj_close: float | None
    volume: int | None
    status: str
    note: str


def load_env(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def parse_float(value: Any) -> float | None:
    if value in (None, "", "NA", "N/A"):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    return None if parsed is None else int(parsed)


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def safe_error(exc: Exception) -> str:
    return SECRET_QUERY_RE.sub(r"\1<redacted>", f"{type(exc).__name__}: {exc}")


def eodhd_symbol(symbol: str) -> str:
    if symbol == "VIX":
        return "VIX.INDX"
    return f"{symbol}.US"


def yf_symbol(symbol: str) -> str:
    return "^VIX" if symbol == "VIX" else symbol


def tiingo_symbol(symbol: str) -> str:
    return "^VIX" if symbol == "VIX" else symbol.lower()


def fetch_alpaca(symbol: str, dates: list[date], client: httpx.Client) -> list[PricePoint]:
    if symbol == "VIX":
        return [
            PricePoint(symbol, target_date, "alpaca", None, None, None, None, "unsupported", "VIX index is not a stock bar symbol on Alpaca")
            for target_date in dates
        ]

    key = require_env("ALPACA_API_KEY_ID")
    secret = require_env("ALPACA_API_SECRET_KEY")
    params = {
        "start": min(dates).isoformat(),
        "end": (max(dates) + timedelta(days=1)).isoformat(),
        "timeframe": "1Day",
        "feed": "iex",
        "adjustment": "raw",
        "limit": 1000,
    }
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    try:
        response = client.get(url, params=params, headers=headers)
        response.raise_for_status()
        bars = response.json().get("bars") or []
        by_date = {datetime.fromisoformat(row["t"].replace("Z", "+00:00")).date(): row for row in bars}
        points: list[PricePoint] = []
        for target_date in dates:
            row = by_date.get(target_date)
            if row is None:
                points.append(PricePoint(symbol, target_date, "alpaca", None, None, None, None, "missing", "no bar returned"))
            else:
                points.append(
                    PricePoint(
                        symbol,
                        target_date,
                        "alpaca",
                        parse_float(row.get("o")),
                        parse_float(row.get("c")),
                        None,
                        parse_int(row.get("v")),
                        "ok",
                        "feed=iex adjustment=raw",
                    )
                )
        return points
    except Exception as exc:
        return [
            PricePoint(symbol, target_date, "alpaca", None, None, None, None, "error", safe_error(exc))
            for target_date in dates
        ]


def fetch_eodhd(symbol: str, dates: list[date], client: httpx.Client) -> list[PricePoint]:
    token = require_env("EODHD_API_TOKEN")
    params = {
        "api_token": token,
        "fmt": "json",
        "from": min(dates).isoformat(),
        "to": max(dates).isoformat(),
    }
    url = f"https://eodhd.com/api/eod/{eodhd_symbol(symbol)}"
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("code"):
            raise RuntimeError(json.dumps(payload, ensure_ascii=False))
        by_date = {date.fromisoformat(row["date"]): row for row in payload}
        points: list[PricePoint] = []
        for target_date in dates:
            row = by_date.get(target_date)
            if row is None:
                points.append(PricePoint(symbol, target_date, "eodhd", None, None, None, None, "missing", "no EOD row returned"))
            else:
                points.append(
                    PricePoint(
                        symbol,
                        target_date,
                        "eodhd",
                        parse_float(row.get("open")),
                        parse_float(row.get("close")),
                        parse_float(row.get("adjusted_close")),
                        parse_int(row.get("volume")),
                        "ok",
                        f"ticker={eodhd_symbol(symbol)}",
                    )
                )
        return points
    except Exception as exc:
        return [
            PricePoint(symbol, target_date, "eodhd", None, None, None, None, "error", safe_error(exc))
            for target_date in dates
        ]


def fetch_tiingo(symbol: str, dates: list[date], client: httpx.Client) -> list[PricePoint]:
    token = require_env("TIINGO_API_TOKEN")
    params = {
        "startDate": min(dates).isoformat(),
        "endDate": max(dates).isoformat(),
        "token": token,
    }
    ticker = tiingo_symbol(symbol)
    url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            raise RuntimeError(json.dumps(payload, ensure_ascii=False))
        by_date = {datetime.fromisoformat(row["date"].replace("Z", "+00:00")).date(): row for row in payload}
        points: list[PricePoint] = []
        for target_date in dates:
            row = by_date.get(target_date)
            if row is None:
                points.append(PricePoint(symbol, target_date, "tiingo", None, None, None, None, "missing", "no Tiingo row returned"))
            else:
                points.append(
                    PricePoint(
                        symbol,
                        target_date,
                        "tiingo",
                        parse_float(row.get("open")),
                        parse_float(row.get("close")),
                        parse_float(row.get("adjClose")),
                        parse_int(row.get("volume")),
                        "ok",
                        f"ticker={ticker}",
                    )
                )
        return points
    except Exception as exc:
        return [
            PricePoint(symbol, target_date, "tiingo", None, None, None, None, "error", safe_error(exc))
            for target_date in dates
        ]


def fetch_yfinance(symbol: str, dates: list[date]) -> list[PricePoint]:
    ticker = yf_symbol(symbol)
    try:
        df = yf.download(
            ticker,
            start=min(dates).isoformat(),
            end=(max(dates) + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
            timeout=HTTP_TIMEOUT,
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        points: list[PricePoint] = []
        for target_date in dates:
            key = pd.Timestamp(target_date)
            if key not in df.index:
                points.append(PricePoint(symbol, target_date, "stockdata_yfinance", None, None, None, None, "missing", "no yfinance row returned"))
                continue
            row = df.loc[key]
            points.append(
                PricePoint(
                    symbol,
                    target_date,
                    "stockdata_yfinance",
                    parse_float(row.get("Open")),
                    None,
                    parse_float(row.get("Close")),
                    parse_int(row.get("Volume")),
                    "ok",
                    f"ticker={ticker} auto_adjust=True",
                )
            )
        return points
    except Exception as exc:
        return [
            PricePoint(symbol, target_date, "stockdata_yfinance", None, None, None, None, "error", safe_error(exc))
            for target_date in dates
        ]


def write_raw(points: list[PricePoint], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["symbol", "date", "source", "open", "close", "adj_close", "volume", "status", "note"],
        )
        writer.writeheader()
        for point in points:
            writer.writerow(
                {
                    "symbol": point.symbol,
                    "date": point.date.isoformat(),
                    "source": point.source,
                    "open": fmt(point.open),
                    "close": fmt(point.close),
                    "adj_close": fmt(point.adj_close),
                    "volume": "" if point.volume is None else point.volume,
                    "status": point.status,
                    "note": point.note,
                }
            )


def build_summary(points: list[PricePoint]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, date], list[PricePoint]] = {}
    for point in points:
        by_key.setdefault((point.symbol, point.date), []).append(point)

    rows: list[dict[str, Any]] = []
    for (symbol, target_date), group in sorted(by_key.items()):
        raw = [point for point in group if point.source in RAW_SOURCES and point.close is not None]
        yf_point = next((point for point in group if point.source == "stockdata_yfinance"), None)
        raw_closes = [point.close for point in raw if point.close is not None]
        raw_opens = [point.open for point in raw if point.open is not None]
        max_raw_close_diff = max(raw_closes) - min(raw_closes) if len(raw_closes) >= 2 else None
        max_raw_open_diff = max(raw_opens) - min(raw_opens) if len(raw_opens) >= 2 else None
        eodhd_point = next((point for point in group if point.source == "eodhd"), None)
        tiingo_point = next((point for point in group if point.source == "tiingo"), None)
        alpaca_point = next((point for point in group if point.source == "alpaca"), None)
        eodhd_tiingo_close_diff = None
        if eodhd_point and tiingo_point and eodhd_point.close is not None and tiingo_point.close is not None:
            eodhd_tiingo_close_diff = eodhd_point.close - tiingo_point.close
        alpaca_vs_raw_median = None
        if alpaca_point and alpaca_point.close is not None and raw_closes:
            alpaca_vs_raw_median = alpaca_point.close - float(pd.Series(raw_closes).median())
        yf_adj_vs_eodhd_adj = None
        if yf_point and eodhd_point and yf_point.adj_close is not None and eodhd_point.adj_close is not None:
            yf_adj_vs_eodhd_adj = yf_point.adj_close - eodhd_point.adj_close
        yf_adj_vs_tiingo_adj = None
        if yf_point and tiingo_point and yf_point.adj_close is not None and tiingo_point.adj_close is not None:
            yf_adj_vs_tiingo_adj = yf_point.adj_close - tiingo_point.adj_close
        rows.append(
            {
                "symbol": symbol,
                "date": target_date.isoformat(),
                "raw_source_count": len(raw_closes),
                "max_raw_open_diff": max_raw_open_diff,
                "max_raw_close_diff": max_raw_close_diff,
                "eodhd_tiingo_close_diff": eodhd_tiingo_close_diff,
                "alpaca_vs_raw_median_close": alpaca_vs_raw_median,
                "yf_adj_vs_eodhd_adj": yf_adj_vs_eodhd_adj,
                "yf_adj_vs_tiingo_adj": yf_adj_vs_tiingo_adj,
                "statuses": "; ".join(f"{point.source}:{point.status}" for point in sorted(group, key=lambda item: item.source)),
            }
        )
    return rows


def write_summary(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, Any]], points: list[PricePoint], path: Path) -> None:
    ok_rows = [row for row in rows if row["raw_source_count"] >= 2]
    raw_close_diffs = [row["max_raw_close_diff"] for row in ok_rows if row["max_raw_close_diff"] is not None]
    yf_eodhd_diffs = [row["yf_adj_vs_eodhd_adj"] for row in rows if row["yf_adj_vs_eodhd_adj"] is not None]
    yf_tiingo_diffs = [row["yf_adj_vs_tiingo_adj"] for row in rows if row["yf_adj_vs_tiingo_adj"] is not None]
    eodhd_tiingo_matches = [
        row for row in rows if row["eodhd_tiingo_close_diff"] is not None and abs(row["eodhd_tiingo_close_diff"]) <= 0.01
    ]
    alpaca_close_within_cent = [
        row for row in rows if row["alpaca_vs_raw_median_close"] is not None and abs(row["alpaca_vs_raw_median_close"]) <= 0.01
    ]
    errors = [point for point in points if point.status != "ok"]
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Price Source Comparison Summary",
        "",
        f"- generated_at_utc: {generated_at}",
        f"- symbols: {len(CORE_SYMBOLS)}",
        f"- month_ends: {', '.join(day.isoformat() for day in MONTH_ENDS)}",
        f"- source_points_ok: {sum(1 for point in points if point.status == 'ok')}/{len(points)}",
        f"- raw_source_rows_with_2plus_sources: {len(ok_rows)}/{len(rows)}",
        f"- eodhd_tiingo_close_within_0.01: {len(eodhd_tiingo_matches)}/{sum(1 for row in rows if row['eodhd_tiingo_close_diff'] is not None)}",
        f"- alpaca_close_vs_raw_median_within_0.01: {len(alpaca_close_within_cent)}/{sum(1 for row in rows if row['alpaca_vs_raw_median_close'] is not None)}",
        f"- max_raw_close_diff_abs: {max((abs(value) for value in raw_close_diffs), default=None)}",
        f"- max_yfinance_adjusted_vs_eodhd_adjusted_abs: {max((abs(value) for value in yf_eodhd_diffs), default=None)}",
        f"- max_yfinance_adjusted_vs_tiingo_adjusted_abs: {max((abs(value) for value in yf_tiingo_diffs), default=None)}",
        "",
        "## Interpretation",
        "",
        "- Alpaca rows use `feed=iex` and `adjustment=raw`; this measures the free IEX feed, not paid SIP.",
        "- EODHD and Tiingo raw close agreement is the strongest free-source proxy for exchange EOD close.",
        "- Stockdata/yfinance is recorded as adjusted close because the current service stores adjusted OHLCV.",
        "",
        "## Non-OK Points",
        "",
    ]
    if errors:
        for point in errors:
            lines.append(f"- {point.symbol} {point.date} {point.source}: {point.status} ({point.note})")
    else:
        lines.append("- none")
    lines.extend(["", "## Source Recommendation", ""])
    if eodhd_tiingo_matches and len(eodhd_tiingo_matches) >= max(1, int(0.9 * len(ok_rows))):
        lines.append("- Primary candidate: EODHD, with Tiingo as independent verifier. Rationale: EODHD/Tiingo raw closes match within $0.01 on most comparable rows.")
    else:
        lines.append("- Primary candidate: unresolved. EODHD/Tiingo raw close agreement is below the 90% threshold in this run.")
    if alpaca_close_within_cent:
        lines.append("- Alpaca IEX: useful as a third check, but IEX-only coverage should not be treated as full-market SIP unless paid SIP access is confirmed.")
    else:
        lines.append("- Alpaca IEX: not recommended as primary from this run; close differs from the raw-source median or coverage is missing.")
    lines.append("- yfinance/Stockdata: keep as reference only; adjusted values can agree numerically while still being unsuitable as the immutable raw source.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--sleep", type=float, default=0.2, help="seconds to sleep between provider requests")
    args = parser.parse_args()

    load_env([Path(".env"), Path("Stockdata-API.env")])
    args.output_dir.mkdir(parents=True, exist_ok=True)

    points: list[PricePoint] = []
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for symbol in CORE_SYMBOLS:
            points.extend(fetch_alpaca(symbol, MONTH_ENDS, client))
            time.sleep(args.sleep)
            points.extend(fetch_eodhd(symbol, MONTH_ENDS, client))
            time.sleep(args.sleep)
            points.extend(fetch_tiingo(symbol, MONTH_ENDS, client))
            time.sleep(args.sleep)
            points.extend(fetch_yfinance(symbol, MONTH_ENDS))

    raw_path = args.output_dir / "price_source_raw.csv"
    summary_path = args.output_dir / "price_source_summary.csv"
    md_path = args.output_dir / "price_source_summary.md"

    write_raw(points, raw_path)
    rows = build_summary(points)
    write_summary(rows, summary_path)
    write_markdown(rows, points, md_path)

    print(f"wrote {raw_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
