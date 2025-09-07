from datetime import date
from urllib.error import HTTPError

import pandas as pd

from app.core.config import Settings
from app.services.fetcher import fetch_prices


def _sample_df():
    return pd.DataFrame(
        {
            "Open": [1.0],
            "High": [1.0],
            "Low": [1.0],
            "Close": [1.0],
            "Volume": [100],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )


def test_fetch_prices_backoff(mocker):
    settings = Settings()
    download = mocker.patch("app.services.fetcher.yf.download")
    sleep = mocker.patch("app.services.fetcher.time.sleep")
    error = HTTPError(url=None, code=429, msg="Too Many Requests", hdrs=None, fp=None)
    download.side_effect = [error, error, _sample_df()]

    df = fetch_prices("AAPL", date(2024, 1, 1), date(2024, 1, 2), settings=settings)

    assert download.call_count == 3
    assert sleep.call_args_list == [mocker.call(1.0), mocker.call(2.0)]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_fetch_prices_end_inclusive(mocker):
    """Test that yfinance end parameter is made inclusive by adding 1 day."""
    settings = Settings()
    download = mocker.patch("app.services.fetcher.yf.download", return_value=_sample_df())

    fetch_prices("AAPL", date(2024, 1, 1), date(2024, 1, 2), settings=settings)

    # yfinanceのend引数が排他的なので、内部で+1日されていることを確認
    assert download.call_args.kwargs["end"] == date(2024, 1, 3)
