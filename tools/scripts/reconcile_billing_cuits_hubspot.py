#!/usr/bin/env python3
"""
Full reconciliation: Billing CUITs (facturacion.csv) vs HubSpot Companies with CUIT.

Strategy:
1. Fetch HubSpot companies with CUIT via search (pagination, max 10k due to HubSpot API limit)
2. Batch-verify "missing" CUITs using IN operator (bypasses 10k limit for targeted lookup)
3. Output billing CUITs NOT found in HubSpot

Usage:
    python tools/scripts/reconcile_billing_cuits_hubspot.py
    python tools/scripts/reconcile_billing_cuits_hubspot.py --facturacion path/to/facturacion.csv
"""
import argparse
import csv
import re
import sys
import time
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv

load_dotenv()


def normalize_cuit_for_matching(cuit_str: str) -> "str | None":
    """
    Normalize CUIT to 11 digits for matching.
    Strips dashes, spaces, dots - any non-digit.
    """
    if cuit_str is None or (isinstance(cuit_str, str) and not str(cuit_str).strip()):
        return None
    digits = re.sub(r"[^\d]", "", str(cuit_str).strip())
    if len(digits) != 11 or not digits.isdigit():
        return None
    return digits


def format_cuit_display(digits: str) -> str:
    """Format 11 digits as XX-XXXXXXXX-X for display."""
    if not digits or len(digits) != 11:
        return str(digits)
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"


EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}

# HubSpot Search API limit per query
HUBSPOT_SEARCH_LIMIT = 10000


def fetch_hubspot_cuits_paginated(max_results: int = HUBSPOT_SEARCH_LIMIT) -> set[str]:
    """
    Fetch HubSpot companies with CUIT via paginated search.
    Stops at max_results (HubSpot API limits to 10k per query).
    """
    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    hub_cuits = set()
    after = None
    total = 0

    filter_groups = [{"filters": [{"propertyName": "cuit", "operator": "HAS_PROPERTY"}]}]
    properties = ["name", "cuit", "type"]

    while total < max_results:
        try:
            response = client.search_objects(
                object_type="companies",
                filter_groups=filter_groups,
                properties=properties,
                limit=100,
                after=after,
            )
        except Exception as e:
            print(f"  Warning: Search API failed ({e}). Using batch verification only.")
            break

        results = response.get("results", [])
        for r in results:
            n = normalize_cuit_for_matching(r.get("properties", {}).get("cuit"))
            if n and n not in EXCLUDE_CUITS:
                hub_cuits.add(n)

        total += len(results)
        if not results:
            break

        paging = response.get("paging", {})
        after = paging.get("next", {}).get("after")
        if not after:
            break

        time.sleep(0.15)  # Rate limiting

    return hub_cuits


def batch_verify_cuits_in_hubspot(cuits: list[str], batch_size: int = 20) -> set[str]:
    """
    Verify which CUITs exist in HubSpot using IN operator (bypasses 10k search limit).
    Returns set of CUITs that were found.
    """
    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    found = set()

    for i in range(0, len(cuits), batch_size):
        batch = cuits[i : i + batch_size]
        # Search with both formats (HubSpot stores mixed)
        values = []
        for c in batch:
            values.append(format_cuit_display(c))
            values.append(c)  # digits-only
        values = list(dict.fromkeys(values))  # dedupe

        try:
            response = client.search_objects(
                object_type="companies",
                filter_groups=[{"filters": [{"propertyName": "cuit", "operator": "IN", "values": values}]}],
                properties=["cuit"],
                limit=100,
            )
            for r in response.get("results", []):
                n = normalize_cuit_for_matching(r.get("properties", {}).get("cuit"))
                if n:
                    found.add(n)
        except Exception as e:
            print(f"  Warning: Batch verify failed for batch {i//batch_size + 1}: {e}")

        time.sleep(0.15)

    return found


