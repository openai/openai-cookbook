#!/usr/bin/env python3
"""
No-Touch Deals Analysis
=======================
Identifies deals closed in a period WITHOUT any human intervention (no sales activities logged).

METHODOLOGY (HubSpot deal-level):
- num_notes: "Number of Sales Activities" - calls, meetings, notes, sales emails, tasks, etc. logged on the deal
- A deal is "no touch" if num_notes = 0 (no sales activities ever logged on the deal record)

Usage:
  python tools/scripts/hubspot/analyze_product_led_deals.py --month 2026-01
  python tools/scripts/hubspot/analyze_product_led_deals.py --start-date 2026-01-01 --end-date 2026-01-31
"""

import os
import sys
import time
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

HUBSPOT_PORTAL_ID = "19877595"
HUBSPOT_UI_DOMAIN = "app.hubspot.com"

API_KEY = os.getenv("HUBSPOT_API_KEY") or os.getenv("COLPPY_CRM_AUTOMATIONS") or os.getenv("ColppyCRMAutomations")
if not API_KEY:
    print("Error: HUBSPOT_API_KEY (or COLPPY_CRM_AUTOMATIONS) not found in .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}
BASE_URL = "https://api.hubapi.com"
RATE_LIMIT_DELAY = float(os.getenv("HUBSPOT_RATE_LIMIT_DELAY", "0.5"))


def search_deals_closed_won(start_date: str, end_date: str):
    """Fetch all deals closed won in the date range with num_notes."""
    url = f"{BASE_URL}/crm/v3/objects/deals/search"
    all_deals = []
    after = None
    while True:
        payload = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"},
                    {"propertyName": "closedate", "operator": "GTE", "value": f"{start_date}T00:00:00.000Z"},
                    {"propertyName": "closedate", "operator": "LTE", "value": f"{end_date}T23:59:59.999Z"},
                ]
            }],
            "properties": ["dealname", "amount", "closedate", "createdate", "hubspot_owner_id", "num_notes"],
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


def is_no_touch_deal(deal: dict) -> bool:
    """Deal has no touch if num_notes is 0 or empty."""
    num_notes = deal.get("properties", {}).get("num_notes")
    if num_notes is None or num_notes == "":
        return True
    try:
        return int(num_notes) == 0
    except (ValueError, TypeError):
        return True


def format_amount(val: str) -> str:
    """Format amount for display."""
    try:
        n = float(val or 0)
        return f"${n:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return val or "N/A"


def generate_deal_link(deal_id: str) -> str:
    return f"https://{HUBSPOT_UI_DOMAIN}/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal_id}"


def run_analysis(start_date: str, end_date: str):
    """Run the no-touch deals analysis."""
    print("=" * 100)
    print("NO-TOUCH DEALS ANALYSIS (Closed without human intervention)")
    print("=" * 100)
    print()
    print("METHODOLOGY:")
    print("- Uses deal-level num_notes (Number of Sales Activities)")
    print("- num_notes = 0 means no calls, meetings, notes, sales emails, or tasks logged on the deal")
    print("- A deal is 'no touch' if num_notes = 0")
    print()
    print(f"Period: {start_date} to {end_date}")
    print()

    deals = search_deals_closed_won(start_date, end_date)
    print(f"Total closed-won deals in period: {len(deals)}")
    print()

    no_touch_deals = [d for d in deals if is_no_touch_deal(d)]

    print("=" * 100)
    print("DEALS CLOSED WITHOUT HUMAN INTERVENTION")
    print("=" * 100)
    print()
    print(f"Count: {len(no_touch_deals)} of {len(deals)} deals ({100 * len(no_touch_deals) / len(deals):.1f}%)" if deals else "Count: 0")
    print()

    if no_touch_deals:
        total_amount = 0
        for i, deal in enumerate(no_touch_deals, 1):
            p = deal["properties"]
            amt = float(p.get("amount") or 0)
            total_amount += amt
            deal_link = generate_deal_link(deal["id"])
            print(f"{i}. [{p.get('dealname', 'N/A')}]({deal_link})")
            print(f"   Amount: {format_amount(p.get('amount'))} | Closed: {(p.get('closedate') or '')[:10]}")
            print()

        print("-" * 100)
        print(f"Total revenue (no touch): {format_amount(str(total_amount))}")
    else:
        print("No no-touch deals found in this period.")

    print()
    print("=" * 100)
    return no_touch_deals


def main():
    parser = argparse.ArgumentParser(description="Analyze deals closed without human intervention (no touch)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--month", type=str, help="Month in YYYY-MM format (e.g. 2026-01)")
    group.add_argument("--start-date", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="End date YYYY-MM-DD (required with --start-date)")
    args = parser.parse_args()

    if args.month:
        year, month = args.month.split("-")
        from calendar import monthrange
        last_day = monthrange(int(year), int(month))[1]
        start_date = f"{args.month}-01"
        end_date = f"{args.month}-{last_day:02d}"
    else:
        if not args.end_date:
            parser.error("--end-date required with --start-date")
        start_date = args.start_date
        end_date = args.end_date

    run_analysis(start_date, end_date)


if __name__ == "__main__":
    main()
