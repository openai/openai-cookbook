#!/usr/bin/env python3
"""
September 2025 Complete Requalification Process Analysis
========================================================

Complete analysis of the requalification process using exact data from RESTful API
with complete pagination to verify if channel sales team is properly creating leads
for accountant companies (tipo "Cuenta Contador").
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any

def complete_requalification_analysis():
    """Complete analysis of the requalification process"""
    
    print("🔍 SEPTEMBER 2025 COMPLETE REQUALIFICATION ANALYSIS")
    print("=" * 65)
    
    # Load the exact data
    companies_file = "hubspot_companies_20250901_20250930_20250908_212217.json"
    contacts_file = "hubspot_contacts_20250901_20250930_20250908_211937.json"
    
    if not os.path.exists(companies_file):
        print(f"❌ Companies file not found: {companies_file}")
        return
    
    if not os.path.exists(contacts_file):
        print(f"❌ Contacts file not found: {contacts_file}")
        return
    
    with open(companies_file, 'r') as f:
        companies_data = json.load(f)
    
    with open(contacts_file, 'r') as f:
        contacts_data = json.load(f)
    
    print(f"📊 DATASET OVERVIEW:")
    print(f"   🏢 Companies: {len(companies_data)}")
    print(f"   📞 Contacts: {len(contacts_data)}")
    
    # Analyze company types and accountant companies
    company_types = {}
    accountant_companies = []
    lead_companies = []
    
    for company in companies_data:
        company_type = company['properties'].get('type')
        lifecycle_stage = company['properties'].get('lifecyclestage')
        company_name = company['properties'].get('name', 'Unknown')
        created_date = company['properties'].get('createdate')
        num_deals_str = company['properties'].get('num_associated_deals', '0')
        num_deals = int(num_deals_str) if num_deals_str and num_deals_str != 'null' else 0
        
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
                'num_deals': num_deals
            })
        
        # Count lead companies
        if lifecycle_stage == 'lead':
            lead_companies.append({
                'id': company['id'],
                'name': company_name,
                'type': company_type,
                'created_date': created_date
            })
    
    # Analyze contacts for accountant identification
    accountant_contacts = []
    utm_conta_contacts = []
    
    for contact in contacts_data:
        es_contador = contact['properties'].get('es_contador')
        utm_campaign = contact['properties'].get('utm_campaign', '')
        contact_name = f"{contact['properties'].get('firstname', '')} {contact['properties'].get('lastname', '')}".strip()
        email = contact['properties'].get('email', '')
        lifecycle_stage = contact['properties'].get('lifecyclestage')
        created_date = contact['properties'].get('createdate')
        
        # Direct accountant flag
        if es_contador == 'true':
            accountant_contacts.append({
                'id': contact['id'],
                'name': contact_name,
                'email': email,
                'lifecycle_stage': lifecycle_stage,
                'created_date': created_date,
                'identification_method': 'es_contador flag'
            })
        
        # UTM campaign with 'conta'
        if utm_campaign and 'conta' in utm_campaign.lower():
            utm_conta_contacts.append({
                'id': contact['id'],
                'name': contact_name,
                'email': email,
                'utm_campaign': utm_campaign,
                'lifecycle_stage': lifecycle_stage,
                'created_date': created_date,
                'identification_method': 'UTM campaign conta'
            })
    
    # Results
    print(f"\n📈 COMPANY TYPES DISTRIBUTION:")
    print("-" * 45)
    for company_type, count in sorted(company_types.items(), key=lambda x: x[1], reverse=True):
        print(f"   {company_type}: {count}")
    
    print(f"\n🎯 ACCOUNTANT COMPANIES ANALYSIS:")
    print("-" * 45)
    print(f"   Total Accountant Companies: {len(accountant_companies)}")
    
    if accountant_companies:
        print(f"\n📋 ACCOUNTANT COMPANIES DETAILS:")
        for i, company in enumerate(accountant_companies, 1):
            print(f"   {i}. {company['name']} ({company['type']})")
            print(f"      - Lifecycle: {company['lifecycle_stage']}")
            print(f"      - Created: {company['created_date']}")
            print(f"      - Associated Deals: {company['num_deals']}")
            print()
    
    print(f"\n📞 CONTACT ANALYSIS:")
    print("-" * 45)
    print(f"   Direct es_contador flag: {len(accountant_contacts)}")
    print(f"   UTM campaign 'conta': {len(utm_conta_contacts)}")
    
    if utm_conta_contacts:
        print(f"\n📋 UTM 'CONTA' CONTACTS:")
        for i, contact in enumerate(utm_conta_contacts, 1):
            print(f"   {i}. {contact['name']} ({contact['email']})")
            print(f"      - UTM Campaign: {contact['utm_campaign']}")
            print(f"      - Lifecycle: {contact['lifecycle_stage']}")
            print(f"      - Created: {contact['created_date']}")
            print()
    
    # Requalification Process Analysis
    print(f"\n🔄 REQUALIFICATION PROCESS ANALYSIS:")
    print("=" * 65)
    
    # Check if accountant companies are in lead stage
    accountant_leads = [c for c in accountant_companies if c['lifecycle_stage'] == 'lead']
    
    print(f"   📊 Total Companies: {len(companies_data)}")
    print(f"   🎯 Accountant Companies: {len(accountant_companies)}")
    print(f"   📞 Total Lead Companies: {len(lead_companies)}")
    print(f"   ✅ Accountant Lead Companies: {len(accountant_leads)}")
    
    if len(accountant_leads) > 0:
        print(f"\n✅ REQUALIFICATION PROCESS STATUS: WORKING")
        print(f"   📈 Success Rate: {len(accountant_leads)/len(accountant_companies)*100:.1f}%")
        print(f"   🎉 Channel sales team is creating leads for accountant companies")
        
        print(f"\n📋 ACCOUNTANT LEADS CREATED:")
        for i, company in enumerate(accountant_leads, 1):
            print(f"   {i}. {company['name']} ({company['type']})")
            print(f"      - Created: {company['created_date']}")
            print(f"      - Associated Deals: {company['num_deals']}")
            print()
    else:
        print(f"\n❌ REQUALIFICATION PROCESS STATUS: NEEDS ATTENTION")
        print(f"   📉 Success Rate: 0%")
        print(f"   ⚠️  No accountant companies found in 'lead' stage")
        print(f"   🔍 This may indicate:")
        print(f"      - Channel sales team is not creating leads for accountant companies")
        print(f"      - Accountant companies are being processed differently")
        print(f"      - Requalification process needs review")
    
    # Additional Insights
    print(f"\n💡 ADDITIONAL INSIGHTS:")
    print("-" * 45)
    
    # Check if accountant companies have deals
    accountant_with_deals = [c for c in accountant_companies if c['num_deals'] > 0]
    print(f"   🎯 Accountant companies with deals: {len(accountant_with_deals)}")
    
    if accountant_with_deals:
        print(f"   ✅ Accountant companies are generating deals")
        for company in accountant_with_deals:
            print(f"      - {company['name']}: {company['num_deals']} deals")
    else:
        print(f"   ⚠️  No deals associated with accountant companies")
    
    # Check lifecycle progression
    lifecycle_distribution = {}
    for company in accountant_companies:
        stage = company['lifecycle_stage'] or 'None'
        lifecycle_distribution[stage] = lifecycle_distribution.get(stage, 0) + 1
    
    print(f"\n📊 ACCOUNTANT COMPANIES LIFECYCLE DISTRIBUTION:")
    for stage, count in lifecycle_distribution.items():
        print(f"   {stage}: {count}")
    
    # Final Summary
    print(f"\n📋 FINAL SUMMARY:")
    print("=" * 65)
    print(f"   📅 Analysis Period: September 1-30, 2025")
    print(f"   🏢 Total Companies: {len(companies_data)}")
    print(f"   📞 Total Contacts: {len(contacts_data)}")
    print(f"   🎯 Accountant Companies: {len(accountant_companies)}")
    print(f"   📞 Total Leads: {len(lead_companies)}")
    print(f"   ✅ Accountant Leads: {len(accountant_leads)}")
    print(f"   🎯 UTM 'conta' Contacts: {len(utm_conta_contacts)}")
    
    if len(accountant_leads) > 0:
        print(f"   🎉 REQUALIFICATION PROCESS: WORKING")
    else:
        print(f"   ⚠️  REQUALIFICATION PROCESS: NEEDS ATTENTION")

if __name__ == "__main__":
    complete_requalification_analysis()
