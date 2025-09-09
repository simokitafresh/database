# Render Environment Variables

## New Variables to Add for Cron Job Functionality:

```
CRON_SECRET_TOKEN=8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA
CRON_BATCH_SIZE=50
CRON_UPDATE_DAYS=7
```

## Existing Variables to Verify:

```
DATABASE_URL=(existing value - do not change)
YF_REQ_CONCURRENCY=2
FETCH_TIMEOUT_SECONDS=30
```

## Render Web Service Configuration:

1. **Environment Variables**: Add the 3 new CRON_ variables above
2. **Health Check Endpoint**: `/v1/health`
3. **Port**: 8000 (default)

## Cron Job Service Configuration:

- **Service Type**: Cron Job
- **Command**: See `scripts/cron_command.sh`
- **Schedule**: Daily at 10:00 AM JST
- **Environment**: Same as web service

## Security Notes:

- The CRON_SECRET_TOKEN is cryptographically secure (43 characters)
- Token should be kept secret and not logged
- Use HTTPS for all external requests to the cron endpoints
