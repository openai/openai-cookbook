#!/usr/bin/env python3
"""
September 2025 Companies Analysis Script
Analyzes companies that became customers in September 2025 to verify:
1. Primary deal associations are correctly set
2. first_deal_closed_won_date is properly calculated
3. Company setup is complete and valid
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests

# Add the current directory to Python path
sys.path.append('/Users/virulana/openai-cookbook/tools/scripts')

def get_hubspot_client():
    """Get HubSpot client using environment variables"""
    try:
        from hubspot import HubSpot
        api_key = os.getenv('HUBSPOT_API_KEY')
        if not api_key:
            raise ValueError("HUBSPOT_API_KEY environment variable not set")
        return HubSpot(api_key=api_key)
    except ImportError:
        print("HubSpot library not available, using direct API calls")
        return None

def get_company_data_direct_api(company_id: str) -> Dict:
    """Get company data using direct API calls"""
    api_key = os.getenv('HUBSPOT_API_KEY')
    if not api_key:
        raise ValueError("HUBSPOT_API_KEY environment variable not set")
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Get company details
    company_url = f'https://api.hubapi.com/crm/v3/objects/companies/{company_id}'
    company_response = requests.get(company_url, headers=headers)
    
    if company_response.status_code != 200:
        print(f"❌ Failed to get company {company_id}: {company_response.status_code}")
        return None
    
    company_data = company_response.json()
    
    # Get deal associations
    associations_url = f'https://api.hubapi.com/crm/v4/associations/companies/deals/batch/read'
    associations_payload = {
        "inputs": [{"id": company_id}]
    }
    
    associations_response = requests.post(associations_url, headers=headers, json=associations_payload)
    
    if associations_response.status_code != 200:
        print(f"❌ Failed to get associations for company {company_id}: {associations_response.status_code}")
        return None
    
    associations_data = associations_response.json()
    
    return {
        'company': company_data,
        'associations': associations_data
    }

def analyze_company(company_id: str, company_name: str) -> Dict:
    """Analyze a single company for primary deal associations and setup"""
    print(f"\n🔍 Analyzing: {company_name} (ID: {company_id})")
    
    try:
        # Get company data
        data = get_company_data_direct_api(company_id)
        if not data:
            return {
                'company_id': company_id,
                'company_name': company_name,
                'status': 'ERROR',
                'error': 'Failed to fetch data'
            }
        
        company = data['company']
        associations = data['associations']
        
        # Extract company properties
        properties = company.get('properties', {})
        company_type = properties.get('company_type', 'Unknown')
        lifecycle_stage = properties.get('lifecyclestage', 'Unknown')
        first_deal_date = properties.get('first_deal_closed_won_date', None)
        company_churn_date = properties.get('company_churn_date', None)
        hubspot_owner_id = properties.get('hubspot_owner_id', None)
        
        # Analyze deal associations
        deal_associations = []
        primary_deals = []
        
        if 'results' in associations and len(associations['results']) > 0:
            for result in associations['results']:
                if 'to' in result:
                    for association in result['to']:
                        deal_id = association['id']
                        type_id = association['typeId']
                        
                        deal_associations.append({
                            'deal_id': deal_id,
                            'type_id': type_id,
                            'is_primary': type_id == 5
                        })
                        
                        if type_id == 5:  # PRIMARY association
                            primary_deals.append(deal_id)
        
        # Get deal details for primary deals
        primary_deal_details = []
        if primary_deals:
            deal_url = 'https://api.hubapi.com/crm/v3/objects/deals/batch/read'
            deal_payload = {
                "inputs": [{"id": deal_id} for deal_id in primary_deals],
                "properties": ["dealname", "dealstage", "closedate", "amount", "hubspot_owner_id"]
            }
            
            deal_response = requests.post(deal_url, headers={
                'Authorization': f'Bearer {os.getenv("HUBSPOT_API_KEY")}',
                'Content-Type': 'application/json'
            }, json=deal_payload)
            
            if deal_response.status_code == 200:
                deal_data = deal_response.json()
                for deal in deal_data.get('results', []):
                    deal_props = deal.get('properties', {})
                    primary_deal_details.append({
                        'deal_id': deal['id'],
                        'name': deal_props.get('dealname', 'Unknown'),
                        'stage': deal_props.get('dealstage', 'Unknown'),
                        'close_date': deal_props.get('closedate', None),
                        'amount': deal_props.get('amount', None),
                        'owner_id': deal_props.get('hubspot_owner_id', None)
                    })
        
        # Determine status
        total_deals = len(deal_associations)
        primary_count = len(primary_deals)
        
        if total_deals == 0:
            status = 'NO_DEALS'
            issue = 'Company has no deals'
        elif primary_count == 0:
            status = 'NO_PRIMARY_DEALS'
            issue = f'Company has {total_deals} deals but no PRIMARY associations'
        elif primary_count > 0:
            status = 'HAS_PRIMARY_DEALS'
            issue = None
        else:
            status = 'UNKNOWN'
            issue = 'Unknown status'
        
        # Check if first_deal_date is set
        has_first_deal_date = first_deal_date is not None and first_deal_date != ''
        
        # Determine if setup is correct
        setup_correct = (
            primary_count > 0 and  # Has primary deals
            has_first_deal_date and  # Has first deal date
            lifecycle_stage in ['customer', 'subscriber']  # Is a customer
        )
        
        return {
            'company_id': company_id,
            'company_name': company_name,
            'status': status,
            'issue': issue,
            'setup_correct': setup_correct,
            'company_type': company_type,
            'lifecycle_stage': lifecycle_stage,
            'first_deal_date': first_deal_date,
            'company_churn_date': company_churn_date,
            'hubspot_owner_id': hubspot_owner_id,
            'total_deals': total_deals,
            'primary_deals_count': primary_count,
            'primary_deal_details': primary_deal_details,
            'deal_associations': deal_associations
        }
        
    except Exception as e:
        print(f"❌ Error analyzing company {company_id}: {str(e)}")
        return {
            'company_id': company_id,
            'company_name': company_name,
            'status': 'ERROR',
            'error': str(e)
        }

def main():
    """Main analysis function"""
    print("🚀 Starting September 2025 Companies Analysis")
    print("=" * 60)
    
    # September 2025 companies list
    companies = [
        ("38959866278", "96589 - Pablo Daniel Tocco"),
        ("38964969041", "96600 - L4BSEGURIDAD SAS"),
        ("39080806318", "96622 - Yupana"),
        ("38668102498", "96417 - CYNTIA ELISABETH OLIVERA"),
        ("39096699058", "96642 - SISTRAN CONSULTORES S A"),
        ("38790803550", "96475 - MUNDO ACERO"),
        ("39131459987", "96698 - ALRAMA S.A."),
        ("39211792554", "96744 - MAB Beauty Center"),
        ("39177700991", "96740 - ALEJANDRO HORACIO MONIS"),
        ("39181653357", "96717 - Tienda Babilonia"),
        ("39034519884", "96606 - TIQUES S.R.L."),
        ("31285203237", "90886 - NEXTVISION SRL"),
        ("33764351415", "Crya"),
        ("39367958165", "96852 - VOY LIDERANDO"),
        ("39300054530", "96831 - Estudio Contable Luis Folgar"),
        ("39365634699", "96848 - GRUPO ZUCO S.A."),
        ("39368265539", "96845 - CASA ZUCO S.A"),
        ("39363224369", "96866 - Fideicomiso las Bardas"),
        ("39353846611", "96874 - Parking del Centro SA"),
        ("39356052798", "96881 - HOTEL FROSSARD S.R.L."),
        ("39489226592", "96945 - LOS VINAGRES DE OMEGA S.R.L."),
        ("39501007019", "96955 - PERIFERICOS MULTIFUNCION S.R.L."),
        ("39501453105", "96944 - SOMOS PURA S.R.L."),
        ("37548237320", "TRR SAS"),
        ("39592694568", "97036 - GP CARGO")
    ]
    
    results = []
    correct_setups = 0
    issues_found = 0
    
    for company_id, company_name in companies:
        result = analyze_company(company_id, company_name)
        results.append(result)
        
        if result['status'] == 'HAS_PRIMARY_DEALS' and result['setup_correct']:
            correct_setups += 1
            print(f"✅ {company_name}: Correctly configured")
        else:
            issues_found += 1
            print(f"⚠️ {company_name}: {result.get('issue', 'Issue found')}")
    
    # Generate summary
    print("\n" + "=" * 60)
    print("📊 ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Total companies analyzed: {len(companies)}")
    print(f"Correctly configured: {correct_setups}")
    print(f"Issues found: {issues_found}")
    print(f"Success rate: {(correct_setups/len(companies)*100):.1f}%")
    
    # Detailed issues breakdown
    print("\n🔍 DETAILED ISSUES BREAKDOWN:")
    print("-" * 40)
    
    no_primary_deals = [r for r in results if r['status'] == 'NO_PRIMARY_DEALS']
    no_deals = [r for r in results if r['status'] == 'NO_DEALS']
    errors = [r for r in results if r['status'] == 'ERROR']
    
    if no_primary_deals:
        print(f"\n❌ NO PRIMARY DEALS ({len(no_primary_deals)} companies):")
        for result in no_primary_deals:
            print(f"  • {result['company_name']}: {result['issue']}")
    
    if no_deals:
        print(f"\n⚠️ NO DEALS ({len(no_deals)} companies):")
        for result in no_deals:
            print(f"  • {result['company_name']}: {result['issue']}")
    
    if errors:
        print(f"\n🚨 ERRORS ({len(errors)} companies):")
        for result in errors:
            print(f"  • {result['company_name']}: {result.get('error', 'Unknown error')}")
    
    # Accountant companies analysis
    accountant_companies = [r for r in results if 'contable' in r['company_name'].lower() or 'estudio' in r['company_name'].lower()]
    if accountant_companies:
        print(f"\n👔 ACCOUNTANT COMPANIES ({len(accountant_companies)} companies):")
        for result in accountant_companies:
            status_emoji = "✅" if result['setup_correct'] else "⚠️"
            print(f"  {status_emoji} {result['company_name']}: {result['status']}")
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"september_2025_companies_analysis_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump({
            'analysis_date': datetime.now().isoformat(),
            'total_companies': len(companies),
            'correct_setups': correct_setups,
            'issues_found': issues_found,
            'success_rate': correct_setups/len(companies)*100,
            'results': results
        }, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to: {filename}")
    
    return results

if __name__ == "__main__":
    main()



