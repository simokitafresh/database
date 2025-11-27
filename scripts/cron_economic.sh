#!/bin/bash
# Cron job command for Render.com daily economic data update (FRED)

# Exit on any error
set -e

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting daily economic data update cron job"

# Validate required environment variables
if [ -z "$RENDER_EXTERNAL_URL" ]; then
    log "RENDER_EXTERNAL_URL not set, using hardcoded fallback"
    RENDER_EXTERNAL_URL="https://stockdata-api-6xok.onrender.com"
fi

if [ -z "$CRON_SECRET_TOKEN" ]; then
    log "CRON_SECRET_TOKEN not set, using hardcoded fallback"
    CRON_SECRET_TOKEN="8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"
fi

# Ensure URL doesn't start with duplicate https://
if [[ "$RENDER_EXTERNAL_URL" == https://https://* ]]; then
    RENDER_EXTERNAL_URL="${RENDER_EXTERNAL_URL#https://}"
    log "Fixed duplicate https:// in URL"
fi

# Construct base URL
BASE_URL="${RENDER_EXTERNAL_URL%/}"

log "Using base URL: ${BASE_URL}"

# Call the economic update endpoint
log "Triggering daily economic update..."
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -X POST "${BASE_URL}/v1/daily-economic-update" \
  -H "Content-Type: application/json" \
  -H "X-Cron-Secret: ${CRON_SECRET_TOKEN}" \
  -d '{"dry_run": false}' \
  --max-time 60)

# Extract HTTP status and body
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')

if [ "$HTTP_STATUS" != "200" ]; then
    log "ERROR: Failed to update economic data. HTTP Status: $HTTP_STATUS"
    log "Response: $BODY"
    exit 1
fi

log "Successfully updated economic data"
log "Response: $BODY"
