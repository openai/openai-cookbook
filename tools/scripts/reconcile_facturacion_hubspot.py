#!/usr/bin/env python3
"""
Reconciliation between Facturacion (billing) and HubSpot company CUITs.

Facturacion columns (semicolon-separated, header on row 2):
  Email; Customer Cuit; Plan description; Id Plan; Amount; Product CUIT

HubSpot export columns (comma-separated, quoted):
  Lifecycle Stage, Razón Social, CUIT, Type, Company ID

Logic (aligned with reconcile_billing_cuits_hubspot.py):
  - Customer Cuit = entity we invoice (who pays Colppy). This is the source of truth for HubSpot reconciliation.
  - Product CUIT = legal entity with the subscription (whose books are managed). Informational only.
  - Normalize all CUITs by stripping dashes
  - Match billing CUITs (Customer Cuit from facturacion) against HubSpot CUITs
  - Report: which Customer CUITs are NOT in HubSpot, revenue coverage by Customer Cuit, etc.
"""

import argparse
import csv
import sys
from pathlib import Path

from collections import defaultdict

# Default paths (aligned with reconcile_billing_cuits_hubspot.py)
SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
DEFAULT_FACTURACION = TOOLS_DIR / "outputs" / "facturacion.csv"
DEFAULT_HUBSPOT = TOOLS_DIR / "outputs" / "reporte-control-facturacion-p.csv"


def normalize_cuit(raw):
    """Strip dashes, whitespace, quotes. Return None if invalid."""
    if not raw:
        return None
    raw = raw.strip().strip('"').strip()
    raw = raw.replace("-", "")
    # Filter out invalid entries
    if raw in ("", "0", "#N/A", "NA", "N/A", "(Novalue)", "00000000000"):
        return None
    if raw == "1234567891":  # dummy
        return None
    # A valid Argentine CUIT is 11 digits
    if not raw.isdigit():
        return None
    if len(raw) != 11:
        return None
    if raw == "00000000000" or raw == "00000000001":
        return None
    return raw


def format_cuit(raw_11):
    """Format 11-digit CUIT as XX-XXXXXXXX-X"""
    return f"{raw_11[:2]}-{raw_11[2:10]}-{raw_11[10]}"


def load_facturacion(path):
    """Load facturacion CSV. Returns list of dicts with normalized CUITs."""
    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        # Row 1 is blank/garbage, row 2 is header
        lines = f.readlines()

    # Find header line
    header_idx = None
    for i, line in enumerate(lines):
        if "Email" in line and "Customer Cuit" in line:
            header_idx = i
            break
    if header_idx is None:
        print("ERROR: Could not find header in facturacion file")
        sys.exit(1)

    data_lines = lines[header_idx + 1:]
    for line in data_lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) < 6:
            continue
        email = parts[0].strip()
        customer_cuit_raw = parts[1].strip()
        plan = parts[2].strip()
        id_plan = parts[3].strip()
        amount = parts[4].strip()
        product_cuit_raw = parts[5].strip()

        customer_cuit = normalize_cuit(customer_cuit_raw)
        product_cuit = normalize_cuit(product_cuit_raw)

        # Skip if amount is suspiciously matching a CUIT field (data quality issue)
        if amount and normalize_cuit(amount):
            # This might be a shifted column
            pass

        records.append({
            "email": email,
            "customer_cuit_raw": customer_cuit_raw,
            "customer_cuit": customer_cuit,
            "plan": plan,
            "id_plan": id_plan,
            "amount": amount,
            "product_cuit_raw": product_cuit_raw,
            "product_cuit": product_cuit,
        })

    return records


