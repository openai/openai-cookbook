#!/usr/bin/env python3
"""
Populate Accountant-Associated Deals (including churned)
========================================================
Fetches deals associated with accountant companies from HubSpot and adds them
to facturacion_hubspot.db. This includes CHURNED deals (id_empresa not in
facturacion) so the MRR matrix can compute portfolio behavior with churn.

Accountant companies:
- type IN (Cuenta Contador, Cuenta Contador y Reseller, Contador Robado)
- OR companies with association type 8 (Estudio Contable) on any deal

Flow:
1. Get accountant company IDs from DB
2. For each, fetch associated deals via HubSpot (companies -> deals)
3. For deals not in deals table, fetch details and insert
4. Optionally run populate_deal_associations for new deals

Usage:
    python tools/scripts/hubspot/populate_accountant_deals.py
    python tools/scripts/hubspot/populate_accountant_deals.py --dry-run
    python tools/scripts/hubspot/populate_accountant_deals.py --skip-associations

When to run: First-time setup; HubSpot data changed (new deals/associations); need full
dataset after a previous --limit run. Do NOT run when only rebuilding the MRR dashboard
(use analyze_accountant_mrr_matrix.py --html instead). See
tools/docs/HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md section 6.
"""
import argparse
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/outputs/facturacion_hubspot.db"
ACCOUNTANT_TYPES = ("Cuenta Contador", "Cuenta Contador y Reseller", "Contador Robado")
DEAL_PROPERTIES = ["dealname", "id_empresa", "dealstage", "amount", "closedate", "hs_object_id"]


def get_accountant_company_ids(conn: sqlite3.Connection) -> list[str]:
    """Get HubSpot company IDs for accountants (type or association type 8)."""
    rows = conn.execute("""
        SELECT DISTINCT c.hubspot_id
        FROM companies c
        WHERE c.hubspot_id != ''
        AND (
            c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            OR c.hubspot_id IN (
                SELECT company_hubspot_id FROM deal_associations WHERE association_type_id = 8
            )
        )
    """).fetchall()
    return [r[0] for r in rows]


def get_existing_deal_ids(conn: sqlite3.Connection) -> set[str]:
    """Get deal HubSpot IDs already in deals table."""
    rows = conn.execute("SELECT hubspot_id FROM deals WHERE hubspot_id != ''").fetchall()
    return {r[0] for r in rows}


def fetch_company_deal_ids(client, company_id: str) -> list[str]:
    """Fetch deal IDs associated with a company."""
    try:
        resp = client.get_associations(company_id, "companies", "deals")
        results = resp.get("results", []) or []
        return [str(r["toObjectId"]) for r in results if r.get("toObjectId")]
    except Exception:
        return []


def fetch_deals_batch(client, deal_ids: list[str]) -> list[dict]:
    """Batch read deal details from HubSpot."""
    if not deal_ids:
        return []
    try:
        resp = client.post(
            "crm/v3/objects/deals/batch/read",
            json_data={
                "inputs": [{"id": did} for did in deal_ids],
                "properties": list(DEAL_PROPERTIES),
            },
        )
        return resp.get("results", [])
    except Exception:
        return []


def insert_deals(conn: sqlite3.Connection, deals: list[dict]) -> tuple[int, list[str]]:
    """Insert or replace deals. Returns (count, list of inserted deal hubspot_ids)."""
    if not deals:
        return 0, []
    rows = []
    inserted_ids = []
    for d in deals:
        props = d.get("properties", {})
        id_empresa = (props.get("id_empresa") or "").strip()
        if not id_empresa or not id_empresa.isdigit():
            continue
        hubspot_id = str(d.get("id", ""))
        if not hubspot_id:
            continue
        rows.append((
            id_empresa,
            hubspot_id,
            props.get("dealname", ""),
            props.get("dealstage", ""),
            props.get("amount", ""),
            props.get("closedate", ""),
        ))
        inserted_ids.append(hubspot_id)
    conn.executemany(
        "INSERT OR REPLACE INTO deals (id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows), inserted_ids


def main():
    parser = argparse.ArgumentParser(
        description="Fetch accountant-associated deals (including churned) from HubSpot"
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to facturacion_hubspot.db")
    parser.add_argument("--dry-run", action="store_true", help="Only report, do not write")
    parser.add_argument("--skip-associations", action="store_true", help="Do not run populate_deal_associations")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between API calls (seconds)")
    parser.add_argument("--limit", type=int, default=0, help="Limit accountant companies (0 = all)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        print("Run build_facturacion_hubspot_mapping.py first.", file=sys.stderr)
        return 1

    from tools.hubspot_api.client import get_hubspot_client
    client = get_hubspot_client()

    conn = sqlite3.connect(str(db_path))
    accountant_ids = get_accountant_company_ids(conn)
    if args.limit:
        accountant_ids = accountant_ids[: args.limit]
        print(f"(Limited to first {args.limit} accountants)")
    existing_deal_ids = get_existing_deal_ids(conn)
    conn.close()

    print("=" * 70)
    print("POPULATE ACCOUNTANT DEALS (including churned)")
    print("=" * 70)
    print(f"\nAccountant companies: {len(accountant_ids):,}")
    print(f"Existing deals in DB: {len(existing_deal_ids):,}")

    # Collect deal IDs from all accountants
    all_deal_ids = set()
    for i, cid in enumerate(accountant_ids):
        deal_ids = fetch_company_deal_ids(client, cid)
        all_deal_ids.update(deal_ids)
        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1:,}/{len(accountant_ids):,} accountants → {len(all_deal_ids):,} deals")
        time.sleep(args.delay)

    new_deal_ids = [did for did in all_deal_ids if did not in existing_deal_ids]
    print(f"\nTotal deals from accountants: {len(all_deal_ids):,}")
    print(f"New deals (not in DB): {len(new_deal_ids):,}")

    if not new_deal_ids:
        print("\nNo new deals to add.")
        return 0

    if args.dry_run:
        print(f"\n[DRY RUN] Would fetch and insert {len(new_deal_ids):,} deals")
        return 0

    # Batch fetch new deals (100 per batch)
    batch_size = 100
    all_deals = []
    for i in range(0, len(new_deal_ids), batch_size):
        batch = new_deal_ids[i : i + batch_size]
        deals = fetch_deals_batch(client, batch)
        all_deals.extend(deals)
        if (i + batch_size) < len(new_deal_ids):
            time.sleep(args.delay)

    conn = sqlite3.connect(str(db_path))
    inserted, inserted_ids = insert_deals(conn, all_deals)
    conn.close()

    print(f"\nInserted {inserted:,} deals into deals table.")

    if not args.skip_associations and inserted_ids:
        print("\nRunning populate_deal_associations for new deals...")
        deal_ids_str = ",".join(inserted_ids)
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent / "populate_deal_associations.py"),
                "--db", str(db_path),
                "--deals", deal_ids_str,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"Warning: populate_deal_associations failed: {result.stderr}", file=sys.stderr)

    print(f"\nDatabase: {db_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
