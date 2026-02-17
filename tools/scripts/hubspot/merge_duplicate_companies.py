#!/usr/bin/env python3
"""
Merge Duplicate HubSpot Companies
=================================
Merges two company records with the same CUIT into one.
Uses: POST /crm/v3/objects/companies/merge

primaryObjectId: Company to KEEP (receives associations from the other)
objectIdToMerge: Company to MERGE INTO primary (will be archived)

Logs successful merges to edit_logs table in facturacion_hubspot.db.

Usage:
    python tools/scripts/hubspot/merge_duplicate_companies.py PRIMARY_ID SECONDARY_ID
    python tools/scripts/hubspot/merge_duplicate_companies.py 19681795121 9018759242 --dry-run
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/data/facturacion_hubspot.db"


def merge_companies(client, primary_id: str, secondary_id: str) -> dict:
    """
    Merge secondary company into primary via HubSpot API.

    Args:
        client: HubSpot API client
        primary_id: HubSpot ID of company to KEEP
        secondary_id: HubSpot ID of company to merge INTO primary

    Returns:
        API response with merged company
    """
    endpoint = "crm/v3/objects/companies/merge"
    payload = {
        "primaryObjectId": str(primary_id),
        "objectIdToMerge": str(secondary_id),
    }
    return client.post(endpoint, payload)


def main():
    parser = argparse.ArgumentParser(
        description="Merge duplicate HubSpot companies (same CUIT)"
    )
    parser.add_argument(
        "primary_id",
        help="HubSpot ID of company to KEEP (receives associations)",
    )
    parser.add_argument(
        "secondary_id",
        help="HubSpot ID of company to merge INTO primary (will be archived)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to facturacion_hubspot.db for edit log")
    args = parser.parse_args()

    if args.dry_run:
        print(
            f"[DRY-RUN] Would merge company {args.secondary_id} INTO {args.primary_id}"
        )
        print("  primaryObjectId (keep):", args.primary_id)
        print("  objectIdToMerge (archive):", args.secondary_id)
        return 0

    from tools.hubspot_api.client import get_hubspot_client
    from tools.scripts.hubspot.edit_log_db import log_edit

    client = get_hubspot_client()
    try:
        result = merge_companies(client, args.primary_id, args.secondary_id)
        print("Merge successful.")
        props = result.get("properties", {})
        merged_name = props.get("name", "N/A")
        print(f"  Merged company: {merged_name} (ID: {result.get('id')})")

        # Log to edit_logs in DB
        db_path = Path(args.db)
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                log_edit(
                    conn,
                    script="merge_duplicate_companies",
                    action="merge",
                    outcome="success",
                    detail=f"Merged {args.secondary_id} into {args.primary_id}",
                    company_id=str(args.primary_id),
                    company_name=merged_name,
                    company_id_secondary=str(args.secondary_id),
                )
            finally:
                conn.close()
        return 0
    except Exception as e:
        print(f"Merge failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
