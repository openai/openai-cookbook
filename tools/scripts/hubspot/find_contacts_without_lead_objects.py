#!/usr/bin/env python3
"""
Find Contacts Without Lead Objects
==================================
Finds contacts created in a period that don't have associated Lead objects,
likely because the workflow that creates leads failed.

Usage:
  python find_contacts_without_lead_objects.py --month 2025-12
  python find_contacts_without_lead_objects.py --start-date 2025-12-01 --end-date 2026-01-01
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

ACCOUNTANT_ROLES = ['contador', 'estudio contable', 'contador público', 'asesor contable']

def is_accountant_role(rol_wizard):
    """Check if rol_wizard indicates accountant role"""
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    rol_lower = str(rol_wizard).lower().strip()
    return 'conta' in rol_lower

def check_lead_association(contact_id):
    """Check if a contact has an associated Lead object"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/leads"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            result = response.json()
            associations = result.get('results', [])
            return len(associations) > 0
        return False
    except:
        return False

def fetch_contacts_without_leads(start_date, end_date, limit=5):
    """
    Fetch contacts created in period with accountant rol_wizard that don't have Lead objects
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search"
    all_contacts = []
    after = None
    
    print(f"🔍 Fetching contacts created between {start_date} and {end_date}...")
    print(f"   Filters: rol_wizard contains 'contador', lead_source ≠ 'Usuario Invitado', Lead status is known")
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "lead_source", "operator": "NEQ", "value": "Usuario Invitado"}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["email", "createdate", "firstname", "lastname", "lead_source", "rol_wizard", 
                          "hs_lead_status", "lifecyclestage", "hs_v2_date_entered_lead"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_contacts.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    # Filter for accountant roles
    accountant_contacts = []
    for contact in all_contacts:
        props = contact.get('properties', {})
        rol_wizard = props.get('rol_wizard', '')
        if is_accountant_role(rol_wizard):
            accountant_contacts.append(contact)
    
    print(f"   Found {len(accountant_contacts)} contacts with accountant rol_wizard")
    print(f"\n🔍 Checking which contacts don't have Lead objects associated...")
    
    # Check Lead associations
    contacts_without_leads = []
    for i, contact in enumerate(accountant_contacts):
        if len(contacts_without_leads) >= limit:
            break
        
        contact_id = contact['id']
        has_lead = check_lead_association(contact_id)
        
        if not has_lead:
            contacts_without_leads.append(contact)
        
        if (i + 1) % 10 == 0:
            print(f"   Progress: {i + 1}/{len(accountant_contacts)} contacts checked...")
        
        time.sleep(0.1)  # Rate limiting
    
    return contacts_without_leads

def format_contact_info(contact):
    """Format contact information for display"""
    props = contact.get('properties', {})
    contact_id = contact.get('id', 'N/A')
    
    email = props.get('email', 'N/A')
    firstname = props.get('firstname', '')
    lastname = props.get('lastname', '')
    name = f"{firstname} {lastname}".strip() or 'N/A'
    
    createdate = props.get('createdate', '')
    if createdate:
        try:
            dt = datetime.fromisoformat(createdate.replace('Z', '+00:00'))
            createdate = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    lead_source = props.get('lead_source', 'N/A')
    rol_wizard = props.get('rol_wizard', 'N/A')
    hs_lead_status = props.get('hs_lead_status', 'N/A')
    lifecyclestage = props.get('lifecyclestage', 'N/A')
    hs_v2_date_entered_lead = props.get('hs_v2_date_entered_lead', 'N/A')
    
    hubspot_url = f"https://app.hubspot.com/contacts/19877595/contact/{contact_id}"
    
    return {
        'contact_id': contact_id,
        'name': name,
        'email': email,
        'createdate': createdate,
        'lead_source': lead_source,
        'rol_wizard': rol_wizard,
        'hs_lead_status': hs_lead_status,
        'lifecyclestage': lifecyclestage,
        'hs_v2_date_entered_lead': hs_v2_date_entered_lead,
        'hubspot_url': hubspot_url
    }

def main():
    parser = argparse.ArgumentParser(description='Find contacts without Lead objects')
    parser.add_argument('--month', type=str, help='Month in YYYY-MM format (e.g., 2025-12)')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    parser.add_argument('--limit', type=int, default=5, help='Number of examples to return (default: 5)')
    
    args = parser.parse_args()
    
    # Determine date range
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
        # Default to current month
        now = datetime.now()
        start_date = f"{now.year}-{now.month:02d}-01"
        if now.month == 12:
            end_date = f"{now.year+1}-01-01"
        else:
            end_date = f"{now.year}-{now.month+1:02d}-01"
    
    print(f"{'='*100}")
    print("CONTACTS WITHOUT LEAD OBJECTS")
    print(f"{'='*100}")
    print(f"\n📅 Period: {start_date} to {end_date}")
    print(f"🔍 Looking for contacts with accountant rol_wizard that don't have Lead objects...")
    print()
    
    contacts_without_leads = fetch_contacts_without_leads(start_date, end_date, limit=args.limit)
    
    if not contacts_without_leads:
        print(f"\n✅ All contacts have Lead objects associated!")
        return
    
    print(f"\n{'='*100}")
    print(f"FOUND {len(contacts_without_leads)} CONTACTS WITHOUT LEAD OBJECTS")
    print(f"{'='*100}\n")
    
    for i, contact in enumerate(contacts_without_leads, 1):
        info = format_contact_info(contact)
        print(f"Example {i}:")
        print(f"  Contact ID: {info['contact_id']}")
        print(f"  Name: {info['name']}")
        print(f"  Email: {info['email']}")
        print(f"  Created: {info['createdate']}")
        print(f"  Lead Source: {info['lead_source']}")
        print(f"  Rol Wizard: {info['rol_wizard']}")
        print(f"  Lead Status: {info['hs_lead_status']}")
        print(f"  Lifecycle Stage: {info['lifecyclestage']}")
        print(f"  Date Entered Lead: {info['hs_v2_date_entered_lead']}")
        print(f"  HubSpot URL: {info['hubspot_url']}")
        print()

if __name__ == '__main__':
    main()












