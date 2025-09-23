#!/usr/bin/env python3
"""
Meta Ads Campaign Performance Analysis
=====================================

Analyzes Meta Ads campaign performance metrics and generates comprehensive reports.
Follows the same pattern as Google Ads analysis scripts.

Features:
- Campaign performance metrics
- Ad set and ad-level analysis
- Cost and conversion tracking
- Argentina-specific formatting
- Export to JSON and CSV formats

Usage:
    python meta_ads_campaign_analysis.py --start-date 2025-08-01 --end-date 2025-08-31

Author: Data Analytics Team - Colppy
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Meta Ads API imports
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.insights import Insights
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

def format_number_ar(n: float | int) -> str:
    """Format number with Argentina locale (comma as decimal separator)"""
    if n is None:
        return "0,00"
    return f"{n:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def build_meta_ads_client() -> FacebookAdsApi:
    """Build Meta Ads API client using environment variables"""
    app_id = os.environ.get("META_ADS_APP_ID")
    app_secret = os.environ.get("META_ADS_APP_SECRET")
    access_token = os.environ.get("META_ADS_ACCESS_TOKEN")
    
    if not all([app_id, app_secret, access_token]):
        print("❌ Missing required Meta Ads environment variables:")
        print("   - META_ADS_APP_ID")
        print("   - META_ADS_APP_SECRET")
        print("   - META_ADS_ACCESS_TOKEN")
        sys.exit(1)
    
    FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
    return FacebookAdsApi.get_default_api()

def get_ad_accounts(api: FacebookAdsApi) -> List[Dict[str, Any]]:
    """Get all accessible ad accounts"""
    try:
        response = api.call('GET', '/me/adaccounts')
        accounts = response.get('data', [])
        
        result = []
        for account in accounts:
            account_info = {
                "id": account.get('id'),
                "name": account.get('name'),
                "account_status": account.get('account_status'),
                "currency": account.get('currency'),
                "timezone": account.get('timezone_name')
            }
            result.append(account_info)
        
        return result
        
    except FacebookRequestError as e:
        print(f"❌ Error fetching ad accounts: {e}")
        return []

def get_campaign_performance(api: FacebookAdsApi, account_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Get campaign performance metrics"""
    try:
        # Ensure account ID has 'act_' prefix
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        account = AdAccount(account_id)
        
        params = {
            'time_range': {
                'since': start_date,
                'until': end_date
            },
            'level': 'campaign',
            'fields': [
                'campaign_id', 'campaign_name', 'impressions', 'clicks', 
                'spend', 'cpm', 'cpc', 'ctr', 'reach', 'frequency',
                'actions', 'cost_per_action_type', 'conversion_values',
                'conversion_rate_ranking', 'engagement_rate_ranking',
                'quality_ranking', 'relevance_score'
            ]
        }
        
        insights = account.get_insights(params=params)
        
        campaigns = []
        for insight in insights:
            campaign_data = {
                "campaign_id": insight.get('campaign_id'),
                "campaign_name": insight.get('campaign_name'),
                "impressions": int(insight.get('impressions', 0)),
                "clicks": int(insight.get('clicks', 0)),
                "spend": float(insight.get('spend', 0)),
                "cpm": float(insight.get('cpm', 0)),
                "cpc": float(insight.get('cpc', 0)),
                "ctr": float(insight.get('ctr', 0)),
                "reach": int(insight.get('reach', 0)),
                "frequency": float(insight.get('frequency', 0)),
                "actions": insight.get('actions', []),
                "cost_per_action_type": insight.get('cost_per_action_type', []),
                "conversion_values": insight.get('conversion_values', []),
                "conversion_rate_ranking": insight.get('conversion_rate_ranking'),
                "engagement_rate_ranking": insight.get('engagement_rate_ranking'),
                "quality_ranking": insight.get('quality_ranking'),
                "relevance_score": insight.get('relevance_score')
            }
            campaigns.append(campaign_data)
        
        return campaigns
        
    except FacebookRequestError as e:
        print(f"❌ Error fetching campaign performance: {e}")
        return []

