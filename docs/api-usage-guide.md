# API Usage Guide for the Stock Data Platform

This guide distills the FastAPI surface of the stock data management system so another LLM (or any automated agent) can interact with it safely. Cross-check design intent in `architecture.md` and live examples in `README.md` when implementing clients.

## Base URLs and Versioning
- Local development: `http://localhost:8000`
- Render deployment example: `https://your-app.onrender.com`
- Global health check lives at `/healthz` (no prefix)
- All versioned resources share the `/v1` prefix. A lightweight status for that scope is exposed at `/v1/health`.

## Request and Response Conventions
- Request and response bodies are JSON unless noted (coverage export streams CSV).
- Dates use `YYYY-MM-DD`. Timestamps are ISO 8601 with a `Z` suffix (UTC).
- Lists of symbols are always comma separated (`symbols=AAPL,MSFT`) and normalized to uppercase.
- Successful responses use standard 2xx codes. Error payloads follow:

```json
{
  "error": {
    "code": "INVALID_DATE_RANGE",
    "message": "...",
    "details": {"field": "value", "...": "..."}
  }
}
```

## Authentication
- General API consumers do not need authentication.
- Cron maintenance endpoints (`/v1/daily-update`, `/v1/daily-economic-update`, `/v1/status`) require the header `X-Cron-Secret: <token>`. The expected token is configured in `settings.CRON_SECRET_TOKEN`.

## Rate Limiting and Throttling

### External API Rate Limits (Yahoo Finance)
When `auto_fetch=true`, requests may trigger Yahoo Finance API calls. These are rate-limited:

| Setting | Value | Description |
|---------|-------|-------------|
| `YF_RATE_LIMIT_REQUESTS_PER_SECOND` | 2.0 | Token bucket rate |
| `YF_RATE_LIMIT_BURST_SIZE` | 10 | Maximum burst capacity |
| `YF_RATE_LIMIT_MAX_BACKOFF_DELAY` | 60s | Maximum retry delay |

### DB-Only Access (`auto_fetch=false`)
When `auto_fetch=false`, **no external API rate limits apply**. However, consider:
- **Connection pool limits**: Supabase Standard Plan has concurrent connection limits
- **Server resources**: Large concurrent requests may strain memory/CPU
- **Recommendation**: Limit parallel requests to **5-10 concurrent** for optimal performance

### Queueing Behavior
Fetch jobs (`POST /v1/fetch`) are queued and processed asynchronously:
- Maximum concurrent jobs: `FETCH_MAX_CONCURRENT_JOBS` (default: 10)
- Worker concurrency: `FETCH_WORKER_CONCURRENCY` (default: 2)
- Jobs exceeding limits are queued with `pending` status

## Pagination Patterns
- `GET /v1/coverage` exposes `page` and `page_size` with a `pagination` object in the response.
- `GET /v1/fetch` uses cursor-like `limit` and `offset` and returns a `total` field.

## Endpoint Reference

### Root and Health
| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | Root ping (`{"status": "ok", "service": "Stock OHLCV API"}`) |
| GET | `/healthz` | Simple health check (`{"status": "ok"}`) |
| GET | `/v1/health` | Version scoped heartbeat (`{"status": "ok", "service": "Stock OHLCV API", "scope": "v1"}`) |

### Symbol Directory
#### GET `/v1/symbols`
Returns every known ticker with metadata.

Query parameters:
- `active` (`bool`, optional): filter to active symbols.

Sample response:
```json
[
  {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "exchange": "NASDAQ",
    "currency": "USD",
    "is_active": true,
    "first_date": "1980-12-12",
    "last_date": "2024-09-10",
    "created_at": "2024-01-10T02:41:25.315000Z"
  }
]
```

### Price Data
#### GET `/v1/prices`
On-demand OHLCV retrieval with automatic registration and refetching.

Query parameters:
| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `symbols` | string | yes | Comma separated tickers, max `settings.API_MAX_SYMBOLS` |
| `from` | date | yes | Inclusive start date |
| `to` | date | yes | Inclusive end date (clipped to today) |
| `auto_fetch` | bool | no (default `true`) | When true, ensures DB coverage by talking to Yahoo Finance. When false, reads only from DB (allows larger limits). |

