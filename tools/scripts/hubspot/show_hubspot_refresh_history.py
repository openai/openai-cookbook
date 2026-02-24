#!/usr/bin/env python3
"""
Show HubSpot refresh history — display logged --refresh-deals-only runs and evolution.

Usage:
    python tools/scripts/hubspot/show_hubspot_refresh_history.py
    python tools/scripts/hubspot/show_hubspot_refresh_history.py --period 2026-02
    python tools/scripts/hubspot/show_hubspot_refresh_history.py --limit 10
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB = "tools/data/facturacion_hubspot.db"


def main():
    parser = argparse.ArgumentParser(
        description="Show HubSpot deals refresh history and evolution"
    )
    parser.add_argument("--db", default=str(REPO_ROOT / DEFAULT_DB), help="SQLite DB path")
    parser.add_argument("--period", type=str, help="Filter by period (e.g. 2026-02)")
    parser.add_argument("--limit", type=int, default=20, help="Max rows (default: 20)")
    args = parser.parse_args()

    from tools.utils.hubspot_refresh_logger import get_hubspot_refresh_history

    rows = get_hubspot_refresh_history(
        db_path=args.db,
        period=args.period,
        limit=args.limit,
    )
    if not rows:
        print("No HubSpot refresh logs found.")
        print("Run: python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year 2026 --month 2")
        return

    print(f"HubSpot refresh history (last {len(rows)} runs)\n")
    print(f"{'timestamp':<28} {'period':<8} {'deals':>6} {'+added':>7} {'~updated':>8} {'-removed':>8}")
    print("-" * 75)
    for r in rows:
        ts = (r.get("timestamp") or "")[:26]
        period = (r.get("period") or "-")[:7]
        deals = r.get("deal_count", 0)
        added = r.get("added_count", 0)
        updated = r.get("updated_count", 0)
        removed = r.get("removed_count", 0)
        print(f"{ts:<28} {period:<8} {deals:>6} {added:>7} {updated:>8} {removed:>8}")

    if rows and (rows[0].get("added_ids") or rows[0].get("removed_ids")):
        print("\nLatest run details:")
        r = rows[0]
        if r.get("added_ids"):
            print(f"  Added: {', '.join(r['added_ids'][:15])}{'...' if len(r['added_ids']) > 15 else ''}")
        if r.get("removed_ids"):
            print(f"  Removed: {', '.join(r['removed_ids'][:15])}{'...' if len(r['removed_ids']) > 15 else ''}")
        if r.get("updated_ids"):
            print(f"  Updated: {', '.join(r['updated_ids'][:15])}{'...' if len(r['updated_ids']) > 15 else ''}")
    print()


if __name__ == "__main__":
    main()
