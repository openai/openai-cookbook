#!/bin/bash

# Test script for Outline API after getting new token
# Usage: ./test_outline_api.sh YOUR_NEW_OUTLINE_TOKEN

if [ -z "$1" ]; then
    echo "Usage: $0 YOUR_OUTLINE_API_TOKEN"
    echo "Example: $0 outline_live_abc123..."
    exit 1
fi

OUTLINE_TOKEN="$1"

echo "🔍 Testing Outline API with new token..."
echo "Token: ${OUTLINE_TOKEN:0:20}..."
echo ""

echo "Test 1: List Collections"
echo "========================"
curl -sS -X POST 'https://dev.fellow.wiki/api/collections.list' \
  -H 'Authorization: Bearer '"$OUTLINE_TOKEN"'' \
  -H 'Content-Type: application/json' \
  -d '{}' | jq .

echo ""
echo "Test 2: List Documents"  
echo "======================"
curl -sS -X POST 'https://dev.fellow.wiki/api/documents.list' \
  -H 'Authorization: Bearer '"$OUTLINE_TOKEN"'' \
  -H 'Content-Type: application/json' \
  -d '{}' | jq .

echo ""
echo "If both return JSON data (not errors), your token is working!"
