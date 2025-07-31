#!/usr/bin/env python3
"""
Test script to diagnose company details fetching issues
"""

import requests
import os
import json

# HubSpot API Configuration
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    raise ValueError("HUBSPOT_API_KEY environment variable is required")
HUBSPOT_BASE_URL = 'https://api.hubspot.com'

def make_hubspot_request(endpoint, search_data=None, params=None, method='POST', timeout=30):
    """Make authenticated request to HubSpot API with error handling"""
    url = f"{HUBSPOT_BASE_URL}{endpoint}"
    headers = {
        'Authorization': f'Bearer {HUBSPOT_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        if method == 'POST':
            response = requests.post(url, headers=headers, json=search_data, timeout=timeout)
        else:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response status: {e.response.status_code}")
            print(f"Response text: {e.response.text}")
        return None

def test_company_details():
    """Test fetching details for a few sample company IDs"""
    
    # Test company IDs from the previous output
    test_company_ids = [
        "36677604781",  # Company with 27 deals
        "34346361263",  # ALL SERVICE SRL
        "9018832476"    # DECON
    ]
    
    print(f"🔍 Testing company details fetch for {len(test_company_ids)} companies...")
    
    for company_id in test_company_ids:
        print(f"\n📞 Testing Company ID: {company_id}")
        
        # Method 1: Direct GET request
        print("   Method 1: Direct GET")
        response1 = make_hubspot_request(f'/crm/v3/objects/companies/{company_id}', method='GET')
        if response1:
            props = response1.get('properties', {})
            name = props.get('name', 'NO NAME PROPERTY')
            print(f"   ✅ Name: {name}")
            print(f"   📊 Properties: {list(props.keys())}")
        else:
            print("   ❌ Failed to fetch via direct GET")
        
        # Method 2: Batch read
        print("   Method 2: Batch Read")
        search_data = {
            "inputs": [{"id": company_id}],
            "properties": ["name", "domain", "industry", "city", "state", "id_empresa"]
        }
        response2 = make_hubspot_request('/crm/v3/objects/companies/batch/read', search_data=search_data)
        if response2 and response2.get('results'):
            for company in response2['results']:
                props = company.get('properties', {})
                name = props.get('name', 'NO NAME PROPERTY')
                print(f"   ✅ Batch Name: {name}")
                print(f"   📊 Batch Properties: {list(props.keys())}")
        else:
            print("   ❌ Failed to fetch via batch read")

def test_company_search():
    """Test searching for companies to see if they exist"""
    print(f"\n🔍 Testing company search...")
    
    search_data = {
        "filterGroups": [{
            "filters": [
                {"propertyName": "createdate", "operator": "GTE", "value": "2025-07-01T00:00:00.000Z"}
            ]
        }],
        "properties": ["name", "domain", "createdate"],
        "limit": 5
    }
    
    response = make_hubspot_request('/crm/v3/objects/companies/search', search_data=search_data)
    if response and response.get('results'):
        print(f"   ✅ Found {len(response['results'])} companies")
        for company in response['results']:
            props = company.get('properties', {})
            name = props.get('name', 'NO NAME')
            print(f"   📊 Company: {name} (ID: {company['id']})")
    else:
        print("   ❌ No companies found in search")

if __name__ == "__main__":
    print(f"🧪 COMPANY DETAILS DIAGNOSTIC TEST")
    print(f"🔑 Using API Key: {HUBSPOT_API_KEY[:10]}...")
    print("=" * 60)
    
    test_company_details()
    test_company_search()