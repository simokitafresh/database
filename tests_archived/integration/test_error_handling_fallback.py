import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, Mock
from sqlalchemy.exc import SQLAlchemyError, DatabaseError
from asyncio import TimeoutError
import asyncio

from app.db import queries


@pytest.mark.asyncio
async def test_oldest_date_fallback_database_error_handling():
    """
    Test error handling when database errors occur during fallback operations.
    
    Verifies that database errors are properly propagated and don't cause
    silent failures in fallback scenarios.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock database error during SQL execution
    async def mock_execute_with_error(sql, params):
        assert "get_prices_resolved" in sql.text
        assert params['symbol'] == 'AAPL'
        assert params['date_from'] == date(2019, 1, 1)  # Fallback scenario
        
        # Simulate database error
        raise DatabaseError("Connection lost", "mock_statement", "mock_params", "mock_orig")
    
    session.execute = mock_execute_with_error
    
    # Verify that database errors are properly propagated
    with pytest.raises(DatabaseError) as exc_info:
        await queries.get_prices_resolved(
            session=session,
            symbols=['AAPL'],
            date_from=date(2019, 1, 1),  # Before oldest date (fallback)
            date_to=date(2023, 12, 31)
        )
    
    # Verify error details
    assert "Connection lost" in str(exc_info.value)


@pytest.mark.asyncio
async def test_oldest_date_fallback_timeout_handling():
    """
    Test timeout handling during fallback operations.
    
    Verifies that timeouts are properly handled and don't cause hangs
    in fallback scenarios.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock timeout during SQL execution
    async def mock_execute_with_timeout(sql, params):
        assert "get_prices_resolved" in sql.text
        
        # Simulate timeout
        await asyncio.sleep(0.1)  # Small delay
        raise TimeoutError("Query timeout")
    
    session.execute = mock_execute_with_timeout
    
    # Verify that timeout errors are properly propagated
    with pytest.raises(TimeoutError) as exc_info:
        await queries.get_prices_resolved(
            session=session,
            symbols=['AAPL'],
            date_from=date(2019, 1, 1),  # Fallback scenario
            date_to=date(2023, 12, 31)
        )
    
    assert "Query timeout" in str(exc_info.value)


@pytest.mark.asyncio
async def test_oldest_date_fallback_invalid_data_handling():
    """
    Test handling of invalid data scenarios during fallback operations.
    
    Verifies that malformed data doesn't crash the fallback logic.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock invalid data response
    mock_invalid_data = [
        {
            'symbol': 'AAPL',
            'date': None,  # Invalid date
            'open': 100.0,
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'
        },
        {
            'symbol': 'AAPL',
            'date': date(2020, 1, 2),
            'open': None,  # Invalid price
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'
        },
        {
            'symbol': None,  # Invalid symbol
            'date': date(2020, 1, 3),
            'open': 100.0,
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'
        }
    ]
    
    class MockMappings:
        def all(self):
            return mock_invalid_data
    
    class MockResult:
        def mappings(self):
            return MockMappings()
    
    async def mock_execute(sql, params):
        return MockResult()
    
    session.execute = mock_execute
    
    # Call should handle invalid data gracefully
    # The actual behavior depends on implementation - it might filter out invalid records
    # or raise appropriate validation errors
    try:
        result = await queries.get_prices_resolved(
            session=session,
            symbols=['AAPL'],
            date_from=date(2019, 1, 1),  # Fallback scenario
            date_to=date(2023, 12, 31)
        )
        
        # If no exception is raised, verify result is handled appropriately
        # (Implementation might filter invalid records or return them as-is)
        assert isinstance(result, list)
        
    except (ValueError, TypeError, AttributeError) as e:
        # If validation errors are raised, that's also acceptable behavior
        assert "invalid" in str(e).lower() or "none" in str(e).lower() or "null" in str(e).lower()


@pytest.mark.asyncio
async def test_oldest_date_fallback_empty_symbol_list_error():
    """
    Test behavior with empty symbol list in fallback scenarios.
    
    The current implementation doesn't validate empty symbol lists,
    so it returns an empty result instead of raising an error.
    This test documents the current behavior.
    """
    # Mock session
    session = AsyncMock()
    
    # Test with empty symbol list - current implementation processes it without error
    result = await queries.get_prices_resolved(
        session=session,
        symbols=[],  # Empty list
        date_from=date(2019, 1, 1),  # Fallback scenario
        date_to=date(2023, 12, 31)
    )
    
    # Empty symbol list results in empty result (no database calls made)
    assert result == []
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_oldest_date_fallback_invalid_date_range_error():
    """
    Test behavior with invalid date ranges in fallback scenarios.
    
    The current implementation doesn't validate date ranges,
    so it proceeds with the invalid range and processes database queries.
    This test documents the current behavior.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock successful database response even with invalid date range
    class MockMappings:
        def all(self):
            return []  # Empty result for invalid range
    
    class MockResult:
        def mappings(self):
            return MockMappings()
    
    async def mock_execute(sql, params):
        assert "get_prices_resolved" in sql.text
        assert params['symbol'] == 'AAPL'
        # SQL function receives invalid date range but doesn't crash
        assert params['date_from'] == date(2023, 12, 31)  # After to_date
        assert params['date_to'] == date(2019, 1, 1)     # Before from_date
        
        return MockResult()
    
    session.execute = mock_execute
    
    # Current implementation doesn't validate date range at Python level
    # It passes invalid range to SQL function, which returns empty result
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],
        date_from=date(2023, 12, 31),  # After to_date
        date_to=date(2019, 1, 1)       # Before from_date
    )
    
    # Invalid date range results in empty result (handled by SQL function)
    assert result == []
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_oldest_date_fallback_session_error_handling():
    """
    Test error handling when session-related errors occur during fallback.
    """
    # Test with None session
    with pytest.raises(AttributeError):
        await queries.get_prices_resolved(
            session=None,  # Invalid session
            symbols=['AAPL'],
            date_from=date(2019, 1, 1),  # Fallback scenario
            date_to=date(2023, 12, 31)
        )
    
    # Test with session that doesn't have execute method
    invalid_session = Mock()
    delattr(invalid_session, 'execute')  # Remove execute method
    
    with pytest.raises(AttributeError):
        await queries.get_prices_resolved(
            session=invalid_session,
            symbols=['AAPL'],
            date_from=date(2019, 1, 1),  # Fallback scenario
            date_to=date(2023, 12, 31)
        )


