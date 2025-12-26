#!/usr/bin/env python3
"""
Analyze HubSpot's 10 deals to understand why they're in the funnel
"""
import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
import json

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

HUBSPOT_DEAL_IDS = ['104584', '104554', '104635', '104676', '104723', '104727', '105376', '105378', '105432']
ACCOUNTANT_ROLES = ['contador', 'estudio contable', 'contador público', 'asesor contable']

def is_accountant_role(rol_wizard):
    if not rol_wizard:
        return False
    return any(role in str(rol_wizard).lower().strip() for role in ACCOUNTANT_ROLES)

def is_smb_role(rol_wizard):
    """FIXED: Excludes null/empty values"""
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    return not is_accountant_role(rol_wizard)

def analyze_deal(deal_id, start_date, end_date):
    """Analyze a single deal"""
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00Z".replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00Z".replace('Z', '+00:00'))
    
    # Fetch deal
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/{deal_id}"
    params = {
        'properties': 'dealname,amount,createdate,closedate,dealstage,primary_company_type',
        'associations': 'contacts'
    }
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    
    if response.status_code != 200:
        return {'error': f"Status {response.status_code}"}
    
    deal_data = response.json()
    props = deal_data.get('properties', {})
    deal_name = props.get('dealname', 'N/A')
    amount = props.get('amount', '0')
    deal_createdate = props.get('createdate', '')
    deal_closedate = props.get('closedate', '')
    
    # Check dates
    deal_created_dt = None
    deal_closed_dt = None
    if deal_createdate:
        try:
            deal_created_dt = datetime.fromisoformat(deal_createdate.replace('Z', '+00:00'))
        except:
            pass
    if deal_closedate:
        try:
            deal_closed_dt = datetime.fromisoformat(deal_closedate.replace('Z', '+00:00'))
        except:
            pass
    
    created_in_period = deal_created_dt and (start_dt <= deal_created_dt < end_dt)
    closed_in_period = deal_closed_dt and (start_dt <= deal_closed_dt < end_dt)
    
    # Get contacts
    associations = deal_data.get('associations', {})
    contacts = associations.get('contacts', {}).get('results', [])
    
    contact_details = []
    matching_contacts = []
    
    for contact_assoc in contacts:
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
            
            # Parse dates
            contact_created_dt = None
            if contact_createdate:
                try:
                    contact_created_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                except:
                    pass
            
            is_smb = is_smb_role(rol_wizard)
            contact_in_period = contact_created_dt and (start_dt <= contact_created_dt < end_dt)
            contact_before_deal = contact_created_dt and deal_created_dt and (contact_created_dt <= deal_created_dt)
            
            contact_info = {
                'id': contact_id,
                'email': contact_props.get('email', 'N/A'),
                'name': f"{contact_props.get('firstname', '')} {contact_props.get('lastname', '')}".strip(),
                'rol_wizard': rol_wizard or '(null)',
                'lead_source': lead_source or '(null)',
                'createdate': contact_createdate[:10] if contact_createdate else 'N/A',
                'is_smb': is_smb,
                'in_period': contact_in_period,
                'before_deal': contact_before_deal,
                'matches_criteria': is_smb and contact_in_period
            }
            
            contact_details.append(contact_info)
            if is_smb and contact_in_period:
                matching_contacts.append(contact_info)
    
    return {
        'deal_id': deal_id,
        'deal_name': deal_name,
        'amount': amount,
        'createdate': deal_createdate[:10] if deal_createdate else 'N/A',
        'closedate': deal_closedate[:10] if deal_closedate else 'N/A',
        'dealstage': props.get('dealstage', 'N/A'),
        'created_in_period': created_in_period,
        'closed_in_period': closed_in_period,
        'total_contacts': len(contact_details),
        'matching_contacts': len(matching_contacts),
        'contacts': contact_details,
        'should_be_in_script': created_in_period and len(matching_contacts) > 0
    }

# Main analysis
print("="*80)
print("HUBSPOT DEALS ANALYSIS - DECEMBER 2025")
print("="*80)
print()

start_date = "2025-12-01"
end_date = "2026-01-01"

results = []
for i, deal_id in enumerate(HUBSPOT_DEAL_IDS, 1):
    print(f"[{i}/{len(HUBSPOT_DEAL_IDS)}] Analyzing deal {deal_id}...", flush=True)
    result = analyze_deal(deal_id, start_date, end_date)
    if 'error' not in result:
        results.append(result)
        status = "✅" if result['should_be_in_script'] else "❌"
        print(f"  {status} {result['deal_name'][:50]}")
        print(f"     Created in Dec: {result['created_in_period']} | SMB contacts: {result['matching_contacts']}/{result['total_contacts']}")
    else:
        print(f"  ❌ Error: {result['error']}")
    print()

# Summary
print("="*80)
print("SUMMARY")
print("="*80)
print()

matching = [r for r in results if r['should_be_in_script']]
not_matching = [r for r in results if not r['should_be_in_script']]

print(f"✅ Deals that SHOULD be in our script: {len(matching)}")
print(f"❌ Deals that should NOT be in our script: {len(not_matching)}")
print()

# Detailed breakdown
print("="*80)
print("DETAILED BREAKDOWN")
print("="*80)
print()

for result in results:
    print(f"\n{'='*80}")
    print(f"Deal ID: {result['deal_id']}")
    print(f"Name: {result['deal_name']}")
    print(f"Amount: ${float(result['amount']):,.2f}" if result['amount'] else "Amount: $0.00")
    print(f"Created: {result['createdate']} (in period: {result['created_in_period']})")
    print(f"Closed: {result['closedate']} (in period: {result['closed_in_period']}) | Stage: {result['dealstage']}")
    print(f"Should be in our script: {result['should_be_in_script']}")
    print(f"Total contacts: {result['total_contacts']} | Matching SMB contacts: {result['matching_contacts']}")
    print()
    
    if result['matching_contacts'] > 0:
        print("✅ MATCHING CONTACTS (SMB + created in Dec):")
        for contact in result['contacts']:
            if contact['matches_criteria']:
                print(f"  • {contact['name']} ({contact['email']})")
                print(f"    rol_wizard: {contact['rol_wizard']}")
                print(f"    lead_source: {contact['lead_source']}")
                print(f"    created: {contact['createdate']}")
                print(f"    created before deal: {contact['before_deal']}")
    else:
        print("❌ NO MATCHING CONTACTS. All contacts:")
        for contact in result['contacts']:
            print(f"  • {contact['name']} ({contact['email']})")
            print(f"    rol_wizard: {contact['rol_wizard']} | is_smb: {contact['is_smb']}")
            print(f"    lead_source: {contact['lead_source']}")
            print(f"    created: {contact['createdate']} | in_period: {contact['in_period']}")
            print(f"    created before deal: {contact['before_deal']}")

print()
print("="*80)
print("ANALYSIS COMPLETE")
print("="*80)

