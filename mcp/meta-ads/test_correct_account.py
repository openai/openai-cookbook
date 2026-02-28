#!/usr/bin/env python3
"""
Test Meta Ads with Correct Account ID
=====================================

Test using the account ID that's actually connected to your app.
"""

import os
import sys
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Your credentials
APP_ID = "1418814982723549"
APP_SECRET = "3f6473bd7eaed520d689ac599486ef95"

# Test both account IDs
ACCOUNT_ID_1 = "act_10150318004158483"  # The one you provided
ACCOUNT_ID_2 = "act_111192969640236"    # The one connected to your app

def test_account(account_id, account_name):
    """Test access to a specific account"""
    print(f"\n🔍 Testing {account_name} ({account_id})...")
    
    # Generate App Token
    app_token = f"{APP_ID}|{APP_SECRET}"
    
    try:
        # Initialize API with App Token
        FacebookAdsApi.init(app_id=APP_ID, app_secret=APP_SECRET, access_token=app_token)
        api = FacebookAdsApi.get_default_api()
        
        # Test account access
        account = AdAccount(account_id)
        
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
        
        # Get account info
        account_info = account.api_get(fields=['name', 'account_status', 'currency'])
        print(f"  ✅ Account: {account_info.get('name', 'Unknown')} ({account_info.get('account_status', 'Unknown')})")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Meta Ads Account Test")
    print("=" * 40)
    print(f"App ID: {APP_ID}")
    print("Testing both account IDs...")
    
    # Test both accounts
    account1_works = test_account(ACCOUNT_ID_1, "Your Provided Account")
    account2_works = test_account(ACCOUNT_ID_2, "App Connected Account")
    
    # Summary
    print("\n📋 Test Summary")
    print("=" * 20)
    print(f"Account 1 ({ACCOUNT_ID_1}): {'✅ WORKS' if account1_works else '❌ FAILED'}")
    print(f"Account 2 ({ACCOUNT_ID_2}): {'✅ WORKS' if account2_works else '❌ FAILED'}")
    
    if account2_works:
        print(f"\n🎉 SUCCESS! Use the connected account:")
        print(f"META_ADS_ACCOUNT_ID={ACCOUNT_ID_2}")
        print(f"\n📝 App Token that works:")
        print(f"META_ADS_ACCESS_TOKEN={APP_ID}|{APP_SECRET}")
    elif account1_works:
        print(f"\n✅ Your provided account works!")
        print(f"META_ADS_ACCOUNT_ID={ACCOUNT_ID_1}")
    else:
        print("\n❌ Neither account works.")
        print("💡 Make sure to add your account ID to the app settings first!")

if __name__ == "__main__":
    main()
