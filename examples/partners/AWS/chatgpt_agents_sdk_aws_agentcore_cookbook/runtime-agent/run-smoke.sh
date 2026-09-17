#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
if [[ $# -gt 0 ]]; then
  payload="$1"
  [[ "$payload" = /* ]] || payload="$PWD/$payload"
else
  payload="$script_dir/smoke-search-flights.json"
fi
export COOKBOOK_FORCE_LOCAL_TOOLS=1
COOKBOOK_EVENT="$(cd "$script_dir" && uv run python demo_date.py --payload "$payload")"
export COOKBOOK_EVENT
cd "$script_dir"
uv run python agent.py
