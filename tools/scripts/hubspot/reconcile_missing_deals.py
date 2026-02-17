#!/usr/bin/env python3
"""
Reconcile Missing Deals — Avoid Duplicates
==========================================
For facturacion rows without a matching deal in HubSpot, searches for existing
deals that may have wrong/empty id_empresa (e.g. deal name "54468 - X" but
id_empresa=54274). Updates id_empresa when a match is found to avoid creating
duplicate deals.

Lookup logic:
1. Get company by customer_cuit (from facturacion) via companies table or HubSpot search
2. List deals associated with that company
3. Match by deal name: starts with "{id_empresa} -" or contains id_empresa
4. If found → update deal's id_empresa (--apply) or report (--dry-run)
5. If not found → report "create new"

IMPORTANT: This script does NOT create deals. For rows with no matching deal, creation
must be done manually or via a separate process — and ONLY after explicit user
confirmation. Never create deals without confirmation.

Usage:
    python tools/scripts/hubspot/reconcile_missing_deals.py --dry-run
    python tools/scripts/hubspot/reconcile_missing_deals.py --apply
    python tools/scripts/hubspot/reconcile_missing_deals.py --db path/to/facturacion_hubspot.db
"""
import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/outputs/facturacion_hubspot.db"
EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}
PORTAL_ID = "19877595"


def normalize_cuit(raw: str) -> str | None:
    """Normalize CUIT to 11 digits."""
    if not raw or str(raw).strip().upper() in ("#N/A", "N/A", ""):
        return None
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    if len(digits) != 11 or not digits.isdigit() or digits in EXCLUDE_CUITS:
        return None
    return digits


def format_cuit_display(digits: str) -> str:
    """Format 11 digits as XX-XXXXXXXX-X."""
    if not digits or len(digits) != 11:
        return str(digits)
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"


def get_missing_facturacion(conn: sqlite3.Connection) -> list[dict]:
    """Get facturacion rows without a deal in HubSpot."""
    rows = conn.execute("""
        SELECT f.email, f.customer_cuit, f.plan, f.amount, f.product_cuit, f.id_empresa
        FROM facturacion f
        WHERE f.id_empresa IS NOT NULL AND f.id_empresa != ''
        AND NOT EXISTS (
            SELECT 1 FROM deals d
            WHERE d.id_empresa = f.id_empresa AND d.hubspot_id IS NOT NULL AND d.hubspot_id != ''
        )
        ORDER BY f.id_empresa
    """).fetchall()
    return [
        {
            "email": r[0],
            "customer_cuit": r[1],
            "plan": r[2],
            "amount": r[3],
            "product_cuit": r[4],
            "id_empresa": r[5],
        }
        for r in rows
    ]


def get_company_hubspot_id(conn: sqlite3.Connection, cuit: str) -> str | None:
    """Get HubSpot company ID for CUIT. Prefers accountant type when multiple per CUIT."""
    cuit_norm = normalize_cuit(cuit)
    if not cuit_norm:
        return None
    row = conn.execute(
        """
        SELECT hubspot_id FROM companies
        WHERE cuit = ? AND hubspot_id != ''
        ORDER BY CASE WHEN type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado') THEN 0 ELSE 1 END,
                 hubspot_id
        LIMIT 1
        """,
        (cuit_norm,),
    ).fetchone()
    return row[0] if row else None


def search_company_by_cuit(client, cuit: str) -> str | None:
    """Search HubSpot for company by CUIT. Returns first hubspot_id or None."""
    cuit_norm = normalize_cuit(cuit)
    if not cuit_norm:
        return None
    values = [format_cuit_display(cuit_norm), cuit_norm]
    try:
        resp = client.search_objects(
            object_type="companies",
            filter_groups=[{"filters": [{"propertyName": "cuit", "operator": "IN", "values": values}]}],
            properties=["hs_object_id"],
            limit=10,
        )
        for r in resp.get("results", []):
            if r.get("id"):
                return str(r["id"])
    except Exception:
        pass
    return None


def deal_name_matches_id_empresa(deal_name: str, id_empresa: str) -> bool:
    """
    Check if deal name suggests it belongs to id_empresa.
    Patterns: "54468 - Company Name", "54468- Company", "id_empresa" at start.
    """
    if not deal_name or not id_empresa:
        return False
    name = (deal_name or "").strip()
    # Exact start: "54468 - " or "54468- "
    if name.startswith(f"{id_empresa} -") or name.startswith(f"{id_empresa}-"):
        return True
    # Deal name is exactly "id_empresa" (unlikely but possible)
    if name == id_empresa:
        return True
    # Deal name starts with id_empresa followed by space
    if name.startswith(id_empresa + " "):
        return True
    return False


