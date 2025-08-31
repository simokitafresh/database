from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Optional
from urllib.error import HTTPError as URLlibHTTPError

import pandas as pd
import requests
import yfinance as yf
from requests.exceptions import HTTPError as RequestsHTTPError

from app.core.config import Settings


def fetch_prices(
    symbol: str,
    start: date,
    end: date,
    *,
    settings: Settings,
    last_date: Optional[date] = None,
) -> pd.DataFrame:
    """Fetch adjusted OHLCV data for ``symbol`` between ``start`` and ``end``.

    Parameters
    ----------
    symbol:
        Ticker symbol understood by Yahoo Finance.
    start, end:
        Date range for the fetch. ``end`` is inclusive.
    settings:
        Application settings providing timeout and refetch parameters.
    last_date:
        Last date of existing data in the database.  If provided, the fetch will
        start from ``max(start, last_date - settings.YF_REFETCH_DAYS)`` to
        re-download the most recent ``N`` days for adjustments.

    Returns
    -------
    pandas.DataFrame
        Data frame with columns ``open``, ``high``, ``low``, ``close``,
        ``volume`` and a ``DatetimeIndex``.

    Note
    ----
    yfinance's end parameter is exclusive, so we add 1 day internally
    to ensure the end date is included in the results.
    """

    fetch_start = start
    if last_date is not None:
        refetch_start = last_date - timedelta(days=settings.YF_REFETCH_DAYS)
        if refetch_start > fetch_start:
            fetch_start = refetch_start

    # yfinanceのend引数は排他的なので、1日加算して包含的にする
    fetch_end = end + timedelta(days=1)

    attempts = 0
    delay = 1.0
    max_attempts = settings.FETCH_MAX_RETRIES

    while True:
        try:
            df = yf.download(
                symbol,
                start=fetch_start,
                end=fetch_end,  # 修正: end → fetch_end (yfinanceの排他的仕様に対応)
                auto_adjust=True,
                progress=False,
                timeout=settings.FETCH_TIMEOUT_SECONDS,
            )
            df = df.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Adj Close": "adj_close",
                    "Volume": "volume",
                }
            )
            if "adj_close" in df.columns:
                df = df.drop(columns=["adj_close"])

            # Guard against empty frames or missing required columns
            required_columns = {"open", "high", "low", "close", "volume"}
            if df is None or df.empty or not required_columns.issubset(df.columns):
                # Fallback: try Ticker().history which sometimes succeeds when download() returns empty
                try:
                    tk = yf.Ticker(symbol)
                    df2 = tk.history(
                        start=fetch_start,
                        end=fetch_end,
                        auto_adjust=True,
                        timeout=settings.FETCH_TIMEOUT_SECONDS,
                    )
                    df2 = df2.rename(
                        columns={
                            "Open": "open",
                            "High": "high",
                            "Low": "low",
                            "Close": "close",
                            "Adj Close": "adj_close",
                            "Volume": "volume",
                        }
                    )
                    if "adj_close" in df2.columns:
                        df2 = df2.drop(columns=["adj_close"])
                    if df2 is not None and not df2.empty and required_columns.issubset(df2.columns):
                        return df2
                except Exception:
                    pass
                return pd.DataFrame()

            return df
        except (
            URLlibHTTPError,
            RequestsHTTPError,
            TimeoutError,
            requests.exceptions.Timeout,
            requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectTimeout,
        ) as exc:  # pragma: no cover - branch executed in tests
            status = getattr(exc, "code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            retryable = isinstance(
                exc,
                (
                    TimeoutError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectTimeout,
                ),
            ) or status in {429, 999}
            if retryable and attempts < max_attempts - 1:
                time.sleep(delay)
                delay = min(delay * 2, settings.FETCH_BACKOFF_MAX_SECONDS)
                attempts += 1
                continue
            raise


__all__ = ["fetch_prices"]
