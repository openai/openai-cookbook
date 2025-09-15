#!/usr/bin/env python3
"""
September 2025 Requalification Process Verification
====================================================

Verifies if the channel sales team is properly going through accountant companies
(tipo "Cuenta Contador") and creating leads for them during September 2025.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any

def analyze_requalification_process():
    """Analyze the requalification process for September 2025"""
    
    print("🔍 SEPTEMBER 2025 REQUALIFICATION PROCESS VERIFICATION")
    print("=" * 60)
    
    # Load the exact companies data
    companies_file = "hubspot_companies_20250901_20250930_20250908_212217.json"
    
    if not os.path.exists(companies_file):
        print(f"❌ Companies file not found: {companies_file}")
        return
    
    with open(companies_file, 'r') as f:
        companies_data = json.load(f)
    
    print(f"📊 Total Companies Analyzed: {len(companies_data)}")
    
    # Analyze company types
    company_types = {}
    accountant_companies = []
    lead_companies = []
    
    for company in companies_data:
        company_type = company['properties'].get('type')
        lifecycle_stage = company['properties'].get('lifecyclestage')
        company_name = company['properties'].get('name', 'Unknown')
        created_date = company['properties'].get('createdate')
        
        # Count company types
        if company_type:
            company_types[company_type] = company_types.get(company_type, 0) + 1
        else:
            company_types['None'] = company_types.get('None', 0) + 1
        
        # Identify accountant companies
        if company_type in ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']:
            accountant_companies.append({
                'id': company['id'],
                'name': company_name,
                'type': company_type,
                'lifecycle_stage': lifecycle_stage,
                'created_date': created_date,
                'has_deals': company['properties'].get('num_associated_deals', 0) or 0
            })
        
        # Count lead companies
        if lifecycle_stage == 'lead':
            lead_companies.append({
                'id': company['id'],
                'name': company_name,
                'type': company_type,
                'created_date': created_date
            })
    
    print(f"\n📈 COMPANY TYPES DISTRIBUTION:")
    print("-" * 40)
    for company_type, count in sorted(company_types.items(), key=lambda x: x[1], reverse=True):
        print(f"   {company_type}: {count}")
    
    print(f"\n🎯 ACCOUNTANT COMPANIES ANALYSIS:")
    print("-" * 40)
    print(f"   Total Accountant Companies: {len(accountant_companies)}")
    
    if accountant_companies:
        print(f"\n📋 ACCOUNTANT COMPANIES DETAILS:")
        for i, company in enumerate(accountant_companies, 1):
            print(f"   {i}. {company['name']} ({company['type']})")
            print(f"      - Lifecycle: {company['lifecycle_stage']}")
            print(f"      - Created: {company['created_date']}")
            print(f"      - Associated Deals: {company['has_deals']}")
            print()
    
    print(f"\n📞 LEAD COMPANIES ANALYSIS:")
    print("-" * 40)
    print(f"   Total Lead Companies: {len(lead_companies)}")
    
    # Check if accountant companies are in lead stage
    accountant_leads = [c for c in accountant_companies if c['lifecycle_stage'] == 'lead']
    print(f"   Accountant Companies as Leads: {len(accountant_leads)}")
    
    if accountant_leads:
        print(f"\n✅ REQUALIFICATION PROCESS VERIFICATION:")
        print("-" * 40)
        print(f"   ✅ {len(accountant_leads)} accountant companies are in 'lead' stage")
        print(f"   ✅ This indicates the requalification process is working")
        
        print(f"\n📋 ACCOUNTANT LEADS CREATED:")
        for i, company in enumerate(accountant_leads, 1):
            print(f"   {i}. {company['name']} ({company['type']})")
            print(f"      - Created: {company['created_date']}")
            print(f"      - Associated Deals: {company['has_deals']}")
            print()
    else:
        print(f"\n❌ REQUALIFICATION PROCESS ISSUE:")
        print("-" * 40)
        print(f"   ❌ No accountant companies found in 'lead' stage")
        print(f"   ❌ This may indicate the requalification process is not working")
    
    # Summary
    print(f"\n📊 REQUALIFICATION PROCESS SUMMARY:")
    print("=" * 60)
    print(f"   📅 Period: September 1-30, 2025")
    print(f"   🏢 Total Companies: {len(companies_data)}")
    print(f"   🎯 Accountant Companies: {len(accountant_companies)}")
    print(f"   📞 Total Leads: {len(lead_companies)}")
    print(f"   ✅ Accountant Leads: {len(accountant_leads)}")
    
    if len(accountant_leads) > 0:
        print(f"   🎉 REQUALIFICATION PROCESS: WORKING")
        print(f"   📈 Success Rate: {len(accountant_leads)/len(accountant_companies)*100:.1f}%")
    else:
        print(f"   ⚠️  REQUALIFICATION PROCESS: NEEDS ATTENTION")
        print(f"   📉 Success Rate: 0%")

if __name__ == "__main__":
    analyze_requalification_process()
