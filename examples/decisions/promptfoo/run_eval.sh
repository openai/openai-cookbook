#!/usr/bin/env bash
# Run once with visible output. No installation, retries, cloud login, or sharing.
set -euo pipefail
cd "$(dirname "$0")"
export PROMPTFOO_DISABLE_TELEMETRY=1
export PROMPTFOO_DISABLE_UPDATE=1
export PROMPTFOO_CONFIG_DIR="$PWD/.local"

if [[ -f .generated/results.json ]]; then
  echo "An exported run already exists. Inspect it before starting another paid run."
  echo "To summarize without API calls: python3 routing_eval.py summarize"
  exit 1
fi
if [[ ! -x node_modules/.bin/promptfoo ]]; then
  echo "Install the pinned dependency first: npm ci"
  exit 1
fi
python3 routing_eval.py prepare
npm run validate
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  read -r -s -p "Paste API key (hidden): " OPENAI_API_KEY
  printf '\n'
fi
if [[ -z "$OPENAI_API_KEY" ]]; then
  echo "No key supplied; no API requests were made."
  exit 1
fi
export OPENAI_API_KEY
trap 'unset OPENAI_API_KEY' EXIT
echo "Starting 120 sequential billable Decisions requests. No automatic retries."
set +e
npm run eval
eval_status=$?
set -e
unset OPENAI_API_KEY
# Promptfoo uses 100 for assertion failures; preserve and summarize those failures.
if [[ "$eval_status" != 0 && "$eval_status" != 100 ]]; then
  echo "Promptfoo stopped with exit code $eval_status. Inspect the error before retrying."
  exit "$eval_status"
fi
python3 routing_eval.py summarize
echo "Complete. Open .generated/report.html to see test messages, responses, and grades."
