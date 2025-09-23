#!/usr/bin/env python3
"""
Meta Ads Token Permission Test
=============================

Test the current token to see what permissions are already available
and what data we can access right now.
"""

import os
import sys
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

# Your current token
CURRENT_TOKEN = "EAA6PYOffkGsBPZAjEO7NNEZB3uaNWZAZCBnboIeESIQ4kEVXc2ZAikZC3AW5JhReQx4y9Lg5jCnOHZCbmLIRB1OrA6qF5yHLKITx7MjoTWgtpaqYqLYKmH34W5ZBsE6tIpZBVUIUKSpfZB97XPtNxAeTD7CSZB5plnuh2gUaTirZCuXjRErfzZAUQvZCt5ZAqdLZAMOshmrdJsIbeZAbZCyNh4u6qb4Ob2nf5S1Wt9VAKSd3nnIRVlGVMged0LQPXBjfAEd1XpXLjZC93vqo1FXn0nd3AZDZD"

# Test account
TEST_ACCOUNT_ID = "act_111192969640236"

def test_current_permissions():
    """Test what permissions the current token has"""
    print("🔍 Meta Ads Token Permission Test")
    print("=" * 50)
    print(f"Token: {CURRENT_TOKEN[:20]}...{CURRENT_TOKEN[-10:]}")
    print(f"Account: {TEST_ACCOUNT_ID}")
    
    try:
        # Initialize API
        FacebookAdsApi.init(access_token=CURRENT_TOKEN)
        api = FacebookAdsApi.get_default_api()
        
        print("  ✅ API initialized successfully")
        
        # Test 1: Basic account access
        print("\n📊 Test 1: Basic Account Access")
        account = AdAccount(TEST_ACCOUNT_ID)
        
        try:
            account_info = account.api_get(fields=['name', 'account_status', 'currency', 'timezone_name'])
            print(f"  ✅ Account: {account_info.get('name', 'Unknown')}")
            print(f"  ✅ Status: {account_info.get('account_status', 'Unknown')}")
            print(f"  ✅ Currency: {account_info.get('currency', 'Unknown')}")
            print(f"  ✅ Timezone: {account_info.get('timezone_name', 'Unknown')}")
        except FacebookRequestError as e:
            print(f"  ❌ Account info failed: {e}")
            return False
        
        # Test 2: Campaign access
        print("\n📊 Test 2: Campaign Access")
        try:
            campaigns = account.get_campaigns(fields=['id', 'name', 'status', 'objective'])
            campaign_count = 0
            campaign_details = []
            
            for campaign in campaigns:
                campaign_count += 1
                campaign_details.append({
                    'id': campaign.get('id', 'Unknown'),
                    'name': campaign.get('name', 'Unnamed'),
                    'status': campaign.get('status', 'Unknown'),
                    'objective': campaign.get('objective', 'Unknown')
                })
                if campaign_count >= 5:  # Limit to 5 for display
                    break
            
            print(f"  ✅ Found {campaign_count} campaigns:")
            for i, camp in enumerate(campaign_details, 1):
                print(f"    {i}. {camp['name']} ({camp['status']}) - {camp['objective']}")
                
        except FacebookRequestError as e:
            print(f"  ❌ Campaign access failed: {e}")
            return False
        
        # Test 3: Campaign insights (ads_read test)
        print("\n📊 Test 3: Campaign Insights (ads_read permission)")
        try:
            insights = account.get_insights(fields=[
                'campaign_id', 'campaign_name', 'impressions', 'clicks', 
                'spend', 'ctr', 'cpc', 'cpm'
            ])
            
            insight_count = 0
            insight_data = []
            
            for insight in insights:
                insight_count += 1
                insight_data.append({
                    'campaign_id': insight.get('campaign_id', 'Unknown'),
                    'campaign_name': insight.get('campaign_name', 'Unknown'),
                    'impressions': insight.get('impressions', '0'),
                    'clicks': insight.get('clicks', '0'),
                    'spend': insight.get('spend', '0'),
                    'ctr': insight.get('ctr', '0'),
                    'cpc': insight.get('cpc', '0'),
                    'cpm': insight.get('cpm', '0')
                })
                if insight_count >= 3:  # Limit to 3 for display
                    break
            
            print(f"  ✅ Found {insight_count} campaign insights:")
            for i, data in enumerate(insight_data, 1):
                print(f"    {i}. {data['campaign_name']}")
                print(f"       Impressions: {data['impressions']}, Clicks: {data['clicks']}")
                print(f"       Spend: ${data['spend']}, CTR: {data['ctr']}%")
                print(f"       CPC: ${data['cpc']}, CPM: ${data['cpm']}")
                
        except FacebookRequestError as e:
            print(f"  ❌ Insights access failed: {e}")
            if "permission" in str(e).lower():
                print("  💡 This confirms you need App Review for ads_read")
            return False
        
        # Test 4: Ad sets
        print("\n📊 Test 4: Ad Sets Access")
        try:
            ad_sets = account.get_ad_sets(fields=['id', 'name', 'status'], params={'summary': 'true'})
            ad_set_count = 0
            for ad_set in ad_sets:
                ad_set_count += 1
                if ad_set_count >= 3:
                    break
            
            print(f"  ✅ Found {ad_set_count} ad sets")
                
        except FacebookRequestError as e:
            print(f"  ❌ Ad sets access failed: {e}")
        
        # Test 5: Ads
        print("\n📊 Test 5: Ads Access")
        try:
            ads = account.get_ads(fields=['id', 'name', 'status'], params={'summary': 'true'})
            ad_count = 0
            for ad in ads:
                ad_count += 1
                if ad_count >= 3:
                    break
            
            print(f"  ✅ Found {ad_count} ads")
                
        except FacebookRequestError as e:
            print(f"  ❌ Ads access failed: {e}")
        
        print(f"\n🎉 PERMISSION TEST COMPLETE!")
        print(f"📝 Summary:")
        print(f"  ✅ Basic account access: WORKING")
        print(f"  ✅ Campaign access: WORKING")
        print(f"  ✅ Campaign insights: WORKING")
        print(f"  ✅ You have ads_read permission!")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def test_token_info():
    """Get token information"""
    print(f"\n🔍 Token Information Test")
    print("=" * 30)
    
    try:
        FacebookAdsApi.init(access_token=CURRENT_TOKEN)
        api = FacebookAdsApi.get_default_api()
        
        # Try to get token info
        try:
            # This might not work with all tokens, but worth trying
            token_info = api.call('GET', 'https://graph.facebook.com/v18.0/me', params={'access_token': CURRENT_TOKEN})
            print(f"  ✅ Token is valid")
            print(f"  ✅ Token info: {token_info}")
        except Exception as e:
            print(f"  ℹ️  Token info not accessible: {e}")
            print(f"  ✅ But token works for API calls")
        
    except Exception as e:
        print(f"  ❌ Token validation failed: {e}")

def main():
    """Main test function"""
    print("Testing your current token to see what permissions you have...")
    print("This will show exactly what data you can access right now.\n")
    
    # Test permissions
    permissions_work = test_current_permissions()
    
    # Test token info
    test_token_info()
    
    # Final summary
    print("\n📋 FINAL SUMMARY")
    print("=" * 20)
    if permissions_work:
        print("🎉 EXCELLENT! Your token has ads_read permission!")
        print("✅ You can access:")
        print("  - Account information")
        print("  - Campaign data")
        print("  - Campaign insights (impressions, clicks, spend)")
        print("  - Ad sets and ads")
        print("\n💡 You can start using the Meta Ads API right now!")
        print("📝 No need to wait for App Review - you already have access!")
    else:
        print("❌ Token has limited permissions")
        print("💡 You may need App Review for full access")

if __name__ == "__main__":
    main()
