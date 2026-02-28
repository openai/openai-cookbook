"""
HubSpot API fetchers for facturacion–HubSpot mapping.
"""
import calendar
import re
import time
from typing import Optional

EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}
ACTIVE_DEAL_STAGES = ("closedwon", "34692158")


def normalize_cuit(raw: str) -> Optional[str]:
    """Normalize CUIT to 11 digits."""
    if not raw or str(raw).strip().upper() in ("#N/A", "N/A", ""):
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


def fetch_companies_by_cuit(client, cuits: set[str], delay: float = 0.3) -> dict[str, list[dict]]:
    """Batch-search companies by cuit IN (25/request) with pagination. Returns CUIT -> list of all companies."""
    cuit_list = sorted(cuits)
    cuit_to_companies: dict[str, list[dict]] = {}
    batch_size = 25
    total_batches = (len(cuit_list) + batch_size - 1) // batch_size

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
                    properties=["name", "cuit", "type", "tipo_icp_contador", "hs_object_id"],
                    limit=100,
                    after=after,
                )
                for r in resp.get("results", []):
                    n = normalize_cuit(r.get("properties", {}).get("cuit"))
                    if n:
                        if n not in cuit_to_companies:
                            cuit_to_companies[n] = []
                        ids_seen = {x.get("id") for x in cuit_to_companies[n]}
                        if r.get("id") not in ids_seen:
                            cuit_to_companies[n].append(r)
                after = resp.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
                time.sleep(delay)
            except Exception as e:
                bn = i // batch_size + 1
                print(f"  Warning: Company batch {bn}/{total_batches} failed: {e}")
                break
        time.sleep(delay)

    return cuit_to_companies


def fetch_deals_by_id_empresa(client, id_empresas: set[str], delay: float = 0.25) -> dict[str, dict]:
    """Batch-search deals by id_empresa IN (100/request) with pagination. Returns id_empresa -> deal."""
    valid_ids = sorted({x for x in id_empresas if x and x.isdigit()})
    id_to_deal = {}
    batch_size = 100
    total_batches = (len(valid_ids) + batch_size - 1) // batch_size

    for i in range(0, len(valid_ids), batch_size):
        batch = valid_ids[i : i + batch_size]
        after = None
        while True:
            try:
                resp = client.search_objects(
                    object_type="deals",
                    filter_groups=[{"filters": [{"propertyName": "id_empresa", "operator": "IN", "values": batch}]}],
                    properties=["dealname", "id_empresa", "dealstage", "amount", "closedate", "hs_object_id", "colppy_plan", "fecha_primer_pago", "dealtype", "nombre_del_plan_del_negocio"],
                    limit=100,
                    after=after,
                )
                for r in resp.get("results", []):
                    raw = (r.get("properties", {}).get("id_empresa") or "").strip()
                    if raw and raw not in id_to_deal:
                        id_to_deal[raw] = r
                after = resp.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
                time.sleep(delay)
            except Exception as e:
                bn = i // batch_size + 1
                print(f"  Warning: Deal batch {bn}/{total_batches} failed: {e}")
                break
        time.sleep(delay)

    return id_to_deal


def fetch_deals_closed_in_month(
    client, year: str, month: int, delay: float = 0.25
) -> dict[str, dict]:
    """Fetch HubSpot closed won deals for given month (filtered at API by closedate)."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    all_deals = []
    after = None
    props = ["dealname", "id_empresa", "dealstage", "amount", "closedate", "hs_object_id", "colppy_plan", "fecha_primer_pago", "dealtype", "nombre_del_plan_del_negocio"]
    filter_groups = [{
        "filters": [
            {"propertyName": "dealstage", "operator": "IN", "values": list(ACTIVE_DEAL_STAGES)},
            {"propertyName": "closedate", "operator": "GTE", "value": start},
            {"propertyName": "closedate", "operator": "LTE", "value": end},
        ]
    }]
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
        time.sleep(delay)
    id_to_deal = {}
    for r in all_deals:
        raw = (r.get("properties", {}).get("id_empresa") or "").strip()
        if raw and raw not in id_to_deal:
            id_to_deal[raw] = r
    return id_to_deal