def load_hubspot(path):
    """Load HubSpot export CSV. Returns list of dicts with normalized CUITs."""
    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cuit_raw = row.get("CUIT", "").strip()
            cuit = normalize_cuit(cuit_raw)
            records.append({
                "lifecycle_stage": row.get("Lifecycle Stage", "").strip(),
                "razon_social": row.get("Razón Social", row.get("Razon Social", "")).strip() if row.get("Razón Social", row.get("Razon Social", "")) else "",
                "cuit_raw": cuit_raw,
                "cuit": cuit,
                "type": row.get("Type", "").strip(),
                "company_id": row.get("Company ID", "").strip(),
            })
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile facturacion (billing) vs HubSpot company CUITs. Uses Customer Cuit as primary."
    )
    parser.add_argument(
        "--facturacion",
        type=str,
        default=str(DEFAULT_FACTURACION),
        help="Path to facturacion.csv (semicolon-separated)",
    )
    parser.add_argument(
        "--hubspot",
        type=str,
        default=str(DEFAULT_HUBSPOT),
        help="Path to HubSpot export CSV (reporte-control-facturacion-p)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("RECONCILIATION: Facturacion vs HubSpot CUITs")
    print("=" * 80)

    # Load data
    fact_records = load_facturacion(args.facturacion)
    hs_records = load_hubspot(args.hubspot)

    print(f"\n## Data Loaded")
    print(f"- Facturacion records: {len(fact_records)}")
    print(f"- HubSpot companies: {len(hs_records)}")

    # --- Facturacion analysis ---
    # Unique Product CUITs (the entity using the product)
    product_cuits = set()
    product_cuit_details = defaultdict(list)  # cuit -> list of records
    customer_cuits = set()
    customer_cuit_details = defaultdict(list)

    skipped_product = 0
    skipped_customer = 0

    for r in fact_records:
        if r["product_cuit"]:
            product_cuits.add(r["product_cuit"])
            product_cuit_details[r["product_cuit"]].append(r)
        else:
            skipped_product += 1

        if r["customer_cuit"]:
            customer_cuits.add(r["customer_cuit"])
            customer_cuit_details[r["customer_cuit"]].append(r)
        else:
            skipped_customer += 1

    # All billing CUITs = union of customer and product CUITs
    all_billing_cuits = product_cuits | customer_cuits

    print(f"\n## Facturacion CUIT Summary")
    print(f"- Unique Product CUITs (product users): {len(product_cuits)}")
    print(f"- Unique Customer CUITs (billing entities): {len(customer_cuits)}")
    print(f"- Total unique CUITs across both: {len(all_billing_cuits)}")
    print(f"- Records with invalid/missing Product CUIT: {skipped_product}")
    print(f"- Records with invalid/missing Customer CUIT: {skipped_customer}")

    # Same vs different CUIT
    same_cuit_count = 0
    diff_cuit_count = 0
    for r in fact_records:
        if r["product_cuit"] and r["customer_cuit"]:
            if r["product_cuit"] == r["customer_cuit"]:
                same_cuit_count += 1
            else:
                diff_cuit_count += 1
    print(f"- Records where Customer CUIT = Product CUIT: {same_cuit_count}")
    print(f"- Records where Customer CUIT ≠ Product CUIT: {diff_cuit_count}")

    # --- HubSpot analysis ---
    hs_cuits = set()
    hs_cuit_details = defaultdict(list)
    hs_no_cuit = 0

    for r in hs_records:
        if r["cuit"]:
            hs_cuits.add(r["cuit"])
            hs_cuit_details[r["cuit"]].append(r)
        else:
            hs_no_cuit += 1

    print(f"\n## HubSpot CUIT Summary")
    print(f"- Total companies: {len(hs_records)}")
    print(f"- Companies with valid CUIT: {len(hs_records) - hs_no_cuit}")
    print(f"- Unique CUITs: {len(hs_cuits)}")
    print(f"- Companies without valid CUIT: {hs_no_cuit}")

    # Lifecycle stage distribution
    lifecycle_counts = defaultdict(int)
    for r in hs_records:
        stage = r["lifecycle_stage"] if r["lifecycle_stage"] and r["lifecycle_stage"] != "(No value)" else "No value"
        lifecycle_counts[stage] += 1
    print(f"\n### HubSpot Lifecycle Stage Distribution")
    for stage, count in sorted(lifecycle_counts.items(), key=lambda x: -x[1]):
        print(f"  - {stage}: {count}")

    # Type distribution
    type_counts = defaultdict(int)
    for r in hs_records:
        t = r["type"] if r["type"] and r["type"] != "(No value)" else "No value"
        type_counts[t] += 1
    print(f"\n### HubSpot Type Distribution")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  - {t}: {count}")

    # ===================================================================
    # RECONCILIATION
    # ===================================================================
    print(f"\n{'=' * 80}")
    print("RECONCILIATION RESULTS")
    print(f"{'=' * 80}")

    # 1. Customer (Billing) CUITs in facturacion NOT in HubSpot [PRIMARY - source of truth]
    customer_not_in_hs = customer_cuits - hs_cuits
    print(f"\n## 1. Customer (Billing) CUITs in Facturacion NOT found in HubSpot: {len(customer_not_in_hs)} [PRIMARY]")
    if customer_not_in_hs:
        print(f"\n| # | Customer CUIT | Email | Plan | Amount |")
        print(f"|---|--------------|-------|------|--------|")
        for i, cuit in enumerate(sorted(customer_not_in_hs), 1):
            details = customer_cuit_details[cuit]
            plan_list = ", ".join(sorted(set(r["plan"] for r in details)))
            email_list = ", ".join(sorted(set(r["email"] for r in details))[:3])
            total_amount = sum(int(r["amount"]) for r in details if r["amount"].isdigit())
            print(f"| {i} | {format_cuit(cuit)} | {email_list} | {plan_list} | {total_amount} |")

    # 2. Product CUITs in facturacion NOT in HubSpot [informational]
    product_not_in_hs = product_cuits - hs_cuits
    print(f"\n## 2. Product CUITs in Facturacion NOT found in HubSpot: {len(product_not_in_hs)} [informational]")
    if product_not_in_hs:
        print(f"\n| # | Product CUIT | Email | Plan | Amount |")
        print(f"|---|-------------|-------|------|--------|")
        for i, cuit in enumerate(sorted(product_not_in_hs), 1):
            details = product_cuit_details[cuit]
            plan_list = ", ".join(sorted(set(r["plan"] for r in details)))
            email_list = ", ".join(sorted(set(r["email"] for r in details))[:3])
            total_amount = sum(int(r["amount"]) for r in details if r["amount"].isdigit())
            print(f"| {i} | {format_cuit(cuit)} | {email_list} | {plan_list} | {total_amount} |")

    # 3. All billing CUITs not in HubSpot
    all_not_in_hs = all_billing_cuits - hs_cuits
    print(f"\n## 3. ALL Billing CUITs (Product + Customer) NOT in HubSpot: {len(all_not_in_hs)}")

    # 4. Customer (Billing) CUITs FOUND in HubSpot [PRIMARY]
    customer_in_hs = customer_cuits & hs_cuits
    print(f"\n## 4. Customer (Billing) CUITs FOUND in HubSpot: {len(customer_in_hs)} / {len(customer_cuits)} [PRIMARY]")

    # 5. Product CUITs FOUND in HubSpot [informational]
    product_in_hs = product_cuits & hs_cuits
    print(f"\n## 5. Product CUITs in Facturacion FOUND in HubSpot: {len(product_in_hs)} / {len(product_cuits)} [informational]")

    # 6. HubSpot CUITs NOT in any facturacion CUIT
    hs_not_in_billing = hs_cuits - all_billing_cuits
    print(f"\n## 6. HubSpot CUITs NOT in Facturacion (neither Product nor Customer): {len(hs_not_in_billing)}")

    # Breakdown by lifecycle stage and type for the non-billing HubSpot CUITs
    hs_not_in_billing_lifecycle = defaultdict(int)
    hs_not_in_billing_type = defaultdict(int)
    for cuit in hs_not_in_billing:
        for r in hs_cuit_details[cuit]:
            stage = r["lifecycle_stage"] if r["lifecycle_stage"] and r["lifecycle_stage"] != "(No value)" else "No value"
            t = r["type"] if r["type"] and r["type"] != "(No value)" else "No value"
            hs_not_in_billing_lifecycle[stage] += 1
            hs_not_in_billing_type[t] += 1

    print(f"\n### Lifecycle Stage of HubSpot companies NOT in billing:")
    for stage, count in sorted(hs_not_in_billing_lifecycle.items(), key=lambda x: -x[1]):
        print(f"  - {stage}: {count}")

    print(f"\n### Type of HubSpot companies NOT in billing:")
    for t, count in sorted(hs_not_in_billing_type.items(), key=lambda x: -x[1]):
        print(f"  - {t}: {count}")

    # 7. Plan distribution for matched vs unmatched (by Customer Cuit - primary)
    print(f"\n## 7. Plan Distribution Analysis (by Customer Cuit)")
    matched_plans = defaultdict(int)
    unmatched_plans = defaultdict(int)
    for r in fact_records:
        if r["customer_cuit"]:
            if r["customer_cuit"] in hs_cuits:
                matched_plans[r["plan"]] += 1
            else:
                unmatched_plans[r["plan"]] += 1

    print(f"\n### Plans for Customer CUITs FOUND in HubSpot:")
    for plan, count in sorted(matched_plans.items(), key=lambda x: -x[1]):
        print(f"  - {plan}: {count}")

    print(f"\n### Plans for Customer CUITs NOT in HubSpot:")
    for plan, count in sorted(unmatched_plans.items(), key=lambda x: -x[1]):
        print(f"  - {plan}: {count}")

    # 8. Revenue impact of unmatched CUITs (by Customer Cuit - we bill the Customer Cuit)
    print(f"\n## 8. Revenue Impact of Unmatched Customer (Billing) CUITs")
    total_revenue_matched = 0
    total_revenue_unmatched = 0
    for r in fact_records:
        if r["customer_cuit"] and r["amount"].isdigit():
            amt = int(r["amount"])
            if r["customer_cuit"] in hs_cuits:
                total_revenue_matched += amt
            else:
                total_revenue_unmatched += amt

    total_revenue = total_revenue_matched + total_revenue_unmatched
    print(f"- Total billing amount (valid Customer CUITs): {total_revenue:,}")
    print(f"- Matched in HubSpot: {total_revenue_matched:,} ({100*total_revenue_matched/total_revenue:.1f}%)" if total_revenue > 0 else "")
    print(f"- NOT matched in HubSpot: {total_revenue_unmatched:,} ({100*total_revenue_unmatched/total_revenue:.1f}%)" if total_revenue > 0 else "")

    # 9. Duplicate CUITs in HubSpot (same CUIT, multiple companies)
    print(f"\n## 9. Duplicate CUITs in HubSpot (same CUIT, multiple companies)")
    dup_count = 0
    for cuit, records in sorted(hs_cuit_details.items(), key=lambda x: -len(x[1])):
        if len(records) > 1:
            dup_count += 1
            if dup_count <= 30:
                names = "; ".join(r["razon_social"][:40] for r in records[:5])
                types = "; ".join((r["type"] if r["type"] and r["type"] != "(No value)" else "N/A") for r in records[:5])
                print(f"  - {format_cuit(cuit)} ({len(records)} companies): {names} | Types: {types}")
    print(f"  Total CUITs with multiple companies: {dup_count}")

    # 10. Cases where Customer CUIT ≠ Product CUIT analysis
    print(f"\n## 10. Billing Intermediary Analysis (Customer CUIT ≠ Product CUIT)")
    intermediary_cases = []
    for r in fact_records:
        if r["customer_cuit"] and r["product_cuit"] and r["customer_cuit"] != r["product_cuit"]:
            intermediary_cases.append(r)

    print(f"- Total records with billing intermediary: {len(intermediary_cases)}")

    # Group by customer CUIT to find accountant/billing patterns
    by_customer = defaultdict(list)
    for r in intermediary_cases:
        by_customer[r["customer_cuit"]].append(r)

    print(f"- Unique billing entities (Customer CUITs) acting as intermediaries: {len(by_customer)}")
    print(f"\n### Top Billing Intermediaries (most product CUITs billed):")
    print(f"| # | Customer CUIT | Email | # Products Billed | In HubSpot? |")
    print(f"|---|--------------|-------|--------------------|-------------|")
    for i, (cust_cuit, records) in enumerate(sorted(by_customer.items(), key=lambda x: -len(x[1]))[:30], 1):
        unique_products = len(set(r["product_cuit"] for r in records if r["product_cuit"]))
        email = records[0]["email"]
        in_hs = "Yes" if cust_cuit in hs_cuits else "NO"
        print(f"| {i} | {format_cuit(cust_cuit)} | {email} | {unique_products} | {in_hs} |")

    # ===================================================================
    # SUMMARY
    # ===================================================================
    print(f"\n{'=' * 80}")
    print("EXECUTIVE SUMMARY")
    print(f"{'=' * 80}")
    pct_cust = (100 * len(customer_in_hs) / len(customer_cuits)) if customer_cuits else 0
    pct_cust_miss = (100 * len(customer_not_in_hs) / len(customer_cuits)) if customer_cuits else 0
    pct_prod = (100 * len(product_in_hs) / len(product_cuits)) if product_cuits else 0
    pct_prod_miss = (100 * len(product_not_in_hs) / len(product_cuits)) if product_cuits else 0
    pct_hs = (100 * len(hs_not_in_billing) / len(hs_cuits)) if hs_cuits else 0
    pct_rev_match = (100 * total_revenue_matched / total_revenue) if total_revenue else 0
    pct_rev_unmatch = (100 * total_revenue_unmatched / total_revenue) if total_revenue else 0

    print(f"""
## Coverage Metrics (Customer Cuit = primary for reconciliation)
- Customer (billing) CUITs: {len(customer_cuits)}
- Customer CUITs found in HubSpot: {len(customer_in_hs)} ({pct_cust:.1f}%)
- Customer CUITs MISSING from HubSpot: {len(customer_not_in_hs)} ({pct_cust_miss:.1f}%)

- Product CUITs in billing (informational): {len(product_cuits)}
- Product CUITs found in HubSpot: {len(product_in_hs)} ({pct_prod:.1f}%)
- Product CUITs MISSING from HubSpot: {len(product_not_in_hs)} ({pct_prod_miss:.1f}%)

- HubSpot companies with CUIT: {len(hs_cuits)}
- HubSpot CUITs not in any billing: {len(hs_not_in_billing)} ({pct_hs:.1f}%)

## Revenue Coverage (by Customer Cuit)
- Billing amount matched to HubSpot: {total_revenue_matched:,} ({pct_rev_match:.1f}%)
- Billing amount NOT matched: {total_revenue_unmatched:,} ({pct_rev_unmatch:.1f}%)
""")


if __name__ == "__main__":
    main()
