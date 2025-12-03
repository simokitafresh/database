import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
import pandas as pd

from app.services.fetch_worker import fetch_symbol_data

@pytest.mark.asyncio
async def test_fetch_symbol_data_triggers_autofix_on_split():
    """Test that split events trigger auto-fix functionality."""
    
    with patch("app.services.fetch_worker.settings") as mock_settings:
        mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
        mock_settings.DB_POOL_PRE_PING = False
        mock_settings.DB_POOL_RECYCLE = 3600
        mock_settings.ADJUSTMENT_AUTO_FIX = True  # Enable auto-fix
        
        # Mock data with split event
        mock_df = pd.DataFrame({
            "open": [100.0], "high": [110.0], "low": [90.0], "close": [105.0], "volume": [1000]
        }, index=pd.to_datetime(["2020-01-01"]))
        
        mock_events = [
            {
                "date": date(2020, 1, 1),
                "type": "stock_split",
                "ratio": 2.0,
                "symbol": "AAPL"
            }
        ]
        
        # Mock run_in_threadpool
        async def mock_run_in_threadpool(func, *args, **kwargs):
            return mock_df, mock_events
        
        with patch("app.services.fetch_worker.run_in_threadpool", side_effect=mock_run_in_threadpool):
            
            # Mock sessions
            mock_session = AsyncMock()
            mock_session_cls = MagicMock(return_value=mock_session)
            mock_session.__aenter__.return_value = mock_session
            
            # Mock Adjustment Fixer at SOURCE module
            with patch("app.services.adjustment_fixer.AdjustmentFixer") as MockFixer:
                mock_fixer_instance = AsyncMock()
                mock_fixer_instance.auto_fix_symbol = AsyncMock(return_value={
                    "symbol": "AAPL",
                    "deleted_rows": 100,
                    "job_id": "test_job_123",
                    "job_created": True
                })
                MockFixer.return_value = mock_fixer_instance
                
                # Mock CorporateEvent query
                mock_event_obj = MagicMock()
                mock_event_obj.id = 1
                mock_event_obj.symbol = "AAPL"
                mock_event_obj.event_type = "stock_split"
                
                mock_query_result = AsyncMock()
                mock_query_result.scalar_one_or_none = AsyncMock(return_value=mock_event_obj)
                
                mock_session.execute = AsyncMock(return_value=mock_query_result)
                
                with patch("app.services.fetch_worker.create_engine_and_sessionmaker", return_value=(None, mock_session_cls)):
                    with patch("app.services.fetch_worker.record_event", new_callable=AsyncMock):
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
                            
                            # Verify auto_fix_symbol was called
                            assert mock_fixer_instance.auto_fix_symbol.call_count == 1
                            call_args = mock_fixer_instance.auto_fix_symbol.call_args
                            assert call_args[0][0] == "AAPL"  # symbol
                            assert call_args[0][1] == 1  # event_id


@pytest.mark.asyncio
async def test_fetch_symbol_data_no_autofix_when_disabled():
    """Test that auto-fix is skipped when ADJUSTMENT_AUTO_FIX=False."""
    
    with patch("app.services.fetch_worker.settings") as mock_settings:
        mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
        mock_settings.DB_POOL_PRE_PING = False
        mock_settings.DB_POOL_RECYCLE = 3600
        mock_settings.ADJUSTMENT_AUTO_FIX = False  # Disable auto-fix
        
        mock_df = pd.DataFrame({
            "open": [100.0], "high": [110.0], "low": [90.0], "close": [105.0], "volume": [1000]
        }, index=pd.to_datetime(["2020-01-01"]))
        
        mock_events = [
            {
                "date": date(2020, 1, 1),
                "type": "stock_split",
                "ratio": 2.0,
                "symbol": "AAPL"
            }
        ]
        
        async def mock_run_in_threadpool(func, *args, **kwargs):
            return mock_df, mock_events
        
        with patch("app.services.fetch_worker.run_in_threadpool", side_effect=mock_run_in_threadpool):
            mock_session = AsyncMock()
            mock_session_cls = MagicMock(return_value=mock_session)
            mock_session.__aenter__.return_value = mock_session
            
            with patch("app.services.adjustment_fixer.AdjustmentFixer") as MockFixer:
                with patch("app.services.fetch_worker.create_engine_and_sessionmaker", return_value=(None, mock_session_cls)):
                    with patch("app.services.fetch_worker.record_event", new_callable=AsyncMock):
                        with patch("app.services.fetch_worker.upsert_prices", new_callable=AsyncMock) as mock_upsert:
                            mock_upsert.return_value = (1, 0)
                            
                            result = await fetch_symbol_data(
                                symbol="AAPL",
                                date_from=date(2020, 1, 1),
                                date_to=date(2020, 1, 2)
                            )
                            
                            # Verify AdjustmentFixer was NOT instantiated
                            assert MockFixer.call_count == 0
