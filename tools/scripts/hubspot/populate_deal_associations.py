#!/usr/bin/env python3
"""
Populate Deal–Company Associations in SQLite
=============================================
Reads deal HubSpot IDs from the facturacion_hubspot.db, fetches their
company associations from HubSpot, and stores them in the deal_associations table.

Batch mode (--batch): Uses POST /crm/v4/associations/deals/companies/batch/read
with retries, missing-deal detection, and individual API fallback for deals omitted
by the batch response. Returns exit code 1 if any deal fetch failed.

Individual mode: Uses GET /crm/v4/objects/deals/{deal_id}/associations/companies
(proven reliable across analyze_smb_mql_funnel.py, analyze_icp_operador_billing.py, etc.)

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

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

DEFAULT_DB = str(REPO_ROOT / "tools" / "data" / "facturacion_hubspot.db")


def get_deal_hubspot_ids(conn: sqlite3.Connection) -> list[str]:
    """Get all unique deal HubSpot IDs from the deals table."""
    rows = conn.execute("SELECT hubspot_id FROM deals WHERE hubspot_id != ''").fetchall()
    return [r[0] for r in rows]


BATCH_SIZE = 100
BATCH_RETRIES = 3
RETRY_BACKOFF = (1.0, 2.0, 4.0)  # seconds


def fetch_deal_associations_batch(client, deal_ids: list[str], log_fn=None) -> tuple[list[dict], set[str]]:
    """
    Fetch company associations for multiple deals via batch v4 API.
    Endpoint: POST /crm/v4/associations/deals/companies/batch/read
    Max 100 deals per request. Returns (associations, returned_deal_ids).
    Raises on API failure after retries. Caller should re-fetch missing deals via individual API.
    """
    if not deal_ids:
        return [], set()
    log_fn = log_fn or (lambda m: None)
    last_error = None
    for attempt in range(BATCH_RETRIES):
        try:
            resp = client.post(
                "crm/v4/associations/deals/companies/batch/read",
                json_data={"inputs": [{"id": did} for did in deal_ids]},
            )
        except Exception as e:
            last_error = e
            log_fn(f"  Batch API attempt {attempt + 1}/{BATCH_RETRIES} failed: {e}")
            if attempt < BATCH_RETRIES - 1:
                time.sleep(RETRY_BACKOFF[attempt])
            continue
        if resp is None:
            last_error = ValueError("API returned None")
            if attempt < BATCH_RETRIES - 1:
                time.sleep(RETRY_BACKOFF[attempt])
            continue
        results = resp.get("results") or []
        all_assocs = []
        returned_deal_ids = set()
        for r in results:
            if r is None or not isinstance(r, dict):
                continue
            from_obj = r.get("from")
            if from_obj is None:
                from_obj = {}
            elif not isinstance(from_obj, dict):
                continue
            deal_id = str(from_obj.get("id") or "")
            if not deal_id:
                continue
            returned_deal_ids.add(deal_id)
            to_list = r.get("to")
            if to_list is None:
                to_list = []
            elif not isinstance(to_list, list):
                continue
            for to_obj in to_list:
                if to_obj is None or not isinstance(to_obj, dict):
                    continue
                company_id = to_obj.get("toObjectId")
                if company_id is None or company_id == "":
                    continue
                assoc_types = to_obj.get("associationTypes") or []
                if not isinstance(assoc_types, list):
                    assoc_types = []
                if not assoc_types:
                    all_assocs.append({
                        "deal_hubspot_id": deal_id,
                        "company_hubspot_id": str(company_id),
                        "association_type_id": 0,
                        "association_category": "UNKNOWN",
                    })
                else:
                    for at in assoc_types:
                        if at is None or not isinstance(at, dict):
                            continue
                        all_assocs.append({
                            "deal_hubspot_id": deal_id,
                            "company_hubspot_id": str(company_id),
                            "association_type_id": at.get("typeId", 0),
                            "association_category": at.get("category", ""),
                        })
        return all_assocs, returned_deal_ids
    raise last_error or ValueError("Batch API failed after retries")


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

    resp = client.get(endpoint)
    if resp is None:
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
    parser.add_argument(
        "--debug-batch",
        type=int,
        metavar="OFFSET",
        help="Fetch one batch at given offset, print raw API response (for investigating failures).",
    )
    args = parser.parse_args()

    from tools.hubspot_api.client import get_hubspot_client
    client = get_hubspot_client()

    db_path = Path(args.db)
    if not db_path.exists():
        log(f"ERROR: Database not found: {db_path}")
        log("Run build_facturacion_hubspot_mapping.py first.")
        return 1

    if args.debug_batch is not None:
        conn = sqlite3.connect(str(db_path))
        deal_ids = get_deal_hubspot_ids(conn)
        conn.close()
        offset = args.debug_batch
        batch = deal_ids[offset : offset + BATCH_SIZE]
        if not batch:
            log(f"No deals at offset {offset} (total: {len(deal_ids)})")
            return 1
        log(f"Debug batch at offset {offset}: {len(batch)} deals")
        log(f"Deal IDs (first 5): {batch[:5]}")
        try:
            resp = client.post(
                "crm/v4/associations/deals/companies/batch/read",
                json_data={"inputs": [{"id": did} for did in batch]},
            )
        except Exception as e:
            log(f"API error: {e}")
            return 1
        import json
        log("\n--- Raw API response (structure) ---")
        if resp is None:
            log("Response is None")
        else:
            log(f"Keys: {list(resp.keys()) if isinstance(resp, dict) else type(resp)}")
            results = resp.get("results", [])
            log(f"results length: {len(results)}")
            for i, r in enumerate(results):
                if r is None:
                    log(f"  results[{i}]: None")
                elif not isinstance(r, dict):
                    log(f"  results[{i}]: type={type(r).__name__}")
                else:
                    from_val = r.get("from")
                    to_val = r.get("to")
                    from_str = "None" if from_val is None else f"dict(id={from_val.get('id') if isinstance(from_val, dict) else '?'})"
                    to_str = "None" if to_val is None else f"list(len={len(to_val)})" if isinstance(to_val, list) else type(to_val).__name__
                    log(f"  results[{i}]: from={from_str}, to={to_str}")
                    if from_val is None:
                        log(f"    FULL: {json.dumps(r, default=str)[:200]}...")
            log("\n--- Full response (first 2 results) ---")
            log(json.dumps({"results": results[:2]}, indent=2, default=str))
        return 0

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
        # Batch fetch: 100 deals per request, with missing-deal detection and individual fallback
        for i in range(0, total, BATCH_SIZE):
            batch = deal_ids[i : i + BATCH_SIZE]
            try:
                assocs, returned_deal_ids = fetch_deal_associations_batch(client, batch, log_fn=log)
                all_associations.extend(assocs)
                deals_processed += len(batch)
                deals_with_assoc += len(set(a["deal_hubspot_id"] for a in assocs))
                # Detect deals omitted by batch API (e.g. 99 results for 100 requests)
                missing = set(batch) - returned_deal_ids
                if missing:
                    log(f"  Batch at {i}: {len(missing)} deals missing from API response, re-fetching individually")
                    for did in missing:
                        try:
                            fallback = fetch_deal_associations(client, did)
                            all_associations.extend(fallback)
                            deals_with_assoc += 1 if fallback else 0
                            time.sleep(args.delay)
                        except Exception as e:
                            deals_failed += 1
                            if deals_failed <= 5:
                                log(f"  Warning: individual fetch for deal {did} failed: {e}")
            except Exception as e:
                log(f"  Warning: batch at {i} failed after retries: {e}")
                # Fallback: fetch each deal individually
                for did in batch:
                    try:
                        fallback = fetch_deal_associations(client, did)
                        all_associations.extend(fallback)
                        deals_processed += 1
                        deals_with_assoc += 1 if fallback else 0
                        time.sleep(args.delay)
                    except Exception as e2:
                        deals_failed += 1
                        if deals_failed <= 5:
                            log(f"  Warning: fallback fetch for deal {did} failed: {e2}")
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

    # Post-fetch validation: ensure we have data for all requested deals
    deals_in_results = {a["deal_hubspot_id"] for a in all_associations}
    never_fetched = set(deal_ids) - deals_in_results
    if never_fetched and deals_failed == 0:
        # Deals with no associations in HubSpot (legitimate empty)
        log(f"  Note: {len(never_fetched):,} deals have no company associations in HubSpot")
    elif never_fetched and deals_failed > 0:
        log(f"  Warning: {len(never_fetched):,} deals have no data (includes {deals_failed} fetch failures)")

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

    # Log refresh timestamp (for "when was deal_associations last synced?")
    total_assocs = conn.execute("SELECT COUNT(*) FROM deal_associations").fetchone()[0]
    unique_deals = conn.execute("SELECT COUNT(DISTINCT deal_hubspot_id) FROM deal_associations").fetchone()[0]
    unique_companies = conn.execute("SELECT COUNT(DISTINCT company_hubspot_id) FROM deal_associations").fetchone()[0]
    try:
        from tools.utils.hubspot_refresh_logger import log_deal_associations_refresh
        log_deal_associations_refresh(
            str(db_path),
            total_associations=total_assocs,
            unique_deals=unique_deals,
            unique_companies=unique_companies,
        )
        log(f"  Refresh logged to hubspot_deal_associations_refresh_logs")
    except Exception as e:
        log(f"  Warning: Could not log refresh: {e}")

    # Log to edit_logs
    try:
        from tools.scripts.hubspot.edit_log_db import log_edit
        log_edit(
            conn,
            script="populate_deal_associations",
            action="populate",
            outcome="failure" if deals_failed > 0 else "success",
            detail=f"associations: {len(all_associations):,}, deals: {deals_processed:,}, failed: {deals_failed}",
        )
    except Exception as e:
        log(f"  Warning: Could not log to edit_logs: {e}")

    conn.close()
    log(f"Database: {db_path}")
    log("=" * 70)
    return 1 if deals_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
