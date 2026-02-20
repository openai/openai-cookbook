#!/usr/bin/env python3
"""
December 2025 Closed Won vs Facturación
=======================================
All closed won deals with close date December 2025 should be in facturación
(invoicing for January 2026). This script lists ALL such deals and checks:
- In facturación? (id_empresa present)
- fecha_primer_pago? (first payment date in HubSpot)
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/data/facturacion_hubspot.db"


def main():
    from tools.hubspot_api.client import get_hubspot_client

    conn = sqlite3.connect(DEFAULT_DB)
    fact_ids = {
        str(r[0]).strip()
        for r in conn.execute(
            "SELECT DISTINCT id_empresa FROM facturacion WHERE id_empresa IS NOT NULL AND TRIM(id_empresa) != ''"
        ).fetchall()
    }
    conn.close()

    client = get_hubspot_client()
    all_deals = []
    after = None
    props = ["dealname", "id_empresa", "amount", "closedate", "fecha_primer_pago", "hs_object_id"]
    filter_groups = [
        {
            "filters": [
                {"propertyName": "dealstage", "operator": "IN", "values": ["closedwon", "34692158"]},
                {"propertyName": "closedate", "operator": "GTE", "value": "2025-12-01"},
                {"propertyName": "closedate", "operator": "LTE", "value": "2025-12-31"},
            ]
        }
    ]
    while True:
        resp = client.search_objects(
            object_type="deals",
            filter_groups=filter_groups,
            properties=props,
            limit=100,
            after=after,
        )
        results = resp.get("results", [])
        all_deals.extend(results)
        after = resp.get("paging", {}).get("next", {}).get("after")
        if not after:
            break

    # Dedupe by id_empresa (keep first)
    by_id = {}
    for d in all_deals:
        ie = (d.get("properties", {}).get("id_empresa") or "").strip()
        if ie and ie not in by_id:
            by_id[ie] = d

    in_fact = []
    not_in_fact = []
    for ie, d in sorted(by_id.items(), key=lambda x: -float(x[1].get("properties", {}).get("amount") or 0)):
        p = d.get("properties", {})
        closedate = (p.get("closedate") or "")[:10]
        fecha_pago = (p.get("fecha_primer_pago") or "").strip()[:10] or "(empty)"
        name = (p.get("dealname") or "")[:40]
        amount = p.get("amount", "")
        row = (ie, name, amount, closedate, fecha_pago)
        if ie in fact_ids:
            in_fact.append(row)
        else:
            not_in_fact.append(row)

    print("=" * 100)
    print("DECEMBER 2025 CLOSED WON: Full reconciliation vs Facturación")
    print("=" * 100)
    print(f"\nTotal closed won Dec 2025 (unique id_empresa): {len(by_id)}")
    print(f"In facturación: {len(in_fact)}")
    print(f"NOT in facturación: {len(not_in_fact)}")
    print("\n--- IN FACTURACIÓN ---")
    print("id_empresa | deal_name | amount | closedate | fecha_primer_pago")
    print("-" * 90)
    for ie, name, amt, cd, fp in in_fact:
        print(f"{ie:<10} | {name:<40} | {amt:>10} | {cd} | {fp}")

    print("\n--- NOT IN FACTURACIÓN (should not exist) ---")
    print("id_empresa | deal_name | amount | closedate | fecha_primer_pago")
    print("-" * 90)
    for ie, name, amt, cd, fp in not_in_fact:
        print(f"{ie:<10} | {name:<40} | {amt:>10} | {cd} | {fp}")

    # fecha_primer_pago summary
    with_fecha_in = sum(1 for r in in_fact if r[4] != "(empty)")
    with_fecha_not = sum(1 for r in not_in_fact if r[4] != "(empty)")
    without_fecha_in = len(in_fact) - with_fecha_in
    without_fecha_not = len(not_in_fact) - with_fecha_not

    print("\n--- FECHA_PRIMER_PAGO SUMMARY ---")
    print(f"In facturación:    {with_fecha_in} with fecha_primer_pago, {without_fecha_in} without")
    print(f"NOT in facturación: {with_fecha_not} with fecha_primer_pago, {without_fecha_not} without")
    print("\nDeals NOT in facturación but WITH fecha_primer_pago = paid per HubSpot, sync issue.")
    print("Deals NOT in facturación and WITHOUT fecha_primer_pago = may not have paid yet.")


if __name__ == "__main__":
    main()
