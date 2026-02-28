#!/usr/bin/env python3
"""
Meta Ads Campaign Status Detection Script
=========================================

This script demonstrates how to detect active campaigns using the Meta Ads API,
similar to the Google Ads API documentation.

Usage:
    python campaign_status_detection.py
"""

import os
import sys
from datetime import datetime, timedelta
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️ python-dotenv not installed. Using system environment variables only.")

# Configuration from environment variables
ACCESS_TOKEN = os.environ.get('META_ADS_ACCESS_TOKEN')
ACCOUNT_ID = os.environ.get('META_ADS_ACCOUNT_ID', 'act_111192969640236')

def initialize_api():
    """Initialize the Meta Ads API"""
    if not ACCESS_TOKEN:
        print("❌ Error: META_ADS_ACCESS_TOKEN not found in environment variables")
        print("Please set META_ADS_ACCESS_TOKEN in your .env file")
        return None
    
    try:
        FacebookAdsApi.init(access_token=ACCESS_TOKEN)
        account = AdAccount(ACCOUNT_ID)
        return account
    except Exception as e:
        print(f"❌ Error initializing API: {e}")
        return None

def get_basic_campaign_status(account):
    """Get basic campaign status information"""
    print("📊 Basic Campaign Status Check")
    print("=" * 40)
    
    try:
        campaigns = account.get_campaigns(fields=['id', 'name', 'status', 'effective_status'])
        
        active_count = 0
        paused_count = 0
        deleted_count = 0
        
        print("Campaign Status Summary:")
        for campaign in campaigns:
            status = campaign.get('status')
            effective_status = campaign.get('effective_status')
            
            if status == 'ACTIVE':
                active_count += 1
                print(f"  ✅ ACTIVE: {campaign.get('name')}")
            elif status == 'PAUSED':
                paused_count += 1
                print(f"  ⏸️ PAUSED: {campaign.get('name')}")
            elif status == 'DELETED':
                deleted_count += 1
                print(f"  🗑️ DELETED: {campaign.get('name')}")
        
        print(f"\nSummary:")
        print(f"  Active: {active_count}")
        print(f"  Paused: {paused_count}")
        print(f"  Deleted: {deleted_count}")
        print(f"  Total: {active_count + paused_count + deleted_count}")
        
        return campaigns
        
    except FacebookRequestError as e:
        print(f"❌ API Error: {e}")
        return None

def get_detailed_campaign_status(account):
    """Get detailed campaign status with timing information"""
    print("\n📊 Detailed Campaign Status with Timing")
    print("=" * 50)
    
    try:
        campaigns = account.get_campaigns(fields=[
            'id', 'name', 'status', 'effective_status',
            'created_time', 'updated_time', 'start_time', 'stop_time',
            'budget_remaining', 'daily_budget', 'lifetime_budget'
        ])
        
        current_time = datetime.now()
        running_now = []
        
        print("Detailed Campaign Analysis:")
        for campaign in campaigns:
            status = campaign.get('status')
            effective_status = campaign.get('effective_status')
            start_time = campaign.get('start_time')
            stop_time = campaign.get('stop_time')
            budget_remaining = campaign.get('budget_remaining')
            
            # Determine if campaign is running now
            is_running_now = False
            timing_status = ""
            
            if status == 'ACTIVE' and effective_status == 'ACTIVE':
                if start_time:
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    if current_time < start_dt:
                        timing_status = "⏰ Scheduled to start"
                    else:
                        is_running_now = True
                        timing_status = "🟢 Running now"
                else:
                    is_running_now = True
                    timing_status = "🟢 Running now"
                
                if stop_time and is_running_now:
                    stop_dt = datetime.fromisoformat(stop_time.replace('Z', '+00:00'))
                    if current_time > stop_dt:
                        is_running_now = False
                        timing_status = "⏹️ Scheduled to stop"
            
            if is_running_now:
                running_now.append(campaign)
            
            print(f"\n  Campaign: {campaign.get('name')}")
            print(f"    ID: {campaign.get('id')}")
            print(f"    Status: {status}")
            print(f"    Effective Status: {effective_status}")
            print(f"    Timing: {timing_status}")
            print(f"    Budget Remaining: ${budget_remaining}")
            print(f"    Daily Budget: ${campaign.get('daily_budget')}")
            print(f"    Lifetime Budget: ${campaign.get('lifetime_budget')}")
            print(f"    Created: {campaign.get('created_time')}")
            print(f"    Updated: {campaign.get('updated_time')}")
            if start_time:
                print(f"    Start Time: {start_time}")
            if stop_time:
                print(f"    Stop Time: {stop_time}")
        
        print(f"\n🎯 Campaigns Currently Running: {len(running_now)}")
        for campaign in running_now:
            print(f"  ✅ {campaign.get('name')} (ID: {campaign.get('id')})")
        
        return running_now
        
    except FacebookRequestError as e:
        print(f"❌ API Error: {e}")
        return None

