#!/bin/bash
# Debug version of cron command for troubleshooting

# Exit on any error
set -e

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "=== DEBUG: Starting cron job troubleshooting ==="

# Show environment variables (without sensitive data)
log "Environment check:"
log "RENDER_EXTERNAL_URL: ${RENDER_EXTERNAL_URL:-'NOT SET'}"
log "CRON_SECRET_TOKEN: ${CRON_SECRET_TOKEN:+SET}${CRON_SECRET_TOKEN:-NOT SET}"

# If URL is not set, try common alternatives
if [ -z "$RENDER_EXTERNAL_URL" ]; then
    log "Trying to determine service URL from environment..."
    
    # Check for Render's automatic environment variables
    if [ -n "$RENDER_EXTERNAL_HOSTNAME" ]; then
        RENDER_EXTERNAL_URL="https://${RENDER_EXTERNAL_HOSTNAME}"
        log "Using RENDER_EXTERNAL_HOSTNAME: $RENDER_EXTERNAL_URL"
    elif [ -n "$RENDER_SERVICE_NAME" ]; then
        RENDER_EXTERNAL_URL="https://${RENDER_SERVICE_NAME}.onrender.com"
        log "Guessing URL from service name: $RENDER_EXTERNAL_URL"
    else
        log "ERROR: Cannot determine service URL. Please set RENDER_EXTERNAL_URL manually."
        exit 1
    fi
fi

# Validate URL format
if [[ ! "$RENDER_EXTERNAL_URL" =~ ^https?:// ]]; then
    log "ERROR: RENDER_EXTERNAL_URL must start with http:// or https://"
    log "Current value: $RENDER_EXTERNAL_URL"
    exit 1
fi

# Test basic connectivity first
log "Testing basic connectivity..."
if curl --connect-timeout 10 --max-time 30 -s -o /dev/null -w "%{http_code}" "${RENDER_EXTERNAL_URL}/healthz" > /tmp/health_status 2>/dev/null; then
    health_status=$(cat /tmp/health_status)
    log "Health check returned: $health_status"
    rm -f /tmp/health_status
else
    log "WARNING: Health check failed, but continuing..."
fi

# Now try the actual cron endpoint
BASE_URL="${RENDER_EXTERNAL_URL%/}"
ENDPOINT_URL="${BASE_URL}/v1/daily-update"

log "Attempting cron job execution..."
log "Full endpoint URL: ${ENDPOINT_URL}"

# First, try with verbose output for debugging
log "Executing with detailed output..."
if curl -X POST "${ENDPOINT_URL}" \
  -H "X-Cron-Secret: ${CRON_SECRET_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}' \
  --max-time 3600 \
  --connect-timeout 30 \
  --retry 1 \
  --retry-delay 10 \
  --fail-with-body \
  --show-error \
  --verbose \
  --output /tmp/cron_response.json 2>&1 | head -50; then
    
    log "Cron job completed successfully"
    if [ -f /tmp/cron_response.json ]; then
        log "Response: $(cat /tmp/cron_response.json)"
        rm -f /tmp/cron_response.json
    fi
else
    curl_exit_code=$?
    log "ERROR: Cron job failed with exit code: $curl_exit_code"
    
    if [ -f /tmp/cron_response.json ]; then
        log "Error response: $(cat /tmp/cron_response.json)"
        rm -f /tmp/cron_response.json
    fi
    
    exit $curl_exit_code
fi

log "=== DEBUG: Cron job troubleshooting completed ==="
