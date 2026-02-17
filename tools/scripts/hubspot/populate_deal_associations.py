#!/usr/bin/env python3
"""
Populate Deal–Company Associations in SQLite
=============================================
Reads deal HubSpot IDs from the facturacion_hubspot.db, fetches their
company associations from HubSpot, and stores them in the deal_associations table.

Uses: GET /crm/v4/objects/deals/{deal_id}/associations/companies
(Individual endpoint per deal – proven reliable across all codebase scripts)

Previous approach used POST /crm/v4/associations/deals/companies/batch/read
which silently dropped deals on failed batches. Switched to individual endpoint
matching the pattern used by analyze_smb_mql_funnel.py, analyze_icp_operador_billing.py,
fetch_hubspot_deals_with_company.py, etc.

Usage:
    python tools/scripts/hubspot/populate_deal_associations.py
    python tools/scripts/hubspot/populate_deal_associations.py --db path/to/db
    python tools/scripts/hubspot/populate_deal_associations.py --dry-run
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/outputs/facturacion_hubspot.db"


def get_deal_hubspot_ids(conn: sqlite3.Connection) -> list[str]:
    """Get all unique deal HubSpot IDs from the deals table."""
    rows = conn.execute("SELECT hubspot_id FROM deals WHERE hubspot_id != ''").fetchall()
    return [r[0] for r in rows]


BATCH_SIZE = 100


def fetch_deal_associations_batch(client, deal_ids: list[str]) -> list[dict]:
    """
    Fetch company associations for multiple deals via batch v4 API.
    Endpoint: POST /crm/v4/associations/deals/companies/batch/read
    Max 100 deals per request. Returns same format as fetch_deal_associations.
    """
    if not deal_ids:
        return []
    all_assocs = []
    try:
        resp = client.post(
            "crm/v4/associations/deals/companies/batch/read",
            json_data={"inputs": [{"id": did} for did in deal_ids]},
        )
    except Exception:
        return []
    for r in resp.get("results", []):
        deal_id = str(r.get("from", {}).get("id", ""))
        if not deal_id:
            continue
        for to_obj in r.get("to", []) or []:
            company_id = to_obj.get("toObjectId")
            if not company_id:
                continue
            assoc_types = to_obj.get("associationTypes", []) or []
            if not assoc_types:
                all_assocs.append({
                    "deal_hubspot_id": deal_id,
                    "company_hubspot_id": str(company_id),
                    "association_type_id": 0,
                    "association_category": "UNKNOWN",
                })
            else:
                for at in assoc_types:
                    if at and isinstance(at, dict):
                        all_assocs.append({
                            "deal_hubspot_id": deal_id,
                            "company_hubspot_id": str(company_id),
                            "association_type_id": at.get("typeId", 0),
                            "association_category": at.get("category", ""),
                        })
    return all_assocs


def fetch_deal_associations(client, deal_id: str) -> list[dict]:
    """
    Fetch company associations for a single deal via the individual v4 API.
    Endpoint: GET /crm/v4/objects/deals/{deal_id}/associations/companies

    This is the same proven pattern used by:
    - analyze_smb_mql_funnel.py (get_primary_company_id)
    - analyze_icp_operador_billing.py (get_primary_company_id)
    - fetch_hubspot_deals_with_company.py (get_deal_company_associations)

    Returns list of {deal_hubspot_id, company_hubspot_id, type_id, category}.
    """
    endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies"

    try:
        resp = client.get(endpoint)
    except Exception:
        return []

    results = resp.get("results", [])
    if not results:
        return []

    associations = []
    for item in results:
        if not item or not isinstance(item, dict):
            continue
        company_id = item.get("toObjectId")
        if not company_id:
            continue
        assoc_types = item.get("associationTypes", [])
        if not assoc_types:
            # Association exists but no specific type info
            associations.append({
                "deal_hubspot_id": deal_id,
                "company_hubspot_id": str(company_id),
                "association_type_id": 0,
                "association_category": "UNKNOWN",
            })
        else:
            for at in assoc_types:
                if not at or not isinstance(at, dict):
                    continue
                associations.append({
                    "deal_hubspot_id": deal_id,
                    "company_hubspot_id": str(company_id),
                    "association_type_id": at.get("typeId", 0),
                    "association_category": at.get("category", ""),
                })
    return associations


def populate_associations(conn: sqlite3.Connection, all_associations: list[dict], replace_all: bool = True):
    """Insert associations into SQLite. If replace_all, clears table first. Else merges for given deals."""
    if replace_all:
        conn.execute("DELETE FROM deal_associations")
    rows = [
        (a["deal_hubspot_id"], a["company_hubspot_id"],
         a["association_type_id"], a["association_category"])
        for a in all_associations
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO deal_associations "
        "(deal_hubspot_id, company_hubspot_id, association_type_id, association_category) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def insert_association_local(conn: sqlite3.Connection, deal_id: str, company_id: str, type_id: int = 5, category: str = "HUBSPOT_DEFINED"):
    """Insert a single association locally (optimistic update after API fix)."""
    conn.execute(
        "INSERT OR REPLACE INTO deal_associations (deal_hubspot_id, company_hubspot_id, association_type_id, association_category) VALUES (?, ?, ?, ?)",
        (deal_id, company_id, type_id, category),
    )
    conn.commit()


def print_summary(conn: sqlite3.Connection):
    """Print association stats."""
    total = conn.execute("SELECT COUNT(*) FROM deal_associations").fetchone()[0]
    unique_deals = conn.execute("SELECT COUNT(DISTINCT deal_hubspot_id) FROM deal_associations").fetchone()[0]
    unique_companies = conn.execute("SELECT COUNT(DISTINCT company_hubspot_id) FROM deal_associations").fetchone()[0]

    print(f"\n  Total association rows: {total:,}")
    print(f"  Unique deals with associations: {unique_deals:,}")
    print(f"  Unique companies in associations: {unique_companies:,}")

    # Association type breakdown
    print("\n  Association type breakdown:")
    type_rows = conn.execute("""
        SELECT association_type_id, association_category, COUNT(*) AS cnt
        FROM deal_associations
        GROUP BY association_type_id, association_category
        ORDER BY cnt DESC
    """).fetchall()

    type_labels = {
        5: "PRIMARY",
        6: "Deal with Primary Company",
        341: "Default/Standard",
        342: "Standard (Alt)",
        8: "Estudio Contable",
        11: "Multiples Negocios",
        2: "Refiere",
        39: "Integrador",
    }
    for tid, cat, cnt in type_rows:
        label = type_labels.get(tid, f"Type {tid}")
        print(f"    {tid} ({cat}) {label}: {cnt:,}")

    # Deals without any association
    deals_total = conn.execute("SELECT COUNT(*) FROM deals WHERE hubspot_id != ''").fetchone()[0]
    deals_no_assoc = conn.execute("""
        SELECT COUNT(*) FROM deals d
        WHERE d.hubspot_id != ''
        AND d.hubspot_id NOT IN (SELECT DISTINCT deal_hubspot_id FROM deal_associations)
    """).fetchone()[0]
    print(f"\n  Deals without any company association: {deals_no_assoc:,} / {deals_total:,}")

    # Deals without PRIMARY (type 5)
    deals_no_primary = conn.execute("""
        SELECT COUNT(DISTINCT d.hubspot_id) FROM deals d
        WHERE d.hubspot_id != ''
        AND d.hubspot_id NOT IN (
            SELECT deal_hubspot_id FROM deal_associations WHERE association_type_id = 5
        )
    """).fetchone()[0]
    print(f"  Deals without PRIMARY company (type 5): {deals_no_primary:,} / {deals_total:,}")

    # Facturacion rows where billing company is NOT primary on the deal (one count per deal+cuit)
    billing_not_primary = conn.execute("""
        SELECT COUNT(*) FROM facturacion f
        JOIN deals d ON f.id_empresa = d.id_empresa
        WHERE d.hubspot_id != '' AND f.customer_cuit != ''
        AND f.customer_cuit IN (SELECT cuit FROM companies WHERE hubspot_id != '')
        AND NOT EXISTS (
            SELECT 1 FROM deal_associations da
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.deal_hubspot_id = d.hubspot_id AND c.cuit = f.customer_cuit
            AND da.association_type_id = 5
        )
    """).fetchone()[0]
    billing_total = conn.execute("""
        SELECT COUNT(*) FROM facturacion f
        JOIN deals d ON f.id_empresa = d.id_empresa
        WHERE d.hubspot_id != '' AND f.customer_cuit != ''
        AND f.customer_cuit IN (SELECT cuit FROM companies WHERE hubspot_id != '')
    """).fetchone()[0]
    print(f"\n  Billing company NOT primary on deal: {billing_not_primary:,} / {billing_total:,}")

    # Billing company not associated at all (one count per deal+cuit)
    billing_no_assoc = conn.execute("""
        SELECT COUNT(*) FROM facturacion f
        JOIN deals d ON f.id_empresa = d.id_empresa
        WHERE d.hubspot_id != '' AND f.customer_cuit != ''
        AND f.customer_cuit IN (SELECT cuit FROM companies WHERE hubspot_id != '')
        AND NOT EXISTS (
            SELECT 1 FROM deal_associations da
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.deal_hubspot_id = d.hubspot_id AND c.cuit = f.customer_cuit
        )
    """).fetchone()[0]
    print(f"  Billing company NOT associated at all: {billing_no_assoc:,} / {billing_total:,}")

    print()


def log(msg: str):
    """Print with flush to avoid buffering in background processes."""
    print(msg, flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch deal–company associations from HubSpot and store in SQLite"
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--delay", type=float, default=0.12, help="Delay between API calls (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Only count, do not fetch/write")
    parser.add_argument(
        "--deals",
        type=str,
        default="",
        help="Comma-separated deal IDs for incremental refresh only (e.g. 123,456,789). Skips full fetch.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Use batch API (100 deals/request) instead of individual calls. Faster for full refresh.",
    )
    args = parser.parse_args()

    from tools.hubspot_api.client import get_hubspot_client
    client = get_hubspot_client()

    db_path = Path(args.db)
    if not db_path.exists():
        log(f"ERROR: Database not found: {db_path}")
        log("Run build_facturacion_hubspot_mapping.py first.")
        return 1

    conn = sqlite3.connect(str(db_path))

    log("=" * 70)
    log("POPULATE DEAL–COMPANY ASSOCIATIONS (individual v4 API)")
    log("=" * 70)

    if args.deals:
        deal_ids = [x.strip() for x in args.deals.split(",") if x.strip()]
        incremental = True
        log(f"\nIncremental mode: {len(deal_ids):,} deals only")
    else:
        deal_ids = get_deal_hubspot_ids(conn)
        incremental = False
        log(f"\nDeals in database: {len(deal_ids):,}")

    if args.dry_run:
        log(f"[DRY RUN] Would fetch associations for {len(deal_ids):,} deals")
        conn.close()
        return 0

    all_associations = []
    deals_processed = 0
    deals_with_assoc = 0
    deals_failed = 0
    total = len(deal_ids)
    log(f"Fetching associations for {total:,} deals...")
    if args.batch:
        log(f"Using batch API ({BATCH_SIZE} deals/request). Estimated time: ~{((total + BATCH_SIZE - 1) // BATCH_SIZE) * 2 / 60:.1f} min\n")
    elif not incremental:
        log(f"Estimated time: ~{total * (args.delay + 0.45) / 60:.0f} min\n")

    if args.batch:
        # Batch fetch: 100 deals per request
        for i in range(0, total, BATCH_SIZE):
            batch = deal_ids[i : i + BATCH_SIZE]
            try:
                assocs = fetch_deal_associations_batch(client, batch)
                all_associations.extend(assocs)
                deals_processed += len(batch)
                deals_with_assoc += len(set(a["deal_hubspot_id"] for a in assocs))
            except Exception as e:
                deals_failed += len(batch)
                if deals_failed <= BATCH_SIZE:
                    log(f"  Warning: batch at {i} failed: {e}")
            if (i + BATCH_SIZE) % 400 == 0 or i + BATCH_SIZE >= total:
                log(
                    f"  {min(i + BATCH_SIZE, total):,}/{total:,} deals | "
                    f"{len(all_associations):,} associations | "
                    f"{deals_with_assoc:,} with companies | "
                    f"{deals_failed} failed"
                )
            time.sleep(0.15)
    else:
        # Individual fetch (reliable approach)
        for i, deal_id in enumerate(deal_ids, 1):
            try:
                assocs = fetch_deal_associations(client, deal_id)
                all_associations.extend(assocs)
                deals_processed += 1
                if assocs:
                    deals_with_assoc += 1
            except Exception as e:
                deals_failed += 1
                if deals_failed <= 5:
                    log(f"  Warning: deal {deal_id} failed: {e}")

            if i % 200 == 0 or i == total:
                log(
                    f"  {i:,}/{total:,} deals | "
                    f"{len(all_associations):,} associations | "
                    f"{deals_with_assoc:,} with companies | "
                    f"{deals_failed} failed"
                )
            time.sleep(args.delay)

    log(f"\nTotal associations fetched: {len(all_associations):,}")
    log(f"Deals processed: {deals_processed:,} | with associations: {deals_with_assoc:,} | failed: {deals_failed}")

    # Populate SQLite
    if incremental:
        # Remove existing rows for these deals, then insert new
        placeholders = ",".join("?" * len(deal_ids))
        conn.execute(f"DELETE FROM deal_associations WHERE deal_hubspot_id IN ({placeholders})", deal_ids)
        conn.commit()
        log(f"Updated associations for {len(deal_ids):,} deals (incremental)")
    log("Writing to deal_associations table...")
    populate_associations(conn, all_associations, replace_all=not incremental)

    # Summary
    print_summary(conn)

    # Log to edit_logs
    try:
        from tools.scripts.hubspot.edit_log_db import log_edit
        log_edit(
            conn,
            script="populate_deal_associations",
            action="populate",
            outcome="success",
            detail=f"associations: {len(all_associations):,}, deals: {deals_processed:,}",
        )
    except Exception as e:
        log(f"  Warning: Could not log to edit_logs: {e}")

    conn.close()
    log(f"Database: {db_path}")
    log("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
