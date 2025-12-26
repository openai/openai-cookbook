#!/usr/bin/env python3
"""
Analyze Accountant Funnel Deals - Compare with HubSpot
"""
import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
import time

load_dotenv()
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    print("❌ HUBSPOT_API_KEY not found")
    sys.exit(1)

HUBSPOT_BASE_URL = 'https://api.hubapi.com'
HEADERS = {
    'Authorization': f'Bearer {HUBSPOT_API_KEY}',
    'Content-Type': 'application/json'
}

ACCOUNTANT_ROLES = ['contador', 'estudio contable', 'contador público', 'asesor contable']

def is_accountant_role(rol_wizard):
    if not rol_wizard:
        return False
    rol_lower = str(rol_wizard).lower().strip()
    return any(accountant_role in rol_lower for accountant_role in ACCOUNTANT_ROLES)

def fetch_all_deals_created(start_date, end_date):
    """Fetch all deals created in December"""
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
            "properties": ["dealname", "amount", "createdate", "closedate", "dealstage"],
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
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    return all_deals

def analyze_deal_for_accountant(deal, start_date, end_date):
    """Check if deal should be in accountant funnel"""
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00Z".replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00Z".replace('Z', '+00:00'))
    
    props = deal.get('properties', {})
    deal_id = deal.get('id')
    deal_createdate = props.get('createdate', '')
    
    # Check if created in period
    created_in_period = False
    if deal_createdate:
        try:
            deal_created_dt = datetime.fromisoformat(deal_createdate.replace('Z', '+00:00'))
            created_in_period = start_dt <= deal_created_dt < end_dt
        except:
            pass
    
    if not created_in_period:
        return None
    
    # Get contacts
    associations = deal.get('associations', {})
    contacts = associations.get('contacts', {}).get('results', [])
    
    matching_contacts = []
    
    for contact_assoc in contacts[:5]:  # Check first 5 contacts
        contact_id = contact_assoc.get('id')
        contact_url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}"
        contact_resp = requests.get(contact_url, headers=HEADERS, params={
            'properties': 'email,createdate,rol_wizard,lead_source,firstname,lastname'
        }, timeout=30)
        
        if contact_resp.status_code == 200:
            contact_data = contact_resp.json()
            contact_props = contact_data.get('properties', {})
            rol_wizard = contact_props.get('rol_wizard', '')
            lead_source = contact_props.get('lead_source', '')
            contact_createdate = contact_props.get('createdate', '')
            
            # Check if accountant
            is_accountant = is_accountant_role(rol_wizard)
            
            # Check if created in period
            contact_in_period = False
            if contact_createdate:
                try:
                    contact_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                    contact_in_period = start_dt <= contact_dt < end_dt
                except:
                    pass
            
            if is_accountant and contact_in_period:
                matching_contacts.append({
                    'id': contact_id,
                    'email': contact_props.get('email', 'N/A'),
                    'rol_wizard': rol_wizard,
                    'createdate': contact_createdate[:10] if contact_createdate else 'N/A'
                })
        
        time.sleep(0.1)
    
    if matching_contacts:
        return {
            'deal_id': deal_id,
            'deal_name': props.get('dealname', 'N/A'),
            'amount': props.get('amount', '0'),
            'createdate': deal_createdate[:10] if deal_createdate else 'N/A',
            'dealstage': props.get('dealstage', 'N/A'),
            'matching_contacts': matching_contacts
        }
    
    return None

# Main
print("="*80)
print("ACCOUNTANT FUNNEL DEAL ANALYSIS")
print("="*80)
print()

start_date = "2025-12-01"
end_date = "2026-01-01"

print("Fetching all deals created in December...")
all_deals = fetch_all_deals_created(start_date, end_date)
print(f"Total deals created: {len(all_deals)}")
print()

print("Analyzing deals for accountant funnel...")
accountant_deals = []

for i, deal in enumerate(all_deals, 1):
    if i % 10 == 0:
        print(f"  Processed {i}/{len(all_deals)} deals...")
    result = analyze_deal_for_accountant(deal, start_date, end_date)
    if result:
        accountant_deals.append(result)
    time.sleep(0.1)

print()
print("="*80)
print("RESULTS")
print("="*80)
print(f"Our script found: {len(accountant_deals)} deals")
print(f"HubSpot shows: 18 deals")
print(f"Difference: {len(accountant_deals) - 18}")
print()

if len(accountant_deals) > 18:
    print(f"⚠️  We have {len(accountant_deals) - 18} extra deals:")
    print()
    for deal in accountant_deals:
        print(f"Deal ID: {deal['deal_id']}")
        print(f"  Name: {deal['deal_name'][:60]}")
        print(f"  Amount: ${float(deal['amount']):,.2f}" if deal['amount'] else "  Amount: $0.00")
        print(f"  Matching accountant contacts: {len(deal['matching_contacts'])}")
        for contact in deal['matching_contacts']:
            print(f"    • {contact['email']} (rol_wizard: {contact['rol_wizard']}, created: {contact['createdate']})")
        print()

print("="*80)

