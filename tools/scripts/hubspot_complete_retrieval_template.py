#!/usr/bin/env python3
"""
HubSpot Complete Data Retrieval Template
Template for retrieving ALL records from HubSpot with proper pagination

Usage:
    python hubspot_complete_retrieval_template.py --object-type contacts --start-date 2025-08-01 --end-date 2025-08-31
    python hubspot_complete_retrieval_template.py --object-type deals --start-date 2025-08-01 --end-date 2025-08-31
    python hubspot_complete_retrieval_template.py --object-type companies --start-date 2025-08-01 --end-date 2025-08-31
"""

import os
import json
import argparse
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
import time

def get_hubspot_token() -> str:
    """Get HubSpot token from environment"""
    token = os.environ.get('HUBSPOT_API_KEY')
    if not token:
        raise ValueError("HUBSPOT_API_KEY environment variable not set")
    return token

def fetch_all_hubspot_records(
    object_type: str, 
    access_token: str,
    filters: Optional[List[Dict]] = None,
    properties: Optional[List[str]] = None,
    associations: Optional[List[str]] = None
) -> List[Dict]:
    """
    Fetch ALL records from HubSpot with complete pagination
    
    Args:
        object_type: Type of object to retrieve (contacts, deals, companies)
        access_token: HubSpot API access token
        filters: List of filter groups for the search
        properties: List of properties to retrieve
        associations: List of associations to include
    
    Returns:
        List of all records retrieved with complete pagination
    """
    
    url = f"https://api.hubapi.com/crm/v3/objects/{object_type}/search"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Default properties if none specified
    if not properties:
        properties = get_default_properties(object_type)
    
    # Search payload
    search_payload = {
        "limit": 100,  # Maximum allowed by API
        "properties": properties
    }
    
    if filters:
        search_payload["filterGroups"] = filters
        
    if associations:
        search_payload["associations"] = associations
    
    all_records = []
    after_cursor = None
    page = 1
    
    print(f"🔍 Starting {object_type} retrieval with complete pagination...")
    print(f"📋 Properties: {len(properties)} fields")
    if filters:
        print(f"🔍 Filters: {len(filters)} filter groups")
    
    while True:
        if after_cursor:
            search_payload["after"] = after_cursor
            
        print(f"📄 Fetching page {page}...")
        
        try:
            response = requests.post(url, headers=headers, json=search_payload)
            response.raise_for_status()
            
            data = response.json()
            records = data.get("results", [])
            
            if not records:
                print(f"✅ No more records found. Total retrieved: {len(all_records)}")
                break
                
            all_records.extend(records)
            print(f"   📊 Retrieved {len(records)} records (Total: {len(all_records)})")
            
            # Check for pagination
            paging = data.get("paging", {})
            after_cursor = paging.get("next", {}).get("after")
            
            if not after_cursor:
                print(f"✅ All records retrieved. Total: {len(all_records)}")
                break
                
            page += 1
            time.sleep(0.1)  # Rate limiting
            
        except requests.RequestException as e:
            print(f"❌ Error fetching records: {e}")
            break
    
    return all_records

def get_default_properties(object_type: str) -> List[str]:
    """Get default properties for each object type"""
    
    if object_type == "contacts":
        return [
            "email", "firstname", "lastname", "company", "lifecyclestage",
            "createdate", "utm_campaign", "utm_source", "utm_medium", 
            "utm_term", "utm_content", "activo", "fecha_activo",
            "num_associated_deals", "hs_lead_status", "hs_analytics_source",
            "hs_analytics_source_data_1", "hs_analytics_source_data_2"
        ]
    elif object_type == "deals":
        return [
            "dealname", "dealstage", "amount", "closedate", "createdate",
            "pipeline", "dealtype", "hs_analytics_source", "description",
            "hubspot_owner_id", "hs_deal_stage_probability", "hs_forecast_probability",
            "hs_forecast_category", "hs_next_step", "hs_notes_last_contacted"
        ]
    elif object_type == "companies":
        return [
            "name", "domain", "industry", "createdate", "lifecyclestage",
            "num_associated_deals", "hs_analytics_source", "city", "state",
            "country", "phone", "website", "description", "annualrevenue",
            "numberofemployees", "type", "hs_analytics_source_data_1",
            "hs_analytics_source_data_2"
        ]
    else:
        return ["createdate", "hs_analytics_source"]

def create_date_filters(start_date: str, end_date: str) -> List[Dict]:
    """Create date filters for HubSpot search"""
    return [{
        "filters": [
            {
                "propertyName": "createdate",
                "operator": "GTE", 
                "value": f"{start_date}T00:00:00.000Z"
            },
            {
                "propertyName": "createdate",
                "operator": "LTE",
                "value": f"{end_date}T23:59:59.999Z"
            }
        ]
    }]

