#!/usr/bin/env python3
"""
Meta Ads API Setup Test Script
==============================

Tests the Meta Ads API configuration and connection.
Validates environment variables and API access.

Usage:
    python test_setup.py

Author: Data Analytics Team - Colppy
"""

import os
import sys
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.exceptions import FacebookRequestError

def load_environment():
    """Load environment variables from .env file"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ Loaded environment from {env_path}")
    else:
        print(f"⚠️  No .env file found at {env_path}")
        print("   Using system environment variables only")

def test_environment():
    """Test if all required environment variables are set"""
    print("\n🔍 Testing Environment Variables...")
    
    required_vars = [
        'META_ADS_APP_ID',
        'META_ADS_APP_SECRET', 
        'META_ADS_ACCESS_TOKEN'
    ]
    
    optional_vars = [
        'META_ADS_ACCOUNT_ID',
        'META_ADS_BUSINESS_ID',
        'META_ADS_TIMEZONE'
    ]
    
    all_good = True
    
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var}: {'*' * min(len(value), 8)}...")
        else:
            print(f"❌ {var}: Not set")
            all_good = False
    
    for var in optional_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var}: {value}")
        else:
            print(f"⚠️  {var}: Not set (optional)")
    
    return all_good

def test_api_connection():
    """Test Meta Ads API connection"""
    print("\n🔗 Testing Meta Ads API Connection...")
    
    try:
        # Initialize API
        app_id = os.environ.get('META_ADS_APP_ID')
        app_secret = os.environ.get('META_ADS_APP_SECRET')
        access_token = os.environ.get('META_ADS_ACCESS_TOKEN')
        
        FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
        print("✅ API initialized successfully")
        
        # Test basic API call
        api = FacebookAdsApi.get_default_api()
        me = api.call('GET', '/me')
        print(f"✅ API connection successful - User: {me.get('name', 'Unknown')}")
        
        return True
        
    except FacebookRequestError as e:
        print(f"❌ Facebook API Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

def test_ad_accounts():
    """Test access to ad accounts"""
    print("\n📊 Testing Ad Account Access...")
    
    try:
        # Get ad accounts
        api = FacebookAdsApi.get_default_api()
        accounts_response = api.call('GET', '/me/adaccounts')
        
        accounts = accounts_response.get('data', [])
        print(f"✅ Found {len(accounts)} ad accounts")
        
        for account in accounts[:3]:  # Show first 3 accounts
            account_id = account.get('id')
            account_name = account.get('name', 'Unnamed')
            account_status = account.get('account_status')
            print(f"   📋 {account_id}: {account_name} ({account_status})")
        
        if len(accounts) > 3:
            print(f"   ... and {len(accounts) - 3} more accounts")
        
        return len(accounts) > 0
        
    except FacebookRequestError as e:
        print(f"❌ Ad Account Access Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Ad Account Error: {e}")
        return False

def test_campaign_access():
    """Test access to campaigns"""
    print("\n🎯 Testing Campaign Access...")
    
    try:
        account_id = os.environ.get('META_ADS_ACCOUNT_ID')
        if not account_id:
            print("⚠️  No default account ID set, skipping campaign test")
            return True
        
        # Ensure account ID has 'act_' prefix
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        account = AdAccount(account_id)
        campaigns = account.get_campaigns(fields=['id', 'name', 'status'])
        
        campaign_count = 0
        for campaign in campaigns:
            campaign_count += 1
            if campaign_count <= 3:  # Show first 3 campaigns
                print(f"   🎯 {campaign.get('id')}: {campaign.get('name')} ({campaign.get('status')})")
        
        if campaign_count > 3:
            print(f"   ... and {campaign_count - 3} more campaigns")
        
        print(f"✅ Found {campaign_count} campaigns in account {account_id}")
        return True
        
    except FacebookRequestError as e:
        print(f"❌ Campaign Access Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Campaign Error: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Meta Ads API Setup Test")
    print("=" * 40)
    
    # Load environment
    load_environment()
    
    # Run tests
    tests = [
        ("Environment Variables", test_environment),
        ("API Connection", test_api_connection),
        ("Ad Account Access", test_ad_accounts),
        ("Campaign Access", test_campaign_access)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📋 Test Summary")
    print("=" * 40)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Results: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Meta Ads API is ready to use.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check your configuration.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
