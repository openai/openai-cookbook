#!/bin/bash

# Basic analysis of exported conversations
node src/analyze.js --file intercom-conversations.csv

# Advanced analysis with custom limits
# node src/analyze.js --file intercom-conversations.csv --top-users 10 --top-admins 8 