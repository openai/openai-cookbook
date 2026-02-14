#!/usr/bin/env python3
"""
Infer Better Names for Numeric-Only Company Names in HubSpot
===========================================================
When a company in HubSpot has a name that is just a number (e.g. "64481", "53114"),
it is likely an internal id or id_empresa. This script infers a better name from:

1. Deal names: When this company bills for deals (via facturacion), extract the
   business name from deal_name patterns like "95973 - PayGoal Uruguay" or "55406 Coordline".
2. Email domain: Extract domain from facturacion emails (e.g. admin@paygoal.io → PayGoal).
   Skips personal domains (gmail, hotmail, yahoo, etc.).

Proposed format: "{id} - {InferredName}" for traceability (e.g. "64481 - PayGoal Uruguay").

Usage:
    python tools/scripts/hubspot/infer_numeric_company_names.py
    python tools/scripts/hubspot/infer_numeric_company_names.py --dry-run
    python tools/scripts/hubspot/infer_numeric_company_names.py --apply
    python tools/scripts/hubspot/infer_numeric_company_names.py --db path/to/facturacion_hubspot.db
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
PORTAL_ID = "19877595"
COMPANY_URL = f"https://app.hubspot.com/contacts/{PORTAL_ID}/company/{{id}}"

# Personal email domains - skip for domain-based inference
PERSONAL_DOMAINS = frozenset({
    "gmail.com", "hotmail.com", "yahoo.com", "yahoo.com.ar", "outlook.com",
    "live.com", "icloud.com", "hotmail.com.ar", "outlook.com.ar",
})


def is_numeric_only(s: str) -> bool:
    """Return True if string is non-empty and contains only digits."""
    return bool(s and s.strip().isdigit())


def extract_name_from_deal(deal_name: str, id_empresa: str) -> str | None:
    """
    Extract business name from deal_name patterns like:
    - "95973 - PayGoal Uruguay" → "PayGoal Uruguay"
    - "55406 Coordline" → "Coordline"
    - "61255 - INDUSTRIAS PETROLA SRL" → "INDUSTRIAS PETROLA SRL"
    """
    if not deal_name or not deal_name.strip():
        return None
    s = deal_name.strip()
    if s.startswith(f"{id_empresa} - "):
        return s[len(id_empresa) + 3 :].strip()
    if s.startswith(f"{id_empresa} "):
        return s[len(id_empresa) :].strip()
    m = re.match(r"^\d+\s*[-–]\s*(.+)$", s)
    if m:
        return m.group(1).strip()
    m = re.match(r"^\d+\s+(.+)$", s)
    if m:
        return m.group(1).strip()
    return None


def domain_to_company_name(email: str) -> str | None:
    """
    Extract domain from email and convert to company name.
    e.g. admin@paygoal.io → PayGoal. Skips personal domains.
    """
    if not email or "@" not in email:
        return None
    domain = email.split("@")[-1].lower().strip()
    if not domain or domain in PERSONAL_DOMAINS:
        return None
    base = domain.split(".")[0]
    if not base or len(base) < 2:
        return None
    return base.capitalize()


def infer_numeric_company_names(db_path: str) -> list[dict]:
    """
    Query DB for companies with numeric-only names and infer better names.
    Returns list of dicts with hubspot_id, current_name, proposed_name, source, etc.
    """
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT c.hubspot_id, c.name, c.cuit
        FROM companies c
        WHERE c.name GLOB '[0-9]*' AND c.name NOT GLOB '*[^0-9]*'
        ORDER BY c.name
        """
    ).fetchall()

    results = []
    for hubspot_id, current_name, cuit in rows:
        deal_names = conn.execute(
            """
            SELECT DISTINCT d.deal_name, d.id_empresa
            FROM facturacion f
            JOIN deals d ON d.id_empresa = f.id_empresa
            WHERE f.customer_cuit = ?
            AND d.deal_name IS NOT NULL AND d.deal_name != ''
            """,
            (cuit,),
        ).fetchall()

        inferred_from_deal = None
        for dn, ie in deal_names:
            extracted = extract_name_from_deal(dn, ie)
            if extracted and len(extracted) > 2 and not extracted.isdigit():
                inferred_from_deal = extracted
                break

        emails = conn.execute(
            """
            SELECT DISTINCT f.email FROM facturacion f
            WHERE f.customer_cuit = ? AND f.email IS NOT NULL
            """,
            (cuit,),
        ).fetchall()

        inferred_from_domain = None
        for (em,) in emails:
            n = domain_to_company_name(em)
            if n:
                inferred_from_domain = n
                break

        inferred = inferred_from_deal or inferred_from_domain
        source = (
            "deal_name"
            if inferred_from_deal
            else ("email_domain" if inferred_from_domain else None)
        )
        proposed = f"{current_name} - {inferred}" if inferred else None

        results.append({
            "hubspot_id": hubspot_id,
            "current_name": current_name,
            "cuit": cuit,
            "proposed_name": proposed,
            "source": source,
            "deal_names": [d[0] for d in deal_names[:3]],
            "emails": [e[0] for e in emails[:3]],
        })

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Infer better names for HubSpot companies with numeric-only names"
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"Path to facturacion_hubspot.db (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to HubSpot. Default: dry-run (no changes).",
    )
    args = parser.parse_args()

    path = Path(args.db)
    if not path.exists():
        print(f"ERROR: Database not found: {path}")
        sys.exit(1)

    results = infer_numeric_company_names(str(path))
    with_inference = [r for r in results if r["proposed_name"]]
    without_inference = [r for r in results if not r["proposed_name"]]

    print("=" * 80)
    print("INFER NUMERIC COMPANY NAMES - HubSpot companies with numeric-only names")
    print("=" * 80)
    print(f"\nTotal: {len(results)} | With inference: {len(with_inference)} | No inference: {len(without_inference)}")

    if with_inference:
        print("\n--- PROPOSED RENAMES (with inference) ---")
        for r in with_inference:
            url = COMPANY_URL.format(id=r["hubspot_id"])
            print(f"\n  [{r['current_name']}] → [{r['proposed_name']}]")
            print(f"  Source: {r['source']} | HubSpot: {url}")
            if r["deal_names"]:
                print(f"  Deals: {r['deal_names']}")
            if r["emails"]:
                print(f"  Emails: {r['emails']}")

    if without_inference:
        print("\n--- NO INFERENCE (manual review) ---")
        for r in without_inference:
            url = COMPANY_URL.format(id=r["hubspot_id"])
            print(f"  {r['current_name']} | {url} | Emails: {r['emails']}")

    if args.apply and with_inference:
        print("\n--- APPLYING UPDATES ---")
        from tools.hubspot_api.client import get_hubspot_client

        client = get_hubspot_client()
        for i in range(0, len(with_inference), 100):
            batch = with_inference[i : i + 100]
            inputs = [
                {
                    "id": r["hubspot_id"],
                    "properties": {"name": r["proposed_name"]},
                }
                for r in batch
            ]
            try:
                client.post("crm/v3/objects/companies/batch/update", {"inputs": inputs})
                print(f"  Updated {len(batch)} companies")
            except Exception as e:
                print(f"  Batch update failed: {e}")
                sys.exit(1)
            time.sleep(0.2)
        print(f"\nDone. Updated {len(with_inference)} companies.")
    elif args.apply and not with_inference:
        print("\n--- Nothing to apply (no inferences). ---")
    elif not args.apply:
        print("\n--- DRY RUN: No changes applied. Use --apply to update HubSpot. ---")


if __name__ == "__main__":
    main()
