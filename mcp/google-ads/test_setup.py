#!/usr/bin/env python3
"""
Test Google Ads MCP setup
"""
import os
import sys
from dotenv import load_dotenv

def test_environment():
    """Test if environment variables are properly set"""
    print("Testing Google Ads MCP Setup")
    print("=" * 50)
    
    # Load .env file
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✓ Loaded .env file from: {env_path}")
    else:
        print(f"✗ .env file not found at: {env_path}")
        print("  Please create .env file with your credentials")
        return False
    
    # Check required environment variables
    required_vars = {
        'GOOGLE_ADS_DEVELOPER_TOKEN': 'Developer Token',
        'GOOGLE_ADS_AUTH_TYPE': 'Auth Type'
    }
    
    all_good = True
    for var, name in required_vars.items():
        value = os.getenv(var)
        if value:
            print(f"✓ {name}: {'*' * min(len(value), 10)}...")
        else:
            print(f"✗ {name}: Not set")
            all_good = False
    
    # Check auth-specific variables
    auth_type = os.getenv('GOOGLE_ADS_AUTH_TYPE', '').lower()
    
    if auth_type == 'oauth':
        oauth_vars = {
            'GOOGLE_ADS_CLIENT_ID': 'Client ID',
            'GOOGLE_ADS_CLIENT_SECRET': 'Client Secret',
            'GOOGLE_ADS_REFRESH_TOKEN': 'Refresh Token'
        }
        for var, name in oauth_vars.items():
            value = os.getenv(var)
            if value:
                print(f"✓ {name}: {'*' * min(len(value), 10)}...")
            else:
                print(f"✗ {name}: Not set")
                all_good = False
                
    elif auth_type == 'service_account':
        creds_path = os.getenv('GOOGLE_ADS_CREDENTIALS_PATH')
        if creds_path and os.path.exists(creds_path):
            print(f"✓ Service Account File: {creds_path}")
        else:
            print(f"✗ Service Account File: Not found at {creds_path}")
            all_good = False
    else:
        print(f"✗ Invalid auth type: {auth_type}")
        all_good = False
    
    return all_good

def test_api_connection():
    """Test actual API connection"""
    try:
        # Import after environment check
        from google.ads.googleads.client import GoogleAdsClient
        from google.ads.googleads.errors import GoogleAdsException
        
        print("\nTesting API Connection...")
        print("-" * 30)
        
        # Try to create client
        try:
            # Create configuration
            config = {
                'developer_token': os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN'),
                'use_proto_plus': True
            }
            
            auth_type = os.getenv('GOOGLE_ADS_AUTH_TYPE', '').lower()
            
            if auth_type == 'oauth':
                config['client_id'] = os.getenv('GOOGLE_ADS_CLIENT_ID')
                config['client_secret'] = os.getenv('GOOGLE_ADS_CLIENT_SECRET')
                config['refresh_token'] = os.getenv('GOOGLE_ADS_REFRESH_TOKEN')
            else:
                config['path_to_private_key_file'] = os.getenv('GOOGLE_ADS_CREDENTIALS_PATH')
            
            client = GoogleAdsClient.load_from_dict(config)
            print("✓ Successfully created Google Ads client")
            
            # Try to list accessible customers
            customer_service = client.get_service("CustomerService")
            accessible_customers = customer_service.list_accessible_customers()
            
            if accessible_customers.resource_names:
                print(f"✓ Found {len(accessible_customers.resource_names)} accessible customers")
                for resource_name in accessible_customers.resource_names[:5]:
                    customer_id = resource_name.split('/')[-1]
                    print(f"  - Customer ID: {customer_id}")
            else:
                print("⚠ No accessible customers found")
                print("  Make sure your developer token has access to Google Ads accounts")
                
        except GoogleAdsException as ex:
            print(f"✗ Google Ads API Error: {ex.error.message}")
            for error in ex.failure.errors:
                print(f"  - {error.message}")
        except Exception as e:
            print(f"✗ Error creating client: {e}")
            
    except ImportError:
        print("✗ google-ads-python not installed properly")
        print("  Run: pip install google-ads")

def main():
    """Run all tests"""
    if test_environment():
        print("\n✓ Environment setup looks good!")
        test_api_connection()
    else:
        print("\n✗ Please fix the environment setup issues above")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("Next steps:")
    print("1. If all tests passed, restart your IDE (Cursor/Claude)")
    print("2. The Google Ads tools should appear in the MCP tools list")
    print("3. Try asking about your Google Ads campaigns!")

if __name__ == "__main__":
    main()

