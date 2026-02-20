#!/usr/bin/env python3
"""
Touch Sequence Analysis (Touch Before/After First Payment)
==========================================================
Classifies closed deals by when sales touched relative to first payment:
- Touch BEFORE first payment: Sales influenced conversion
- Touch AFTER first payment: Touch post-conversion (e.g. task/note, not influential)
- No touch: Product-led conversion (no contacts) or no deal-associated activities

METHODOLOGY:
- First payment: fecha_primer_pago (deal) or closedate fallback
- First touch: Earliest hs_timestamp among engagements (calls, emails, meetings, notes, tasks)
  associated with the deal. If no contacts → no touch. If contacts exist, use activities
  linked to the deal (not contact-level fields).

Usage:
  python tools/scripts/hubspot/analyze_touch_sequence_deals.py --month 2026-01
  python tools/scripts/hubspot/analyze_touch_sequence_deals.py --start-date 2026-01-01 --end-date 2026-01-31
"""

import os
import sys
import time
import argparse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

HUBSPOT_PORTAL_ID = "19877595"
HUBSPOT_UI_DOMAIN = "app.hubspot.com"

API_KEY = os.getenv("HUBSPOT_API_KEY") or os.getenv("COLPPY_CRM_AUTOMATIONS") or os.getenv("ColppyCRMAutomations")
if not API_KEY:
    print("Error: HUBSPOT_API_KEY (or COLPPY_CRM_AUTOMATIONS) not found in .env")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
BASE_URL = "https://api.hubapi.com"
RATE_LIMIT_DELAY = float(os.getenv("HUBSPOT_RATE_LIMIT_DELAY", "0.5"))

ENGAGEMENT_TYPES = ("calls", "emails", "meetings", "notes", "tasks")


def parse_ts(s: str) -> datetime | None:
    """Parse HubSpot datetime to datetime."""
    if not s or not str(s).strip():
        return None
    try:
        s = str(s).replace("Z", "+00:00")
        if "T" in s:
            return datetime.fromisoformat(s)
        return datetime.fromisoformat(s + "T00:00:00+00:00")
    except (ValueError, TypeError):
        return None


def search_deals_closed_won(start_date: str, end_date: str) -> list[dict]:
    """Fetch deals closed won in period with fecha_primer_pago."""
    url = f"{BASE_URL}/crm/v3/objects/deals/search"
    all_deals = []
    after = None
    props = ["dealname", "amount", "closedate", "createdate", "hubspot_owner_id", "fecha_primer_pago"]
    while True:
        payload = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"},
                    {"propertyName": "closedate", "operator": "GTE", "value": f"{start_date}T00:00:00.000Z"},
                    {"propertyName": "closedate", "operator": "LTE", "value": f"{end_date}T23:59:59.999Z"},
                ]
            }],
            "properties": props,
            "limit": 100,
        }
        if after:
            payload["after"] = after
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"Error: {resp.status_code} {resp.text}")
            break
        data = resp.json()
        results = data.get("results", [])
        all_deals.extend(results)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        time.sleep(RATE_LIMIT_DELAY)
    return all_deals


def get_deal_contact_ids(deal_id: str) -> list[str]:
    """Get contact IDs associated with deal."""
    url = f"{BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/contacts"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return []
        return [str(r["toObjectId"]) for r in resp.json().get("results", [])]
    except Exception:
        return []


def get_deal_engagement_ids(deal_id: str) -> list[tuple[str, str]]:
    """Get engagement IDs (object_type, id) associated with deal."""
    ids = []
    for obj_type in ENGAGEMENT_TYPES:
        url = f"{BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/{obj_type}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    ids.append((obj_type, str(r["toObjectId"])))
            time.sleep(RATE_LIMIT_DELAY * 0.3)
        except Exception:
            pass
    return ids


def batch_read_engagement_timestamps(engagement_refs: list[tuple[str, str]]) -> list[datetime]:
    """Batch read engagements and return list of hs_timestamp values."""
    if not engagement_refs:
        return []
    timestamps = []
    by_type: dict[str, list[str]] = {}
    for obj_type, eid in engagement_refs:
        by_type.setdefault(obj_type, []).append(eid)
    for obj_type, eids in by_type.items():
        url = f"{BASE_URL}/crm/v3/objects/{obj_type}/batch/read"
        for i in range(0, len(eids), 100):
            batch = eids[i : i + 100]
            payload = {"inputs": [{"id": eid} for eid in batch], "properties": ["hs_timestamp", "createdate"]}
            try:
                resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
                if resp.status_code == 200:
                    for r in resp.json().get("results", []):
                        p = r.get("properties", {})
                        ts = (p.get("hs_timestamp") or p.get("createdate") or "").strip()
                        if ts:
                            dt = parse_ts(ts)
                            if dt:
                                timestamps.append(dt)
                time.sleep(RATE_LIMIT_DELAY)
            except Exception:
                pass
    return timestamps


