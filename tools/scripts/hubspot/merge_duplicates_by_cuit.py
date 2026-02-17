#!/usr/bin/env python3
"""
Merge Duplicate HubSpot Companies by CUIT (Batch)
==================================================
Finds all CUITs (in facturacion) with multiple HubSpot company records and merges
them into one company per CUIT. Uses HubSpot merge API (pairwise).

Primary selection: Prefer company with type set, then prefer name that is not just
a number. Merges all secondaries into primary.

Uses: POST /crm/v3/objects/companies/merge
Logs successful merges to edit_logs in facturacion_hubspot.db.

Usage:
    python tools/scripts/hubspot/merge_duplicates_by_cuit.py --dry-run
    python tools/scripts/hubspot/merge_duplicates_by_cuit.py --apply --batch 10
    python tools/scripts/hubspot/merge_duplicates_by_cuit.py --apply --exclude-test
"""
import argparse
import warnings

# Suppress urllib3 LibreSSL warning on macOS (Python built with LibreSSL 2.8.3)
warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL.*")
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/data/facturacion_hubspot.db"
TEST_CUIT = "20000000001"


def _primary_score(row: tuple) -> tuple:
    """
    Score for primary selection: higher = better.
    (has_type, name_not_just_number, hubspot_id for tiebreak)
    """
    hubspot_id, name, ctype = row[1], row[2] or "", row[3] or ""
    has_type = 1 if ctype.strip() else 0
    name_clean = (name or "").strip()
    # Name is "just a number" if it matches only digits (possibly with spaces)
    name_not_number = 1 if name_clean and not re.match(r"^\d+\s*$", name_clean) else 0
    return (has_type, name_not_number, hubspot_id)


def get_merge_plan(conn: sqlite3.Connection, exclude_test: bool = False) -> list[dict]:
    """
    Returns list of merge actions: [{"cuit", "primary_id", "primary_name", "secondary_id", "secondary_name"}, ...]
    One merge per secondary; primary is the one to keep.
    """
    fact_cuits = set(
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT customer_cuit FROM facturacion WHERE customer_cuit != ''"
        ).fetchall()
    )
    if exclude_test and TEST_CUIT in fact_cuits:
        fact_cuits.discard(TEST_CUIT)

    # All companies per CUIT (in facturacion)
    rows = conn.execute(
        """
        SELECT c.cuit, c.hubspot_id, c.name, c.type
        FROM companies c
        WHERE c.cuit IN ({})
          AND c.hubspot_id != ''
        """.format(",".join("?" * len(fact_cuits))),
        list(fact_cuits),
    ).fetchall()

    # Group by CUIT
    by_cuit: dict[str, list[tuple]] = {}
    for r in rows:
        cuit = r[0]
        if cuit not in by_cuit:
            by_cuit[cuit] = []
        by_cuit[cuit].append(r)

    plan = []
    for cuit, companies in by_cuit.items():
        if len(companies) < 2:
            continue
        # Dedupe by hubspot_id
        seen = set()
        unique = []
        for r in companies:
            if r[1] not in seen:
                seen.add(r[1])
                unique.append(r)
        if len(unique) < 2:
            continue

        # Sort: primary first (has type, name not just number)
        unique.sort(key=lambda r: (-_primary_score(r)[0], -_primary_score(r)[1], _primary_score(r)[2]))
        primary = unique[0]
        secondaries = unique[1:]

        for sec in secondaries:
            plan.append({
                "cuit": cuit,
                "primary_id": str(primary[1]),
                "primary_name": primary[2] or "(no name)",
                "secondary_id": str(sec[1]),
                "secondary_name": sec[2] or "(no name)",
            })
    return plan


def _log_merge_outcome(
    db_path: Path,
    m: dict,
    outcome: str,
    detail: str,
    company_id: str = "",
    company_name: str = "",
) -> None:
    """Log merge outcome (success, failed, skipped) to edit_logs."""
    from tools.scripts.hubspot.edit_log_db import log_edit

    conn = sqlite3.connect(str(db_path))
    try:
        log_edit(
            conn,
            script="merge_duplicates_by_cuit",
            action="merge",
            outcome=outcome,
            detail=detail[:500],
            company_id=(company_id or m.get("primary_id", ""))[:50],
            company_name=(company_name or m.get("primary_name", ""))[:200],
            company_url=f"https://app.hubspot.com/contacts/19877595/company/{company_id}" if company_id else "",
            company_id_secondary=str(m.get("secondary_id", ""))[:50],
            customer_cuit=str(m.get("cuit", ""))[:20],
        )
    finally:
        conn.close()


def resolve_canonical_id(client, company_id: str) -> Optional[str]:
    """
    Resolve company ID to canonical (current) ID. HubSpot redirects merged records
    to the new canonical ID. Returns the canonical id, or None if not found.
    """
    try:
        result = client.get(f"crm/v3/objects/companies/{company_id}")
        return str(result.get("id", company_id))
    except Exception:
        return None


def _merge_with_error_detail(client, primary_id: str, secondary_id: str):
    """
    Merge and return (result, None) on success or (None, error_msg) on failure.
    Uses direct request to capture 400 response body (client retries hide it).
    """
    import requests

    from tools.hubspot_api.config import get_config

    config = get_config()
    url = f"{config.base_url}/crm/v3/objects/companies/merge"
    payload = {
        "primaryObjectId": str(primary_id),
        "objectIdToMerge": str(secondary_id),
    }
    resp = requests.post(url, json=payload, headers=config.headers, timeout=config.timeout)
    if resp.status_code in (200, 201):
        return (resp.json(), None)
    err_msg = f"{resp.status_code} {resp.reason}"
    if resp.text:
        err_msg = f"{err_msg} | {resp.text[:600]}"
    return (None, err_msg)