def get_campaign_performance_status(account):
    """Get campaign status with performance metrics"""
    print("\n📊 Campaign Performance Status (Last 7 Days)")
    print("=" * 55)
    
    try:
        campaigns = account.get_campaigns(fields=['id', 'name', 'status', 'effective_status'])
        
        performance_data = []
        
        for campaign in campaigns:
            if campaign.get('status') == 'ACTIVE':
                try:
                    # Get insights for the last 7 days
                    insights = campaign.get_insights(fields=[
                        'impressions', 'clicks', 'spend', 'ctr', 'cpc', 'cpm'
                    ], params={
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
                    
                    ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
                    cpc = total_spend / total_clicks if total_clicks > 0 else 0
                    cpm = (total_spend / total_impressions * 1000) if total_impressions > 0 else 0
                    
                    performance_data.append({
                        'name': campaign.get('name'),
                        'id': campaign.get('id'),
                        'impressions': total_impressions,
                        'clicks': total_clicks,
                        'spend': total_spend,
                        'ctr': ctr,
                        'cpc': cpc,
                        'cpm': cpm
                    })
                    
                except FacebookRequestError as e:
                    print(f"  ⚠️ Could not get performance data for {campaign.get('name')}: {e}")
        
        print("Active Campaigns Performance:")
        for data in performance_data:
            print(f"\n  Campaign: {data['name']}")
            print(f"    Impressions: {data['impressions']:,}")
            print(f"    Clicks: {data['clicks']:,}")
            print(f"    Spend: ${data['spend']:.2f}")
            print(f"    CTR: {data['ctr']:.2f}%")
            print(f"    CPC: ${data['cpc']:.2f}")
            print(f"    CPM: ${data['cpm']:.2f}")
        
        return performance_data
        
    except FacebookRequestError as e:
        print(f"❌ API Error: {e}")
        return None

def get_campaign_status_summary(account):
    """Get a comprehensive summary of all campaign statuses"""
    print("\n📊 Comprehensive Campaign Status Summary")
    print("=" * 50)
    
    try:
        campaigns = account.get_campaigns(fields=[
            'id', 'name', 'status', 'effective_status',
            'created_time', 'updated_time', 'start_time', 'stop_time',
            'budget_remaining', 'daily_budget', 'lifetime_budget'
        ])
        
        summary = {
            'total_campaigns': 0,
            'active_campaigns': 0,
            'paused_campaigns': 0,
            'deleted_campaigns': 0,
            'campaigns_with_budget': 0,
            'campaigns_running_now': 0,
            'campaign_details': []
        }
        
        current_time = datetime.now()
        
        for campaign in campaigns:
            summary['total_campaigns'] += 1
            
            status = campaign.get('status')
            effective_status = campaign.get('effective_status')
            
            # Count by status
            if status == 'ACTIVE':
                summary['active_campaigns'] += 1
            elif status == 'PAUSED':
                summary['paused_campaigns'] += 1
            elif status == 'DELETED':
                summary['deleted_campaigns'] += 1
            
            # Check if campaign has budget
            budget_remaining = campaign.get('budget_remaining')
            if budget_remaining and float(budget_remaining) > 0:
                summary['campaigns_with_budget'] += 1
            
            # Check if campaign is running now
            is_running_now = False
            if status == 'ACTIVE' and effective_status == 'ACTIVE':
                start_time = campaign.get('start_time')
                stop_time = campaign.get('stop_time')
                
                if start_time:
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    if current_time >= start_dt:
                        is_running_now = True
                else:
                    is_running_now = True
                
                if stop_time and is_running_now:
                    stop_dt = datetime.fromisoformat(stop_time.replace('Z', '+00:00'))
                    if current_time > stop_dt:
                        is_running_now = False
            
            if is_running_now:
                summary['campaigns_running_now'] += 1
            
            # Add campaign details
            summary['campaign_details'].append({
                'id': campaign.get('id'),
                'name': campaign.get('name'),
                'status': status,
                'effective_status': effective_status,
                'is_running_now': is_running_now,
                'budget_remaining': budget_remaining,
                'daily_budget': campaign.get('daily_budget'),
                'lifetime_budget': campaign.get('lifetime_budget'),
                'created_time': campaign.get('created_time'),
                'updated_time': campaign.get('updated_time'),
                'start_time': campaign.get('start_time'),
                'stop_time': campaign.get('stop_time')
            })
        
        print("Campaign Status Summary:")
        print(f"  Total Campaigns: {summary['total_campaigns']}")
        print(f"  Active Campaigns: {summary['active_campaigns']}")
        print(f"  Paused Campaigns: {summary['paused_campaigns']}")
        print(f"  Deleted Campaigns: {summary['deleted_campaigns']}")
        print(f"  Campaigns with Budget: {summary['campaigns_with_budget']}")
        print(f"  Campaigns Running Now: {summary['campaigns_running_now']}")
        
        print(f"\n🎯 Currently Active Campaigns:")
        for campaign in summary['campaign_details']:
            if campaign['is_running_now']:
                print(f"  ✅ {campaign['name']} (ID: {campaign['id']})")
                print(f"     Status: {campaign['status']}")
                print(f"     Effective Status: {campaign['effective_status']}")
                print(f"     Budget Remaining: ${campaign['budget_remaining']}")
                print()
        
        return summary
        
    except FacebookRequestError as e:
        print(f"❌ API Error: {e}")
        return None

def main():
    """Main function to demonstrate campaign status detection"""
    print("🚀 Meta Ads Campaign Status Detection")
    print("=" * 50)
    print(f"Account: {ACCOUNT_ID}")
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize API
    account = initialize_api()
    if not account:
        return
    
    # Get account info
    try:
        account_info = account.api_get(fields=['name', 'account_status', 'currency'])
        print(f"Account Name: {account_info.get('name', 'Unknown')}")
        print(f"Account Status: {account_info.get('account_status', 'Unknown')}")
        print(f"Currency: {account_info.get('currency', 'Unknown')}")
    except Exception as e:
        print(f"⚠️ Could not get account info: {e}")
    
    # Run all status checks
    basic_status = get_basic_campaign_status(account)
    if basic_status:
        detailed_status = get_detailed_campaign_status(account)
        performance_status = get_campaign_performance_status(account)
        summary = get_campaign_status_summary(account)
    
    print("\n🎉 Campaign Status Detection Complete!")
    print("=" * 50)
    print("This script demonstrates how to:")
    print("✅ Check basic campaign status (ACTIVE, PAUSED, DELETED)")
    print("✅ Get detailed status with timing information")
    print("✅ Monitor campaign performance metrics")
    print("✅ Generate comprehensive status summaries")
    print("✅ Identify campaigns currently running")

if __name__ == "__main__":
    main()
