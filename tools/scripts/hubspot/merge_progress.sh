#!/bin/bash
# Merge progress monitor: counts, last merges, next 5 pending.
# Usage: ./merge_progress.sh [interval_seconds] [--no-clear]
#   interval 0 = run once and exit
#   --no-clear = don't clear screen (useful when clear hides output)
#   Press Ctrl+C to stop the loop.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"
DB="$REPO_ROOT/tools/outputs/facturacion_hubspot.db"
INTERVAL="${1:-5}"
NO_CLEAR=""
[[ "${2:-}" == "--no-clear" || "${2:-}" == "-n" ]] && NO_CLEAR=1

run_once() {
  if [[ -n "$NO_CLEAR" ]]; then
    echo "----------------------------------------"
  else
    clear
  fi
  echo "=== Merge progress $(date +%H:%M:%S) ==="
  sqlite3 "$DB" "
    SELECT outcome, COUNT(*) FROM edit_logs 
    WHERE script='merge_duplicates_by_cuit' GROUP BY outcome;
  "
  sqlite3 "$DB" "
    SELECT 'Recent (60s): ' || COUNT(*) || ' | Total logged: ' || (SELECT COUNT(*) FROM edit_logs WHERE script='merge_duplicates_by_cuit' AND outcome IN ('success','skipped','failed'))
    FROM edit_logs WHERE script='merge_duplicates_by_cuit' AND outcome IN ('success','skipped') AND datetime(timestamp) > datetime('now', '-1 minute');
  "
  echo ""
  python3 "$SCRIPT_DIR/merge_next_pending.py" --stats "$DB" 2>/dev/null || echo "Processed: ?/? | Pending: ? | (error)"
  echo ""
  echo "=== Last 10 actions (OK=merged, SKIP=already merged) ==="
  sqlite3 "$DB" "
    SELECT substr(timestamp,12,8) || ' | ' || 
      CASE outcome WHEN 'success' THEN 'OK ' ELSE 'SKIP' END || ' | ' || 
      customer_cuit || ' | ' || substr(COALESCE(company_name,''),1,28) || ' <- ' || company_id_secondary
    FROM edit_logs WHERE script='merge_duplicates_by_cuit' AND outcome IN ('success','skipped')
    ORDER BY id DESC LIMIT 10;
  "
  echo ""
  echo "=== Next 5 pending ==="
  python3 "$SCRIPT_DIR/merge_next_pending.py" "$DB" 5 || echo "  (error)"
}

if [[ "$INTERVAL" == "0" ]]; then
  run_once
else
  while true; do
    run_once
    sleep "$INTERVAL"
  done
fi
