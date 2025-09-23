#!/usr/bin/env python3
"""
Complete HubSpot August 2025 Contacts Retrieval with Pagination
Retrieves ALL contacts created in August 2025 using proper pagination
"""

import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Any
import time

def get_hubspot_token() -> str:
    """Get HubSpot token from environment"""
    token = os.environ.get('HUBSPOT_API_KEY')
    if not token:
        raise ValueError("HUBSPOT_API_KEY environment variable not set")
    return token

def fetch_all_contacts_august_2025(token: str) -> List[Dict]:
    """Fetch ALL contacts created in August 2025 with proper pagination"""
    
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Search criteria for August 2025
    search_criteria = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "createdate",
                        "operator": "GTE",
                        "value": "2025-08-01T00:00:00.000Z"
                    },
                    {
                        "propertyName": "createdate", 
                        "operator": "LTE",
                        "value": "2025-08-31T23:59:59.999Z"
                    }
                ]
            }
        ],
        "properties": [
            "email",
            "firstname", 
            "lastname",
            "company",
            "lifecyclestage",
            "createdate",
            "utm_campaign",
            "utm_source", 
            "utm_medium",
            "utm_term",
            "utm_content",
            "activo",
            "fecha_activo",
            "num_associated_deals",
            "hs_lead_status",
            "hs_analytics_source",
            "hs_analytics_source_data_1",
            "hs_analytics_source_data_2"
        ],
        "limit": 100  # Maximum per page
    }
    
    all_contacts = []
    after = None
    page_count = 0
    
    print("Starting HubSpot contacts retrieval for August 2025...")
    print("=" * 60)
    
    while True:
        page_count += 1
        print(f"Fetching page {page_count}...")
        
        # Add pagination token if we have one
        if after:
            search_criteria["after"] = after
            
        try:
            response = requests.post(url, headers=headers, json=search_criteria)
            response.raise_for_status()
            
            data = response.json()
            contacts = data.get("results", [])
            
            if not contacts:
                print(f"No more contacts found on page {page_count}")
                break
                
            all_contacts.extend(contacts)
            print(f"  Retrieved {len(contacts)} contacts (Total: {len(all_contacts)})")
            
            # Check for next page
            paging = data.get("paging", {})
            next_page = paging.get("next")
            
            if not next_page:
                print("No more pages available")
                break
                
            after = next_page.get("after")
            if not after:
                print("No pagination token for next page")
                break
                
            # Remove after from search criteria for next iteration
            if "after" in search_criteria:
                del search_criteria["after"]
                
            # Rate limiting - HubSpot allows 100 requests per 10 seconds
            time.sleep(0.1)
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page_count}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response text: {e.response.text}")
            break
        except Exception as e:
            print(f"Unexpected error on page {page_count}: {e}")
            break
    
    print("=" * 60)
    print(f"Retrieval complete! Total contacts found: {len(all_contacts)}")
    return all_contacts

def analyze_contacts(contacts: List[Dict]) -> Dict[str, Any]:
    """Analyze the retrieved contacts"""
    
    analysis = {
        "total_contacts": len(contacts),
        "by_lifecycle_stage": {},
        "by_source": {},
        "utm_campaigns": {},
        "utm_sources": {},
        "utm_mediums": {},
        "utm_terms": {},
        "active_users": 0,
        "with_deals": 0,
        "by_day": {},
        "top_companies": {},
        "contacts_with_email": 0,
        "contacts_with_company": 0
    }
    
    for contact in contacts:
        props = contact.get("properties", {})
        
        # Basic counts
        if props.get("email"):
            analysis["contacts_with_email"] += 1
        if props.get("company"):
            analysis["contacts_with_company"] += 1
            
        # Lifecycle stage
        lifecycle = props.get("lifecyclestage", "unknown")
        analysis["by_lifecycle_stage"][lifecycle] = analysis["by_lifecycle_stage"].get(lifecycle, 0) + 1
        
        # Source analysis
        source = props.get("hs_analytics_source", "unknown")
        analysis["by_source"][source] = analysis["by_source"].get(source, 0) + 1
        
        # UTM analysis
        utm_campaign = props.get("utm_campaign", "")
        if utm_campaign:
            analysis["utm_campaigns"][utm_campaign] = analysis["utm_campaigns"].get(utm_campaign, 0) + 1
            
        utm_source = props.get("utm_source", "")
        if utm_source:
            analysis["utm_sources"][utm_source] = analysis["utm_sources"].get(utm_source, 0) + 1
            
        utm_medium = props.get("utm_medium", "")
        if utm_medium:
            analysis["utm_mediums"][utm_medium] = analysis["utm_mediums"].get(utm_medium, 0) + 1
            
        utm_term = props.get("utm_term", "")
        if utm_term:
            analysis["utm_terms"][utm_term] = analysis["utm_terms"].get(utm_term, 0) + 1
        
        # Active users
        if props.get("activo") == "true":
            analysis["active_users"] += 1
            
        # Users with deals
        num_deals = props.get("num_associated_deals", "0")
        if num_deals and int(num_deals) > 0:
            analysis["with_deals"] += 1
            
        # Company analysis
        company = props.get("company", "")
        if company:
            analysis["top_companies"][company] = analysis["top_companies"].get(company, 0) + 1
            
        # Daily breakdown
        created_date = contact.get("createdAt", "")
        if created_date:
            day = created_date[:10]  # Extract YYYY-MM-DD
            analysis["by_day"][day] = analysis["by_day"].get(day, 0) + 1
    
    return analysis

