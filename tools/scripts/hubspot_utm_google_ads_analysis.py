#!/usr/bin/env python3
"""
HubSpot UTM Campaign to Google Ads Campaign Linkage Analysis
============================================================

Analyzes UTM campaigns from HubSpot contacts and matches them to Google Ads campaigns
using the existing Google Ads API integration.

Features:
- Extracts UTM campaigns from HubSpot contacts 
- Searches Google Ads campaigns for matches
- Correlates campaign performance with lead generation
- Generates actionable insights for campaign optimization

Usage:
    python hubspot_utm_google_ads_analysis.py --start-date 2025-08-01 --end-date 2025-08-31

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

# Import existing Google Ads modules
sys.path.append(os.path.dirname(__file__))
try:
    from google.ads.googleads.client import GoogleAdsClient
except ImportError:
    print("❌ Google Ads API not available. Install google-ads library.")
    sys.exit(1)

def build_google_ads_client() -> GoogleAdsClient:
    """Build Google Ads client using environment variables"""
    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "use_proto_plus": True,
        "login_customer_id": os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
    }
    
    if not config["login_customer_id"]:
        config["login_customer_id"] = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")
    
    return GoogleAdsClient.load_from_dict(config)

def fetch_hubspot_contacts_with_utm(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Fetch HubSpot contacts with UTM campaign data for date range"""
    api_key = os.getenv('HUBSPOT_API_KEY')
    if not api_key:
        raise ValueError("HUBSPOT_API_KEY environment variable required")
    
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    search_data = {
        'filterGroups': [{
            'filters': [{
                'propertyName': 'createdate',
                'operator': 'BETWEEN',
                'value': start_datetime,
                'highValue': end_datetime
            }]
        }],
        'properties': [
            'email', 'firstname', 'lastname', 'createdate', 'utm_campaign', 
            'hs_latest_source', 'lifecyclestage', 'activo'
        ],
        'limit': 100
    }
    
    url = 'https://api.hubapi.com/crm/v3/objects/contacts/search'
    all_contacts = []
    after = None
    
    print(f"📞 FETCHING HUBSPOT CONTACTS WITH UTM DATA")
    print(f"📅 Date Range: {start_date} to {end_date}")
    
    while True:
        if after:
            search_data["after"] = after
            
        response = requests.post(url, headers=headers, json=search_data)
        
        if response.status_code != 200:
            print(f"❌ HubSpot API error: {response.status_code} - {response.text}")
            break
            
        data = response.json()
        
        for contact in data.get('results', []):
            props = contact.get('properties', {})
            
            contact_data = {
                'contact_id': contact['id'],
                'email': props.get('email', ''),
                'firstname': props.get('firstname', ''),
                'lastname': props.get('lastname', ''),
                'createdate': props.get('createdate', ''),
                'utm_campaign': props.get('utm_campaign', '').strip() if props.get('utm_campaign') else '',
                'latest_source': props.get('hs_latest_source', '').strip() if props.get('hs_latest_source') else '',
                'lifecyclestage': props.get('lifecyclestage', ''),
                'is_pql': props.get('activo') == 'true'
            }
            
            all_contacts.append(contact_data)
        
        # Check for pagination
        paging = data.get('paging', {})
        after = paging.get('next', {}).get('after')
        
        if not after:
            break
        
        if len(all_contacts) % 500 == 0:
            print(f"📈 Progress: {len(all_contacts)} contacts fetched...")
    
    print(f"✅ CONTACTS EXTRACTED: {len(all_contacts)} total")
    
    # Filter contacts with UTM campaigns
    utm_contacts = [c for c in all_contacts if c['utm_campaign']]
    print(f"🎯 CONTACTS WITH UTM: {len(utm_contacts)} ({len(utm_contacts)/len(all_contacts)*100:.1f}%)")
    
    return all_contacts

