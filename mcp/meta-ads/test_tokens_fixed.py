#!/usr/bin/env python3
"""
Meta Ads Token Test - Fixed
===========================

Tests access tokens using correct Facebook Business SDK syntax.
"""

import os
import sys
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Your credentials
APP_ID = "1418814982723549"
APP_SECRET = "3f6473bd7eaed520d689ac599486ef95"
ACCESS_TOKEN_1 = "EAAUKZA5sMF90BPYECnftcpQygYwPg0ZCZAQY32T0sZBZCY1PLy3LZCDmhabZAacMjZCZAgiAjErlqrnL9UEropz1gzGZCeBl24QdCL6imWLkdBB0fIpWUCFuCjnWtbpWSU7ZCNL7Lkyx6JMfPmbkRacbe3GZBlVD0sNJrME2FeMHsdn1EZCkZAAOBuWs0HkSMQO9AECByPsE2cYwhS9ZApxrgx4df78PNmqMkQZCAJbsYmt6G9GeQhoZD"
ACCESS_TOKEN_2 = "EAA6PYOffkGsBPWgaPeQKnwZCBgNqr7ZAvlsZBiytGQJoxZCO8ZCnVHZByAGGmy4MvETgjkhmHtYSYZA21Bglpjl3T7ZCqWZA0LG6nut0DqinhHxYMWk4oL5U9MsYxHlOhMM42DhzKZAFAYwVcemNsVfnWerK26ZCYZCQFkPNz8ZBpJwP9f892Hpsnj0lKcY5nmfiSGasrQPwf96272pehOAnPT13C9RrsZCZCCpfZCmLXnKnHHhRlC0ZD"
ACCOUNT_ID = "act_10150318004158483"

def test_token(token_name, token):
    """Test a specific access token"""
    print(f"\n🔍 Testing {token_name}...")
    print(f"Token: {token[:20]}...{token[-10:]}")
    
    try:
        # Initialize API
        FacebookAdsApi.init(app_id=APP_ID, app_secret=APP_SECRET, access_token=token)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized successfully")
        
        # Test account access
        account = AdAccount(ACCOUNT_ID)
        
        # Get campaigns with correct syntax
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
        
        # Try to get insights
        insights = account.get_insights(fields=['campaign_id', 'campaign_name', 'impressions', 'clicks'])
        insight_count = 0
        
        for insight in insights:
            insight_count += 1
            if insight_count >= 2:  # Limit to 2 for display
                break
        
        print(f"  ✅ Found {insight_count} campaign insights")
        
        # Test account info
        account_info = account.api_get(fields=['name', 'account_status', 'currency'])
        print(f"  ✅ Account: {account_info.get('name', 'Unknown')} ({account_info.get('account_status', 'Unknown')})")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        if "Invalid access token" in str(e):
            print("  💡 Token may have expired or lack permissions")
        elif "Invalid appsecret_proof" in str(e):
            print("  💡 App secret verification failed")
        elif "Insufficient permissions" in str(e):
            print("  💡 Token lacks required permissions (ads_read)")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Meta Ads Token Test - Fixed")
    print("=" * 40)
    print(f"App ID: {APP_ID}")
    print(f"Account ID: {ACCOUNT_ID}")
    
    # Test both tokens
    token1_works = test_token("Access Token 1", ACCESS_TOKEN_1)
    token2_works = test_token("User Access Token", ACCESS_TOKEN_2)
    
    # Summary
    print("\n📋 Test Summary")
    print("=" * 20)
    print(f"Access Token 1: {'✅ WORKS' if token1_works else '❌ FAILED'}")
    print(f"User Access Token: {'✅ WORKS' if token2_works else '❌ FAILED'}")
    
    if token1_works and token2_works:
        print("\n🎉 Both tokens work!")
        print("💡 Recommendation: Use the User Access Token for better permissions")
        print(f"\n📝 Add to your .env file:")
        print(f"META_ADS_ACCESS_TOKEN={ACCESS_TOKEN_2}")
    elif token1_works:
        print("\n✅ Use Access Token 1")
        print(f"\n📝 Add to your .env file:")
        print(f"META_ADS_ACCESS_TOKEN={ACCESS_TOKEN_1}")
    elif token2_works:
        print("\n✅ Use User Access Token")
        print(f"\n📝 Add to your .env file:")
        print(f"META_ADS_ACCESS_TOKEN={ACCESS_TOKEN_2}")
    else:
        print("\n❌ Neither token works.")
        print("🔧 Next steps:")
        print("  1. Check if tokens have expired")
        print("  2. Verify your app has access to ad account 10150318004158483")
        print("  3. Ensure tokens have 'ads_read' permission")
        print("  4. Try generating a new token from Graph API Explorer")

if __name__ == "__main__":
    main()
