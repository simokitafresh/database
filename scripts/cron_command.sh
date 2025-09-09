#!/bin/bash
# Cron job command for Render.com daily stock data update

# Exit on any error
set -e

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting daily stock data update cron job"

# Validate required environment variables
if [ -z "$RENDER_EXTERNAL_URL" ]; then
    log "RENDER_EXTERNAL_URL not set, using hardcoded fallback"
    RENDER_EXTERNAL_URL="https://stockdata-api-6xok.onrender.com"
fi

if [ -z "$CRON_SECRET_TOKEN" ]; then
    log "CRON_SECRET_TOKEN not set, using hardcoded fallback"
    CRON_SECRET_TOKEN="8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"
fi

# Debug: Show the URL being used (without token for security)
log "Using URL: ${RENDER_EXTERNAL_URL}/v1/daily-update"

# Execute the cron job with retry logic
log "Executing daily update endpoint..."

# Ensure URL doesn't have trailing slash and construct full endpoint URL
BASE_URL="${RENDER_EXTERNAL_URL%/}"
ENDPOINT_URL="${BASE_URL}/v1/daily-update"

log "Full endpoint URL: ${ENDPOINT_URL}"

curl -X POST "${ENDPOINT_URL}" \
  -H "X-Cron-Secret: ${CRON_SECRET_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}' \
  --max-time 3600 \
  --retry 2 \
  --retry-delay 30 \
  --fail \
  --show-error \
  --silent \
  --output /tmp/cron_response.json

# Check if response file exists and show results
if [ -f /tmp/cron_response.json ]; then
    log "Cron job completed successfully"
    log "Response: $(cat /tmp/cron_response.json)"
    
    # Extract status from response
    status=$(cat /tmp/cron_response.json | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('status', 'unknown'))")
    log "Job status: $status"
    
    # Clean up
    rm -f /tmp/cron_response.json
else
    log "ERROR: No response received from cron endpoint"
    exit 1
fi

log "Daily stock data update completed"
