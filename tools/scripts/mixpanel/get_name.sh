#!/bin/bash
# Simple wrapper to get just the name of a user from Mixpanel
# Usage: ./get_name.sh jonetto@colppy.com

if [ -z "$1" ]; then
  echo "Usage: ./get_name.sh <email>"
  echo "Example: ./get_name.sh jonetto@colppy.com"
  exit 1
fi

python3 get_user_name.py "$1" | grep "^Name:" | cut -d ':' -f 2- | xargs 