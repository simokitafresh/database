import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
from decimal import Decimal
import pandas as pd

from app.services.fetch_worker import fetch_symbol_data
from app.schemas.fetch_jobs import FetchJobResult
from app.schemas.events import EventTypeEnum

@pytest.mark.asyncio
async def test_fetch_symbol_data_records_events():
    # Mock settings
    with patch("app.services.fetch_worker.settings") as mock_settings:
        mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
        mock_settings.DB_POOL_PRE_PING = False
        mock_settings.DB_POOL_RECYCLE = 3600

        # Mock fetch_prices_and_events
        mock_df = pd.DataFrame({
            "open": [100.0], "high": [110.0], "low": [90.0], "close": [105.0], "volume": [1000]
        }, index=pd.to_datetime(["2020-01-01"]))
        
        mock_events = [
            {
                "date": date(2020, 1, 1),
                "type": "stock_split",
                "ratio": 4.0,
                "symbol": "AAPL"
            }
        ]

        # Mock run_in_threadpool to return our data immediately
        async def mock_run_in_threadpool(func, *args, **kwargs):
            return mock_df, mock_events

        with patch("app.services.fetch_worker.run_in_threadpool", side_effect=mock_run_in_threadpool):
            
            # Mock create_engine_and_sessionmaker to return a mock session
            mock_session = AsyncMock()
            mock_session_cls = MagicMock(return_value=mock_session)
            mock_session.__aenter__.return_value = mock_session
            
            with patch("app.services.fetch_worker.create_engine_and_sessionmaker", return_value=(None, mock_session_cls)):
                
                # Mock record_event
                with patch("app.services.fetch_worker.record_event", new_callable=AsyncMock) as mock_record_event:
                    
                    # Mock upsert_prices
                    with patch("app.services.fetch_worker.upsert_prices", new_callable=AsyncMock) as mock_upsert:
                        mock_upsert.return_value = (1, 0)

                        # Run the function
                        result = await fetch_symbol_data(
                            symbol="AAPL",
                            date_from=date(2020, 1, 1),
                            date_to=date(2020, 1, 2)
                        )

                        # Verify result
                        assert result.status == "success"
                        assert result.rows_fetched == 1

                        # Verify record_event was called
                        assert mock_record_event.call_count == 1
                        call_args = mock_record_event.call_args
                        event_data = call_args[0][1]
                        
                        assert event_data.symbol == "AAPL"
                        assert event_data.event_type == EventTypeEnum.STOCK_SPLIT
                        assert event_data.ratio == Decimal("4.0")
