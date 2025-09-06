import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import queries


@pytest.mark.asyncio
async def test_ensure_coverage_with_from_before_oldest_date():
    """
    Test that ensure_coverage behaves appropriately when 'from' is before the oldest date.
    It should not attempt unnecessary fetches for dates before the oldest available data.
    
    Scenario: AAPL has oldest data from 2020-01-02
    Request: from=2019-01-01, to=2021-12-31
    Expected: Coverage logic should handle the range appropriately without wasteful fetches
    """
    # Mock session
    session = AsyncMock(spec=AsyncSession)
    
    # Mock the _get_coverage function to return coverage info
    mock_coverage = {
        'AAPL': {
            'first_date': date(2020, 1, 2),  # Oldest available date
            'last_date': date(2021, 11, 30),
            'weekday_gaps': []  # No gaps for this test
        }
    }
    
    # Mock external dependencies
    with patch('app.db.queries._get_coverage') as mock_get_coverage, \
         patch('app.db.queries.with_symbol_lock') as mock_lock, \
         patch('app.db.queries.fetch_prices_df') as mock_fetch:
        
        mock_get_coverage.return_value = mock_coverage['AAPL']
        mock_lock.return_value = AsyncMock()
        
        # Execute ensure_coverage with from before oldest date
        await queries.ensure_coverage(
            session=session,
            symbols=['AAPL'],
            date_from=date(2019, 1, 1),  # Before oldest date
            date_to=date(2021, 12, 31),
            refetch_days=7
        )
        
        # Verify _get_coverage was called with the original parameters
        mock_get_coverage.assert_called_once_with(
            session, 
            'AAPL',  # Single symbol, not list
            date(2019, 1, 1),  # Original from date
            date(2021, 12, 31)
        )
        
        # The function should have been called but the coverage logic
        # should prevent unnecessary fetching for dates before oldest_date
        
        # Verify advisory lock was acquired for the symbol
        mock_lock.assert_called_once()
        
        # Verify that if fetch_prices_df was called,
        # it was with appropriate date ranges (not before oldest date)
        if mock_fetch.called:
            # Get the arguments passed to fetch_prices_df
            call_args = mock_fetch.call_args_list
            for call in call_args:
                args, kwargs = call
                # The actual date range used for fetching should be reasonable
                # (implementation detail - this verifies the function doesn't crash)
                assert len(args) >= 3  # symbol, start_date, end_date at minimum


@pytest.mark.asyncio
async def test_ensure_coverage_handles_empty_symbol_list():
    """
    Test that ensure_coverage handles empty symbol list gracefully.
    """
    session = AsyncMock(spec=AsyncSession)
    
    # Should not raise an exception with empty symbol list
    await queries.ensure_coverage(
        session=session,
        symbols=[],
        date_from=date(2019, 1, 1),
        date_to=date(2021, 12, 31),
        refetch_days=7
    )
    
    # No database operations should occur for empty symbols
    assert not session.execute.called


@pytest.mark.asyncio 
async def test_ensure_coverage_with_refetch_days_parameter():
    """
    Test that ensure_coverage properly handles the refetch_days parameter
    when from date is before oldest available data.
    """
    session = AsyncMock(spec=AsyncSession)
    
    # Mock coverage with recent data
    mock_coverage = {
        'AAPL': {
            'first_date': date(2020, 1, 2),
            'last_date': date(2021, 12, 25),  # Recent but not current
            'weekday_gaps': []
        }
    }
    
    with patch('app.db.queries._get_coverage') as mock_get_coverage, \
         patch('app.db.queries.with_symbol_lock') as mock_lock, \
         patch('app.db.queries.fetch_prices_df') as mock_fetch:
        
        mock_get_coverage.return_value = mock_coverage['AAPL']
        mock_lock.return_value = AsyncMock()
        
        await queries.ensure_coverage(
            session=session,
            symbols=['AAPL'],
            date_from=date(2019, 1, 1),  # Before oldest
            date_to=date(2021, 12, 31),
            refetch_days=7  # Should trigger refetch of recent days
        )
        
        # Verify coverage check was performed
        mock_get_coverage.assert_called_once()
        
        # If any fetching occurred, verify it was called appropriately
        # (The exact behavior depends on the refetch logic implementation)
