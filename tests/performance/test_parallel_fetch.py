# tests/performance/test_parallel_fetch.py
import pytest
import asyncio
import time
from app.services.fetcher import fetch_prices_batch, fetch_prices
from app.core.config import settings
from datetime import date, timedelta

@pytest.mark.asyncio
async def test_parallel_vs_sequential():
    symbols = ["AAPL", "MSFT", "GOOGL"]
    end = date.today()
    start = end - timedelta(days=30)
    
    # Sequential
    t0 = time.time()
    for symbol in symbols:
        await asyncio.to_thread(fetch_prices, symbol, start, end, settings=settings)
    seq_time = time.time() - t0
    
    # Parallel
    t0 = time.time()
    await fetch_prices_batch(symbols, start, end, settings)
    par_time = time.time() - t0
    
    print(f"Sequential: {seq_time:.2f}s, Parallel: {par_time:.2f}s")
    assert par_time < seq_time * 0.7  # 並行が30%以上高速