def get_ad_set_performance(api: FacebookAdsApi, account_id: str, campaign_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Get ad set performance metrics"""
    try:
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        account = AdAccount(account_id)
        
        params = {
            'time_range': {
                'since': start_date,
                'until': end_date
            },
            'level': 'adset',
            'fields': [
                'adset_id', 'adset_name', 'campaign_id', 'impressions', 'clicks',
                'spend', 'cpm', 'cpc', 'ctr', 'reach', 'frequency',
                'actions', 'cost_per_action_type'
            ],
            'filtering': [{'field': 'campaign.id', 'operator': 'IN', 'value': [campaign_id]}]
        }
        
        insights = account.get_insights(params=params)
        
        ad_sets = []
        for insight in insights:
            ad_set_data = {
                "adset_id": insight.get('adset_id'),
                "adset_name": insight.get('adset_name'),
                "campaign_id": insight.get('campaign_id'),
                "impressions": int(insight.get('impressions', 0)),
                "clicks": int(insight.get('clicks', 0)),
                "spend": float(insight.get('spend', 0)),
                "cpm": float(insight.get('cpm', 0)),
                "cpc": float(insight.get('cpc', 0)),
                "ctr": float(insight.get('ctr', 0)),
                "reach": int(insight.get('reach', 0)),
                "frequency": float(insight.get('frequency', 0)),
                "actions": insight.get('actions', []),
                "cost_per_action_type": insight.get('cost_per_action_type', [])
            }
            ad_sets.append(ad_set_data)
        
        return ad_sets
        
    except FacebookRequestError as e:
        print(f"❌ Error fetching ad set performance: {e}")
        return []

def analyze_campaign_performance(campaigns: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze campaign performance and generate insights"""
    if not campaigns:
        return {"error": "No campaign data available"}
    
    total_impressions = sum(c.get('impressions', 0) for c in campaigns)
    total_clicks = sum(c.get('clicks', 0) for c in campaigns)
    total_spend = sum(c.get('spend', 0) for c in campaigns)
    
    # Calculate overall metrics
    overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    overall_cpm = (total_spend / total_impressions * 1000) if total_impressions > 0 else 0
    overall_cpc = (total_spend / total_clicks) if total_clicks > 0 else 0
    
    # Find top performers
    top_spend_campaigns = sorted(campaigns, key=lambda x: x.get('spend', 0), reverse=True)[:5]
    top_ctr_campaigns = sorted(campaigns, key=lambda x: x.get('ctr', 0), reverse=True)[:5]
    top_cpc_campaigns = sorted(campaigns, key=lambda x: x.get('cpc', 0), reverse=True)[:5]
    
    analysis = {
        "summary": {
            "total_campaigns": len(campaigns),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_spend": total_spend,
            "overall_ctr": overall_ctr,
            "overall_cpm": overall_cpm,
            "overall_cpc": overall_cpc
        },
        "top_performers": {
            "by_spend": top_spend_campaigns,
            "by_ctr": top_ctr_campaigns,
            "by_cpc": top_cpc_campaigns
        },
        "insights": []
    }
    
    # Generate insights
    if overall_ctr > 2.0:
        analysis["insights"].append("✅ Good overall CTR performance (>2%)")
    elif overall_ctr < 1.0:
        analysis["insights"].append("⚠️ Low CTR performance (<1%) - consider ad creative optimization")
    
    if overall_cpc > 2.0:
        analysis["insights"].append("⚠️ High CPC (>$2) - consider bid optimization")
    elif overall_cpc < 0.5:
        analysis["insights"].append("✅ Low CPC (<$0.50) - good cost efficiency")
    
    if total_spend > 1000:
        analysis["insights"].append("💰 High spend campaign - monitor ROI closely")
    
    return analysis

def export_to_csv(campaigns: List[Dict[str, Any]], filename: str):
    """Export campaign data to CSV with Argentina formatting"""
    if not campaigns:
        print("⚠️ No campaign data to export")
        return
    
    # Flatten the data for CSV export
    flattened_data = []
    for campaign in campaigns:
        row = {
            "Campaign ID": campaign.get('campaign_id'),
            "Campaign Name": campaign.get('campaign_name'),
            "Impressions": campaign.get('impressions'),
            "Clicks": campaign.get('clicks'),
            "Spend": campaign.get('spend'),
            "CPM": campaign.get('cpm'),
            "CPC": campaign.get('cpc'),
            "CTR": campaign.get('ctr'),
            "Reach": campaign.get('reach'),
            "Frequency": campaign.get('frequency')
        }
        flattened_data.append(row)
    
    df = pd.DataFrame(flattened_data)
    
    # Format numbers for Argentina locale
    numeric_columns = ['Spend', 'CPM', 'CPC', 'CTR', 'Frequency']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: format_number_ar(x) if pd.notna(x) else "0,00")
    
    df.to_csv(filename, index=False, encoding='utf-8')
    print(f"📊 Campaign data exported to {filename}")

