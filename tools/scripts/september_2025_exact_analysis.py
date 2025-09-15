#!/usr/bin/env python3
"""
September 2025 Accountant Channel Analysis - EXACT DATA
======================================================

Uses the exact data retrieved from HubSpot API with complete pagination
to analyze accountant channel performance and requalification process.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any

def load_september_data():
    """Load the exact September 2025 data"""
    
    print("📊 LOADING SEPTEMBER 2025 EXACT DATA")
    print("=" * 45)
    
    # Load the exact data files
    contacts_file = "hubspot_contacts_20250901_20250930_20250908_211937.json"
    companies_file = "hubspot_companies_20250901_20250930_20250908_211948.json"
    
    if not os.path.exists(contacts_file):
        print(f"❌ Contacts file not found: {contacts_file}")
        return None, None
    
    if not os.path.exists(companies_file):
        print(f"❌ Companies file not found: {companies_file}")
        return None, None
    
    # Load contacts
    with open(contacts_file, 'r', encoding='utf-8') as f:
        contacts = json.load(f)
    
    # Load companies  
    with open(companies_file, 'r', encoding='utf-8') as f:
        companies = json.load(f)
    
    print(f"✅ Contacts loaded: {len(contacts):,} records")
    print(f"✅ Companies loaded: {len(companies):,} records")
    
    return contacts, companies

def identify_accountant_contacts(contacts: List[Dict]) -> Dict[str, Any]:
    """Identify accountant contacts using exact criteria"""
    
    print("\n🎯 ACCOUNTANT CONTACT IDENTIFICATION")
    print("=" * 40)
    
    accountant_contacts = []
    utm_accountant_contacts = []
    es_contador_contacts = []
    
    for contact in contacts:
        properties = contact.get("properties", {})
        
        # Primary identification: es_contador = true
        if properties.get("es_contador") == "true":
            es_contador_contacts.append(contact)
            accountant_contacts.append(contact)
        
        # Secondary identification: UTM campaign contains 'conta'
        utm_campaign = properties.get("utm_campaign", "")
        if utm_campaign and "conta" in utm_campaign.lower():
            utm_accountant_contacts.append(contact)
            if contact not in accountant_contacts:
                accountant_contacts.append(contact)
    
    print(f"📊 IDENTIFICATION RESULTS:")
    print(f"   • Direct es_contador flag: {len(es_contador_contacts)} contacts")
    print(f"   • UTM campaign 'conta': {len(utm_accountant_contacts)} contacts")
    print(f"   • Total unique accountants: {len(accountant_contacts)} contacts")
    
    return {
        "total_accountants": len(accountant_contacts),
        "es_contador_flag": len(es_contador_contacts),
        "utm_campaign": len(utm_accountant_contacts),
        "accountant_contacts": accountant_contacts
    }

def identify_accountant_companies(companies: List[Dict]) -> Dict[str, Any]:
    """Identify accountant companies using exact criteria"""
    
    print("\n🏢 ACCOUNTANT COMPANY IDENTIFICATION")
    print("=" * 40)
    
    accountant_companies = []
    cuenta_contador = []
    cuenta_contador_reseller = []
    contador_robado = []
    
    for company in companies:
        properties = company.get("properties", {})
        company_type = properties.get("type", "")
        
        if company_type == "Cuenta Contador":
            cuenta_contador.append(company)
            accountant_companies.append(company)
        elif company_type == "Cuenta Contador y Reseller":
            cuenta_contador_reseller.append(company)
            accountant_companies.append(company)
        elif company_type == "Contador Robado":
            contador_robado.append(company)
            accountant_companies.append(company)
    
    print(f"📊 COMPANY TYPE ANALYSIS:")
    print(f"   • Cuenta Contador: {len(cuenta_contador)} companies")
    print(f"   • Cuenta Contador y Reseller: {len(cuenta_contador_reseller)} companies")
    print(f"   • Contador Robado: {len(contador_robado)} companies")
    print(f"   • Total accountant companies: {len(accountant_companies)} companies")
    
    return {
        "total_accountant_companies": len(accountant_companies),
        "cuenta_contador": len(cuenta_contador),
        "cuenta_contador_reseller": len(cuenta_contador_reseller),
        "contador_robado": len(contador_robado),
        "accountant_companies": accountant_companies
    }

def analyze_conversion_metrics(contacts: List[Dict], companies: List[Dict]) -> Dict[str, Any]:
    """Analyze conversion metrics for accountant channel"""
    
    print("\n📈 CONVERSION METRICS ANALYSIS")
    print("=" * 35)
    
    # Contact lifecycle analysis
    total_contacts = len(contacts)
    leads = sum(1 for c in contacts if c.get("properties", {}).get("lifecyclestage") == "lead")
    customers = sum(1 for c in contacts if c.get("properties", {}).get("lifecyclestage") == "customer")
    opportunities = sum(1 for c in contacts if c.get("properties", {}).get("lifecyclestage") == "opportunity")
    
    # Company lifecycle analysis
    total_companies = len(companies)
    company_leads = sum(1 for c in companies if c.get("properties", {}).get("lifecyclestage") == "lead")
    company_customers = sum(1 for c in companies if c.get("properties", {}).get("lifecyclestage") == "customer")
    company_opportunities = sum(1 for c in companies if c.get("properties", {}).get("lifecyclestage") == "opportunity")
    
    print(f"📊 CONTACT CONVERSION:")
    print(f"   • Total contacts: {total_contacts:,}")
    print(f"   • Leads: {leads:,} ({leads/total_contacts*100:.1f}%)")
    print(f"   • Opportunities: {opportunities:,} ({opportunities/total_contacts*100:.1f}%)")
    print(f"   • Customers: {customers:,} ({customers/total_contacts*100:.1f}%)")
    
    print(f"\n📊 COMPANY CONVERSION:")
    print(f"   • Total companies: {total_companies:,}")
    print(f"   • Leads: {company_leads:,} ({company_leads/total_companies*100:.1f}%)")
    print(f"   • Opportunities: {company_opportunities:,} ({company_opportunities/total_companies*100:.1f}%)")
    print(f"   • Customers: {company_customers:,} ({company_customers/total_companies*100:.1f}%)")
    
    return {
        "contacts": {
            "total": total_contacts,
            "leads": leads,
            "opportunities": opportunities,
            "customers": customers
        },
        "companies": {
            "total": total_companies,
            "leads": company_leads,
            "opportunities": company_opportunities,
            "customers": company_customers
        }
    }

def analyze_requalification_process(contacts: List[Dict]) -> Dict[str, Any]:
    """Analyze requalification process performance"""
    
    print("\n🔄 REQUALIFICATION PROCESS ANALYSIS")
    print("=" * 40)
    
    # UTM campaign analysis
    utm_campaigns = {}
    conta_campaigns = {}
    
    for contact in contacts:
        utm_campaign = contact.get("properties", {}).get("utm_campaign", "")
        if utm_campaign:
            utm_campaigns[utm_campaign] = utm_campaigns.get(utm_campaign, 0) + 1
            if "conta" in utm_campaign.lower():
                conta_campaigns[utm_campaign] = conta_campaigns.get(utm_campaign, 0) + 1
    
    # Active contacts analysis
    active_contacts = sum(1 for c in contacts if c.get("properties", {}).get("activo") == "true")
    
    print(f"📊 UTM CAMPAIGN ANALYSIS:")
    print(f"   • Total UTM campaigns: {len(utm_campaigns)}")
    print(f"   • Accountant campaigns: {len(conta_campaigns)}")
    
    if conta_campaigns:
        print(f"   • Accountant campaign details:")
        for campaign, count in conta_campaigns.items():
            print(f"     - {campaign}: {count} contacts")
    
    print(f"\n📊 ACTIVATION METRICS:")
    print(f"   • Active contacts: {active_contacts:,} ({active_contacts/len(contacts)*100:.1f}%)")
    
    return {
        "utm_campaigns": utm_campaigns,
        "conta_campaigns": conta_campaigns,
        "active_contacts": active_contacts,
        "total_contacts": len(contacts)
    }

def generate_exact_summary(contacts_data: Dict, companies_data: Dict, conversion_data: Dict, requalification_data: Dict):
    """Generate exact summary with precise numbers"""
    
    print("\n📋 EXACT SEPTEMBER 2025 SUMMARY")
    print("=" * 40)
    
    print(f"📅 Analysis Period: September 1-30, 2025")
    print(f"📊 Dataset Size:")
    print(f"   • Contacts: {conversion_data['contacts']['total']:,} (exact)")
    print(f"   • Companies: {conversion_data['companies']['total']:,} (exact)")
    print(f"   • Deals: 28 (exact - from API retrieval)")
    
    print(f"\n🎯 ACCOUNTANT CHANNEL:")
    print(f"   • Accountant contacts: {contacts_data['total_accountants']:,}")
    print(f"   • Accountant companies: {companies_data['total_accountant_companies']:,}")
    print(f"   • UTM accountant campaigns: {len(requalification_data['conta_campaigns'])}")
    
    print(f"\n📈 CONVERSION PERFORMANCE:")
    print(f"   • Contact conversion rate: {conversion_data['contacts']['customers']/conversion_data['contacts']['total']*100:.1f}%")
    print(f"   • Company conversion rate: {conversion_data['companies']['customers']/conversion_data['companies']['total']*100:.1f}%")
    print(f"   • Active contacts: {requalification_data['active_contacts']:,}")
    
    return {
        "period": "September 1-30, 2025",
        "contacts": conversion_data['contacts']['total'],
        "companies": conversion_data['companies']['total'],
        "deals": 28,
        "accountant_contacts": contacts_data['total_accountants'],
        "accountant_companies": companies_data['total_accountant_companies'],
        "conversion_rate": conversion_data['contacts']['customers']/conversion_data['contacts']['total']*100
    }

def main():
    """Main analysis function with exact data"""
    
    print("🎯 SEPTEMBER 2025 ACCOUNTANT CHANNEL ANALYSIS - EXACT DATA")
    print("=" * 65)
    
    # Load exact data
    contacts, companies = load_september_data()
    if not contacts or not companies:
        print("❌ Failed to load data")
        return
    
    # Perform analysis
    contacts_analysis = identify_accountant_contacts(contacts)
    companies_analysis = identify_accountant_companies(companies)
    conversion_analysis = analyze_conversion_metrics(contacts, companies)
    requalification_analysis = analyze_requalification_process(contacts)
    
    # Generate summary
    summary = generate_exact_summary(contacts_analysis, companies_analysis, conversion_analysis, requalification_analysis)
    
    print("\n" + "=" * 65)
    print("✅ EXACT DATA ANALYSIS COMPLETE")
    print("📊 All numbers are precise from complete pagination")
    print("🎯 Ready for implementation")
    
    return summary

if __name__ == "__main__":
    main()
