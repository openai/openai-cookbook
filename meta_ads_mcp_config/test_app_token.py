#!/usr/bin/env python3
"""
Test Meta Ads with App Token
============================

Test using App Token instead of User Access Token.
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

def test_app_token():
    """Test using App Token"""
    print("🚀 Meta Ads App Token Test")
    print("=" * 30)
    
    # Generate App Token (App ID + App Secret)
    app_token = f"{APP_ID}|{APP_SECRET}"
    print(f"App Token: {app_token[:20]}...{app_token[-10:]}")
    
    try:
        # Initialize API with App Token
        FacebookAdsApi.init(app_id=APP_ID, app_secret=APP_SECRET, access_token=app_token)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized with App Token")
        
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
        
        print(f"\n🎉 SUCCESS! App Token works!")
        print(f"\n📝 Use this App Token in your .env file:")
        print(f"META_ADS_ACCESS_TOKEN={app_token}")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        if "permission" in str(e).lower():
            print("  💡 App still needs access to the ad account")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_app_token()
