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

# Ensure URL doesn't start with duplicate https://
if [[ "$RENDER_EXTERNAL_URL" == https://https://* ]]; then
    RENDER_EXTERNAL_URL="${RENDER_EXTERNAL_URL#https://}"
    log "Fixed duplicate https:// in URL"
fi

# Construct base URL
BASE_URL="${RENDER_EXTERNAL_URL%/}"

log "Using base URL: ${BASE_URL}"

# Step 1: Get active symbols
log "Fetching active symbols..."
SYMBOLS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  "${BASE_URL}/v1/symbols?active=true" \
  -H "X-Cron-Secret: ${CRON_SECRET_TOKEN}" \
  --max-time 30)

# Extract HTTP status and body
HTTP_STATUS=$(echo "$SYMBOLS_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
SYMBOLS_BODY=$(echo "$SYMBOLS_RESPONSE" | sed '/HTTP_STATUS:/d')

if [ "$HTTP_STATUS" != "200" ]; then
    log "ERROR: Failed to fetch symbols. HTTP Status: $HTTP_STATUS"
    log "Response: $SYMBOLS_BODY"
    exit 1
fi

# Extract symbols array from JSON response
SYMBOLS=$(echo "$SYMBOLS_BODY" | python3 -c "
import json
import sys
try:
    data = json.load(sys.stdin)
    symbols = [item['symbol'] for item in data if item.get('is_active', False)]
    print(','.join(symbols))
except:
    print('')
")

if [ -z "$SYMBOLS" ]; then
    log "ERROR: No active symbols found"
    exit 1
fi

log "Found active symbols: $SYMBOLS"

# Step 2: Calculate date range (last 30 days)
START_DATE=$(date -d '30 days ago' +%Y-%m-%d)
END_DATE=$(date +%Y-%m-%d)

log "Date range: $START_DATE to $END_DATE"

# Step 3: Create fetch job
log "Creating fetch job..."
JOB_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -X POST "${BASE_URL}/v1/fetch" \
  -H "Content-Type: application/json" \
  -d "{\"symbols\": [\"$(echo $SYMBOLS | sed 's/,/\",\"/g')\"], \"date_from\": \"$START_DATE\", \"date_to\": \"$END_DATE\"}" \
  --max-time 60)

# Extract HTTP status and body
JOB_HTTP_STATUS=$(echo "$JOB_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
JOB_BODY=$(echo "$JOB_RESPONSE" | sed '/HTTP_STATUS:/d')

if [ "$JOB_HTTP_STATUS" != "200" ]; then
    log "ERROR: Failed to create fetch job. HTTP Status: $JOB_HTTP_STATUS"
    log "Response: $JOB_BODY"
    exit 1
fi

# Extract job ID from response
JOB_ID=$(echo "$JOB_BODY" | python3 -c "
import json
import sys
try:
    data = json.load(sys.stdin)
    print(data.get('id', ''))
except:
    print('')
")

if [ -z "$JOB_ID" ]; then
    log "ERROR: Failed to extract job ID from response"
    log "Response: $JOB_BODY"
    exit 1
fi

log "Successfully created fetch job with ID: $JOB_ID"
log "Job details: $JOB_BODY"

log "Daily stock data update job initiated successfully"
