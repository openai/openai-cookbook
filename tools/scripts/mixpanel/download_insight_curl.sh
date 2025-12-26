#!/bin/bash
# Direct download of Mixpanel Insight Report using curl
# No Python API wrapper needed - just curl and jq

set -e

BOOKMARK_ID="${1:-72369475}"
OUTPUT_FILE="${2:-insight_report_${BOOKMARK_ID}.csv}"

# Load credentials from .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep MIXPANEL | xargs)
fi

if [ -z "$MIXPANEL_USERNAME" ] || [ -z "$MIXPANEL_PASSWORD" ] || [ -z "$MIXPANEL_PROJECT_ID" ]; then
    echo "❌ Error: Mixpanel credentials not found in .env file"
    echo "   Required: MIXPANEL_USERNAME, MIXPANEL_PASSWORD, MIXPANEL_PROJECT_ID"
    exit 1
fi

echo "📊 Downloading insight report (bookmark: $BOOKMARK_ID)..."

# Try endpoint 1: /api/2.0/bookmark/view (GET)
URL="https://mixpanel.com/api/2.0/bookmark/view"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    -u "$MIXPANEL_USERNAME:$MIXPANEL_PASSWORD" \
    -H "Content-Type: application/json" \
    "$URL?bookmark_id=$BOOKMARK_ID&project_id=$MIXPANEL_PROJECT_ID" 2>&1)

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Successfully retrieved report data"
    echo "$BODY" | python3 -c "
import sys
import json
import csv
import io

data = json.load(sys.stdin)

# Convert to CSV
if isinstance(data, list):
    rows = data
elif isinstance(data, dict):
    if 'data' in data:
        rows = data['data'] if isinstance(data['data'], list) else [data['data']]
    else:
        rows = [data]
else:
    rows = [{'result': str(data)}]

if rows:
    all_keys = set()
    for row in rows:
        if isinstance(row, dict):
            all_keys.update(row.keys())
    
    fieldnames = sorted(all_keys)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for row in rows:
        if isinstance(row, dict):
            clean_row = {k: str(v) if v is not None else '' for k, v in row.items()}
            writer.writerow(clean_row)
    
    print(output.getvalue())
" > "$OUTPUT_FILE"
    
    echo "✅ Report saved to: $OUTPUT_FILE"
    echo "📁 Full path: $(cd "$(dirname "$OUTPUT_FILE")" && pwd)/$(basename "$OUTPUT_FILE")"
    exit 0
fi

# Try endpoint 2: /api/query/insights (POST)
echo "⚠️  First endpoint failed (HTTP $HTTP_CODE), trying alternative endpoint..."
URL="https://mixpanel.com/api/query/insights"

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    -X POST \
    -u "$MIXPANEL_USERNAME:$MIXPANEL_PASSWORD" \
    -H "Content-Type: application/json" \
    -d "{\"project_id\":\"$MIXPANEL_PROJECT_ID\",\"bookmark_id\":\"$BOOKMARK_ID\"}" \
    "$URL" 2>&1)

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Successfully retrieved report data"
    echo "$BODY" | python3 -c "
import sys
import json
import csv
import io

data = json.load(sys.stdin)

# Convert to CSV
if isinstance(data, list):
    rows = data
elif isinstance(data, dict):
    if 'data' in data:
        rows = data['data'] if isinstance(data['data'], list) else [data['data']]
    else:
        rows = [data]
else:
    rows = [{'result': str(data)}]

if rows:
    all_keys = set()
    for row in rows:
        if isinstance(row, dict):
            all_keys.update(row.keys())
    
    fieldnames = sorted(all_keys)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for row in rows:
        if isinstance(row, dict):
            clean_row = {k: str(v) if v is not None else '' for k, v in row.items()}
            writer.writerow(clean_row)
    
    print(output.getvalue())
" > "$OUTPUT_FILE"
    
    echo "✅ Report saved to: $OUTPUT_FILE"
    echo "📁 Full path: $(cd "$(dirname "$OUTPUT_FILE")" && pwd)/$(basename "$OUTPUT_FILE")"
else
    echo "❌ Error: Failed to download report (HTTP $HTTP_CODE)"
    echo "Response: $BODY"
    exit 1
fi






