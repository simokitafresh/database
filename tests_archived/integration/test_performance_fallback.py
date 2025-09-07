import pytest
import time
from datetime import date, datetime
from unittest.mock import AsyncMock

from app.db import queries


@pytest.mark.asyncio
async def test_oldest_date_fallback_performance_single_symbol():
    """
    Test performance characteristics of oldest date fallback for single symbol queries.
    
    Verifies that fallback behavior doesn't significantly degrade performance
    compared to normal date range queries.
    """
    # Mock session
    session = AsyncMock()
    
    # Mock large dataset (1000 records)
    mock_large_dataset = []
    base_date = date(2020, 1, 1)
    for i in range(1000):
        days_offset = i
        current_date = date(base_date.year, base_date.month, base_date.day)
        # Calculate date with day offset
        import calendar
        year, month, day = base_date.year, base_date.month, base_date.day + days_offset
        
        # Handle month/year overflow
        while day > 28:  # Conservative approach
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            day -= 28
            
        if month > 12:
            year += month // 12
            month = month % 12
            if month == 0:
                month = 12
                year -= 1
                
        mock_large_dataset.append({
            'symbol': 'AAPL',
            'date': date(year, month, day),
            'open': 100.0 + (i * 0.1),
            'high': 105.0 + (i * 0.1),
            'low': 99.0 + (i * 0.1),  
            'close': 103.0 + (i * 0.1),
            'volume': 1000000 + (i * 1000),
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'
        })
    
    # Mock database response
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
    
    # Performance test with fallback scenario (from date before oldest)
    call_count = 0
    async def mock_execute(sql, params):
        nonlocal call_count
        call_count += 1
        
        assert "get_prices_resolved" in sql.text
        assert params['symbol'] == 'AAPL'
        assert params['date_from'] == date(2019, 1, 1)  # Before oldest (fallback scenario)
        assert params['date_to'] == date(2023, 12, 31)
        
        # Simulate database processing time (small delay)
        # In real scenario, SQL function handles large dataset efficiently
        await AsyncMock(return_value=None)()
        
        return MockResult(mock_large_dataset)
    
    session.execute = mock_execute
    
    # Measure execution time
    start_time = time.time()
    
    result = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],
        date_from=date(2019, 1, 1),  # Fallback scenario: before oldest
        date_to=date(2023, 12, 31)
    )
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Performance assertions
    assert execution_time < 1.0  # Should complete within 1 second for mocked data
    assert call_count == 1  # Only one database call
    
    # Result validation
    assert len(result) == 1000
    assert result[0]['symbol'] == 'AAPL'
    
    # Verify result is properly sorted
    for i in range(len(result) - 1):
        assert result[i]['date'] <= result[i + 1]['date']
    
    print(f"Single symbol fallback performance: {execution_time:.4f}s for {len(result)} records")