def fetch_google_ads_campaigns(client: GoogleAdsClient, customer_id: str, start_date: str, end_date: str) -> Dict[str, Dict[str, Any]]:
    """Fetch Google Ads campaigns with performance metrics"""
    service = client.get_service("GoogleAdsService")
    
    query = f"""
    SELECT 
        campaign.id,
        campaign.name,
        campaign.status,
        campaign.advertising_channel_type,
        campaign.tracking_url_template,
        campaign.final_url_suffix,
        metrics.cost_micros,
        metrics.clicks,
        metrics.impressions,
        metrics.conversions
    FROM campaign
    WHERE segments.date >= '{start_date}' AND segments.date <= '{end_date}'
    ORDER BY metrics.cost_micros DESC
    """
    
    print(f"💰 FETCHING GOOGLE ADS CAMPAIGNS")
    print(f"📅 Date Range: {start_date} to {end_date}")
    
    campaigns = {}
    
    try:
        rows = service.search(customer_id=customer_id, query=query)
        
        for row in rows:
            campaign = row.campaign
            metrics = row.metrics
            
            campaign_data = {
                'id': str(campaign.id),
                'name': campaign.name,
                'status': campaign.status.name if campaign.status else 'UNKNOWN',
                'channel_type': campaign.advertising_channel_type.name if campaign.advertising_channel_type else 'UNKNOWN',
                'tracking_template': getattr(campaign, 'tracking_url_template', ''),
                'final_url_suffix': getattr(campaign, 'final_url_suffix', ''),
                'cost_micros': int(metrics.cost_micros or 0),
                'clicks': int(metrics.clicks or 0),
                'impressions': int(metrics.impressions or 0),
                'conversions': float(metrics.conversions or 0)
            }
            
            campaigns[campaign_data['id']] = campaign_data
        
        print(f"✅ GOOGLE ADS CAMPAIGNS: {len(campaigns)} fetched")
        
    except Exception as e:
        print(f"❌ Error fetching Google Ads campaigns: {e}")
        return {}
    
    return campaigns

def normalize_campaign_name(name: str) -> str:
    """Normalize campaign name for matching"""
    return "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")

