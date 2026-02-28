#!/usr/bin/env python3
"""
Meta Ads Campaign Analysis - Ready to Use
==========================================

This script analyzes your Meta Ads campaigns and provides insights.
Since you already have ads_read permission, this works immediately!
"""

import os
import sys
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError
from datetime import datetime, timedelta
import json

# Your working credentials
ACCESS_TOKEN = "EAA6PYOffkGsBPZAjEO7NNEZB3uaNWZAZCBnboIeESIQ4kEVXc2ZAikZC3AW5JhReQx4y9Lg5jCnOHZCbmLIRB1OrA6qF5yHLKITx7MjoTWgtpaqYqLYKmH34W5ZBsE6tIpZBVUIUKSpfZB97XPtNxAeTD7CSZB5plnuh2gUaTirZCuXjRErfzZAUQvZCt5ZAqdLZAMOshmrdJsIbeZAbZCyNh4u6qb4Ob2nf5S1Wt9VAKSd3nnIRVlGVMged0LQPXBjfAEd1XpXLjZC93vqo1FXn0nd3AZDZD"
ACCOUNT_ID = "act_111192969640236"

def analyze_campaigns():
    """Analyze Meta Ads campaigns"""
    print("🚀 Meta Ads Campaign Analysis")
    print("=" * 50)
    print(f"Account: {ACCOUNT_ID}")
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Initialize API
        FacebookAdsApi.init(access_token=ACCESS_TOKEN)
        account = AdAccount(ACCOUNT_ID)
        
        # Get account info
        account_info = account.api_get(fields=['name', 'account_status', 'currency', 'timezone_name'])
        print(f"\n📊 Account Information:")
        print(f"  Name: {account_info.get('name', 'Unknown')}")
        print(f"  Status: {account_info.get('account_status', 'Unknown')}")
        print(f"  Currency: {account_info.get('currency', 'Unknown')}")
        print(f"  Timezone: {account_info.get('timezone_name', 'Unknown')}")
        
        # Get campaigns
        print(f"\n📊 Campaign Analysis:")
        campaigns = account.get_campaigns(fields=[
            'id', 'name', 'status', 'objective', 'created_time', 
            'updated_time', 'start_time', 'stop_time'
        ])
        
        campaign_data = []
        active_campaigns = 0
        paused_campaigns = 0
        
        for campaign in campaigns:
            status = campaign.get('status', 'Unknown')
            if status == 'ACTIVE':
                active_campaigns += 1
            elif status == 'PAUSED':
                paused_campaigns += 1
            
            campaign_data.append({
                'id': campaign.get('id', 'Unknown'),
                'name': campaign.get('name', 'Unnamed'),
                'status': status,
                'objective': campaign.get('objective', 'Unknown'),
                'created_time': campaign.get('created_time', 'Unknown'),
                'updated_time': campaign.get('updated_time', 'Unknown'),
                'start_time': campaign.get('start_time', 'Unknown'),
                'stop_time': campaign.get('stop_time', 'Unknown')
            })
        
        print(f"  Total Campaigns: {len(campaign_data)}")
        print(f"  Active: {active_campaigns}")
        print(f"  Paused: {paused_campaigns}")
        
        # Display campaign details
        print(f"\n📋 Campaign Details:")
        for i, camp in enumerate(campaign_data, 1):
            print(f"  {i}. {camp['name']}")
            print(f"     ID: {camp['id']}")
            print(f"     Status: {camp['status']}")
            print(f"     Objective: {camp['objective']}")
            print(f"     Created: {camp['created_time']}")
            print()
        
        # Get campaign insights (performance data)
        print(f"\n📊 Campaign Performance (Last 30 Days):")
        try:
            insights = account.get_insights(fields=[
                'campaign_id', 'campaign_name', 'impressions', 'clicks', 
                'spend', 'ctr', 'cpc', 'cpm', 'reach', 'frequency'
            ], params={
                'time_range': {'since': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                              'until': datetime.now().strftime('%Y-%m-%d')}
            })
            
            total_impressions = 0
            total_clicks = 0
            total_spend = 0
            
            for insight in insights:
                impressions = int(insight.get('impressions', 0))
                clicks = int(insight.get('clicks', 0))
                spend = float(insight.get('spend', 0))
                
                total_impressions += impressions
                total_clicks += clicks
                total_spend += spend
                
                print(f"  Campaign: {insight.get('campaign_name', 'Unknown')}")
                print(f"    Impressions: {impressions:,}")
                print(f"    Clicks: {clicks:,}")
                print(f"    Spend: ${spend:,.2f}")
                print(f"    CTR: {insight.get('ctr', '0')}%")
                print(f"    CPC: ${insight.get('cpc', '0')}")
                print(f"    CPM: ${insight.get('cpm', '0')}")
                print()
            
            # Summary
            if total_impressions > 0:
                overall_ctr = (total_clicks / total_impressions) * 100
                overall_cpc = total_spend / total_clicks if total_clicks > 0 else 0
                overall_cpm = (total_spend / total_impressions) * 1000 if total_impressions > 0 else 0
                
                print(f"📈 30-Day Summary:")
                print(f"  Total Impressions: {total_impressions:,}")
                print(f"  Total Clicks: {total_clicks:,}")
                print(f"  Total Spend: ${total_spend:,.2f}")
                print(f"  Overall CTR: {overall_ctr:.2f}%")
                print(f"  Overall CPC: ${overall_cpc:.2f}")
                print(f"  Overall CPM: ${overall_cpm:.2f}")
            else:
                print(f"  No performance data available for the last 30 days")
                
        except FacebookRequestError as e:
            print(f"  ❌ Performance data not available: {e}")
        
        # Save data to file
        output_data = {
            'account_info': account_info,
            'campaigns': campaign_data,
            'summary': {
                'total_campaigns': len(campaign_data),
                'active_campaigns': active_campaigns,
                'paused_campaigns': paused_campaigns,
                'analysis_date': datetime.now().isoformat()
            }
        }
        
        output_file = f"meta_ads_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        
        print(f"\n💾 Analysis saved to: {output_file}")
        print(f"\n🎉 Analysis Complete!")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Main analysis function"""
    print("Meta Ads Campaign Analysis - Ready to Use!")
    print("Since you already have ads_read permission, this works immediately.\n")
    
    success = analyze_campaigns()
    
    if success:
        print("\n✅ SUCCESS! Your Meta Ads API integration is working perfectly!")
        print("📝 You can now:")
        print("  - Analyze campaign performance")
        print("  - Track ROI and spending")
        print("  - Generate automated reports")
        print("  - Integrate with your CRM system")
    else:
        print("\n❌ Analysis failed. Check your token and permissions.")

if __name__ == "__main__":
    main()
