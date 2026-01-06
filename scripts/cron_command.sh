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

# Step 3: Create fetch jobs in batches (API limit: 100 symbols per request)
BATCH_SIZE=100
SYMBOLS_ARRAY=(${SYMBOLS//,/ })
TOTAL_SYMBOLS=${#SYMBOLS_ARRAY[@]}
log "Total symbols: $TOTAL_SYMBOLS (will process in batches of $BATCH_SIZE)"

BATCH_NUM=0
SUCCESS_COUNT=0
FAILED_BATCHES=""

for ((i=0; i<TOTAL_SYMBOLS; i+=BATCH_SIZE)); do
    BATCH_NUM=$((BATCH_NUM + 1))
    BATCH_SYMBOLS=("${SYMBOLS_ARRAY[@]:i:BATCH_SIZE}")
    BATCH_COUNT=${#BATCH_SYMBOLS[@]}
    BATCH_STR=$(IFS=,; echo "${BATCH_SYMBOLS[*]}")
    
    log "Creating fetch job for batch $BATCH_NUM ($BATCH_COUNT symbols)..."
    
    JOB_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
      -X POST "${BASE_URL}/v1/fetch" \
      -H "Content-Type: application/json" \
      -d "{\"symbols\": [\"$(echo $BATCH_STR | sed 's/,/\",\"/g')\"], \"date_from\": \"$START_DATE\", \"date_to\": \"$END_DATE\"}" \
      --max-time 1800)
    
    # Extract HTTP status and body
    JOB_HTTP_STATUS=$(echo "$JOB_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
    JOB_BODY=$(echo "$JOB_RESPONSE" | sed '/HTTP_STATUS:/d')
    
    if [ "$JOB_HTTP_STATUS" != "200" ]; then
        log "ERROR: Failed to create fetch job for batch $BATCH_NUM. HTTP Status: $JOB_HTTP_STATUS"
        log "Response: $JOB_BODY"
        FAILED_BATCHES="$FAILED_BATCHES $BATCH_NUM"
        continue
    fi
    
    # Extract job ID from response
    JOB_ID=$(echo "$JOB_BODY" | python3 -c "
import json
import sys
try:
    data = json.load(sys.stdin)
    print(data.get('job_id', ''))
except:
    print('')
")
    
    if [ -z "$JOB_ID" ]; then
        log "WARNING: Failed to extract job ID for batch $BATCH_NUM"
        log "Response: $JOB_BODY"
        FAILED_BATCHES="$FAILED_BATCHES $BATCH_NUM"
        continue
    fi
    
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    log "Batch $BATCH_NUM: Successfully created fetch job with ID: $JOB_ID"
done

log "Fetch job summary: $SUCCESS_COUNT/$BATCH_NUM batches succeeded"

if [ -n "$FAILED_BATCHES" ]; then
    log "WARNING: Failed batches:$FAILED_BATCHES"
fi

if [ "$SUCCESS_COUNT" -eq 0 ]; then
    log "ERROR: All fetch job batches failed"
    exit 1
fi

# Step 4: Trigger economic data update (FRED)
log "Triggering daily economic data update..."
ECO_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -X POST "${BASE_URL}/v1/daily-economic-update" \
  -H "Content-Type: application/json" \
  -H "X-Cron-Secret: ${CRON_SECRET_TOKEN}" \
  -d '{"dry_run": false}' \
  --max-time 60)

ECO_HTTP_STATUS=$(echo "$ECO_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
ECO_BODY=$(echo "$ECO_RESPONSE" | sed '/HTTP_STATUS:/d')

if [ "$ECO_HTTP_STATUS" != "200" ]; then
    log "WARNING: Failed to update economic data. HTTP Status: $ECO_HTTP_STATUS"
    log "Response: $ECO_BODY"
    # Don't exit with error, as stock data update was successful
else
    log "Successfully updated economic data"
    log "Response: $ECO_BODY"
fi

log "Daily stock data update job initiated successfully"
