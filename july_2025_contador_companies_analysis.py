#!/usr/bin/env python3
"""
July 2025 Companies with Contador-Related Type Analysis
Finds companies created in July 2025 with "Cuenta Contador", "Contador Robado", or other contador-related types
"""

import requests
import pandas as pd
from datetime import datetime
import os
import json
import argparse
import time

# HubSpot API Configuration
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    raise ValueError("HUBSPOT_API_KEY environment variable is required")
HUBSPOT_BASE_URL = 'https://api.hubspot.com'

# Contador-related company type values from the configuration
CONTADOR_TYPES = {
    "Cuenta Contador": "961",
    "Cuenta Contador y Reseller": "49", 
    "Contador Robado": "3298"
}

def make_hubspot_request(endpoint, search_data=None, params=None, method='POST', timeout=30):
    """Make authenticated request to HubSpot API with error handling"""
    url = f"{HUBSPOT_BASE_URL}{endpoint}"
    headers = {
        'Authorization': f'Bearer {HUBSPOT_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    for attempt in range(3):
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=search_data, timeout=timeout)
            else:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API Error (attempt {attempt + 1}): {e}")
            if hasattr(e, 'response') and e.response.status_code == 429:
                print("⏳ Rate limit hit, waiting 10 seconds...")
                time.sleep(10)
            else:
                time.sleep(2)
    return None

def fetch_july_2025_companies():
    """Fetch all companies created in July 2025"""
    all_companies = []
    after_cursor = None
    
    # Properties to fetch including the tipo_de_empresa field
    properties = [
        "name", "domain", "industry", "city", "state", "country", 
        "createdate", "id_empresa", "tipo_de_empresa"
    ]
    
    print(f"📡 Fetching companies created in July 2025...")
    
    while True:
        search_data = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "createdate", "operator": "GTE", "value": "2025-07-01T00:00:00.000Z"},
                    {"propertyName": "createdate", "operator": "LTE", "value": "2025-07-31T23:59:59.999Z"}
                ]
            }],
            "properties": properties,
            "limit": 100,
            "after": after_cursor
        }
        
        response = make_hubspot_request('/crm/v3/objects/companies/search', search_data=search_data)
        
        if not response or not response.get('results'):
            break
        
        all_companies.extend(response['results'])
        
        if response.get('paging') and response['paging'].get('next'):
            after_cursor = response['paging']['next']['after']
        else:
            break
    
    print(f"✅ Found {len(all_companies)} companies created in July 2025")
    return all_companies

def filter_contador_companies(companies):
    """Filter companies with contador-related tipo_de_empresa values"""
    contador_companies = []
    
    print(f"🔍 Filtering for contador-related company types...")
    print(f"📋 Looking for: {list(CONTADOR_TYPES.keys())}")
    
    for company in companies:
        props = company.get('properties', {})
        tipo_empresa = props.get('tipo_de_empresa', '')
        
        # Check if tipo_de_empresa matches any contador-related values
        company_type_match = None
        for type_name, type_value in CONTADOR_TYPES.items():
            if tipo_empresa == type_value:
                company_type_match = type_name
                break
        
        # Also check for any field containing "Contador" text
        company_name = props.get('name', '') or ''
        company_industry = props.get('industry', '') or ''
        contador_in_name = 'contador' in company_name.lower()
        contador_in_industry = 'contador' in company_industry.lower()
        
        if company_type_match or contador_in_name or contador_in_industry:
            company_info = {
                'company_id': company['id'],
                'name': props.get('name', 'Unknown Company'),
                'domain': props.get('domain', ''),
                'industry': props.get('industry', ''),
                'city': props.get('city', ''),
                'state': props.get('state', ''),
                'country': props.get('country', ''),
                'createdate': props.get('createdate', ''),
                'id_empresa': props.get('id_empresa', ''),
                'tipo_de_empresa': tipo_empresa,
                'tipo_empresa_match': company_type_match,
                'contador_in_name': contador_in_name,
                'contador_in_industry': contador_in_industry,
                'hubspot_url': f"https://app.hubspot.com/contacts/19877595/company/{company['id']}/"
            }
            contador_companies.append(company_info)
    
    return contador_companies

def analyze_contador_companies(contador_companies):
    """Analyze the contador companies by type and characteristics"""
    
    if not contador_companies:
        print("❌ No contador-related companies found in July 2025")
        return {}
    
    print(f"✅ Found {len(contador_companies)} contador-related companies")
    
    # Group by tipo_de_empresa
    by_type = {}
    by_name_match = []
    by_industry_match = []
    
    for company in contador_companies:
        tipo_match = company['tipo_empresa_match']
        
        if tipo_match:
            if tipo_match not in by_type:
                by_type[tipo_match] = []
            by_type[tipo_match].append(company)
        
        if company['contador_in_name']:
            by_name_match.append(company)
        
        if company['contador_in_industry']:
            by_industry_match.append(company)
    
    results = {
        'total_contador_companies': len(contador_companies),
        'by_company_type': by_type,
        'by_name_containing_contador': by_name_match,
        'by_industry_containing_contador': by_industry_match,
        'all_companies': contador_companies
    }
    
    return results

