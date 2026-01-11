#!/usr/bin/env python3
"""
🎯 COLPPY NPS ICP DATA QUALITY ANALYSIS
Analyzes data quality for company-level ICP classification step by step

This script:
1. Loads NPS survey responses from Intercom
2. Step 1: Tries to get primary company (association typeId 1) for each contact
3. Reports coverage statistics for Step 1
4. Step 2: Fallback to deal primary company (association typeId 5) for contacts without primary company
5. Step 3: Fallback to any associated company for remaining contacts
6. Step 4: Final classification and reporting

Each step saves enrichment data to CSV for caching and analysis acceleration.

Usage:
    python analyze_nps_icp_data_quality.py --files nps_file1.csv nps_file2.csv [--output-dir outputs/]
    python analyze_nps_icp_data_quality.py --file nps_file.csv [--output-dir outputs/]
"""

import pandas as pd
import numpy as np
from datetime import datetime
import argparse
import os
import json
from pathlib import Path
import warnings
import time
import sys
import requests
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

warnings.filterwarnings('ignore')

# Load environment variables from .env file
root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), '.env')
if os.path.exists(root_env):
    load_dotenv(root_env)
else:
    load_dotenv()

# HubSpot API Configuration
HUBSPOT_BASE_URL = "https://api.hubapi.com"

def get_hubspot_api_key():
    """Get HubSpot API key from environment variables"""
    return (
        os.getenv("HUBSPOT_API_KEY") or
        os.getenv("HUBSPOT_ACCESS_TOKEN") or
        os.getenv("HUBSPOT_TOKEN") or
        os.getenv("COLPPY_CRM_AUTOMATIONS") or
        os.getenv("ColppyCRMAutomations")
    )

def get_contact_by_email(email: str, api_key: str) -> Optional[Dict]:
    """
    Get contact by email using HubSpot Search API
    
    Args:
        email: Contact email address
        api_key: HubSpot API key
    
    Returns:
        Contact object with id and properties, or None if not found
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    search_url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search"
    payload = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "email",
                "operator": "EQ",
                "value": str(email).strip().lower()
            }]
        }],
        "properties": ["email", "firstname", "lastname"],
        "limit": 1
    }
    
    try:
        response = requests.post(search_url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results and len(results) > 0:
                return results[0]
        elif response.status_code == 429:
            # Rate limited - wait and retry
            retry_after = int(response.headers.get('Retry-After', 2))
            time.sleep(retry_after)
            return get_contact_by_email(email, api_key)
    except Exception as e:
        print(f"   ⚠️  Error fetching contact {email}: {str(e)}")
    
    return None

def get_contact_primary_company(contact_id: str, api_key: str) -> Optional[Dict]:
    """
    Get primary company for a contact using association typeId 1
    
    Args:
        contact_id: HubSpot contact ID
        api_key: HubSpot API key
    
    Returns:
        Dict with company_id and company details, or None if not found
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Get contact-company associations
    associations_url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/companies"
    
    try:
        response = requests.get(associations_url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            # Look for primary company (association typeId 1)
            for assoc in results:
                association_types = assoc.get('associationTypes', [])
                for assoc_type in association_types:
                    if assoc_type.get('typeId') == 1:  # Primary association
                        company_id = assoc.get('toObjectId')
                        # Get company details
                        company_details = get_company_details(company_id, api_key)
                        if company_details:
                            return {
                                'company_id': company_id,
                                'company_name': company_details.get('name'),
                                'company_type': company_details.get('type'),
                                'tipo_icp_contador': company_details.get('tipo_icp_contador'),
                                'method': 'primary_company_type1'
                            }
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 2))
            time.sleep(retry_after)
            return get_contact_primary_company(contact_id, api_key)
    except Exception as e:
        print(f"   ⚠️  Error fetching primary company for contact {contact_id}: {str(e)}")
    
    return None

