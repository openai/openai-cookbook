#!/usr/bin/env python3
"""
ICP Type population from billing data (Customer Cuit = who we bill).

Products are billed to a CUIT. Target model: no "Empresa Administrada" - we only classify
the billing entity (Customer Cuit).

Logic:
- Customer Cuit = Product CUIT (self-billed) + accountant plan → Cuenta Contador
- Customer Cuit = Product CUIT (self-billed) + regular plan → Cuenta Pyme
- Customer Cuit ≠ Product CUIT (bills for other products) → Cuenta Contador

MIGRATION: Some plans still have "empresa administrada" structure. Use --migration-mode
to also classify Product CUITs (Customer≠Product) as Empresa Administrada until migration
completes. Do NOT run --revert-empresa-administrada during migration.

Usage:
    python tools/scripts/hubspot/icp_type_from_billing.py
    python tools/scripts/hubspot/icp_type_from_billing.py --migration-mode  # During migration: also set Empresa Administrada for Product CUITs
    python tools/scripts/hubspot/icp_type_from_billing.py --facturacion path/to/facturacion.csv --dry-run
    python tools/scripts/hubspot/icp_type_from_billing.py --revert-empresa-administrada  # AFTER migration: fix companies wrongly set to Empresa Administrada
    python tools/scripts/hubspot/icp_type_from_billing.py --fix-empresa-administrada-accountants  # Empresa Administrada + industria contabilidad → Cuenta Contador
"""
import argparse
import csv
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

ACCOUNTANT_PLANS = [
    "Contador Independiente",
    "Contador Independiente + Sueldos",
    "Contador Inicio + Sueldos",
    "Consultoras y Estudios",
    "Consultoras y Estudios + Sueldos",
    "Consultoras y Estudios + Sueldos + Portal",
]

ACCOUNTANT_COMPANY_TYPES = [
    "Cuenta Contador",
    "Cuenta Contador y Reseller",
    "Contador Robado",
]

# Industria values that indicate accounting (Contabilidad, impuestos, legales)
INDUSTRIA_CONTABILIDAD = "Contabilidad, impuestos, legales"

EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}


