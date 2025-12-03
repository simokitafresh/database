# Speedup and Stability Improvements

This document outlines comprehensive strategies for improving the performance (speedup) and stability of the Stock Data Platform, incorporating 2025 best practices for async Python, PostgreSQL, and distributed systems.

---

## 1. Database Connection Management ⭐ **CRITICAL**

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

#### Recommended Pool Configuration (2025)
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    DATABASE_URL,
    pool_size=15,              # Higher than default (5)
    max_overflow=10,           # Allow bursts
    pool_pre_ping=True,        # Verify connection health
    pool_recycle=3600,         # Recycle connections every hour
    echo_pool=True,            # Enable for debugging (disable in prod)
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,    # Avoid detached instance issues
    class_=AsyncSession
)
```

#### Implementation in `app/core/db.py`
```python
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from app.core.config import settings

_engine: AsyncEngine | None = None
_session_factory = None

def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=15,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600
        )
    return _engine

def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False
        )
    return _session_factory
```

- **Benefit**: Drastically reduces connection overhead and latency per symbol (**80-90% improvement expected**).

---

## 2. Upsert Performance

### As-Is
- **Method**: Uses `INSERT ... ON CONFLICT DO UPDATE` via SQLAlchemy's `execute` with a list of dictionaries (`executemany` style).
- **Batch Size**: Fixed at 500 rows per batch.
- **Logic**: Iterates through rows, normalizes them, and executes SQL.

### To-Be

#### Dynamic Batch Sizing
- **Adaptive Batching**: Adjust batch size based on network latency and row size.
  - **Small rows** (<10 columns): 3,000-5,000 rows
  - **Large rows** (>20 columns): 1,000-2,000 rows
  - Monitor execution time and adjust dynamically

#### Modern SQLAlchemy 2.0 Bulk Insert
```python
from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Recommended approach (SQLAlchemy 2.0+)
stmt = insert(PriceModel).values(list_of_dicts)
stmt = stmt.on_conflict_do_update(
    index_elements=['symbol', 'date'],
    set_={
        'open': stmt.excluded.open,
        'high': stmt.excluded.high,
        'low': stmt.excluded.low,
        'close': stmt.excluded.close,
        'volume': stmt.excluded.volume,
        'updated_at': func.now()
    }
)
await session.execute(stmt)
```

#### COPY Strategy for Bulk Loads (>10k rows)
```python
import asyncpg

# Hybrid approach: COPY to temp table, then INSERT with conflict handling
async def bulk_load_with_copy(records: list[dict]):
    async with engine.begin() as conn:
        raw_conn = await conn.get_raw_connection()
        
        # COPY to temporary table
        await raw_conn.driver_connection.copy_records_to_table(
            'temp_prices',
            records=[(r['symbol'], r['date'], r['close'], ...) for r in records],
            columns=['symbol', 'date', 'close', 'open', 'high', 'low', 'volume']
        )
        
        # Bulk upsert from temp table
        await conn.execute(text('''
            INSERT INTO prices 
            SELECT * FROM temp_prices
            ON CONFLICT (symbol, date) DO UPDATE
            SET close = EXCLUDED.close, ...
        '''))
        
        # Clean up
        await conn.execute(text('TRUNCATE temp_prices'))
```

- **Benefit**: **30-50% improvement** for normal batches, **5-10x improvement** for bulk loads.

---

## 3. Concurrency & Worker Efficiency

### As-Is
- **Concurrency Control**: Uses `asyncio.Semaphore` at multiple levels (`fetch_worker`, `fetcher`).
- **Blocking I/O**: `yfinance` is synchronous. It runs in a thread pool (`run_in_threadpool`), which is good, but context switching has overhead.
- **Resource Usage**: Each worker process manages its own concurrency.

### To-Be

#### Unified Concurrency Control
- Centralize concurrency management in a single layer
- Use distributed semaphore (Redis-based) for multi-instance deployments

#### Modern Async Patterns (Python 3.11+)
```python
import asyncio

# Use TaskGroup instead of gather() for better error handling
async def fetch_all_symbols(symbols: list[str]):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch_symbol(s)) for s in symbols]
    # All tasks completed or first exception raised
```

#### Long-term: Replace yfinance
- **Risk**: `yfinance` uses unofficial Yahoo Finance API, prone to breaking changes
- **Alternatives**:
  - Alpha Vantage (free tier: 25 req/day)
  - Polygon.io (better rate limits)
  - Direct async HTTP with custom parsing

- **Benefit**: Better CPU utilization, improved throughput, and long-term stability.

---

## 4. Distributed Stability ⭐ **CRITICAL**

### As-Is
- **Rate Limiting**: In-memory `RateLimiter` using `asyncio.Lock` and `time.sleep`.
- **Scope**: Rate limiting is local to the process. Multiple worker replicas (e.g., on Render) will not share the limit, potentially leading to 429s from Yahoo Finance.

### To-Be

#### Distributed Rate Limiting (Token Bucket Algorithm)
```python
import redis.asyncio as redis
from typing import Optional

