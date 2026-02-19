#!/usr/bin/env python3
"""
Deal Conversion by Lead Source Analysis
=======================================

Calculates Deal Created → Deal Closed Won conversion rate by lead_source.
Used to validate product vision claims (e.g., Referencia Empresa Administrada ~90%,
Orgánico/Directo ~14%).

FUNNEL LOGIC:
- All deals CREATED in period
- Closed Won: dealstage = closedwon AND both createdate and closedate in period
- Conversion Rate: (Closed Won / Deal Created) × 100 per lead_source

Usage:
  python analyze_deal_conversion_by_lead_source.py --start-date 2025-10-01 --end-date 2026-02-01
  python analyze_deal_conversion_by_lead_source.py --month 2025-12
"""

import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
import argparse
import time

load_dotenv()
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    raise ValueError("HUBSPOT_API_KEY environment variable is required")

HUBSPOT_BASE_URL = 'https://api.hubapi.com'
HEADERS = {
    'Authorization': f'Bearer {HUBSPOT_API_KEY}',
    'Content-Type': 'application/json'
}


def fetch_deals_created_in_period(start_date, end_date):
    """Fetch all deals created in period with lead_source, dealstage, closedate."""
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    all_deals = []
    after = None

    while True:
        payload = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                    {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"}
                ]
            }],
            "properties": ["dealname", "createdate", "dealstage", "closedate", "lead_source", "amount"],
            "limit": 100
        }
        if after:
            payload["after"] = after

        try:
            response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])
            all_deals.extend(results)
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after:
                break
            time.sleep(0.2)
        except Exception as e:
            print(f"Error fetching deals: {e}")
            break

    return all_deals


def analyze_conversion_by_lead_source(start_date, end_date):
    """Analyze Deal→Won conversion rate by lead_source."""
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")

    print("="*80)
    print("DEAL CONVERSION BY LEAD SOURCE")
    print("="*80)
    print(f"Period: {start_date} to {end_date}")
    print("Funnel: Deal Created → Deal Closed Won (both dates in period)")
    print()

    deals = fetch_deals_created_in_period(start_date, end_date)
    print(f"📊 Fetched {len(deals)} deals created in period")

    # Group by lead_source
    by_source = {}
    for deal in deals:
        props = deal.get('properties', {})
        lead_source = props.get('lead_source', '') or '(empty)'
        lead_source = lead_source.strip() or '(empty)'

        if lead_source not in by_source:
            by_source[lead_source] = {'created': 0, 'closed_won': 0}

        by_source[lead_source]['created'] += 1

        dealstage = props.get('dealstage', '')
        createdate_str = props.get('createdate', '')
        closedate_str = props.get('closedate', '')

        # closedwon + 34692158 (Cerrado Ganado Recupero) per fix_deal_associations, hubspot_first_deal_won
        if dealstage in ('closedwon', '34692158') and createdate_str and closedate_str:
            try:
                created_dt = datetime.fromisoformat(createdate_str.replace('Z', '+00:00'))
                closed_dt = datetime.fromisoformat(closedate_str.replace('Z', '+00:00'))
                if start_dt <= created_dt < end_dt and start_dt <= closed_dt < end_dt:
                    by_source[lead_source]['closed_won'] += 1
            except Exception:
                pass

    # Sort by closed_won count descending
    rows = []
    for source, counts in by_source.items():
        created = counts['created']
        won = counts['closed_won']
        rate = (won / created * 100) if created > 0 else 0
        rows.append((source, created, won, rate))

    rows.sort(key=lambda x: (-x[2], -x[1]))

    print()
    print("| Lead Source | Deals Created | Closed Won | Deal→Won % |")
    print("|-------------|---------------|------------|------------|")
    for source, created, won, rate in rows:
        print(f"| {source} | {created} | {won} | {rate:.1f}% |")

    print()
    print("="*80)
    print("KEY METRICS FOR PRODUCT VISION")
    print("="*80)
    print()
    print("Referencia Empresa Administrada (Contador refiere PyME administrada):")
    ref_emp = by_source.get('Referencia Empresa Administrada', {'created': 0, 'closed_won': 0})
    if ref_emp['created'] > 0:
        rate = ref_emp['closed_won'] / ref_emp['created'] * 100
        print(f"  Deal→Won: {rate:.1f}% ({ref_emp['closed_won']}/{ref_emp['created']})")
    else:
        print("  No deals in period")
    print()
    print("Orgánico / Directo (organic acquisition):")
    organico = by_source.get('Orgánico', {'created': 0, 'closed_won': 0})
    if organico['created'] > 0:
        rate = organico['closed_won'] / organico['created'] * 100
        print(f"  Deal→Won: {rate:.1f}% ({organico['closed_won']}/{organico['created']})")
    else:
        print("  No deals in period")
    print()
    print("Referencia Externa Contador (broader Contador channel):")
    ref_cont = by_source.get('Referencia Externa Contador', {'created': 0, 'closed_won': 0})
    if ref_cont['created'] > 0:
        rate = ref_cont['closed_won'] / ref_cont['created'] * 100
        print(f"  Deal→Won: {rate:.1f}% ({ref_cont['closed_won']}/{ref_cont['created']})")
    else:
        print("  No deals in period")
    print()

    return by_source


def main():
    parser = argparse.ArgumentParser(description='Deal conversion by lead source')
    parser.add_argument('--start-date', help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', help='End date YYYY-MM-DD')
    parser.add_argument('--month', help='Month YYYY-MM')
    args = parser.parse_args()

    if args.month:
        year, month = args.month.split('-')
        start_date = f"{year}-{month}-01"
        if month == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            end_date = f"{year}-{int(month)+1:02d}-01"
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        # Default: Oct 2025 - Jan 2026
        start_date = '2025-10-01'
        end_date = '2026-02-01'
        print("Using default period: Oct 2025 - Jan 2026")
        print()

    analyze_conversion_by_lead_source(start_date, end_date)


if __name__ == '__main__':
    main()
