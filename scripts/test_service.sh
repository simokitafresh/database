#!/bin/bash
# Quick test script for the actual Render service

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

SERVICE_URL="https://stockdata-api-6xok.onrender.com"
CRON_TOKEN="8CTZxexeO9P-IASSF6B7r8cd6cCAimFK-eCeO384ZjA"

log "=== Testing stockdata-api-6xok.onrender.com ==="

# Test health endpoint
log "1. Testing health endpoint..."
curl -s "$SERVICE_URL/healthz" && echo " ✓ Health OK" || echo " ✗ Health failed"

# Test API documentation
log "2. Testing API docs..."
curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/docs" | grep -q "200" && echo " ✓ Docs accessible" || echo " ✗ Docs failed"

# Test cron status endpoint
log "3. Testing cron status..."
curl -s -X GET "$SERVICE_URL/v1/status" \
  -H "X-Cron-Secret: $CRON_TOKEN" \
  && echo " ✓ Cron status OK" || echo " ✗ Cron status failed"

# Test cron dry-run
log "4. Testing cron dry-run..."
curl -s -X POST "$SERVICE_URL/v1/daily-update" \
  -H "X-Cron-Secret: $CRON_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}' \
  && echo " ✓ Cron dry-run OK" || echo " ✗ Cron dry-run failed"

log "=== Test completed ==="