Behavior highlights:
- Unknown tickers are auto-registered when `ENABLE_AUTO_REGISTRATION` is true.
- Symbol changes are resolved transparently (one-hop) so merged histories are returned.
- Each call re-fetches the last `settings.YF_REFETCH_DAYS` to incorporate late adjustments.
- **Bulk Fetching**: Set `auto_fetch=false` to enable bulk read mode.
  - `auto_fetch=true`: Max 10 symbols, 50,000 rows (External API limit)
  - `auto_fetch=false`: Max 100 symbols, 200,000 rows (DB-only limit)

**Important**: `GET /v1/prices` does **not** support pagination. For data exceeding 200,000 rows, use date range splitting:
```python
# Example: Fetching 100 symbols × 20 years (split by year)
for year in range(2005, 2025):
    response = requests.get(
        f"/v1/prices?symbols={symbols}&from={year}-01-01&to={year}-12-31&auto_fetch=false"
    )
```

Sample request:
```
curl "http://localhost:8000/v1/prices?symbols=AAPL,MSFT&from=2024-01-01&to=2024-01-31"
```

Sample response (trimmed):
```json
[
  {
    "symbol": "AAPL",
    "date": "2024-01-02",
    "open": 184.22,
    "high": 186.00,
    "low": 183.89,
    "close": 185.64,
    "volume": 48682000,
    "source": "database",
    "last_updated": "2024-02-01T04:12:23Z",
    "source_symbol": "AAPL"
  }
]
```

Sample bulk request (DB-only):
```
curl "http://localhost:8000/v1/prices?symbols=AAPL,MSFT,...(up to 100)&from=2020-01-01&to=2024-12-31&auto_fetch=false"
```

#### DELETE `/v1/prices/{symbol}`
Permanently removes price rows for one symbol.

Query parameters:
| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `date_from` | date | no | Inclusive lower bound |
| `date_to` | date | no | Inclusive upper bound |
| `confirm` | bool | yes | Must be `true`; otherwise a `CONFIRMATION_REQUIRED` error is returned |

Sample request:
```
curl -X DELETE "http://localhost:8000/v1/prices/AAPL?date_from=2024-01-01&date_to=2024-06-30&confirm=true"
```

Sample response:
```json
{
  "symbol": "AAPL",
  "deleted_rows": 126,
  "date_range": {"from": "2024-01-01", "to": "2024-06-30"},
  "deleted_at": "2024-09-12T03:15:22Z",
  "message": "Successfully deleted 126 price records"
}
```

### Coverage Analytics
#### GET `/v1/coverage`
Paginated coverage dashboard backed by the `coverage_summary` view.

Key query parameters:
| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | int | 1 | 1-based index |
| `page_size` | int | 50 | 1-1000 |
| `q` | string | none | Search by symbol or name |
| `sort_by` | string | `symbol` | Must be one of `symbol`, `name`, `exchange`, `currency`, `is_active`, `data_start`, `data_end`, `data_days`, `row_count`, `last_updated` |
| `order` | string | `asc` | Either `asc` or `desc` |
| `has_data` | bool | none | Filter by data availability |
| `start_after` | date | none | Require data_start after this value |
| `end_before` | date | none | Require data_end before this value |
| `updated_after` | datetime | none | Require last_updated after this timestamp |

Sample response (abbreviated):
```json
{
  "items": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "exchange": "NASDAQ",
      "currency": "USD",
      "is_active": true,
      "data_start": "1980-12-12",
      "data_end": "2024-09-11",
      "data_days": 11023,
      "row_count": 11023,
      "last_updated": "2024-09-11T03:18:45Z",
      "has_gaps": false
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_items": 5423,
    "total_pages": 109
  },
  "meta": {
    "query_time_ms": 42,
    "cached": true,
    "cache_updated_at": "2024-09-11T03:20:00Z"
  }
}
```

#### GET `/v1/coverage/export`
Streams the same data set as CSV. Accepts the same filters plus `max_rows` (1-50,000). Response headers include `Content-Type: text/csv` and `Content-Disposition: attachment; filename=coverage_YYYYMMDD_HHMMSS.csv`.

### Fetch Job Management
Fetch jobs orchestrate bulk historical loads through the background worker (`app/services/fetch_worker.py`).

#### POST `/v1/fetch`
Creates a job and schedules it for asynchronous execution.

