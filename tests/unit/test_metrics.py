import pandas as pd
import numpy as np
import pytest

from app.services.metrics import compute_metrics


def test_compute_metrics_formulas():
    dates = pd.date_range('2020-01-01', periods=4, freq='D')
    prices = pd.DataFrame({'adj_close': [100, 120, 80, 90]}, index=dates)
    result = compute_metrics({'AAA': prices})[0]

    log_ret = np.log(prices['adj_close'] / prices['adj_close'].shift(1)).dropna()
    n = len(log_ret)
    expected_cagr = np.exp(log_ret.sum() * 252 / n) - 1
    expected_stdev = log_ret.std(ddof=1) * np.sqrt(252)
    curve = np.exp(log_ret.cumsum())
    expected_maxdd = (1 - curve / curve.cummax()).max()

    assert result['symbol'] == 'AAA'
    assert result['n_days'] == n
    assert result['cagr'] == pytest.approx(expected_cagr)
    assert result['stdev'] == pytest.approx(expected_stdev)
    assert result['max_drawdown'] == pytest.approx(expected_maxdd)
