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
    log "ERROR: RENDER_EXTERNAL_URL not set"
    exit 1
fi

if [ -z "$CRON_SECRET_TOKEN" ]; then
    log "ERROR: CRON_SECRET_TOKEN not set"
    exit 1
fi

# Execute the cron job with retry logic
log "Executing daily update endpoint..."

curl -X POST "${RENDER_EXTERNAL_URL}/v1/daily-update" \
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
