#!/usr/bin/env python3
"""
Meta Ads API - Quick Reference Script
=====================================

This script provides quick examples of the most common Meta Ads API calls
for campaign status detection, similar to Google Ads API documentation.

Usage:
    python meta_ads_quick_reference.py
"""

import os
from datetime import datetime, timedelta
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuration
ACCESS_TOKEN = os.environ.get('META_ADS_ACCESS_TOKEN')
ACCOUNT_ID = os.environ.get('META_ADS_ACCOUNT_ID', 'act_111192969640236')

def quick_campaign_status_check():
    """Quick check for active campaigns"""
    print("🚀 Meta Ads API - Quick Reference")
    print("=" * 40)
    
    if not ACCESS_TOKEN:
        print("❌ META_ADS_ACCESS_TOKEN not found")
        return
    
    try:
        FacebookAdsApi.init(access_token=ACCESS_TOKEN)
        account = AdAccount(ACCOUNT_ID)
        
        # 1. Basic campaign status
        print("\n📊 1. Basic Campaign Status:")
        campaigns = account.get_campaigns(fields=['id', 'name', 'status'])
        
        active_count = 0
        for campaign in campaigns:
            if campaign.get('status') == 'ACTIVE':
                active_count += 1
                print(f"  ✅ {campaign.get('name')}")
        
        print(f"\nTotal Active Campaigns: {active_count}")
        
        # 2. Campaigns with performance data
        print("\n📊 2. Active Campaigns with Performance (Last 7 Days):")
        active_campaigns = account.get_campaigns(fields=['id', 'name'], params={'status': 'ACTIVE'})
        
        for campaign in active_campaigns:
            try:
                insights = campaign.get_insights(fields=['impressions', 'clicks', 'spend'], params={
                    'time_range': {
                        'since': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                        'until': datetime.now().strftime('%Y-%m-%d')
                    }
                })
                
                total_impressions = 0
                total_clicks = 0
                total_spend = 0
                
                for insight in insights:
                    total_impressions += int(insight.get('impressions', 0))
                    total_clicks += int(insight.get('clicks', 0))
                    total_spend += float(insight.get('spend', 0))
                
                if total_impressions > 0:
                    print(f"  📈 {campaign.get('name')}")
                    print(f"     Impressions: {total_impressions:,}")
                    print(f"     Clicks: {total_clicks:,}")
                    print(f"     Spend: ${total_spend:.2f}")
                    print(f"     CTR: {(total_clicks/total_impressions*100):.2f}%")
                    print()
                
            except FacebookRequestError as e:
                print(f"  ⚠️ No data for {campaign.get('name')}: {e}")
        
        # 3. Campaign timing check
        print("\n📊 3. Campaign Timing Check:")
        campaigns_with_timing = account.get_campaigns(fields=[
            'id', 'name', 'status', 'start_time', 'stop_time'
        ])
        
        current_time = datetime.now().replace(tzinfo=None)
        running_now = []
        
        for campaign in campaigns_with_timing:
            if campaign.get('status') == 'ACTIVE':
                start_time = campaign.get('start_time')
                stop_time = campaign.get('stop_time')
                
                is_running = True
                timing_info = "Running"
                
                if start_time:
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00')).replace(tzinfo=None)
                    if current_time < start_dt:
                        is_running = False
                        timing_info = f"Scheduled to start: {start_time}"
                
                if stop_time and is_running:
                    stop_dt = datetime.fromisoformat(stop_time.replace('Z', '+00:00')).replace(tzinfo=None)
                    if current_time > stop_dt:
                        is_running = False
                        timing_info = f"Scheduled to stop: {stop_time}"
                
                if is_running:
                    running_now.append(campaign.get('name'))
                    print(f"  🟢 {campaign.get('name')} - {timing_info}")
                else:
                    print(f"  ⏸️ {campaign.get('name')} - {timing_info}")
        
        print(f"\nCampaigns Running Right Now: {len(running_now)}")
        
        # 4. Account summary
        print("\n📊 4. Account Summary:")
        account_info = account.api_get(fields=['name', 'account_status', 'currency'])
        print(f"  Account: {account_info.get('name')}")
        print(f"  Status: {account_info.get('account_status')}")
        print(f"  Currency: {account_info.get('currency')}")
        
        print("\n✅ Quick Reference Complete!")
        print("\nKey API Calls Used:")
        print("  - account.get_campaigns(fields=['id', 'name', 'status'])")
        print("  - campaign.get_insights(fields=['impressions', 'clicks', 'spend'])")
        print("  - account.api_get(fields=['name', 'account_status', 'currency'])")
        
    except FacebookRequestError as e:
        print(f"❌ API Error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    quick_campaign_status_check()
