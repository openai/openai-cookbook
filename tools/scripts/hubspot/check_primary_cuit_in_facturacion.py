#!/usr/bin/env python3
"""
Check if deals (closed won, not in facturación) have primary company CUIT in facturación.
If the primary company's CUIT appears in facturación, there's at least a relationship.
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/data/facturacion_hubspot.db"


def normalize_cuit(raw: str) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    if len(digits) != 11 or not digits.isdigit():
        return None
    return digits


def get_facturacion_cuits(conn) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT customer_cuit FROM facturacion WHERE customer_cuit IS NOT NULL AND TRIM(customer_cuit) != ''"
    ).fetchall()
    return {normalize_cuit(r[0]) for r in rows if normalize_cuit(r[0])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--csv", required=True, help="Path to closedwon_not_facturacion CSV")
    args = parser.parse_args()

    # Load id_empresa from CSV
    id_empresas = []
    with open(args.csv, encoding="utf-8") as f:
        next(f)  # header
        for line in f:
            parts = line.strip().split(";")
            if parts:
                id_empresas.append(parts[0].strip())

    conn = sqlite3.connect(args.db)
    fact_cuits = get_facturacion_cuits(conn)
    conn.close()

    from tools.hubspot_api.client import get_hubspot_client
    client = get_hubspot_client()

    # Search deals by id_empresa
    resp = client.search_objects(
        object_type="deals",
        filter_groups=[{"filters": [{"propertyName": "id_empresa", "operator": "IN", "values": id_empresas}]}],
        properties=["dealname", "id_empresa", "amount", "closedate", "fecha_primer_pago"],
        limit=100,
    )
    deals = {r["id"]: r for r in resp.get("results", [])}
    id_to_deal = {(r.get("properties", {}).get("id_empresa") or "").strip(): r for r in deals.values()}

    # Get associations for each deal
    deal_to_primary_company = {}
    for deal_id in deals:
        assoc = client.get(
            f"crm/v4/objects/deals/{deal_id}/associations/companies",
            params={"limit": 500},
        )
        for a in assoc.get("results", []):
            for t in a.get("associationTypes", []):
                if t.get("typeId") == 5:
                    deal_to_primary_company[str(deal_id)] = str(a.get("toObjectId"))
                    break
            else:
                continue
            break

    primary_company_ids = list(set(deal_to_primary_company.values()))

    # Batch read companies for CUIT
    company_cuit = {}
    if primary_company_ids:
        for i in range(0, len(primary_company_ids), 100):
            chunk = primary_company_ids[i : i + 100]
            resp = client.post(
                "crm/v3/objects/companies/batch/read",
                json_data={"inputs": [{"id": cid} for cid in chunk], "properties": ["name", "cuit"]},
            )
            for r in resp.get("results", []):
                cid = str(r.get("id"))
                cuit = (r.get("properties", {}).get("cuit") or "").strip()
                company_cuit[cid] = (cuit, (r.get("properties", {}).get("name") or "").strip())

    # Build report
    print("id_empresa | deal_name | amount | closedate | fecha_primer_pago | primary_company | primary_cuit | cuit_in_fact")
    print("-" * 120)
    matches = 0
    for ie in id_empresas:
        deal = id_to_deal.get(ie)
        if not deal:
            print(f"{ie} | (deal not found)")
            continue
        deal_id = deal["id"]
        props = deal.get("properties", {})
        name = (props.get("dealname") or "")[:30]
        amount = props.get("amount", "")
        closedate = (props.get("closedate") or "")[:10]
        fecha_pago = (props.get("fecha_primer_pago") or "").strip()[:10] or "(empty)"
        primary_id = deal_to_primary_company.get(str(deal_id))
        if not primary_id:
            print(f"{ie} | {name} | {amount} | {closedate} | {fecha_pago} | (no primary) | |")
            continue
        cuit_raw, comp_name = company_cuit.get(primary_id, ("", ""))
        cuit_norm = normalize_cuit(cuit_raw)
        in_fact = "YES" if cuit_norm and cuit_norm in fact_cuits else "NO"
        if in_fact == "YES":
            matches += 1
        print(f"{ie} | {name} | {amount} | {closedate} | {fecha_pago} | {(comp_name or '')[:25]} | {cuit_raw or '(empty)'} | {in_fact}")

    print("-" * 100)
    print(f"Primary company CUIT in facturación: {matches} / {len(id_empresas)}")


if __name__ == "__main__":
    main()
