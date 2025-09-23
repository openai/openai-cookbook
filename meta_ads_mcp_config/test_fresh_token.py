#!/usr/bin/env python3
"""
Meta Ads API Test with Fresh Token
==================================

Test with a fresh access token from Graph API Explorer
"""

import os
import sys
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Your app credentials
APP_ID = "4098296043769963"
APP_SECRET = "3f6473bd7eaed520d689ac599486ef95"

# Test account
TEST_ACCOUNT_ID = "act_111192969640236"

def test_with_fresh_token():
    """Test with a fresh access token"""
    print("🚀 Meta Ads API Test with Fresh Token")
    print("=" * 40)
    
    # Fresh token from Graph API Explorer
    FRESH_TOKEN = "EAA6PYOffkGsBPZAjEO7NNEZB3uaNWZAZCBnboIeESIQ4kEVXc2ZAikZC3AW5JhReQx4y9Lg5jCnOHZCbmLIRB1OrA6qF5yHLKITx7MjoTWgtpaqYqLYKmH34W5ZBsE6tIpZBVUIUKSpfZB97XPtNxAeTD7CSZB5plnuh2gUaTirZCuXjRErfzZAUQvZCt5ZAqdLZAMOshmrdJsIbeZAbZCyNh4u6qb4Ob2nf5S1Wt9VAKSd3nnIRVlGVMged0LQPXBjfAEd1XpXLjZC93vqo1FXn0nd3AZDZD"
    
    if FRESH_TOKEN == "YOUR_FRESH_TOKEN_HERE":
        print("❌ Please replace FRESH_TOKEN with a new token from Graph API Explorer")
        print("\n📝 Steps to get fresh token:")
        print("1. Go to: https://developers.facebook.com/tools/explorer/")
        print("2. Select app: Colppy Ads Integration")
        print("3. Click 'Generate Access Token'")
        print("4. Add 'ads_read' permission")
        print("5. Copy the token and replace FRESH_TOKEN in this script")
        return False
    
    try:
        # Initialize API with fresh token
        FacebookAdsApi.init(access_token=FRESH_TOKEN)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized with fresh token")
        
        # Test account access
        account = AdAccount(TEST_ACCOUNT_ID)
        
        # Get account info
        account_info = account.api_get(fields=['name', 'account_status', 'currency'])
        print(f"  ✅ Account: {account_info.get('name', 'Unknown')}")
        print(f"  ✅ Status: {account_info.get('account_status', 'Unknown')}")
        
        # Get campaigns
        campaigns = account.get_campaigns(fields=['id', 'name'], params={'summary': 'true'})
        campaign_count = 0
        for campaign in campaigns:
            campaign_count += 1
            if campaign_count >= 3:
                break
        
        print(f"  ✅ Found {campaign_count} campaigns")
        print("  ✅ ads_read permission test successful!")
        
        print(f"\n🎉 SUCCESS! Test API call completed!")
        print(f"📝 The 'Request advanced access' button should become active within 24 hours")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_with_fresh_token()
