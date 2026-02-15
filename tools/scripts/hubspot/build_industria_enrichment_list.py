#!/usr/bin/env python3
"""
Build HubSpot List (Segment) - Companies Needing Industria Enrichment
=====================================================================
Creates a HubSpot list containing billing companies (from facturacion) that exist
in HubSpot but do NOT have industria populated. Use this list to trigger the
industry enrichment workflow or for manual enrichment.

Modes:
- MANUAL: Fetches companies, creates list, adds via API (HubSpot caps manual list at 100 members)
- DYNAMIC: Creates list with filters - includes ALL companies with CUIT and no industria (~20k)
- PROPERTY-BASED: Sets industria_enrichment_batch=true on facturacion companies, creates DYNAMIC list
  filtered by that property - exact 1369 companies, no 100 limit

Uses HubSpot Lists API:
- POST /crm/v3/lists - Create list (MANUAL or DYNAMIC)
- PUT /crm/v3/lists/{listId}/memberships/add - Add company IDs (MANUAL only)

Usage:
    python tools/scripts/hubspot/build_industria_enrichment_list.py --property-based  # Recommended
    python tools/scripts/hubspot/build_industria_enrichment_list.py --dynamic
    python tools/scripts/hubspot/build_industria_enrichment_list.py --dry-run
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}
DEFAULT_LIST_NAME = "Empresas facturacion sin industria - Enrichment"
DEFAULT_DYNAMIC_LIST_NAME = "Empresas sin industria - Dynamic (CUIT + sin industria)"
DEFAULT_PROPERTY_LIST_NAME = "Empresas facturacion sin industria - Static (1369)"
COMPANY_OBJECT_TYPE = "0-2"  # HubSpot object type for companies
ADD_MEMBERSHIPS_BATCH = 100
BATCH_UPDATE_SIZE = 100
INDUSTRIA_ENRICHMENT_PROP = "industria_enrichment_batch"


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


def fetch_billing_companies_without_industria(
    client,
    billing_cuits: set[str],
    facturacion_path: str,
    delay: float = 0.35,
) -> list[dict]:
    """
    Fetch billing companies from HubSpot, return those WITHOUT industria.
    One company per CUIT; dedupes when multiple HubSpot records share same CUIT.
    """
    billing_companies = []
    cuit_list = sorted(billing_cuits)
    batch_size = 25

    for i in range(0, len(cuit_list), batch_size):
        batch = cuit_list[i : i + batch_size]
        values = [format_cuit_display(c) for c in batch] + list(batch)
        values = list(dict.fromkeys(values))
        after = None
        while True:
            try:
                resp = client.search_objects(
                    object_type="companies",
                    filter_groups=[{"filters": [{"propertyName": "cuit", "operator": "IN", "values": values}]}],
                    properties=["name", "cuit", "industria", "type"],
                    limit=100,
                    after=after,
                )
                for r in resp.get("results", []):
                    billing_companies.append(r)
                after = resp.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
                time.sleep(delay)
            except Exception as e:
                print(f"  Warning: Batch {i//batch_size + 1} failed: {e}")
                break
        time.sleep(delay)

    # Dedupe by CUIT: one company per billing CUIT; prefer one WITHOUT industria (for our list)
    cuit_to_company = {}
    for c in billing_companies:
        n = normalize_cuit(c.get("properties", {}).get("cuit"))
        if not n:
            continue
        p = c.get("properties", {})
        ind = (p.get("industria") or "").strip()
        has_industria = bool(ind and ind != "(No value)")

        existing = cuit_to_company.get(n)
        if not existing:
            cuit_to_company[n] = c
        else:
            ep = existing.get("properties", {})
            existing_has = bool((ep.get("industria") or "").strip() and (ep.get("industria") or "").strip() != "(No value)")
            # Prefer company WITHOUT industria (we're building the "need enrichment" list)
            if not has_industria and existing_has:
                cuit_to_company[n] = c

    # Filter to those WITHOUT industria
    without_industria = []
    for c in cuit_to_company.values():
        ind = (c.get("properties", {}).get("industria") or "").strip()
        if not ind or ind == "(No value)":
            without_industria.append(c)

    return without_industria


def create_list_manual(client, name: str, dry_run: bool) -> str | None:
    """Create a MANUAL company list. Returns listId or None."""
    if dry_run:
        print(f"  [DRY RUN] Would create MANUAL list: {name}")
        return "dry-run-list-id"

    payload = {
        "name": name,
        "objectTypeId": COMPANY_OBJECT_TYPE,
        "processingType": "MANUAL",
    }
    try:
        resp = client.post("crm/v3/lists", payload)
        list_data = resp.get("list", resp)
        list_id = list_data.get("listId") or list_data.get("id")
        print(f"  Created MANUAL list: {name} (ID: {list_id})")
        return str(list_id)
    except Exception as e:
        print(f"  ERROR creating list: {e}")
        return None


def _create_list_dynamic_raw(payload: dict) -> tuple[dict | None, str | None]:
    """Make raw POST to capture API error. Returns (success_response, error_message)."""
    import requests
    from tools.hubspot_api.config import get_config
    cfg = get_config()
    r = requests.post(
        f"{cfg.base_url}/crm/v3/lists",
        json=payload,
        headers=cfg.headers,
        timeout=cfg.timeout,
    )
    if r.ok:
        return r.json(), None
    return None, f"{r.status_code}: {r.text[:600]}"


def set_industria_enrichment_batch(
    client,
    company_ids: list[str],
    dry_run: bool,
    delay: float = 0.35,
    verbose: bool = False,
) -> int:
    """Set industria_enrichment_batch=true on companies. Returns count updated."""
    if dry_run:
        print(f"  [DRY RUN] Would set {INDUSTRIA_ENRICHMENT_PROP}=true on {len(company_ids)} companies")
        return len(company_ids)

    total = 0
    endpoint = "crm/v3/objects/companies/batch/update"
    for i in range(0, len(company_ids), BATCH_UPDATE_SIZE):
        batch_ids = company_ids[i : i + BATCH_UPDATE_SIZE]
        inputs = [
            {"id": cid, "properties": {INDUSTRIA_ENRICHMENT_PROP: "true"}}
            for cid in batch_ids
        ]
        try:
            resp = client.post(endpoint, {"inputs": inputs})
            total += len(resp.get("results", []))
            if verbose:
                print(f"    Batch {i//BATCH_UPDATE_SIZE + 1}: updated {len(batch_ids)} companies")
        except Exception as e:
            print(f"  Warning: Batch {i//BATCH_UPDATE_SIZE + 1} failed: {e}")
        time.sleep(delay)
    return total


def create_list_dynamic_property(client, name: str, dry_run: bool) -> str | None:
    """Create DYNAMIC list filtered by industria_enrichment_batch=true.
    Only companies we explicitly tagged will appear - exact static set."""
    if dry_run:
        print(f"  [DRY RUN] Would create DYNAMIC list: {name}")
        return "dry-run-list-id"

    payload = {
        "name": name,
        "objectTypeId": COMPANY_OBJECT_TYPE,
        "processingType": "DYNAMIC",
        "filterBranch": {
            "filterBranchType": "OR",
            "filters": [],
            "filterBranches": [
                {
                    "filterBranchType": "AND",
                    "filters": [
                        {
                            "filterType": "PROPERTY",
                            "property": INDUSTRIA_ENRICHMENT_PROP,
                            "operation": {"operationType": "BOOL", "operator": "IS_EQUAL_TO", "value": "true"},
                        },
                    ],
                    "filterBranches": [],
                }
            ],
        },
    }
    try:
        resp, err = _create_list_dynamic_raw(payload)
        if err:
            print(f"  ERROR creating list: {err}")
            return None
        list_data = resp.get("list", resp)
        list_id = list_data.get("listId") or list_data.get("id")
        print(f"  Created DYNAMIC list: {name} (ID: {list_id})")
        print(f"  Filter: industria_enrichment_batch = true (facturacion companies only)")
        return str(list_id)
    except Exception as e:
        print(f"  ERROR creating list: {e}")
        return None


def create_list_dynamic(client, name: str, dry_run: bool) -> str | None:
    """Create a DYNAMIC company list: cuit HAS_PROPERTY AND industria NOT_HAS_PROPERTY.
    No 100-member limit - HubSpot evaluates filters automatically.
    HubSpot requires root OR with AND sub-branches."""
    if dry_run:
        print(f"  [DRY RUN] Would create DYNAMIC list: {name}")
        return "dry-run-list-id"

    payload = {
        "name": name,
        "objectTypeId": COMPANY_OBJECT_TYPE,
        "processingType": "DYNAMIC",
        "filterBranch": {
            "filterBranchType": "OR",
            "filters": [],
            "filterBranches": [
                {
                    "filterBranchType": "AND",
                    "filters": [
                        {
                            "filterType": "PROPERTY",
                            "property": "cuit",
                            "operation": {"operationType": "ALL_PROPERTY", "operator": "IS_KNOWN"},
                        },
                        {
                            "filterType": "PROPERTY",
                            "property": "industria",
                            "operation": {"operationType": "ALL_PROPERTY", "operator": "IS_UNKNOWN"},
                        },
                    ],
                    "filterBranches": [],
                }
            ],
        },
    }
    try:
        resp, err = _create_list_dynamic_raw(payload)
        if err:
            print(f"  ERROR creating list: {err}")
            return None
        list_data = resp.get("list", resp)
        list_id = list_data.get("listId") or list_data.get("id")
        print(f"  Created DYNAMIC list: {name} (ID: {list_id})")
        print(f"  Filter: Companies with CUIT and without industria (auto-updates)")
        return str(list_id)
    except Exception as e:
        print(f"  ERROR creating list: {e}")
        return None


def add_companies_to_list(
    client,
    list_id: str,
    company_ids: list[str],
    dry_run: bool,
    delay: float = 0.3,
    verbose: bool = False,
) -> tuple[int, int]:
    """Add company IDs to MANUAL list in batches. Returns (added, missing).
    Uses PUT /memberships/add with array body (HubSpot accepts up to 100 per request)."""
    if dry_run:
        print(f"  [DRY RUN] Would add {len(company_ids)} companies to list {list_id}")
        return len(company_ids), 0

    total_added = 0
    total_missing = 0
    endpoint = f"crm/v3/lists/{list_id}/memberships/add"

    for i in range(0, len(company_ids), ADD_MEMBERSHIPS_BATCH):
        batch = company_ids[i : i + ADD_MEMBERSHIPS_BATCH]
        batch_ids = [str(cid) for cid in batch]
        try:
            resp = client.put(endpoint, batch_ids)
            added = resp.get("recordIdsAdded") or resp.get("recordsIdsAdded") or []
            missing = resp.get("recordIdsMissing") or []
            total_added += len(added)
            total_missing += len(missing)
            if verbose:
                print(f"    Batch {i//ADD_MEMBERSHIPS_BATCH + 1}: added {len(added)}, missing {len(missing)}")
        except Exception as e:
            print(f"  Warning: Batch {i//ADD_MEMBERSHIPS_BATCH + 1} failed: {e}")
        time.sleep(delay)

    return total_added, total_missing


def main():
    parser = argparse.ArgumentParser(
        description="Build HubSpot list with billing companies that need industria enrichment"
    )
    parser.add_argument(
        "--facturacion",
        default="tools/outputs/facturacion.csv",
        help="Path to facturacion.csv",
    )
    parser.add_argument(
        "--list-name",
        default=DEFAULT_LIST_NAME,
        help=f"Name for the HubSpot list (default: {DEFAULT_LIST_NAME})",
    )
    parser.add_argument(
        "--list-id",
        type=str,
        help="Add to existing list by ID (skips create; use to repopulate list 2661)",
    )
    parser.add_argument(
        "--property-based",
        action="store_true",
        help="Set industria_enrichment_batch on companies, create DYNAMIC list (exact static set, no 100 limit)",
    )
    parser.add_argument(
        "--dynamic",
        action="store_true",
        help="Create DYNAMIC list with filters (all companies with CUIT and no industria ~20k)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-batch progress when adding companies",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only analyze, do not create list or add companies",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Delay between API calls in seconds",
    )
    args = parser.parse_args()

    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()

    print("=" * 70)
    print("BUILD HUBSPOT LIST - Companies Needing Industria Enrichment")
    print("=" * 70)

    # Property-based mode: set property on companies, create DYNAMIC list filtered by it
    if args.property_based:
        billing_cuits = parse_billing_cuits(args.facturacion)
        if not billing_cuits:
            print("\nNo billing CUITs found in facturacion. Exiting.")
            return 1
        print(f"\nBilling CUITs in facturacion: {len(billing_cuits)}")
        print("Fetching companies from HubSpot...")
        companies = fetch_billing_companies_without_industria(
            client, billing_cuits, args.facturacion, delay=args.delay
        )
        print(f"  Companies needing industria: {len(companies)}")
        if not companies:
            print("\nNo companies need industria enrichment. Exiting.")
            return 0
        company_ids = [str(c["id"]) for c in companies]
        list_name = args.list_name if args.list_name != DEFAULT_LIST_NAME else DEFAULT_PROPERTY_LIST_NAME
        print(f"\nSetting {INDUSTRIA_ENRICHMENT_PROP}=true on {len(company_ids)} companies...")
        set_industria_enrichment_batch(
            client, company_ids, args.dry_run, args.delay, verbose=args.verbose
        )
        if not args.dry_run:
            print(f"  Updated {len(company_ids)} companies")
        print(f"\nCreating DYNAMIC list: {list_name}")
        list_id = create_list_dynamic_property(client, list_name, args.dry_run)
        if not list_id:
            return 1
        list_url = f"https://app.hubspot.com/contacts/19877595/lists/{list_id}"
        print(f"\nList URL: {list_url}")
        print("\n" + "=" * 70)
        return 0

    # Dynamic mode: create list with filters only (no fetch, no add)
    if args.dynamic:
        list_name = args.list_name if args.list_name != DEFAULT_LIST_NAME else DEFAULT_DYNAMIC_LIST_NAME
        print(f"\nCreating DYNAMIC list: {list_name}")
        print("  (Includes all companies with CUIT and without industria - auto-updates)")
        list_id = create_list_dynamic(client, list_name, args.dry_run)
        if not list_id:
            return 1
        list_url = f"https://app.hubspot.com/contacts/19877595/lists/{list_id}"
        print(f"\nList URL: {list_url}")
        print("\n" + "=" * 70)
        return 0

    billing_cuits = parse_billing_cuits(args.facturacion)
    if not billing_cuits:
        print("\nNo billing CUITs found in facturacion. Exiting.")
        return 1

    print(f"\nBilling CUITs in facturacion: {len(billing_cuits)}")
    print("Fetching companies from HubSpot...")

    companies = fetch_billing_companies_without_industria(
        client,
        billing_cuits,
        args.facturacion,
        delay=args.delay,
    )

    print(f"  Companies needing industria: {len(companies)}")

    if not companies:
        print("\nNo companies need industria enrichment. Exiting.")
        return 0

    company_ids = [str(c["id"]) for c in companies]

    # Create list or use existing
    if args.list_id:
        list_id = args.list_id
        print(f"\nUsing existing list ID: {list_id}")
    else:
        print(f"\nCreating MANUAL list: {args.list_name}")
        list_id = create_list_manual(client, args.list_name, args.dry_run)
        if not list_id:
            return 1

    print(f"\nAdding {len(company_ids)} companies to list...")
    added, missing = add_companies_to_list(
        client, list_id, company_ids, args.dry_run, args.delay, verbose=args.verbose
    )
    if not args.dry_run:
        print(f"  Added: {added}")
        if missing:
            print(f"  Missing (not found): {missing}")
    list_url = f"https://app.hubspot.com/contacts/19877595/lists/{list_id}"
    print(f"\nList URL: {list_url}")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
