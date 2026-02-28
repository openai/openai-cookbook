#!/usr/bin/env python3
"""
Quick Meta Ads Token Test
========================

Test your new token with ads_read permission.
"""

import os
import sys
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Your credentials
APP_ID = "1418814982723549"
APP_SECRET = "3f6473bd7eaed520d689ac599486ef95"
ACCOUNT_ID = "act_10150318004158483"

def test_new_token():
    """Test the new token you'll provide"""
    print("🚀 Meta Ads Token Test")
    print("=" * 30)
    print("Please paste your NEW token with ads_read permission:")
    print("(The one you just generated from Graph API Explorer)")
    
    # Get token from user
    new_token = input("\nEnter your new access token: ").strip()
    
    if not new_token:
        print("❌ No token provided")
        return
    
    print(f"\n🔍 Testing token: {new_token[:20]}...{new_token[-10:]}")
    
    try:
        # Initialize API
        FacebookAdsApi.init(app_id=APP_ID, app_secret=APP_SECRET, access_token=new_token)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized successfully")
        
        # Test account access
        account = AdAccount(ACCOUNT_ID)
        
        # Get campaigns
        campaigns = account.get_campaigns(fields=['id', 'name'])
        campaign_count = 0
        campaign_names = []
        
        for campaign in campaigns:
            campaign_count += 1
            campaign_names.append(campaign.get('name', 'Unnamed'))
            if campaign_count >= 3:  # Limit to 3 for display
                break
        
        print(f"  ✅ Found {campaign_count} campaigns:")
        for name in campaign_names:
            print(f"    - {name}")
        
        # Get insights
        insights = account.get_insights(fields=['campaign_id', 'campaign_name', 'impressions', 'clicks'])
        insight_count = 0
        
        for insight in insights:
            insight_count += 1
            if insight_count >= 2:  # Limit to 2 for display
                break
        
        print(f"  ✅ Found {insight_count} campaign insights")
        
        # Get account info
        account_info = account.api_get(fields=['name', 'account_status', 'currency'])
        print(f"  ✅ Account: {account_info.get('name', 'Unknown')} ({account_info.get('account_status', 'Unknown')})")
        
        print(f"\n🎉 SUCCESS! Your token works perfectly!")
        print(f"\n📝 Add this to your .env file:")
        print(f"META_ADS_ACCESS_TOKEN={new_token}")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        if "ads_read" in str(e).lower():
            print("  💡 Token still lacks ads_read permission")
        elif "Invalid access token" in str(e):
            print("  💡 Token may be invalid or expired")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_new_token()