def print_analysis_results(results):
    """Print the analysis results in a formatted way"""
    
    if not results:
        return
    
    print(f"\n🏦 JULY 2025 - COMPANIES WITH CONTADOR-RELATED FIELDS")
    print("=" * 80)
    
    total = results['total_contador_companies']
    print(f"📊 Total Companies Found: {total}")
    
    # By company type
    by_type = results['by_company_type']
    if by_type:
        print(f"\n🎯 BY COMPANY TYPE (tipo_de_empresa):")
        print("-" * 50)
        for type_name, companies in by_type.items():
            type_value = CONTADOR_TYPES.get(type_name, 'Unknown')
            print(f"\n📋 **{type_name}** (Value: {type_value}) - {len(companies)} companies:")
            
            for company in companies:
                print(f"   • {company['name']}")
                print(f"     🆔 ID: {company['company_id']}")
                print(f"     🌐 Domain: {company['domain'] or 'N/A'}")
                print(f"     🏭 Industry: {company['industry'] or 'N/A'}")
                print(f"     📍 Location: {company['city']}, {company['state']}" if company['city'] else "     📍 Location: N/A")
                print(f"     📅 Created: {company['createdate']}")
                print(f"     🔗 HubSpot: {company['hubspot_url']}")
                print()
    
    # By name containing "contador"
    by_name = results['by_name_containing_contador']
    if by_name:
        print(f"\n🔤 COMPANIES WITH 'CONTADOR' IN NAME ({len(by_name)}):")
        print("-" * 50)
        for company in by_name:
            if not company['tipo_empresa_match']:  # Only show if not already shown above
                print(f"   • {company['name']}")
                print(f"     🆔 ID: {company['company_id']}")
                print(f"     🎯 Type Value: {company['tipo_de_empresa']}")
                print(f"     🔗 HubSpot: {company['hubspot_url']}")
                print()
    
    # By industry containing "contador"
    by_industry = results['by_industry_containing_contador']
    if by_industry:
        print(f"\n🏭 COMPANIES WITH 'CONTADOR' IN INDUSTRY ({len(by_industry)}):")
        print("-" * 50)
        for company in by_industry:
            if not company['tipo_empresa_match'] and not company['contador_in_name']:  # Only show if not already shown above
                print(f"   • {company['name']}")
                print(f"     🆔 ID: {company['company_id']}")
                print(f"     🏭 Industry: {company['industry']}")
                print(f"     🎯 Type Value: {company['tipo_de_empresa']}")
                print(f"     🔗 HubSpot: {company['hubspot_url']}")
                print()
    
    print(f"\n📋 SUMMARY:")
    print(f"   🎯 By Company Type: {sum(len(companies) for companies in by_type.values())} companies")
    print(f"   🔤 By Name Match: {len(by_name)} companies")  
    print(f"   🏭 By Industry Match: {len(by_industry)} companies")
    print(f"   📊 Total Unique: {total} companies")

def main():
    parser = argparse.ArgumentParser(description='July 2025 Contador Companies Analysis')
    parser.add_argument('--api-key', help='HubSpot API key. If not provided, will use HUBSPOT_API_KEY environment variable.')
    args = parser.parse_args()

    global HUBSPOT_API_KEY
    if args.api_key:
        HUBSPOT_API_KEY = args.api_key

    print(f"🏦 JULY 2025 CONTADOR COMPANIES ANALYSIS")
    print(f"📅 Period: July 1-31, 2025")
    print(f"🎯 Focus: Companies with contador-related tipo_de_empresa values")
    print(f"🔑 Using HubSpot API Key: {HUBSPOT_API_KEY[:10]}...")
    print("=" * 80)

    try:
        # Step 1: Fetch all July 2025 companies
        all_companies = fetch_july_2025_companies()
        
        if not all_companies:
            print("❌ No companies found created in July 2025.")
            return
        
        # Step 2: Filter for contador-related companies
        contador_companies = filter_contador_companies(all_companies)
        
        # Step 3: Analyze the results
        results = analyze_contador_companies(contador_companies)
        
        # Step 4: Display results
        print_analysis_results(results)
        
        # Step 5: Save results
        if results:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"tools/outputs/july_2025_contador_companies_{timestamp}.json"
            os.makedirs("tools/outputs", exist_ok=True)

            final_results = {
                'analysis_date': datetime.now().isoformat(),
                'period': 'July 1-31, 2025',
                'criteria': {
                    'company_types_searched': CONTADOR_TYPES,
                    'additional_filters': ['name contains "contador"', 'industry contains "contador"']
                },
                'summary': {
                    'total_companies_july': len(all_companies),
                    'total_contador_companies': results['total_contador_companies'],
                    'by_type_count': {k: len(v) for k, v in results['by_company_type'].items()},
                    'name_matches': len(results['by_name_containing_contador']),
                    'industry_matches': len(results['by_industry_containing_contador'])
                },
                'detailed_results': results
            }

            with open(output_file, 'w') as f:
                json.dump(final_results, f, indent=2, default=str)

            print(f"\n💾 Results saved to: {output_file}")

    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()