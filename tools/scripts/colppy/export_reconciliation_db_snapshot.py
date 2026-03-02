#!/usr/bin/env python3
"""
Export Colppy ↔ HubSpot Reconciliation Snapshot for Plugin
==========================================================
Runs reconciliation for each requested month and exports JSON to the plugin docs folder.
Requires colppy_export.db and facturacion_hubspot.db (with deals_any_stage populated).

For WRONG_STAGE detection, run HubSpot refresh first:
  python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year YYYY --month M --fetch-wrong-stage

Usage:
  python tools/scripts/colppy/export_reconciliation_db_snapshot.py --months 14
  python tools/scripts/colppy/export_reconciliation_db_snapshot.py --year 2025 --month 4
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_COLPPY_DB = REPO_ROOT / "tools/data/colppy_export.db"
DEFAULT_HUBSPOT_DB = REPO_ROOT / "tools/data/facturacion_hubspot.db"
DEFAULT_OUTPUT = REPO_ROOT / "plugins/colppy-revops/docs/colppy_hubspot_reconciliation_snapshot.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export reconciliation snapshot for plugin")
    parser.add_argument("--months", type=int, default=14, help="Number of months to export (from current)")
    parser.add_argument("--year", type=str, help="Single year (use with --month)")
    parser.add_argument("--month", type=int, help="Single month 1-12 (use with --year)")
    parser.add_argument("--colppy-db", type=Path, default=DEFAULT_COLPPY_DB)
    parser.add_argument("--hubspot-db", type=Path, default=DEFAULT_HUBSPOT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()

    if not args.colppy_db.exists():
        print(f"Error: Colppy DB not found: {args.colppy_db}")
        return 1
    if not args.hubspot_db.exists():
        print(f"Error: HubSpot DB not found: {args.hubspot_db}")
        return 1

    from tools.scripts.colppy.reconcile_colppy_hubspot_db_only import run_reconciliation_data

    if args.year and args.month:
        months_to_export = [(args.year, args.month)]
    else:
        now = datetime.now()
        months_to_export = []
        for i in range(args.months):
            y = now.year
            m = now.month - i
            while m <= 0:
                m += 12
                y -= 1
            months_to_export.append((str(y), m))

    reports = {}
    for year, month in months_to_export:
        month_key = f"{year}-{month:02d}"
        if not args.quiet:
            print(f"Reconciling {month_key}...")
        data = run_reconciliation_data(year, month, args.colppy_db, args.hubspot_db)
        if data:
            reports[month_key] = data
            if not args.quiet:
                s = data["summary"]
                print(f"  {s['colppy_total']} Colppy, {s['hubspot_total']} HubSpot, match={s['match_count']}")
        else:
            if not args.quiet:
                print(f"  Skipped (no data)")

    snapshot = {
        "metadata": {
            "exported_at": datetime.now().isoformat(),
            "source": "reconcile_colppy_hubspot_db_only",
            "colppy_db": str(args.colppy_db),
            "hubspot_db": str(args.hubspot_db),
            "months_included": list(reports.keys()),
        },
        "reports_by_month": reports,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    if not args.quiet:
        print(f"\nExported {len(reports)} months to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
