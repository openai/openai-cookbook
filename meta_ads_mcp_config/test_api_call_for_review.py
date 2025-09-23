#!/usr/bin/env python3
"""
Meta Ads API Test Call for App Review
=====================================

This script makes a test API call to satisfy Meta's requirement
for requesting advanced access to ads_read permission.

The warning says: "To request advanced access to this permission, 
you need to make a successful test API call. It may take up to 24 hours 
after the first API call for this button to become active."
"""

import os
import sys
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Your app credentials
APP_ID = "4098296043769963"  # From your screenshot
APP_SECRET = "3f6473bd7eaed520d689ac599486ef95"  # Your app secret

# Test with the account from your Business Suite
TEST_ACCOUNT_ID = "act_111192969640236"

def make_test_api_call():
    """Make a test API call to satisfy Meta's requirement"""
    print("🚀 Meta Ads API Test Call for App Review")
    print("=" * 50)
    print(f"App ID: {APP_ID}")
    print(f"Test Account: {TEST_ACCOUNT_ID}")
    
    # Generate App Token
    app_token = f"{APP_ID}|{APP_SECRET}"
    print(f"App Token: {app_token[:20]}...{app_token[-10:]}")
    
    try:
        # Initialize API
        FacebookAdsApi.init(app_id=APP_ID, app_secret=APP_SECRET, access_token=app_token)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized successfully")
        
        # Test 1: Get account info (basic call)
        print("\n📊 Test 1: Getting account information...")
        account = AdAccount(TEST_ACCOUNT_ID)
        
        try:
            account_info = account.api_get(fields=['name', 'account_status', 'currency'])
            print(f"  ✅ Account: {account_info.get('name', 'Unknown')}")
            print(f"  ✅ Status: {account_info.get('account_status', 'Unknown')}")
            print(f"  ✅ Currency: {account_info.get('currency', 'Unknown')}")
        except FacebookRequestError as e:
            print(f"  ❌ Account info failed: {e}")
            return False
        
        # Test 2: Try to get campaigns (this should trigger ads_read)
        print("\n📊 Test 2: Getting campaigns (ads_read test)...")
        try:
            campaigns = account.get_campaigns(fields=['id', 'name'], params={'summary': 'true'})
            campaign_count = 0
            for campaign in campaigns:
                campaign_count += 1
                if campaign_count >= 3:  # Limit to 3 for test
                    break
            
            print(f"  ✅ Found {campaign_count} campaigns")
            print("  ✅ ads_read permission test successful!")
            
        except FacebookRequestError as e:
            print(f"  ❌ Campaigns failed: {e}")
            if "permission" in str(e).lower():
                print("  💡 Still need ads_read permission - this is expected")
                return False
        
        # Test 3: Try to get insights (this definitely requires ads_read)
        print("\n📊 Test 3: Getting campaign insights (ads_read test)...")
        try:
            insights = account.get_insights(fields=['campaign_id', 'campaign_name', 'impressions', 'clicks'])
            insight_count = 0
            for insight in insights:
                insight_count += 1
                if insight_count >= 2:  # Limit to 2 for test
                    break
            
            print(f"  ✅ Found {insight_count} insights")
            print("  ✅ ads_read permission test successful!")
            
        except FacebookRequestError as e:
            print(f"  ❌ Insights failed: {e}")
            if "permission" in str(e).lower():
                print("  💡 Still need ads_read permission - this is expected")
                return False
        
        print(f"\n🎉 SUCCESS! Test API call completed!")
        print(f"📝 The 'Request advanced access' button should become active within 24 hours")
        print(f"🔄 Check back tomorrow to submit for App Review")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def test_with_user_token():
    """Alternative test with user token"""
    print(f"\n🔍 Alternative: Testing with User Token...")
    
    # Try with a user token if available
    user_token = "EAAUKZA5sMF90BPYECnftcpQygYwPg0ZCZAQY32T0sZBZCY1PLy3LZCDmhabZAacMjZCZAgiAjErlqrnL9UEropz1gzGZCeBl24QdCL6imWLkdBB0fIpWUCFuCjnWtbpWSU7ZCNL7Lkyx6JMfPmbkRacbe3GZBlVD0sNJrME2FeMHsdn1EZCkZAAOBuWs0HkSMQO9AECByPsE2cYwhS9ZApxrgx4df78PNmqMkQZCAJbsYmt6G9GeQhoZD"
    
    try:
        FacebookAdsApi.init(access_token=user_token)
        api = FacebookAdsApi.get_default_api()
        
        account = AdAccount(TEST_ACCOUNT_ID)
        campaigns = account.get_campaigns(fields=['id', 'name'], params={'summary': 'true'})
        
        campaign_count = 0
        for campaign in campaigns:
            campaign_count += 1
            if campaign_count >= 3:
                break
        
        print(f"  ✅ User Token test found {campaign_count} campaigns")
        return True
        
    except Exception as e:
        print(f"  ❌ User Token test failed: {e}")
        return False

def main():
    """Main test function"""
    print("This script makes a test API call to satisfy Meta's requirement")
    print("for requesting advanced access to ads_read permission.\n")
    
    # Test with App Token
    app_token_success = make_test_api_call()
    
    # Test with User Token if App Token fails
    if not app_token_success:
        user_token_success = test_with_user_token()
    
    # Summary
    print("\n📋 Final Summary")
    print("=" * 20)
    if app_token_success or user_token_success:
        print("✅ Test API call completed!")
        print("📝 Check back in 24 hours to see if 'Request advanced access' button is active")
        print("🔄 Then you can submit for App Review")
    else:
        print("❌ Test API call failed")
        print("💡 You may need to:")
        print("   1. Wait for the app to be fully activated")
        print("   2. Try with a different access token")
        print("   3. Contact Meta support if issues persist")

if __name__ == "__main__":
    main()