def get_company_details(company_id: str, api_key: str) -> Optional[Dict]:
    """Get company details including name, type, and tipo_icp_contador (calculated ICP field)"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/{company_id}"
    params = {
        "properties": "name,type,tipo_icp_contador"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            props = data.get('properties', {})
            return {
                'name': props.get('name'),
                'type': props.get('type'),
                'tipo_icp_contador': props.get('tipo_icp_contador')
            }
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 2))
            time.sleep(retry_after)
            return get_company_details(company_id, api_key)
    except Exception as e:
        print(f"   ⚠️  Error fetching company {company_id}: {str(e)}")
    
    return None

def get_contact_deals(contact_id: str, api_key: str) -> List[Dict]:
    """Get all deals associated with a contact"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    associations_url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/deals"
    
    try:
        response = requests.get(associations_url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            return [{'deal_id': r.get('toObjectId')} for r in results]
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 2))
            time.sleep(retry_after)
            return get_contact_deals(contact_id, api_key)
    except Exception as e:
        print(f"   ⚠️  Error fetching deals for contact {contact_id}: {str(e)}")
    
    return []

def get_deal_primary_company(deal_id: str, api_key: str) -> Optional[Dict]:
    """
    Get primary company from deal using association typeId 5
    
    Args:
        deal_id: HubSpot deal ID
        api_key: HubSpot API key
    
    Returns:
        Dict with company_id and company details, or None if not found
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    associations_url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/companies"
    
    try:
        response = requests.get(associations_url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            # Look for primary company (association typeId 5)
            for assoc in results:
                association_types = assoc.get('associationTypes', [])
                for assoc_type in association_types:
                    if assoc_type.get('typeId') == 5:  # Primary association
                        company_id = assoc.get('toObjectId')
                        company_details = get_company_details(company_id, api_key)
                        if company_details:
                            return {
                                'company_id': company_id,
                                'company_name': company_details.get('name'),
                                'company_type': company_details.get('type'),
                                'tipo_icp_contador': company_details.get('tipo_icp_contador'),
                                'method': 'deal_primary_company_type5'
                            }
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 2))
            time.sleep(retry_after)
            return get_deal_primary_company(deal_id, api_key)
    except Exception as e:
        print(f"   ⚠️  Error fetching deal primary company for deal {deal_id}: {str(e)}")
    
    return None

def get_contact_all_companies(contact_id: str, api_key: str) -> List[Dict]:
    """
    Get all companies associated with a contact (any association type)
    
    Args:
        contact_id: HubSpot contact ID
        api_key: HubSpot API key
    
    Returns:
        List of company dicts with company_id and details
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    associations_url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/companies"
    
    companies = []
    try:
        response = requests.get(associations_url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            for assoc in results:
                company_id = assoc.get('toObjectId')
                company_details = get_company_details(company_id, api_key)
                if company_details:
                    companies.append({
                        'company_id': company_id,
                        'company_name': company_details.get('name'),
                        'company_type': company_details.get('type'),
                        'tipo_icp_contador': company_details.get('tipo_icp_contador'),
                        'method': 'any_associated_company'
                    })
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 2))
            time.sleep(retry_after)
            return get_contact_all_companies(contact_id, api_key)
    except Exception as e:
        print(f"   ⚠️  Error fetching all companies for contact {contact_id}: {str(e)}")
    
    return companies

def classify_icp_by_tipo_icp_contador(tipo_icp_contador: Optional[str], company_type: Optional[str] = None) -> str:
    """
    Classify ICP based on tipo_icp_contador calculated field (primary method)
    Falls back to company_type if tipo_icp_contador is empty
    
    Args:
        tipo_icp_contador: Calculated ICP field from HubSpot (Híbrido, Operador, Asesor, or empty)
        company_type: Company type field (fallback if tipo_icp_contador is empty)
    
    Returns:
        ICP classification string
    """
    # Primary method: Use tipo_icp_contador (calculated field)
    if tipo_icp_contador and str(tipo_icp_contador).strip():
        tipo_str = str(tipo_icp_contador).strip()
        if tipo_str in ["Híbrido", "Operador", "Asesor"]:
            return f"ICP Accountant - {tipo_str}"
    
    # Fallback: Use company_type if tipo_icp_contador is empty
    if company_type and not pd.isna(company_type):
        company_type_str = str(company_type).strip()
        
        # ICP Accountant (by type field)
        if company_type_str in ["Cuenta Contador", "Cuenta Contador y Reseller", "Contador Robado"]:
            return "ICP Accountant (type field)"
        
        # ICP SMB
        if company_type_str in ["Cuenta Pyme", "Empresa Administrada"]:
            return "ICP SMB"
        
        # ICP Partner
        if company_type_str in ["Alianza", "Integración Comercial", "Integración Tecnológica", "Reseller / Consultor"]:
            return "ICP Partner"
        
        # ICP Other
        if company_type_str in ["Proveedor", "Otra"]:
            return "ICP Other"
    
    return "Unknown"

