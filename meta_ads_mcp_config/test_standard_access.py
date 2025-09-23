#!/usr/bin/env python3
"""
Meta Ads Standard Access Test
============================

Test with the account that's actually connected to your app.
Based on your Business Suite screenshot, account 111192969640236 is active.
"""

import os
import sys
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Your credentials
APP_ID = "1418814982723549"
APP_SECRET = "3f6473bd7eaed520d689ac599486ef95"

# The account from your Business Suite screenshot
CONNECTED_ACCOUNT_ID = "act_111192969640236"

def test_standard_access():
    """Test with Standard Access using the connected account"""
    print("🚀 Meta Ads Standard Access Test")
    print("=" * 40)
    print(f"App ID: {APP_ID}")
    print(f"Testing account from Business Suite: {CONNECTED_ACCOUNT_ID}")
    
    # Generate App Token (this should work with Standard Access)
    app_token = f"{APP_ID}|{APP_SECRET}"
    print(f"App Token: {app_token[:20]}...{app_token[-10:]}")
    
    try:
        # Initialize API with App Token
        FacebookAdsApi.init(app_id=APP_ID, app_secret=APP_SECRET, access_token=app_token)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized successfully")
        
        # Test account access
        account = AdAccount(CONNECTED_ACCOUNT_ID)
        
        # Get account info first
        account_info = account.api_get(fields=['name', 'account_status', 'currency', 'timezone_name'])
        print(f"  ✅ Account: {account_info.get('name', 'Unknown')}")
        print(f"  ✅ Status: {account_info.get('account_status', 'Unknown')}")
        print(f"  ✅ Currency: {account_info.get('currency', 'Unknown')}")
        
        # Get campaigns
        campaigns = account.get_campaigns(fields=['id', 'name', 'status'])
        campaign_count = 0
        campaign_names = []
        
        for campaign in campaigns:
            campaign_count += 1
            campaign_names.append(f"{campaign.get('name', 'Unnamed')} ({campaign.get('status', 'Unknown')})")
            if campaign_count >= 5:  # Show up to 5 campaigns
                break
        
        print(f"  ✅ Found {campaign_count} campaigns:")
        for name in campaign_names:
            print(f"    - {name}")
        
        # Try to get insights (this is what we really need)
        insights = account.get_insights(fields=['campaign_id', 'campaign_name', 'impressions', 'clicks', 'spend'])
        insight_count = 0
        
        for insight in insights:
            insight_count += 1
            if insight_count >= 3:  # Show up to 3 insights
                break
        
        print(f"  ✅ Found {insight_count} campaign insights")
        
        print(f"\n🎉 SUCCESS! Standard Access works!")
        print(f"\n📝 Use these credentials:")
        print(f"META_ADS_ACCESS_TOKEN={app_token}")
        print(f"META_ADS_ACCOUNT_ID={CONNECTED_ACCOUNT_ID}")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        if "permission" in str(e).lower():
            print("  💡 Still need App Review for ads_read permission")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def test_user_token():
    """Test with a simple user token approach"""
    print(f"\n🔍 Alternative: Testing with User Token approach...")
    
    # Try without app secret (sometimes works better)
    try:
        FacebookAdsApi.init(access_token=f"{APP_ID}|{APP_SECRET}")
        api = FacebookAdsApi.get_default_api()
        
        account = AdAccount(CONNECTED_ACCOUNT_ID)
        campaigns = account.get_campaigns(fields=['id', 'name'])
        
        campaign_count = 0
        for campaign in campaigns:
            campaign_count += 1
            if campaign_count >= 3:
                break
        
        print(f"  ✅ User Token approach found {campaign_count} campaigns")
        return True
        
    except Exception as e:
        print(f"  ❌ User Token approach failed: {e}")
        return False

def main():
    """Main test function"""
    # Test Standard Access
    standard_works = test_standard_access()
    
    # Test alternative approach
    if not standard_works:
        user_token_works = test_user_token()
    
    # Summary
    print("\n📋 Final Summary")
    print("=" * 20)
    if standard_works:
        print("✅ Standard Access works! You can proceed with:")
        print(f"   META_ADS_ACCESS_TOKEN={APP_ID}|{APP_SECRET}")
        print(f"   META_ADS_ACCOUNT_ID={CONNECTED_ACCOUNT_ID}")
    else:
        print("❌ Standard Access not working yet.")
        print("💡 Next steps:")
        print("   1. Submit App Review for ads_read permission")
        print("   2. Or use System User Token from Business Manager")
        print("   3. Or try generating a User Access Token from Graph API Explorer")

if __name__ == "__main__":
    main()
