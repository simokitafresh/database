import numpy as np
import pandas as pd

from app.services.metrics import compute_metrics


def test_metrics_returns_finite_values_even_with_zeros():
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    prices = pd.DataFrame({"adj_close": [100, 0, 100]}, index=dates)
    result = compute_metrics({"AAA": prices})[0]

    assert result["n_days"] == 2
    assert np.isfinite(result["cagr"])
    assert np.isfinite(result["stdev"])
    assert np.isfinite(result["max_drawdown"])
