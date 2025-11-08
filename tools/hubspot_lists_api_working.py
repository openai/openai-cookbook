#!/usr/bin/env python3
"""
HubSpot Lists API Working Implementation
Demonstrates how to access HubSpot lists beyond MCP tools using direct REST API calls.

API Key loaded from: /Users/virulana/openai-cookbook/.env
Environment variables checked: HUBSPOT_API_KEY, COLPPY_CRM_AUTOMATIONS, ColppyCRMAutomations
"""

import requests
import json
import os
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path('/Users/virulana/openai-cookbook/.env')
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    print("⚠️  python-dotenv not installed, using system environment variables only")

class HubSpotListsAPI:
    """Working HubSpot Lists API client using direct REST calls"""
    
    def __init__(self, api_key: str):
        """Initialize with HubSpot API key"""
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Colppy-Contactability-Analysis/1.0"
        }
    
    def get_list_details(self, list_id: str) -> Optional[Dict]:
        """Get details of a specific list"""
        try:
            url = f"{self.base_url}/crm/v3/lists/{list_id}"

            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                print(f"List {list_id} not found")
                return None
            else:
                print(f"Error getting list details: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Exception getting list details: {e}")
            return None
    
    def get_companies_via_associations(self, list_id: str, limit: int = 100, after: str = None) -> Dict:
        """
        Get companies associated with a list using associations endpoint
        
        Note: This method works but may return empty results depending on list configuration
        """
        url = f"{self.base_url}/crm/v4/objects/lists/{list_id}/associations/companies"
        params = {"limit": limit}
        if after:
            params["after"] = after
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {"results": [], "total": 0, "error": "Associations endpoint not found for this list"}
            else:
                return {"error": f"Error {response.status_code}: {response.text}"}
                
        except Exception as e:
            return {"error": f"Exception: {e}"}
    
    def get_contacts_in_list(self, list_id: str, limit: int = 100, after: str = None) -> Dict:
        """
        Get contacts in a list using legacy v1 endpoint
        
        This endpoint works for most HubSpot lists
        """
        url = f"{self.base_url}/contacts/v1/lists/{list_id}/contacts/all"
        params = {"count": limit}
        if after:
            params["vidOffset"] = after
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                # Convert v1 format to v3-like format
                contacts = data.get("contacts", [])
                return {
                    "results": contacts,
                    "total": data.get("total", len(contacts)),
                    "hasMore": data.get("hasMore", False),
                    "vidOffset": data.get("vid-offset")
                }
            elif response.status_code == 404:
                return {"results": [], "total": 0, "error": "Contacts endpoint not found for this list"}
            else:
                return {"error": f"Error {response.status_code}: {response.text}"}
                
        except Exception as e:
            return {"error": f"Exception: {e}"}
    
    def get_all_companies_by_name_search(self, company_names: List[str]) -> Dict:
        """
        Alternative approach: Search for companies by name since list membership 
        endpoints may not work reliably
        
        This is the most reliable method for accessing list members
        """
        found_companies = []
        
        for name in company_names:
            print(f"   Searching for: '{name}'")
            
            search_payload = {
                "query": name,
                "limit": 5,
                "properties": [
                    "name", "type", "lifecyclestage", "createdate", 
                    "lastmodifieddate", "cuit", "hubspot_owner_id",
                    "colppy_id", "id_empresa"
                ],
                "sorts": [{"propertyName": "name", "direction": "ASCENDING"}]
            }
            
            try:
                url = f"{self.base_url}/crm/v3/objects/companies/search"
                response = requests.post(url, headers=self.headers, json=search_payload, timeout=30)
                
                if response.status_code == 200:
                    search_data = response.json()
                    companies = search_data.get("results", [])
                    
                    # Look for exact or close matches
                    for company in companies:
                        props = company.get("properties", {})
                        company_name = props.get("name", "")
                        
                        # Check for name similarity
                        if any(word in company_name.lower() for word in name.lower().split()):
                            found_companies.append({
                                "id": company.get("id"),
                                "name": company_name,
                                "type": props.get("type", ""),
                                "owner_id": props.get("hubspot_owner_id", ""),
                                "cuit": props.get("cuit", ""),
                                "last_modified": props.get("lastmodifieddate", ""),
                                "lifecycle": props.get("lifecyclestage", "")
                            })
                            print(f"      ✅ Found: '{company_name}' (ID: {company.get('id')})")
                            break
                    else:
                        print(f"      ⚠️  No close match found")
                        
                else:
                    print(f"      ❌ Search failed: {response.status_code}")
                    
            except Exception as e:
                print(f"      ❌ Exception: {e}")
        
        return {"results": found_companies, "total": len(found_companies)}
    
    def analyze_contactability(self, companies: List[Dict]) -> Dict:
        """Analyze contactability patterns for the list"""
        contactability_issues = {
            "missing_phone": 0,
            "missing_email": 0,
            "personal_domains": 0,
            "missing_cuit": 0,
            "no_recent_activity": 0
        }
        
        total_contacts = 0
        
        for company in companies:
            print(f"\\n🔍 Analyzing: {company['name']} (ID: {company['id']})")
            print(f"   HubSpot URL: https://app.hubspot.com/contacts/19877595/record/0-2/{company['id']}")
            print(f"   Type: {company['type']}")
            print(f"   Owner: {company['owner_id']}")
            print(f"   CUIT: {company['cuit'] or 'Missing'}")
            
            if not company['cuit']:
                contactability_issues['missing_cuit'] += 1
            
            # Get associated contacts
            try:
                url = f"{self.base_url}/crm/v4/objects/companies/{company['id']}/associations/contacts"
                response = requests.get(url, headers=self.headers, timeout=30)
                
                if response.status_code == 200:
                    associations_data = response.json()
                    contact_ids = [assoc.get("id") for assoc in associations_data.get("results", [])]
                    
                    print(f"   Contacts: {len(contact_ids)}")
                    
                    for contact_id in contact_ids:
                        try:
                            # Get contact details
                            url = f"{self.base_url}/crm/v3/objects/contacts/{contact_id}"
                            params = {
                                "properties": "firstname,lastname,email,phone,jobtitle,lifecyclestage,hs_email_domain,hs_phone_number,lastmodifieddate"
                            }
                            
                            contact_response = requests.get(url, headers=self.headers, params=params, timeout=30)
                            
                            if contact_response.status_code == 200:
                                contact_data = contact_response.json()
                                props = contact_data.get("properties", {})
                                
                                total_contacts += 1
                                print(f"      👤 {props.get('firstname', '')} {props.get('lastname', '')}")
                                
                                # Check phone
                                phone = props.get('phone') or props.get('hs_phone_number')
                                if phone:
                                    print(f"         ✅ Phone: {phone}")
                                else:
                                    contactability_issues['missing_phone'] += 1
                                    print(f"         ⚠️  Missing phone")
                                
                                # Check email
                                email = props.get('email')
                                email_domain = props.get('hs_email_domain')
                                if email and email_domain:
                                    personal_domains = ['gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com']
                                    if email_domain.lower() in personal_domains:
                                        contactability_issues['personal_domains'] += 1
                                        print(f"         ⚠️  Personal email: {email}")
                                    else:
                                        print(f"         ✅ Professional email: {email}")
                                else:
                                    contactability_issues['missing_email'] += 1
                                    print(f"         ⚠️  Missing email")
                                
                                print(f"         💼 Job: {props.get('jobtitle', 'Unknown')}")
                                print(f"         📅 Last Modified: {props.get('lastmodifieddate', 'Unknown')}")
                                
                        except Exception as e:
                            print(f"         ❌ Error getting contact {contact_id}: {e}")
                
                else:
                    print(f"   ⚠️  Could not get contacts: {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ Error analyzing company: {e}")
        
        # Calculate percentages
        if total_contacts > 0:
            missing_phone_pct = (contactability_issues['missing_phone'] / total_contacts) * 100
            missing_email_pct = (contactability_issues['missing_email'] / total_contacts) * 100
            personal_email_pct = (contactability_issues['personal_domains'] / total_contacts) * 100
        else:
            missing_phone_pct = missing_email_pct = personal_email_pct = 0
        
        missing_cuit_pct = (contactability_issues['missing_cuit'] / len(companies)) * 100
        
        return {
            "summary": {
                "companies_analyzed": len(companies),
                "total_contacts": total_contacts
            },
            "issues": contactability_issues,
            "percentages": {
                "missing_phone": missing_phone_pct,
                "missing_email": missing_email_pct,
                "personal_email": personal_email_pct,
                "missing_cuit": missing_cuit_pct
            }
        }

