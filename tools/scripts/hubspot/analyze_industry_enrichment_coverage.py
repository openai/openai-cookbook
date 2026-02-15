#!/usr/bin/env python3
"""
Industry Enrichment Coverage Analysis
=====================================
Analyzes how much the industria (and type) fields are populated across HubSpot companies.

Segments:
1. All companies with CUIT (billing-relevant pool)
2. Billing companies only (from facturacion.csv)

Usage:
    python tools/scripts/hubspot/analyze_industry_enrichment_coverage.py
    python tools/scripts/hubspot/analyze_industry_enrichment_coverage.py --billing-only
    python tools/scripts/hubspot/analyze_industry_enrichment_coverage.py --max-companies 5000
"""
import argparse
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}


def normalize_cuit(raw: str) -> str | None:
    """Normalize CUIT to 11 digits."""
    if not raw:
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


def parse_billing_cuits(facturacion_path: str) -> set[str]:
    """Parse facturacion.csv and return unique Customer Cuit (billing) CUITs."""
    path = Path(facturacion_path)
    if not path.exists():
        return set()

    with open(path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    header_idx = None
    for i, line in enumerate(lines):
        if "Email" in line and "Customer Cuit" in line:
            header_idx = i
            break
    if header_idx is None:
        return set()

    cuits = set()
    for line in lines[header_idx + 1 :]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) < 2:
            continue
        n = normalize_cuit(parts[1].strip())
        if n:
            cuits.add(n)
    return cuits


def fetch_companies_with_cuit(
    client,
    max_results: int = 10000,
    batch_size: int = 100,
    delay: float = 0.25,
) -> list[dict]:
    """Fetch HubSpot companies that have CUIT populated."""
    all_results = []
    after = None

    while len(all_results) < max_results:
        try:
            response = client.search_objects(
                object_type="companies",
                filter_groups=[{"filters": [{"propertyName": "cuit", "operator": "HAS_PROPERTY"}]}],
                properties=["name", "cuit", "industria", "type", "lifecyclestage"],
                limit=batch_size,
                after=after,
            )
        except Exception as e:
            print(f"  Warning: Search failed ({e})")
            break

        results = response.get("results", [])
        if not results:
            break

        all_results.extend(results)
        if len(results) < batch_size:
            break

        after = response.get("paging", {}).get("next", {}).get("after")
        if not after:
            break

        time.sleep(delay)

    return all_results


def analyze_companies(companies: list[dict], segment_name: str) -> dict:
    """Aggregate industria and type coverage from company list."""
    total = len(companies)
    with_industria = 0
    without_industria = 0
    with_type = 0
    without_type = 0
    both = 0
    neither = 0
    industria_values: dict[str, int] = defaultdict(int)
    type_values: dict[str, int] = defaultdict(int)

    for c in companies:
        props = c.get("properties", {})
        ind = (props.get("industria") or "").strip()
        typ = (props.get("type") or "").strip()

        has_ind = bool(ind and ind != "(No value)")
        has_typ = bool(typ and typ != "(No value)")

        if has_ind:
            with_industria += 1
            industria_values[ind] += 1
        else:
            without_industria += 1

        if has_typ:
            with_type += 1
            type_values[typ] += 1
        else:
            without_type += 1

        if has_ind and has_typ:
            both += 1
        elif not has_ind and not has_typ:
            neither += 1

    return {
        "segment": segment_name,
        "total": total,
        "with_industria": with_industria,
        "without_industria": without_industria,
        "with_type": with_type,
        "without_type": without_type,
        "both": both,
        "neither": neither,
        "industria_values": dict(industria_values),
        "type_values": dict(type_values),
    }