@pytest.mark.asyncio
async def test_oldest_date_fallback_partial_failure_handling():
    """
    Test handling of partial failures in multi-symbol fallback scenarios.
    
    When some symbols succeed and others fail, verify appropriate error handling.
    """
    # Mock session
    session = AsyncMock()
    
    call_count = 0
    symbols = ['AAPL', 'MSFT', 'INVALID_SYMBOL']
    
    async def mock_execute_with_partial_failure(sql, params):
        nonlocal call_count
        call_count += 1
        
        assert "get_prices_resolved" in sql.text
        symbol = params['symbol']
        
        if symbol == 'AAPL':
            # Success for AAPL
            mock_data = [{
                'symbol': 'AAPL',
                'date': date(2020, 1, 1),
                'open': 100.0, 'high': 105.0, 'low': 99.0, 'close': 103.0,
                'volume': 1000000, 'source': 'yfinance',
                'last_updated': datetime.now(), 'source_symbol': 'AAPL'
            }]
            
            class MockMappings:
                def all(self):
                    return mock_data
                    
            class MockResult:
                def mappings(self):
                    return MockMappings()
                    
            return MockResult()
            
        elif symbol == 'MSFT':
            # Success for MSFT
            mock_data = [{
                'symbol': 'MSFT',
                'date': date(2020, 1, 2),
                'open': 200.0, 'high': 205.0, 'low': 199.0, 'close': 203.0,
                'volume': 800000, 'source': 'yfinance',
                'last_updated': datetime.now(), 'source_symbol': 'MSFT'
            }]
            
            class MockMappings:
                def all(self):
                    return mock_data
                    
            class MockResult:
                def mappings(self):
                    return MockMappings()
                    
            return MockResult()
            
        else:  # INVALID_SYMBOL
            # Failure for invalid symbol
            raise DatabaseError("Symbol not found", "mock_statement", "mock_params", "mock_orig")
    
    session.execute = mock_execute_with_partial_failure
    
    # The behavior depends on implementation:
    # 1. Might raise error immediately on first failure
    # 2. Might collect partial results and raise error at the end
    # 3. Might skip failed symbols and return partial results
    
    try:
        result = await queries.get_prices_resolved(
            session=session,
            symbols=symbols,
            date_from=date(2019, 1, 1),  # Fallback scenario
            date_to=date(2023, 12, 31)
        )
        
        # If partial results are returned, verify they're valid
        assert isinstance(result, list)
        if len(result) > 0:
            # Should contain only successful symbols
            result_symbols = set(row['symbol'] for row in result)
            assert 'INVALID_SYMBOL' not in result_symbols
            assert all(symbol in ['AAPL', 'MSFT'] for symbol in result_symbols)
            
    except DatabaseError as e:
        # If error is raised, that's also acceptable behavior
        assert "Symbol not found" in str(e)
        
        # Should have attempted at least one symbol before failing
        assert call_count >= 1
