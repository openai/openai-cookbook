#!/usr/bin/env python3
"""
Compare HubSpot Funnel Deals with Our Script Results
=====================================================
This script compares the deals found in HubSpot's funnel report with our script's results.
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
    print("❌ HUBSPOT_API_KEY not found in environment")
    sys.exit(1)

HUBSPOT_BASE_URL = 'https://api.hubapi.com'
HEADERS = {
    'Authorization': f'Bearer {HUBSPOT_API_KEY}',
    'Content-Type': 'application/json'
}

# HubSpot deal IDs from the funnel report image
HUBSPOT_DEAL_IDS = [
    '104584',  # LUIS ERNESTO TAMINI ELICEGUI
    '104554',  # TECNOFLY SOLUTIONS
    '104635',  # EMILIANO MARTIN SCHLISHTING
    '104676',  # FUNDACION ATREVERSE
    '104723',  # CAROLINA ERIKA SZMOISZ
    '104727',  # aa - 24-39644875-7
    '105376',  # LEONES DEL SUR S. A. S.
    '105378',  # COOPERATIVA DE TRABAJO NAVALCOOP
    '105432',  # EQUIPO REDES S.R.L.
    # Note: "Estudio Asesor" deal has no ID shown
]

def is_smb_contact(rol_wizard, lead_source):
    """Check if contact matches SMB criteria"""
    is_smb = True
    if rol_wizard:
        rol_lower = str(rol_wizard).lower()
        accountant_roles = ['contador', 'estudio contable', 'contador público', 'asesor contable']
        if any(role in rol_lower for role in accountant_roles):
            is_smb = False
    if lead_source == 'Usuario Invitado':
        is_smb = False
    return is_smb

def fetch_deal_details(deal_id):
    """Fetch deal details with associated contacts"""
    try:
        url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/{deal_id}"
        params = {
            'properties': 'dealname,amount,createdate,closedate,dealstage,primary_company_type',
            'associations': 'contacts'
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error fetching deal {deal_id}: {e}")
        return None

def fetch_contact_details(contact_id):
    """Fetch contact details"""
    try:
        url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}"
        params = {
            'properties': 'email,createdate,rol_wizard,lead_source,firstname,lastname'
        }
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def main():
    import sys
    sys.stdout.flush()
    print("="*80)
    print("HUBSPOT vs OUR SCRIPT - DEAL COMPARISON")
    print("="*80)
    print()
    sys.stdout.flush()
    
    start_date = "2025-12-01"
    end_date = "2026-01-01"
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00Z".replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00Z".replace('Z', '+00:00'))
    
    # Step 1: Analyze HubSpot's deals
    print("="*80)
    print("STEP 1: ANALYZING HUBSPOT'S DEALS")
    print("="*80)
    print()
    
    hubspot_deals_analysis = []
    
    for deal_id in HUBSPOT_DEAL_IDS:
        print(f"Fetching deal {deal_id}...")
        deal_data = fetch_deal_details(deal_id)
        
        if not deal_data:
            print(f"  ❌ Deal {deal_id} not found")
            continue
        
        props = deal_data.get('properties', {})
        deal_name = props.get('dealname', 'N/A')
        amount = props.get('amount', '0')
        createdate = props.get('createdate', '')
        closedate = props.get('closedate', '')
        
        # Get associated contacts
        associations = deal_data.get('associations', {})
        contacts = associations.get('contacts', {}).get('results', [])
        
        contact_analysis = []
        has_smb_contact_in_dec = False
        
        for contact_assoc in contacts:
            contact_id = contact_assoc.get('id')
            contact_data = fetch_contact_details(contact_id)
            
            if contact_data:
                contact_props = contact_data.get('properties', {})
                rol_wizard = contact_props.get('rol_wizard', '')
                lead_source = contact_props.get('lead_source', '')
                contact_createdate = contact_props.get('createdate', '')
                
                is_smb = is_smb_contact(rol_wizard, lead_source)
                
                contact_in_period = False
                if contact_createdate:
                    try:
                        contact_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                        if start_dt <= contact_dt < end_dt:
                            contact_in_period = True
                    except:
                        pass
                
                contact_analysis.append({
                    'id': contact_id,
                    'email': contact_props.get('email', 'N/A'),
                    'name': f"{contact_props.get('firstname', '')} {contact_props.get('lastname', '')}".strip(),
                    'rol_wizard': rol_wizard,
                    'lead_source': lead_source,
                    'createdate': contact_createdate[:10] if contact_createdate else 'N/A',
                    'is_smb': is_smb,
                    'in_period': contact_in_period
                })
                
                if is_smb and contact_in_period:
                    has_smb_contact_in_dec = True
        
        hubspot_deals_analysis.append({
            'deal_id': deal_id,
            'deal_name': deal_name,
            'amount': amount,
            'createdate': createdate[:10] if createdate else 'N/A',
            'closedate': closedate[:10] if closedate else 'N/A',
            'has_smb_contact_in_dec': has_smb_contact_in_dec,
            'contacts': contact_analysis
        })
        
        status = "✅" if has_smb_contact_in_dec else "❌"
        print(f"  {status} {deal_name[:50]}")
        print(f"     Amount: ${float(amount):,.2f}" if amount else "     Amount: $0.00")
        print(f"     Has SMB contact (created in Dec): {has_smb_contact_in_dec}")
        print()
        time.sleep(0.2)
    
    # Step 2: Fetch all deals created in December (our script's logic)
    print("="*80)
    print("STEP 2: FETCHING ALL DEALS CREATED IN DECEMBER")
    print("="*80)
    print()
    
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    all_deals = []
    after = None
    page = 0
    
    while True:
        page += 1
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
        print(f"  Page {page}: {len(results)} deals (total: {len(all_deals)})")
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    print(f"\n✅ Total deals created in December: {len(all_deals)}")
    print()
    
    # Step 3: Filter for deals with SMB contacts (our script's logic)
    print("="*80)
    print("STEP 3: FILTERING DEALS WITH SMB CONTACTS (OUR SCRIPT LOGIC)")
    print("="*80)
    print()
    
    our_script_deals = []
    
    for deal in all_deals:
        deal_id = deal.get('id')
        associations = deal.get('associations', {})
        contacts = associations.get('contacts', {}).get('results', [])
        
        has_smb_contact = False
        for contact_assoc in contacts[:5]:  # Check first 5 contacts
            contact_id = contact_assoc.get('id')
            contact_data = fetch_contact_details(contact_id)
            
            if contact_data:
                contact_props = contact_data.get('properties', {})
                rol_wizard = contact_props.get('rol_wizard', '')
                lead_source = contact_props.get('lead_source', '')
                contact_createdate = contact_props.get('createdate', '')
                
                is_smb = is_smb_contact(rol_wizard, lead_source)
                
                contact_in_period = False
                if contact_createdate:
                    try:
                        contact_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                        if start_dt <= contact_dt < end_dt:
                            contact_in_period = True
                    except:
                        pass
                
                if is_smb and contact_in_period:
                    has_smb_contact = True
                    break
            
            time.sleep(0.1)
        
        if has_smb_contact:
            our_script_deals.append(deal_id)
    
    print(f"✅ Deals with SMB contacts (created in Dec): {len(our_script_deals)}")
    print()
    
    # Step 4: Compare
    print("="*80)
    print("STEP 4: COMPARISON RESULTS")
    print("="*80)
    print()
    
    our_deal_ids_set = set(our_script_deals)
    hubspot_deal_ids_set = set(HUBSPOT_DEAL_IDS)
    
    matching = our_deal_ids_set.intersection(hubspot_deal_ids_set)
    only_ours = our_deal_ids_set - hubspot_deal_ids_set
    only_hubspot = hubspot_deal_ids_set - our_deal_ids_set
    
    print(f"✅ Matching deals: {len(matching)}")
    if matching:
        print(f"   IDs: {sorted([int(d) for d in matching])}")
    print()
    print(f"⚠️  Only in our script: {len(only_ours)}")
    if only_ours:
        print(f"   IDs: {sorted([int(d) for d in only_ours])}")
    print()
    print(f"⚠️  Only in HubSpot: {len(only_hubspot)}")
    if only_hubspot:
        print(f"   IDs: {sorted([int(d) for d in only_hubspot])}")
    print()
    
    # Step 5: Detailed analysis
    print("="*80)
    print("STEP 5: DETAILED ANALYSIS")
    print("="*80)
    print()
    
    print("HubSpot Deals Analysis:")
    for deal in hubspot_deals_analysis:
        status = "✅" if deal['has_smb_contact_in_dec'] else "❌"
        print(f"  {status} {deal['deal_id']}: {deal['deal_name'][:50]}")
        print(f"     Has SMB contact (created in Dec): {deal['has_smb_contact_in_dec']}")
        if deal['contacts']:
            smb_contacts = [c for c in deal['contacts'] if c['is_smb'] and c['in_period']]
            print(f"     SMB contacts in period: {len(smb_contacts)}")
    print()
    
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print()
    print(f"Our Script: {len(our_script_deals)} deals")
    print(f"HubSpot: {len(HUBSPOT_DEAL_IDS)} deals")
    print(f"Matching: {len(matching)} deals")
    print(f"Difference: {len(our_script_deals) - len(HUBSPOT_DEAL_IDS)} deals")
    print()

if __name__ == "__main__":
    main()

