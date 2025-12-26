#!/usr/bin/env python3
"""
Show real examples of MQL contacts with SQL conversion but NO deal associations
"""

import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
HUBSPOT_BASE_URL = 'https://api.hubapi.com'
HEADERS = {
    'Authorization': f'Bearer {HUBSPOT_API_KEY}',
    'Content-Type': 'application/json'
}

# Real examples from the script output
examples = [
    {
        'email': 'wandalemma@indy.com.ar',
        'contact_id': None,  # Will fetch
        'created_date': '2025-12-12',
        'sql_date': '2025-12-12'
    },
    {
        'email': 'ppacheco@steplix.com',
        'contact_id': None,  # Will fetch
        'created_date': '2025-12-18',
        'sql_date': '2025-12-18'
    }
]

def get_contact_by_email(email):
    """Get contact ID by email"""
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search"
    payload = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "email",
                "operator": "EQ",
                "value": email
            }]
        }],
        "properties": ["email", "createdate", "hs_v2_date_entered_opportunity", "rol_wizard", "firstname", "lastname"],
        "limit": 1
    }
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                return results[0]
    except:
        pass
    return None

def get_contact_deals(contact_id):
    """Get all deals associated with contact"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/deals"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            return [assoc.get('toObjectId') for assoc in associations]
    except:
        pass
    return []

def get_contact_companies(contact_id):
    """Get companies associated with contact"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/companies"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            return [assoc.get('toObjectId') for assoc in associations]
    except:
        pass
    return []

def get_company_deals(company_id):
    """Get all deals for a company"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/companies/{company_id}/associations/deals"
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
            
            return all_deals
    except:
        pass
    return []

print("="*80)
print("REAL EXAMPLES: MQL Contacts with SQL Conversion but NO Deal Associations")
print("="*80)
print()

for example in examples:
    email = example['email']
    print(f"**Example: {email}**")
    print()
    
    # Get contact details
    contact = get_contact_by_email(email)
    if not contact:
        print(f"  ❌ Contact not found")
        print()
        continue
    
    contact_id = contact.get('id')
    props = contact.get('properties', {})
    
    print(f"  **Contact Details:**")
    print(f"  - Contact ID: {contact_id}")
    print(f"  - Email: {props.get('email', 'N/A')}")
    print(f"  - Name: {props.get('firstname', '')} {props.get('lastname', '')}".strip() or 'N/A')
    print(f"  - Created Date: {props.get('createdate', 'N/A')}")
    print(f"  - SQL Date (hs_v2_date_entered_opportunity): {props.get('hs_v2_date_entered_opportunity', 'N/A')}")
    print(f"  - Rol Wizard: {props.get('rol_wizard', 'N/A')}")
    print()
    
    # Check deal associations
    print(f"  **Deal Associations:**")
    deal_ids = get_contact_deals(contact_id)
    if deal_ids:
        print(f"  - Associated Deal IDs: {deal_ids}")
    else:
        print(f"  ❌ NO DEALS ASSOCIATED WITH CONTACT")
    print()
    
    # Check company deals
    print(f"  **Company Deals (not associated with contact):**")
    company_ids = get_contact_companies(contact_id)
    if company_ids:
        print(f"  - Associated Company IDs: {company_ids}")
        for company_id in company_ids:
            company_deals = get_company_deals(company_id)
            if company_deals:
                print(f"  - Company {company_id} has {len(company_deals)} deal(s):")
                for deal in company_deals:
                    deal_props = deal.get('properties', {})
                    deal_id = deal.get('id')
                    deal_name = deal_props.get('dealname', 'N/A')
                    deal_created = deal_props.get('createdate', 'N/A')[:10] if deal_props.get('createdate') else 'N/A'
                    deal_stage = deal_props.get('dealstage', 'N/A')
                    is_associated = deal_id in deal_ids if deal_ids else False
                    print(f"    • {deal_name} (ID: {deal_id})")
                    print(f"      Created: {deal_created}, Stage: {deal_stage}")
                    print(f"      Associated with contact: {'✅ YES' if is_associated else '❌ NO'}")
            else:
                print(f"  - Company {company_id}: No deals")
    else:
        print(f"  - No companies associated")
    print()
    
    print("="*80)
    print()

