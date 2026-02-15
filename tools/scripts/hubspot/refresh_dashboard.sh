#!/usr/bin/env bash
#
# Refresh Colppy MRR dashboard: rebuild DB from billing + HubSpot, then regenerate HTML.
#
# Prerequisites:
#   - tools/outputs/facturacion.csv must exist and be up to date (export from billing).
#   - HUBSPOT_API_KEY (or HUBSPOT_ACCESS_TOKEN) in .env or environment.
#
# Usage:
#   ./tools/scripts/hubspot/refresh_dashboard.sh              # Full: build + populate + dashboard
#   ./tools/scripts/hubspot/refresh_dashboard.sh --dashboard-only   # Only regenerate HTML from existing DB
#   ./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs  # Write HTML to docs/ (default)
#
# See tools/docs/HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md section 9.
#
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

FACTURACION="${FACTURACION:-tools/outputs/facturacion.csv}"
DB="${DB:-tools/outputs/facturacion_hubspot.db}"
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

echo "=== Colppy dashboard refresh ==="
echo "  DB: $DB"
echo "  Output: $OUTPUT_DIR/"
echo "  Mode: $([ "$DASHBOARD_ONLY" = true ] && echo 'dashboard only' || echo 'full')"
echo ""

if [ "$DASHBOARD_ONLY" != true ]; then
  if [ ! -f "$FACTURACION" ]; then
    echo "ERROR: Facturacion file not found: $FACTURACION" >&2
    echo "Export billing to $FACTURACION or run with --dashboard-only to only regenerate HTML." >&2
    exit 1
  fi
  echo "1/4 Build facturacion–HubSpot mapping..."
  python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --facturacion "$FACTURACION" --db "$DB" --csv
  echo "2/4 Populate deal associations..."
  python tools/scripts/hubspot/populate_deal_associations.py --db "$DB"
  echo "3/4 Populate accountant deals (incl. churned)..."
  python tools/scripts/hubspot/populate_accountant_deals.py --db "$DB"
else
  if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found: $DB" >&2
    echo "Run without --dashboard-only first, or ensure $DB exists." >&2
    exit 1
  fi
  echo "Skipping build and populate (--dashboard-only)."
fi

echo "Regenerate dashboards..."
mkdir -p "$OUTPUT_DIR"
python tools/scripts/hubspot/analyze_accountant_mrr_matrix.py --db "$DB" --html "$OUTPUT_DIR/mrr_dashboard.html"
python tools/scripts/hubspot/analyze_icp_dashboard.py --html "$OUTPUT_DIR/icp_dashboard.html"

echo ""
echo "Done. Dashboards written to $OUTPUT_DIR/mrr_dashboard.html and $OUTPUT_DIR/icp_dashboard.html"