def get_first_touch_from_deal_engagements(deal_id: str) -> datetime | None:
    """
    First touch = earliest hs_timestamp among engagements associated with the deal.
    If no contacts on deal → no touch (return None).
    If contacts exist, use activities linked to the deal.
    """
    contact_ids = get_deal_contact_ids(deal_id)
    time.sleep(RATE_LIMIT_DELAY * 0.3)
    if not contact_ids:
        return None
    refs = get_deal_engagement_ids(deal_id)
    if not refs:
        return None
    timestamps = batch_read_engagement_timestamps(refs)
    return min(timestamps) if timestamps else None


def get_first_payment_date(deal: dict) -> datetime | None:
    """First payment date: fecha_primer_pago or closedate fallback."""
    p = deal.get("properties", {})
    v = (p.get("fecha_primer_pago") or "").strip()
    if v:
        dt = parse_ts(v)
        if dt:
            return dt
    return parse_ts(p.get("closedate") or "")


def run_analysis(start_date: str, end_date: str, table: bool = False):
    """Run touch sequence analysis."""
    print("=" * 100)
    print("TOUCH SEQUENCE ANALYSIS (Touch Before/After First Payment)")
    print("=" * 100)
    print()
    print("METHODOLOGY:")
    print("- First payment: fecha_primer_pago (deal) or closedate fallback")
    print("- First touch: Earliest hs_timestamp among deal-associated engagements (calls, emails, meetings, notes, tasks)")
    print("- No contacts on deal → no touch. If contacts exist, use activities linked to the deal.")
    print("- Touch BEFORE payment = sales influenced conversion")
    print("- Touch AFTER payment = touch post-conversion (e.g. task, not influential)")
    print("- No touch = product-led (no contacts or no deal-associated activities)")
    print()
    print(f"Period: {start_date} to {end_date}")
    print()

    deals = search_deals_closed_won(start_date, end_date)
    print(f"Total closed-won deals in period: {len(deals)}", flush=True)
    print("Fetching deal-associated engagements (calls, emails, meetings, notes, tasks)...", flush=True)
    print()

    touch_before = []
    touch_after = []
    no_touch = []
    no_payment_date = []

    for deal in deals:
        deal_id = deal["id"]
        first_touch = get_first_touch_from_deal_engagements(deal_id)
        first_payment = get_first_payment_date(deal)

        if first_payment is None:
            no_payment_date.append(deal)
            continue

        if first_touch is None:
            no_touch.append(deal)
        elif first_touch < first_payment:
            touch_before.append((deal, first_touch, first_payment))
        else:
            touch_after.append((deal, first_touch, first_payment))

    # Summary
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()
    total = len(deals)
    print(f"| Category | Count | % | Revenue |")
    print(f"|----------|-------|---|---------|")

    def sum_amount(items, get_deal=lambda x: x):
        return sum(float(get_deal(d).get("properties", {}).get("amount") or 0) for d in items)

    def fmt_amt(amt):
        return f"${amt:,.0f}".replace(",", ".")

    def fmt_pct(n, t):
        return f"{100 * n / t:.1f}%" if t else "0%"

    rev_before = sum_amount(touch_before, lambda x: x[0])
    rev_after = sum_amount(touch_after, lambda x: x[0])
    rev_no = sum_amount(no_touch)
    rev_na = sum_amount(no_payment_date)

    print(f"| Touch BEFORE first payment (sales influenced) | {len(touch_before)} | {fmt_pct(len(touch_before), total)} | {fmt_amt(rev_before)} |")
    print(f"| Touch AFTER first payment (post-conversion) | {len(touch_after)} | {fmt_pct(len(touch_after), total)} | {fmt_amt(rev_after)} |")
    print(f"| No touch (product-led) | {len(no_touch)} | {fmt_pct(len(no_touch), total)} | {fmt_amt(rev_no)} |")
    if no_payment_date:
        print(f"| No fecha_primer_pago (using closedate fallback) | {len(no_payment_date)} | {fmt_pct(len(no_payment_date), total)} | {fmt_amt(rev_na)} |")
    print()

    # Detail: Touch before
    print("=" * 100)
    print("TOUCH BEFORE FIRST PAYMENT (sales influenced conversion)")
    print("=" * 100)
    print()
    for i, (deal, ft, fp) in enumerate(touch_before[:20], 1):
        p = deal["properties"]
        link = f"https://{HUBSPOT_UI_DOMAIN}/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal['id']}"
        print(f"{i}. [{p.get('dealname', 'N/A')}]({link})")
        print(f"   Amount: {fmt_amt(float(p.get('amount') or 0))} | First touch: {ft.strftime('%Y-%m-%d')} | First payment: {fp.strftime('%Y-%m-%d')}")
        print()
    if len(touch_before) > 20:
        print(f"   ... and {len(touch_before) - 20} more")
    print()

    # Detail: Touch after
    print("=" * 100)
    print("TOUCH AFTER FIRST PAYMENT (post-conversion touch)")
    print("=" * 100)
    print()
    for i, (deal, ft, fp) in enumerate(touch_after[:20], 1):
        p = deal["properties"]
        link = f"https://{HUBSPOT_UI_DOMAIN}/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal['id']}"
        print(f"{i}. [{p.get('dealname', 'N/A')}]({link})")
        print(f"   Amount: {fmt_amt(float(p.get('amount') or 0))} | First touch: {ft.strftime('%Y-%m-%d')} | First payment: {fp.strftime('%Y-%m-%d')}")
        print()
    if len(touch_after) > 20:
        print(f"   ... and {len(touch_after) - 20} more")
    print()

    # Detail: No touch
    print("=" * 100)
    print("NO TOUCH (product-led)")
    print("=" * 100)
    print()
    for i, deal in enumerate(no_touch[:20], 1):
        p = deal["properties"]
        link = f"https://{HUBSPOT_UI_DOMAIN}/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal['id']}"
        print(f"{i}. [{p.get('dealname', 'N/A')}]({link})")
        print(f"   Amount: {fmt_amt(float(p.get('amount') or 0))} | First payment: {get_first_payment_date(deal).strftime('%Y-%m-%d')}")
        print()
    if len(no_touch) > 20:
        print(f"   ... and {len(no_touch) - 20} more")
    print()

    if no_payment_date:
        print("=" * 100)
        print("DEALS WITHOUT fecha_primer_pago (excluded from sequence)")
        print("=" * 100)
        print()
        for i, deal in enumerate(no_payment_date[:10], 1):
            p = deal["properties"]
            link = f"https://{HUBSPOT_UI_DOMAIN}/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal['id']}"
            print(f"{i}. [{p.get('dealname', 'N/A')}]({link})")
        if len(no_payment_date) > 10:
            print(f"   ... and {len(no_payment_date) - 10} more")
        print()

    if table:
        print("=" * 100)
        print("FULL TABLE (clickable links to HubSpot)")
        print("=" * 100)
        print()
        print("| # | Category | Deal | Amount | First Touch | First Payment |")
        print("|---|----------|------|--------|-------------|---------------|")
        n = 1
        for i, (deal, ft, fp) in enumerate(touch_before, 1):
            p = deal["properties"]
            link = f"https://{HUBSPOT_UI_DOMAIN}/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal['id']}"
            name = (p.get("dealname") or "N/A").replace("|", "-")
            print(f"| {n} | Touch before | [{name}]({link}) | {fmt_amt(float(p.get('amount') or 0))} | {ft.strftime('%Y-%m-%d')} | {fp.strftime('%Y-%m-%d')} |")
            n += 1
        for i, (deal, ft, fp) in enumerate(touch_after, 1):
            p = deal["properties"]
            link = f"https://{HUBSPOT_UI_DOMAIN}/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal['id']}"
            name = (p.get("dealname") or "N/A").replace("|", "-")
            print(f"| {n} | Touch after | [{name}]({link}) | {fmt_amt(float(p.get('amount') or 0))} | {ft.strftime('%Y-%m-%d')} | {fp.strftime('%Y-%m-%d')} |")
            n += 1
        for i, deal in enumerate(no_touch, 1):
            p = deal["properties"]
            link = f"https://{HUBSPOT_UI_DOMAIN}/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal['id']}"
            name = (p.get("dealname") or "N/A").replace("|", "-")
            fp = get_first_payment_date(deal)
            print(f"| {n} | No touch | [{name}]({link}) | {fmt_amt(float(p.get('amount') or 0))} | - | {fp.strftime('%Y-%m-%d') if fp else '-'} |")
            n += 1
        print()

    print("=" * 100)
    return {"touch_before": touch_before, "touch_after": touch_after, "no_touch": no_touch, "no_payment_date": no_payment_date}


def main():
    parser = argparse.ArgumentParser(description="Analyze touch sequence vs first payment")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--month", type=str, help="Month YYYY-MM")
    group.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    parser.add_argument("--table", action="store_true", help="Print full table with clickable HubSpot links")
    args = parser.parse_args()

    if args.month:
        year, month = args.month.split("-")
        from calendar import monthrange
        last = monthrange(int(year), int(month))[1]
        start_date = f"{args.month}-01"
        end_date = f"{args.month}-{last:02d}"
    else:
        if not args.end_date:
            parser.error("--end-date required with --start-date")
        start_date = args.start_date
        end_date = args.end_date

    run_analysis(start_date, end_date, table=args.table)


if __name__ == "__main__":
    main()
