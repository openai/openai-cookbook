#!/usr/bin/env python3
"""
Show reconciliation history — display logged runs and record-level changes.

Usage:
    python tools/scripts/colppy/show_reconciliation_history.py
    python tools/scripts/colppy/show_reconciliation_history.py --diff
    python tools/scripts/colppy/show_reconciliation_history.py --diff --script reconcile_colppy_hubspot
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB = "tools/data/facturacion_hubspot.db"


def main():
    parser = argparse.ArgumentParser(description="Show reconciliation run history and record-level changes")
    parser.add_argument("--db", default=str(REPO_ROOT / DEFAULT_DB), help="SQLite DB path")
    parser.add_argument("--script", type=str, help="Filter by script name")
    parser.add_argument("--type", "--reconciliation-type", dest="reconciliation_type", type=str, help="Filter by reconciliation_type")
    parser.add_argument("--period", type=str, help="Filter by period (e.g. 2026-02)")
    parser.add_argument("--limit", type=int, default=20, help="Max rows (default: 20)")
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Compare latest vs previous run: show record-level status (fixed, new, unchanged, regression)",
    )
    parser.add_argument(
        "--filter",
        type=str,
        metavar="STATUS",
        help="With --diff: only show records with given status (comma-separated: fixed,new,unchanged,regression)",
    )
    args = parser.parse_args()

    if args.diff:
        from tools.utils.reconciliation_logger import get_reconciliation_diff

        diff = get_reconciliation_diff(
            db_path=args.db,
            script=args.script,
            reconciliation_type=args.reconciliation_type,
            period=args.period,
        )
        if not diff:
            print("Need at least 2 runs to show diff. Run a reconciliation script again.")
            return
        if not diff.get("prev_has_record_ids"):
            print("Note: Previous run had no record-level ids (logged before record tracking was added).")
            print("All records show as 'new'. Run reconciliation again to get accurate diff on next run.\n")
        s = diff["summary"]
        print("Reconciliation diff (latest vs previous run)\n")
        print(f"Current:  {diff['current_run']}")
        print(f"Previous: {diff['previous_run']}\n")
        print("Summary:")
        print(f"  fixed:     {s['fixed']} (was in only, now in match)")
        print(f"  new:       {s['new']} (didn't exist in previous run)")
        print(f"  unchanged: {s['unchanged']}")
        print(f"  regression: {s['regression']} (was in match, now in only)")
        print(f"  removed:   {s['removed']} (in previous run, not in current)")
        print()
        status_filter = None
        if args.filter:
            status_filter = {s.strip() for s in args.filter.split(",") if s.strip()}
        print(f"{'id_empresa':<12} {'bucket':<16} {'status':<12}")
        print("-" * 42)
        for r in diff["records"]:
            if status_filter and r["status"] not in status_filter:
                continue
            print(f"{r['id']:<12} {r['bucket']:<16} {r['status']:<12}")
        if diff["removed_ids"]:
            print()
            print("Removed (in previous, not in current):", ", ".join(diff["removed_ids"]))
        return

    from tools.utils.reconciliation_logger import get_reconciliation_history

    rows = get_reconciliation_history(
        db_path=args.db,
        script=args.script,
        reconciliation_type=args.reconciliation_type,
        period=args.period,
        limit=args.limit,
    )
    if not rows:
        print("No reconciliation logs found.")
        if args.script or args.reconciliation_type or args.period:
            print("Try without filters or run a reconciliation script first.")
        return

    print(f"Reconciliation history (last {len(rows)} runs)\n")
    print(f"{'timestamp':<28} {'script':<35} {'type':<40} {'period':<8} {'match':>6} {'A_total':>8} {'B_total':>8} {'A_only':>7} {'B_only':>7}")
    print("-" * 155)
    for r in rows:
        ts = (r.get("timestamp") or "")[:26]
        script = (r.get("script") or "")[:34]
        rtype = (r.get("reconciliation_type") or "")[:39]
        period = (r.get("period") or "-")[:7]
        match = r.get("match_count", 0)
        a_total = r.get("source_a_total", 0)
        b_total = r.get("source_b_total", 0)
        a_only = r.get("source_a_only_count", 0)
        b_only = r.get("source_b_only_count", 0)
        print(f"{ts:<28} {script:<35} {rtype:<40} {period:<8} {match:>6} {a_total:>8} {b_total:>8} {a_only:>7} {b_only:>7}")
    print()
    if rows and rows[0].get("source_metadata"):
        print("Latest source_metadata:", rows[0].get("source_metadata"))
    extra = rows[0].get("extra") if rows else {}
    if isinstance(extra, dict) and any(k.startswith("match_ok_") or k.startswith("colppy_only_") or k.startswith("hubspot_") for k in extra):
        print()
        print("Latest run — bucket breakdown (from extra):")
        print("-" * 50)
        # Match breakdown
        if "match_ok_count" in extra:
            print(f"  MATCH (id_empresa + close_date + id_plan align): {extra.get('match_ok_count', 0)}")
        if "match_ok_id_plan_blank_count" in extra:
            print(f"  MATCH but id_plan blank: {extra.get('match_ok_id_plan_blank_count', 0)}")
        if "match_ok_id_plan_hubspot_has_count" in extra:
            print(f"  MATCH but id_plan HubSpot has (Colppy blank): {extra.get('match_ok_id_plan_hubspot_has_count', 0)}")
        if "match_ok_plan_mismatch_count" in extra:
            print(f"  MATCH but id_plan MISMATCH: {extra.get('match_ok_plan_mismatch_count', 0)}")
        if "match_fecha_primer_pago_blank_count" in extra:
            print(f"  MATCH but fecha_primer_pago blank: {extra.get('match_fecha_primer_pago_blank_count', 0)}")
        if "match_close_date_mismatch_count" in extra:
            print(f"  MATCH but close_date MISMATCH: {extra.get('match_close_date_mismatch_count', 0)}")
        # Colppy unmatched
        if "colppy_only_wrong_close_date_count" in extra:
            print(f"  Colppy unmatched — WRONG_CLOSE_DATE: {extra.get('colppy_only_wrong_close_date_count', 0)}")
        if "colppy_only_wrong_stage_count" in extra:
            print(f"  Colppy unmatched — WRONG_STAGE: {extra.get('colppy_only_wrong_stage_count', 0)}")
        if "colppy_only_no_deal_count" in extra:
            print(f"  Colppy unmatched — NO_HUBSPOT_DEAL: {extra.get('colppy_only_no_deal_count', 0)}")
        # HubSpot breakdown
        if "hubspot_only_strict_count" in extra:
            print(f"  HubSpot only (truly not in Colppy): {extra.get('hubspot_only_strict_count', 0)}")
        if "hubspot_colppy_discrepancy_count" in extra:
            print(f"  HubSpot / Colppy discrepancy: {extra.get('hubspot_colppy_discrepancy_count', 0)}")
            if "hubspot_discrepancy_in_empresa_no_pago_count" in extra:
                print(f"    ↳ IN_EMPRESA_NO_PAGO: {extra.get('hubspot_discrepancy_in_empresa_no_pago_count', 0)}")
            if "hubspot_discrepancy_primer_pago_other_month_count" in extra:
                print(f"    ↳ PRIMER_PAGO_OTHER_MONTH: {extra.get('hubspot_discrepancy_primer_pago_other_month_count', 0)}")
            if "hubspot_discrepancy_in_empresa_pago_no_primer_count" in extra:
                print(f"    ↳ IN_EMPRESA_PAGO_NO_PRIMER: {extra.get('hubspot_discrepancy_in_empresa_pago_no_primer_count', 0)}")
    print()
    print("Use --diff to see record-level changes (fixed, new, unchanged, regression) vs previous run.")


if __name__ == "__main__":
    main()
