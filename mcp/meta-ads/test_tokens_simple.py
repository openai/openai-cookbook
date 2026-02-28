#!/usr/bin/env python3
"""
Simple Meta Ads Token Test
=========================

Tests access tokens using the proper Facebook Business SDK methods.
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

def test_token_simple(token_name, token):
    """Test a specific access token using simple methods"""
    print(f"\n🔍 Testing {token_name}...")
    print(f"Token: {token[:20]}...{token[-10:]}")
    
    try:
        # Initialize API without app secret first
        FacebookAdsApi.init(access_token=token)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized successfully")
        
        # Test direct account access
        account = AdAccount(ACCOUNT_ID)
        
        # Try to get campaigns
        campaigns = account.get_campaigns(fields=['id', 'name'], limit=3)
        campaign_count = 0
        campaign_names = []
        
        for campaign in campaigns:
            campaign_count += 1
            campaign_names.append(campaign.get('name', 'Unnamed'))
        
        print(f"  ✅ Found {campaign_count} campaigns:")
        for name in campaign_names:
            print(f"    - {name}")
        
        # Try to get insights
        insights = account.get_insights(fields=['campaign_id', 'campaign_name', 'impressions', 'clicks'], limit=2)
        insight_count = 0
        
        for insight in insights:
            insight_count += 1
        
        print(f"  ✅ Found {insight_count} campaign insights")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def test_token_with_secret(token_name, token):
    """Test token with app secret"""
    print(f"\n🔍 Testing {token_name} with App Secret...")
    
    try:
        # Initialize API with app secret
        FacebookAdsApi.init(app_id=APP_ID, app_secret=APP_SECRET, access_token=token)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized with app secret")
        
        # Test account access
        account = AdAccount(ACCOUNT_ID)
        campaigns = account.get_campaigns(fields=['id', 'name'], limit=3)
        
        campaign_count = 0
        for campaign in campaigns:
            campaign_count += 1
        
        print(f"  ✅ Found {campaign_count} campaigns")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Meta Ads Token Test (Simple)")
    print("=" * 40)
    print(f"App ID: {APP_ID}")
    print(f"Account ID: {ACCOUNT_ID}")
    
    # Test both tokens without app secret
    token1_works = test_token_simple("Access Token 1", ACCESS_TOKEN_1)
    token2_works = test_token_simple("User Access Token", ACCESS_TOKEN_2)
    
    # Test with app secret if simple test failed
    if not token1_works:
        token1_works = test_token_with_secret("Access Token 1", ACCESS_TOKEN_1)
    
    if not token2_works:
        token2_works = test_token_with_secret("User Access Token", ACCESS_TOKEN_2)
    
    # Summary
    print("\n📋 Test Summary")
    print("=" * 20)
    print(f"Access Token 1: {'✅ WORKS' if token1_works else '❌ FAILED'}")
    print(f"User Access Token: {'✅ WORKS' if token2_works else '❌ FAILED'}")
    
    if token1_works and token2_works:
        print("\n🎉 Both tokens work!")
        print("💡 Recommendation: Use the User Access Token")
    elif token1_works:
        print("\n✅ Use Access Token 1")
    elif token2_works:
        print("\n✅ Use User Access Token")
    else:
        print("\n❌ Neither token works.")
        print("🔧 Troubleshooting:")
        print("  1. Check if tokens have expired")
        print("  2. Verify app has access to the ad account")
        print("  3. Ensure tokens have 'ads_read' permission")
        print("  4. Check if account ID is correct")

if __name__ == "__main__":
    main()
