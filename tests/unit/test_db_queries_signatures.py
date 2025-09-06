import inspect
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from app.db import queries


@pytest.mark.asyncio
async def test_get_prices_resolved_signature_and_sql():
    sig = inspect.signature(queries.get_prices_resolved)
    assert list(sig.parameters) == ["session", "symbols", "date_from", "date_to"]

    session = AsyncMock()

    class DummyRes:
        def mappings(self):
            class M:
                def all(self_inner):
                    return []

            return M()

    session.execute.return_value = DummyRes()
    await queries.get_prices_resolved(session, ["AAA"], date(2024, 1, 1), date(2024, 1, 2))
    executed_sql = session.execute.call_args[0][0].text
    assert "get_prices_resolved" in executed_sql


@pytest.mark.asyncio
async def test_list_symbols_signature_and_sql():
    sig = inspect.signature(queries.list_symbols)
    assert list(sig.parameters) == ["session", "active"]

    session = AsyncMock()
    session.execute.return_value.fetchall.return_value = []
    await queries.list_symbols(session, active=True)
    executed_sql = session.execute.call_args[0][0].text
    assert "FROM symbols" in executed_sql


@pytest.mark.asyncio
async def test_get_prices_resolved_fallback_behavior():
    """
    Test that get_prices_resolved SQL function handles requests where 'from' 
    is before the oldest available data appropriately.
    
    This test verifies the SQL function level behavior for oldest data fallback.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock SQL result for fallback scenario
    # Simulating that SQL function returns only available data (from oldest date onwards)
    mock_sql_result_fallback = [
        {
            'symbol': 'AAPL',
            'date': date(2020, 1, 2),  # Oldest available date
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
            'date': date(2020, 1, 3),
            'open': 103.0,
            'high': 107.0,
            'low': 102.0, 
            'close': 106.0,
            'volume': 1100000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'
        }
    ]
    
    # Mock the database response
    class MockMappings:
        def __init__(self, data):
            self.data = data
        def all(self):
            return self.data
    
    class MockResult:
        def __init__(self, data):
            self.data = data
        def mappings(self):
            return MockMappings(self.data)
    
    async def mock_execute(sql, params):
        # Verify SQL function is called with correct parameters
        assert "get_prices_resolved" in sql.text
        assert params['symbol'] == 'AAPL'
        assert params['date_from'] == date(2019, 1, 1)  # Original from date (before oldest)
        assert params['date_to'] == date(2021, 12, 31)
        
        # Return data from oldest date onwards (natural SQL function behavior)
        return MockResult(mock_sql_result_fallback)
    
    session.execute = mock_execute
    
    # Call get_prices_resolved with from date before oldest available date
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],
        date_from=date(2019, 1, 1),  # Before oldest date (2020-01-02)
        date_to=date(2021, 12, 31)
    )
    
    # Verify the result contains only data from oldest date onwards
    assert len(result) == 2
    assert result[0]['date'] == date(2020, 1, 2)  # Oldest available date
    assert result[1]['date'] == date(2020, 1, 3)
    assert result[0]['symbol'] == 'AAPL'
    assert result[1]['symbol'] == 'AAPL'
    
    # Verify all returned dates are >= oldest date
    oldest_date = date(2020, 1, 2)
    for row in result:
        assert row['date'] >= oldest_date


@pytest.mark.asyncio 
async def test_get_prices_resolved_empty_result_before_oldest():
    """
    Test that get_prices_resolved returns empty result when both from and to 
    are before the oldest available data.
    """
    # Mock session
    session = AsyncMock()
    
    async def mock_execute(sql, params):
        # Verify SQL function is called with correct parameters
        assert "get_prices_resolved" in sql.text  
        assert params['symbol'] == 'AAPL'
        assert params['date_from'] == date(2018, 1, 1)  # Before oldest
        assert params['date_to'] == date(2019, 12, 31)   # Also before oldest
        
        # Return empty result (no data in this range)
        class MockMappings:
            def all(self):
                return []
        
        class MockResult:
            def mappings(self):
                return MockMappings()
                
        return MockResult()
    
    session.execute = mock_execute
    
    # Call get_prices_resolved with both dates before oldest available date
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],
        date_from=date(2018, 1, 1),  # Before oldest date
        date_to=date(2019, 12, 31)   # Also before oldest date
    )
    
    # Verify empty result
    assert len(result) == 0
    assert result == []


@pytest.mark.asyncio
async def test_get_prices_resolved_multiple_symbols_fallback():
    """
    Test get_prices_resolved with multiple symbols having different oldest dates.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock data for two symbols with different start dates
    mock_data_by_symbol = {
        'AAPL': [
            {
                'symbol': 'AAPL',
                'date': date(2020, 1, 2),  # AAPL's oldest
                'open': 100.0, 'high': 105.0, 'low': 99.0, 'close': 103.0,
                'volume': 1000000, 'source': 'yfinance', 
                'last_updated': datetime.now(), 'source_symbol': 'AAPL'
            }
        ],
        'MSFT': [
            {
                'symbol': 'MSFT', 
                'date': date(2020, 6, 1),  # MSFT's oldest (later than AAPL)
                'open': 200.0, 'high': 205.0, 'low': 199.0, 'close': 203.0,
                'volume': 800000, 'source': 'yfinance',
                'last_updated': datetime.now(), 'source_symbol': 'MSFT'
            }
        ]
    }
    
    call_count = 0
    async def mock_execute(sql, params):
        nonlocal call_count
        call_count += 1
        
        assert "get_prices_resolved" in sql.text
        symbol = params['symbol']
        assert symbol in ['AAPL', 'MSFT']
        assert params['date_from'] == date(2019, 1, 1)  # Before both oldest dates
        assert params['date_to'] == date(2021, 12, 31)
        
        class MockMappings:
            def __init__(self, data):
                self.data = data
            def all(self):
                return self.data
        
        class MockResult:
            def __init__(self, data):
                self.data = data
            def mappings(self):
                return MockMappings(self.data)
        
        return MockResult(mock_data_by_symbol[symbol])
    
    session.execute = mock_execute
    
    # Call get_prices_resolved with multiple symbols
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL', 'MSFT'],
        date_from=date(2019, 1, 1),  # Before both oldest dates
        date_to=date(2021, 12, 31)
    )
    
    # Verify SQL function was called for each symbol
    assert call_count == 2
    
    # Verify result contains data from each symbol's oldest date onwards  
    assert len(result) == 2
    
    # Results should be sorted by (date, symbol)
    assert result[0]['date'] == date(2020, 1, 2)  # AAPL first (earlier date)
    assert result[0]['symbol'] == 'AAPL'
    assert result[1]['date'] == date(2020, 6, 1)  # MSFT second (later date)
    assert result[1]['symbol'] == 'MSFT'
