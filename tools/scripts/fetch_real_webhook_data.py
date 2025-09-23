#!/usr/bin/env python3
"""
Real Mixpanel Webhook Data Fetcher
Version: 1.0.0
Last Updated: 2025-01-09T18:30:00Z

This script fetches real data from the HubSpot webhook to show
the actual member data structure and content.
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

class RealWebhookDataFetcher:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        
    def fetch_real_data(self):
        """Fetch real data from the HubSpot webhook"""
        print("🔗 FETCHING REAL DATA FROM HUBSPOT WEBHOOK")
        print("=" * 80)
        print(f"📡 Webhook URL: {self.webhook_url}")
        print(f"⏰ Timestamp: {datetime.now().isoformat()}")
        print("=" * 80)
        
        try:
            # Try different methods to access the data
            print("📡 Attempting to fetch webhook data...")
            
            # Method 1: Direct GET request
            response = requests.get(self.webhook_url, timeout=30)
            print(f"📊 GET Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ SUCCESS: Retrieved JSON data")
                    return self.analyze_data(data)
                except json.JSONDecodeError:
                    print("❌ Response is not JSON")
                    print(f"📄 Response Text: {response.text[:500]}")
            elif response.status_code == 405:
                print("ℹ️ GET not allowed (405) - webhook only accepts POST")
                return self.try_post_methods()
            else:
                print(f"❌ HTTP Error: {response.status_code}")
                print(f"📄 Response: {response.text[:500]}")
                
        except requests.exceptions.RequestException as e:
            print(f"💥 Request Error: {e}")
            
        return None
    
    def try_post_methods(self):
        """Try different POST methods to trigger data"""
        print("\n🔍 TRYING POST METHODS TO ACCESS DATA")
        print("-" * 50)
        
        # Try different POST payloads
        post_payloads = [
            {"action": "get_data", "format": "json"},
            {"request": "data", "type": "members"},
            {"method": "fetch", "data": "all"},
            {"trigger": "export", "cohort": "Registros Ultimas 24 horas"},
            {"action": "members", "parameters": {"mixpanel_cohort_name": "Registros Ultimas 24 horas"}},
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
                        if self.is_member_data(data):
                            print("   ✅ FOUND MEMBER DATA!")
                            return self.analyze_data(data)
                    except:
                        print(f"   Text: {response.text[:200]}...")
                else:
                    print(f"   Error: {response.status_code}")
            except Exception as e:
                print(f"   Exception: {e}")
        
        return None
    
    def is_member_data(self, data: Any) -> bool:
        """Check if data contains member information"""
        if not data:
            return False
        
        # Check for the expected structure
        if isinstance(data, dict):
            if data.get('action') == 'members' and 'members' in data:
                return True
            if 'members' in data and isinstance(data['members'], list):
                return True
        
        return False
    
    def analyze_data(self, data: Any):
        """Analyze and display the webhook data"""
        print("\n📊 ANALYZING WEBHOOK DATA")
        print("=" * 80)
        
        if not data:
            print("❌ No data to analyze")
            return None
        
        print("📋 RAW DATA STRUCTURE:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        # Check if this is member data
        if self.is_member_data(data):
            print("\n🎯 MEMBER DATA DETECTED!")
            return self.display_member_data(data)
        else:
            print("\n❌ No member data found in response")
            return None
    
    def display_member_data(self, data: Dict[str, Any]):
        """Display detailed member information"""
        print("\n👥 MEMBER DATA ANALYSIS")
        print("=" * 80)
        
        # Extract cohort information
        if 'parameters' in data:
            params = data['parameters']
            print("📊 COHORT INFORMATION:")
            print(f"   • Cohort Name: {params.get('mixpanel_cohort_name', 'N/A')}")
            print(f"   • Cohort ID: {params.get('mixpanel_cohort_id', 'N/A')}")
            print(f"   • Project ID: {params.get('mixpanel_project_id', 'N/A')}")
            print(f"   • Session ID: {params.get('mixpanel_session_id', 'N/A')}")
            print(f"   • Integration ID: {params.get('mixpanel_integration_id', 'N/A')}")
        
        # Extract members
        members = data.get('members', [])
        print(f"\n👥 MEMBERS COUNT: {len(members)}")
        
        if members:
            print("\n📋 MEMBER DETAILS:")
            print("-" * 50)
            
            for i, member in enumerate(members, 1):
                print(f"\n👤 MEMBER {i}:")
                print(f"   • Email/Distinct ID: {member.get('$distinct_id', member.get('mixpanel_distinct_id', 'N/A'))}")
                
                # UTM Parameters
                utm_params = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content']
                utm_data = {param: member.get(param, '') for param in utm_params if member.get(param)}
                
                if utm_data:
                    print("   📊 UTM Parameters:")
                    for param, value in utm_data.items():
                        if value:  # Only show non-empty values
                            print(f"      - {param}: {value}")
                
                # Other properties
                other_props = {k: v for k, v in member.items() 
                             if not k.startswith('$') and not k.startswith('utm_') and not k.startswith('mixpanel_')}
                
                if other_props:
                    print("   🔧 Other Properties:")
                    for prop, value in other_props.items():
                        if value:  # Only show non-empty values
                            print(f"      - {prop}: {value}")
                
                # Show full member data for first few members
                if i <= 3:
                    print(f"   📄 Full Data:")
                    print(f"      {json.dumps(member, indent=6, ensure_ascii=False)}")
            
            # Summary statistics
            print(f"\n📊 SUMMARY STATISTICS:")
            print("-" * 50)
            
            # Count UTM sources
            utm_sources = {}
            utm_mediums = {}
            utm_campaigns = {}
            
            for member in members:
                if member.get('utm_source'):
                    utm_sources[member['utm_source']] = utm_sources.get(member['utm_source'], 0) + 1
                if member.get('utm_medium'):
                    utm_mediums[member['utm_medium']] = utm_mediums.get(member['utm_medium'], 0) + 1
                if member.get('utm_campaign'):
                    utm_campaigns[member['utm_campaign']] = utm_campaigns.get(member['utm_campaign'], 0) + 1
            
            if utm_sources:
                print("📊 UTM Sources:")
                for source, count in utm_sources.items():
                    print(f"   • {source}: {count} users")
            
            if utm_mediums:
                print("📊 UTM Mediums:")
                for medium, count in utm_mediums.items():
                    print(f"   • {medium}: {count} users")
            
            if utm_campaigns:
                print("📊 UTM Campaigns:")
                for campaign, count in utm_campaigns.items():
                    print(f"   • {campaign}: {count} users")
        
        return {
            'cohort_info': data.get('parameters', {}),
            'members': members,
            'total_members': len(members)
        }
    
    def create_sample_payload(self):
        """Create a sample payload based on the expected structure"""
        print("\n📋 SAMPLE PAYLOAD STRUCTURE")
        print("=" * 80)
        
        sample_payload = {
            "action": "members",
            "parameters": {
                "mixpanel_cohort_id": "5167408",
                "mixpanel_project_id": "2201475",
                "mixpanel_session_id": "37163825-ae24-4bc8-b8f8-a8b034d1d678",
                "mixpanel_cohort_name": "Registros Ultimas 24 horas",
                "mixpanel_integration_id": "0"
            },
            "members": [
                {
                    "utm_term": "",
                    "utm_medium": "ppc",
                    "utm_source": "google",
                    "utm_content": "",
                    "$distinct_id": "zoem7960@gmail.com",
                    "utm_campaign": "Sales-Performance Max-V2",
                    "mixpanel_distinct_id": "zoem7960@gmail.com"
                },
                {
                    "utm_term": "",
                    "utm_medium": "social",
                    "utm_source": "facebook",
                    "utm_content": "",
                    "$distinct_id": "user2@example.com",
                    "utm_campaign": "Brand Awareness",
                    "mixpanel_distinct_id": "user2@example.com"
                }
            ]
        }
        
        print("📄 Expected Payload Structure:")
        print(json.dumps(sample_payload, indent=2, ensure_ascii=False))
        
        return sample_payload

def main():
    """Main function to fetch and display real webhook data"""
    webhook_url = "https://api-na1.hubapi.com/automation/v4/webhook-triggers/19877595/fXMW5p0"
    
    print("🔍 REAL MIXPANEL WEBHOOK DATA FETCHER")
    print("=" * 80)
    print()
    
    fetcher = RealWebhookDataFetcher(webhook_url)
    
    # Try to fetch real data
    result = fetcher.fetch_real_data()
    
    if result:
        print("\n✅ SUCCESS: Real data retrieved and analyzed")
        print(f"📊 Total Members: {result['total_members']}")
    else:
        print("\n❌ Could not retrieve real data from webhook")
        print("💡 This is expected - webhooks typically don't store data")
        print("📋 Showing expected data structure instead:")
        
        # Show sample structure
        fetcher.create_sample_payload()
        
        print("\n💡 TO ACCESS REAL DATA:")
        print("-" * 50)
        print("1. Deploy the HubSpot custom code")
        print("2. Configure Mixpanel to send data to the webhook")
        print("3. Monitor HubSpot workflow logs for incoming data")
        print("4. The custom code will process real member data automatically")
    
    print("\n" + "=" * 80)
    print("🎯 NEXT STEPS:")
    print("=" * 80)
    print("1. Deploy the HubSpot custom code from the previous script")
    print("2. Configure your Mixpanel integration to send data")
    print("3. Monitor the webhook for incoming member data")
    print("4. Check HubSpot contact properties for updates")
    print("=" * 80)

if __name__ == "__main__":
    main()