def main():
    parser = argparse.ArgumentParser(
        description="Merge duplicate HubSpot companies (same CUIT) in batch"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show merge plan, no changes")
    parser.add_argument("--apply", action="store_true", help="Execute merges")
    parser.add_argument(
        "--batch",
        type=int,
        default=0,
        help="Limit merges per run (0 = all)",
    )
    parser.add_argument(
        "--exclude-test",
        action="store_true",
        help=f"Exclude test CUIT {TEST_CUIT}",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between operations (default 1.0; use 0.5 for faster, 2 for safer)",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to facturacion_hubspot.db")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Use --dry-run to preview or --apply to execute.")
        return 1

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        plan = get_merge_plan(conn, exclude_test=args.exclude_test)
    finally:
        conn.close()

    if not plan:
        print("No duplicate companies to merge.")
        return 0

    if args.batch and args.batch > 0:
        plan = plan[: args.batch]

    # Filter to pending only: skip items already in edit_logs (success/skipped)
    if not args.dry_run:
        conn = sqlite3.connect(str(db_path))
        try:
            done = set(
                r[0]
                for r in conn.execute(
                    "SELECT company_id_secondary FROM edit_logs "
                    "WHERE script='merge_duplicates_by_cuit' AND outcome IN ('success','skipped')"
                ).fetchall()
            )
            plan_before = len(plan)
            plan = [m for m in plan if m["secondary_id"] not in done]
            skipped_count = plan_before - len(plan)
            if skipped_count > 0:
                print(f"Skipping {skipped_count} already processed (in edit_logs), {len(plan)} pending.")
            if not plan:
                print("Nothing to do (all already processed).")
                return 0
        finally:
            conn.close()

    print(f"Merge plan: {len(plan)} merges ({'dry-run' if args.dry_run else 'apply'})")
    if args.exclude_test:
        print(f"  (excluding test CUIT {TEST_CUIT})")
    print()

    for i, m in enumerate(plan[: 20 if args.dry_run else len(plan)], 1):
        print(f"  {i}. CUIT {m['cuit']}: merge {m['secondary_id']} ({m['secondary_name'][:40]}) -> {m['primary_id']} ({m['primary_name'][:40]})")
    if len(plan) > 20 and args.dry_run:
        print(f"  ... and {len(plan) - 20} more")

    if args.dry_run:
        print(f"\nTotal: {len(plan)} merges. Run with --apply to execute.")
        return 0

    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    ok, fail, skip = 0, 0, 0
    # Track current canonical primary per CUIT (HubSpot creates new ID on each merge)
    primary_by_cuit: dict[str, str] = {}
    delay_sec = max(0.2, args.delay)  # Min 0.2s to avoid rate limits
    for i, m in enumerate(plan):
        if i > 0:
            time.sleep(delay_sec)
        # Resolve to canonical IDs (HubSpot creates new ID on merge; old IDs redirect)
        if m["cuit"] in primary_by_cuit:
            primary_canonical = primary_by_cuit[m["cuit"]]
        else:
            primary_canonical = resolve_canonical_id(client, m["primary_id"])
            if primary_canonical:
                primary_by_cuit[m["cuit"]] = primary_canonical
        secondary_canonical = resolve_canonical_id(client, m["secondary_id"])
        if not primary_canonical or not secondary_canonical:
            fail += 1
            err_detail = "Could not resolve to canonical ID"
            print(f"  FAIL: {err_detail} {m['secondary_id']} or {m['primary_id']}", file=sys.stderr)
            _log_merge_outcome(db_path, m, "failed", err_detail, company_id=m["primary_id"])
            continue
        if primary_canonical == secondary_canonical:
            skip += 1
            print(f"  SKIP: {m['secondary_id']} already merged into {m['primary_id']}")
            _log_merge_outcome(db_path, m, "skipped", "already_merged", company_id=primary_canonical)
            continue
        result, err = _merge_with_error_detail(
            client, primary_canonical, secondary_canonical
        )
        if err:
            fail += 1
            print(f"  FAIL: {m['secondary_id']} -> {m['primary_id']}: {err}", file=sys.stderr)
            _log_merge_outcome(db_path, m, "failed", err[:500], company_id=m["primary_id"])
            continue
        ok += 1
        # HubSpot creates new canonical ID on merge; use it for next merge in same CUIT
        new_id = str(result.get("id", primary_canonical))
        primary_by_cuit[m["cuit"]] = new_id
        name = result.get("properties", {}).get("name", "N/A")
        print(f"  OK: {m['secondary_id']} -> {m['primary_id']} ({name[:50]})")

        _log_merge_outcome(db_path, m, "success", f"Merged {m['secondary_id']} into {m['primary_id']} (canonical: {new_id})", company_id=new_id, company_name=name)

    print(f"\nDone: {ok} merged, {skip} skipped (already merged), {fail} failed.")
    # Log run summary to edit_logs
    _log_merge_outcome(
        db_path,
        {"cuit": "", "primary_id": "", "secondary_id": "", "primary_name": "", "secondary_name": ""},
        "completed",
        f"merged={ok} skipped={skip} failed={fail} total_plan={len(plan)}",
        company_id="",
        company_name="",
    )
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
