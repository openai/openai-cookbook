#!/usr/bin/env python3
import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
import time

load_dotenv()
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    print("❌ HUBSPOT_API_KEY not found", flush=True)
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
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    return not is_accountant_role(rol_wizard)

print("="*80, flush=True)
print("DEAL ANALYSIS - HUBSPOT vs OUR SCRIPT", flush=True)
print("="*80, flush=True)
print(flush=True)

start_date = "2025-12-01"
end_date = "2026-01-01"
start_dt = datetime.fromisoformat(f"{start_date}T00:00:00Z".replace('Z', '+00:00'))
end_dt = datetime.fromisoformat(f"{end_date}T00:00:00Z".replace('Z', '+00:00'))

results = []

for i, deal_id in enumerate(HUBSPOT_DEAL_IDS, 1):
    print(f"[{i}/{len(HUBSPOT_DEAL_IDS)}] Analyzing deal {deal_id}...", flush=True)
    
    # Fetch deal
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/{deal_id}"
    params = {
        'properties': 'dealname,amount,createdate,closedate,dealstage',
        'associations': 'contacts'
    }
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    
    if response.status_code != 200:
        print(f"  ❌ Error: {response.status_code}", flush=True)
        continue
    
    deal_data = response.json()
    props = deal_data.get('properties', {})
    deal_name = props.get('dealname', 'N/A')
    amount = props.get('amount', '0')
    deal_createdate = props.get('createdate', '')
    
    # Check if created in period
    created_in_period = False
    if deal_createdate:
        try:
            deal_created_dt = datetime.fromisoformat(deal_createdate.replace('Z', '+00:00'))
            created_in_period = start_dt <= deal_created_dt < end_dt
        except:
            pass
    
    # Get contacts
    associations = deal_data.get('associations', {})
    contacts = associations.get('contacts', {}).get('results', [])
    
    matching_contacts = []
    all_contact_details = []
    
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
            
            is_smb = is_smb_role(rol_wizard)
            contact_in_period = False
            
            if contact_createdate:
                try:
                    contact_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                    contact_in_period = start_dt <= contact_dt < end_dt
                except:
                    pass
            
            contact_info = {
                'email': contact_props.get('email', 'N/A'),
                'rol_wizard': rol_wizard or '(null)',
                'lead_source': lead_source or '(null)',
                'createdate': contact_createdate[:10] if contact_createdate else 'N/A',
                'is_smb': is_smb,
                'in_period': contact_in_period,
                'matches': is_smb and contact_in_period
            }
            
            all_contact_details.append(contact_info)
            if is_smb and contact_in_period:
                matching_contacts.append(contact_info)
        
        time.sleep(0.1)
    
    should_be_in_script = created_in_period and len(matching_contacts) > 0
    
    result = {
        'deal_id': deal_id,
        'deal_name': deal_name,
        'amount': amount,
        'created_in_period': created_in_period,
        'matching_contacts': len(matching_contacts),
        'total_contacts': len(all_contact_details),
        'should_be_in_script': should_be_in_script,
        'contacts': all_contact_details
    }
    results.append(result)
    
    status = "✅" if should_be_in_script else "❌"
    print(f"  {status} {deal_name[:50]}", flush=True)
    print(f"     Created in Dec: {created_in_period} | SMB contacts: {len(matching_contacts)}/{len(all_contact_details)}", flush=True)
    print(flush=True)
    time.sleep(0.2)

# Summary
print("="*80, flush=True)
print("SUMMARY", flush=True)
print("="*80, flush=True)
print(flush=True)

matching = [r for r in results if r['should_be_in_script']]
not_matching = [r for r in results if not r['should_be_in_script']]

print(f"✅ Should be in our script: {len(matching)}", flush=True)
print(f"❌ Should NOT be in our script: {len(not_matching)}", flush=True)
print(flush=True)

# Detailed breakdown
print("="*80, flush=True)
print("DETAILED BREAKDOWN", flush=True)
print("="*80, flush=True)
print(flush=True)

for result in results:
    print(f"\nDeal ID: {result['deal_id']}", flush=True)
    print(f"Name: {result['deal_name']}", flush=True)
    print(f"Amount: ${float(result['amount']):,.2f}" if result['amount'] else "Amount: $0.00", flush=True)
    print(f"Created in Dec: {result['created_in_period']}", flush=True)
    print(f"Should be in script: {result['should_be_in_script']}", flush=True)
    print(f"Contacts: {result['matching_contacts']} matching / {result['total_contacts']} total", flush=True)
    
    if result['matching_contacts'] > 0:
        print("  ✅ Matching contacts:", flush=True)
        for contact in result['contacts']:
            if contact['matches']:
                print(f"     • {contact['email']}", flush=True)
                print(f"       rol_wizard: {contact['rol_wizard']} | created: {contact['createdate']}", flush=True)
    else:
        print("  ❌ No matching contacts. All contacts:", flush=True)
        for contact in result['contacts']:
            print(f"     • {contact['email']}", flush=True)
            print(f"       rol_wizard: {contact['rol_wizard']} | is_smb: {contact['is_smb']} | in_period: {contact['in_period']}", flush=True)
    print("-"*80, flush=True)

print("\n✅ Analysis complete!", flush=True)

