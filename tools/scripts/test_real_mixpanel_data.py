#!/usr/bin/env python3
"""
Real Data Test Script for Mixpanel Webhook Processing
Version: 1.1.0
Last Updated: 2025-01-09T17:00:00Z

This script attempts to access real Mixpanel data from the webhook
using different methods and approaches.
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

class RealMixpanelWebhookTester:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        
    def try_different_endpoints(self):
        """Try different endpoint variations to access real data"""
        print("🔍 TRYING DIFFERENT ENDPOINT VARIATIONS")
        print("=" * 60)
        
        endpoints_to_try = [
            # Original endpoint
            self.webhook_url,
            # Add trailing slash variations
            self.webhook_url.rstrip('/') + '/',
            # Try with different parameters
            self.webhook_url + '?format=json',
            self.webhook_url + '?data=true',
            self.webhook_url + '?export=true',
            # Try different paths
            self.webhook_url.replace('/catch/', '/data/'),
            self.webhook_url.replace('/catch/', '/export/'),
            # Try with different HTTP methods
        ]
        
        for i, endpoint in enumerate(endpoints_to_try, 1):
            print(f"\n📡 TRYING ENDPOINT {i}: {endpoint}")
            try:
                response = requests.get(endpoint, timeout=10)
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                        if self.is_real_mixpanel_data(data):
                            print("   ✅ FOUND REAL MIXPANEL DATA!")
                            return data
                    except:
                        print(f"   Text: {response.text[:200]}...")
                else:
                    print(f"   Error: {response.status_code}")
            except Exception as e:
                print(f"   Exception: {e}")
        
        return None
    
    def try_post_with_data(self):
        """Try POST requests with different payloads to trigger data export"""
        print("\n🔍 TRYING POST REQUESTS TO TRIGGER DATA EXPORT")
        print("=" * 60)
        
        post_payloads = [
            {"action": "export", "format": "json"},
            {"trigger": "export", "data": "all"},
            {"export": True, "format": "json"},
            {"cohort": "Registros Ultimas 24 horas", "export": True},
            {"request": "data", "cohort": "all"},
            {"method": "export", "cohort": "last_24h"},
        ]
        
        for i, payload in enumerate(post_payloads, 1):
            print(f"\n📡 TRYING POST {i}: {payload}")
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                        if self.is_real_mixpanel_data(data):
                            print("   ✅ FOUND REAL MIXPANEL DATA!")
                            return data
                    except:
                        print(f"   Text: {response.text[:200]}...")
                else:
                    print(f"   Error: {response.status_code}")
            except Exception as e:
                print(f"   Exception: {e}")
        
        return None
    
    def try_with_headers(self):
        """Try requests with different headers to access data"""
        print("\n🔍 TRYING REQUESTS WITH DIFFERENT HEADERS")
        print("=" * 60)
        
        header_combinations = [
            {'Accept': 'application/json', 'Content-Type': 'application/json'},
            {'Accept': 'application/json', 'User-Agent': 'Mixpanel-Export/1.0'},
            {'Accept': 'application/json', 'Authorization': 'Bearer test'},
            {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
            {'Accept': 'application/json', 'X-Export-Data': 'true'},
            {'Accept': 'application/json', 'X-Cohort-Export': 'true'},
        ]
        
        for i, headers in enumerate(header_combinations, 1):
            print(f"\n📡 TRYING HEADERS {i}: {headers}")
            try:
                response = requests.get(
                    self.webhook_url,
                    headers=headers,
                    timeout=10
                )
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                        if self.is_real_mixpanel_data(data):
                            print("   ✅ FOUND REAL MIXPANEL DATA!")
                            return data
                    except:
                        print(f"   Text: {response.text[:200]}...")
                else:
                    print(f"   Error: {response.status_code}")
            except Exception as e:
                print(f"   Exception: {e}")
        
        return None
    
    def try_zapier_specific_endpoints(self):
        """Try Zapier-specific endpoint variations"""
        print("\n🔍 TRYING ZAPIER-SPECIFIC ENDPOINT VARIATIONS")
        print("=" * 60)
        
        # Extract base URL and hook ID
        base_url = "https://hooks.zapier.com"
        hook_path = "/hooks/catch/24538/2f03rbk/"
        
        zapier_endpoints = [
            # Try different Zapier API endpoints
            f"{base_url}/hooks/catch/24538/2f03rbk/data",
            f"{base_url}/hooks/catch/24538/2f03rbk/export",
            f"{base_url}/hooks/catch/24538/2f03rbk/logs",
            f"{base_url}/hooks/catch/24538/2f03rbk/history",
            f"{base_url}/hooks/catch/24538/2f03rbk/status",
            # Try with different parameters
            f"{base_url}{hook_path}?view=data",
            f"{base_url}{hook_path}?view=export",
            f"{base_url}{hook_path}?view=logs",
            f"{base_url}{hook_path}?view=history",
            # Try different HTTP methods
        ]
        
        for i, endpoint in enumerate(zapier_endpoints, 1):
            print(f"\n📡 TRYING ZAPIER ENDPOINT {i}: {endpoint}")
            try:
                response = requests.get(endpoint, timeout=10)
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                        if self.is_real_mixpanel_data(data):
                            print("   ✅ FOUND REAL MIXPANEL DATA!")
                            return data
                    except:
                        print(f"   Text: {response.text[:200]}...")
                else:
                    print(f"   Error: {response.status_code}")
            except Exception as e:
                print(f"   Exception: {e}")
        
        return None
    
    def is_real_mixpanel_data(self, data: Any) -> bool:
        """Check if data contains real Mixpanel user data"""
        if not data:
            return False
        
        # Check for array of user objects
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if isinstance(first_item, dict):
                # Look for Mixpanel user properties
                mixpanel_keys = ['distinct_id', 'email', 'properties', 'event', 'time']
                if any(key in first_item for key in mixpanel_keys):
                    return True
        
        # Check for single user object
        if isinstance(data, dict):
            mixpanel_keys = ['distinct_id', 'email', 'properties', 'event', 'time']
            if any(key in data for key in mixpanel_keys):
                return True
        
        # Check for nested data structure
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list) and len(value) > 0:
                    if self.is_real_mixpanel_data(value):
                        return True
        
        return False
    
    def analyze_current_response(self):
        """Analyze the current webhook response in detail"""
        print("\n🔍 ANALYZING CURRENT WEBHOOK RESPONSE")
        print("=" * 60)
        
        try:
            response = requests.get(self.webhook_url, timeout=10)
            print(f"📊 Status Code: {response.status_code}")
            print(f"📋 Headers: {dict(response.headers)}")
            
            data = response.json()
            print(f"📄 Response Data: {json.dumps(data, indent=2)}")
            
            # Look for any hidden data or clues
            print("\n🔍 RESPONSE ANALYSIS:")
            print(f"   - Response Type: {type(data)}")
            print(f"   - Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            
            # Check if there are any clues about data availability
            if 'status' in data:
                print(f"   - Status: {data['status']}")
            if 'id' in data:
                print(f"   - Request ID: {data['id']}")
            if 'attempt' in data:
                print(f"   - Attempt ID: {data['attempt']}")
            
            # Check headers for clues
            headers = response.headers
            if 'x-zapier-hook-status' in headers:
                print(f"   - Zapier Status: {headers['x-zapier-hook-status']}")
            if 'x-zapier-hook-id' in headers:
                print(f"   - Zapier Hook ID: {headers['x-zapier-hook-id']}")
            
            return data
            
        except Exception as e:
            print(f"❌ Error analyzing response: {e}")
            return None
    
    def run_comprehensive_test(self):
        """Run comprehensive test to find real data"""
        print("🚀 COMPREHENSIVE REAL DATA TEST")
        print("=" * 80)
        print(f"📡 Webhook URL: {self.webhook_url}")
        print(f"⏰ Timestamp: {datetime.now().isoformat()}")
        print("=" * 80)
        
        # Step 1: Analyze current response
        current_data = self.analyze_current_response()
        
        # Step 2: Try different endpoints
        real_data = self.try_different_endpoints()
        if real_data:
            return real_data
        
        # Step 3: Try POST requests
        real_data = self.try_post_with_data()
        if real_data:
            return real_data
        
        # Step 4: Try different headers
        real_data = self.try_with_headers()
        if real_data:
            return real_data
        
        # Step 5: Try Zapier-specific endpoints
        real_data = self.try_zapier_specific_endpoints()
        if real_data:
            return real_data
        
        print("\n❌ NO REAL MIXPANEL DATA FOUND")
        print("📊 The webhook appears to be a status endpoint only")
        print("💡 Real data might be processed by Zapier and sent elsewhere")
        
        return None

def main():
    """Main function to run the comprehensive real data test"""
    webhook_url = "https://hooks.zapier.com/hooks/catch/24538/2f03rbk/"
    
    print("🧪 Real Mixpanel Data Test")
    print("=" * 60)
    print()
    
    tester = RealMixpanelWebhookTester(webhook_url)
    real_data = tester.run_comprehensive_test()
    
    if real_data:
        print("\n" + "=" * 80)
        print("🎉 REAL MIXPANEL DATA FOUND!")
        print("=" * 80)
        print(json.dumps(real_data, indent=2, ensure_ascii=False))
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("📊 TEST CONCLUSION")
        print("=" * 80)
        print("The webhook endpoint is designed to:")
        print("1. ✅ Receive Mixpanel data from Zapier")
        print("2. ✅ Process the data in Zapier")
        print("3. ✅ Return status confirmation")
        print("4. ❌ NOT store or expose the raw data")
        print()
        print("To access real Mixpanel data, you would need to:")
        print("- Configure Zapier to send data to your HubSpot workflow")
        print("- Use the HubSpot custom code to process incoming data")
        print("- Or access Mixpanel data directly via their API")
        print("=" * 80)

if __name__ == "__main__":
    main()



