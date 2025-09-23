#!/usr/bin/env python3
"""
Meta Ads UTM Campaign Linkage Analysis
=====================================

Analyzes UTM campaigns from HubSpot contacts and matches them to Meta Ads campaigns
using the existing Meta Ads API integration.

Features:
- Extracts UTM campaigns from HubSpot contacts 
- Searches Meta Ads campaigns for matches
- Correlates campaign performance with lead generation
- Generates actionable insights for campaign optimization

Usage:
    python meta_ads_utm_analysis.py --start-date 2025-08-01 --end-date 2025-08-31

Author: Data Analytics Team - Colppy
"""

import os
import sys
import json
import requests
import argparse
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Any
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Meta Ads API imports
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.exceptions import FacebookRequestError

def load_environment():
    """Load environment variables"""
    from dotenv import load_dotenv
    
    # Try multiple .env locations
    env_paths = [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    ]
    
    for env_path in env_paths:
        if os.path.exists(env_path):
            load_dotenv(env_path)
            print(f"✅ Loaded environment from {env_path}")
            break

def build_meta_ads_client() -> FacebookAdsApi:
    """Build Meta Ads client using environment variables"""
    app_id = os.environ.get("META_ADS_APP_ID")
    app_secret = os.environ.get("META_ADS_APP_SECRET")
    access_token = os.environ.get("META_ADS_ACCESS_TOKEN")
    
    if not all([app_id, app_secret, access_token]):
        print("❌ Missing required Meta Ads environment variables")
        sys.exit(1)
    
    FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
    return FacebookAdsApi.get_default_api()