def print_report(data: dict) -> None:
    """Print analysis report to stdout."""
    t = data["total"]
    if t == 0:
        print("  No companies to analyze.")
        return

    wi = data["with_industria"]
    wo = data["without_industria"]
    wt = data["with_type"]
    wot = data["without_type"]
    both = data["both"]
    neither = data["neither"]

    pct_ind = 100 * wi / t
    pct_typ = 100 * wt / t
    pct_both = 100 * both / t
    pct_neither = 100 * neither / t

    print(f"\n  Total companies: {t:,}")
    print(f"  With industria:   {wi:,} ({pct_ind:.1f}%)")
    print(f"  Without industria: {wo:,} ({100 - pct_ind:.1f}%)")
    print(f"  With type:       {wt:,} ({pct_typ:.1f}%)")
    print(f"  Without type:    {wot:,} ({100 - pct_typ:.1f}%)")
    print(f"  Both populated: {both:,} ({pct_both:.1f}%)")
    print(f"  Neither:        {neither:,} ({pct_neither:.1f}%)")

    if data["industria_values"]:
        print(f"\n  Top 10 industria values:")
        for val, cnt in sorted(data["industria_values"].items(), key=lambda x: -x[1])[:10]:
            pct = 100 * cnt / t
            print(f"    - {val[:50]}: {cnt:,} ({pct:.1f}%)")

    if data["type_values"]:
        print(f"\n  Type distribution:")
        for val, cnt in sorted(data["type_values"].items(), key=lambda x: -x[1])[:12]:
            pct = 100 * cnt / t
            print(f"    - {val}: {cnt:,} ({pct:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze industry (industria) and type enrichment coverage in HubSpot"
    )
    parser.add_argument(
        "--billing-only",
        action="store_true",
        help="Only analyze billing companies (skip 10k CUIT pool, fewer API calls)",
    )
    parser.add_argument(
        "--facturacion",
        default="tools/outputs/facturacion.csv",
        help="Path to facturacion.csv",
    )
    parser.add_argument(
        "--max-companies",
        type=int,
        default=10000,
        help="Max companies to fetch (default 10000)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Delay between API calls in seconds (default 0.3)",
    )
    args = parser.parse_args()

    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()

    print("=" * 70)
    print("INDUSTRY ENRICHMENT COVERAGE ANALYSIS")
    print("=" * 70)

    # 1. Full pool (optional)
    if not args.billing_only:
        print(f"\nFetching companies with CUIT (max {args.max_companies})...")
        companies = fetch_companies_with_cuit(
            client,
            max_results=args.max_companies,
            delay=args.delay,
        )
        print(f"  Fetched {len(companies)} companies")
        if companies:
            full_data = analyze_companies(companies, "Companies with CUIT")
            print("\n" + "-" * 70)
            print("## SEGMENT: All companies with CUIT (sample)")
            print("-" * 70)
            print_report(full_data)

    # 2. Billing companies (facturacion focus): fetch ALL billing companies via batch lookup (complete picture)
    billing_cuits = parse_billing_cuits(args.facturacion)
    if billing_cuits:
        # Batch-fetch billing companies by CUIT (bypasses 10k limit for targeted lookup)
        print(f"\nFetching all {len(billing_cuits)} billing companies by CUIT...")
        billing_companies = []
        cuit_list = sorted(billing_cuits)
        batch_size = 25
        for i in range(0, len(cuit_list), batch_size):
            batch = cuit_list[i : i + batch_size]
            values = [format_cuit_display(c) for c in batch] + list(batch)  # both formats
            values = list(dict.fromkeys(values))
            after = None
            while True:
                try:
                    resp = client.search_objects(
                        object_type="companies",
                        filter_groups=[{"filters": [{"propertyName": "cuit", "operator": "IN", "values": values}]}],
                        properties=["name", "cuit", "industria", "type", "lifecyclestage"],
                        limit=100,
                        after=after,
                    )
                    for r in resp.get("results", []):
                        billing_companies.append(r)
                    after = resp.get("paging", {}).get("next", {}).get("after")
                    if not after:
                        break
                    time.sleep(args.delay)
                except Exception as e:
                    print(f"  Warning: Batch {i//batch_size + 1} failed: {e}")
                    break
            time.sleep(args.delay)
        # Dedupe by CUIT: one company per billing CUIT (facturacion focus)
        # When multiple HubSpot companies share same CUIT, prefer one with type or industria
        cuit_to_company = {}
        for c in billing_companies:
            n = normalize_cuit(c.get("properties", {}).get("cuit"))
            if not n:
                continue
            existing = cuit_to_company.get(n)
            if not existing:
                cuit_to_company[n] = c
            else:
                p, ep = c.get("properties", {}), existing.get("properties", {})
                has_both = bool(((p.get("type") or "").strip()) and ((p.get("industria") or "").strip()))
                existing_has = bool(((ep.get("type") or "").strip()) and ((ep.get("industria") or "").strip()))
                if has_both and not existing_has:
                    cuit_to_company[n] = c
        billing_companies = list(cuit_to_company.values())
        not_found = len(billing_cuits) - len(billing_companies)
        print(f"  Billing CUITs in facturacion: {len(billing_cuits)}")
        print(f"  Found in HubSpot (1 per CUIT): {len(billing_companies)}")
        if not_found > 0:
            print(f"  Not in HubSpot: {not_found}")

        if billing_companies:
            billing_data = analyze_companies(billing_companies, "Billing companies")
            print("\n" + "-" * 70)
            print("## SEGMENT: Billing companies (facturacion Customer Cuit, 1 per CUIT)")
            print("-" * 70)
            print_report(billing_data)

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
