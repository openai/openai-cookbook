#!/usr/bin/env python3
"""
HubSpot List Contactability Analyzer
Automatically analyzes any HubSpot list by name

Usage:
    python analyze_hubspot_list_by_name.py "Lista Prioridad 10 Sofi- Empresas"
    python analyze_hubspot_list_by_name.py --list-id 2333
"""

import requests
import json
import os
import sys
from typing import Dict, List, Optional
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

class HubSpotListAnalyzer:
    """Automated HubSpot List Contactability Analyzer"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.portal_id = "19877595"
    
    def find_list_by_name(self, list_name: str) -> Optional[Dict]:
        """Find a list by name (case-insensitive partial match)"""
        print(f"🔍 Searching for list: '{list_name}'")
        
        # Since /crm/v3/lists returns empty, we need the user to provide the ID
        # This is a known HubSpot API limitation
        print("⚠️  HubSpot Lists API has limitations - need List ID")
        print(f"Please find the list in HubSpot UI and provide the List ID from the URL")
        print(f"URL format: https://app.hubspot.com/contacts/{self.portal_id}/objectLists/[LIST_ID]/filters")
        return None
    
    def get_list_details(self, list_id: str) -> Optional[Dict]:
        """Get list details by ID"""
        url = f"{self.base_url}/crm/v3/lists/{list_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('list', {})
            else:
                print(f"❌ Error getting list {list_id}: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Exception: {e}")
            return None
    
    def get_list_members(self, list_id: str) -> List[str]:
        """Get all company IDs from a list"""
        url = f"{self.base_url}/crm/v3/lists/{list_id}/memberships"
        
        all_members = []
        after = None
        
        while True:
            params = {'limit': 100}
            if after:
                params['after'] = after
            
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    members = data.get('results', [])
                    
                    for member in members:
                        record_id = member.get('recordId')
                        if record_id:
                            all_members.append(record_id)
                    
                    # Check for pagination
                    paging = data.get('paging', {})
                    next_page = paging.get('next', {})
                    after = next_page.get('after')
                    
                    if not after:
                        break
                else:
                    print(f"⚠️  Error getting members: {response.status_code}")
                    break
                    
            except Exception as e:
                print(f"❌ Exception: {e}")
                break
        
        return all_members
    
    def get_companies_batch(self, company_ids: List[str]) -> List[Dict]:
        """Get company details in batch"""
        url = f"{self.base_url}/crm/v3/objects/companies/batch/read"
        
        properties = [
            "name", "type", "cuit", "hubspot_owner_id", "phone", "website", 
            "domain", "city", "country", "createdate", "hs_lastmodifieddate",
            "lifecyclestage", "num_associated_contacts"
        ]
        
        payload = {
            "properties": properties,
            "inputs": [{"id": comp_id} for comp_id in company_ids]
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('results', [])
            else:
                print(f"❌ Error getting companies: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Exception: {e}")
            return []
    
    def get_company_contacts(self, company_id: str) -> List[Dict]:
        """Get all contacts for a company"""
        # Get contact IDs
        url = f"{self.base_url}/crm/v4/objects/companies/{company_id}/associations/contacts"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code != 200:
                return []
            
            contact_ids = [assoc.get('toObjectId') or assoc.get('id') 
                          for assoc in response.json().get('results', [])]
            
            if not contact_ids:
                return []
            
            # Get contact details in batch
            contacts_url = f"{self.base_url}/crm/v3/objects/contacts/batch/read"
            
            properties = [
                "firstname", "lastname", "email", "phone", "mobilephone",
                "jobtitle", "lifecyclestage", "hs_email_domain", 
                "createdate", "lastmodifieddate"
            ]
            
            payload = {
                "properties": properties,
                "inputs": [{"id": str(cid)} for cid in contact_ids]
            }
            
            response = requests.post(contacts_url, headers=self.headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                return response.json().get('results', [])
            else:
                return []
                
        except Exception as e:
            print(f"⚠️  Error getting contacts for company {company_id}: {e}")
            return []
    
    def analyze_contact(self, contact: Dict) -> Dict:
        """Analyze a single contact"""
        props = contact.get('properties', {})
        
        email = props.get('email', '')
        email_domain = props.get('hs_email_domain', '')
        phone = props.get('phone', '')
        mobile = props.get('mobilephone', '')
        
        personal_domains = ['gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com',
                           'live.com', 'icloud.com', 'protonmail.com']
        
        return {
            'id': contact.get('id'),
            'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
            'email': email,
            'email_domain': email_domain,
            'has_email': bool(email),
            'is_personal_email': email_domain.lower() in personal_domains if email_domain else False,
            'phone': phone,
            'mobile': mobile,
            'has_phone': bool(phone),
            'has_mobile': bool(mobile),
            'has_any_phone': bool(phone or mobile),
            'jobtitle': props.get('jobtitle', ''),
            'lifecycle': props.get('lifecyclestage', ''),
            'contactable': bool(email) and bool(phone or mobile)
        }
    
    def generate_stats(self, companies: List[Dict], all_contacts: List[Dict]) -> Dict:
        """Generate contactability statistics"""
        
        total_companies = len(companies)
        total_contacts = len(all_contacts)
        
        if total_companies == 0:
            return {"error": "No companies found"}
        
        # Company stats
        companies_with_cuit = sum(1 for c in companies if c.get('properties', {}).get('cuit'))
        companies_with_phone = sum(1 for c in companies if c.get('properties', {}).get('phone'))
        companies_with_website = sum(1 for c in companies if c.get('properties', {}).get('website'))
        
        # Contact stats
        contacts_analyzed = [self.analyze_contact(c) for c in all_contacts]
        
        contacts_with_email = sum(1 for c in contacts_analyzed if c['has_email'])
        contacts_with_personal = sum(1 for c in contacts_analyzed if c['is_personal_email'])
        contacts_with_professional = contacts_with_email - contacts_with_personal
        contacts_with_any_phone = sum(1 for c in contacts_analyzed if c['has_any_phone'])
        contacts_fully_contactable = sum(1 for c in contacts_analyzed if c['contactable'])
        contacts_with_jobtitle = sum(1 for c in contacts_analyzed if c['jobtitle'])
        
        # Email domains
        email_domains = defaultdict(int)
        for c in contacts_analyzed:
            if c['email_domain']:
                email_domains[c['email_domain']] += 1
        
        return {
            'summary': {
                'total_companies': total_companies,
                'total_contacts': total_contacts,
                'avg_contacts_per_company': round(total_contacts / total_companies, 2) if total_companies > 0 else 0
            },
            'company_stats': {
                'with_cuit': companies_with_cuit,
                'with_cuit_pct': round(companies_with_cuit / total_companies * 100, 1),
                'with_phone': companies_with_phone,
                'with_phone_pct': round(companies_with_phone / total_companies * 100, 1),
                'with_website': companies_with_website,
                'with_website_pct': round(companies_with_website / total_companies * 100, 1)
            },
            'contact_stats': {
                'with_email': contacts_with_email,
                'with_email_pct': round(contacts_with_email / total_contacts * 100, 1) if total_contacts > 0 else 0,
                'with_professional_email': contacts_with_professional,
                'with_professional_email_pct': round(contacts_with_professional / total_contacts * 100, 1) if total_contacts > 0 else 0,
                'with_personal_email': contacts_with_personal,
                'with_personal_email_pct': round(contacts_with_personal / total_contacts * 100, 1) if total_contacts > 0 else 0,
                'with_any_phone': contacts_with_any_phone,
                'with_any_phone_pct': round(contacts_with_any_phone / total_contacts * 100, 1) if total_contacts > 0 else 0,
                'fully_contactable': contacts_fully_contactable,
                'fully_contactable_pct': round(contacts_fully_contactable / total_contacts * 100, 1) if total_contacts > 0 else 0,
                'with_jobtitle': contacts_with_jobtitle,
                'with_jobtitle_pct': round(contacts_with_jobtitle / total_contacts * 100, 1) if total_contacts > 0 else 0
            },
            'top_email_domains': dict(sorted(email_domains.items(), key=lambda x: x[1], reverse=True)[:10]),
            'companies': companies,
            'contacts': contacts_analyzed
        }
    
    def analyze_list(self, list_id: str) -> Dict:
        """Complete list analysis"""
        
        print(f"\n{'=' * 80}")
        print(f"🚀 HubSpot List Contactability Analysis")
        print(f"{'=' * 80}\n")
        
        # Get list details
        list_details = self.get_list_details(list_id)
        
        if not list_details:
            return {"error": "List not found"}
        
        list_name = list_details.get('name', 'Unnamed')
        list_size = list_details.get('size', 0)
        list_type = list_details.get('processingType', 'UNKNOWN')
        
        print(f"📋 List: {list_name}")
        print(f"🆔 List ID: {list_id}")
        print(f"📊 Size: {list_size} companies")
        print(f"⚙️  Type: {list_type}")
        print()
        
        # Get list members
        print(f"🔍 Getting list members...")
        company_ids = self.get_list_members(list_id)
        
        print(f"✅ Found {len(company_ids)} companies")
        
        if not company_ids:
            print("⚠️  No companies found in list")
            return {"error": "Empty list"}
        
        # Get company details
        print(f"\n📥 Fetching company details...")
        companies = self.get_companies_batch(company_ids)
        
        print(f"✅ Retrieved {len(companies)} company records")
        
        # Get contacts for each company
        print(f"\n👥 Fetching contacts for each company...")
        all_contacts = []
        
        for i, company in enumerate(companies, 1):
            company_id = company.get('id')
            company_name = company.get('properties', {}).get('name', 'Unknown')
            
            print(f"   {i}. {company_name}...", end=' ')
            
            contacts = self.get_company_contacts(company_id)
            all_contacts.extend(contacts)
            
            print(f"{len(contacts)} contacts")
        
        print(f"\n✅ Total contacts retrieved: {len(all_contacts)}")
        
        # Generate statistics
        print(f"\n📊 Generating contactability statistics...")
        stats = self.generate_stats(companies, all_contacts)
        
        # Display results
        self.display_results(list_name, list_id, stats)
        
        # Save to file
        self.save_results(list_name, list_id, stats)
        
        return stats
    
    def display_results(self, list_name: str, list_id: str, stats: Dict):
        """Display analysis results"""
        
        print(f"\n{'=' * 80}")
        print(f"📊 CONTACTABILITY ANALYSIS RESULTS")
        print(f"{'=' * 80}\n")
        
        print(f"📋 List: {list_name}")
        print(f"🆔 List ID: {list_id}")
        print()
        
        # Summary
        print(f"📈 SUMMARY")
        print(f"   Total Companies: {stats['summary']['total_companies']}")
        print(f"   Total Contacts: {stats['summary']['total_contacts']}")
        print(f"   Avg Contacts/Company: {stats['summary']['avg_contacts_per_company']}")
        
        # Company stats
        print(f"\n🏢 COMPANY DATA QUALITY")
        print(f"   With CUIT: {stats['company_stats']['with_cuit']}/{stats['summary']['total_companies']} ({stats['company_stats']['with_cuit_pct']}%)")
        print(f"   Missing CUIT: {stats['summary']['total_companies'] - stats['company_stats']['with_cuit']} ({100 - stats['company_stats']['with_cuit_pct']:.1f}%)")
        print(f"   With Phone: {stats['company_stats']['with_phone']}/{stats['summary']['total_companies']} ({stats['company_stats']['with_phone_pct']}%)")
        print(f"   With Website: {stats['company_stats']['with_website']}/{stats['summary']['total_companies']} ({stats['company_stats']['with_website_pct']}%)")
        
        # Contact stats
        print(f"\n👥 CONTACT REACHABILITY")
        print(f"   With Email: {stats['contact_stats']['with_email']}/{stats['summary']['total_contacts']} ({stats['contact_stats']['with_email_pct']}%)")
        print(f"   - Professional: {stats['contact_stats']['with_professional_email']} ({stats['contact_stats']['with_professional_email_pct']}%)")
        print(f"   - Personal: {stats['contact_stats']['with_personal_email']} ({stats['contact_stats']['with_personal_email_pct']}%)")
        print(f"   With Phone: {stats['contact_stats']['with_any_phone']}/{stats['summary']['total_contacts']} ({stats['contact_stats']['with_any_phone_pct']}%)")
        print(f"   ✅ FULLY CONTACTABLE: {stats['contact_stats']['fully_contactable']}/{stats['summary']['total_contacts']} ({stats['contact_stats']['fully_contactable_pct']}%)")
        
        # Top domains
        if stats['top_email_domains']:
            print(f"\n📧 TOP EMAIL DOMAINS")
            for domain, count in list(stats['top_email_domains'].items())[:5]:
                domain_type = "🏠 Personal" if domain.lower() in ['gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com'] else "🏢 Professional"
                print(f"   {domain_type} - {domain}: {count} contacts")
        
        print(f"\n{'=' * 80}")
    
    def save_results(self, list_name: str, list_id: str, stats: Dict):
        """Save results to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"list_{list_id}_contactability_{timestamp}.json"
        filepath = f"/Users/virulana/openai-cookbook/tools/outputs/{filename}"
        
        output = {
            'list_name': list_name,
            'list_id': list_id,
            'analysis_date': datetime.now().isoformat(),
            'stats': stats
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Results saved to: {filepath}")


def main():
    """Main execution"""
    
    # Get API key
    api_key = (
        os.environ.get('HUBSPOT_API_KEY') or 
        os.environ.get('COLPPY_CRM_AUTOMATIONS') or
        os.environ.get('ColppyCRMAutomations')
    )
    
    if not api_key:
        print("❌ HubSpot API key not found in environment")
        print("Please set HUBSPOT_API_KEY in /Users/virulana/openai-cookbook/.env")
        return
    
    analyzer = HubSpotListAnalyzer(api_key)
    
    # Get list ID from command line or prompt
    if len(sys.argv) > 1:
        if sys.argv[1] == '--list-id':
            list_id = sys.argv[2]
        else:
            # List name provided - need to convert to ID
            list_name = sys.argv[1]
            print(f"\n⚠️  HubSpot API Limitation:")
            print(f"Cannot search lists by name via API.")
            print(f"\nPlease provide the List ID instead:")
            print(f"1. Find '{list_name}' in HubSpot")
            print(f"2. Click on it and copy the ID from URL")
            print(f"3. Run: python {sys.argv[0]} --list-id [ID]")
            return
    else:
        print("Usage:")
        print(f"  python {sys.argv[0]} --list-id 2333")
        return
    
    # Run analysis
    analyzer.analyze_list(list_id)


if __name__ == "__main__":
    main()






