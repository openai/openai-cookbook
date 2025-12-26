#!/usr/bin/env python3
"""
Find the 2 extra accountant deals
"""
import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
import time

load_dotenv()
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
HUBSPOT_BASE_URL = 'https://api.hubapi.com'
HEADERS = {'Authorization': f'Bearer {HUBSPOT_API_KEY}', 'Content-Type': 'application/json'}

ACCOUNTANT_ROLES = ['contador', 'estudio contable', 'contador público', 'asesor contable']

def is_accountant_role(rol_wizard):
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    return any(role in str(rol_wizard).lower().strip() for role in ACCOUNTANT_ROLES)

# Fetch all deals created in December
print("Fetching all deals created in December 2025...")
start_date = "2025-12-01"
end_date = "2026-01-01"
start_dt = datetime.fromisoformat(f"{start_date}T00:00:00Z".replace('Z', '+00:00'))
end_dt = datetime.fromisoformat(f"{end_date}T00:00:00Z".replace('Z', '+00:00'))

url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
all_deals = []
after = None

while True:
    filters = [
        {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
        {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"}
    ]
    payload = {
        "filterGroups": [{"filters": filters}],
        "properties": ["dealname", "amount", "createdate"],
        "associations": ["contacts"],
        "limit": 100
    }
    if after:
        payload["after"] = after
    
    response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    results = data.get('results', [])
    all_deals.extend(results)
    print(f"  Retrieved {len(results)} deals (total: {len(all_deals)})")
    
    after = data.get('paging', {}).get('next', {}).get('after')
    if not after:
        break
    time.sleep(0.2)

print(f"\nTotal deals created in December: {len(all_deals)}")
print()

# Analyze each deal
print("Analyzing deals for accountant contacts...")
accountant_deals = []

for i, deal in enumerate(all_deals, 1):
    if i % 10 == 0:
        print(f"  Processing {i}/{len(all_deals)}...")
    
    deal_id = deal.get('id')
    deal_props = deal.get('properties', {})
    deal_name = deal_props.get('dealname', 'N/A')
    deal_createdate_str = deal_props.get('createdate', '')
    
    if not deal_createdate_str:
        continue
    
    try:
        deal_created_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
    except:
        continue
    
    # Get contacts
    associations = deal.get('associations', {})
    contacts = associations.get('contacts', {}).get('results', [])
    
    has_accountant_contact_before = False
    contact_details = []
    
    for contact_assoc in contacts[:5]:  # Check first 5 contacts
        contact_id = contact_assoc.get('id')
        contact_url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}"
        contact_resp = requests.get(contact_url, headers=HEADERS, params={
            'properties': 'email,createdate,rol_wizard,lead_source'
        }, timeout=30)
        
        if contact_resp.status_code == 200:
            contact_data = contact_resp.json()
            contact_props = contact_data.get('properties', {})
            rol_wizard = contact_props.get('rol_wizard', '')
            lead_source = contact_props.get('lead_source', '')
            contact_createdate_str = contact_props.get('createdate', '')
            
            # Check if accountant and created in December
            is_accountant = is_accountant_role(rol_wizard)
            contact_in_dec = False
            contact_before_deal = False
            
            if contact_createdate_str:
                try:
                    contact_dt = datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))
                    contact_in_dec = start_dt <= contact_dt < end_dt
                    contact_before_deal = contact_dt < deal_created_dt
                except:
                    pass
            
            if is_accountant and contact_in_dec and contact_before_deal:
                has_accountant_contact_before = True
                contact_details.append({
                    'email': contact_props.get('email', 'N/A'),
                    'createdate': contact_createdate_str[:10],
                    'rol_wizard': rol_wizard or '(null)',
                    'hours_before': (deal_created_dt - datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))).total_seconds() / 3600
                })
        
        time.sleep(0.1)
    
    if has_accountant_contact_before:
        accountant_deals.append({
            'deal_id': deal_id,
            'deal_name': deal_name,
            'amount': deal_props.get('amount', '0'),
            'createdate': deal_createdate_str[:10],
            'contacts': contact_details
        })

print(f"\n✅ Deals with accountant contacts (created in Dec, before deal): {len(accountant_deals)}")
print(f"📊 HubSpot shows: 18")
print(f"📈 Difference: {len(accountant_deals) - 18:+d}")
print()

# Show all deals
print("="*80)
print("ALL ACCOUNTANT DEALS")
print("="*80)
print()

for deal in sorted(accountant_deals, key=lambda x: int(x['deal_id'])):
    print(f"Deal ID: {deal['deal_id']}")
    print(f"  Name: {deal['deal_name'][:60]}")
    print(f"  Amount: ${float(deal['amount']):,.2f}" if deal['amount'] else "  Amount: $0.00")
    print(f"  Created: {deal['createdate']}")
    print(f"  Valid accountant contacts: {len(deal['contacts'])}")
    for contact in deal['contacts']:
        print(f"    • {contact['email']} (created: {contact['createdate']}, {contact['hours_before']:.1f}h before)")
    print()

print("="*80)
print("ANALYSIS")
print("="*80)
print()
if len(accountant_deals) > 18:
    print(f"⚠️  We have {len(accountant_deals) - 18} extra deals.")
    print("Possible reasons:")
    print("  1. HubSpot may use primary contact only (not all contacts)")
    print("  2. HubSpot may require contact created on same day (<= instead of <)")
    print("  3. HubSpot may have different association timing logic")
else:
    print("✅ Deal count matches or is less than HubSpot")

