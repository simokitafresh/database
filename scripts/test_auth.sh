#!/bin/bash
# Test authentication and basic connectivity

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

SERVICE_URL="https://stockdata-api-6xok.onrender.com"
CORRECT_TOKEN="8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"

log "=== Authentication and Connectivity Test ==="

# Test 1: Health endpoint (no auth required)
log "1. Testing health endpoint (no auth)..."
health_status=$(curl -s -w "%{http_code}" -o /tmp/health.txt "$SERVICE_URL/healthz" || echo "000")
if [ -f /tmp/health.txt ]; then
    health_body=$(cat /tmp/health.txt)
    log "Health: $health_status - $health_body"
    rm -f /tmp/health.txt
fi

# Test 2: API docs (no auth required)
log "2. Testing API docs..."
docs_status=$(curl -s -w "%{http_code}" -o /dev/null "$SERVICE_URL/docs" || echo "000")
log "Docs: $docs_status"

# Test 3: Cron status with correct token
log "3. Testing cron status with correct token..."
status_response=$(curl -s -w "HTTPSTATUS:%{http_code}" -X GET "$SERVICE_URL/v1/status" -H "X-Cron-Secret: $CORRECT_TOKEN" 2>&1)
if [[ $status_response =~ HTTPSTATUS:([0-9]+) ]]; then
    status_code="${BASH_REMATCH[1]}"
    status_body="${status_response%HTTPSTATUS:*}"
    log "Status endpoint: $status_code - $status_body"
else
    log "Status endpoint error: $status_response"
fi

# Test 4: Cron status with wrong token
log "4. Testing cron status with wrong token..."
wrong_response=$(curl -s -w "HTTPSTATUS:%{http_code}" -X GET "$SERVICE_URL/v1/status" -H "X-Cron-Secret: wrong-token" 2>&1)
if [[ $wrong_response =~ HTTPSTATUS:([0-9]+) ]]; then
    wrong_code="${BASH_REMATCH[1]}"
    wrong_body="${wrong_response%HTTPSTATUS:*}"
    log "Wrong token: $wrong_code - $wrong_body"
else
    log "Wrong token error: $wrong_response"
fi

# Test 5: Dry run with correct token
log "5. Testing dry run..."
dryrun_response=$(curl -s -w "HTTPSTATUS:%{http_code}" -X POST "$SERVICE_URL/v1/daily-update" \
  -H "X-Cron-Secret: $CORRECT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}' 2>&1)

if [[ $dryrun_response =~ HTTPSTATUS:([0-9]+) ]]; then
    dryrun_code="${BASH_REMATCH[1]}"
    dryrun_body="${dryrun_response%HTTPSTATUS:*}"
    log "Dry run: $dryrun_code - $dryrun_body"
else
    log "Dry run error: $dryrun_response"
fi

log "=== Test completed ==="

# Summary
log "SUMMARY:"
log "- Health endpoint: $health_status"
log "- API docs: $docs_status"  
log "- Cron status (correct token): $status_code"
log "- Cron status (wrong token): $wrong_code"
log "- Dry run: $dryrun_code"

if [ "$dryrun_code" = "500" ]; then
    log ""
    log "❌ DRY RUN FAILED WITH 500 ERROR"
    log "This indicates a server-side application error."
    log "Check Render logs for detailed Python stack trace."
    log ""
    log "Common causes:"
    log "1. Database connection failed (check DATABASE_URL)"
    log "2. Missing environment variables" 
    log "3. asyncpg compilation/import errors"
    log "4. Application startup errors"
fi