class DistributedRateLimiter:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)
    
    async def acquire(self, key: str, rate: int, per: int) -> bool:
        """
        Token bucket implementation using Redis.
        Args:
            key: Rate limit key (e.g., "yfinance:api")
            rate: Number of requests allowed
            per: Time period in seconds
        Returns:
            True if request can proceed, False otherwise
        """
        lua_script = """
        local key = KEYS[1]
        local rate = tonumber(ARGV[1])
        local per = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        
        local tokens = redis.call('GET', key)
        if not tokens then
            redis.call('SET', key, rate - 1, 'EX', per)
            return 1
        end
        
        tokens = tonumber(tokens)
        if tokens > 0 then
            redis.call('DECR', key)
            return 1
        end
        return 0
        """
        
        import time
        result = await self.redis.eval(
            lua_script, 
            1, 
            key, 
            rate, 
            per, 
            int(time.time())
        )
        return bool(result)
```

#### Circuit Breaker Pattern
```python
from aiobreaker import CircuitBreaker

yf_breaker = CircuitBreaker(
    fail_max=5,              # Open after 5 failures
    timeout_duration=60,     # Stay open for 60s
    reset_timeout=30         # Try half-open after 30s
)

@yf_breaker
async def fetch_from_yfinance(symbol: str):
    # Fetch logic here
    pass
```

- **Benefit**: Prevents IP bans, ensures stability across multiple instances (**100% improvement in stability**).

---

## 5. Caching Strategy (Tiered Architecture)

### As-Is
- **Cache**: Redis caching is mentioned in docs but `fetcher.py` always fetches from YF (unless `auto_fetch=false` which reads DB).
- **Hit Rate**: No caching of YF responses for short durations.

### To-Be: Three-Tier Caching

#### L1: Application Memory Cache
```python
from cachetools import TTLCache
import asyncio

# In-memory cache for hot data
memory_cache = TTLCache(maxsize=1000, ttl=60)  # 1 minute TTL

async def get_symbol_price(symbol: str):
    # L1: Check memory
    if symbol in memory_cache:
        return memory_cache[symbol]
    
    # L2: Check Redis
    redis_data = await redis_client.get(f"price:{symbol}")
    if redis_data:
        memory_cache[symbol] = redis_data
        return redis_data
    
    # L3: Fetch from API/DB
    data = await fetch_from_source(symbol)
    
    # Populate caches
    await redis_client.setex(f"price:{symbol}", 300, data)  # 5 min
    memory_cache[symbol] = data
    return data
```

#### L2: Redis Cache (Short-term)
- **TTL**: 1-5 minutes for real-time data
- **Key Pattern**: `yf:{symbol}:{date}:v1` (include version for cache busting)

#### L3: PostgreSQL (Persistent)
- Primary data store

#### Cache Invalidation Strategy
```python
# Version-based invalidation
CACHE_VERSION = "v2"
cache_key = f"yf:{symbol}:{date}:{CACHE_VERSION}"

# Tag-based invalidation
await redis_client.delete(*await redis_client.keys("yf:*:v1"))
```

- **Benefit**: Reduces redundant API calls, improves response time for hot data.

---

## 6. Code Structure & Maintenance

### As-Is
- **Coupling**: `fetch_worker` imports directly from `app.db.engine`.
- **Complexity**: `fetcher.py` mixes fetching, cleaning, and error handling.

### To-Be
- **Service Layer**: Clear separation. `FetchService` should handle the logic of "get data, maybe from cache, maybe from API".
- **Refactoring**: Move `create_engine_and_sessionmaker` usage to `app.core.db` or similar singleton pattern.
- **Dependency Injection**: Use FastAPI's dependency injection for session management

---

## 7. PostgreSQL Configuration Optimization 🆕

### Recommended `postgresql.conf` Settings

```ini
# Memory Settings
shared_buffers = 2GB                    # 25% of total RAM (for 8GB system)
effective_cache_size = 6GB              # 75% of total RAM
work_mem = 64MB                         # Per-operation memory for sorts/joins
maintenance_work_mem = 512MB            # For VACUUM, CREATE INDEX

# Write-Ahead Log
wal_buffers = 16MB                      # For write-heavy workloads
checkpoint_timeout = 15min              # Balance recovery time vs write perf
max_wal_size = 4GB                      # Allow larger checkpoints

# Query Planning
random_page_cost = 1.1                  # For SSD storage
effective_io_concurrency = 200          # For SSD RAID

# Parallelism
max_parallel_workers_per_gather = 4     # CPUs for parallel queries
max_parallel_workers = 8                # Total parallel workers
max_worker_processes = 8                # Background workers

# Connection Management
max_connections = 100                   # Use PgBouncer if >300 needed

# Autovacuum (Critical for performance)
autovacuum_vacuum_scale_factor = 0.05   # Vacuum after 5% of table updated
autovacuum_analyze_scale_factor = 0.02  # Analyze after 2% updated
autovacuum_max_workers = 4              # Concurrent autovacuum processes
```

### Indexing Strategy
```sql
-- Composite indexes for frequent query patterns
CREATE INDEX idx_prices_symbol_date ON prices(symbol, date DESC);
CREATE INDEX idx_prices_date_symbol ON prices(date DESC, symbol);

