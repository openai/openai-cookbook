#!/usr/bin/env bash
# Display one real Decisions request and response; no evaluation or installation.
set +x
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
trap 'unset OPENAI_API_KEY' EXIT
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  if ! read -r -s -p "Paste API key (hidden): " OPENAI_API_KEY; then
    printf '\nNo key supplied; no API request was made.\n'
    exit 1
  fi
  printf '\n'
fi
if [[ -z "$OPENAI_API_KEY" ]]; then
  echo "No key supplied; no API request was made."
  exit 1
fi
export OPENAI_API_KEY
echo "Making one billable Decisions request. No automatic retries."
python3 "$script_dir/run_customer_request_routing.py" --preview
