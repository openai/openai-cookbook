#!/usr/bin/env bash
# Display a small live routing batch; no evaluation framework or installation.
set +x
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  exec python3 "$script_dir/run_customer_request_routing.py" "$@"
fi
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
echo "Starting live routing demo: 10 public customer-support examples, or one with --message. No automatic retries."
python3 "$script_dir/run_customer_request_routing.py" "$@"