Request body:
- `symbols` (list[str], 1-100, validated against `[\^A-Z0-9.-]{1,20}`)
- `date_from` (date, not more than 20 years back)
- `date_to` (date, same or after `date_from`, not in the future, max 10-year span)
- `interval` (`1d`, `1wk`, `1mo`, `3mo`, default `1d`)
- `force` (bool, default `false`)
- `priority` (`low`, `normal`, `high`, default `normal`)

Sample response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Fetch job created for 3 symbols",
  "symbols_count": 3,
  "date_range": {"from": "2024-01-01", "to": "2024-12-31"}
}
```

#### GET `/v1/fetch/{job_id}`
Returns full job state, including progress tracking and per-symbol outcomes.

Example fragment:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "symbols": ["AAPL", "MSFT", "GOOGL"],
  "date_from": "2024-01-01",
  "date_to": "2024-12-31",
  "progress": {
    "total_symbols": 3,
    "completed_symbols": 1,
    "current_symbol": "MSFT",
    "total_rows": 0,
    "fetched_rows": 1245,
    "percent": 33.3
  },
  "results": [
    {"symbol": "AAPL", "status": "success", "rows_fetched": 252},
    {"symbol": "MSFT", "status": "running"}
  ],
  "errors": [],
  "created_at": "2024-09-11T21:14:05Z"
}
```

#### GET `/v1/fetch`
Lists jobs, newest first.

Query parameters:
- `status` (optional filter; one of `pending`, `processing`, `completed`, `completed_errors`, `failed`, `cancelled`)
- `date_from` (optional ISO 8601 timestamp; returns jobs created after it)
- `limit` (1-100, default 20)
- `offset` (>= 0, default 0)

Response shape:
```json
{
  "jobs": [
    {"job_id": "...", "status": "completed", "symbols": ["AAPL"], "created_at": "..."}
  ],
  "total": 42
}
```

#### POST `/v1/fetch/{job_id}/cancel`
Attempts to cancel a pending or processing job. Responds with `{ "success": true, "message": "...", "job_id": "...", "cancelled_at": "..." }`. Cancelling an already terminal job yields `JOB_NOT_CANCELLABLE` (400); unknown IDs return `JOB_NOT_FOUND` (404).

### Scheduled Maintenance (Cron) Endpoints
These endpoints are meant for trusted automation and enforce the cron secret header.

#### POST `/v1/daily-update`
Triggers a batched refresh for all active symbols.

Headers:
- `X-Cron-Secret`: required.

Request body:
- `dry_run` (bool, default `false`): when true, returns the plan without executing fetches.
- `date_from` / `date_to` (optional `YYYY-MM-DD` strings): override the default window (yesterday back to `settings.CRON_UPDATE_DAYS`).

Success response fields include:
- `status`: `success`, `completed_with_errors`, or `failed`
- `message`: human summary
- `total_symbols`, `batch_count`, `batch_size`
- `date_range`: processed window
- `success_count`, `failed_symbols` (if any)

#### GET `/v1/status`
Also gated by `X-Cron-Secret`. Summarises recent cron activity and current configuration (active symbol count, batch size, YF concurrency).

Sample response:
```json
{
  "status": "active",
  "last_run": null,
  "recent_job_count": 0,
  "job_status_counts": {},
  "settings": {
    "batch_size": 50,
    "update_days": 7,
    "yf_concurrency": 5,
    "active_symbols": 150
  }
}
```

#### POST `/v1/daily-economic-update`
Triggers an update for economic indicator data (FRED DTB3 3-Month Treasury Bill Rate).

Headers:
- `X-Cron-Secret`: required.

Request body:
- `dry_run` (bool, default `false`): when true, returns the plan without executing fetches.
- `date_from` / `date_to` (optional `YYYY-MM-DD` strings): override the default date range.

The endpoint automatically detects whether full history or incremental updates are needed.

Success response fields include:
- `status`: `success`
- `message`: human summary
- `total_symbols`: always 1 (DTB3)
- `batch_count`: 1
- `date_range`: processed window
- `success_count`: number of data points updated

### Debug and Performance Endpoints

#### GET `/v1/prices/count/{symbol}`
Debug helper returning the count of stored price rows and the min/max date range for a symbol.

Sample response:
```json
{
  "symbol": "AAPL",
  "count": 11023,
  "date_range": {
    "min": "1980-12-12",
    "max": "2024-09-11"
  }
}
```

