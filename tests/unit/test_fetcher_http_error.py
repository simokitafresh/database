import pandas as pd
import pytest
import requests
from datetime import date

from app.core.config import Settings
from app.services import fetcher


def _sample_df():
    return pd.DataFrame(
        {
            "Open": [1.0],
            "High": [1.0],
            "Low": [1.0],
            "Close": [1.0],
            "Adj Close": [1.0],
            "Volume": [100],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )


@pytest.mark.parametrize("status", [429, 999])
def test_fetcher_retries_on_http_error(status, mocker):
    settings = Settings(FETCH_MAX_RETRIES=3, FETCH_BACKOFF_MAX_SECONDS=2)
    err = requests.exceptions.HTTPError(response=mocker.Mock(status_code=status))
    download = mocker.patch("app.services.fetcher.yf.download", side_effect=[err, _sample_df()])
    sleep = mocker.patch("app.services.fetcher.time.sleep")

    df = fetcher.fetch_prices("AAPL", date(2024, 1, 1), date(2024, 1, 2), settings=settings)

    assert download.call_count == 2
    assert sleep.call_count == 1
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