def analyze_records(records: List[Dict], object_type: str) -> Dict[str, Any]:
    """Basic analysis of retrieved records"""
    
    analysis = {
        "total_records": len(records),
        "object_type": object_type,
        "analysis_timestamp": datetime.now().isoformat()
    }
    
    if not records:
        return analysis
    
    # Basic stats
    analysis["with_email"] = sum(1 for r in records if r.get("properties", {}).get("email"))
    analysis["with_company"] = sum(1 for r in records if r.get("properties", {}).get("company"))
    analysis["with_deals"] = sum(1 for r in records if r.get("properties", {}).get("num_associated_deals", "0") and int(r["properties"]["num_associated_deals"]) > 0)
    
    # Lifecycle stages
    lifecycle_stages = {}
    for record in records:
        stage = record.get("properties", {}).get("lifecyclestage", "Unknown")
        lifecycle_stages[stage] = lifecycle_stages.get(stage, 0) + 1
    analysis["lifecycle_stages"] = lifecycle_stages
    
    # Sources
    sources = {}
    for record in records:
        source = record.get("properties", {}).get("hs_analytics_source", "Unknown")
        sources[source] = sources.get(source, 0) + 1
    analysis["sources"] = sources
    
    return analysis

def print_analysis(analysis: Dict[str, Any]):
    """Print analysis results"""
    
    print(f"\n📊 {analysis['object_type'].upper()} ANALYSIS RESULTS")
    print("=" * 60)
    
    print(f"\n📈 SUMMARY STATISTICS")
    print("-" * 30)
    print(f"Total Records: {analysis['total_records']:,}")
    print(f"Analysis Time: {analysis['analysis_timestamp']}")
    
    if analysis['total_records'] > 0:
        print(f"With Email: {analysis['with_email']:,} ({analysis['with_email']/analysis['total_records']*100:.1f}%)")
        print(f"With Company: {analysis['with_company']:,} ({analysis['with_company']/analysis['total_records']*100:.1f}%)")
        print(f"With Deals: {analysis['with_deals']:,} ({analysis['with_deals']/analysis['total_records']*100:.1f}%)")
        
        if analysis['lifecycle_stages']:
            print(f"\n🔄 LIFECYCLE STAGES")
            print("-" * 30)
            for stage, count in sorted(analysis['lifecycle_stages'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {stage}: {count:,}")
        
        if analysis['sources']:
            print(f"\n📡 TRAFFIC SOURCES")
            print("-" * 30)
            for source, count in sorted(analysis['sources'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {source}: {count:,}")

def save_data(records: List[Dict], analysis: Dict[str, Any], object_type: str, start_date: str, end_date: str):
    """Save raw data and analysis results"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save raw data
    raw_filename = f"hubspot_{object_type}_{start_date.replace('-', '')}_{end_date.replace('-', '')}_{timestamp}.json"
    with open(raw_filename, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    
    # Save analysis
    analysis_filename = f"hubspot_{object_type}_analysis_{start_date.replace('-', '')}_{end_date.replace('-', '')}_{timestamp}.json"
    with open(analysis_filename, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 DATA SAVED")
    print(f"Raw Data: {raw_filename}")
    print(f"Analysis: {analysis_filename}")

def main():
    """Main function"""
    
    parser = argparse.ArgumentParser(description="Complete HubSpot data retrieval with pagination")
    parser.add_argument("--object-type", required=True, choices=["contacts", "deals", "companies"], 
                       help="Type of HubSpot object to retrieve")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--properties", nargs="+", help="Specific properties to retrieve")
    parser.add_argument("--associations", nargs="+", help="Associations to include")
    
    args = parser.parse_args()
    
    try:
        # Get token
        token = get_hubspot_token()
        
        # Create date filters
        filters = create_date_filters(args.start_date, args.end_date)
        
        # Fetch all records with complete pagination
        records = fetch_all_hubspot_records(
            object_type=args.object_type,
            access_token=token,
            filters=filters,
            properties=args.properties,
            associations=args.associations
        )
        
        if not records:
            print(f"❌ No {args.object_type} found for {args.start_date} to {args.end_date}")
            return
            
        # Analyze data
        analysis = analyze_records(records, args.object_type)
        
        # Print analysis
        print_analysis(analysis)
        
        # Save data
        save_data(records, analysis, args.object_type, args.start_date, args.end_date)
        
        print(f"\n✅ Complete {args.object_type} analysis finished successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