def normalize_cuit(raw: str) -> str | None:
    """Normalize CUIT to 11 digits."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    if len(digits) != 11 or not digits.isdigit():
        return None
    if digits in EXCLUDE_CUITS:
        return None
    return digits


def format_cuit_display(digits: str) -> str:
    """Format 11 digits as XX-XXXXXXXX-X."""
    if not digits or len(digits) != 11:
        return str(digits)
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"


def load_facturacion(path: str) -> list[dict]:
    """Load facturacion CSV. Returns list of dicts with normalized CUITs."""
    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    header_idx = None
    for i, line in enumerate(lines):
        if "Email" in line and "Customer Cuit" in line:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Header not found in facturacion file")

    for line in lines[header_idx + 1 :]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) < 6:
            continue
        customer_cuit = normalize_cuit(parts[1].strip())
        product_cuit = normalize_cuit(parts[5].strip())
        if not customer_cuit:
            continue
        records.append({
            "email": parts[0].strip(),
            "customer_cuit": customer_cuit,
            "plan": parts[2].strip(),
            "amount": parts[4].strip(),
            "product_cuit": product_cuit,
        })
    return records


def derive_billing_segmentation(customer_records: list[dict]) -> tuple[str, str]:
    """
    Derive suggested type for a Customer Cuit (billing entity).

    Returns:
        (suggested_type, reason)
    """
    has_intermediary = False
    has_self_billed = False
    plans = set()

    for r in customer_records:
        plans.add(r["plan"])
        if r["product_cuit"]:
            if r["customer_cuit"] == r["product_cuit"]:
                has_self_billed = True
            else:
                has_intermediary = True

    if has_intermediary:
        n_products = len(set(r["product_cuit"] for r in customer_records if r["product_cuit"] and r["customer_cuit"] != r["product_cuit"]))
        return "Cuenta Contador", f"Bills for {n_products} product(s) (intermediary)"

    if has_self_billed:
        accountant_plans = [p for p in plans if p in ACCOUNTANT_PLANS]
        if accountant_plans:
            return "Cuenta Contador", f"Self-billed with accountant plan: {', '.join(accountant_plans[:2])}"
        return "Cuenta Pyme", f"Self-billed with plan: {', '.join(sorted(plans)[:2])}"

    return "Cuenta Pyme", "Self-billed (no product CUIT)"


def fetch_companies_by_cuits(cuits: list[str], batch_size: int = 20) -> dict[str, list[dict]]:
    """
    Fetch HubSpot companies by CUIT. Returns cuit -> list of company objects.
    """
    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    cuit_to_companies: dict[str, list[dict]] = defaultdict(list)

    for i in range(0, len(cuits), batch_size):
        batch = cuits[i : i + batch_size]
        values = []
        for c in batch:
            values.append(format_cuit_display(c))
            values.append(c)
        values = list(dict.fromkeys(values))

        after = None
        while True:
            try:
                response = client.search_objects(
                    object_type="companies",
                    filter_groups=[{"filters": [{"propertyName": "cuit", "operator": "IN", "values": values}]}],
                    properties=["name", "cuit", "type", "hs_object_id"],
                    limit=100,
                    after=after,
                )
                for r in response.get("results", []):
                    props = r.get("properties", {})
                    n = normalize_cuit(props.get("cuit"))
                    if n:
                        cuit_to_companies[n].append({
                            "id": r.get("id"),
                            "name": props.get("name"),
                            "cuit": props.get("cuit"),
                            "type": props.get("type") or "(No value)",
                        })
                after = response.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
                time.sleep(0.15)
            except Exception as e:
                print(f"  Warning: Batch fetch failed ({e})")
                break

        time.sleep(0.15)

    return dict(cuit_to_companies)


def pick_company_for_cuit(companies: list[dict]) -> dict | None:
    """Pick one company when multiple share same CUIT. Prefer one with type."""
    if not companies:
        return None
    typed = [c for c in companies if c.get("type") and c["type"] != "(No value)"]
    return (typed[0] if typed else companies[0])


def _revert_empresa_administrada(facturacion_path: str, dry_run: bool) -> int:
    """
    Revert companies that were Product CUIT (Customer≠Product) from Empresa Administrada
    to Cuenta Pyme. Empresa Administrada concept is deprecated.
    """
    records = load_facturacion(facturacion_path)
    product_cuits_with_intermediary = set()
    for r in records:
        if r["product_cuit"] and r["customer_cuit"] and r["customer_cuit"] != r["product_cuit"]:
            product_cuits_with_intermediary.add(r["product_cuit"])

    print(f"Product CUITs (billed by another entity): {len(product_cuits_with_intermediary)}")
    cuit_to_companies = fetch_companies_by_cuits(sorted(product_cuits_with_intermediary))

    to_revert = []
    for cuit in product_cuits_with_intermediary:
        companies = cuit_to_companies.get(cuit)
        if not companies:
            continue
        company = pick_company_for_cuit(companies)
        if company and (company.get("type") or "") == "Empresa Administrada":
            to_revert.append((company["id"], company.get("name", "")))

    print(f"Companies with Empresa Administrada to revert: {len(to_revert)}")
    if not to_revert:
        return 0

    if dry_run:
        for i, (cid, name) in enumerate(to_revert[:20], 1):
            print(f"  {i}. {cid} ({name[:40]}) → Cuenta Pyme")
        if len(to_revert) > 20:
            print(f"  ... and {len(to_revert) - 20} more")
        return 0

    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    for i in range(0, len(to_revert), 100):
        batch = to_revert[i : i + 100]
        inputs = [{"id": cid, "properties": {"type": "Cuenta Pyme"}} for cid, _ in batch]
        try:
            client.post("crm/v3/objects/companies/batch/update", {"inputs": inputs})
        except Exception as e:
            print(f"  Batch update failed: {e}")
            return 1
        time.sleep(0.2)

    print(f"Reverted {len(to_revert)} companies to Cuenta Pyme.")
    return 0


def _fix_empresa_administrada_accountants(dry_run: bool) -> int:
    """
    Fix companies with type=Empresa Administrada and industria=Contabilidad, impuestos, legales.
    Sets type to Cuenta Contador (they are accountant firms, misclassified).
    """
    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    filter_groups = [
        {
            "filters": [
                {"propertyName": "type", "operator": "EQ", "value": "Empresa Administrada"},
                {"propertyName": "industria", "operator": "EQ", "value": INDUSTRIA_CONTABILIDAD},
            ]
        }
    ]
    companies = client.get_all_objects(
        object_type="companies",
        filter_groups=filter_groups,
        properties=["name", "cuit", "type", "industria"],
    )

    if not companies:
        print("No companies with Empresa Administrada + industria contabilidad found.")
        return 0

    print(f"Found {len(companies)} companies: Empresa Administrada + industria={INDUSTRIA_CONTABILIDAD}")
    for i, c in enumerate(companies[:20], 1):
        props = c.get("properties", {})
        name = (props.get("name") or "")[:50]
        cid = c.get("id", "")
        print(f"  {i}. {cid} ({name}) → Cuenta Contador")
    if len(companies) > 20:
        print(f"  ... and {len(companies) - 20} more")

    if dry_run:
        return 0

    to_update = [(c["id"], "Cuenta Contador") for c in companies]
    for i in range(0, len(to_update), 100):
        batch = to_update[i : i + 100]
        inputs = [{"id": cid, "properties": {"type": new_type}} for cid, new_type in batch]
        try:
            client.post("crm/v3/objects/companies/batch/update", {"inputs": inputs})
        except Exception as e:
            print(f"  Batch update failed: {e}")
            return 1
        time.sleep(0.2)

    print(f"Updated {len(to_update)} companies to Cuenta Contador.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Populate Company type from billing data (Customer Cuit vs Product CUIT)"
    )
    parser.add_argument(
        "--facturacion",
        default="tools/outputs/facturacion.csv",
        help="Path to facturacion.csv",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only analyze, do not update HubSpot",
    )
    parser.add_argument(
        "--revert-empresa-administrada",
        action="store_true",
        help="Revert companies (Product CUIT when Customer≠Product) from Empresa Administrada to Cuenta Pyme. Do NOT run during migration.",
    )
    parser.add_argument(
        "--fix-empresa-administrada-accountants",
        action="store_true",
        help="Fix companies with Empresa Administrada + industria=Contabilidad, impuestos, legales → Cuenta Contador.",
    )
    parser.add_argument(
        "--migration-mode",
        action="store_true",
        help="During migration: also classify Product CUITs (Customer≠Product) as Empresa Administrada. Some plans still have this structure.",
    )
    args = parser.parse_args()

    if args.fix_empresa_administrada_accountants:
        return _fix_empresa_administrada_accountants(args.dry_run)

    path = Path(args.facturacion)
    if not path.exists():
        print(f"ERROR: Facturacion file not found: {path}")
        sys.exit(1)

    if args.revert_empresa_administrada:
        return _revert_empresa_administrada(str(path), args.dry_run)

    print("=" * 80)
    mode = " [MIGRATION MODE - also Product CUITs → Empresa Administrada]" if args.migration_mode else ""
    print(f"ICP TYPE FROM BILLING - Customer Cuit (billing entity) segmentation{mode}")
    print("=" * 80)

    records = load_facturacion(str(path))
    print(f"\nLoaded {len(records)} facturacion records")

    # Group by Customer Cuit (billing entity - who we bill)
    by_customer = defaultdict(list)
    for r in records:
        by_customer[r["customer_cuit"]].append(r)

    # Derive suggested type for each Customer Cuit only (no Product CUIT classification)
    customer_suggestions: dict[str, tuple[str, str]] = {}
    for cuit, recs in by_customer.items():
        customer_suggestions[cuit] = derive_billing_segmentation(recs)

    # Product CUITs (Customer≠Product) - only in migration mode
    product_cuits: set[str] = set()
    if args.migration_mode:
        for r in records:
            if r["product_cuit"] and r["customer_cuit"] and r["customer_cuit"] != r["product_cuit"]:
                product_cuits.add(r["product_cuit"])
        product_cuits -= set(customer_suggestions.keys())  # Exclude if already Customer Cuit
        print(f"Product CUITs (Empresa Administrada during migration): {len(product_cuits)}")

    # Process billing entities (Customer Cuit) + optionally Product CUITs
    all_cuits = set(customer_suggestions.keys()) | product_cuits
    print(f"Unique CUITs to process: {len(all_cuits)}")

    # Fetch HubSpot companies
    print(f"\nFetching HubSpot companies for {len(all_cuits)} CUITs...")
    cuit_to_companies = fetch_companies_by_cuits(sorted(all_cuits))
    print(f"  Found {len(cuit_to_companies)} CUITs in HubSpot")

    # Build update list: (company_id, suggested_type, reason, source)
    updates: list[tuple[str, str, str, str]] = []
    for cuit in all_cuits:
        companies = cuit_to_companies.get(cuit)
        if not companies:
            continue

        company = pick_company_for_cuit(companies)
        if not company:
            continue

        current_type = company.get("type") or "(No value)"

        # Customer Cuit (billing entity) or Product CUIT (migration: Empresa Administrada)
        if cuit in customer_suggestions:
            cust_type, cust_reason = customer_suggestions[cuit]
            if cust_type and (current_type == "(No value)" or current_type != cust_type):
                if current_type in ACCOUNTANT_COMPANY_TYPES and cust_type == "Cuenta Pyme":
                    continue
                updates.append((company["id"], cust_type, cust_reason, "customer_cuit"))
        elif cuit in product_cuits and args.migration_mode:
            # Migration: Product CUIT (billed by another entity) → Empresa Administrada
            if current_type == "(No value)" or current_type != "Empresa Administrada":
                updates.append((company["id"], "Empresa Administrada", "Product CUIT (billed by another entity)", "product_cuit_migration"))

    # Dedupe by company ID (keep last)
    seen = {}
    for cid, stype, reason, src in updates:
        seen[cid] = (stype, reason, src)
    updates = [(cid, stype, reason, src) for cid, (stype, reason, src) in seen.items()]

    # Report
    print(f"\n## Segmentation summary")
    cust_dist = defaultdict(int)
    for cuit, (stype, _) in customer_suggestions.items():
        cust_dist[stype] += 1
    if args.migration_mode and product_cuits:
        cust_dist["Empresa Administrada"] = cust_dist.get("Empresa Administrada", 0) + len(product_cuits)
    for t, count in sorted(cust_dist.items(), key=lambda x: -x[1]):
        print(f"  - {t}: {count}")

    print(f"\n## Companies to update: {len(updates)}")
    if not updates:
        print("No updates needed.")
        return 0

    if args.dry_run:
        print("\n[DRY RUN] Would update:")
        for i, (cid, stype, reason, src) in enumerate(updates[:30], 1):
            print(f"  {i}. Company {cid} → {stype} ({reason} [{src}])")
        if len(updates) > 30:
            print(f"  ... and {len(updates) - 30} more")
        return 0

    # Batch update
    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    batch_size = 100
    updated = 0
    for i in range(0, len(updates), batch_size):
        batch = updates[i : i + batch_size]
        inputs = [{"id": cid, "properties": {"type": stype}} for cid, stype, _, _ in batch]
        try:
            result = client.post("crm/v3/objects/companies/batch/update", {"inputs": inputs})
            updated += len(batch)
        except Exception as e:
            print(f"  Batch update failed: {e}")
            break

        time.sleep(0.2)

    print(f"\nUpdated {updated} companies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
