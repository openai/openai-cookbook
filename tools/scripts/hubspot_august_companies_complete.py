#!/usr/bin/env python3
"""
Complete HubSpot August 2025 Companies Retrieval with Pagination
Retrieves ALL companies created in August 2025 using proper pagination
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

def fetch_all_companies_august_2025(token: str) -> List[Dict]:
    """Fetch ALL companies created in August 2025 with proper pagination"""
    
    url = "https://api.hubapi.com/crm/v3/objects/companies/search"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Search payload for August 2025
    search_payload = {
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
            "name",
            "domain", 
            "industry",
            "createdate",
            "lifecyclestage",
            "num_associated_deals",
            "hs_analytics_source",
            "hs_analytics_source_data_1",
            "hs_analytics_source_data_2",
            "city",
            "state",
            "country",
            "phone",
            "website",
            "description",
            "annualrevenue",
            "numberofemployees"
        ],
        "limit": 100
    }
    
    all_companies = []
    after = None
    page = 1
    
    print(f"🔍 Starting companies retrieval for August 2025...")
    
    while True:
        if after:
            search_payload["after"] = after
            
        print(f"📄 Fetching page {page}...")
        
        try:
            response = requests.post(url, headers=headers, json=search_payload)
            response.raise_for_status()
            
            data = response.json()
            companies = data.get("results", [])
            
            if not companies:
                print(f"✅ No more companies found. Total retrieved: {len(all_companies)}")
                break
                
            all_companies.extend(companies)
            print(f"   📊 Retrieved {len(companies)} companies (Total: {len(all_companies)})")
            
            # Check for pagination
            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            
            if not after:
                print(f"✅ All companies retrieved. Total: {len(all_companies)}")
                break
                
            page += 1
            time.sleep(0.1)  # Rate limiting
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching companies: {e}")
            break
    
    return all_companies

def analyze_companies(companies: List[Dict]) -> Dict[str, Any]:
    """Analyze the companies data"""
    
    analysis = {
        "total_companies": len(companies),
        "with_domain": 0,
        "with_industry": 0,
        "with_deals": 0,
        "with_revenue": 0,
        "with_employees": 0,
        "lifecycle_stages": {},
        "industries": {},
        "sources": {},
        "countries": {},
        "states": {},
        "cities": {},
        "revenue_ranges": {},
        "employee_ranges": {}
    }
    
    for company in companies:
        props = company.get("properties", {})
        
        # Basic stats
        if props.get("domain"):
            analysis["with_domain"] += 1
            
        if props.get("industry"):
            analysis["with_industry"] += 1
            
        # Deals
        num_deals = props.get("num_associated_deals", "0")
        if num_deals and int(num_deals) > 0:
            analysis["with_deals"] += 1
            
        # Revenue
        if props.get("annualrevenue"):
            analysis["with_revenue"] += 1
            
        # Employees
        if props.get("numberofemployees"):
            analysis["with_employees"] += 1
            
        # Lifecycle stages
        stage = props.get("lifecyclestage", "Unknown")
        analysis["lifecycle_stages"][stage] = analysis["lifecycle_stages"].get(stage, 0) + 1
        
        # Industries
        industry = props.get("industry", "Unknown")
        analysis["industries"][industry] = analysis["industries"].get(industry, 0) + 1
        
        # Sources
        source = props.get("hs_analytics_source", "Unknown")
        analysis["sources"][source] = analysis["sources"].get(source, 0) + 1
        
        # Geography
        country = props.get("country", "Unknown")
        analysis["countries"][country] = analysis["countries"].get(country, 0) + 1
        
        state = props.get("state", "Unknown")
        analysis["states"][state] = analysis["states"].get(state, 0) + 1
        
        city = props.get("city", "Unknown")
        analysis["cities"][city] = analysis["cities"].get(city, 0) + 1
        
        # Revenue ranges
        revenue = props.get("annualrevenue")
        if revenue:
            try:
                rev_num = float(revenue)
                if rev_num < 1000000:
                    range_key = "< $1M"
                elif rev_num < 10000000:
                    range_key = "$1M - $10M"
                elif rev_num < 50000000:
                    range_key = "$10M - $50M"
                else:
                    range_key = "> $50M"
                analysis["revenue_ranges"][range_key] = analysis["revenue_ranges"].get(range_key, 0) + 1
            except:
                pass
                
        # Employee ranges
        employees = props.get("numberofemployees")
        if employees:
            try:
                emp_num = int(employees)
                if emp_num < 10:
                    range_key = "< 10"
                elif emp_num < 50:
                    range_key = "10-49"
                elif emp_num < 200:
                    range_key = "50-199"
                elif emp_num < 1000:
                    range_key = "200-999"
                else:
                    range_key = "> 1000"
                analysis["employee_ranges"][range_key] = analysis["employee_ranges"].get(range_key, 0) + 1
            except:
                pass
    
    return analysis

def print_analysis(analysis: Dict[str, Any]):
    """Print the analysis results"""
    
    print(f"\n📊 COMPANIES ANALYSIS RESULTS")
    print("=" * 50)
    
    print(f"\n📈 SUMMARY STATISTICS")
    print("-" * 30)
    print(f"Total Companies: {analysis['total_companies']:,}")
    print(f"With Domain: {analysis['with_domain']:,} ({analysis['with_domain']/analysis['total_companies']*100:.1f}%)")
    print(f"With Industry: {analysis['with_industry']:,} ({analysis['with_industry']/analysis['total_companies']*100:.1f}%)")
    print(f"With Deals: {analysis['with_deals']:,} ({analysis['with_deals']/analysis['total_companies']*100:.1f}%)")
    print(f"With Revenue: {analysis['with_revenue']:,} ({analysis['with_revenue']/analysis['total_companies']*100:.1f}%)")
    print(f"With Employees: {analysis['with_employees']:,} ({analysis['with_employees']/analysis['total_companies']*100:.1f}%)")
    
    if analysis['lifecycle_stages']:
        print(f"\n🔄 LIFECYCLE STAGES")
        print("-" * 30)
        for stage, count in sorted(analysis['lifecycle_stages'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {stage}: {count:,}")
    
    if analysis['industries']:
        print(f"\n🏭 TOP INDUSTRIES")
        print("-" * 30)
        for industry, count in sorted(analysis['industries'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {industry}: {count:,}")
    
    if analysis['sources']:
        print(f"\n📡 TRAFFIC SOURCES")
        print("-" * 30)
        for source, count in sorted(analysis['sources'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {source}: {count:,}")
    
    if analysis['countries']:
        print(f"\n🌍 COUNTRIES")
        print("-" * 30)
        for country, count in sorted(analysis['countries'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {country}: {count:,}")
    
    if analysis['states']:
        print(f"\n🗺️ STATES/PROVINCES")
        print("-" * 30)
        for state, count in sorted(analysis['states'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {state}: {count:,}")
    
    if analysis['cities']:
        print(f"\n🏙️ TOP CITIES")
        print("-" * 30)
        for city, count in sorted(analysis['cities'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {city}: {count:,}")
    
    if analysis['revenue_ranges']:
        print(f"\n💰 REVENUE RANGES")
        print("-" * 30)
        for range_key, count in sorted(analysis['revenue_ranges'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {range_key}: {count:,}")
    
    if analysis['employee_ranges']:
        print(f"\n👥 EMPLOYEE RANGES")
        print("-" * 30)
        for range_key, count in sorted(analysis['employee_ranges'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {range_key}: {count:,}")

def main():
    """Main function"""
    try:
        # Get token
        token = get_hubspot_token()
        
        # Fetch all companies
        companies = fetch_all_companies_august_2025(token)
        
        if not companies:
            print("❌ No companies found for August 2025")
            return
            
        # Analyze data
        analysis = analyze_companies(companies)
        
        # Print analysis
        print_analysis(analysis)
        
        # Save raw data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"hubspot_august_2025_companies_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(companies, f, indent=2, ensure_ascii=False)
            
        print(f"\n💾 Raw data saved to: {filename}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
