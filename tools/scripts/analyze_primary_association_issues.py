#!/usr/bin/env python3
"""
Analyze deals created in September 2025 to identify missing PRIMARY company associations.
This script checks for the data quality issue where deals have companies associated
but none are marked as PRIMARY, affecting revenue attribution.
"""

import requests
import json
from datetime import datetime
import time

# HubSpot API configuration
HUBSPOT_ACCESS_TOKEN = "YOUR_HUBSPOT_ACCESS_TOKEN_HERE"  # Replace with actual token
BASE_URL = "https://api.hubapi.com"

def get_deal_associations(deal_id):
    """Get all company associations for a deal"""
    url = f"{BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/companies"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting associations for deal {deal_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception getting associations for deal {deal_id}: {e}")
        return None

def get_company_details(company_id):
    """Get company details including name and type"""
    url = f"{BASE_URL}/crm/v3/objects/companies/{company_id}"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    params = {
        "properties": "name,type,lifecyclestage"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting company {company_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception getting company {company_id}: {e}")
        return None

def analyze_deal_associations(deal_id, deal_name, deal_stage, deal_amount):
    """Analyze a single deal's company associations"""
    associations = get_deal_associations(deal_id)
    if not associations:
        return None
    
    companies = []
    has_primary = False
    accountant_companies = []
    client_companies = []
    
    for result in associations.get('results', []):
        company_id = result['toObjectId']
        association_types = result.get('associationTypes', [])
        
        # Check if this company has PRIMARY association
        is_primary = any(at['typeId'] == 5 for at in association_types)
        if is_primary:
            has_primary = True
        
        # Get company details
        company_details = get_company_details(company_id)
        if company_details:
            company_name = company_details['properties'].get('name', 'Unknown')
            company_type = company_details['properties'].get('type', 'Unknown')
            lifecycle_stage = company_details['properties'].get('lifecyclestage', 'Unknown')
            
            company_info = {
                'id': company_id,
                'name': company_name,
                'type': company_type,
                'lifecycle_stage': lifecycle_stage,
                'is_primary': is_primary,
                'association_types': [at['typeId'] for at in association_types]
            }
            
            companies.append(company_info)
            
            # Categorize companies
            if company_type in ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']:
                accountant_companies.append(company_info)
            else:
                client_companies.append(company_info)
        
        time.sleep(0.1)  # Rate limiting
    
    return {
        'deal_id': deal_id,
        'deal_name': deal_name,
        'deal_stage': deal_stage,
        'deal_amount': deal_amount,
        'has_primary': has_primary,
        'companies': companies,
        'accountant_companies': accountant_companies,
        'client_companies': client_companies,
        'total_companies': len(companies)
    }

def main():
    """Main analysis function"""
    print("🔍 Analyzing PRIMARY association issues for September 2025 deals...")
    print("=" * 80)
    
    # Sample deals from September 2025 (first 20 for analysis)
    september_deals = [
        ("43239499286", "96581 - FCP SA", "closedlost", "130000"),
        ("43157560911", "7927 DATA FACTORY S.R.L.", "closedwon", "214500"),
        ("43239957577", "96589 - Estormin Comunicacion", "closedwon", "134500"),
        ("43175682054", "95742 - MAQUEN  -", "closedwon", "214500"),
        ("43235450705", "96076 - SEBASTIAN ALEJANDRO MONTERO ECHAGUE", "closedlost", "130000"),
        ("43235451308", "72931 - DIEGO LUIS GIRON", "presentationscheduled", "130000"),
        ("43214707883", "96600 - L4BSEGURIDAD SAS", "closedwon", "91500"),
        ("43235453018", "96417 - CYNTIA ELISABETH OLIVERA", "closedwon", "220900"),
        ("43157967193", "grupo unimet", "qualifiedtobuy", "130000"),
        ("43253531726", "96610 - I.MET S.R.L.", "decisionmakerboughtin", "185900"),
        ("43281146636", "96622 - Yupana", "closedwon", "220900"),
        ("43282630429", "Fluotech", "qualifiedtobuy", "130000"),
        ("43289280313", "96608 - CONTADORA MARCELA ELIZABETH ROLANDO", "qualifiedtobuy", "130000"),
        ("43289343489", "Uzcudun Motorstore", "qualifiedtobuy", "130000"),
        ("43288787853", "96572 - SAKNOUMOR S. A. S.", "qualifiedtobuy", "130000"),
        ("43289469773", "96642 - SISTRAN CONSULTORES S A", "closedwon", "160153"),
        ("43319732353", "THINKION", "presentationscheduled", "130000"),
        ("43331373110", "95968 - AP DESARROLLOS SRL", "qualifiedtobuy", "130000"),
        ("43369101837", "96606 - TIQUES S.R.L.", "closedwon", "185900"),
        ("43347730503", "96698 - ALRAMA S.A.", "closedwon", "134500")
    ]
    
    issues_found = []
    total_analyzed = 0
    
    for deal_id, deal_name, deal_stage, deal_amount in september_deals:
        print(f"\n📊 Analyzing Deal: {deal_name}")
        print(f"   ID: {deal_id} | Stage: {deal_stage} | Amount: ${deal_amount}")
        
        analysis = analyze_deal_associations(deal_id, deal_name, deal_stage, deal_amount)
        total_analyzed += 1
        
        if analysis:
            if not analysis['has_primary']:
                print(f"   🚨 ISSUE: No PRIMARY company association found!")
                issues_found.append(analysis)
                
                # Show company details
                for company in analysis['companies']:
                    primary_status = "✅ PRIMARY" if company['is_primary'] else "❌ NOT PRIMARY"
                    print(f"   📋 Company: {company['name']} ({primary_status})")
                    print(f"      Type: {company['type']} | Stage: {company['lifecycle_stage']}")
                    print(f"      Association Types: {company['association_types']}")
            else:
                print(f"   ✅ OK: Has PRIMARY company association")
        
        time.sleep(0.2)  # Rate limiting
    
    # Summary report
    print("\n" + "=" * 80)
    print("📋 SUMMARY REPORT")
    print("=" * 80)
    print(f"Total deals analyzed: {total_analyzed}")
    print(f"Issues found: {len(issues_found)}")
    
    if issues_found:
        print(f"\n🚨 DEALS WITH MISSING PRIMARY ASSOCIATIONS:")
        print("-" * 60)
        
        for issue in issues_found:
            print(f"\n📊 Deal: {issue['deal_name']}")
            print(f"   ID: {issue['deal_id']} | Stage: {issue['deal_stage']} | Amount: ${issue['deal_amount']}")
            print(f"   Companies: {issue['total_companies']}")
            
            # Categorize the issue
            if issue['accountant_companies'] and issue['client_companies']:
                print(f"   🔍 ISSUE TYPE: Accountant + Client (Missing PRIMARY on client)")
                for client in issue['client_companies']:
                    print(f"      Client: {client['name']} (should be PRIMARY)")
                for accountant in issue['accountant_companies']:
                    print(f"      Accountant: {accountant['name']} (referring partner)")
            elif issue['accountant_companies']:
                print(f"   🔍 ISSUE TYPE: Accountant only (may be normal)")
            else:
                print(f"   🔍 ISSUE TYPE: Client companies only (missing PRIMARY)")
    
    print(f"\n💡 RECOMMENDATION:")
    print(f"   - Review the {len(issues_found)} deals with missing PRIMARY associations")
    print(f"   - For accountant + client deals: Set client company as PRIMARY")
    print(f"   - For accountant-only deals: Verify if this is normal referral pattern")
    print(f"   - Consider implementing automated PRIMARY association rules")

if __name__ == "__main__":
    main()
