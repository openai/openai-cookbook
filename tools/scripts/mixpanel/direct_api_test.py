#!/usr/bin/env python3
"""
🔗 DIRECT MIXPANEL API TEST
Tests Mixpanel API directly using CURL to bypass MCP layer

Usage: python3 direct_api_test.py --email user1@example.com
"""

import sys
import json
import os
import argparse
import subprocess
import base64
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
MIXPANEL_USERNAME = os.getenv("MIXPANEL_USERNAME")
MIXPANEL_PASSWORD = os.getenv("MIXPANEL_PASSWORD") 
MIXPANEL_PROJECT_ID = os.getenv("MIXPANEL_PROJECT_ID")

def check_credentials():
    """Check if we have the necessary Mixpanel credentials"""
    if not MIXPANEL_PROJECT_ID:
        print("❌ MIXPANEL_PROJECT_ID environment variable not set.")
        print("Add your Mixpanel project ID to the .env file")
        return False
    
    if not MIXPANEL_USERNAME or not MIXPANEL_PASSWORD:
        print("❌ Need MIXPANEL_USERNAME and MIXPANEL_PASSWORD")
        print("Add these to your .env file")
        return False
    
    print(f"✅ Using project ID: {MIXPANEL_PROJECT_ID}")
    print(f"✅ Using username: {MIXPANEL_USERNAME}")
    return True

def create_basic_auth():
    """Create basic auth header for Mixpanel API"""
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    return f"Basic {encoded_auth}"

def query_profiles_direct(email=None, limit=10):
    """Query Mixpanel profiles using direct CURL call"""
    print(f"🌐 Querying profiles directly via Mixpanel API...")
    
    # Construct the query
    if email:
        where_clause = f'properties["$email"] == "{email}"'
        print(f"🔍 Searching for email: {email}")
    else:
        where_clause = ""
        print(f"🔍 Getting {limit} sample profiles")
    
    # Prepare the request body
    request_data = {
        "output_properties": ["$email", "$name", "distinct_id", "$last_seen"]
    }
    
    if where_clause:
        request_data["where"] = where_clause
    else:
        request_data["limit"] = limit
    
    # Create auth header
    auth_header = create_basic_auth()
    
    # Construct CURL command
    curl_cmd = [
        "curl",
        "-X", "POST",
        f"https://mixpanel.com/api/query/engage?project_id={MIXPANEL_PROJECT_ID}",
        "-H", f"Authorization: {auth_header}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(request_data),
        "--silent",
        "--show-error"
    ]
    
    print(f"📡 Making direct API call...")
    print(f"🔗 Endpoint: https://mixpanel.com/api/query/engage")
    
    try:
        # Execute CURL command
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
        
        print(f"📊 Response Status: {result.returncode}")
        
        if result.returncode == 0:
            # Parse response
            try:
                response_data = json.loads(result.stdout)
                print(f"✅ API call successful!")
                
                if "results" in response_data:
                    results = response_data["results"]
                    print(f"👥 Found {len(results)} profiles")
                    
                    for i, profile in enumerate(results[:3]):  # Show first 3
                        distinct_id = profile.get("distinct_id", "N/A")
                        properties = profile.get("properties", {})
                        email = properties.get("$email", "N/A")
                        name = properties.get("$name", "N/A")
                        
                        print(f"  {i+1}. {name} ({email}) - ID: {distinct_id}")
                        
                elif "error" in response_data:
                    print(f"❌ API Error: {response_data['error']}")
                    if "rate limit" in response_data['error'].lower():
                        print("🚫 RATE LIMIT HIT - Same as MCP!")
                        return False
                else:
                    print(f"📄 Raw response: {response_data}")
                    
                return True
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing error: {e}")
                print(f"📄 Raw response: {result.stdout}")
                return False
                
        else:
            print(f"❌ CURL failed with exit code: {result.returncode}")
            print(f"📄 Error output: {result.stderr}")
            
            if "429" in result.stderr or "rate limit" in result.stderr.lower():
                print("🚫 RATE LIMIT HIT - Same as MCP!")
                return False
                
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Request timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def get_top_events_direct():
    """Get top events using direct CURL call"""
    print(f"🌐 Getting top events directly via Mixpanel API...")
    
    # Create auth header
    auth_header = create_basic_auth()
    
    # Construct CURL command for top events
    curl_cmd = [
        "curl",
        "-X", "GET",
        f"https://mixpanel.com/api/query/events/top?project_id={MIXPANEL_PROJECT_ID}&type=general&limit=5",
        "-H", f"Authorization: {auth_header}",
        "--silent",
        "--show-error"
    ]
    
    print(f"📡 Making direct API call...")
    print(f"🔗 Endpoint: https://mixpanel.com/api/query/events/top")
    
    try:
        # Execute CURL command
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
        
        print(f"📊 Response Status: {result.returncode}")
        
        if result.returncode == 0:
            try:
                response_data = json.loads(result.stdout)
                print(f"✅ API call successful!")
                print(f"📄 Raw response: {response_data}")
                return True
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing error: {e}")
                print(f"📄 Raw response: {result.stdout}")
                
                # Check if it contains rate limit error in plain text
                if "rate limit" in result.stdout.lower() or "429" in result.stdout:
                    print("🚫 RATE LIMIT HIT - Same as MCP!")
                    return False
                    
                return False
                
        else:
            print(f"❌ CURL failed with exit code: {result.returncode}")
            print(f"📄 Error output: {result.stderr}")
            
            if "429" in result.stderr or "rate limit" in result.stderr.lower():
                print("🚫 RATE LIMIT HIT - Same as MCP!")
                return False
                
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Request timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test Mixpanel API directly via CURL")
    parser.add_argument("--email", type=str, help="Email address to search for")
    parser.add_argument("--sample", action="store_true", help="Get sample profiles instead")
    parser.add_argument("--events", action="store_true", help="Get top events")
    
    args = parser.parse_args()
    
    print("🚀 Direct Mixpanel API Test")
    print("=" * 50)
    
    # Check credentials
    if not check_credentials():
        sys.exit(1)
    
    success = True
    
    if args.events:
        success = get_top_events_direct()
    elif args.email:
        success = query_profiles_direct(email=args.email)
    elif args.sample:
        success = query_profiles_direct(limit=5)
    else:
        print("Please specify --email, --sample, or --events")
        sys.exit(1)
    
    if success:
        print("\n✅ Direct API call completed successfully!")
        print("🎯 This confirms the API is working and not rate limited via CURL")
    else:
        print("\n❌ Direct API call failed!")
        print("🎯 This helps isolate where the rate limiting is occurring")

if __name__ == "__main__":
    main() 