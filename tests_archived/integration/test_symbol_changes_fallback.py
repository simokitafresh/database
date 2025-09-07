import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock

from app.db import queries


@pytest.mark.asyncio
async def test_symbol_changes_fallback_with_old_new_transition():
    """
    Test fallback behavior when requesting data across a symbol change boundary
    where the request 'from' date is before the oldest available data for both symbols.
    
    Scenario:
    - Old symbol (AAPL_OLD) has data from 2020-01-02 to 2020-05-31
    - New symbol (AAPL) has data from 2020-06-01 onwards  
    - Symbol change date: 2020-06-01
    - Request: from=2019-01-01 (before both oldest dates), to=2021-12-31
    
    Expected: Data from oldest available dates of each symbol, properly integrated.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock integrated data that SQL function would return
    # The get_prices_resolved SQL function handles symbol change integration internally
    mock_integrated_data = [
        {
            'symbol': 'AAPL',  # New symbol name in response
            'date': date(2020, 1, 2),  # From old symbol period, oldest available
            'open': 100.0,
            'high': 105.0,
            'low': 99.0,
            'close': 103.0,
            'volume': 1000000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL_OLD'  # Indicates data came from old symbol
        },
        {
            'symbol': 'AAPL',
            'date': date(2020, 5, 31),  # Last day of old symbol
            'open': 120.0,
            'high': 125.0,
            'low': 119.0,
            'close': 123.0,
            'volume': 1200000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL_OLD'
        },
        {
            'symbol': 'AAPL', 
            'date': date(2020, 6, 1),  # First day of new symbol (change date)
            'open': 123.0,
            'high': 128.0,
            'low': 122.0,
            'close': 126.0,
            'volume': 1300000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'  # Data from new symbol
        },
        {
            'symbol': 'AAPL',
            'date': date(2020, 6, 2),
            'open': 126.0,
            'high': 131.0,
            'low': 125.0,
            'close': 129.0,
            'volume': 1400000,
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
        # Verify SQL function is called
        assert "get_prices_resolved" in sql.text
        assert params['symbol'] == 'AAPL'  # Request for new symbol
        assert params['date_from'] == date(2019, 1, 1)  # Before oldest of both symbols
        assert params['date_to'] == date(2021, 12, 31)
        
        # SQL function returns integrated data from both old and new symbols
        return MockResult(mock_integrated_data)
    
    session.execute = mock_execute
    
    # Call get_prices_resolved for the new symbol with from date before oldest
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],  # Request new symbol
        date_from=date(2019, 1, 1),  # Before oldest data of both symbols
        date_to=date(2021, 12, 31)
    )
    
    # Verify the result contains integrated data from oldest available dates
    assert len(result) == 4
    
    # Verify data sequence and symbol change integration
    assert result[0]['date'] == date(2020, 1, 2)  # Oldest from old symbol
    assert result[0]['symbol'] == 'AAPL'  # Unified symbol name
    assert result[0]['source_symbol'] == 'AAPL_OLD'  # But sourced from old symbol
    
    assert result[1]['date'] == date(2020, 5, 31)  # Last from old symbol
    assert result[1]['source_symbol'] == 'AAPL_OLD'
    
    assert result[2]['date'] == date(2020, 6, 1)  # First from new symbol (change date)
    assert result[2]['source_symbol'] == 'AAPL'  # New symbol as source
    
    assert result[3]['date'] == date(2020, 6, 2)  # Continue from new symbol
    assert result[3]['source_symbol'] == 'AAPL'
    
    # Verify all results use unified symbol name
    for row in result:
        assert row['symbol'] == 'AAPL'
    
    # Verify chronological order
    for i in range(len(result) - 1):
        assert result[i]['date'] <= result[i + 1]['date']


@pytest.mark.asyncio
async def test_symbol_changes_empty_before_all_oldest_dates():
    """
    Test symbol change scenario where request dates are before all available data.
    """
    # Mock session
    session = AsyncMock()
    
    async def mock_execute(sql, params):
        assert "get_prices_resolved" in sql.text
        assert params['symbol'] == 'AAPL'
        assert params['date_from'] == date(2018, 1, 1)  # Before all data
        assert params['date_to'] == date(2019, 12, 31)   # Also before all data
        
        # SQL function returns empty result (no data in this range)
        class MockMappings:
            def all(self):
                return []
        
        class MockResult:
            def mappings(self):
                return MockMappings()
                
        return MockResult()
    
    session.execute = mock_execute
    
    # Call get_prices_resolved with dates before all symbol data
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],
        date_from=date(2018, 1, 1),  # Before old symbol's oldest
        date_to=date(2019, 12, 31)   # Also before old symbol's oldest
    )
    
    # Verify empty result
    assert len(result) == 0
    assert result == []


@pytest.mark.asyncio  
async def test_symbol_changes_fallback_multiple_symbols_with_changes():
    """
    Test fallback behavior with multiple symbols, some having symbol changes.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock data for different symbols with varying oldest dates and symbol changes
    mock_data_by_symbol = {
        'AAPL': [  # Has symbol change, integrated data
            {
                'symbol': 'AAPL', 'date': date(2020, 1, 2),  # From old symbol
                'open': 100.0, 'high': 105.0, 'low': 99.0, 'close': 103.0,
                'volume': 1000000, 'source': 'yfinance',
                'last_updated': datetime.now(), 'source_symbol': 'AAPL_OLD'
            },
            {
                'symbol': 'AAPL', 'date': date(2020, 6, 1),  # From new symbol  
                'open': 123.0, 'high': 128.0, 'low': 122.0, 'close': 126.0,
                'volume': 1300000, 'source': 'yfinance',
                'last_updated': datetime.now(), 'source_symbol': 'AAPL'
            }
        ],
        'MSFT': [  # No symbol change, direct data
            {
                'symbol': 'MSFT', 'date': date(2020, 3, 1),  # MSFT's oldest
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
        assert params['date_from'] == date(2019, 1, 1)  # Before all oldest dates
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
        date_from=date(2019, 1, 1),  # Before all oldest dates
        date_to=date(2021, 12, 31)
    )
    
    # Verify SQL function was called for each symbol
    assert call_count == 2
    
    # Verify result contains data from each symbol's oldest available date
    assert len(result) == 3
    
    # Verify sorting by (date, symbol)
    assert result[0]['date'] == date(2020, 1, 2)  # AAPL first (earliest date)
    assert result[0]['symbol'] == 'AAPL'
    
    assert result[1]['date'] == date(2020, 3, 1)  # MSFT next
    assert result[1]['symbol'] == 'MSFT'
    
    assert result[2]['date'] == date(2020, 6, 1)  # AAPL again (later date)
    assert result[2]['symbol'] == 'AAPL'