def main():
    """Main analysis function"""
    parser = argparse.ArgumentParser(description='Meta Ads Campaign Performance Analysis')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--account-id', help='Specific ad account ID (optional)')
    parser.add_argument('--output-dir', default='tools/outputs', help='Output directory')
    
    args = parser.parse_args()
    
    print("🚀 Meta Ads Campaign Performance Analysis")
    print("=" * 50)
    print(f"📅 Date Range: {args.start_date} to {args.end_date}")
    
    # Load environment
    load_environment()
    
    # Initialize API
    try:
        api = build_meta_ads_client()
        print("✅ Meta Ads API initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Meta Ads API: {e}")
        sys.exit(1)
    
    # Get ad accounts
    accounts = get_ad_accounts(api)
    if not accounts:
        print("❌ No ad accounts found or accessible")
        sys.exit(1)
    
    print(f"📋 Found {len(accounts)} ad accounts")
    
    # Use specific account or first available
    if args.account_id:
        account_id = args.account_id
        account_name = next((acc['name'] for acc in accounts if acc['id'] == account_id), 'Unknown')
    else:
        account_id = accounts[0]['id']
        account_name = accounts[0]['name']
    
    print(f"🎯 Analyzing account: {account_name} ({account_id})")
    
    # Get campaign performance
    campaigns = get_campaign_performance(api, account_id, args.start_date, args.end_date)
    if not campaigns:
        print("❌ No campaign data found for the specified period")
        sys.exit(1)
    
    print(f"📊 Found {len(campaigns)} campaigns with performance data")
    
    # Analyze performance
    analysis = analyze_campaign_performance(campaigns)
    
    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export results
    os.makedirs(args.output_dir, exist_ok=True)
    
    # JSON export
    json_filename = os.path.join(args.output_dir, f"meta_ads_campaign_analysis_{args.start_date}_{args.end_date}_{timestamp}.json")
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump({
            "metadata": {
                "account_id": account_id,
                "account_name": account_name,
                "date_range": {"start": args.start_date, "end": args.end_date},
                "generated_at": datetime.now().isoformat(),
                "total_campaigns": len(campaigns)
            },
            "campaigns": campaigns,
            "analysis": analysis
        }, f, indent=2, ensure_ascii=False)
    
    print(f"📄 Analysis exported to {json_filename}")
    
    # CSV export
    csv_filename = os.path.join(args.output_dir, f"meta_ads_campaign_data_{args.start_date}_{args.end_date}_{timestamp}.csv")
    export_to_csv(campaigns, csv_filename)
    
    # Display summary
    print("\n📈 Performance Summary")
    print("=" * 30)
    summary = analysis['summary']
    print(f"Total Campaigns: {summary['total_campaigns']}")
    print(f"Total Impressions: {summary['total_impressions']:,}")
    print(f"Total Clicks: {summary['total_clicks']:,}")
    print(f"Total Spend: ${summary['total_spend']:,.2f}")
    print(f"Overall CTR: {summary['overall_ctr']:.2f}%")
    print(f"Overall CPM: ${summary['overall_cpm']:.2f}")
    print(f"Overall CPC: ${summary['overall_cpc']:.2f}")
    
    # Display insights
    if analysis['insights']:
        print("\n💡 Key Insights")
        print("=" * 20)
        for insight in analysis['insights']:
            print(f"  {insight}")
    
    print(f"\n✅ Analysis complete! Files saved to {args.output_dir}")

if __name__ == "__main__":
    main()
