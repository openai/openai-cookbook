#!/usr/bin/env python3
"""
Fix HubSpot Deal id_empresa — Use Colppy id_empresa
===================================================
Colppy is source of truth. HubSpot deals MUST use Colppy id_empresa to match.
When a deal has CRM id_empresa (e.g. 97897) but Colppy uses a different id (87956)
for the same company, update the deal to use Colppy id_empresa.

Mapping (Nov 2025 Colppy-only cases): 97897→87956, 97896→87957, 103741→88337.
Also updates dealname to "{colppy_id} - Company Name" for consistency.

Usage:
    python tools/scripts/hubspot/fix_colppy_id_empresa_on_deals.py --dry-run
    python tools/scripts/hubspot/fix_colppy_id_empresa_on_deals.py --apply
    python tools/scripts/hubspot/fix_colppy_id_empresa_on_deals.py --apply --mapping "97897:87956,97896:87957,103741:88337"
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

DEFAULT_DB = "tools/data/facturacion_hubspot.db"
PORTAL_ID = "19877595"

# Default mapping: CRM id_empresa → Colppy id_empresa (same CUIT, Colppy dictates)
DEFAULT_MAPPING = {
    "97897": "87956",   # ENCONCRETO SOLUCIONES
    "97896": "87957",   # DESARROLLOS CONSTRUCTIVOS SUDAMERICANOS
    "103741": "88337",  # COOPERATIVA FLOR DEL ALBA
}


def parse_mapping(s: str) -> dict[str, str]:
    """Parse 'crm1:colppy1,crm2:colppy2' into {crm1: colppy1, ...}."""
    out = {}
    for part in (s or "").strip().split(","):
        part = part.strip()
        if ":" in part:
            crm, colppy = part.split(":", 1)
            out[crm.strip()] = colppy.strip()
    return out


def build_dealname(colppy_id: str, old_name: str) -> str:
    """Build dealname as '{colppy_id} - Company Name' from old 'crm_id - Company Name'."""
    if not old_name:
        return f"{colppy_id} - "
    # Strip leading "crm_id - " or "crm_id- "
    match = re.match(r"^\d+\s*-\s*(.+)$", old_name.strip())
    if match:
        rest = match.group(1).strip()
        return f"{colppy_id} - {rest}"
    return f"{colppy_id} - {old_name}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update HubSpot deal id_empresa from CRM id to Colppy id (Colppy is source of truth)"
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to facturacion_hubspot.db")
    parser.add_argument("--dry-run", action="store_true", help="Only report, do not update HubSpot")
    parser.add_argument("--apply", action="store_true", help="Update id_empresa and dealname in HubSpot")
    parser.add_argument(
        "--mapping",
        type=str,
        help="Override mapping: crm1:colppy1,crm2:colppy2 (default: 97897:87956,97896:87957,103741:88337)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply")
        return 1

    mapping = parse_mapping(args.mapping) if args.mapping else DEFAULT_MAPPING
    if not mapping:
        print("No mapping specified.")
        return 1

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get deals with crm id_empresa
    placeholders = ",".join("?" * len(mapping))
    cur = conn.execute(
        f"""
        SELECT id_empresa, hubspot_id, deal_name
        FROM deals
        WHERE id_empresa IN ({placeholders}) AND hubspot_id IS NOT NULL AND hubspot_id != ''
        """,
        list(mapping.keys()),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        print("No deals found with CRM id_empresa in mapping.")
        return 0

    print(f"Found {len(rows)} deal(s) to update (CRM → Colppy id_empresa):")
    print()

    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    updated = 0

    for r in rows:
        crm_id = str(r["id_empresa"])
        colppy_id = mapping.get(crm_id)
        if not colppy_id:
            continue

        hubspot_id = r["hubspot_id"]
        old_name = r["deal_name"] or ""
        new_name = build_dealname(colppy_id, old_name)

        if args.apply:
            try:
                client.patch(
                    f"crm/v3/objects/deals/{hubspot_id}",
                    json_data={
                        "properties": {
                            "id_empresa": colppy_id,
                            "dealname": new_name,
                        }
                    },
                )
                print(f"  {crm_id} → {colppy_id}: UPDATED deal {hubspot_id}")
                print(f"    dealname: {old_name[:50]}... → {new_name[:50]}...")
                print(f"    https://app.hubspot.com/contacts/{PORTAL_ID}/deal/{hubspot_id}")

                # Update local DB
                conn = sqlite3.connect(str(db_path))
                conn.execute(
                    "UPDATE deals SET id_empresa = ?, deal_name = ? WHERE hubspot_id = ?",
                    (colppy_id, new_name, hubspot_id),
                )
                conn.commit()

                # Log
                from tools.scripts.hubspot.edit_log_db import ensure_edit_log_table, log_edit

                ensure_edit_log_table(conn)
                log_edit(
                    conn,
                    script="fix_colppy_id_empresa_on_deals",
                    action="update_id_empresa",
                    outcome="success",
                    detail=f"{crm_id} → {colppy_id}",
                    deal_id=str(hubspot_id),
                    deal_name=new_name[:200],
                )
                conn.close()

                updated += 1
            except Exception as e:
                print(f"  {crm_id} → {colppy_id}: FAILED deal {hubspot_id}: {e}")
        else:
            print(f"  {crm_id} → {colppy_id}: would update deal {hubspot_id} ({old_name[:40]}...)")
            print(f"    new dealname: {new_name[:60]}...")

        time.sleep(0.15)

    print()
    print("=" * 60)
    print(f"  Updated: {updated}")

    if args.apply and updated > 0:
        print()
        print("  Run build_facturacion_hubspot_mapping.py --refresh-deals-only to refresh local DB.")
        print("  Then re-run Colppy ↔ HubSpot reconciliation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