def find_matching_deal(deal_list: list[dict], id_empresa: str) -> dict | None:
    """From list of deals, return first whose name matches id_empresa."""
    for d in deal_list:
        name = (d.get("properties", {}).get("dealname") or "").strip()
        if deal_name_matches_id_empresa(name, id_empresa):
            return d
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile missing deals: find existing deals with wrong id_empresa, update to avoid duplicates"
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to facturacion_hubspot.db")
    parser.add_argument("--dry-run", action="store_true", help="Only report, do not update HubSpot")
    parser.add_argument("--apply", action="store_true", help="Update id_empresa on matched deals in HubSpot")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply")
        return 1

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    from tools.hubspot_api.client import get_hubspot_client
    client = get_hubspot_client()

    conn = sqlite3.connect(str(db_path))
    missing = get_missing_facturacion(conn)
    conn.close()

    if not missing:
        print("No facturacion rows without deals. Nothing to reconcile.")
        return 0

    print(f"Reconciling {len(missing)} facturacion rows without deals...")
    print()

    updated = 0
    to_create = []
    no_company = []
    no_match = []

    for row in missing:
        id_empresa = row["id_empresa"]
        customer_cuit = row.get("customer_cuit")
        cuit_norm = normalize_cuit(customer_cuit) if customer_cuit else None

        # Get company HubSpot ID
        conn = sqlite3.connect(str(db_path))
        company_id = get_company_hubspot_id(conn, customer_cuit or "")
        conn.close()

        if not company_id:
            company_id = search_company_by_cuit(client, customer_cuit or "")
        if not company_id:
            no_company.append(row)
            continue

        # Get deals associated with company
        try:
            assoc = client.get_associations(company_id, "companies", "deals")
            deal_ids = [a.get("toObjectId") for a in assoc.get("results", []) if a.get("toObjectId")]
        except Exception as e:
            print(f"  {id_empresa}: Failed to get associations: {e}")
            no_match.append(row)
            time.sleep(0.2)
            continue

        if not deal_ids:
            no_match.append(row)
            time.sleep(0.2)
            continue

        # Batch read deals
        try:
            resp = client.post(
                "crm/v3/objects/deals/batch/read",
                json_data={
                    "inputs": [{"id": str(did)} for did in deal_ids],
                    "properties": ["dealname", "id_empresa", "dealstage", "amount"],
                },
            )
            deal_list = resp.get("results", [])
        except Exception as e:
            print(f"  {id_empresa}: Failed to read deals: {e}")
            no_match.append(row)
            time.sleep(0.2)
            continue

        match = find_matching_deal(deal_list, id_empresa)
        if match:
            deal_id = match.get("id")
            current_ie = (match.get("properties", {}).get("id_empresa") or "").strip()
            deal_name = (match.get("properties", {}).get("dealname") or "").strip()

            if args.apply:
                try:
                    client.patch(
                        f"crm/v3/objects/deals/{deal_id}",
                        json_data={"properties": {"id_empresa": id_empresa}},
                    )
                    print(f"  {id_empresa}: UPDATED deal {deal_id} ({deal_name}) id_empresa {current_ie} → {id_empresa}")
                    print(f"    https://app.hubspot.com/contacts/{PORTAL_ID}/deal/{deal_id}")
                    updated += 1
                    # Log to edit_logs
                    conn_log = sqlite3.connect(str(db_path))
                    try:
                        from tools.scripts.hubspot.edit_log_db import log_edit
                        log_edit(
                            conn_log,
                            script="reconcile_missing_deals",
                            action="update_id_empresa",
                            outcome="success",
                            detail=f"{current_ie} → {id_empresa}",
                            deal_id=str(deal_id),
                            deal_name=(deal_name or "")[:200],
                            customer_cuit=(cuit_norm or "") if cuit_norm else "",
                        )
                    finally:
                        conn_log.close()
                except Exception as e:
                    print(f"  {id_empresa}: FAILED to update deal {deal_id}: {e}")
            else:
                print(f"  {id_empresa}: FOUND deal {deal_id} ({deal_name}) — id_empresa {current_ie} → {id_empresa}")
                print(f"    https://app.hubspot.com/contacts/{PORTAL_ID}/deal/{deal_id}")
        else:
            no_match.append(row)

        time.sleep(0.15)

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Updated (id_empresa fixed):  {updated}")
    print(f"  No company (CUIT missing):  {len(no_company)}")
    print(f"  No matching deal (create):   {len(no_match)}")
    if no_company:
        print()
        print("  No company for CUIT:")
        for r in no_company:
            print(f"    {r['id_empresa']} {r['email']} (cuit: {r.get('customer_cuit') or 'N/A'})")
    if no_match:
        print()
        print("  Create new deals for (REQUIRES CONFIRMATION before creating):")
        for r in no_match:
            print(f"    {r['id_empresa']} {r['email']} {r['plan']} ${r['amount']}")
        print()
        print("  ⚠️  Do NOT create these deals without explicit user confirmation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