def parse_billing_cuits(facturacion_path: str):
    """Parse facturacion.csv and return (unique_cuits, details_by_cuit)."""
    path = Path(facturacion_path)
    if not path.exists():
        raise FileNotFoundError(f"Facturacion file not found: {facturacion_path}")

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Skip first row (junk), use row 2 as header
    reader = csv.DictReader(
        lines[2:],
        delimiter=";",
        fieldnames=[
            "Email",
            "Customer Cuit",
            "Plan description",
            "Id Plan",
            "Amount",
            "Product CUIT",
        ],
        restkey="extra",
    )
    rows = list(reader)

    billing_cuits = set()
    billing_details = {}

    for row in rows:
        cuit = row.get("Customer Cuit", "").strip()
        n = normalize_cuit_for_matching(cuit)
        if n and n not in EXCLUDE_CUITS:
            billing_cuits.add(n)
            if n not in billing_details:
                billing_details[n] = []
            billing_details[n].append(
                {
                    "email": row.get("Email", ""),
                    "plan": row.get("Plan description", ""),
                    "amount": row.get("Amount", ""),
                }
            )

    return billing_cuits, billing_details


def run_reconciliation(
    facturacion_path: str,
    output_path: "str | None" = None,
) -> dict:
    """
    Run full reconciliation and optionally write output CSV.

    Returns:
        Dict with counts and missing_cuits list.
    """
    # 1. Parse billing first
    print(f"Parsing {facturacion_path}...")
    billing_cuits, billing_details = parse_billing_cuits(facturacion_path)
    print(f"  Found {len(billing_cuits)} unique billing CUITs")

    # 2. Fetch HubSpot companies with CUIT (paginated, max 10k)
    print("Fetching HubSpot companies with CUIT (paginated, max 10k)...")
    try:
        hub_cuits = fetch_hubspot_cuits_paginated()
        print(f"  Retrieved {len(hub_cuits)} companies with CUIT from search")
    except Exception as e:
        print(f"  Search failed ({e}). Using batch verification only.")
        hub_cuits = set()

    # 3. Initial reconcile
    missing = billing_cuits - hub_cuits
    matched = billing_cuits & hub_cuits

    # 4. Batch-verify "missing" CUITs (bypasses HubSpot 10k search limit)
    if missing:
        print(f"Batch-verifying {len(missing)} initially-missing CUITs...")
        try:
            verified_found = batch_verify_cuits_in_hubspot(sorted(missing))
            hub_cuits.update(verified_found)
            missing = billing_cuits - hub_cuits
            matched = billing_cuits & hub_cuits
            print(f"  Found {len(verified_found)} more in HubSpot. Remaining missing: {len(missing)}")
        except Exception as e:
            print(f"  Batch verify failed ({e}). Using initial results.")

    print("")
    print("=" * 60)
    print("RECONCILIATION RESULTS")
    print("=" * 60)
    print(f"Billing CUITs (total):     {len(billing_cuits)}")
    print(f"HubSpot companies w/CUIT:  {len(hub_cuits)}")
    print(f"Matched (in both):         {len(matched)} ({100 * len(matched) / len(billing_cuits):1.1f}%)")
    print(f"NOT in HubSpot:            {len(missing)} ({100 * len(missing) / len(billing_cuits):1.1f}%)")
    print("=" * 60)

    # 4. Write output if path provided
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("CUIT;Email;Plan;Amount\n")
            for c in sorted(missing):
                fmt = format_cuit_display(c)
                d = billing_details.get(c, [{}])[0]
                email = d.get("email", "") if isinstance(d, dict) else ""
                plan = d.get("plan", "") if isinstance(d, dict) else ""
                amount = d.get("amount", "") if isinstance(d, dict) else ""
                f.write(f"{fmt};{email};{plan};{amount}\n")
        print(f"\nWrote {len(missing)} rows to {output_path}")

    return {
        "billing_cuits": len(billing_cuits),
        "hub_cuits": len(hub_cuits),
        "matched": len(matched),
        "matched_cuits": matched,
        "missing": len(missing),
        "missing_cuits": sorted(missing),
        "billing_details": billing_details,
    }


