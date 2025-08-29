import numpy as np
import pandas as pd

from app.services.upsert import df_to_rows


def test_df_to_rows_returns_dicts():
    df = pd.DataFrame(
        {
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.05],
            "volume": [100],
        },
        index=pd.to_datetime(["2023-01-01"]),
    )
    rows = df_to_rows(df, symbol="AAPL", source="yfinance")
    assert isinstance(rows, list) and len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {"symbol", "date", "open", "high", "low", "close", "volume", "source"}


def test_df_to_rows_skips_nan_rows():
    df = pd.DataFrame(
        {
            "open": [1.0, np.nan],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.05, 2.05],
            "volume": [100, 200],
        },
        index=pd.to_datetime(["2023-01-01", "2023-01-02"]),
    )
    rows = df_to_rows(df, symbol="AAPL", source="yfinance")
    assert len(rows) == 1
    assert rows[0]["date"].isoformat() == "2023-01-01"
