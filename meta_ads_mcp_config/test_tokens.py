#!/usr/bin/env python3
"""
Meta Ads Token Test Script
=========================

Tests both access tokens to determine which one works best.
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
        
        # Test 1: Basic API call
        print("  ✅ API initialized successfully")
        
        # Test 2: Get user info
        me = api.call('GET', 'https://graph.facebook.com/v18.0/me')
        print(f"  ✅ User info: {me.get('name', 'Unknown')}")
        
        # Test 3: Get ad accounts
        accounts_response = api.call('GET', 'https://graph.facebook.com/v18.0/me/adaccounts')
        accounts = accounts_response.get('data', [])
        print(f"  ✅ Found {len(accounts)} ad accounts")
        
        # Test 4: Test specific account access
        account = AdAccount(ACCOUNT_ID)
        campaigns = account.get_campaigns(fields=['id', 'name'], limit=5)
        campaign_count = 0
        for campaign in campaigns:
            campaign_count += 1
        
        print(f"  ✅ Access to account {ACCOUNT_ID}: Found {campaign_count} campaigns")
        
        # Test 5: Get campaign insights
        insights = account.get_insights(fields=['campaign_id', 'campaign_name', 'impressions', 'clicks', 'spend'], limit=3)
        insight_count = 0
        for insight in insights:
            insight_count += 1
        
        print(f"  ✅ Campaign insights: Found {insight_count} insights")
        
        return True
        
    except FacebookRequestError as e:
        print(f"  ❌ Facebook API Error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Meta Ads Token Test")
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
        print("\n🎉 Both tokens work! Use either one.")
        print("💡 Recommendation: Use the User Access Token for better permissions")
    elif token1_works:
        print("\n✅ Use Access Token 1")
    elif token2_works:
        print("\n✅ Use User Access Token")
    else:
        print("\n❌ Neither token works. Please check your credentials and permissions.")

if __name__ == "__main__":
    main()
