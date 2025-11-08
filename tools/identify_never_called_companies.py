#!/usr/bin/env python3
"""
Identify Never-Called Companies from List 2314
Analyzes characteristics of companies that have never been contacted by phone
"""

import requests
import json
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Load environment
try:
    from dotenv import load_dotenv
    env_path = Path('/Users/virulana/openai-cookbook/.env')
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Company Type Definitions from HubSpot README
COMPANY_TYPES = {
    'Alianza': 'Strategic partnerships',
    'Cuenta Pyme': 'Standard SMB accounts',
    'Cuenta Contador': 'Accountant channel companies',
    'Cuenta Contador y Reseller': 'Accountant + reseller',
    'Integración Comercial': 'Business integrations',
    'Integración Tecnológica': 'Technical integrations',
    'Pyme Referida': 'Referred SMBs',
    'RESELLER': 'Resellers',
    'VENDOR': 'Vendor/supplier',
    'OTHER': 'Other/unclassified',
    'Contador Robado': 'Reverse discovery accountants (using our product)',
    'Empresa Administrada': 'Managed companies'
}

class NeverCalledAnalyzer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def get_list_companies(self, list_id: str) -> list:
        """Get all company IDs from list"""
        url = f"{self.base_url}/crm/v3/lists/{list_id}/memberships"
        all_ids = []
        after = None
        
        print(f"📥 Fetching all companies from list {list_id}...")
        
        while True:
            params = {'limit': 100}
            if after:
                params['after'] = after
            
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code != 200:
                break
            
            data = response.json()
            batch = [m.get('recordId') for m in data.get('results', [])]
            all_ids.extend(batch)
            
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after:
                break
        
        return all_ids
    
    def has_calls(self, company_id: str) -> bool:
        """Check if company has any call engagements"""
        url = f"{self.base_url}/crm/v3/objects/companies/{company_id}/associations/calls"
        
        try:
            response = requests.get(url, headers=self.headers, params={'limit': 1}, timeout=10)
            
            if response.status_code == 200:
                results = response.json().get('results', [])
                return len(results) > 0
            return False
        except:
            return False
    
    def get_companies_details(self, company_ids: list) -> list:
        """Get company details in batch"""
        url = f"{self.base_url}/crm/v3/objects/companies/batch/read"
        
        properties = [
            'name', 'type', 'cuit', 'hubspot_owner_id', 'phone', 'website',
            'createdate', 'hs_lastmodifieddate', 'lifecyclestage',
            'num_associated_deals', 'num_associated_contacts',
            'notes_last_contacted', 'hs_last_sales_activity_timestamp'
        ]
        
        all_companies = []
        
        # Process in batches of 100
        for i in range(0, len(company_ids), 100):
            batch = company_ids[i:i+100]
            
            payload = {
                'properties': properties,
                'inputs': [{'id': cid} for cid in batch]
            }
            
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                all_companies.extend(response.json().get('results', []))
        
        return all_companies
    
    def analyze_never_called(self, list_id: str):
        """Identify and analyze never-called companies"""
        
        print(f"🚀 Identifying Never-Called Companies - List {list_id}")
        print("=" * 80)
        
        # Get list details
        response = requests.get(f"{self.base_url}/crm/v3/lists/{list_id}", headers=self.headers)
        list_data = response.json().get('list', {})
        list_name = list_data.get('name', 'Unknown')
        
        print(f"📋 List: {list_name}")
        print()
        
        # Get all companies
        company_ids = self.get_list_companies(list_id)
        print(f"✅ Found {len(company_ids):,} total companies")
        print()
        
        # Check which companies have calls
        print(f"🔍 Checking call history for each company...")
        print(f"   (This may take a few minutes...)")
        print()
        
        never_called = []
        ever_called = []
        
        for i, comp_id in enumerate(company_ids, 1):
            if i % 100 == 0:
                print(f"   Checked {i}/{len(company_ids)} companies...")
            
            if self.has_calls(comp_id):
                ever_called.append(comp_id)
            else:
                never_called.append(comp_id)
        
        print(f"\n✅ Scan complete!")
        print(f"   Companies with calls: {len(ever_called):,} ({len(ever_called)/len(company_ids)*100:.1f}%)")
        print(f"   Companies never called: {len(never_called):,} ({len(never_called)/len(company_ids)*100:.1f}%)")
        print()
        
        # Get details for never-called companies
        print(f"📥 Fetching details for {len(never_called):,} never-called companies...")
        never_called_details = self.get_companies_details(never_called)
        print(f"✅ Retrieved details for {len(never_called_details):,} companies")
        print()
        
        # Analyze characteristics
        stats = self.analyze_characteristics(never_called_details)
        
        # Display results
        self.display_results(list_name, stats, never_called_details)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"/Users/virulana/openai-cookbook/tools/outputs/never_called_companies_{list_id}_{timestamp}.json"
        
        output = {
            'list_name': list_name,
            'list_id': list_id,
            'total_companies': len(company_ids),
            'never_called_count': len(never_called),
            'statistics': stats,
            'companies': never_called_details
        }
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        print(f"💾 Full data saved to: {filename}")
        
        # Also create CSV for easy import
        csv_filename = f"/Users/virulana/openai-cookbook/tools/outputs/never_called_companies_{list_id}_{timestamp}.csv"
        self.save_to_csv(never_called_details, csv_filename)
        print(f"📊 CSV exported to: {csv_filename}")
    
    def analyze_characteristics(self, companies: list) -> dict:
        """Analyze characteristics of never-called companies"""
        
        stats = {
            'by_type': defaultdict(int),
            'by_owner': defaultdict(int),
            'with_phone': 0,
            'without_phone': 0,
            'with_cuit': 0,
            'without_cuit': 0,
            'with_website': 0,
            'with_deals': 0,
            'with_contacts': 0,
            'avg_contacts': 0,
            'creation_dates': [],
            'last_modified_dates': []
        }
        
        total_contacts = 0
        
        for company in companies:
            props = company.get('properties', {})
            
            # Type
            comp_type = props.get('type', 'Unknown')
            stats['by_type'][comp_type] += 1
            
            # Owner
            owner_id = props.get('hubspot_owner_id', 'Unassigned')
            stats['by_owner'][owner_id] += 1
            
            # Phone
            if props.get('phone'):
                stats['with_phone'] += 1
            else:
                stats['without_phone'] += 1
            
            # CUIT
            if props.get('cuit'):
                stats['with_cuit'] += 1
            else:
                stats['without_cuit'] += 1
            
            # Website
            if props.get('website'):
                stats['with_website'] += 1
            
            # Deals
            num_deals = int(props.get('num_associated_deals') or 0)
            if num_deals > 0:
                stats['with_deals'] += 1
            
            # Contacts
            num_contacts = int(props.get('num_associated_contacts') or 0)
            if num_contacts > 0:
                stats['with_contacts'] += 1
            total_contacts += num_contacts
            
            # Dates
            if props.get('createdate'):
                stats['creation_dates'].append(props.get('createdate'))
            if props.get('hs_lastmodifieddate'):
                stats['last_modified_dates'].append(props.get('hs_lastmodifieddate'))
        
        stats['avg_contacts'] = total_contacts / len(companies) if companies else 0
        
        return stats
    
    def display_results(self, list_name: str, stats: dict, companies: list):
        """Display analysis results"""
        
        total = len(companies)
        
        print("=" * 80)
        print("🎯 NEVER-CALLED COMPANIES ANALYSIS")
        print("=" * 80)
        
        print(f"\n📋 List: {list_name}")
        print(f"🚫 Never-Called Companies: {total:,}")
        print()
        
        # By type
        print(f"📊 BREAKDOWN BY COMPANY TYPE")
        print("-" * 80)
        for comp_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
            description = COMPANY_TYPES.get(comp_type, 'Unknown type')
            pct = count / total * 100
            print(f"{comp_type}: {count:,} ({pct:.1f}%)")
            print(f"   → {description}")
        print()
        
        # By owner
        print(f"👤 BREAKDOWN BY OWNER")
        print("-" * 80)
        top_owners = sorted(stats['by_owner'].items(), key=lambda x: x[1], reverse=True)[:10]
        for owner_id, count in top_owners:
            pct = count / total * 100
            print(f"Owner {owner_id}: {count:,} companies ({pct:.1f}%)")
        print()
        
        # Data quality
        print(f"📋 DATA QUALITY")
        print("-" * 80)
        print(f"With Phone: {stats['with_phone']:,}/{total:,} ({stats['with_phone']/total*100:.1f}%)")
        print(f"WITHOUT Phone: {stats['without_phone']:,}/{total:,} ({stats['without_phone']/total*100:.1f}%) ⚠️")
        print(f"With CUIT: {stats['with_cuit']:,}/{total:,} ({stats['with_cuit']/total*100:.1f}%)")
        print(f"WITHOUT CUIT: {stats['without_cuit']:,}/{total:,} ({stats['without_cuit']/total*100:.1f}%) ⚠️")
        print(f"With Website: {stats['with_website']:,}/{total:,} ({stats['with_website']/total*100:.1f}%)")
        print()
        
        # Business metrics
        print(f"💼 BUSINESS METRICS")
        print("-" * 80)
        print(f"With Associated Deals: {stats['with_deals']:,}/{total:,} ({stats['with_deals']/total*100:.1f}%)")
        print(f"With Contacts: {stats['with_contacts']:,}/{total:,} ({stats['with_contacts']/total*100:.1f}%)")
        print(f"Avg Contacts per Company: {stats['avg_contacts']:.1f}")
        print()
        
        # Sample companies
        print(f"📋 SAMPLE NEVER-CALLED COMPANIES (First 10)")
        print("-" * 80)
        for i, company in enumerate(companies[:10], 1):
            props = company.get('properties', {})
            comp_id = company.get('id')
            name = props.get('name', 'Unknown')
            comp_type = props.get('type', 'Unknown')
            phone = props.get('phone', 'No phone')
            
            print(f"{i}. {name}")
            print(f"   ID: {comp_id} | Type: {comp_type}")
            print(f"   Phone: {phone}")
            print(f"   URL: https://app.hubspot.com/contacts/19877595/record/0-2/{comp_id}")
            print()
        
        print("=" * 80)
    
    def save_to_csv(self, companies: list, filename: str):
        """Save to CSV for easy import"""
        import csv
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Headers
            writer.writerow([
                'Company ID', 'Name', 'Type', 'Owner ID', 'Phone', 'CUIT',
                'Website', 'Num Deals', 'Num Contacts', 'Created Date',
                'HubSpot URL'
            ])
            
            # Data
            for company in companies:
                props = company.get('properties', {})
                comp_id = company.get('id')
                
                writer.writerow([
                    comp_id,
                    props.get('name', ''),
                    props.get('type', ''),
                    props.get('hubspot_owner_id', ''),
                    props.get('phone', ''),
                    props.get('cuit', ''),
                    props.get('website', ''),
                    props.get('num_associated_deals', '0'),
                    props.get('num_associated_contacts', '0'),
                    props.get('createdate', ''),
                    f"https://app.hubspot.com/contacts/19877595/record/0-2/{comp_id}"
                ])


def main():
    import sys
    
    api_key = (
        os.environ.get('HUBSPOT_API_KEY') or 
        os.environ.get('COLPPY_CRM_AUTOMATIONS')
    )
    
    if not api_key:
        print("❌ API key not found")
        return
    
    list_id = sys.argv[1] if len(sys.argv) > 1 else "2314"
    
    analyzer = NeverCalledAnalyzer(api_key)
    analyzer.analyze_never_called(list_id)


if __name__ == "__main__":
    main()