def check_industry_enrichment(matched_cuits: set[str], facturacion_path: str = "tools/outputs/facturacion.csv") -> dict:
    """
    Check industria enrichment status for billing companies that exist in HubSpot.

    Returns:
        Dict with total, with_industria, without_industria, and sample companies.
    """
    from tools.hubspot_api.client import get_hubspot_client

    def fmt(c: str) -> str:
        return f"{c[:2]}-{c[2:10]}-{c[10]}" if len(c) == 11 else c

    client = get_hubspot_client()
    all_companies = []
    cuit_list = sorted(matched_cuits)
    batch_size = 25

    for i in range(0, len(cuit_list), batch_size):
        batch = cuit_list[i : i + batch_size]
        values = [fmt(c) for c in batch]
        try:
            resp = client.search_objects(
                object_type="companies",
                filter_groups=[
                    {"filters": [{"propertyName": "cuit", "operator": "IN", "values": values}]}
                ],
                properties=["name", "cuit", "industria", "type"],
                limit=100,
            )
            for r in resp.get("results", []):
                all_companies.append(r)
            time.sleep(0.2)
        except Exception as e:
            print(f"  Warning: Batch error: {e}")

    by_id = {c["id"]: c for c in all_companies}
    companies = list(by_id.values())

    with_industria = sum(
        1
        for c in companies
        if c.get("properties", {}).get("industria")
        and str(c["properties"]["industria"]).strip()
        and c["properties"]["industria"] != "(No value)"
    )
    without = len(companies) - with_industria

    return {
        "total": len(companies),
        "with_industria": with_industria,
        "without_industria": without,
        "companies": companies,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile billing CUITs vs HubSpot companies (full pagination)"
    )
    parser.add_argument(
        "--facturacion",
        default="tools/outputs/facturacion.csv",
        help="Path to facturacion.csv",
    )
    parser.add_argument(
        "--output",
        default="tools/outputs/billing_cuits_not_in_hubspot.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--check-industry",
        action="store_true",
        help="Also check industria enrichment status for matched billing companies",
    )
    parser.add_argument(
        "--industry-only",
        action="store_true",
        help="Only run industry check (skip full reconcile, use facturacion CUITs directly)",
    )
    args = parser.parse_args()

    if args.industry_only:
        billing_cuits, _ = parse_billing_cuits(args.facturacion)
        print("INDUSTRY ENRICHMENT CHECK (billing companies in HubSpot)")
        print("-" * 50)
        industry_result = check_industry_enrichment(billing_cuits, args.facturacion)
        total = industry_result["total"]
        with_ind = industry_result["with_industria"]
        without = industry_result["without_industria"]
        pct = 100 * with_ind / total if total else 0
        print(f"Billing companies in HubSpot: {total}")
        print(f"  With industria: {with_ind} ({pct:.1f}%)")
        print(f"  Without industria: {without} ({100 - pct:.1f}%)")
        return 0

    result = run_reconciliation(
        facturacion_path=args.facturacion,
        output_path=args.output,
    )

    if args.check_industry:
        print("\n" + "=" * 60)
        print("INDUSTRY ENRICHMENT CHECK (billing companies in HubSpot)")
        print("=" * 60)
        industry_result = check_industry_enrichment(result["matched_cuits"], args.facturacion)
        total = industry_result["total"]
        with_ind = industry_result["with_industria"]
        without = industry_result["without_industria"]
        pct = 100 * with_ind / total if total else 0
        print(f"Billing companies in HubSpot: {total}")
        print(f"  With industria: {with_ind} ({pct:.1f}%)")
        print(f"  Without industria: {without} ({100 - pct:.1f}%)")
        print("=" * 60)

    return 0 if result["missing"] == 0 else 0  # Exit 0 always for reporting


if __name__ == "__main__":
    sys.exit(main())
