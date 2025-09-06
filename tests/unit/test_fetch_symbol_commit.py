import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
import pandas as pd


@pytest.mark.asyncio
async def test_fetch_symbol_data_commits_transaction():
    """fetch_symbol_data should commit after upserting prices."""
    from app.services.fetch_worker import fetch_symbol_data

    # Prepare mock DataFrame returned by yfinance
    df = pd.DataFrame({
        "Open": [1.0],
        "High": [1.0],
        "Low": [1.0],
        "Close": [1.0],
        "Volume": [100],
    })
    df.index = pd.DatetimeIndex([pd.Timestamp("2024-01-02")])
    df.index.name = "Date"

    with patch("yfinance.Ticker") as mock_ticker, \
         patch("app.services.fetch_worker.create_engine_and_sessionmaker") as mock_engine, \
         patch("app.services.upsert.upsert_prices", new=AsyncMock(return_value=(1, 0))):
        mock_ticker.return_value.history.return_value = df

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = mock_session
        mock_engine.return_value = (None, lambda: session_ctx)

        result = await fetch_symbol_data("AAPL", date(2024, 1, 1), date(2024, 1, 31))

        mock_session.commit.assert_awaited()
        assert result.status == "success"
