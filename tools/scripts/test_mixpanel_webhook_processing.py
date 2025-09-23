#!/usr/bin/env python3
"""
Test Script for Mixpanel Webhook Processing
Version: 1.0.0
Last Updated: 2025-01-09T16:30:00Z

This script tests the webhook processing logic locally to simulate
what would happen in HubSpot custom code when processing Mixpanel data.
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

class MixpanelWebhookTester:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.test_results = []
        
    def fetch_webhook_data(self) -> Dict[str, Any]:
        """Fetch data from the Mixpanel webhook"""
        print("🔗 FETCHING MIXPANEL DATA FROM WEBHOOK")
        print(f"📡 Webhook URL: {self.webhook_url}")
        
        try:
            response = requests.get(
                self.webhook_url,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'HubSpot-CustomCode-Test/1.0'
                },
                timeout=30
            )
            
            print(f"📊 WEBHOOK RESPONSE STATUS: {response.status_code}")
            print(f"📋 RESPONSE HEADERS: {dict(response.headers)}")
            
            if not response.ok:
                raise Exception(f"HTTP {response.status_code}: {response.status_text}")
            
            data = response.json()
            print("✅ WEBHOOK DATA RECEIVED:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            return data
            
        except Exception as error:
            print(f"❌ WEBHOOK FETCH ERROR: {error}")
            raise error
    
    def is_mixpanel_data(self, data: Dict[str, Any]) -> bool:
        """Check if response contains actual Mixpanel data"""
        print("🔍 CHECKING IF DATA IS MIXPANEL EVENT DATA")
        
        # Check if it's a status response (current format)
        if data and isinstance(data, dict):
            status_keys = ['attempt', 'id', 'request_id', 'status']
            if all(key in data for key in status_keys):
                print("ℹ️ DETECTED: Status response (not Mixpanel data)")
                return False
        
        # Check for Mixpanel event structure
        if isinstance(data, list):
            has_mixpanel_structure = any(
                item and isinstance(item, dict) and 
                any(key in item for key in ['event', 'event_name', 'distinct_id', 'email'])
                for item in data
            )
            if has_mixpanel_structure:
                print("✅ DETECTED: Array of Mixpanel events")
                return True
        
        if data and isinstance(data, dict):
            has_mixpanel_structure = any(key in data for key in ['event', 'event_name', 'distinct_id', 'email'])
            if has_mixpanel_structure:
                print("✅ DETECTED: Single Mixpanel event")
                return True
        
        print("❌ DETECTED: Unknown data format")
        return False
    
    def process_mixpanel_data(self, mixpanel_data: Any) -> List[Dict[str, Any]]:
        """Process Mixpanel data and map to HubSpot contact properties"""
        print("🔄 PROCESSING MIXPANEL DATA")
        print("📊 RAW DATA:", json.dumps(mixpanel_data, indent=2, ensure_ascii=False))
        
        contact_updates = []
        
        # Handle array of events
        if isinstance(mixpanel_data, list):
            print(f"📋 PROCESSING ARRAY WITH {len(mixpanel_data)} ITEMS")
            for index, record in enumerate(mixpanel_data):
                print(f"📋 PROCESSING RECORD {index + 1}:", json.dumps(record, indent=2, ensure_ascii=False))
                
                email = (record.get('distinct_id') or 
                        record.get('email') or 
                        record.get('user_email') or 
                        record.get('properties', {}).get('email'))
                
                if email:
                    properties = self._extract_properties_from_record(record)
                    contact_updates.append({
                        'email': email,
                        'properties': properties
                    })
                    print(f"✅ EXTRACTED: {email} -> {len(properties)} properties")
                else:
                    print(f"⚠️ SKIPPED: No email found in record {index + 1}")
        
        # Handle single event
        elif isinstance(mixpanel_data, dict):
            print("📋 PROCESSING SINGLE EVENT")
            email = (mixpanel_data.get('distinct_id') or 
                    mixpanel_data.get('email') or 
                    mixpanel_data.get('user_email') or 
                    mixpanel_data.get('properties', {}).get('email'))
            
            if email:
                properties = self._extract_properties_from_record(mixpanel_data)
                contact_updates.append({
                    'email': email,
                    'properties': properties
                })
                print(f"✅ EXTRACTED: {email} -> {len(properties)} properties")
            else:
                print("⚠️ SKIPPED: No email found in single event")
        
        print(f"📊 PROCESSED {len(contact_updates)} CONTACT UPDATE(S)")
        return contact_updates
    
    def _extract_properties_from_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and map properties from a Mixpanel record"""
        properties = {}
        
        # Map Mixpanel event data to HubSpot properties
        if record.get('event') or record.get('event_name'):
            properties['last_mixpanel_event'] = record.get('event') or record.get('event_name')
        
        if record.get('time') or record.get('event_time') or record.get('timestamp'):
            timestamp = record.get('time') or record.get('event_time') or record.get('timestamp')
            # Handle both Unix timestamps and ISO strings
            if isinstance(timestamp, (int, float)):
                event_time = datetime.fromtimestamp(timestamp)
            else:
                event_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            properties['last_mixpanel_event_date'] = event_time.isoformat()
        
        # Map properties from Mixpanel event
        if record.get('properties'):
            props = record['properties']
            
            # Company information
            if props.get('company_name') or props.get('company'):
                properties['company'] = props.get('company_name') or props.get('company')
            
            # User type and role
            if props.get('user_type'):
                properties['user_type'] = props['user_type']
            if props.get('role'):
                properties['role'] = props['role']
            
            # Subscription and billing
            if props.get('subscription_plan') or props.get('plan'):
                properties['subscription_plan'] = props.get('subscription_plan') or props.get('plan')
            if props.get('subscription_status'):
                properties['subscription_status'] = props['subscription_status']
            
            # Feature usage
            if props.get('feature_usage'):
                properties['feature_usage'] = props['feature_usage']
            if props.get('feature_name'):
                properties['last_feature_used'] = props['feature_name']
            
            # Platform and version info
            if props.get('platform') or props.get('$os'):
                properties['platform'] = props.get('platform') or props.get('$os')
            if props.get('app_version') or props.get('$app_version'):
                properties['app_version'] = props.get('app_version') or props.get('$app_version')
            
            # Geographic data
            if props.get('country') or props.get('$country_code'):
                properties['country'] = props.get('country') or props.get('$country_code')
            if props.get('city') or props.get('$city'):
                properties['city'] = props.get('city') or props.get('$city')
            
            # Custom properties for Colppy
            if props.get('invoice_count'):
                properties['invoice_count'] = props['invoice_count']
            if props.get('accountant_name'):
                properties['accountant_name'] = props['accountant_name']
            if props.get('business_type'):
                properties['business_type'] = props['business_type']
            
            # Additional Mixpanel properties
            if props.get('$browser'):
                properties['browser'] = props['$browser']
            if props.get('$os'):
                properties['operating_system'] = props['$os']
            if props.get('$referrer'):
                properties['referrer'] = props['$referrer']
        
        # Set last webhook sync timestamp
        properties['last_mixpanel_sync'] = datetime.now().isoformat()
        
        return properties
    
    def simulate_contact_search(self, email: str) -> Optional[Dict[str, Any]]:
        """Simulate HubSpot contact search (mock implementation)"""
        print(f"🔍 SIMULATING CONTACT SEARCH: {email}")
        
        # Mock contact data - in real implementation this would call HubSpot API
        mock_contacts = {
            'test@colppy.com': {
                'id': '12345',
                'properties': {
                    'email': 'test@colppy.com',
                    'firstname': 'Test',
                    'lastname': 'User',
                    'company': 'Colppy Test'
                }
            },
            'juan@example.com': {
                'id': '67890',
                'properties': {
                    'email': 'juan@example.com',
                    'firstname': 'Juan',
                    'lastname': 'Onetto',
                    'company': 'Colppy'
                }
            }
        }
        
        if email in mock_contacts:
            contact = mock_contacts[email]
            print(f"✅ MOCK CONTACT FOUND: ID {contact['id']} - {contact['properties']['email']}")
            return contact
        else:
            print(f"❌ MOCK CONTACT NOT FOUND: {email}")
            return None
    
    def simulate_contact_update(self, contact_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate HubSpot contact update (mock implementation)"""
        print(f"🔄 SIMULATING CONTACT UPDATE: ID {contact_id}")
        print("📝 PROPERTIES TO UPDATE:", json.dumps(properties, indent=2, ensure_ascii=False))
        
        # Mock update response
        update_response = {
            'id': contact_id,
            'properties': properties,
            'updatedAt': datetime.now().isoformat(),
            'archived': False
        }
        
        print(f"✅ MOCK CONTACT UPDATED SUCCESSFULLY: ID {contact_id}")
        return update_response
    
    def run_test(self) -> Dict[str, Any]:
        """Run the complete test simulation"""
        print("=" * 80)
        print("🚀 MIXPANEL WEBHOOK PROCESSING TEST STARTED")
        print("=" * 80)
        print("📋 TEST INFO:")
        print(f"   Timestamp: {datetime.now().isoformat()}")
        print(f"   Webhook URL: {self.webhook_url}")
        print("=" * 80)
        
        try:
            # Step 1: Fetch data from webhook
            webhook_data = self.fetch_webhook_data()
            
            if not webhook_data:
                print("❌ NO DATA RECEIVED FROM WEBHOOK")
                return {
                    'success': False,
                    'message': 'No data received from webhook',
                    'dataType': 'no_data'
                }
            
            # Step 2: Check if this is actual Mixpanel data
            if not self.is_mixpanel_data(webhook_data):
                print("ℹ️ WEBHOOK RETURNED STATUS RESPONSE, NOT MIXPANEL DATA")
                print("📊 This indicates the webhook is active but no Mixpanel events have been received yet")
                
                # Test with mock Mixpanel data to show how it would work
                print("\n🧪 TESTING WITH MOCK MIXPANEL DATA:")
                mock_mixpanel_data = {
                    'event': 'User Login',
                    'distinct_id': 'test@colppy.com',
                    'time': int(datetime.now().timestamp()),
                    'properties': {
                        'company_name': 'Colppy Test Company',
                        'user_type': 'accountant',
                        'subscription_plan': 'premium',
                        'platform': 'web',
                        'app_version': '2.1.0',
                        'country': 'AR',
                        'invoice_count': 150,
                        'accountant_name': 'Juan Ignacio Onetto',
                        'business_type': 'SMB'
                    }
                }
                
                contact_updates = self.process_mixpanel_data(mock_mixpanel_data)
                
                # Step 3: Simulate contact updates
                results = []
                for update in contact_updates:
                    contact = self.simulate_contact_search(update['email'])
                    if contact:
                        update_result = self.simulate_contact_update(contact['id'], update['properties'])
                        results.append({
                            'email': update['email'],
                            'contactId': contact['id'],
                            'status': 'success',
                            'updatedProperties': list(update['properties'].keys()),
                            'updateResponse': update_result
                        })
                    else:
                        results.append({
                            'email': update['email'],
                            'contactId': None,
                            'status': 'not_found',
                            'error': 'Contact not found in HubSpot'
                        })
                
                print("\n" + "=" * 80)
                print("📊 MOCK TEST RESULTS SUMMARY")
                print("=" * 80)
                print(f"✅ Successfully processed: {len([r for r in results if r['status'] == 'success'])} contact(s)")
                print(f"❌ Errors/Not found: {len([r for r in results if r['status'] != 'success'])} contact(s)")
                print("=" * 80)
                
                return {
                    'success': True,
                    'message': 'Webhook active but no Mixpanel data received yet - tested with mock data',
                    'status': webhook_data,
                    'dataType': 'status_response',
                    'mockTestResults': results
                }
            
            # Step 3: Process actual Mixpanel data
            contact_updates = self.process_mixpanel_data(webhook_data)
            
            if not contact_updates:
                print("❌ NO CONTACT UPDATES TO PROCESS")
                return {
                    'success': False,
                    'message': 'No contact updates to process',
                    'dataType': 'no_contacts'
                }
            
            # Step 4: Simulate contact updates
            results = []
            for update in contact_updates:
                contact = self.simulate_contact_search(update['email'])
                if contact:
                    update_result = self.simulate_contact_update(contact['id'], update['properties'])
                    results.append({
                        'email': update['email'],
                        'contactId': contact['id'],
                        'status': 'success',
                        'updatedProperties': list(update['properties'].keys()),
                        'updateResponse': update_result
                    })
                else:
                    results.append({
                        'email': update['email'],
                        'contactId': None,
                        'status': 'not_found',
                        'error': 'Contact not found in HubSpot'
                    })
            
            # Step 5: Log final results
            print("\n" + "=" * 80)
            print("📊 FINAL RESULTS SUMMARY")
            print("=" * 80)
            success_count = len([r for r in results if r['status'] == 'success'])
            error_count = len([r for r in results if r['status'] != 'success'])
            print(f"✅ Successfully updated: {success_count} contact(s)")
            print(f"❌ Errors/Not found: {error_count} contact(s)")
            print(f"📋 Total processed: {len(contact_updates)} record(s)")
            
            return {
                'success': True,
                'message': f'Processed {len(contact_updates)} records: {success_count} updated, {error_count} errors',
                'results': results,
                'summary': {
                    'total': len(contact_updates),
                    'success': success_count,
                    'errors': error_count
                },
                'dataType': 'mixpanel_data'
            }
            
        except Exception as error:
            print(f"💥 FATAL ERROR IN TEST: {error}")
            return {
                'success': False,
                'error': str(error),
                'message': 'Failed to process webhook data'
            }

def main():
    """Main function to run the webhook processing test"""
    webhook_url = "https://hooks.zapier.com/hooks/catch/24538/2f03rbk/"
    
    print("🧪 Mixpanel Webhook Processing Test")
    print("=" * 60)
    print()
    
    tester = MixpanelWebhookTester(webhook_url)
    result = tester.run_test()
    
    print("\n" + "=" * 60)
    print("📋 FINAL TEST RESULT:")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 60)

if __name__ == "__main__":
    main()



