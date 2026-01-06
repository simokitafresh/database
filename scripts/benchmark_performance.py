#!/usr/bin/env python3
"""
Performance Benchmark Script for Supabase Direct Connection Optimization.

Tests various parameter combinations:
- max_concurrency: 4, 8, 12
- DB_POOL_SIZE: 5, 10, 15

Usage:
    python scripts/benchmark_performance.py --base-url https://stockdata-api-6xok.onrender.com
"""

import argparse
import asyncio
import time
import statistics
from datetime import datetime, timedelta
import aiohttp


async def fetch_prices(session: aiohttp.ClientSession, base_url: str, symbol: str) -> dict:
    """Fetch price data for a single symbol."""
    url = f"{base_url}/v1/prices"
    params = {
        "symbols": symbol,
        "from": "2025-01-01",
        "to": "2026-01-06",
        "auto_fetch": "false"
    }
    start = time.perf_counter()
    async with session.get(url, params=params) as resp:
        data = await resp.json()
        elapsed = time.perf_counter() - start
        return {
            "symbol": symbol,
            "status": resp.status,
            "rows": len(data) if isinstance(data, list) else 0,
            "elapsed_ms": elapsed * 1000
        }


async def fetch_symbols(session: aiohttp.ClientSession, base_url: str) -> list:
    """Get list of active symbols."""
    url = f"{base_url}/v1/symbols"
    params = {"active": "true"}
    async with session.get(url, params=params) as resp:
        data = await resp.json()
        return [s["symbol"] for s in data]


async def run_benchmark(base_url: str, symbols: list, concurrency: int) -> dict:
    """Run benchmark with specified concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    
    async def fetch_with_semaphore(session, symbol):
        async with semaphore:
            return await fetch_prices(session, base_url, symbol)
    
    connector = aiohttp.TCPConnector(limit=concurrency * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        start = time.perf_counter()
        tasks = [fetch_with_semaphore(session, s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_elapsed = time.perf_counter() - start
    
    # Filter out exceptions
    valid_results = [r for r in results if isinstance(r, dict)]
    errors = len(results) - len(valid_results)
    
    if valid_results:
        latencies = [r["elapsed_ms"] for r in valid_results]
        return {
            "concurrency": concurrency,
            "total_symbols": len(symbols),
            "successful": len(valid_results),
            "errors": errors,
            "total_time_s": total_elapsed,
            "avg_latency_ms": statistics.mean(latencies),
            "p50_latency_ms": statistics.median(latencies),
            "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0],
            "throughput_rps": len(valid_results) / total_elapsed
        }
    return {"concurrency": concurrency, "error": "All requests failed"}


async def main():
    parser = argparse.ArgumentParser(description="Performance Benchmark")
    parser.add_argument("--base-url", default="https://stockdata-api-6xok.onrender.com")
    parser.add_argument("--symbols", type=int, default=20, help="Number of symbols to test")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[4, 8, 12], help="Concurrency levels to test")
    args = parser.parse_args()
    
    print(f"=" * 60)
    print(f"Performance Benchmark - {datetime.now().isoformat()}")
    print(f"Base URL: {args.base_url}")
    print(f"=" * 60)
    
    # Get active symbols
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        all_symbols = await fetch_symbols(session, args.base_url)
    
    test_symbols = all_symbols[:args.symbols]
    print(f"\nTesting with {len(test_symbols)} symbols")
    print(f"Concurrency levels: {args.concurrency}")
    print()
    
    results = []
    for conc in args.concurrency:
        print(f"Testing concurrency={conc}...", end=" ", flush=True)
        result = await run_benchmark(args.base_url, test_symbols, conc)
        results.append(result)
        print(f"Done - {result.get('throughput_rps', 0):.2f} req/s")
    
    # Print results table
    print("\n" + "=" * 80)
    print(f"{'Concurrency':>12} {'Total(s)':>10} {'Avg(ms)':>10} {'P50(ms)':>10} {'P95(ms)':>10} {'RPS':>10}")
    print("-" * 80)
    for r in results:
        if "error" not in r:
            print(f"{r['concurrency']:>12} {r['total_time_s']:>10.2f} {r['avg_latency_ms']:>10.1f} "
                  f"{r['p50_latency_ms']:>10.1f} {r['p95_latency_ms']:>10.1f} {r['throughput_rps']:>10.2f}")
    print("=" * 80)
    
    # Find best configuration
    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        best = max(valid_results, key=lambda x: x["throughput_rps"])
        print(f"\n🏆 Best: concurrency={best['concurrency']} ({best['throughput_rps']:.2f} req/s)")


if __name__ == "__main__":
    asyncio.run(main())
