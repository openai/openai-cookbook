#!/usr/bin/env python3
"""
Investigate Accountant Funnel Deals - Find the 2 extra deals
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
    """Check if rol_wizard indicates accountant role"""
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    rol_lower = str(rol_wizard).lower().strip()
    return any(accountant_role in rol_lower for accountant_role in ACCOUNTANT_ROLES)

def fetch_accountant_mqls(start_date, end_date):
    """Fetch accountant MQL contacts"""
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search"
    all_contacts = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "lead_source", "operator": "NEQ", "value": "Usuario Invitado"}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["email", "createdate", "rol_wizard", "lead_source"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_contacts.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    # Filter for accountant roles
    accountant_mqls = []
    for contact in all_contacts:
        props = contact.get('properties', {})
        rol_wizard = props.get('rol_wizard', '')
        if is_accountant_role(rol_wizard):
            accountant_mqls.append(contact)
    
    return accountant_mqls

def get_contact_deals(contact_id, start_date, end_date):
    """Get deals associated with a contact, created in period"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/deals"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            deal_ids = [assoc.get('toObjectId') for assoc in associations]
            
            if not deal_ids:
                return []
            
            # Fetch deal details
            all_deals = []
            for i in range(0, len(deal_ids), 100):
                batch_ids = deal_ids[i:i+100]
                url_search = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/batch/read"
                payload = {
                    "properties": ["dealname", "createdate", "closedate", "dealstage", "amount"],
                    "inputs": [{"id": deal_id} for deal_id in batch_ids]
                }
                response = requests.post(url_search, headers=HEADERS, json=payload, timeout=30)
                if response.status_code == 200:
                    deals = response.json().get('results', [])
                    all_deals.extend(deals)
            
            # Filter by createdate in period
            deals_in_period = []
            start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
            end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
            for deal in all_deals:
                props = deal.get('properties', {})
                deal_createdate = props.get('createdate', '')
                if deal_createdate:
                    deal_created_dt = datetime.fromisoformat(deal_createdate.replace('Z', '+00:00'))
                    if start_dt <= deal_created_dt < end_dt:
                        deals_in_period.append(deal)
            
            return deals_in_period
    except:
        pass
    return []

