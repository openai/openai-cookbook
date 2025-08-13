#!/usr/bin/env python3
"""
Simple HubSpot API Key Test
Tests if your HubSpot API key is working correctly
"""

import sys
import os

def test_hubspot_api_key():
    """Test HubSpot API key configuration"""
    print('🔑 Testing HubSpot API Key')
    print('='*40)
    
    try:
        from hubspot_api.client import HubSpotClient
        from hubspot_api.config import get_config
        
        # Test configuration
        print('📋 Step 1: Testing configuration...')
        try:
            config = get_config()
            print(f'   ✅ Configuration loaded: {config.environment} environment')
        except Exception as e:
            print(f'   ❌ Configuration error: {e}')
            return False
        
        # Test API connection
        print('\n📡 Step 2: Testing API connection...')
        try:
            client = HubSpotClient()
            
            # Test with a simple API call (get owners)
            if client.test_connection():
                print('   ✅ HubSpot API connection successful!')
                
                # Get some basic info
                stats = client.get_stats()
                print(f'   📊 Environment: {stats["environment"]}')
                print(f'   📊 Total requests: {stats["total_requests"]}')
                
                return True
            else:
                print('   ❌ HubSpot API connection failed')
                return False
                
        except Exception as e:
            print(f'   ❌ API connection error: {e}')
            return False
    
    except Exception as e:
        print(f'❌ Test error: {e}')
        return False

def main():
    """Main test function"""
    print('🚀 HubSpot API Key Test')
    print('='*30)
    print()
    
    success = test_hubspot_api_key()
    
    print('\n' + '='*50)
    if success:
        print('🎉 SUCCESS: HubSpot API key is working!')
        print()
        print('✅ Ready to run full analysis:')
        print('   python3 july_2025_closed_won_cuit_analysis_restful.py')
    else:
        print('❌ FAILED: HubSpot API key needs attention')
        print()
        print('📝 Steps to fix:')
        print('   1. Get your API key from HubSpot Settings > Integrations > Private Apps')
        print('   2. Edit: ../openai-cookbook/.env')
        print('   3. Replace: HUBSPOT_API_KEY=your_hubspot_api_key_here')
        print('   4. With: HUBSPOT_API_KEY=your_actual_api_key')
        print('   5. Run this test again')
    
    return success

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)