class NPSICPDataQualityAnalyzer:
    """Analyze NPS data quality for ICP classification step by step"""
    
    def __init__(self, file_paths: List[str], output_dir: str = "tools/outputs/nps_icp_data_quality"):
        self.file_paths = file_paths
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.df_nps = None
        self.df_enriched = None
        self.api_key = get_hubspot_api_key()
        
        if not self.api_key:
            print("⚠️  Warning: HubSpot API key not found.")
            print("   Please set one of: HUBSPOT_API_KEY, HUBSPOT_ACCESS_TOKEN, HUBSPOT_TOKEN")
            print("   Or use: COLPPY_CRM_AUTOMATIONS, ColppyCRMAutomations")
            sys.exit(1)
    
    def load_nps_data(self):
        """Load and combine NPS data from multiple CSV files"""
        print("📊 Loading NPS data from Intercom...")
        
        dfs = []
        for file_path in self.file_paths:
            if not os.path.exists(file_path):
                print(f"⚠️  Warning: File not found: {file_path}")
                continue
            
            df = pd.read_csv(file_path)
            df['source_file'] = os.path.basename(file_path)
            dfs.append(df)
            print(f"   ✓ Loaded {len(df)} records from {os.path.basename(file_path)}")
        
        if not dfs:
            raise ValueError("No valid NPS files found")
        
        self.df_nps = pd.concat(dfs, ignore_index=True)
        print(f"\n✅ Total NPS records loaded: {len(self.df_nps):,}")
        
        # Standardize email column
        if 'email' in self.df_nps.columns:
            self.df_nps['email'] = self.df_nps['email'].astype(str).str.strip().str.lower()
        
        # Get unique emails
        unique_emails = self.df_nps['email'].dropna().unique()
        print(f"   Unique emails: {len(unique_emails):,}")
    
    def step1_primary_company_analysis(self):
        """
        Step 1: Try to get primary company (association typeId 1) for each contact
        Reports coverage statistics
        """
        print("\n" + "="*70)
        print("STEP 1: PRIMARY COMPANY ANALYSIS (Association TypeId 1)")
        print("="*70)
        
        unique_emails = self.df_nps['email'].dropna().unique()
        total_emails = len(unique_emails)
        
        print(f"\n🔍 Analyzing {total_emails:,} unique emails...")
        print(f"   Method: Contact → Primary Company (Association TypeId 1)")
        print(f"   ICP Field: tipo_icp_contador (calculated field: Híbrido/Operador/Asesor)")
        
        enrichment_data = []
        found_count = 0
        not_found_count = 0
        contact_not_found_count = 0
        
        for idx, email in enumerate(unique_emails, 1):
            if idx % 50 == 0:
                print(f"   Progress: {idx:,}/{total_emails:,} ({idx/total_emails*100:.1f}%)")
            
            # Get contact by email
            contact = get_contact_by_email(email, self.api_key)
            
            if not contact:
                enrichment_data.append({
                    'email': email,
                    'contact_id': None,
                    'contact_found': False,
                    'step1_company_id': None,
                    'step1_company_name': None,
                    'step1_company_type': None,
                    'step1_tipo_icp_contador': None,
                    'step1_icp_classification': None,
                    'step1_method': None,
                    'step1_success': False
                })
                contact_not_found_count += 1
                not_found_count += 1
                continue
            
            contact_id = contact.get('id')
            
            # Try to get primary company (typeId 1)
            primary_company = get_contact_primary_company(contact_id, self.api_key)
            
            if primary_company:
                icp_classification = classify_icp_by_tipo_icp_contador(
                    primary_company.get('tipo_icp_contador'),
                    primary_company.get('company_type')
                )
                enrichment_data.append({
                    'email': email,
                    'contact_id': contact_id,
                    'contact_found': True,
                    'step1_company_id': primary_company.get('company_id'),
                    'step1_company_name': primary_company.get('company_name'),
                    'step1_company_type': primary_company.get('company_type'),
                    'step1_tipo_icp_contador': primary_company.get('tipo_icp_contador'),
                    'step1_icp_classification': icp_classification,
                    'step1_method': primary_company.get('method'),
                    'step1_success': True
                })
                found_count += 1
            else:
                enrichment_data.append({
                    'email': email,
                    'contact_id': contact_id,
                    'contact_found': True,
                    'step1_company_id': None,
                    'step1_company_name': None,
                    'step1_company_type': None,
                    'step1_tipo_icp_contador': None,
                    'step1_icp_classification': None,
                    'step1_method': None,
                    'step1_success': False
                })
                not_found_count += 1
            
            # Rate limiting
            time.sleep(0.1)
        
        # Create DataFrame
        df_step1 = pd.DataFrame(enrichment_data)
        
        # Save to CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = self.output_dir / f"step1_primary_company_enrichment_{timestamp}.csv"
        df_step1.to_csv(csv_path, index=False)
        print(f"\n💾 Saved Step 1 enrichment data to: {csv_path}")
        
        # Report coverage statistics
        print("\n" + "-"*70)
        print("STEP 1 COVERAGE STATISTICS")
        print("-"*70)
        print(f"Total unique emails analyzed: {total_emails:,}")
        print(f"\nContact Lookup:")
        print(f"   ✓ Contacts found in HubSpot: {found_count + (not_found_count - contact_not_found_count):,} ({((found_count + (not_found_count - contact_not_found_count))/total_emails*100):.1f}%)")
        print(f"   ✗ Contacts not found in HubSpot: {contact_not_found_count:,} ({contact_not_found_count/total_emails*100:.1f}%)")
        print(f"\nPrimary Company (TypeId 1) Lookup:")
        print(f"   ✓ Primary company found: {found_count:,} ({found_count/total_emails*100:.1f}%)")
        print(f"   ✗ Primary company not found: {not_found_count:,} ({not_found_count/total_emails*100:.1f}%)")
        
        # ICP Classification breakdown
        if found_count > 0:
            icp_breakdown = df_step1[df_step1['step1_success'] == True]['step1_icp_classification'].value_counts()
            print(f"\nICP Classification (from {found_count:,} contacts with primary company):")
            for icp_type, count in icp_breakdown.items():
                print(f"   • {icp_type}: {count:,} ({count/found_count*100:.1f}%)")
            
            # Show tipo_icp_contador breakdown
            tipo_icp_breakdown = df_step1[df_step1['step1_success'] == True]['step1_tipo_icp_contador'].value_counts(dropna=False)
            print(f"\ntipo_icp_contador breakdown (calculated field):")
            for tipo_icp, count in tipo_icp_breakdown.items():
                tipo_display = tipo_icp if pd.notna(tipo_icp) and str(tipo_icp).strip() else "Empty/Not Accountant"
                print(f"   • {tipo_display}: {count:,} ({count/found_count*100:.1f}%)")
        
        print(f"\n📊 Step 1 Coverage: {found_count/total_emails*100:.1f}%")
        print(f"📊 Remaining to process: {not_found_count:,} contacts")
        
        return df_step1
    
    def run_analysis(self):
        """Run the complete step-by-step analysis"""
        self.load_nps_data()
        
        # Step 1: Primary Company Analysis
        df_step1 = self.step1_primary_company_analysis()
        
        print("\n" + "="*70)
        print("✅ STEP 1 ANALYSIS COMPLETE")
        print("="*70)
        print("\nNext steps:")
        print("   1. Review Step 1 coverage statistics above")
        print("   2. If coverage is acceptable, proceed to Step 2 (Deal Primary Company)")
        print("   3. Then Step 3 (Any Associated Company)")
        print("   4. Finally Step 4 (Final Classification)")
        print(f"\n💾 Step 1 data saved to: {self.output_dir}")

def main():
    parser = argparse.ArgumentParser(
        description="Analyze NPS data quality for ICP classification step by step"
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--files', nargs='+', help='Multiple NPS CSV files to process')
    group.add_argument('--file', help='Single NPS CSV file to process (backward compatibility)')
    
    parser.add_argument('--output-dir', default='tools/outputs/nps_icp_data_quality',
                       help='Output directory for results (default: tools/outputs/nps_icp_data_quality)')
    
    args = parser.parse_args()
    
    # Handle both --file and --files arguments
    file_paths = args.files if args.files else [args.file]
    
    analyzer = NPSICPDataQualityAnalyzer(file_paths, args.output_dir)
    analyzer.run_analysis()

if __name__ == "__main__":
    main()

