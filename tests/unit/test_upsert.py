import pandas as pd

from app.services.upsert import df_to_rows, upsert_prices_sql


def test_upsert_sql_contains_on_conflict():
    sql = upsert_prices_sql()
    assert "ON CONFLICT (symbol, date) DO UPDATE" in sql


def test_df_to_rows_drops_nan_and_casts():
    df = pd.DataFrame(
        {
            "open": [1.0, 2.0, None],
            "high": [1.1, 2.1, 3.1],
            "low": [0.9, 1.9, 2.9],
            "close": [1.05, 2.05, 3.05],
            "volume": [100, 200, 300],
        },
        index=pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
    )
    rows = df_to_rows(df, symbol="AAPL", source="yfinance")
    # The row with None open should be dropped
    assert len(rows) == 2
    first = rows[0]
    assert first[0] == "AAPL"
    assert str(first[1]) == "2023-01-01"
    assert first[-1] == "yfinance"
    assert isinstance(first[6], int)