#### GET `/v1/performance/report`
Returns performance profiling report for debugging bottlenecks.

Sample response:
```json
{
  "performance_report": {
    "get_prices_api": {
      "count": 150,
      "avg_ms": 45.3,
      "max_ms": 230.5
    }
  },
  "timestamp": "2024-09-11T03:20:00Z"
}
```

#### GET `/v1/debug/cache-stats`
Returns cache statistics (development/staging environments only).

Sample response:
```json
{
  "total_items": 25,
  "max_size": 1000,
  "ttl_seconds": 300,
  "sample_items": [
    {
      "key": "prices:AAPL:2024-01-01:2024-09-11",
      "age_seconds": 120.5,
      "size_bytes": 45230
    }
  ]
}
```

### Economic Indicators (FRED Data)

#### GET `/v1/economic`
List all available economic data series with metadata.

Sample response:
```json
[
  {
    "symbol": "DTB3",
    "name": "3-Month Treasury Bill Secondary Market Rate",
    "description": "The 3-Month Treasury Bill rate is the yield received for investing in a US government issued treasury bill with a 3-month maturity.",
    "frequency": "Daily",
    "units": "Percent",
    "source": "FRED (Federal Reserve Economic Data)",
    "data_start": "1954-01-04",
    "data_end": "2024-11-25",
    "row_count": 17845,
    "last_updated": "2024-11-26T03:00:00Z"
  }
]
```

#### GET `/v1/economic/{symbol}`
Get historical economic indicator data for a specific series.

Query parameters:
| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `from` | date | no | Start date (YYYY-MM-DD) |
| `to` | date | no | End date (YYYY-MM-DD) |
| `limit` | int | no (default 1000) | Max records (1-10000) |
| `order` | string | no (default `asc`) | `asc` or `desc` |

Sample request:
```
curl "http://localhost:8000/v1/economic/DTB3?from=2024-01-01&to=2024-12-31"
```

Sample response:
```json
{
  "symbol": "DTB3",
  "data": [
    {
      "symbol": "DTB3",
      "date": "2024-01-02",
      "value": 5.22,
      "last_updated": "2024-01-03T03:00:00Z"
    },
    {
      "symbol": "DTB3",
      "date": "2024-01-03",
      "value": 5.24,
      "last_updated": "2024-01-04T03:00:00Z"
    }
  ],
  "count": 2,
  "date_range": {
    "from": "2024-01-02",
    "to": "2024-01-03"
  }
}
```

#### GET `/v1/economic/{symbol}/latest`
Get the most recent data point for an economic series.

Sample request:
```
curl "http://localhost:8000/v1/economic/DTB3/latest"
```

Sample response:
```json
{
  "symbol": "DTB3",
  "date": "2024-11-25",
  "value": 4.42,
  "last_updated": "2024-11-26T03:00:00Z"
}
```

### Maintenance Endpoints (Price Adjustment Detection)
These endpoints detect and fix discrepancies between stored prices and Yahoo Finance's adjusted prices caused by corporate actions (splits, dividends).

#### POST `/v1/maintenance/check-adjustments`
Scans symbols for price adjustments that need correction.

Request body:
- `symbols` (list[str], optional): specific symbols to check (defaults to all active)
- `threshold_pct` (float, optional, default from settings): minimum % diff to flag
- `sample_points` (int, optional, 2-50): number of date samples per symbol

Sample request:
```bash
curl -X POST "http://localhost:8000/v1/maintenance/check-adjustments" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT"], "threshold_pct": 1.0}'
```

Sample response:
```json
{
  "status": "success",
  "message": "Adjustment check completed",
  "scanned": 2,
  "needs_refresh_count": 1,
  "no_change_count": 1,
  "affected_symbols": ["AAPL"],
  "summary": {
    "by_type": {"stock_split": 1},
    "by_severity": {"critical": 1}
  }
}
```

#### GET `/v1/maintenance/adjustment-report`
Returns detailed results from the last scan.

Query parameters:
- `symbol` (string, optional): filter to one symbol

Sample request:
```bash
curl "http://localhost:8000/v1/maintenance/adjustment-report?symbol=AAPL"
```

