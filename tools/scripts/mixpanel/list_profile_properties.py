#!/usr/bin/env python3
"""
👥 LIST MIXPANEL USER PROFILE PROPERTIES
Gets sample user profiles and their properties from staging environment

Usage: python3 list_profile_properties.py
"""

import sys
import json
import os
import subprocess
import base64
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration - Using STAGING project
MIXPANEL_USERNAME = os.getenv("MIXPANEL_USERNAME")
MIXPANEL_PASSWORD = os.getenv("MIXPANEL_PASSWORD") 
MIXPANEL_PROJECT_ID_STAGING = os.getenv("MIXPANEL_PROJECT_ID_STAGING")

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def query_user_profiles():
    """Query user profiles from staging environment"""
    
    log("🚀 Querying user profiles from STAGING")
    log(f"📊 STAGING Project ID: {MIXPANEL_PROJECT_ID_STAGING}")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Query for user profiles - using correct Query API endpoint
    endpoint = f"https://mixpanel.com/api/query/engage?project_id={MIXPANEL_PROJECT_ID_STAGING}"
    
    log(f"🔗 Endpoint: {endpoint}")
    log("📡 Making API call to get user profiles...")
    
    # Construct CURL command
    curl_cmd = [
        "curl",
        "-X", "GET",
        endpoint,
        "-H", f"Authorization: {auth_header}",
        "-H", "User-Agent: ProfileLister/1.0",
        "-w", "\\nHTTP_CODE:%{http_code}\\nTIME_TOTAL:%{time_total}\\n",
        "--silent",
        "--show-error"
    ]
    
    start_time = time.time()
    
    try:
        # Execute the API call
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
        
        end_time = time.time()
        duration = end_time - start_time
        
        log(f"⏱️  Response time: {duration:.2f} seconds")
        log(f"📊 Exit code: {result.returncode}")
        
        if result.returncode == 0:
            # Parse the response
            response_lines = result.stdout.strip().split('\n')
            
            # Extract HTTP code and timing info
            http_code = None
            time_total = None
            response_body = []
            
            for line in response_lines:
                if line.startswith("HTTP_CODE:"):
                    http_code = line.split(":", 1)[1]
                elif line.startswith("TIME_TOTAL:"):
                    time_total = line.split(":", 1)[1]
                else:
                    response_body.append(line)
            
            log(f"🌐 HTTP Code: {http_code}")
            log(f"⏱️  Total time: {time_total}s")
            
            # Join response body
            response_text = '\n'.join(response_body).strip()
            log(f"📄 Response length: {len(response_text)} characters")
            
            # Try to parse as JSON
            try:
                response_data = json.loads(response_text)
                log("✅ Valid JSON response received")
                
                if "error" in response_data:
                    log(f"❌ API Error: {response_data['error']}")
                    return False
                        
                elif "results" in response_data:
                    log("✅ SUCCESS: Got user profile data!")
                    
                    profiles = response_data.get('results', [])
                    log(f"📊 Number of profiles: {len(profiles)}")
                    
                    if len(profiles) == 0:
                        log("📭 No user profiles found in staging environment")
                        return True
                    
                    # Analyze profile properties
                    analyze_profile_properties(profiles[:5])  # Look at first 5 profiles
                    
                    return True
                    
                else:
                    log(f"📄 Unexpected response structure")
                    log(f"📄 Response keys: {list(response_data.keys())}")
                    return True
                    
            except json.JSONDecodeError:
                log("❌ Response is not valid JSON")
                log(f"📄 Raw response: {response_text[:200]}...")
                return False
                
        else:
            log(f"❌ CURL failed with exit code: {result.returncode}")
            log(f"📄 Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log("⏰ Request timed out after 30 seconds")
        return False
    except Exception as e:
        log(f"❌ Unexpected error: {e}")
        return False

def analyze_profile_properties(profiles):
    """Analyze and display profile properties"""
    
    log("=" * 60)
    log("📋 PROFILE PROPERTIES ANALYSIS")
    log("=" * 60)
    
    all_properties = set()
    default_properties = set()
    custom_properties = set()
    
    for i, profile in enumerate(profiles):
        log(f"\n👤 Profile {i+1}:")
        
        # Get distinct_id
        distinct_id = profile.get('$distinct_id', 'Unknown')
        log(f"  🆔 Distinct ID: {distinct_id}")
        
        # Get properties
        properties = profile.get('$properties', {})
        log(f"  📊 Total properties: {len(properties)}")
        
        # Categorize properties
        for prop_name, prop_value in properties.items():
            all_properties.add(prop_name)
            
            # Check if it's a default/reserved property
            if prop_name.startswith('$') or prop_name.startswith('mp_'):
                default_properties.add(prop_name)
            else:
                custom_properties.add(prop_name)
            
            # Show first few properties as examples
            if len(properties) <= 10:  # If not too many, show them all
                log(f"    📝 {prop_name}: {prop_value}")
        
        if len(properties) > 10:
            log(f"    ... (showing first few properties only)")
            for prop_name, prop_value in list(properties.items())[:3]:
                log(f"    📝 {prop_name}: {prop_value}")
    
    # Summary
    log("\n" + "=" * 60)
    log("📊 PROPERTIES SUMMARY")
    log("=" * 60)
    log(f"📈 Total unique properties found: {len(all_properties)}")
    log(f"🔧 Default/Reserved properties: {len(default_properties)}")
    log(f"⚙️  Custom properties: {len(custom_properties)}")
    
    if default_properties:
        log(f"\n🔧 Default/Reserved Properties:")
        for prop in sorted(default_properties):
            log(f"  • {prop}")
    
    if custom_properties:
        log(f"\n⚙️  Custom Properties:")
        for prop in sorted(custom_properties):
            log(f"  • {prop}")
    
    log("\n📖 According to Mixpanel documentation:")
    log("  • Properties with '$' prefix are default/reserved properties")
    log("  • Properties with 'mp_' prefix are Mixpanel-generated properties")
    log("  • Other properties are custom properties set by your application")

def main():
    log("=" * 60)
    log("👥 MIXPANEL USER PROFILE PROPERTIES LISTER")
    log("=" * 60)
    
    # Check credentials
    if not all([MIXPANEL_PROJECT_ID_STAGING, MIXPANEL_USERNAME, MIXPANEL_PASSWORD]):
        log("❌ Missing staging credentials in .env file")
        sys.exit(1)
    
    # Query user profiles
    success = query_user_profiles()
    
    log("=" * 60)
    if success:
        log("✅ Profile properties listed successfully!")
    else:
        log("❌ Failed to retrieve profile properties")
    log("=" * 60)

if __name__ == "__main__":
    main() 