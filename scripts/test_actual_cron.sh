#!/bin/bash
# Test actual cron job execution (not dry run)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

SERVICE_URL="https://stockdata-api-6xok.onrender.com"
CORRECT_TOKEN="8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"

log "=== Testing Actual Cron Job Execution ==="

# Test actual execution (not dry run)
log "Executing actual daily update..."
actual_response=$(curl -s -w "HTTPSTATUS:%{http_code}" -X POST "$SERVICE_URL/v1/daily-update" \
  -H "X-Cron-Secret: $CORRECT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}' 2>&1)

if [[ $actual_response =~ HTTPSTATUS:([0-9]+) ]]; then
    actual_code="${BASH_REMATCH[1]}"
    actual_body="${actual_response%HTTPSTATUS:*}"
    log "Actual execution: $actual_code"
    log "Response: $actual_body"
else
    log "Actual execution error: $actual_response"
fi

log "=== Cron Job Test Completed ==="

if [ "$actual_code" = "200" ]; then
    log "✅ SUCCESS: Cron job is working correctly!"
    log "Ready for production cron scheduling."
else
    log "❌ FAILED: Cron job returned HTTP $actual_code"
    log "Check the response above for details."
fi
