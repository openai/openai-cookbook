#!/usr/bin/env python3
"""Print next N pending merges for merge_progress.sh. No heavy imports."""
import sqlite3
import sys
from pathlib import Path

# Add repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.scripts.hubspot.merge_duplicates_by_cuit import get_merge_plan


def main() -> int:
    args = sys.argv[1:]
    stats_only = args and args[0] == "--stats"
    if stats_only:
        args = args[1:]
    db_path = args[0] if args else "tools/outputs/facturacion_hubspot.db"
    n = int(args[1]) if len(args) > 1 and not stats_only else (0 if stats_only else 5)

    conn = sqlite3.connect(db_path, timeout=10)
    try:
        plan = get_merge_plan(conn, exclude_test=True)
        done = set(
            r[0]
            for r in conn.execute(
                "SELECT company_id_secondary FROM edit_logs "
                "WHERE script='merge_duplicates_by_cuit' AND outcome IN ('success','skipped')"
            ).fetchall()
        )
        pending = [m for m in plan if m["secondary_id"] not in done]
        plan_size = len(plan)
        processed = plan_size - len(pending)
        pct = round(100.0 * processed / plan_size, 1) if plan_size else 0

        if stats_only:
            print(f"Processed: {processed}/{plan_size} | Pending: {len(pending)} | {pct}%")
            return 0

        for i, m in enumerate(pending[:n], 1):
            pname = (m["primary_name"] or "")[:32]
            sname = (m["secondary_name"] or "")[:28]
            print(f"  {i}. {m['cuit']} | {pname} <- {m['secondary_id']} ({sname})")
        if not pending:
            print("  (all done)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
