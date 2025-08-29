import math

import pandas as pd

from app.services.metrics import compute_metrics


def _df(dates, prices):
    return pd.DataFrame({"adj_close": prices}, index=pd.to_datetime(dates))


def test_common_trading_days_intersection_applied():
    # AAA is missing 2021-01-03
    dates_a = ["2021-01-01", "2021-01-02", "2021-01-04", "2021-01-05"]
    prices_a = [100.0, 101.0, 102.0, 103.0]
    df_a = _df(dates_a, prices_a)

    # BBB is missing 2021-01-02
    dates_b = ["2021-01-01", "2021-01-03", "2021-01-04", "2021-01-05"]
    prices_b = [200.0, 202.0, 204.0, 206.0]
    df_b = _df(dates_b, prices_b)

    res = compute_metrics({"AAA": df_a, "BBB": df_b})
    by_symbol = {r["symbol"]: r for r in res}

    # Common trading days are 01-01, 01-04, 01-05 -> three days -> N=2 returns
    assert by_symbol["AAA"]["n_days"] == 2
    assert by_symbol["BBB"]["n_days"] == 2

    # Ensure metrics are numeric and not NaN
    for key in ("cagr", "stdev", "max_drawdown"):
        assert isinstance(by_symbol["AAA"][key], float)
        assert not math.isnan(by_symbol["AAA"][key])


def test_empty_or_single_day_results_are_safe():
    df1 = _df(["2021-01-01"], [100.0])
    df2 = _df(["2021-01-01"], [200.0])

    res = compute_metrics({"X": df1, "Y": df2})
    for r in res:
        assert r["n_days"] == 0
        assert r["cagr"] == 0.0
        assert r["stdev"] == 0.0
        assert r["max_drawdown"] == 0.0

