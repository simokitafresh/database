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
- Cron maintenance endpoints require the header `X-Cron-Secret: <token>`. The expected token is configured in `settings.CRON_SECRET_TOKEN`.

## Pagination Patterns
- `GET /v1/coverage` exposes `page` and `page_size` with a `pagination` object in the response.
- `GET /v1/fetch` uses cursor-like `limit` and `offset` and returns a `total` field.

## Endpoint Reference

### Root and Health
| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | Root ping (`{"status": "ok", "service": "Stock OHLCV API"}`) |
| GET | `/healthz` | Process and database heartbeat |
| GET | `/v1/health` | Version scoped heartbeat with service label |

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
| `auto_fetch` | bool | no (default `true`) | When true, ensures DB coverage by talking to Yahoo Finance |

Behavior highlights:
- Unknown tickers are auto-registered when `ENABLE_AUTO_REGISTRATION` is true.
- Symbol changes are resolved transparently (one-hop) so merged histories are returned.
- Each call re-fetches the last `settings.YF_REFETCH_DAYS` to incorporate late adjustments.

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

#### GET `/v1/prices/count/{symbol}`
Debug helper returning the number of stored rows and min/max dates for a symbol.

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
- `symbols` (list[str], 1-100, validated against `[A-Z0-9.-]{1,20}`)
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
- `status` (optional filter; one of `pending`, `processing`, `completed`, `completed_with_errors`, `failed`, `cancelled`)
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

## Common Workflows
1. **Serve end-user charts**: call `GET /v1/prices` with `auto_fetch=true`. Cache results and monitor coverage via `GET /v1/coverage` for anomalies.
2. **Backfill history**: create a fetch job with `POST /v1/fetch`, poll `/v1/fetch/{job_id}`, and reconcile results. Retry failed symbols via a follow-up job or manual `GET /v1/prices`.
3. **Daily operations**: run `/v1/daily-update` from a scheduler using the cron secret, then inspect `/v1/status` to confirm success.

## Helpful Source Files
- `app/api/v1/prices.py`
- `app/api/v1/coverage.py`
- `app/api/v1/fetch.py`
- `app/api/v1/cron.py`
- `app/api/v1/symbols.py`
- Schemas in `app/schemas/`

Keep this guide alongside the canonical specs (`architecture.md`, `README.md`, `docs/implementation-task-list.md`) so automated agents remain aligned with production behavior.
