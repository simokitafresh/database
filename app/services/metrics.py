"""Financial metrics computation utilities."""

from typing import Dict, List

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _select_price_series(df: pd.DataFrame) -> pd.Series:
    """Return price series with a ``DatetimeIndex`` and missing values removed.

    Preferred column order: ``adj_close`` -> ``close`` -> ``Adj Close``.
    If a ``date`` column exists it will be used for the index.
    """

    col = None
    for candidate in ("adj_close", "close", "Adj Close"):
        if candidate in df.columns:
            col = candidate
            break
    if col is None:
        raise KeyError("price column not found (expected one of: adj_close, close, Adj Close)")

    series = df[col].copy()

    if "date" in df.columns:
        series.index = pd.to_datetime(df["date"])
    elif not isinstance(series.index, pd.DatetimeIndex):
        series.index = pd.to_datetime(series.index)

    return series.dropna().sort_index()


def _common_trading_index(series_map: Dict[str, pd.Series]) -> pd.DatetimeIndex:
    """Return sorted index of trading days common across all symbols."""

    common_index: pd.DatetimeIndex | None = None
    for series in series_map.values():
        idx = series.index
        common_index = idx if common_index is None else common_index.intersection(idx)

    if common_index is None:
        return pd.DatetimeIndex([])

    return common_index.sort_values()


def compute_metrics(price_frames: Dict[str, pd.DataFrame]) -> List[dict]:
    """Compute financial metrics on a common trading calendar.

    Each DataFrame may contain ``adj_close``, ``close`` or ``Adj Close`` columns.
    Metrics are computed after aligning all symbols on the intersection of non-missing
    trading days. Daily log returns are used:

    - ``CAGR = exp(sum(r) * 252 / N) - 1``
    - ``STDEV = std(r, ddof=1) * sqrt(252)``
    - ``MaxDD`` is derived from the cumulative equity curve.
    """

    if not price_frames:
        return []

    # Extract non-missing price series for each symbol
    series_map: Dict[str, pd.Series] = {}
    for symbol, frame in price_frames.items():
        if frame is None or len(frame) == 0:
            continue
        series_map[symbol] = _select_price_series(frame)

    if not series_map:
        return []

    # Determine common trading days across all symbols
    common_index = _common_trading_index(series_map)

    if len(common_index) <= 1:
        return [
            {
                "symbol": symbol,
                "cagr": 0.0,
                "stdev": 0.0,
                "max_drawdown": 0.0,
                "n_days": 0,
            }
            for symbol in price_frames.keys()
        ]

    results: List[dict] = []
    for symbol in price_frames.keys():
        series = series_map.get(symbol)
        if series is None:
            results.append(
                {
                    "symbol": symbol,
                    "cagr": 0.0,
                    "stdev": 0.0,
                    "max_drawdown": 0.0,
                    "n_days": 0,
                }
            )
            continue

        aligned = series.reindex(common_index)
        log_ret = np.log(aligned / aligned.shift(1)).dropna()
        n = int(log_ret.shape[0])

        if n <= 0:
            results.append(
                {
                    "symbol": symbol,
                    "cagr": 0.0,
                    "stdev": 0.0,
                    "max_drawdown": 0.0,
                    "n_days": 0,
                }
            )
            continue

        cagr = float(np.exp(log_ret.sum() * TRADING_DAYS_PER_YEAR / n) - 1)
        stdev = float(log_ret.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if n > 1 else 0.0
        curve = np.exp(log_ret.cumsum())
        drawdowns = 1.0 - curve / curve.cummax()
        max_dd = float(drawdowns.max()) if n > 0 else 0.0

        results.append(
            {
                "symbol": symbol,
                "cagr": cagr,
                "stdev": stdev,
                "max_drawdown": max_dd,
                "n_days": n,
            }
        )

    return results


__all__ = ["compute_metrics"]
