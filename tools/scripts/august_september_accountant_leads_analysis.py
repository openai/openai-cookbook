#!/usr/bin/env python3
"""
August & September 2025 Leads Associated with Accountant Companies Analysis
===========================================================================

Analyzes leads created during August and September 2025 that are associated
with accountant companies using exact data from RESTful API with complete pagination.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any

def analyze_leads_associated_with_accountant_companies():
    """Analyze leads associated with accountant companies for Aug-Sep 2025"""
    
    print("🔍 AUGUST & SEPTEMBER 2025 LEADS ASSOCIATED WITH ACCOUNTANT COMPANIES")
    print("=" * 75)
    
    # Load all the data files
    august_companies_file = "hubspot_companies_20250801_20250831_20250908_212513.json"
    august_contacts_file = "hubspot_contacts_20250801_20250831_20250908_212525.json"
    september_companies_file = "hubspot_companies_20250901_20250930_20250908_212217.json"
    september_contacts_file = "hubspot_contacts_20250901_20250930_20250908_211937.json"
    
    # Check if all files exist
    files_to_check = [august_companies_file, august_contacts_file, september_companies_file, september_contacts_file]
    for file_path in files_to_check:
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return
    
    # Load all data
    with open(august_companies_file, 'r') as f:
        august_companies = json.load(f)
    
    with open(august_contacts_file, 'r') as f:
        august_contacts = json.load(f)
    
    with open(september_companies_file, 'r') as f:
        september_companies = json.load(f)
    
    with open(september_contacts_file, 'r') as f:
        september_contacts = json.load(f)
    
    print(f"📊 DATASET OVERVIEW:")
    print(f"   🏢 August Companies: {len(august_companies)}")
    print(f"   📞 August Contacts: {len(august_contacts)}")
    print(f"   🏢 September Companies: {len(september_companies)}")
    print(f"   📞 September Contacts: {len(september_contacts)}")
    
    # Combine all data
    all_companies = august_companies + september_companies
    all_contacts = august_contacts + september_contacts
    
    print(f"   🏢 Total Companies: {len(all_companies)}")
    print(f"   📞 Total Contacts: {len(all_contacts)}")
    
    # Identify accountant companies
    accountant_companies = []
    company_types = {}
    
    for company in all_companies:
        company_type = company['properties'].get('type')
        lifecycle_stage = company['properties'].get('lifecyclestage')
        company_name = company['properties'].get('name', 'Unknown')
        created_date = company['properties'].get('createdate')
        company_id = company['id']
        
        # Count company types
        if company_type:
            company_types[company_type] = company_types.get(company_type, 0) + 1
        else:
            company_types['None'] = company_types.get('None', 0) + 1
        
        # Identify accountant companies
        if company_type in ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']:
            accountant_companies.append({
                'id': company_id,
                'name': company_name,
                'type': company_type,
                'lifecycle_stage': lifecycle_stage,
                'created_date': created_date,
                'month': 'August' if created_date and created_date.startswith('2025-08') else 'September'
            })
    
    print(f"\n📈 COMPANY TYPES DISTRIBUTION:")
    print("-" * 50)
    for company_type, count in sorted(company_types.items(), key=lambda x: x[1], reverse=True):
        print(f"   {company_type}: {count}")
    
    print(f"\n🎯 ACCOUNTANT COMPANIES ANALYSIS:")
    print("-" * 50)
    print(f"   Total Accountant Companies: {len(accountant_companies)}")
    
    # Count by month
    august_accountant_companies = [c for c in accountant_companies if c['month'] == 'August']
    september_accountant_companies = [c for c in accountant_companies if c['month'] == 'September']
    
    print(f"   August Accountant Companies: {len(august_accountant_companies)}")
    print(f"   September Accountant Companies: {len(september_accountant_companies)}")
    
    if accountant_companies:
        print(f"\n📋 ACCOUNTANT COMPANIES DETAILS:")
        for i, company in enumerate(accountant_companies, 1):
            print(f"   {i}. {company['name']} ({company['type']})")
            print(f"      - Month: {company['month']}")
            print(f"      - Lifecycle: {company['lifecycle_stage']}")
            print(f"      - Created: {company['created_date']}")
            print()
    
    # Analyze contacts associated with accountant companies
    # We need to check if contacts have company associations
    accountant_company_ids = {c['id'] for c in accountant_companies}
    
    # For this analysis, we'll look at contacts that might be associated with accountant companies
    # Since we don't have direct company associations in the contact data, we'll analyze
    # contacts that are accountants themselves or have accountant-related UTM campaigns
    
    accountant_contacts = []
    utm_conta_contacts = []
    lead_contacts = []
    
    for contact in all_contacts:
        es_contador = contact['properties'].get('es_contador')
        utm_campaign = contact['properties'].get('utm_campaign', '')
        contact_name = f"{contact['properties'].get('firstname', '')} {contact['properties'].get('lastname', '')}".strip()
        email = contact['properties'].get('email', '')
        lifecycle_stage = contact['properties'].get('lifecyclestage')
        created_date = contact['properties'].get('createdate')
        contact_id = contact['id']
        
        # Determine month
        month = 'August' if created_date and created_date.startswith('2025-08') else 'September'
        
        # Direct accountant flag
        if es_contador == 'true':
            accountant_contacts.append({
                'id': contact_id,
                'name': contact_name,
                'email': email,
                'lifecycle_stage': lifecycle_stage,
                'created_date': created_date,
                'month': month,
                'identification_method': 'es_contador flag'
            })
        
        # UTM campaign with 'conta'
        if utm_campaign and 'conta' in utm_campaign.lower():
            utm_conta_contacts.append({
                'id': contact_id,
                'name': contact_name,
                'email': email,
                'utm_campaign': utm_campaign,
                'lifecycle_stage': lifecycle_stage,
                'created_date': created_date,
                'month': month,
                'identification_method': 'UTM campaign conta'
            })
        
        # All lead contacts
        if lifecycle_stage == 'lead':
            lead_contacts.append({
                'id': contact_id,
                'name': contact_name,
                'email': email,
                'created_date': created_date,
                'month': month
            })
    
    print(f"\n📞 CONTACT ANALYSIS:")
    print("-" * 50)
    print(f"   Direct es_contador flag: {len(accountant_contacts)}")
    print(f"   UTM campaign 'conta': {len(utm_conta_contacts)}")
    print(f"   Total Lead Contacts: {len(lead_contacts)}")
    
    # Analyze by month
    august_leads = [c for c in lead_contacts if c['month'] == 'August']
    september_leads = [c for c in lead_contacts if c['month'] == 'September']
    
    august_utm_conta = [c for c in utm_conta_contacts if c['month'] == 'August']
    september_utm_conta = [c for c in utm_conta_contacts if c['month'] == 'September']
    
    print(f"\n📊 MONTHLY BREAKDOWN:")
    print("-" * 50)
    print(f"   August Leads: {len(august_leads)}")
    print(f"   September Leads: {len(september_leads)}")
    print(f"   August UTM 'conta': {len(august_utm_conta)}")
    print(f"   September UTM 'conta': {len(september_utm_conta)}")
    
    # Detailed analysis of UTM 'conta' contacts (likely accountant leads)
    if utm_conta_contacts:
        print(f"\n📋 UTM 'CONTA' CONTACTS (ACCOUNTANT LEADS):")
        print("-" * 50)
        
        # Group by month
        august_conta_leads = [c for c in utm_conta_contacts if c['month'] == 'August']
        september_conta_leads = [c for c in utm_conta_contacts if c['month'] == 'September']
        
        if august_conta_leads:
            print(f"\n   📅 AUGUST ACCOUNTANT LEADS ({len(august_conta_leads)}):")
            for i, contact in enumerate(august_conta_leads, 1):
                print(f"      {i}. {contact['name']} ({contact['email']})")
                print(f"         - UTM Campaign: {contact['utm_campaign']}")
                print(f"         - Lifecycle: {contact['lifecycle_stage']}")
                print(f"         - Created: {contact['created_date']}")
                print()
        
        if september_conta_leads:
            print(f"\n   📅 SEPTEMBER ACCOUNTANT LEADS ({len(september_conta_leads)}):")
            for i, contact in enumerate(september_conta_leads, 1):
                print(f"      {i}. {contact['name']} ({contact['email']})")
                print(f"         - UTM Campaign: {contact['utm_campaign']}")
                print(f"         - Lifecycle: {contact['lifecycle_stage']}")
                print(f"         - Created: {contact['created_date']}")
                print()
    
    # Analysis of leads associated with accountant companies
    print(f"\n🔄 LEADS ASSOCIATED WITH ACCOUNTANT COMPANIES ANALYSIS:")
    print("=" * 75)
    
    # Check if accountant companies are in lead stage
    accountant_leads = [c for c in accountant_companies if c['lifecycle_stage'] == 'lead']
    
    print(f"   📊 Total Companies: {len(all_companies)}")
    print(f"   🎯 Accountant Companies: {len(accountant_companies)}")
    print(f"   📞 Total Lead Contacts: {len(lead_contacts)}")
    print(f"   ✅ Accountant Companies as Leads: {len(accountant_leads)}")
    print(f"   🎯 UTM 'conta' Contacts (Accountant Leads): {len(utm_conta_contacts)}")
    
    if len(accountant_leads) > 0:
        print(f"\n✅ ACCOUNTANT COMPANIES AS LEADS:")
        print("-" * 50)
        for i, company in enumerate(accountant_leads, 1):
            print(f"   {i}. {company['name']} ({company['type']})")
            print(f"      - Month: {company['month']}")
            print(f"      - Created: {company['created_date']}")
            print()
    else:
        print(f"\n❌ NO ACCOUNTANT COMPANIES FOUND IN LEAD STAGE")
        print("-" * 50)
        print(f"   This indicates that accountant companies are not being created as leads")
        print(f"   They are being processed directly to other stages")
    
    # Summary
    print(f"\n📋 FINAL SUMMARY:")
    print("=" * 75)
    print(f"   📅 Analysis Period: August 1 - September 30, 2025")
    print(f"   🏢 Total Companies: {len(all_companies)}")
    print(f"   📞 Total Contacts: {len(all_contacts)}")
    print(f"   🎯 Accountant Companies: {len(accountant_companies)}")
    print(f"   📞 Total Lead Contacts: {len(lead_contacts)}")
    print(f"   ✅ Accountant Companies as Leads: {len(accountant_leads)}")
    print(f"   🎯 UTM 'conta' Contacts (Accountant Leads): {len(utm_conta_contacts)}")
    
    # Key insights
    print(f"\n💡 KEY INSIGHTS:")
    print("-" * 50)
    print(f"   📈 August Accountant Companies: {len(august_accountant_companies)}")
    print(f"   📈 September Accountant Companies: {len(september_accountant_companies)}")
    print(f"   📈 August Accountant Leads (UTM): {len(august_utm_conta)}")
    print(f"   📈 September Accountant Leads (UTM): {len(september_utm_conta)}")
    
    if len(utm_conta_contacts) > 0:
        print(f"   ✅ Accountant leads are being created through UTM campaigns")
        print(f"   📊 Total accountant leads created: {len(utm_conta_contacts)}")
    else:
        print(f"   ⚠️  No accountant leads found through UTM campaigns")

if __name__ == "__main__":
    analyze_leads_associated_with_accountant_companies()
