#!/usr/bin/env python3
"""
HubSpot List Contactability Analysis
Detailed contactability analysis for List 2216
"""

import requests
import json
import os
from typing import Dict, List
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path('/Users/virulana/openai-cookbook/.env')
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

class ContactabilityAnalyzer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
    def search_company(self, name: str) -> Dict:
        """Search for a company by name"""
        payload = {
            "query": name,
            "limit": 5,
            "properties": [
                "name", "type", "lifecyclestage", "cuit", "hubspot_owner_id",
                "phone", "website", "domain", "city", "country"
            ]
        }
        
        url = f"{self.base_url}/crm/v3/objects/companies/search"
        response = requests.post(url, headers=self.headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results:
                return results[0]  # Return best match
        return None
    
    def get_company_contacts(self, company_id: str) -> List[Dict]:
        """Get all contacts for a company with full details"""
        # First get contact IDs
        url = f"{self.base_url}/crm/v4/objects/companies/{company_id}/associations/contacts"
        response = requests.get(url, headers=self.headers, timeout=30)
        
        if response.status_code != 200:
            return []
        
        contact_ids = [assoc.get("id") for assoc in response.json().get("results", [])]
        
        # Then get full contact details
        contacts = []
        for contact_id in contact_ids:
            url = f"{self.base_url}/crm/v3/objects/contacts/{contact_id}"
            params = {
                "properties": "firstname,lastname,email,phone,mobilephone,jobtitle,lifecyclestage,hs_email_domain,lastmodifieddate,createdate"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                contact_data = response.json()
                contacts.append({
                    "id": contact_id,
                    "properties": contact_data.get("properties", {})
                })
        
        return contacts
    
    def analyze_contact(self, contact: Dict) -> Dict:
        """Analyze a single contact for contactability"""
        props = contact.get("properties", {})
        
        email = props.get("email", "")
        email_domain = props.get("hs_email_domain", "")
        phone = props.get("phone", "")
        mobile = props.get("mobilephone", "")
        
        # Personal email domains
        personal_domains = ['gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 
                           'live.com', 'icloud.com', 'protonmail.com']
        
        return {
            "contact_id": contact.get("id"),
            "name": f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
            "email": email,
            "email_domain": email_domain,
            "has_email": bool(email),
            "is_personal_email": email_domain.lower() in personal_domains if email_domain else False,
            "phone": phone,
            "mobile": mobile,
            "has_phone": bool(phone),
            "has_mobile": bool(mobile),
            "has_any_phone": bool(phone or mobile),
            "jobtitle": props.get("jobtitle", ""),
            "lifecycle": props.get("lifecyclestage", ""),
            "last_modified": props.get("lastmodifieddate", ""),
            "contactable": bool(email) and bool(phone or mobile)
        }
    
    def analyze_list(self, company_names: List[str]) -> Dict:
        """Full contactability analysis for a list"""
        print("🔍 Starting Contactability Analysis")
        print("=" * 80)
        
        all_companies = []
        all_contacts_data = []
        
        # Get companies
        for name in company_names:
            print(f"\n📊 Analyzing: {name}")
            company = self.search_company(name)
            
            if not company:
                print(f"   ⚠️  Not found")
                continue
            
            company_id = company.get("id")
            props = company.get("properties", {})
            
            company_info = {
                "id": company_id,
                "name": props.get("name", ""),
                "type": props.get("type", ""),
                "cuit": props.get("cuit", ""),
                "owner_id": props.get("hubspot_owner_id", ""),
                "phone": props.get("phone", ""),
                "website": props.get("website", ""),
                "url": f"https://app.hubspot.com/contacts/19877595/record/0-2/{company_id}"
            }
            
            # Get contacts
            contacts = self.get_company_contacts(company_id)
            print(f"   ✅ Found {len(contacts)} contacts")
            
            company_info["contacts_count"] = len(contacts)
            company_info["contacts"] = []
            
            for contact in contacts:
                contact_analysis = self.analyze_contact(contact)
                company_info["contacts"].append(contact_analysis)
                all_contacts_data.append(contact_analysis)
            
            all_companies.append(company_info)
        
        return self.generate_stats(all_companies, all_contacts_data)
    
    def generate_stats(self, companies: List[Dict], contacts: List[Dict]) -> Dict:
        """Generate comprehensive contactability statistics"""
        
        total_companies = len(companies)
        total_contacts = len(contacts)
        
        # Company stats
        companies_with_cuit = sum(1 for c in companies if c.get("cuit"))
        companies_with_phone = sum(1 for c in companies if c.get("phone"))
        
        # Contact stats
        contacts_with_email = sum(1 for c in contacts if c.get("has_email"))
        contacts_with_personal_email = sum(1 for c in contacts if c.get("is_personal_email"))
        contacts_with_professional_email = contacts_with_email - contacts_with_personal_email
        contacts_with_phone = sum(1 for c in contacts if c.get("has_phone"))
        contacts_with_mobile = sum(1 for c in contacts if c.get("has_mobile"))
        contacts_with_any_phone = sum(1 for c in contacts if c.get("has_any_phone"))
        contacts_fully_contactable = sum(1 for c in contacts if c.get("contactable"))
        contacts_with_jobtitle = sum(1 for c in contacts if c.get("jobtitle"))
        
        # Missing data
        contacts_no_email = total_contacts - contacts_with_email
        contacts_no_phone = total_contacts - contacts_with_any_phone
        contacts_no_email_or_phone = sum(1 for c in contacts if not c.get("has_email") and not c.get("has_any_phone"))
        
        # Email domains
        email_domains = defaultdict(int)
        for c in contacts:
            if c.get("email_domain"):
                email_domains[c.get("email_domain")] += 1
        
        # Job titles
        job_titles = defaultdict(int)
        for c in contacts:
            if c.get("jobtitle"):
                job_titles[c.get("jobtitle")] += 1
        
        return {
            "summary": {
                "total_companies": total_companies,
                "total_contacts": total_contacts,
                "avg_contacts_per_company": round(total_contacts / total_companies, 2) if total_companies > 0 else 0
            },
            "company_stats": {
                "with_cuit": companies_with_cuit,
                "with_cuit_pct": round(companies_with_cuit / total_companies * 100, 1) if total_companies > 0 else 0,
                "missing_cuit": total_companies - companies_with_cuit,
                "with_phone": companies_with_phone,
                "with_phone_pct": round(companies_with_phone / total_companies * 100, 1) if total_companies > 0 else 0
            },
            "contact_stats": {
                "with_email": contacts_with_email,
                "with_email_pct": round(contacts_with_email / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "with_professional_email": contacts_with_professional_email,
                "with_professional_email_pct": round(contacts_with_professional_email / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "with_personal_email": contacts_with_personal_email,
                "with_personal_email_pct": round(contacts_with_personal_email / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "with_phone": contacts_with_phone,
                "with_phone_pct": round(contacts_with_phone / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "with_mobile": contacts_with_mobile,
                "with_mobile_pct": round(contacts_with_mobile / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "with_any_phone": contacts_with_any_phone,
                "with_any_phone_pct": round(contacts_with_any_phone / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "fully_contactable": contacts_fully_contactable,
                "fully_contactable_pct": round(contacts_fully_contactable / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "with_jobtitle": contacts_with_jobtitle,
                "with_jobtitle_pct": round(contacts_with_jobtitle / total_contacts * 100, 1) if total_contacts > 0 else 0
            },
            "gaps": {
                "no_email": contacts_no_email,
                "no_email_pct": round(contacts_no_email / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "no_phone": contacts_no_phone,
                "no_phone_pct": round(contacts_no_phone / total_contacts * 100, 1) if total_contacts > 0 else 0,
                "no_email_or_phone": contacts_no_email_or_phone,
                "no_email_or_phone_pct": round(contacts_no_email_or_phone / total_contacts * 100, 1) if total_contacts > 0 else 0
            },
            "top_email_domains": dict(sorted(email_domains.items(), key=lambda x: x[1], reverse=True)[:10]),
            "top_job_titles": dict(sorted(job_titles.items(), key=lambda x: x[1], reverse=True)[:10]),
            "companies": companies,
            "contacts": contacts
        }

def main():
    # Get API key
    api_key = (
        os.environ.get('HUBSPOT_API_KEY') or 
        os.environ.get('COLPPY_CRM_AUTOMATIONS') or
        os.environ.get('ColppyCRMAutomations')
    )
    
    if not api_key:
        print("❌ HubSpot API key not found")
        return
    
    print("🚀 HubSpot List 2216 - Contactability Analysis")
    print("=" * 80)
    print(f"🔑 API Key: {api_key[:20]}...")
    print()
    
    analyzer = ContactabilityAnalyzer(api_key)
    
    # Companies from List 2216
    company_names = [
        "Contadora Fernanda Carini",
        "Chicolino, de Luca & Asoc.",
        "Estudio Glave", 
        "Estudio Szmedra",
        "C&C Consultoria",
        "Contadora Giselle Cosentino",
        "Estudio BDR",
        "1163 - Estudio GAF S.R.L.",
        "Cra Noelia Braña",
        "Contador Fabian Manzoni"
    ]
    
    # Run analysis
    results = analyzer.analyze_list(company_names)
    
    # Display results
    print("\n" + "=" * 80)
    print("📊 CONTACTABILITY ANALYSIS RESULTS - LIST 2216")
    print("=" * 80)
    
    # Summary
    print(f"\n📈 SUMMARY")
    print(f"   Total Companies: {results['summary']['total_companies']}")
    print(f"   Total Contacts: {results['summary']['total_contacts']}")
    print(f"   Avg Contacts per Company: {results['summary']['avg_contacts_per_company']}")
    
    # Company stats
    print(f"\n🏢 COMPANY DATA QUALITY")
    print(f"   With CUIT: {results['company_stats']['with_cuit']}/{results['summary']['total_companies']} ({results['company_stats']['with_cuit_pct']}%)")
    print(f"   Missing CUIT: {results['company_stats']['missing_cuit']} ({100 - results['company_stats']['with_cuit_pct']:.1f}%)")
    print(f"   With Phone: {results['company_stats']['with_phone']}/{results['summary']['total_companies']} ({results['company_stats']['with_phone_pct']}%)")
    
    # Contact stats
    print(f"\n👥 CONTACT REACHABILITY")
    print(f"   With Email: {results['contact_stats']['with_email']}/{results['summary']['total_contacts']} ({results['contact_stats']['with_email_pct']}%)")
    print(f"   - Professional Email: {results['contact_stats']['with_professional_email']} ({results['contact_stats']['with_professional_email_pct']}%)")
    print(f"   - Personal Email: {results['contact_stats']['with_personal_email']} ({results['contact_stats']['with_personal_email_pct']}%)")
    print(f"\n   With Phone (fixed): {results['contact_stats']['with_phone']}/{results['summary']['total_contacts']} ({results['contact_stats']['with_phone_pct']}%)")
    print(f"   With Mobile: {results['contact_stats']['with_mobile']}/{results['summary']['total_contacts']} ({results['contact_stats']['with_mobile_pct']}%)")
    print(f"   With Any Phone: {results['contact_stats']['with_any_phone']}/{results['summary']['total_contacts']} ({results['contact_stats']['with_any_phone_pct']}%)")
    print(f"\n   ✅ FULLY CONTACTABLE (email + phone): {results['contact_stats']['fully_contactable']}/{results['summary']['total_contacts']} ({results['contact_stats']['fully_contactable_pct']}%)")
    
    # Gaps
    print(f"\n⚠️  DATA GAPS")
    print(f"   Missing Email: {results['gaps']['no_email']} contacts ({results['gaps']['no_email_pct']}%)")
    print(f"   Missing Phone: {results['gaps']['no_phone']} contacts ({results['gaps']['no_phone_pct']}%)")
    print(f"   Missing Both: {results['gaps']['no_email_or_phone']} contacts ({results['gaps']['no_email_or_phone_pct']}%)")
    
    # Job titles
    print(f"\n💼 JOB TITLES")
    print(f"   With Job Title: {results['contact_stats']['with_jobtitle']}/{results['summary']['total_contacts']} ({results['contact_stats']['with_jobtitle_pct']}%)")
    if results['top_job_titles']:
        print(f"\n   Top Job Titles:")
        for title, count in list(results['top_job_titles'].items())[:5]:
            print(f"   - {title}: {count} contacts")
    
    # Email domains
    if results['top_email_domains']:
        print(f"\n📧 TOP EMAIL DOMAINS")
        for domain, count in list(results['top_email_domains'].items())[:10]:
            domain_type = "🏠 Personal" if domain.lower() in ['gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com'] else "🏢 Professional"
            print(f"   {domain_type} - {domain}: {count} contacts")
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/Users/virulana/openai-cookbook/tools/outputs/contactability_analysis_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Detailed results saved to:")
    print(f"   {output_file}")
    
    print("\n" + "=" * 80)
    print("✅ Analysis completed!")
    print("=" * 80)

if __name__ == "__main__":
    main()