-- Covering index for common queries
CREATE INDEX idx_prices_cover ON prices(symbol, date) 
    INCLUDE (close, volume);

-- Partial indexes for active data
CREATE INDEX idx_prices_recent ON prices(date, symbol) 
    WHERE date > CURRENT_DATE - INTERVAL '1 year';
```

---

## 8. Observability & Monitoring 🆕

### OpenTelemetry Integration
```python
from opentelemetry import trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# Auto-instrument database queries
SQLAlchemyInstrumentor().instrument(engine=engine)

# Auto-instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Auto-instrument HTTP client calls
HTTPXClientInstrumentor().instrument()
```

### Key Metrics to Monitor
- **Database**:
  - Connection pool utilization (`pg_stat_activity`)
  - Query execution time (`pg_stat_statements`)
  - Cache hit rate (`shared_buffers` hit rate)
  - Dead tuples (`pg_stat_user_tables`)
  
- **Application**:
  - Request latency (p50, p95, p99)
  - Error rate (5xx responses)
  - Rate limiter rejections
  - Cache hit/miss ratios

### Logging Configuration
```python
import logging

# Enable slow query logging
logging.basicConfig(level=logging.INFO)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)

# Log queries >1s
engine = create_async_engine(
    DATABASE_URL,
    echo_pool='debug',
    # Log slow queries
    execution_options={"logging_name": "sqlalchemy.engine"}
)
```

---

## 9. Additional Best Practices 🆕

### Batch Processing with Streaming
For large result sets, use cursor-based streaming:
```python
async with session.execute(
    select(Price).execution_options(stream_results=True)
) as result:
    async for partition in result.partitions(1000):
        await process_batch(partition.all())
```

### Error Handling & Retries
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def fetch_with_retry(symbol: str):
    return await fetch_symbol(symbol)
```

### Health Checks
```python
@app.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    # Check database connectivity
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "ok"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}, 503
```

---

## Summary of Priorities (Updated)

| Priority | Item | Impact | Effort | ROI |
|----------|------|--------|--------|-----|
| 🔴 **Critical** | Fix `fetch_worker.py` to use Singleton Engine | **80-90% speedup** | Low | ⭐⭐⭐⭐⭐ |
| 🔴 **Critical** | Implement Redis-based distributed rate limiting | **100% stability** | Medium | ⭐⭐⭐⭐⭐ |
| 🔴 **Critical** | Optimize connection pool settings | **20-30% speedup** | Low | ⭐⭐⭐⭐ |
| 🟡 **High** | Increase upsert batch size to 2000-5000 | **30-50% speedup** | Low | ⭐⭐⭐⭐ |
| 🟡 **High** | Implement Circuit Breaker pattern | **High availability** | Medium | ⭐⭐⭐⭐ |
| 🟡 **High** | PostgreSQL configuration tuning | **25-40% speedup** | Low | ⭐⭐⭐⭐ |
| 🟢 **Medium** | Implement COPY strategy for bulk loads | **5-10x for bulk** | High | ⭐⭐⭐ |
| 🟢 **Medium** | Three-tier caching (L1/L2/L3) | **Varies by workload** | Medium | ⭐⭐⭐ |
| 🟢 **Medium** | OpenTelemetry observability | **Debugging efficiency** | Medium | ⭐⭐⭐ |
| 🔵 **Low** | Replace `yfinance` with official API | **Long-term stability** | Very High | ⭐⭐ |
| 🔵 **Low** | Streaming result processing | **Memory optimization** | Medium | ⭐⭐ |

---

## Implementation Roadmap

### Phase 1: Quick Wins (Week 1)
1. ✅ Implement Singleton Engine in `app/core/db.py`
2. ✅ Update `fetch_worker.py` to use global engine
3. ✅ Increase upsert batch size to 3000
4. ✅ Optimize connection pool settings

**Expected Impact**: 70-80% overall performance improvement

### Phase 2: Stability (Week 2)
1. ✅ Implement Redis-based distributed rate limiter
2. ✅ Add Circuit Breaker pattern
3. ✅ Add health check endpoints

**Expected Impact**: Near-zero API bans, 99.5%+ uptime

### Phase 3: Advanced Optimization (Week 3-4)
1. ✅ Implement tiered caching strategy
2. ✅ Add OpenTelemetry instrumentation
3. ✅ Tune PostgreSQL configuration
4. ✅ Implement COPY strategy for bulk loads

**Expected Impact**: Additional 20-30% speedup, better observability

### Phase 4: Future Enhancements (Month 2+)
1. ⏳ Evaluate and migrate to official data provider
2. ⏳ Implement streaming for large result sets
3. ⏳ Advanced query optimization

---

## References

- [SQLAlchemy 2.0 Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Redis Rate Limiting Patterns](https://redis.io/docs/manual/patterns/rate-limiter/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [asyncpg Performance Guide](https://github.com/MagicStack/asyncpg#performance)
