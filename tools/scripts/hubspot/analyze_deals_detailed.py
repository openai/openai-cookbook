#!/usr/bin/env python3
"""
Detailed Deal Analysis - Compare HubSpot vs Our Script
=======================================================
Analyzes each deal individually to understand differences
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

# HubSpot deal IDs from funnel report
HUBSPOT_DEAL_IDS = [
    '104584', '104554', '104635', '104676', '104723', 
    '104727', '105376', '105378', '105432'
]

ACCOUNTANT_ROLES = ['contador', 'estudio contable', 'contador público', 'asesor contable']

def is_accountant_role(rol_wizard):
    if not rol_wizard:
        return False
    rol_lower = str(rol_wizard).lower().strip()
    return any(role in rol_lower for role in ACCOUNTANT_ROLES)

def is_smb_role(rol_wizard):
    """FIXED: Excludes null/empty values"""
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    return not is_accountant_role(rol_wizard)

def fetch_deal_with_contacts(deal_id):
    """Fetch deal with all associated contacts"""
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

def analyze_deal(deal_id, start_date, end_date):
    """Analyze a single deal to see if it matches our criteria"""
    deal_data = fetch_deal_with_contacts(deal_id)
    if not deal_data:
        return None
    
    props = deal_data.get('properties', {})
    deal_name = props.get('dealname', 'N/A')
    amount = props.get('amount', '0')
    deal_createdate = props.get('createdate', '')
    deal_closedate = props.get('closedate', '')
    
    # Parse dates
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
    
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00Z".replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00Z".replace('Z', '+00:00'))
    
    # Check if deal created in period
    created_in_period = deal_created_dt and (start_dt <= deal_created_dt < end_dt)
    
    # Get associated contacts
    associations = deal_data.get('associations', {})
    contacts = associations.get('contacts', {}).get('results', [])
    
    contact_analysis = []
    has_smb_contact_in_dec = False
    matching_contacts = []
    
    for contact_assoc in contacts:
        contact_id = contact_assoc.get('id')
        contact_data = fetch_contact_details(contact_id)
        
        if contact_data:
            contact_props = contact_data.get('properties', {})
            rol_wizard = contact_props.get('rol_wizard', '')
            lead_source = contact_props.get('lead_source', '')
            contact_createdate = contact_props.get('createdate', '')
            
            # Parse contact created date
            contact_created_dt = None
            if contact_createdate:
                try:
                    contact_created_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                except:
                    pass
            
            # Check criteria
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
            
            contact_analysis.append(contact_info)
            
            if is_smb and contact_in_period:
                has_smb_contact_in_dec = True
                if contact_before_deal or not deal_created_dt:
                    matching_contacts.append(contact_info)
        
        time.sleep(0.1)
    
    return {
        'deal_id': deal_id,
        'deal_name': deal_name,
        'amount': amount,
        'createdate': deal_createdate[:10] if deal_createdate else 'N/A',
        'closedate': deal_closedate[:10] if deal_closedate else 'N/A',
        'dealstage': props.get('dealstage', 'N/A'),
        'created_in_period': created_in_period,
        'has_smb_contact_in_dec': has_smb_contact_in_dec,
        'matching_contacts': matching_contacts,
        'all_contacts': contact_analysis,
        'should_be_in_our_script': created_in_period and has_smb_contact_in_dec
    }

def main():
    print("="*80)
    print("DETAILED DEAL ANALYSIS - HUBSPOT vs OUR SCRIPT")
    print("="*80)
    print()
    
    start_date = "2025-12-01"
    end_date = "2026-01-01"
    
    print("Analyzing HubSpot's deals one by one...")
    print()
    
    results = []
    for i, deal_id in enumerate(HUBSPOT_DEAL_IDS, 1):
        print(f"[{i}/{len(HUBSPOT_DEAL_IDS)}] Analyzing deal {deal_id}...")
        analysis = analyze_deal(deal_id, start_date, end_date)
        if analysis:
            results.append(analysis)
            status = "✅" if analysis['should_be_in_our_script'] else "❌"
            print(f"  {status} {analysis['deal_name'][:50]}")
            print(f"     Should be in our script: {analysis['should_be_in_our_script']}")
            print(f"     Has SMB contact (created in Dec): {analysis['has_smb_contact_in_dec']}")
            print(f"     Matching contacts: {len(analysis['matching_contacts'])}")
        print()
        time.sleep(0.3)
    
    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print()
    
    matching = [r for r in results if r['should_be_in_our_script']]
    not_matching = [r for r in results if not r['should_be_in_our_script']]
    
    print(f"✅ Deals that SHOULD be in our script: {len(matching)}")
    print(f"❌ Deals that should NOT be in our script: {len(not_matching)}")
    print()
    
    # Detailed breakdown
    print("="*80)
    print("DETAILED BREAKDOWN")
    print("="*80)
    print()
    
    for result in results:
        print(f"Deal ID: {result['deal_id']}")
        print(f"Name: {result['deal_name']}")
        print(f"Amount: ${float(result['amount']):,.2f}" if result['amount'] else "Amount: $0.00")
        print(f"Created: {result['createdate']} (in period: {result['created_in_period']})")
        print(f"Closed: {result['closedate']} | Stage: {result['dealstage']}")
        print(f"Should be in our script: {result['should_be_in_our_script']}")
        print()
        print(f"Associated Contacts: {len(result['all_contacts'])}")
        print(f"  SMB contacts (created in Dec): {len(result['matching_contacts'])}")
        print()
        
        if result['matching_contacts']:
            print("  ✅ Matching Contacts (SMB + created in Dec):")
            for contact in result['matching_contacts']:
                print(f"     • {contact['name']} ({contact['email']})")
                print(f"       rol_wizard: {contact['rol_wizard']}")
                print(f"       lead_source: {contact['lead_source']}")
                print(f"       created: {contact['createdate']}")
                print(f"       created before deal: {contact['before_deal']}")
        else:
            print("  ❌ No matching contacts found")
            print("  All contacts:")
            for contact in result['all_contacts']:
                status = "✅" if contact['matches_criteria'] else "❌"
                print(f"     {status} {contact['name']} ({contact['email']})")
                print(f"        rol_wizard: {contact['rol_wizard']} | is_smb: {contact['is_smb']}")
                print(f"        lead_source: {contact['lead_source']}")
                print(f"        created: {contact['createdate']} | in_period: {contact['in_period']}")
                print(f"        created before deal: {contact['before_deal']}")
        
        print()
        print("-"*80)
        print()

if __name__ == "__main__":
    main()

