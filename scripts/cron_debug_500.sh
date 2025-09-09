#!/bin/bash
# Debug version for analyzing 500 errors

# Exit on any error
set -e

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting daily stock data update cron job (debug mode)"

# Clean URL handling
SERVICE_URL="stockdata-api-6xok.onrender.com"
CRON_TOKEN="8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"

# Use environment variables if available
if [ -n "$CRON_SECRET_TOKEN" ]; then
    CRON_TOKEN="$CRON_SECRET_TOKEN"
fi

# Construct clean URL
FULL_URL="https://${SERVICE_URL}/v1/daily-update"

log "Using service: $SERVICE_URL"
log "Full endpoint: $FULL_URL"

# First check if service is healthy
log "Checking service health..."
health_response=$(curl -s -w "%{http_code}" -o /tmp/health_check.txt "https://${SERVICE_URL}/healthz" || echo "000")
if [ -f /tmp/health_check.txt ]; then
    health_content=$(cat /tmp/health_check.txt)
    log "Health check response ($health_response): $health_content"
    rm -f /tmp/health_check.txt
fi

# Check cron status endpoint first
log "Checking cron status endpoint..."
status_response=$(curl -s -w "%{http_code}" -o /tmp/status_check.txt -X GET "https://${SERVICE_URL}/v1/status" -H "X-Cron-Secret: $CRON_TOKEN" || echo "000")
if [ -f /tmp/status_check.txt ]; then
    status_content=$(cat /tmp/status_check.txt)
    log "Status check response ($status_response): $status_content"
    rm -f /tmp/status_check.txt
fi

# Now try the daily update with detailed error info
log "Executing daily update endpoint..."

# Don't fail immediately on curl error, capture the response
set +e
curl_output=$(curl -X POST "$FULL_URL" \
  -H "X-Cron-Secret: $CRON_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}' \
  -w "HTTPSTATUS:%{http_code}" \
  --max-time 3600 \
  --show-error \
  --silent 2>&1)

curl_exit_code=$?
set -e

# Parse response and status code
if [[ $curl_output =~ HTTPSTATUS:([0-9]+) ]]; then
    http_status="${BASH_REMATCH[1]}"
    response_body="${curl_output%HTTPSTATUS:*}"
else
    http_status="unknown"
    response_body="$curl_output"
fi

log "HTTP Status: $http_status"
log "Response Body: $response_body"
log "Curl Exit Code: $curl_exit_code"

if [ "$http_status" = "200" ]; then
    log "Cron job completed successfully"
    
    # Try to parse JSON response
    if command -v python3 >/dev/null 2>&1 && [[ $response_body =~ ^\{.*\}$ ]]; then
        status=$(echo "$response_body" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('status', 'unknown'))" 2>/dev/null || echo "unknown")
        log "Job status: $status"
    fi
else
    log "ERROR: Request failed with HTTP $http_status"
    log "This indicates an application error on the server side"
    
    # Try to parse error details if JSON
    if command -v python3 >/dev/null 2>&1 && [[ $response_body =~ ^\{.*\}$ ]]; then
        error_detail=$(echo "$response_body" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print('Error:', data.get('detail', data.get('error', 'Unknown error')))
except:
    print('Could not parse error response')
" 2>/dev/null || echo "Could not parse error response")
        log "$error_detail"
    fi
    
    exit 1
fi

log "Daily stock data update completed"