@pytest.mark.asyncio
async def test_oldest_date_fallback_performance_multiple_symbols():
    """
    Test performance characteristics of oldest date fallback for multiple symbol queries.
    
    Verifies that performance scales reasonably with number of symbols.
    """
    # Mock session
    session = AsyncMock()
    
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']  # 5 symbols
    records_per_symbol = 200  # 200 records each = 1000 total
    
    # Generate mock data for each symbol
    mock_data_by_symbol = {}
    for symbol in symbols:
        symbol_data = []
        for i in range(records_per_symbol):
            # Simple date calculation
            year = 2020 + (i // 365)
            month = 1 + ((i % 365) // 30)
            day = 1 + (i % 30)
            
            # Clamp month and day
            month = min(month, 12)
            day = min(day, 28)  # Conservative day limit
            
            symbol_data.append({
                'symbol': symbol,
                'date': date(year, month, day),
                'open': 100.0 + (i * 0.1),
                'high': 105.0 + (i * 0.1),
                'low': 99.0 + (i * 0.1),
                'close': 103.0 + (i * 0.1),
                'volume': 1000000 + (i * 1000),
                'source': 'yfinance',
                'last_updated': datetime.now(),
                'source_symbol': symbol
            })
        mock_data_by_symbol[symbol] = symbol_data
    
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
    
    # Track database calls
    call_count = 0
    async def mock_execute(sql, params):
        nonlocal call_count
        call_count += 1
        
        assert "get_prices_resolved" in sql.text
        symbol = params['symbol']
        assert symbol in symbols
        assert params['date_from'] == date(2019, 1, 1)  # Before all oldest dates
        assert params['date_to'] == date(2023, 12, 31)
        
        # Simulate database processing time
        await AsyncMock(return_value=None)()
        
        return MockResult(mock_data_by_symbol[symbol])
    
    session.execute = mock_execute
    
    # Measure execution time for multiple symbols
    start_time = time.time()
    
    result = await queries.get_prices_resolved(
        session=session,
        symbols=symbols,
        date_from=date(2019, 1, 1),  # Fallback scenario: before all oldest dates
        date_to=date(2023, 12, 31)
    )
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Performance assertions
    assert execution_time < 2.0  # Should complete within 2 seconds for 5 symbols
    assert call_count == len(symbols)  # One call per symbol
    
    # Result validation
    total_expected_records = len(symbols) * records_per_symbol
    assert len(result) == total_expected_records
    
    # Verify each symbol is represented
    symbols_in_result = set(row['symbol'] for row in result)
    assert symbols_in_result == set(symbols)
    
    # Verify proper sorting (by date, then symbol)
    for i in range(len(result) - 1):
        curr_date = result[i]['date']
        next_date = result[i + 1]['date']
        if curr_date == next_date:
            # Same date: should be sorted by symbol
            assert result[i]['symbol'] <= result[i + 1]['symbol']
        else:
            # Different dates: should be chronologically ordered
            assert curr_date < next_date
    
    print(f"Multi-symbol fallback performance: {execution_time:.4f}s for {len(symbols)} symbols, {len(result)} total records")


@pytest.mark.asyncio
async def test_oldest_date_fallback_performance_comparison():
    """
    Compare performance between normal date range and fallback scenarios.
    
    Verifies that fallback logic doesn't add significant overhead.
    """
    # Mock session
    session = AsyncMock()
    
    # Smaller dataset for comparison test
    mock_dataset = []
    for i in range(100):
        mock_dataset.append({
            'symbol': 'AAPL',
            'date': date(2020, 1, 1 + i % 28),  # Cycle through January
            'open': 100.0 + i,
            'high': 105.0 + i,
            'low': 99.0 + i,
            'close': 103.0 + i,
            'volume': 1000000 + (i * 1000),
            'source': 'yfinance',
            'last_updated': datetime.now(),
            'source_symbol': 'AAPL'
        })
    
    class MockMappings:
        def all(self):
            return mock_dataset
    
    class MockResult:
        def mappings(self):
            return MockMappings()
    
    async def mock_execute(sql, params):
        assert "get_prices_resolved" in sql.text
        await AsyncMock(return_value=None)()
        return MockResult()
    
    session.execute = mock_execute
    
    # Test 1: Normal date range (within available data)
    start_time = time.time()
    
    result_normal = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],
        date_from=date(2020, 1, 15),  # Within available range
        date_to=date(2020, 1, 28)
    )
    
    normal_time = time.time() - start_time
    
    # Test 2: Fallback scenario (before oldest date)
    start_time = time.time()
    
    result_fallback = await queries.get_prices_resolved(
        session=session,
        symbols=['AAPL'],
        date_from=date(2019, 1, 1),  # Before oldest (fallback)
        date_to=date(2020, 1, 28)
    )
    
    fallback_time = time.time() - start_time
    
    # Performance comparison
    performance_ratio = fallback_time / normal_time if normal_time > 0 else 1.0
    
    # Both should return same dataset (mocked)
    assert len(result_normal) == len(result_fallback) == 100
    
    # Fallback shouldn't be more than 50% slower than normal case
    assert performance_ratio <= 1.5, f"Fallback is {performance_ratio:.2f}x slower than normal"
    
    # Both should complete quickly (mocked scenario)
    assert normal_time < 0.5
    assert fallback_time < 0.5
    
    print(f"Performance comparison:")
    print(f"  Normal query: {normal_time:.4f}s")
    print(f"  Fallback query: {fallback_time:.4f}s") 
    print(f"  Ratio: {performance_ratio:.2f}x")