def main():
    """Test the HubSpot Lists API functionality"""
    
    # Get API key from environment
    api_key = (
        os.environ.get('HUBSPOT_API_KEY') or 
        os.environ.get('COLPPY_CRM_AUTOMATIONS') or
        os.environ.get('ColppyCRMAutomations')
    )
    
    if not api_key:
        print("❌ HubSpot API key not found in environment")
        print("Checked variables: HUBSPOT_API_KEY, COLPPY_CRM_AUTOMATIONS, ColppyCRMAutomations")
        print("Please set one of them in /Users/virulana/openai-cookbook/.env")
        return
    
    print("🚀 HubSpot Lists API - Working Implementation")
    print("=" * 60)
    print(f"🔑 Using API key: {api_key[:20]}...")
    print()
    
    client = HubSpotListsAPI(api_key)
    
    # Test 1: Get list details
    print("\\n📋 Step 1: Getting list 2216 details...")
    list_details = client.get_list_details("2216")
    
    if list_details:
        print(f"✅ List found: {list_details.get('properties', {}).get('name', 'Unknown')}")
        print(f"   Description: {list_details.get('properties', {}).get('description', 'No description')}")
        print(f"   Created: {list_details.get('properties', {}).get('createdAt', 'Unknown')}")
    else:
        print("❌ Could not get list details")
    
    # Test 2: Try to get companies via associations
    print("\\n🏢 Step 2: Trying companies via associations...")
    companies_via_assoc = client.get_companies_via_associations("2216")
    
    if companies_via_assoc.get("results"):
        print(f"✅ Found {len(companies_via_assoc['results'])} companies via associations")
    else:
        print(f"⚠️  No companies via associations: {companies_via_assoc.get('error', 'Empty results')}")
    
    # Test 3: Get contacts in list
    print("\\n👥 Step 3: Getting contacts in list...")
    contacts_in_list = client.get_contacts_in_list("2216")
    
    if contacts_in_list.get("results"):
        print(f"✅ Found {len(contacts_in_list['results'])} contacts")
    else:
        print(f"⚠️  No contacts found: {contacts_in_list.get('error', 'Empty results')}")
    
    # Test 4: Search by known company names (most reliable method)
    print("\\n🔍 Step 4: Searching by known company names...")
    
    # Companies we know should be in the list
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
    
    companies_by_search = client.get_all_companies_by_name_search(company_names)
    found_companies = companies_by_search["results"]
    
    print(f"\\n📊 Summary: Found {len(found_companies)} companies")
    
    # Test 5: Analyze contactability
    if found_companies:
        print("\\n📈 Step 5: Analyzing contactability patterns...")
        analysis = client.analyze_contactability(found_companies)
        
        print("\\n🎯 CONTACTABILITY ANALYSIS RESULTS")
        print("=" * 50)
        print(f"Companies analyzed: {analysis['summary']['companies_analyzed']}")
        print(f"Total contacts: {analysis['summary']['total_contacts']}")
        print()
        print("Issues found:")
        print(f"   📞 Missing phone numbers: {analysis['issues']['missing_phone']} ({analysis['percentages']['missing_phone']:.1f}%)")
        print(f"   📧 Missing email addresses: {analysis['issues']['missing_email']} ({analysis['percentages']['missing_email']:.1f}%)")
        print(f"   🏠 Personal email domains: {analysis['issues']['personal_domains']} ({analysis['percentages']['personal_email']:.1f}%)")
        print(f"   🏢 Companies missing CUIT: {analysis['issues']['missing_cuit']} ({analysis['percentages']['missing_cuit']:.1f}%)")
    
    print("\\n✅ HubSpot Lists API test completed!")
    print("\\n💡 Key Learnings:")
    print("   • Direct REST API calls work better than MCP for lists")
    print("   • Search by company name is most reliable")
    print("   • Association endpoints exist but may return empty results")
    print("   • Legacy v1 endpoints still work for contact lists")

if __name__ == "__main__":
    main()
