#!/usr/bin/env python3
"""
Check the final state of the GORUKA deal
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Deal, Company

def check_goruka_state():
    """Check current state of GORUKA deal"""
    
    deal_id = "40272444002"
    
    print(f"🔍 CHECKING GORUKA DEAL FINAL STATE")
    print(f"=" * 60)
    print(f"Deal ID: {deal_id}")
    
    client = get_client()
    
    # Get deal info
    deal = Deal.find_by_id(deal_id, properties=['dealname', 'lead_source', 'amount'])
    if deal:
        props = deal.get('properties', {})
        print(f"\n📊 DEAL INFO:")
        print(f"   Name: {props.get('dealname', 'Unknown')}")
        print(f"   Amount: ${props.get('amount', '0')}")
        print(f"   Lead Source: {props.get('lead_source', 'Unknown')}")
    
    # Get associations
    assocs = client.get_associations(deal_id, 'deals', 'companies')
    
    print(f"\n🏢 ASSOCIATIONS:")
    
    primary_company = None
    accountant_company = None
    customer_company = None
    
    for assoc in assocs.get('results', []):
        company_id = str(assoc['toObjectId'])
        company = Company.find_by_id(company_id, properties=['name', 'cuit'])
        
        if company:
            company_props = company.get('properties', {})
            company_name = company_props.get('name', 'Unknown')
            cuit = company_props.get('cuit', 'NOT SET')
            
            # Check labels
            is_primary = False
            is_accountant = False
            labels = []
            
            for assoc_type in assoc.get('associationTypes', []):
                label = assoc_type.get('label', '')
                if label:
                    labels.append(label)
                
                if label == 'Primary':
                    is_primary = True
                elif 'Estudio Contable' in str(label):
                    is_accountant = True
            
            # Categorize
            if is_primary:
                primary_company = company_name
            if is_accountant:
                accountant_company = company_name
            if 'GORUKA' in company_name:
                customer_company = company_name
            
            # Display
            status = []
            if is_primary:
                status.append("PRIMARY")
            if is_accountant:
                status.append("ACCOUNTANT")
            
            status_str = f" ({', '.join(status)})" if status else ""
            
            print(f"   • {company_name}{status_str}")
            print(f"     ID: {company_id}")
            print(f"     CUIT: {cuit}")
            print(f"     Labels: {labels}")
    
    print(f"\n📋 SUMMARY:")
    print(f"   Primary Company: {primary_company or 'NONE'}")
    print(f"   Accountant: {accountant_company or 'NONE'}")
    print(f"   Customer: {customer_company or 'NONE'}")
    
    print(f"\n🎯 BUSINESS LOGIC CHECK:")
    print(f"   Lead Source: Referencia Empresa Administrada")
    print(f"   Expected: Accountant should be PRIMARY")
    print(f"   Expected: Customer should be ASSOCIATED")
    
    if primary_company and 'Contador' in primary_company:
        print(f"   ✅ CORRECT: Accountant is primary")
    elif primary_company and 'GORUKA' in primary_company:
        print(f"   ❌ INCORRECT: Customer is primary (should be accountant)")
    else:
        print(f"   ⚠️  UNCLEAR: Primary is {primary_company}")
    
    if accountant_company and customer_company:
        print(f"   ✅ GOOD: Both accountant and customer are present")
    else:
        print(f"   ❌ PROBLEM: Missing companies")

def main():
    check_goruka_state()

if __name__ == "__main__":
    main()