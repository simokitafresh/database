from datetime import date

import pandas as pd
import pytest
import requests

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


def test_requests_timeout_is_retried_then_succeeds(mocker):
    settings = Settings(FETCH_MAX_RETRIES=3, FETCH_BACKOFF_MAX_SECONDS=2)
    download = mocker.patch("app.services.fetcher.yf.download")
    sleep = mocker.patch("app.services.fetcher.time.sleep")
    download.side_effect = [requests.exceptions.Timeout("boom"), _sample_df()]

    df = fetch_prices("AAPL", date(2024, 1, 1), date(2024, 1, 2), settings=settings)

    assert download.call_count == 2
    assert sleep.call_args_list == [mocker.call(1.0)]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_retry_succeeds_within_limit(mocker):
    settings = Settings(FETCH_MAX_RETRIES=3, FETCH_BACKOFF_MAX_SECONDS=2)
    download = mocker.patch("app.services.fetcher.yf.download")
    sleep = mocker.patch("app.services.fetcher.time.sleep")
    download.side_effect = [TimeoutError("boom"), TimeoutError("boom"), _sample_df()]

    df = fetch_prices("AAPL", date(2024, 1, 1), date(2024, 1, 2), settings=settings)

    assert download.call_count == 3
    assert sleep.call_args_list == [mocker.call(1.0), mocker.call(2.0)]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_retry_exceeds_limit_raises(mocker):
    settings = Settings(FETCH_MAX_RETRIES=2, FETCH_BACKOFF_MAX_SECONDS=2)
    download = mocker.patch("app.services.fetcher.yf.download", side_effect=TimeoutError("boom"))
    sleep = mocker.patch("app.services.fetcher.time.sleep")

    with pytest.raises(TimeoutError):
        fetch_prices("AAPL", date(2024, 1, 1), date(2024, 1, 2), settings=settings)

    assert download.call_count == 2
    assert sleep.call_args_list == [mocker.call(1.0)]
