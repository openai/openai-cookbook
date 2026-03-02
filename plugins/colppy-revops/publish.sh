#!/bin/bash
# Build colppy-revops plugin zip for Claude Cowork upload.
# Optionally refreshes reconciliation snapshots from local DBs.
# Output: ../../tools/outputs/colppy-revops-plugin-full.zip
#
# Usage:
#   ./publish.sh           # Zip only; if colppy_export.db exists, refresh snapshots first
#   ./publish.sh --refresh # Full refresh: MySQL → SQLite → snapshot → zip (requires VPN)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGINS_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/tools/outputs"
ZIP_NAME="colppy-revops-plugin-full.zip"
DB_PATH="$REPO_ROOT/tools/data/colppy_export.db"
HUBSPOT_DB="$REPO_ROOT/tools/data/facturacion_hubspot.db"

mkdir -p "$OUTPUT_DIR"

if [ "$1" = "--refresh" ]; then
  echo "Exporting Colppy MySQL → colppy_export.db (requires VPN)..."
  cd "$REPO_ROOT"
  python tools/scripts/colppy/export_colppy_to_sqlite.py
  echo ""
fi

cd "$REPO_ROOT"

if [ -f "$DB_PATH" ]; then
  echo "Refreshing reconciliation snapshot JSON from colppy_export.db..."
  python "$REPO_ROOT/tools/scripts/colppy/export_reconciliation_snapshot.py" --months 62
  echo "Exporting Colppy id_empresa → CUIT snapshot..."
  python "$REPO_ROOT/tools/scripts/colppy/export_colppy_cuit_snapshot.py" --quiet
else
  echo "colppy_export.db not found; skipping snapshot refresh (use bundled snapshot if present)"
fi

if [ -f "$DB_PATH" ] && [ -f "$HUBSPOT_DB" ]; then
  echo "Exporting Colppy–HubSpot reconciliation snapshot..."
  python "$REPO_ROOT/tools/scripts/colppy/export_reconciliation_db_snapshot.py" --months 14 --quiet
else
  echo "colppy_export.db or facturacion_hubspot.db not found; skipping reconciliation snapshot"
fi

echo "Building plugin zip..."
cd "$PLUGINS_DIR"
zip -r "$OUTPUT_DIR/$ZIP_NAME" colppy-revops \
  -x "*.git*" \
  -x "colppy-revops/publish.sh" \
  -x "*.DS_Store"
echo "Created: $OUTPUT_DIR/$ZIP_NAME"
