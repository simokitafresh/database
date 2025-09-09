#!/bin/bash
# Simplified cron command with hardcoded URL for immediate fix

# Exit on any error
set -e

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting daily stock data update cron job"

# Hardcoded values (temporary fix)
SERVICE_URL="https://stockdata-api-6xok.onrender.com"
CRON_TOKEN="8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"

# Use environment variable if available, otherwise use hardcoded
if [ -n "$CRON_SECRET_TOKEN" ]; then
    TOKEN="$CRON_SECRET_TOKEN"
else
    TOKEN="$CRON_TOKEN"
    log "Using hardcoded token (CRON_SECRET_TOKEN not set)"
fi

log "Using service URL: $SERVICE_URL"
log "Executing daily update endpoint..."

# Execute the cron job
curl -X POST "${SERVICE_URL}/v1/daily-update" \
  -H "X-Cron-Secret: ${TOKEN}" \
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
    
    # Extract status from response if possible
    if command -v python3 >/dev/null 2>&1; then
        status=$(cat /tmp/cron_response.json | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('status', 'unknown'))" 2>/dev/null || echo "unknown")
        log "Job status: $status"
    fi
    
    # Clean up
    rm -f /tmp/cron_response.json
else
    log "ERROR: No response received from cron endpoint"
    exit 1
fi

log "Daily stock data update completed"