def get_deal_contacts(deal_id):
    """Get all contacts associated with a deal"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/contacts"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            contact_ids = [assoc.get('toObjectId') for assoc in associations]
            
            if contact_ids:
                # Fetch contact details
                contacts_data = []
                for i in range(0, len(contact_ids), 100):
                    batch_ids = contact_ids[i:i+100]
                    url_batch = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/batch/read"
                    payload = {
                        "properties": ["email", "createdate", "rol_wizard", "lead_source", "firstname", "lastname"],
                        "inputs": [{"id": contact_id} for contact_id in batch_ids]
                    }
                    response = requests.post(url_batch, headers=HEADERS, json=payload, timeout=30)
                    if response.status_code == 200:
                        contacts = response.json().get('results', [])
                        for contact in contacts:
                            props = contact.get('properties', {})
                            contacts_data.append({
                                'id': contact.get('id'),
                                'email': props.get('email', ''),
                                'createdate': props.get('createdate', ''),
                                'rol_wizard': props.get('rol_wizard', ''),
                                'lead_source': props.get('lead_source', ''),
                                'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
                            })
                return contacts_data
    except:
        pass
    return []

print("="*80)
print("INVESTIGATING ACCOUNTANT FUNNEL DEALS")
print("="*80)
print()

start_date = "2025-12-01"
end_date = "2026-01-01"
start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")

# Step 1: Get all accountant MQL contacts
print("Step 1: Fetching accountant MQL contacts...")
mql_contacts = fetch_accountant_mqls(start_date, end_date)
print(f"Found {len(mql_contacts)} accountant MQL contacts")
print()

# Step 2: Get all deals associated with these contacts
print("Step 2: Fetching deals associated with accountant MQL contacts...")
all_deals_created = []
contact_to_deals = {}

for i, contact in enumerate(mql_contacts, 1):
    if i % 20 == 0:
        print(f"  Processing contact {i}/{len(mql_contacts)}...")
    
    contact_id = contact.get('id')
    contact_props = contact.get('properties', {})
    contact_createdate_str = contact_props.get('createdate', '')
    
    if not contact_createdate_str:
        continue
    
    try:
        contact_created_dt = datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))
    except:
        continue
    
    deals = get_contact_deals(contact_id, start_date, end_date)
    if deals:
        # Validate: Contact must be created before deal
        validated_deals = []
        for deal in deals:
            deal_props = deal.get('properties', {})
            deal_createdate_str = deal_props.get('createdate', '')
            if deal_createdate_str:
                try:
                    deal_created_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                    # Contact must be created before deal
                    if contact_created_dt < deal_created_dt:
                        validated_deals.append(deal)
                except:
                    pass
        
        if validated_deals:
            contact_to_deals[contact_id] = {
                'contact': contact,
                'deals': validated_deals
            }
            all_deals_created.extend(validated_deals)
    
    time.sleep(0.1)

# Remove duplicates
unique_deals_created = {}
for deal in all_deals_created:
    deal_id = deal.get('id')
    if deal_id not in unique_deals_created:
        unique_deals_created[deal_id] = deal

deals_created = list(unique_deals_created.values())
print(f"\nFound {len(deals_created)} unique deals (HubSpot: 18, difference: {len(deals_created) - 18:+d})")
print()

# Step 3: Analyze each deal in detail
print("="*80)
print("DETAILED DEAL ANALYSIS")
print("="*80)
print()

deal_analysis = []

for deal in deals_created:
    deal_id = deal.get('id')
    deal_props = deal.get('properties', {})
    deal_name = deal_props.get('dealname', 'N/A')
    deal_createdate_str = deal_props.get('createdate', '')
    deal_amount = deal_props.get('amount', '0')
    
    # Get all contacts associated with this deal
    deal_contacts = get_deal_contacts(deal_id)
    
    # Find accountant contacts created in December
    accountant_contacts_in_dec = []
    for dc in deal_contacts:
        dc_createdate_str = dc.get('createdate', '')
        if dc_createdate_str:
            try:
                dc_created_dt = datetime.fromisoformat(dc_createdate_str.replace('Z', '+00:00'))
                if start_dt <= dc_created_dt < end_dt:
                    if is_accountant_role(dc.get('rol_wizard', '')):
                        accountant_contacts_in_dec.append(dc)
            except:
                pass
    
    # Check if any accountant contact was created before the deal
    has_valid_contact = False
    contact_details = []
    
    if deal_createdate_str:
        try:
            deal_created_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
            for ac in accountant_contacts_in_dec:
                ac_createdate_str = ac.get('createdate', '')
                if ac_createdate_str:
                    try:
                        ac_created_dt = datetime.fromisoformat(ac_createdate_str.replace('Z', '+00:00'))
                        if ac_created_dt < deal_created_dt:
                            has_valid_contact = True
                            contact_details.append({
                                'email': ac.get('email', ''),
                                'createdate': ac_createdate_str[:10],
                                'rol_wizard': ac.get('rol_wizard', ''),
                                'time_diff_hours': (deal_created_dt - ac_created_dt).total_seconds() / 3600
                            })
                    except:
                        pass
        except:
            pass
    
    deal_analysis.append({
        'deal_id': deal_id,
        'deal_name': deal_name,
        'amount': deal_amount,
        'createdate': deal_createdate_str[:10] if deal_createdate_str else 'N/A',
        'has_valid_contact': has_valid_contact,
        'accountant_contacts_count': len(accountant_contacts_in_dec),
        'valid_contacts': contact_details,
        'all_contacts_count': len(deal_contacts)
    })
    
    time.sleep(0.1)

# Sort by deal ID for easier comparison
deal_analysis.sort(key=lambda x: int(x['deal_id']))

# Display results
print(f"Total deals analyzed: {len(deal_analysis)}")
print()

# Show deals with potential issues
print("="*80)
print("DEALS WITH POTENTIAL ISSUES")
print("="*80)
print()

issues_found = []
for deal in deal_analysis:
    if not deal['has_valid_contact']:
        issues_found.append(deal)
        print(f"⚠️  Deal ID: {deal['deal_id']}")
        print(f"   Name: {deal['deal_name'][:60]}")
        print(f"   Amount: ${float(deal['amount']):,.2f}" if deal['amount'] else "   Amount: $0.00")
        print(f"   Created: {deal['createdate']}")
        print(f"   Accountant contacts in Dec: {deal['accountant_contacts_count']}")
        print(f"   Total contacts: {deal['all_contacts_count']}")
        print(f"   ❌ NO accountant contact created BEFORE deal")
        print()

if not issues_found:
    print("✅ All deals have valid accountant contacts created before them")
    print()
    print("Possible reasons for 2 extra deals:")
    print("  1. HubSpot may use different association logic (primary contact vs all contacts)")
    print("  2. HubSpot may require contact to be created strictly before (not same day)")
    print("  3. HubSpot may filter deals differently based on contact creation timing")
    print()

# Show all deals summary
print("="*80)
print("ALL DEALS SUMMARY")
print("="*80)
print()

for deal in deal_analysis:
    status = "✅" if deal['has_valid_contact'] else "❌"
    print(f"{status} Deal {deal['deal_id']}: {deal['deal_name'][:50]}")
    print(f"   Created: {deal['createdate']} | Valid contact: {deal['has_valid_contact']} | Contacts: {deal['accountant_contacts_count']}")
    if deal['valid_contacts']:
        for contact in deal['valid_contacts']:
            print(f"      • {contact['email']} (created: {contact['createdate']}, {contact['time_diff_hours']:.1f}h before deal)")
    print()

print("="*80)
print("ANALYSIS COMPLETE")
print("="*80)
print(f"Total deals: {len(deal_analysis)}")
print(f"HubSpot shows: 18")
print(f"Difference: {len(deal_analysis) - 18:+d}")
print()

