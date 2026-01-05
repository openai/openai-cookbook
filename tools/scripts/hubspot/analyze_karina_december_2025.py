#!/usr/bin/env python3
"""
Analyze Karina's deals in December 2025
Shows which cohort month this corresponds to and lists all deals
"""

import sys
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from hubspot_api.client import HubSpotClient
from owner_utils import get_owner_name, _STATIC_OWNER_MAP

# Import the fetch function from the main script
sys.path.insert(0, os.path.dirname(__file__))
from sales_ramp_cohort_analysis import fetch_closed_won_deals, parse_closedate, get_rep_team

# Karina's start date: September 2024 (month 9, year 2024)
KARINA_START_MONTH = 9
KARINA_START_YEAR = 2024

# December 2025
TARGET_MONTH = 12
TARGET_YEAR = 2025

# Calculate cohort month
# Month 0 = September 2024
# Month 1 = October 2024
# ...
# Month 15 = December 2025
months_diff = (TARGET_YEAR - KARINA_START_YEAR) * 12 + (TARGET_MONTH - KARINA_START_MONTH)
cohort_month = months_diff

print("=" * 100)
print("KARINA LORENA RUSSO - DECEMBER 2025 COHORT ANALYSIS")
print("=" * 100)
print(f"Start Date: September 2024 (Month 0)")
print(f"Target Date: December 2025 (Month {cohort_month})")
print(f"Cohort Month: {cohort_month}")
print("=" * 100)
print()

# Get Karina's owner ID
owner_name_to_id = {v: k for k, v in _STATIC_OWNER_MAP.items()}
karina_name = "Karina Lorena Russo"
karina_owner_id = owner_name_to_id.get(karina_name)

if not karina_owner_id:
    print(f"❌ Could not find owner ID for {karina_name}")
    sys.exit(1)

print(f"✅ Found Karina's Owner ID: {karina_owner_id}")
print()

# Verify Karina is in Accountant Channel
client = HubSpotClient()
karina_team = get_rep_team(karina_name, karina_owner_id, client)
print(f"✅ Karina's Team: {karina_team}")
if karina_team == "Accountant Channel":
    print("   → Karina is in Accountant Channel - deals will count if she's owner OR collaborator")
else:
    print("   ⚠️  Warning: Karina should be in Accountant Channel")
print()

# Fetch deals closed in December 2025
start_date = datetime(2025, 12, 1)
end_date = datetime(2025, 12, 31)

print(f"🔍 Fetching deals closed between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}...")
print()

deals = fetch_closed_won_deals(start_date, end_date, client)

print(f"✅ Total closed won deals in December 2025: {len(deals)}")
print()

# Filter deals where Karina is owner or collaborator
karina_deals = []

for deal in deals:
    props = deal.get('properties', {})
    owner_id = props.get('hubspot_owner_id', '')
    collaborator_ids_str = props.get('hs_all_collaborator_owner_ids', '')
    
    # Check if Karina is owner
    is_owner = (owner_id == karina_owner_id)
    
    # Check if Karina is collaborator
    is_collaborator = False
    collaborator_names = []
    if collaborator_ids_str:
        collaborator_ids = [cid.strip() for cid in str(collaborator_ids_str).split(';') if cid.strip()]
        is_collaborator = karina_owner_id in collaborator_ids
        collaborator_names = [get_owner_name(cid) for cid in collaborator_ids if get_owner_name(cid)]
    
    if is_owner or is_collaborator:
        close_date_str = props.get('closedate', '')
        close_month_year = parse_closedate(close_date_str)
        
        deal_info = {
            'deal_id': deal.get('id'),
            'deal_name': props.get('dealname', 'N/A'),
            'amount': props.get('amount', '0'),
            'close_date_str': close_date_str,
            'close_month_year': close_month_year,
            'owner_id': owner_id,
            'owner_name': get_owner_name(owner_id) if owner_id else 'N/A',
            'collaborator_ids': collaborator_ids_str,
            'collaborator_names': collaborator_names,
            'is_owner': is_owner,
            'is_collaborator': is_collaborator,
            'dealstage': props.get('dealstage', 'N/A')
        }
        karina_deals.append(deal_info)

print("=" * 100)
print(f"DEALS WHERE KARINA IS OWNER OR COLLABORATOR (December 2025)")
print("=" * 100)
print(f"Total deals: {len(karina_deals)}")
print()

if karina_deals:
    for i, deal in enumerate(karina_deals, 1):
        print(f"{i}. Deal: {deal['deal_name']}")
        print(f"   Deal ID: {deal['deal_id']}")
        print(f"   Amount: ${deal['amount']}")
        print(f"   Close Date: {deal['close_date_str']}")
        print(f"   Owner: {deal['owner_name']} (ID: {deal['owner_id']})")
        print(f"   Karina is Owner: {'✅ YES' if deal['is_owner'] else '❌ NO'}")
        print(f"   Karina is Collaborator: {'✅ YES' if deal['is_collaborator'] else '❌ NO'}")
        if deal['collaborator_names']:
            print(f"   All Collaborators: {', '.join(deal['collaborator_names'])}")
        print(f"   Deal Stage: {deal['dealstage']}")
        print()
else:
    print("❌ No deals found for Karina in December 2025")

print("=" * 100)
print(f"\nSummary:")
print(f"  - Cohort Month for December 2025: {cohort_month}")
print(f"  - Total deals attributed to Karina: {len(karina_deals)}")
print(f"  - As Owner: {sum(1 for d in karina_deals if d['is_owner'])}")
print(f"  - As Collaborator: {sum(1 for d in karina_deals if d['is_collaborator'])}")
print("=" * 100)


