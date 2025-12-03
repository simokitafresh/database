# Speedup and Stability Improvements

This document outlines ideas for improving the performance (speedup) and stability of the Stock Data Platform.

## 1. Database Connection Management

### As-Is
- **Repeated Engine Creation**: The `fetch_worker.py` creates a *new* SQLAlchemy engine and session factory for *every* job, and worse, for *every single symbol* fetch within `fetch_symbol_data`.
  - `process_fetch_job` calls `create_engine_and_sessionmaker`.
  - `fetch_symbol_data` calls `create_engine_and_sessionmaker` again with `pool_size=1`.
- **Connection Overhead**: Creating an engine involves setting up connection pools (even if `NullPool`) and overhead. Doing this per symbol is extremely inefficient and stresses the database connection limit.
- **Pool Settings**: Explicitly setting `pool_size=1` and `max_overflow=0` for single fetches effectively disables pooling benefits.

### To-Be
- **Singleton Engine**: Use a global/singleton `AsyncEngine` instance initialized at application startup (in `app.main` lifespan).
- **Dependency Injection**: Pass the session factory or engine to services instead of creating them on the fly.
- **Connection Pooling**: Allow the global pool to manage connections. Remove per-symbol engine creation.
- **Benefit**: Drastically reduces connection overhead and latency per symbol.

## 2. Upsert Performance

### As-Is
- **Method**: Uses `INSERT ... ON CONFLICT DO UPDATE` via SQLAlchemy's `execute` with a list of dictionaries (`executemany` style).
- **Batch Size**: Fixed at 500 rows per batch.
- **Logic**: Iterates through rows, normalizes them, and executes SQL.

### To-Be
- **Increased Batch Size**: Increase batch size to 2,000-5,000 rows. PostgreSQL can handle larger batches efficiently.
- **COPY Strategy (for Bulk)**: For initial data loads (where conflict is unlikely or we can ignore duplicates), use PostgreSQL `COPY` command (via `asyncpg.copy_records_to_table`).
  - *Hybrid Approach*: Use `COPY` into a temporary table, then `INSERT INTO target SELECT * FROM temp ON CONFLICT ...`. This is significantly faster for large datasets (>10k rows).
- **Benefit**: Reduces network round-trips and database CPU usage.

## 3. Concurrency & Worker Efficiency

### As-Is
- **Concurrency Control**: Uses `asyncio.Semaphore` at multiple levels (`fetch_worker`, `fetcher`).
- **Blocking I/O**: `yfinance` is synchronous. It runs in a thread pool (`run_in_threadpool`), which is good, but context switching has overhead.
- **Resource Usage**: Each worker process manages its own concurrency.

### To-Be
- **Unified Concurrency**: Centralize concurrency control. If using `fetch_worker`, let it manage the semaphore.
- **Async HTTP (Long-term)**: Consider replacing `yfinance` with a direct async HTTP client (e.g., `aiohttp`) for raw data fetching if `yfinance` becomes a bottleneck, though this requires re-implementing parsing logic.
- **Process Pool**: For heavy data parsing (Pandas operations), consider `ProcessPoolExecutor` instead of `ThreadPoolExecutor` to avoid GIL issues, though `run_in_threadpool` uses threads.
- **Benefit**: Better CPU utilization and throughput.

## 4. Distributed Stability

### As-Is
- **Rate Limiting**: In-memory `RateLimiter` using `asyncio.Lock` and `time.sleep`.
- **Scope**: Rate limiting is local to the process. Multiple worker replicas (e.g., on Render) will not share the limit, potentially leading to 429s from Yahoo Finance.

### To-Be
- **Distributed Rate Limiting**: Implement Redis-based rate limiting (Token Bucket or Leaky Bucket).
  - Use `redis-py` (already in requirements) to store token counts.
- **Circuit Breaker**: Implement a circuit breaker pattern. If YF returns 5xx or 429s repeatedly, stop fetching for a cooldown period to prevent cascading failures.
- **Benefit**: Prevents IP bans and ensures stability across multiple instances.

## 5. Caching Strategy

### As-Is
- **Cache**: Redis caching is mentioned in docs but `fetcher.py` always fetches from YF (unless `auto_fetch=false` which reads DB).
- **Hit Rate**: No caching of YF responses for short durations.

### To-Be
- **Short-term Cache**: Cache YF responses in Redis for a short duration (e.g., 1-5 minutes) to prevent redundant fetches for the same symbol in quick succession (e.g., multiple users requesting same data).
- **Tiered Storage**: Use local memory cache (LRU) for very hot data (e.g., market status, active symbols).

## 6. Code Structure & Maintenance

### As-Is
- **Coupling**: `fetch_worker` imports directly from `app.db.engine`.
- **Complexity**: `fetcher.py` mixes fetching, cleaning, and error handling.

### To-Be
- **Service Layer**: clear separation. `FetchService` should handle the logic of "get data, maybe from cache, maybe from API".
- **Refactoring**: Move `create_engine_and_sessionmaker` usage to `app.core.db` or similar singleton pattern.

---

## Summary of Priorities

1.  **High**: Fix `fetch_worker.py` to reuse the database engine. This is a critical performance fix.
2.  **High**: Implement Redis-based distributed rate limiting.
3.  **Medium**: Increase upsert batch size and explore `COPY` for bulk loads.
4.  **Low**: Async HTTP replacement for `yfinance`.
