#!/bin/bash

# Make sure to create a .env file with your Intercom API token first
# echo "INTERCOM_ACCESS_TOKEN=your_token_here" > .env

# Export last 7 days of conversations
node src/index.js --from $(date -v-7d +%Y-%m-%d) --to $(date +%Y-%m-%d) --output recent-conversations.csv

# Export a specific date range
# node src/index.js --from 2023-01-01 --to 2023-03-31 --output q1-conversations.csv

# Export with a limit (for testing)
# node src/index.js --from 2023-01-01 --to $(date +%Y-%m-%d) --limit 10 --output sample-conversations.csv 