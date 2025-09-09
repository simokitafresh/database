# Cron API Documentation

## Overview

The Cron API provides endpoints for scheduled daily updates of stock price data. It includes authentication, batch processing, and status monitoring capabilities.

## Authentication

All cron endpoints require the `X-Cron-Secret` header for authentication:

```http
X-Cron-Secret: your-secret-token-here
```

**Note**: If `CRON_SECRET_TOKEN` is not configured, authentication is bypassed with a warning (development mode).

## Endpoints

### POST /v1/daily-update

Execute daily update for all active symbols.

#### Request

```http
POST /v1/daily-update
Content-Type: application/json
X-Cron-Secret: your-token

{
    "dry_run": false,
    "date_from": "2025-09-01",
    "date_to": "2025-09-08"
}
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dry_run` | boolean | No | If true, simulate without execution (default: false) |
| `date_from` | string | No | Start date in YYYY-MM-DD format (default: CRON_UPDATE_DAYS ago) |
| `date_to` | string | No | End date in YYYY-MM-DD format (default: yesterday) |

#### Response

```json
{
    "status": "success",
    "message": "Daily update started for 27 symbols",
    "total_symbols": 27,
    "batch_count": 1,
    "job_ids": ["cron_job_20250909_125930_0"],
    "date_range": {
        "from": "2025-09-02",
        "to": "2025-09-08"
    },
    "timestamp": "2025-09-09T12:59:30.123456",
    "estimated_completion_minutes": 13.5
}
```

#### Status Codes

- `200 OK`: Request processed successfully
- `401 Unauthorized`: Missing X-Cron-Secret header
- `403 Forbidden`: Invalid authentication token
- `422 Unprocessable Entity`: Invalid request parameters
- `500 Internal Server Error`: Server error occurred

### GET /v1/status

Get current status of cron jobs and system configuration.

#### Request

```http
GET /v1/status
X-Cron-Secret: your-token
```

#### Response

```json
{
    "status": "active",
    "last_run": null,
    "recent_job_count": 0,
    "job_status_counts": {},
    "settings": {
        "batch_size": 50,
        "update_days": 7,
        "yf_concurrency": 4
    }
}
```

#### Response Fields

| Field | Description |
|-------|-------------|
| `status` | Overall cron system status ("active") |
| `last_run` | Timestamp of last cron execution (ISO format) |
| `recent_job_count` | Number of recent jobs in the system |
| `job_status_counts` | Count of jobs by status |
| `settings` | Current cron configuration values |

## Error Handling

All endpoints return structured error responses:

```json
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human readable error message"
    }
}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CRON_SECRET_TOKEN` | `""` | Authentication token (empty = no auth) |
| `CRON_BATCH_SIZE` | `50` | Maximum symbols per batch |
| `CRON_UPDATE_DAYS` | `7` | Default date range (days ago) |

## Usage Examples

### Curl Examples

```bash
# Dry run test
curl -X POST "https://your-app.onrender.com/v1/daily-update" \
  -H "X-Cron-Secret: your-token" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Full execution
curl -X POST "https://your-app.onrender.com/v1/daily-update" \
  -H "X-Cron-Secret: your-token" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# Check status
curl -X GET "https://your-app.onrender.com/v1/status" \
  -H "X-Cron-Secret: your-token"
```

### Python Examples

```python
import requests

headers = {"X-Cron-Secret": "your-token"}
base_url = "https://your-app.onrender.com"

# Dry run
response = requests.post(
    f"{base_url}/v1/daily-update",
    json={"dry_run": True},
    headers=headers
)

# Check status
status = requests.get(
    f"{base_url}/v1/status",
    headers=headers
)
```

## Integration Notes

1. **Render Cron Jobs**: Use the provided `scripts/cron_command.sh` for scheduled execution
2. **Monitoring**: Check `/v1/status` endpoint for system health
3. **Batch Processing**: Large symbol lists are automatically split into configurable batches
4. **Date Handling**: All dates are in ISO format (YYYY-MM-DD)
5. **Timezone**: All timestamps are in UTC

## Security Considerations

- Always use HTTPS in production
- Keep the CRON_SECRET_TOKEN secure and rotate regularly
- Monitor failed authentication attempts
- Use environment variables for sensitive configuration