Sample response:
```json
{
  "last_scan_timestamp": "2024-09-15T10:30:00Z",
  "results": [
    {
      "symbol": "AAPL",
      "needs_refresh": true,
      "max_pct_diff": 50.2,
      "events": [
        {
          "date": "2020-08-31",
          "db_price": 500.28,
          "yf_price": 125.07,
          "pct_diff": 300.0,
          "adjustment_type": "stock_split",
          "severity": "critical"
        }
      ],
      "scan_timestamp": "2024-09-15T10:30:00Z"
    }
  ]
}
```

#### POST `/v1/maintenance/fix-adjustments`
Deletes affected price data and creates re-fetch jobs.

Request body:
- `symbols` (list[str], optional): symbols to fix (defaults to all flagged)
- `confirm` (bool, required): must be `true` to execute

Sample request:
```bash
curl -X POST "http://localhost:8000/v1/maintenance/fix-adjustments" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL"], "confirm": true}'
```

Sample response:
```json
{
  "status": "success",
  "message": "Fixed 1 symbols",
  "fixed_count": 1,
  "fix_results": [
    {
      "symbol": "AAPL",
      "deleted_rows": 11023,
      "job_id": "550e8400-e29b-41d4-a716-446655440000"
    }
  ],
  "timestamp": "2024-09-15T10:35:00Z"
}
```

#### POST `/v1/adjustment-check` (Cron)
Authenticated endpoint for scheduled adjustment checks.

Headers:
- `X-Cron-Secret`: required

Query parameters:
- `symbols` (string, optional): comma-separated symbols
- `auto_fix` (bool, optional): auto-apply fixes when true

Sample request:
```bash
curl -X POST "http://localhost:8000/v1/adjustment-check?auto_fix=true" \
  -H "X-Cron-Secret: your-secret-token"
```

Sample response:
```json
{
  "status": "success",
  "message": "Adjustment check completed",
  "scanned": 150,
  "needs_refresh_count": 3,
  "affected_symbols": ["AAPL", "TSLA", "NVDA"],
  "fixed_count": 3,
  "fixed_symbols": ["AAPL", "TSLA", "NVDA"],
  "duration_seconds": 45.2
}
```

**Error Responses:**
- `ADJUSTMENT_CHECK_DISABLED` (200, skipped): feature disabled via settings
- `ADJUSTMENT_CHECK_FAILED` (500): internal error during scan
- `AUTO_FIX_DISABLED` (400): `auto_fix=true` but `ADJUSTMENT_AUTO_FIX=false`
- `CONFIRMATION_REQUIRED` (400): `confirm` not true for fix endpoint

## Database Architecture

### Indexing Strategy
The `prices` table uses a **composite primary key** on `(symbol, date)`, which automatically creates a B-tree index. This optimizes:
- Range queries: `WHERE symbol = 'AAPL' AND date BETWEEN '2024-01-01' AND '2024-12-31'`
- Multi-symbol queries: `WHERE symbol = ANY(ARRAY['AAPL', 'MSFT', ...]) AND date BETWEEN ...`

### Connection Pooling
SQLAlchemy async connection pooling is configured:

| Setting | Value | Description |
|---------|-------|-------------|
| `DB_POOL_SIZE` | 5 | Base connections in pool |
| `DB_MAX_OVERFLOW` | 5 | Additional connections allowed |
| `DB_POOL_PRE_PING` | True | Health check before use |
| `DB_POOL_RECYCLE` | 900s | Connection lifetime |

When using Supabase Pooler (PgBouncer), the system automatically switches to `NullPool` mode.

### Query Execution
Multi-symbol queries use PostgreSQL's `ANY` operator for efficient batch retrieval:
```sql
SELECT * FROM prices
WHERE symbol = ANY(:symbols)
  AND date BETWEEN :date_from AND :date_to
ORDER BY symbol, date
```

### Caching
Redis-backed caching with in-memory fallback:

| Setting | Value | Description |
|---------|-------|-------------|
| `CACHE_TTL_SECONDS` | 3600 | Cache lifetime (1 hour) |
| `ENABLE_CACHE` | true | Enable/disable caching |

Cache keys:
- Individual: `prices:{symbol}:{date_from}:{date_to}`
- Batch: `prices:batch:{sorted_symbols}:{date_from}:{date_to}`

## ETL Integration Guide

### Recommended Data Flow
For ETL/batch processing systems, use this workflow:

