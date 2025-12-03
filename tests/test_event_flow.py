import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
import pandas as pd

from app.services.daily_update_service import DailyUpdateService
from app.schemas.cron import CronDailyUpdateRequest
from app.schemas.events import EventTypeEnum, EventStatusEnum, CorporateEventCreate
from app.db.models import CorporateEvent

@pytest.mark.asyncio
async def test_event_driven_fix_flow():
    """Test that a detected split triggers a fix (using mocks)."""
    
    # Mock Session
    session = AsyncMock()
    
    # Mock list_symbols to return one symbol
    # list_symbols returns a list of Row objects or dict-like
    with patch("app.services.daily_update_service.list_symbols", new_callable=AsyncMock) as mock_list_symbols:
        mock_list_symbols.return_value = [{"symbol": "TEST_SPLIT"}]
        
        # Mock ensure_coverage to simulate the callback execution
        # We need to manually call the on_events callback passed to ensure_coverage
        async def mock_ensure_coverage(*args, **kwargs):
            on_events = kwargs.get("on_events")
            if on_events:
                # Simulate detecting a split event
                events = [{
                    "symbol": "TEST_SPLIT",
                    "date": date(2024, 1, 5),
                    "type": "stock_split",
                    "ratio": 2.0
                }]
                await on_events(events)
        
        with patch("app.services.daily_update_service.ensure_coverage", side_effect=mock_ensure_coverage) as mock_ensure_cov:
            
            # Mock event_service.record_event
            # It should return a CorporateEvent object
            mock_event = MagicMock(spec=CorporateEvent)
            mock_event.symbol = "TEST_SPLIT"
            mock_event.id = 123
            mock_event.event_type = EventTypeEnum.STOCK_SPLIT
            mock_event.status = EventStatusEnum.DETECTED
            
            with patch("app.services.event_service.record_event", new_callable=AsyncMock) as mock_record_event:
                mock_record_event.return_value = mock_event
                
                # Mock AdjustmentFixer
                with patch("app.services.daily_update_service.AdjustmentFixer") as MockFixer:
                    mock_fixer_instance = MockFixer.return_value
                    mock_fixer_instance.auto_fix_symbol = AsyncMock()
                    
                    # Run Service
                    service = DailyUpdateService(session)
                    request = CronDailyUpdateRequest(
                        date_from="2024-01-01",
                        date_to="2024-01-05",
                        dry_run=False
                    )
                    
                    await service.execute_daily_update(request)
                    
                    # Verifications
                    
                    # 1. ensure_coverage called
                    assert mock_ensure_cov.called
                    
                    # 2. event_service.record_event called
                    mock_record_event.assert_called_once()
                    call_args = mock_record_event.call_args
                    event_data = call_args[0][1] # second arg is event_data
                    assert isinstance(event_data, CorporateEventCreate)
                    assert event_data.symbol == "TEST_SPLIT"
                    assert event_data.event_type == EventTypeEnum.STOCK_SPLIT
                    
                    # 3. AdjustmentFixer.auto_fix_symbol called
                    mock_fixer_instance.auto_fix_symbol.assert_called_once_with("TEST_SPLIT", 123)