def print_analysis(analysis: Dict[str, Any]):
    """Print the analysis results"""
    
    print("\n" + "=" * 80)
    print("HUBSPOT AUGUST 2025 CONTACTS ANALYSIS")
    print("=" * 80)
    
    print(f"\n📊 SUMMARY")
    print("-" * 40)
    print(f"Total Contacts: {analysis['total_contacts']:,}")
    print(f"Contacts with Email: {analysis['contacts_with_email']:,}")
    print(f"Contacts with Company: {analysis['contacts_with_company']:,}")
    print(f"Active Users: {analysis['active_users']:,}")
    print(f"Contacts with Deals: {analysis['with_deals']:,}")
    
    if analysis['total_contacts'] > 0:
        email_rate = (analysis['contacts_with_email'] / analysis['total_contacts']) * 100
        company_rate = (analysis['contacts_with_company'] / analysis['total_contacts']) * 100
        active_rate = (analysis['active_users'] / analysis['total_contacts']) * 100
        deal_rate = (analysis['with_deals'] / analysis['total_contacts']) * 100
        
        print(f"\n📈 CONVERSION RATES")
        print("-" * 40)
        print(f"Email Capture Rate: {email_rate:.1f}%")
        print(f"Company Association Rate: {company_rate:.1f}%")
        print(f"Active User Rate: {active_rate:.1f}%")
        print(f"Contact-to-Deal Rate: {deal_rate:.1f}%")
    
    print(f"\n🔄 LIFECYCLE STAGE DISTRIBUTION")
    print("-" * 40)
    for stage, count in sorted(analysis['by_lifecycle_stage'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / analysis['total_contacts']) * 100
        print(f"  {stage}: {count:,} ({percentage:.1f}%)")
    
    print(f"\n🌐 TRAFFIC SOURCE DISTRIBUTION")
    print("-" * 40)
    for source, count in sorted(analysis['by_source'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / analysis['total_contacts']) * 100
        print(f"  {source}: {count:,} ({percentage:.1f}%)")
    
    if analysis['utm_campaigns']:
        print(f"\n📢 TOP UTM CAMPAIGNS")
        print("-" * 40)
        for campaign, count in sorted(analysis['utm_campaigns'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {campaign}: {count:,}")
    
    if analysis['utm_sources']:
        print(f"\n🔗 TOP UTM SOURCES")
        print("-" * 40)
        for source, count in sorted(analysis['utm_sources'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {source}: {count:,}")
    
    if analysis['utm_terms']:
        print(f"\n🏷️ TOP UTM TERMS")
        print("-" * 40)
        for term, count in sorted(analysis['utm_terms'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {term}: {count:,}")
    
    print(f"\n📅 DAILY BREAKDOWN")
    print("-" * 40)
    for day, count in sorted(analysis['by_day'].items())[:15]:
        print(f"  {day}: {count:,} contacts")
    
    print("\n" + "=" * 80)

def save_data(contacts: List[Dict], analysis: Dict[str, Any], output_file: str):
    """Save the data to a JSON file"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{output_file}_{timestamp}.json"
    
    data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_contacts": len(contacts),
            "date_range": "2025-08-01 to 2025-08-31"
        },
        "contacts": contacts,
        "analysis": analysis
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n💾 Data saved to: {filename}")
    return filename

def main():
    """Main function"""
    try:
        # Get HubSpot token
        token = get_hubspot_token()
        
        # Fetch all contacts
        contacts = fetch_all_contacts_august_2025(token)
        
        if not contacts:
            print("No contacts found for August 2025")
            return
        
        # Analyze contacts
        analysis = analyze_contacts(contacts)
        
        # Print analysis
        print_analysis(analysis)
        
        # Save data
        output_file = "hubspot_august_2025_contacts"
        save_data(contacts, analysis, output_file)
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
