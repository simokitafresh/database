import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import queries
from app.db.models import Symbol, Price


@pytest.mark.asyncio
async def test_fallback_before_oldest_date_natural_trim():
    """
    Test that when 'from' is before the oldest available date,
    the response naturally trims to include only data from the oldest date onwards.
    
    Scenario: AAPL has oldest data from 2020-01-02
    Request: from=2019-01-01, to=2021-12-31  
    Expected: Response contains only data from 2020-01-02 onwards
    """
    # Mock session
    session = AsyncMock(spec=AsyncSession)
    
    # Mock data: AAPL with data starting from 2020-01-02
    mock_prices = [
        {
            'symbol': 'AAPL',
            'date': date(2020, 1, 2),
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
        return MockResult(mock_prices)
    
    session.execute = mock_execute
    
    # Execute the query with from date before oldest available date
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],
        date_from=date(2019, 1, 1),  # Before oldest date
        date_to=date(2021, 12, 31)
    )
    
    # Verify the result contains data from oldest date onwards
    assert len(result) == 2
    assert result[0]['date'] == date(2020, 1, 2)  # Oldest available date
    assert result[1]['date'] == date(2020, 1, 3)
    
    # Verify all returned dates are >= oldest date (2020-01-02)
    oldest_date = date(2020, 1, 2)
    for price_row in result:
        assert price_row['date'] >= oldest_date
        
    # Verify symbol consistency
    for price_row in result:
        assert price_row['symbol'] == 'AAPL'


@pytest.mark.asyncio
async def test_empty_array_when_both_dates_before_oldest():
    """
    Test that when both 'from' and 'to' are before the oldest available date,
    an empty array is returned.
    
    Scenario: AAPL has oldest data from 2020-01-02
    Request: from=2018-01-01, to=2019-12-31 (both before oldest)
    Expected: Empty array response
    """
    # Mock session
    session = AsyncMock(spec=AsyncSession)
    
    # Mock empty result (no data in the requested range)
    class MockMappings:
        def all(self):
            return []
    
    class MockResult:
        def mappings(self):
            return MockMappings()
    
    async def mock_execute(sql, params):
        return MockResult()
    
    session.execute = mock_execute
    
    # Execute the query with both dates before oldest available date
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
async def test_multiple_symbols_different_start_dates_sorted():
    """
    Test that with multiple symbols having different oldest dates,
    the response is properly sorted by (date, symbol).
    
    Scenario: 
    - AAPL has oldest data from 2020-01-02
    - MSFT has oldest data from 2020-06-01  
    Request: from=2019-01-01, to=2021-12-31
    Expected: Response sorted by (date, symbol) containing data from each symbol's oldest date onwards
    """
    # Mock session
    session = AsyncMock(spec=AsyncSession)
    
    # Mock data: Multiple symbols with different start dates, pre-sorted
    mock_prices = [
        {
            'symbol': 'AAPL',
            'date': date(2020, 1, 2),
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
            'date': date(2020, 6, 1),
            'open': 110.0,
            'high': 115.0,
            'low': 109.0,
            'close': 113.0,
            'volume': 1200000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'
        },
        {
            'symbol': 'MSFT',
            'date': date(2020, 6, 1),  # MSFT's oldest date
            'open': 200.0,
            'high': 205.0,
            'low': 199.0,
            'close': 203.0,
            'volume': 800000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'MSFT'
        },
        {
            'symbol': 'AAPL',
            'date': date(2020, 6, 2),
            'open': 113.0,
            'high': 117.0,
            'low': 112.0,
            'close': 116.0,
            'volume': 1300000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'
        },
        {
            'symbol': 'MSFT',
            'date': date(2020, 6, 2),
            'open': 203.0,
            'high': 207.0,
            'low': 202.0,
            'close': 206.0,
            'volume': 900000,
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'MSFT'
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
        # Return different data based on the symbol being queried
        symbol = params.get('symbol', '')
        if symbol == 'AAPL':
            aapl_data = [row for row in mock_prices if row['symbol'] == 'AAPL']
            return MockResult(aapl_data)
        elif symbol == 'MSFT':
            msft_data = [row for row in mock_prices if row['symbol'] == 'MSFT']
            return MockResult(msft_data)
        return MockResult([])
    
    session.execute = mock_execute
    
    # Execute the query with multiple symbols
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL', 'MSFT'],
        date_from=date(2019, 1, 1),  # Before both symbols' oldest dates
        date_to=date(2021, 12, 31)
    )
    
    # Verify the result contains expected number of rows
    assert len(result) == 5
    
    # Verify sorting by (date, symbol)
    for i in range(len(result) - 1):
        current = result[i]
        next_item = result[i + 1]
        
        # Either date is earlier, or same date with symbol alphabetically before
        assert (current['date'] < next_item['date'] or 
                (current['date'] == next_item['date'] and 
                 current['symbol'] <= next_item['symbol']))
    
    # Verify AAPL data starts from its oldest date (2020-01-02)
    aapl_rows = [row for row in result if row['symbol'] == 'AAPL']
    assert len(aapl_rows) == 3
    assert min(row['date'] for row in aapl_rows) == date(2020, 1, 2)
    
    # Verify MSFT data starts from its oldest date (2020-06-01)  
    msft_rows = [row for row in result if row['symbol'] == 'MSFT']
    assert len(msft_rows) == 2
    assert min(row['date'] for row in msft_rows) == date(2020, 6, 1)