```
┌─────────────────────┐
│ 1. POST /v1/fetch   │  Create async job for data ingestion
│    (symbols, dates) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. GET /v1/fetch/   │  Poll until status="completed"
│    {job_id}         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. GET /v1/prices   │  Retrieve data from DB
│    auto_fetch=false │  (no external API calls)
└─────────────────────┘
```

### Use Case Matrix

| Use Case | Endpoint | Parameters | Symbol Limit | Row Limit |
|----------|----------|------------|--------------|----------|
| Real-time display | `GET /v1/prices` | `auto_fetch=true` (default) | 10 | 50,000 |
| Batch calculation | `GET /v1/prices` | `auto_fetch=false` | 100 | 200,000 |
| Historical backfill | `POST /v1/fetch` | - | 100 | - |
| Gap detection | `GET /v1/coverage` | - | - | - |

### Handling Large Datasets (>200,000 rows)
Since `GET /v1/prices` lacks pagination, split requests by:

1. **Date range** (recommended): Fetch year-by-year or quarter-by-quarter
2. **Symbol batches**: Split into 50-symbol chunks

Example for 100 symbols × 20 years:
```python
import requests

symbols = "AAPL,MSFT,..."  # 100 symbols
all_data = []

# Split by year to stay under 200,000 row limit
for year in range(2005, 2025):
    response = requests.get(
        "https://api.example.com/v1/prices",
        params={
            "symbols": symbols,
            "from": f"{year}-01-01",
            "to": f"{year}-12-31",
            "auto_fetch": "false"
        }
    )
    all_data.extend(response.json())
```

### Fetch Job Data Flow
**Important**: Fetch job responses contain only status metadata, not price data.

```json
// GET /v1/fetch/{job_id} returns:
{
  "job_id": "...",
  "status": "completed",
  "results": [
    {"symbol": "AAPL", "status": "success", "rows_fetched": 252}
  ]
  // Note: Actual price data is NOT included here
}
```

To retrieve the actual data after job completion:
```bash
curl "http://localhost:8000/v1/prices?symbols=AAPL&from=2024-01-01&to=2024-12-31&auto_fetch=false"
```

## Common Workflows
1. **Serve end-user charts**: call `GET /v1/prices` with `auto_fetch=true`. Cache results and monitor coverage via `GET /v1/coverage` for anomalies.
2. **Backfill history**: create a fetch job with `POST /v1/fetch`, poll `/v1/fetch/{job_id}`, and reconcile results. Retry failed symbols via a follow-up job or manual `GET /v1/prices`.
3. **Daily operations**: run `/v1/daily-update` from a scheduler using the cron secret, then inspect `/v1/status` to confirm success.
4. **Economic data updates**: run `/v1/daily-economic-update` for FRED Treasury Bill rate data updates.
5. **Debug and monitor**: use `/v1/prices/count/{symbol}` to check data persistence, `/v1/performance/report` for profiling, and `/v1/debug/cache-stats` for cache inspection (dev/staging only).
6. **Price adjustment maintenance**: periodically run `/v1/maintenance/check-adjustments` or `/v1/adjustment-check` (cron) to detect split/dividend adjustments; review with `/v1/maintenance/adjustment-report`; fix via `/v1/maintenance/fix-adjustments`.

## Helpful Source Files
- `app/api/v1/prices.py` - Price data retrieval and deletion
- `app/api/v1/coverage.py` - Coverage analytics and export
- `app/api/v1/fetch.py` - Fetch job management
- `app/api/v1/cron.py` - Scheduled maintenance endpoints
- `app/api/v1/maintenance.py` - Price adjustment detection and fixing
- `app/api/v1/symbols.py` - Symbol directory
- `app/api/v1/health.py` - Health check endpoints
- `app/api/v1/debug.py` - Debug endpoints (cache stats)
- `app/api/v1/economic.py` - Economic indicators API (DTB3)
- `app/services/adjustment_detector.py` - Adjustment detection service
- `app/services/fred_service.py` - FRED API integration
- `app/schemas/maintenance.py` - Adjustment check/fix schemas
- `app/schemas/economic.py` - Economic data schemas
- Schemas in `app/schemas/`

Keep this guide alongside the canonical specs (`architecture.md`, `README.md`, `docs/implementation-task-list.md`) so automated agents remain aligned with production behavior.
