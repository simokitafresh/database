from typing import Any, Dict, List
import pandas as pd


def compute_metrics(price_frames: Dict[str, pd.DataFrame]) -> List[dict[str, Any]]:
    import numpy as np

    """Compute financial metrics for provided price data.

    Each DataFrame must contain an ``adj_close`` column indexed by date.
    The function calculates daily log returns and derives annualised metrics
    using the formulas:

    - ``CAGR = exp(sum(r) * 252 / N) - 1``
    - ``STDEV = std(r, ddof=1) * sqrt(252)``
    - ``MaxDD = min(exp(cum_r - cum_r.cummax()) - 1)``
    """
    results: List[dict[str, Any]] = []

    for symbol, df in price_frames.items():
        prices = df["adj_close"].dropna().astype(float)
        log_ret = np.log(prices / prices.shift(1)).dropna()
        n = len(log_ret)
        if n == 0:
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

        cagr = float(np.exp(log_ret.sum() * 252 / n) - 1)
        stdev = float(log_ret.std(ddof=1) * np.sqrt(252))
        cum_r = log_ret.cumsum()
        drawdowns = np.exp(cum_r - cum_r.cummax()) - 1
        max_dd = float(drawdowns.min())

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
