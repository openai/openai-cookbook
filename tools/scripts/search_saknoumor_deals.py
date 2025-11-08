#!/usr/bin/env python3
"""
Search for all SAKNOUMOR deals to find the correct deal IDs
"""

import requests
import json
import os

def search_saknoumor_deals():
    """
    Search for all deals related to SAKNOUMOR to find the actual deal IDs
    """

    print("🔍 SEARCHING FOR SAKNOUMOR DEALS")
    print("=" * 50)

    access_token = os.getenv('ColppyCRMAutomations')
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    # Search for deals containing "SAKNOUMOR"
    search_url = "https://api.hubapi.com/crm/v3/objects/deals/search"

    search_data = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "dealname",
                "operator": "CONTAINS_TOKEN",
                "value": "SAKNOUMOR"
            }]
        }],
        "properties": [
            "dealname", "amount", "dealstage", "closedate",
            "createdate", "hs_object_id", "empresa_adicional"
        ],
        "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
        "limit": 20
    }

    try:
        print("🔍 Searching for deals containing 'SAKNOUMOR'...")
        response = requests.post(search_url, headers=headers, json=search_data)

        if response.status_code == 200:
            results = response.json()
            deals = results.get('results', [])

            print(f"📋 Found {len(deals)} SAKNOUMOR deals:")
            print("=" * 80)

            for i, deal in enumerate(deals, 1):
                deal_id = deal['id']
                properties = deal.get('properties', {})
                deal_name = properties.get('dealname', 'Unknown')
                amount = properties.get('amount', 'Unknown')
                create_date = properties.get('createdate', 'Unknown')
                empresa_adicional = properties.get('empresa_adicional', 'Unknown')

                print(f"\n{i}. Deal ID: {deal_id}")
                print(f"   Name: {deal_name}")
                print(f"   Amount: {amount}")
                print(f"   Created: {create_date}")
                print(f"   Empresa Adicional: {empresa_adicional}")

                # Check associations for each deal
                print(f"   🔗 Checking associations...")
                assoc_url = f"https://api.hubapi.com/crm/v4/objects/deals/{deal_id}/associations/companies"
                assoc_response = requests.get(assoc_url, headers=headers)

                if assoc_response.status_code == 200:
                    associations = assoc_response.json()
                    results_list = associations.get('results', [])

                    if len(results_list) == 0:
                        print(f"   ❌ NO COMPANY ASSOCIATIONS - This might be the orphaned deal!")
                    else:
                        print(f"   ✅ {len(results_list)} company associations:")
                        for assoc in results_list:
                            company_id = assoc['toObjectId']
                            assoc_types = assoc.get('associationTypes', [])
                            for assoc_type in assoc_types:
                                type_id = assoc_type.get('typeId')
                                label = assoc_type.get('label') or 'No Label'
                                if type_id == 5:
                                    print(f"      🚨 PRIMARY with company {company_id}")
                                else:
                                    print(f"      📎 Type {type_id}: {label} with company {company_id}")

            # Also search by company association
            print(f"\n" + "=" * 80)
            print("🔍 Also checking deals associated with Customer Company 38965107090...")

            # Get deals associated with the customer company
            company_deals_url = f"https://api.hubapi.com/crm/v4/objects/companies/38965107090/associations/deals"
            company_response = requests.get(company_deals_url, headers=headers)

            if company_response.status_code == 200:
                company_deals = company_response.json()
                deal_ids = [result['toObjectId'] for result in company_deals.get('results', [])]
                print(f"📋 Found {len(deal_ids)} deals associated with Customer Company:")
                for deal_id in deal_ids:
                    print(f"   - Deal ID: {deal_id}")

        else:
            print(f"❌ Search failed: {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    search_saknoumor_deals()