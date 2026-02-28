#!/bin/bash
# Build Claude plugin zip. Creates colppy-ceo-assistant/ as root in zip.
# Output: ../../tools/outputs/colppy-ceo-assistant-plugin-full.zip
#
# Usage:
#   ./publish.sh           # Zip only; if colppy_export.db exists, refresh snapshot first
#   ./publish.sh --refresh # Full refresh: MySQL → SQLite → snapshot → zip (requires VPN)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGINS_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$(cd "$REPO_ROOT/tools/outputs" && pwd)"
ZIP_NAME="colppy-ceo-assistant-plugin-full.zip"
DB_PATH="$REPO_ROOT/tools/data/colppy_export.db"

if [ "$1" = "--refresh" ]; then
  echo "Exporting Colppy MySQL → colppy_export.db (requires VPN)..."
  cd "$REPO_ROOT"
  python tools/scripts/colppy/export_colppy_to_sqlite.py
  echo ""
fi

cd "$REPO_ROOT"

if [ -f "$DB_PATH" ]; then
  echo "Refreshing snapshot JSON from colppy_export.db..."
  python "$REPO_ROOT/tools/scripts/colppy/export_reconciliation_snapshot.py" --months 62
  echo "Exporting Colppy id_empresa → CUIT snapshot..."
  python "$REPO_ROOT/tools/scripts/colppy/export_colppy_cuit_snapshot.py" --quiet
else
  echo "colppy_export.db not found; skipping snapshot refresh (use bundled snapshot if present)"
fi

HUBSPOT_DB="$REPO_ROOT/tools/data/facturacion_hubspot.db"
if [ -f "$DB_PATH" ] && [ -f "$HUBSPOT_DB" ]; then
  echo "Exporting Colppy–HubSpot reconciliation snapshot..."
  python "$REPO_ROOT/tools/scripts/colppy/export_reconciliation_db_snapshot.py" --months 14 --quiet
else
  echo "colppy_export.db or facturacion_hubspot.db not found; skipping reconciliation snapshot"
fi

echo "Building plugin zip..."
cd "$PLUGINS_DIR"
# Exclude colppy_export.db (35MB) from plugin zip to stay under 50MB upload limit
# DB_IN_PLUGIN: path inside plugin dir; if a symlink/copy exists there, move aside before zip
DB_IN_PLUGIN="$SCRIPT_DIR/tools/data/colppy_export.db"
TMP_BAK="$REPO_ROOT/tools/data/colppy_export_plugin_bak.db"
if [ -f "$DB_IN_PLUGIN" ]; then
  mv "$DB_IN_PLUGIN" "$TMP_BAK"
fi
zip -r "$OUTPUT_DIR/$ZIP_NAME" colppy-ceo-assistant -x "*.git*" -x "colppy-ceo-assistant/publish.sh" -x "*.DS_Store" -x "colppy-ceo-assistant/mcp/node_modules/*"
if [ -f "$TMP_BAK" ]; then
  mv "$TMP_BAK" "$DB_IN_PLUGIN"
fi
echo "Created: $OUTPUT_DIR/$ZIP_NAME"
