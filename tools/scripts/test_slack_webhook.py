#!/usr/bin/env python3
"""
Test Slack Webhook - Simple test to verify webhook is working
"""

import requests
import json

def test_slack_webhook():
    """Test the Slack webhook URL"""
    
    webhook_url = 'YOUR_SLACK_WEBHOOK_URL_HERE'
    
    # Simple test message
    test_message = {
        "text": "🧪 Slack Webhook Test",
        "attachments": [
            {
                "color": "good",
                "fields": [
                    {
                        "title": "Test Status",
                        "value": "✅ Webhook is working!",
                        "short": True
                    },
                    {
                        "title": "Timestamp",
                        "value": "2025-09-15T12:45:00Z",
                        "short": True
                    }
                ]
            }
        ]
    }
    
    try:
        print("🔍 Testing Slack webhook...")
        print(f"URL: {webhook_url}")
        print(f"Message: {json.dumps(test_message, indent=2)}")
        
        response = requests.post(
            webhook_url,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(test_message),
            timeout=10
        )
        
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print("✅ SUCCESS: Webhook is working!")
            print(f"Response: {response.text}")
        else:
            print(f"❌ FAILED: Status {response.status_code}")
            print(f"Error: {response.text}")
            
            if response.status_code == 403:
                print("\n🔍 403 Forbidden Analysis:")
                print("- Webhook URL might be expired")
                print("- Webhook might be disabled")
                print("- Channel permissions might have changed")
                print("- Webhook might be from different workspace")
                
    except requests.exceptions.RequestException as e:
        print(f"❌ NETWORK ERROR: {e}")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    test_slack_webhook()