def find_campaign_matches(utm_campaigns: Set[str], google_ads_campaigns: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """Find matches between UTM campaigns and Google Ads campaigns"""
    matches = defaultdict(list)
    
    print(f"\n🔍 MATCHING UTM CAMPAIGNS TO GOOGLE ADS")
    print(f"UTM campaigns to match: {len(utm_campaigns)}")
    print(f"Google Ads campaigns available: {len(google_ads_campaigns)}")
    
    for utm in utm_campaigns:
        utm_norm = normalize_campaign_name(utm)
        utm_lower = utm.lower()
        
        for gad_id, gad_data in google_ads_campaigns.items():
            gad_name = gad_data['name']
            gad_norm = normalize_campaign_name(gad_name)
            gad_lower = gad_name.lower()
            
            # Multiple matching strategies
            if (
                utm_norm == gad_norm or  # Exact normalized match
                utm_lower in gad_lower or  # UTM contained in Google Ads name
                gad_lower in utm_lower or  # Google Ads name contained in UTM
                any(word in gad_lower for word in utm_lower.split() if len(word) > 3)  # Key word overlap
            ):
                matches[utm].append(gad_id)
    
    return dict(matches)

def analyze_campaign_performance(contacts: List[Dict[str, Any]], campaigns: Dict[str, Dict[str, Any]], matches: Dict[str, List[str]]) -> Dict[str, Any]:
    """Analyze performance correlation between UTM campaigns and Google Ads"""
    analysis = {
        'utm_campaign_stats': {},
        'matched_campaigns': {},
        'unmatched_utms': [],
        'summary_metrics': {}
    }
    
    # Analyze UTM campaign performance in HubSpot
    utm_stats = defaultdict(lambda: {
        'total_contacts': 0,
        'pql_contacts': 0,
        'pql_rate': 0.0,
        'sources': set()
    })
    
    for contact in contacts:
        utm = contact['utm_campaign']
        if not utm:
            continue
            
        utm_stats[utm]['total_contacts'] += 1
        if contact['is_pql']:
            utm_stats[utm]['pql_contacts'] += 1
        utm_stats[utm]['sources'].add(contact['latest_source'])
    
    # Calculate rates and convert sets to lists
    for utm, stats in utm_stats.items():
        stats['pql_rate'] = (stats['pql_contacts'] / stats['total_contacts'] * 100) if stats['total_contacts'] > 0 else 0.0
        stats['sources'] = list(stats['sources'])
    
    analysis['utm_campaign_stats'] = dict(utm_stats)
    
    # Analyze matched campaigns
    for utm, gad_ids in matches.items():
        utm_data = utm_stats.get(utm, {})
        gad_data = [campaigns.get(gad_id, {}) for gad_id in gad_ids]
        
        # Aggregate Google Ads metrics
        total_cost = sum(gad.get('cost_micros', 0) for gad in gad_data)
        total_clicks = sum(gad.get('clicks', 0) for gad in gad_data)
        total_impressions = sum(gad.get('impressions', 0) for gad in gad_data)
        total_conversions = sum(gad.get('conversions', 0) for gad in gad_data)
        
        # Calculate efficiency metrics
        cost_per_lead = (total_cost / 1_000_000) / utm_data.get('total_contacts', 1) if utm_data.get('total_contacts', 0) > 0 else 0
        cost_per_pql = (total_cost / 1_000_000) / utm_data.get('pql_contacts', 1) if utm_data.get('pql_contacts', 0) > 0 else 0
        
        analysis['matched_campaigns'][utm] = {
            'hubspot_metrics': utm_data,
            'google_ads_metrics': {
                'total_cost_ars': total_cost / 1_000_000,
                'total_clicks': total_clicks,
                'total_impressions': total_impressions,
                'total_conversions': total_conversions,
                'matched_campaigns': [gad.get('name', '') for gad in gad_data]
            },
            'efficiency_metrics': {
                'cost_per_lead_ars': round(cost_per_lead, 2),
                'cost_per_pql_ars': round(cost_per_pql, 2),
                'clicks_per_lead': round(total_clicks / utm_data.get('total_contacts', 1), 2) if utm_data.get('total_contacts', 0) > 0 else 0
            }
        }
    
    # Track unmatched UTMs
    all_utms = set(utm_stats.keys())
    matched_utms = set(matches.keys())
    analysis['unmatched_utms'] = list(all_utms - matched_utms)
    
    # Summary metrics
    total_matched_contacts = sum(utm_stats[utm]['total_contacts'] for utm in matched_utms)
    total_matched_pqls = sum(utm_stats[utm]['pql_contacts'] for utm in matched_utms)
    total_unmatched_contacts = sum(utm_stats[utm]['total_contacts'] for utm in analysis['unmatched_utms'])
    
    analysis['summary_metrics'] = {
        'total_utm_campaigns': len(all_utms),
        'matched_campaigns': len(matched_utms),
        'match_rate': round(len(matched_utms) / len(all_utms) * 100, 1) if all_utms else 0,
        'matched_contacts': total_matched_contacts,
        'matched_pqls': total_matched_pqls,
        'unmatched_contacts': total_unmatched_contacts
    }
    
    return analysis

def print_analysis_summary(analysis: Dict[str, Any]):
    """Print formatted analysis summary"""
    print(f"\n{'='*80}")
    print("HUBSPOT UTM ↔ GOOGLE ADS CAMPAIGN ANALYSIS")
    print(f"{'='*80}")
    
    summary = analysis['summary_metrics']
    print(f"📊 SUMMARY METRICS:")
    print(f"   Total UTM Campaigns: {summary['total_utm_campaigns']}")
    print(f"   Matched to Google Ads: {summary['matched_campaigns']} ({summary['match_rate']:.1f}%)")
    print(f"   Matched Contacts: {summary['matched_contacts']:,}")
    print(f"   Matched PQLs: {summary['matched_pqls']}")
    print(f"   Unmatched Contacts: {summary['unmatched_contacts']:,}")
    
    print(f"\n🎯 TOP PERFORMING MATCHED CAMPAIGNS:")
    matched = analysis['matched_campaigns']
    
    # Sort by PQL rate
    top_campaigns = sorted(
        matched.items(), 
        key=lambda x: x[1]['hubspot_metrics'].get('pql_rate', 0), 
        reverse=True
    )[:5]
    
    for utm, data in top_campaigns:
        hs_metrics = data['hubspot_metrics']
        gad_metrics = data['google_ads_metrics']
        eff_metrics = data['efficiency_metrics']
        
        print(f"\n   🚀 {utm}")
        print(f"      HubSpot: {hs_metrics['total_contacts']} contacts, {hs_metrics['pql_contacts']} PQLs ({hs_metrics['pql_rate']:.1f}%)")
        print(f"      Google Ads: ${gad_metrics['total_cost_ars']:,.0f} cost, {gad_metrics['total_clicks']:,} clicks")
        print(f"      Efficiency: ${eff_metrics['cost_per_lead_ars']:.0f}/lead, ${eff_metrics['cost_per_pql_ars']:.0f}/PQL")
        print(f"      Matched to: {', '.join(gad_metrics['matched_campaigns'][:2])}")
    
    if analysis['unmatched_utms']:
        print(f"\n⚠️  UNMATCHED UTM CAMPAIGNS ({len(analysis['unmatched_utms'])}):")
        for utm in analysis['unmatched_utms'][:5]:
            stats = analysis['utm_campaign_stats'].get(utm, {})
            print(f"   - {utm} ({stats.get('total_contacts', 0)} contacts)")

def save_analysis_results(analysis: Dict[str, Any], start_date: str, end_date: str):
    """Save analysis results to JSON file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_start = start_date.replace('-', '')
    safe_end = end_date.replace('-', '')
    
    output_dir = 'tools/outputs'
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = f"{output_dir}/hubspot_utm_google_ads_analysis_{safe_start}_{safe_end}_{timestamp}.json"
    
    output_data = {
        'analysis_date': datetime.now().isoformat(),
        'date_range': {'start_date': start_date, 'end_date': end_date},
        'methodology': 'HubSpot UTM to Google Ads Campaign Linkage Analysis',
        'analysis': analysis
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {output_file}")
    return output_file

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='HubSpot UTM to Google Ads Campaign Analysis')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--customer-id', help='Google Ads customer ID (defaults to env var)')
    
    args = parser.parse_args()
    
    customer_id = args.customer_id or os.getenv('GOOGLE_ADS_CUSTOMER_ID')
    if not customer_id:
        print("❌ Google Ads customer ID required (--customer-id or GOOGLE_ADS_CUSTOMER_ID env var)")
        sys.exit(1)
    
    print(f"🎯 HUBSPOT UTM ↔ GOOGLE ADS CAMPAIGN ANALYSIS")
    print(f"📅 Period: {args.start_date} to {args.end_date}")
    print(f"🔑 Google Ads Customer ID: {customer_id}")
    print("=" * 60)
    
    try:
        # Step 1: Fetch HubSpot contacts with UTM data
        contacts = fetch_hubspot_contacts_with_utm(args.start_date, args.end_date)
        
        # Step 2: Extract unique UTM campaigns
        utm_campaigns = set(c['utm_campaign'] for c in contacts if c['utm_campaign'])
        print(f"🎯 UNIQUE UTM CAMPAIGNS: {len(utm_campaigns)}")
        
        # Step 3: Fetch Google Ads campaigns
        google_ads_client = build_google_ads_client()
        google_ads_campaigns = fetch_google_ads_campaigns(
            google_ads_client, customer_id, args.start_date, args.end_date
        )
        
        # Step 4: Match UTM campaigns to Google Ads campaigns
        matches = find_campaign_matches(utm_campaigns, google_ads_campaigns)
        
        # Step 5: Analyze performance correlation
        analysis = analyze_campaign_performance(contacts, google_ads_campaigns, matches)
        
        # Step 6: Present results
        print_analysis_summary(analysis)
        
        # Step 7: Save results
        output_file = save_analysis_results(analysis, args.start_date, args.end_date)
        
        print(f"\n✅ ANALYSIS COMPLETED")
        print(f"📁 Results saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

