#!/bin/bash
# Full refresh from Jan 2025: HubSpot deals (all months) + reconciliation export + plugin publish.
# Run in background. Check progress: tail -f /tmp/full_refresh_publish.log
#
# Usage: ./tools/scripts/run_full_refresh_and_publish.sh

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG="/tmp/full_refresh_publish.log"
cd "$REPO_ROOT"

echo "=== Full refresh from Jan 2025 ===" | tee "$LOG"
echo "Started at: $(date '+%Y-%m-%dT%H:%M:%S')" | tee -a "$LOG"

# HubSpot refresh: Jan 2025 through Feb 2026 (14 months)
MONTHS="2025-01 2025-02 2025-03 2025-04 2025-05 2025-06 2025-07 2025-08 2025-09 2025-10 2025-11 2025-12 2026-01 2026-02"
for ym in $MONTHS; do
  year="${ym%-*}"
  month="${ym#*-}"
  echo "" | tee -a "$LOG"
  echo "[$(date +%H:%M:%S)] Refreshing HubSpot $ym..." | tee -a "$LOG"
  python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py \
    --refresh-deals-only --year "$year" --month "$month" --fetch-wrong-stage 2>&1 | tee -a "$LOG" || true
done

echo "" | tee -a "$LOG"
echo "[$(date +%H:%M:%S)] Exporting reconciliation snapshot..." | tee -a "$LOG"
python tools/scripts/colppy/export_reconciliation_db_snapshot.py --months 14 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "[$(date +%H:%M:%S)] Publishing plugin..." | tee -a "$LOG"
cd "$REPO_ROOT/plugins/colppy-ceo-assistant" && ./publish.sh 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "=== DONE at $(date '+%Y-%m-%dT%H:%M:%S') ===" | tee -a "$LOG"
echo "Plugin zip: $REPO_ROOT/tools/outputs/colppy-ceo-assistant-plugin-full.zip" | tee -a "$LOG"