def fetch_hubspot_contacts_with_utm(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Fetch HubSpot contacts with UTM campaign data"""
    hubspot_api_key = os.environ.get("HUBSPOT_API_KEY")
    if not hubspot_api_key:
        print("❌ HUBSPOT_API_KEY not found in environment")
        return []
    
    headers = {
        "Authorization": f"Bearer {hubspot_api_key}",
        "Content-Type": "application/json"
    }
    
    # Convert dates to timestamps
    start_timestamp = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_timestamp = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
    
    contacts = []
    after = None
    
    while True:
        url = "https://api.hubapi.com/crm/v3/objects/contacts"
        params = {
            "properties": [
                "firstname", "lastname", "email", "hs_analytics_source",
                "hs_analytics_source_data_1", "hs_analytics_source_data_2",
                "hs_analytics_campaign", "createdate", "hs_lead_status"
            ],
            "limit": 100
        }
        
        if after:
            params["after"] = after
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            batch_contacts = data.get("results", [])
            
            # Filter by date range
            filtered_contacts = []
            for contact in batch_contacts:
                created_at = contact.get("properties", {}).get("createdate")
                if created_at:
                    created_timestamp = int(created_at)
                    if start_timestamp <= created_timestamp <= end_timestamp:
                        filtered_contacts.append(contact)
            
            contacts.extend(filtered_contacts)
            
            # Check for pagination
            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            if not after:
                break
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching HubSpot contacts: {e}")
            break
    
    print(f"📋 Found {len(contacts)} HubSpot contacts in date range")
    return contacts

def extract_utm_campaigns(contacts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Extract UTM campaigns from HubSpot contacts"""
    utm_campaigns = defaultdict(list)
    
    for contact in contacts:
        properties = contact.get("properties", {})
        
        # Get UTM campaign data
        utm_campaign = properties.get("hs_analytics_campaign")
        utm_source = properties.get("hs_analytics_source")
        utm_medium = properties.get("hs_analytics_source_data_1")
        utm_content = properties.get("hs_analytics_source_data_2")
        
        if utm_campaign:
            campaign_key = utm_campaign.lower().strip()
            contact_data = {
                "contact_id": contact.get("id"),
                "email": properties.get("email"),
                "firstname": properties.get("firstname"),
                "lastname": properties.get("lastname"),
                "createdate": properties.get("createdate"),
                "hs_lead_status": properties.get("hs_lead_status"),
                "utm_campaign": utm_campaign,
                "utm_source": utm_source,
                "utm_medium": utm_medium,
                "utm_content": utm_content
            }
            utm_campaigns[campaign_key].append(contact_data)
    
    print(f"🎯 Found {len(utm_campaigns)} unique UTM campaigns")
    return dict(utm_campaigns)

def fetch_meta_ads_campaigns(api: FacebookAdsApi, account_id: str, start_date: str, end_date: str) -> Dict[str, Dict[str, str]]:
    """Fetch Meta Ads campaigns and create searchable index"""
    try:
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        account = AdAccount(account_id)
        
        # Get campaign insights for the period
        params = {
            'time_range': {
                'since': start_date,
                'until': end_date
            },
            'level': 'campaign',
            'fields': ['campaign_id', 'campaign_name', 'impressions', 'clicks', 'spend']
        }
        
        insights = account.get_insights(params=params)
        
        campaigns = {}
        for insight in insights:
            campaign_id = insight.get('campaign_id')
            campaign_name = insight.get('campaign_name')
            
            if campaign_id and campaign_name:
                # Create searchable variations of campaign name
                search_terms = [
                    campaign_name.lower().strip(),
                    campaign_name.lower().replace(' ', ''),
                    campaign_name.lower().replace(' ', '_'),
                    campaign_name.lower().replace(' ', '-')
                ]
                
                campaign_data = {
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "impressions": int(insight.get('impressions', 0)),
                    "clicks": int(insight.get('clicks', 0)),
                    "spend": float(insight.get('spend', 0))
                }
                
                for term in search_terms:
                    campaigns[term] = campaign_data
        
        print(f"📊 Found {len(set(c['campaign_id'] for c in campaigns.values()))} Meta Ads campaigns")
        return campaigns
        
    except FacebookRequestError as e:
        print(f"❌ Error fetching Meta Ads campaigns: {e}")
        return {}

def match_utm_to_meta_campaigns(utm_campaigns: Dict[str, List[Dict[str, Any]]], 
                               meta_campaigns: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """Match UTM campaigns to Meta Ads campaigns"""
    matches = {}
    unmatched_utm = []
    
    for utm_campaign, contacts in utm_campaigns.items():
        # Try different matching strategies
        matched_campaign = None
        
        # Exact match
        if utm_campaign in meta_campaigns:
            matched_campaign = meta_campaigns[utm_campaign]
        else:
            # Partial match - look for campaigns containing UTM campaign name
            for meta_term, meta_data in meta_campaigns.items():
                if utm_campaign in meta_term or meta_term in utm_campaign:
                    matched_campaign = meta_data
                    break
        
        if matched_campaign:
            matches[utm_campaign] = {
                "meta_campaign": matched_campaign,
                "hubspot_contacts": contacts,
                "contact_count": len(contacts),
                "match_type": "exact" if utm_campaign in meta_campaigns else "partial"
            }
        else:
            unmatched_utm.append({
                "utm_campaign": utm_campaign,
                "contact_count": len(contacts),
                "contacts": contacts
            })
    
    return {
        "matches": matches,
        "unmatched": unmatched_utm,
        "match_rate": len(matches) / len(utm_campaigns) * 100 if utm_campaigns else 0
    }

def analyze_campaign_performance(matches: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze matched campaign performance"""
    if not matches:
        return {"error": "No matches found"}
    
    total_contacts = sum(match["contact_count"] for match in matches.values())
    total_impressions = sum(match["meta_campaign"]["impressions"] for match in matches.values())
    total_clicks = sum(match["meta_campaign"]["clicks"] for match in matches.values())
    total_spend = sum(match["meta_campaign"]["spend"] for match in matches.values())
    
    # Calculate conversion metrics
    overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    cost_per_contact = (total_spend / total_contacts) if total_contacts > 0 else 0
    contacts_per_click = (total_contacts / total_clicks) if total_clicks > 0 else 0
    
    # Find top performing campaigns
    top_campaigns = sorted(matches.items(), 
                          key=lambda x: x[1]["contact_count"], 
                          reverse=True)[:5]
    
    analysis = {
        "summary": {
            "total_matched_campaigns": len(matches),
            "total_contacts": total_contacts,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_spend": total_spend,
            "overall_ctr": overall_ctr,
            "cost_per_contact": cost_per_contact,
            "contacts_per_click": contacts_per_click
        },
        "top_campaigns": top_campaigns,
        "insights": []
    }
    
    # Generate insights
    if cost_per_contact < 10:
        analysis["insights"].append("✅ Low cost per contact (<$10) - efficient lead generation")
    elif cost_per_contact > 50:
        analysis["insights"].append("⚠️ High cost per contact (>$50) - consider optimization")
    
    if contacts_per_click > 0.1:
        analysis["insights"].append("✅ Good conversion rate from clicks to contacts")
    elif contacts_per_click < 0.05:
        analysis["insights"].append("⚠️ Low conversion rate from clicks - check landing page")
    
    if overall_ctr > 2:
        analysis["insights"].append("✅ Good CTR performance (>2%)")
    elif overall_ctr < 1:
        analysis["insights"].append("⚠️ Low CTR (<1%) - consider ad creative optimization")
    
    return analysis

def export_results(results: Dict[str, Any], filename: str):
    """Export analysis results to JSON"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

def main():
    """Main analysis function"""
    parser = argparse.ArgumentParser(description='Meta Ads UTM Campaign Linkage Analysis')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--account-id', help='Meta Ads account ID (optional)')
    parser.add_argument('--output-dir', default='tools/outputs', help='Output directory')
    
    args = parser.parse_args()
    
    print("🚀 Meta Ads UTM Campaign Linkage Analysis")
    print("=" * 50)
    print(f"📅 Date Range: {args.start_date} to {args.end_date}")
    
    # Load environment
    load_environment()
    
    # Initialize Meta Ads API
    try:
        meta_api = build_meta_ads_client()
        print("✅ Meta Ads API initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Meta Ads API: {e}")
        sys.exit(1)
    
    # Get default account ID if not provided
    if not args.account_id:
        account_id = os.environ.get("META_ADS_ACCOUNT_ID")
        if not account_id:
            print("❌ No account ID provided and META_ADS_ACCOUNT_ID not set")
            sys.exit(1)
    else:
        account_id = args.account_id
    
    print(f"🎯 Using Meta Ads account: {account_id}")
    
    # Fetch HubSpot contacts with UTM data
    print("\n📋 Fetching HubSpot contacts...")
    contacts = fetch_hubspot_contacts_with_utm(args.start_date, args.end_date)
    if not contacts:
        print("❌ No HubSpot contacts found")
        sys.exit(1)
    
    # Extract UTM campaigns
    print("\n🎯 Extracting UTM campaigns...")
    utm_campaigns = extract_utm_campaigns(contacts)
    
    # Fetch Meta Ads campaigns
    print("\n📊 Fetching Meta Ads campaigns...")
    meta_campaigns = fetch_meta_ads_campaigns(meta_api, account_id, args.start_date, args.end_date)
    if not meta_campaigns:
        print("❌ No Meta Ads campaigns found")
        sys.exit(1)
    
    # Match UTM campaigns to Meta campaigns
    print("\n🔗 Matching UTM campaigns to Meta Ads...")
    matches = match_utm_to_meta_campaigns(utm_campaigns, meta_campaigns)
    
    # Analyze performance
    print("\n📈 Analyzing campaign performance...")
    analysis = analyze_campaign_performance(matches["matches"])
    
    # Prepare results
    results = {
        "metadata": {
            "date_range": {"start": args.start_date, "end": args.end_date},
            "account_id": account_id,
            "generated_at": datetime.now().isoformat(),
            "total_hubspot_contacts": len(contacts),
            "total_utm_campaigns": len(utm_campaigns),
            "total_meta_campaigns": len(set(c["campaign_id"] for c in meta_campaigns.values())),
            "match_rate": matches["match_rate"]
        },
        "utm_campaigns": utm_campaigns,
        "meta_campaigns": meta_campaigns,
        "matches": matches,
        "analysis": analysis
    }
    
    # Export results
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(args.output_dir, f"meta_ads_utm_analysis_{args.start_date}_{args.end_date}_{timestamp}.json")
    export_results(results, filename)
    
    # Display summary
    print("\n📈 Analysis Summary")
    print("=" * 30)
    print(f"HubSpot Contacts: {len(contacts):,}")
    print(f"UTM Campaigns: {len(utm_campaigns)}")
    print(f"Meta Ads Campaigns: {len(set(c['campaign_id'] for c in meta_campaigns.values()))}")
    print(f"Match Rate: {matches['match_rate']:.1f}%")
    print(f"Matched Campaigns: {len(matches['matches'])}")
    print(f"Unmatched UTM: {len(matches['unmatched'])}")
    
    if analysis.get("summary"):
        summary = analysis["summary"]
        print(f"\n💰 Performance Metrics")
        print(f"Total Contacts: {summary['total_contacts']:,}")
        print(f"Total Spend: ${summary['total_spend']:,.2f}")
        print(f"Cost per Contact: ${summary['cost_per_contact']:.2f}")
        print(f"Overall CTR: {summary['overall_ctr']:.2f}%")
    
    # Display insights
    if analysis.get("insights"):
        print(f"\n💡 Key Insights")
        for insight in analysis["insights"]:
            print(f"  {insight}")
    
    print(f"\n✅ Analysis complete! Results saved to {filename}")

if __name__ == "__main__":
    main()
