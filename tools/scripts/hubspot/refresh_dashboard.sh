#!/usr/bin/env bash
#
# Refresh Colppy MRR dashboard: rebuild DB from billing + HubSpot, then regenerate HTML.
#
# Prerequisites:
#   - For full refresh: tools/outputs/facturacion.csv (or any facturacion*.csv there). Auto-detected.
#   - For HTML-only refresh: tools/data/facturacion_hubspot.db (or any facturacion*.db there). Auto-detected.
#   - HUBSPOT_API_KEY (or HUBSPOT_ACCESS_TOKEN) in .env or environment.
#
# Usage:
#   ./tools/scripts/hubspot/refresh_dashboard.sh   # Full if CSV found; else HTML-only from existing DB. No prompts.
#   ./tools/scripts/hubspot/refresh_dashboard.sh --dashboard-only   # Only regenerate HTML from existing DB
#   ./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs   # Write HTML to docs/ (default)
#
# See tools/docs/HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md section 9.
#
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

DB="${DB:-tools/data/facturacion_hubspot.db}"
OUTPUT_DIR="${OUTPUT_DIR:-docs}"
DASHBOARD_ONLY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --dashboard-only)
      DASHBOARD_ONLY=true
      shift
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --facturacion)
      FACTURACION="$2"
      shift 2
      ;;
    --db)
      DB="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--dashboard-only] [--output-dir DIR] [--facturacion PATH] [--db PATH]"
      echo "  --dashboard-only  Skip build and populate; only regenerate dashboard HTML from existing DB."
      echo "  --output-dir DIR  Write mrr_dashboard.html and icp_dashboard.html to DIR (default: docs)."
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Auto-detect facturacion if not set: default path, then any facturacion*.csv in tools/outputs
if [ -z "${FACTURACION:-}" ]; then
  if [ -f "tools/outputs/facturacion.csv" ]; then
    FACTURACION="tools/outputs/facturacion.csv"
  else
    SHORTLIST=$(find tools/outputs -maxdepth 1 -name 'facturacion*.csv' 2>/dev/null | head -1)
    if [ -n "$SHORTLIST" ]; then
      FACTURACION="$SHORTLIST"
    fi
  fi
fi

# Auto-detect DB if default missing: any facturacion*.db in tools/outputs
if [ ! -f "$DB" ]; then
  FALLBACK_DB=$(find tools/outputs -maxdepth 1 -name 'facturacion*.db' 2>/dev/null | head -1)
  if [ -n "$FALLBACK_DB" ]; then
    DB="$FALLBACK_DB"
  fi
fi

# If no CSV or --dashboard-only: refresh HTML from existing DB only
if [ "$DASHBOARD_ONLY" = true ] || [ -z "${FACTURACION:-}" ] || [ ! -f "$FACTURACION" ]; then
  DASHBOARD_ONLY=true
fi

echo "=== Colppy dashboard refresh ==="
echo "  DB: $DB"
echo "  Output: $OUTPUT_DIR/"
echo "  Mode: $([ "$DASHBOARD_ONLY" = true ] && echo 'dashboard only' || echo 'full')"
if [ "$DASHBOARD_ONLY" != true ]; then
  echo "  Facturacion: $FACTURACION"
fi
echo ""

if [ ! -f "$DB" ]; then
  if [ "$DASHBOARD_ONLY" = true ]; then
    echo "No DB at $DB. Put facturacion.csv in tools/outputs/ and run this script for a full refresh." >&2
    exit 1
  fi
  # Full run without existing DB: we need CSV
  if [ -z "${FACTURACION:-}" ] || [ ! -f "$FACTURACION" ]; then
    echo "No facturacion CSV and no DB. Put facturacion.csv in tools/outputs/ for a full refresh." >&2
    exit 1
  fi
fi

if [ "$DASHBOARD_ONLY" != true ]; then
  echo "1/4 Build facturacion–HubSpot mapping..."
  python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --facturacion "$FACTURACION" --db "$DB" --csv
  echo "2/4 Populate deal associations..."
  python tools/scripts/hubspot/populate_deal_associations.py --db "$DB"
  echo "3/4 Populate accountant deals (incl. churned)..."
  python tools/scripts/hubspot/populate_accountant_deals.py --db "$DB"
else
  echo "Skipping build and populate (using existing DB)."
fi

echo "Regenerate dashboards..."
mkdir -p "$OUTPUT_DIR"
python tools/scripts/hubspot/analyze_accountant_mrr_matrix.py --db "$DB" --html "$OUTPUT_DIR/mrr_dashboard.html"
python tools/scripts/hubspot/analyze_icp_dashboard.py --html "$OUTPUT_DIR/icp_dashboard.html"

echo ""
echo "Done. Dashboards written to $OUTPUT_DIR/mrr_dashboard.html and $OUTPUT_DIR/icp_dashboard.html"
echo ""
echo "To ensure the browser shows this run: open the HTML file, then hard refresh (Ctrl+Shift+R or Cmd+Shift+R)."
echo "The MRR dashboard shows a 'Generated: <date time>' line under the title; if that matches this run, the view is up to date."
