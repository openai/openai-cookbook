#!/usr/bin/env python3
"""
📈 GET REAL USER EVENTS FROM MIXPANEL - FIXED VERSION
Gets top events for real users using direct CURL API calls with proper URL encoding

Usage: python3 get_real_user_events_fixed.py
"""

import sys
import json
import os
import subprocess
import base64
import time
import urllib.parse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration - Using STAGING project
MIXPANEL_USERNAME = os.getenv("MIXPANEL_USERNAME")
MIXPANEL_PASSWORD = os.getenv("MIXPANEL_PASSWORD") 
MIXPANEL_PROJECT_ID_STAGING = os.getenv("MIXPANEL_PROJECT_ID_STAGING")

# Real users found in staging environment
REAL_USERS = [
    "valeria.gonzalez@cabify.com",
    "vilaconstanza@hotmail.com", 
    "oficinariogallegos@gmail.com",
    "andresperez@rpa-consulting.com",
    "clavorato@geneva.com.ar"
]

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def url_encode_properly(value):
    """Properly URL encode a value"""
    return urllib.parse.quote(value, safe='')

def get_user_profile_activity(distinct_id):
    """Get profile activity for a specific user using engage endpoint"""
    
    log(f"🚀 Getting profile for user: {distinct_id}")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Use the engage endpoint for user profiles
    # Properly encode the distinct_id parameter
    encoded_distinct_id = url_encode_properly(distinct_id)
    endpoint = f"https://mixpanel.com/api/engage?project_id={MIXPANEL_PROJECT_ID_STAGING}&distinct_id={encoded_distinct_id}"
    
    log(f"🔗 Endpoint: {endpoint}")
    log("📡 Making API call...")
    
    # Construct CURL command
    curl_cmd = [
        "curl",
        "-X", "GET",
        endpoint,
        "-H", f"Authorization: {auth_header}",
        "-H", "User-Agent: UserProfileGetter/1.0",
        "-w", "\\nHTTP_CODE:%{http_code}\\nTIME_TOTAL:%{time_total}\\n",
        "--silent",
        "--show-error"
    ]
    
    return execute_api_call(curl_cmd, f"profile for {distinct_id}")

def get_events_with_proper_segmentation():
    """Get events using proper segmentation endpoint"""
    
    log("🚀 Getting events with proper segmentation...")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Calculate date range (last 7 days for real data)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    from_date = start_date.strftime("%Y-%m-%d")
    to_date = end_date.strftime("%Y-%m-%d")
    
    # Using a specific event instead of wildcard
    event_name = url_encode_properly("Login")
    endpoint = f"https://mixpanel.com/api/query/segmentation?project_id={MIXPANEL_PROJECT_ID_STAGING}&event={event_name}&from_date={from_date}&to_date={to_date}&unit=day"
    
    log(f"🔗 Endpoint: {endpoint}")
    log(f"📅 Date range: {from_date} to {to_date}")
    log("📡 Making API call...")
    
    # Construct CURL command
    curl_cmd = [
        "curl",
        "-X", "GET",
        endpoint,
        "-H", f"Authorization: {auth_header}",
        "-H", "User-Agent: SegmentationGetter/1.0",
        "-w", "\\nHTTP_CODE:%{http_code}\\nTIME_TOTAL:%{time_total}\\n",
        "--silent",
        "--show-error"
    ]
    
    return execute_api_call(curl_cmd, "segmented Login events")

def get_event_data_export(days=7):
    """Try to get event data using export endpoint"""
    
    log("🚀 Getting event data using export endpoint...")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    from_date = start_date.strftime("%Y-%m-%d")
    to_date = end_date.strftime("%Y-%m-%d")
    
    # Use export endpoint
    endpoint = f"https://data.mixpanel.com/api/2.0/export?project_id={MIXPANEL_PROJECT_ID_STAGING}&from_date={from_date}&to_date={to_date}"
    
    log(f"🔗 Endpoint: {endpoint}")
    log(f"📅 Date range: {from_date} to {to_date}")
    log("📡 Making API call...")
    
    # Construct CURL command
    curl_cmd = [
        "curl",
        "-X", "GET",
        endpoint,
        "-H", f"Authorization: {auth_header}",
        "-H", "User-Agent: EventExporter/1.0",
        "-w", "\\nHTTP_CODE:%{http_code}\\nTIME_TOTAL:%{time_total}\\n",
        "--silent",
        "--show-error"
    ]
    
    return execute_api_call(curl_cmd, "exported events")

def get_top_events_overall():
    """Get overall top events from staging environment"""
    
    log("🚀 Getting overall top events from staging...")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Simple request for top events
    endpoint = f"https://mixpanel.com/api/query/events/top?project_id={MIXPANEL_PROJECT_ID_STAGING}&type=general&limit=10"
    
    log(f"🔗 Endpoint: {endpoint}")
    log("📡 Making API call...")
    
    # Construct CURL command
    curl_cmd = [
        "curl",
        "-X", "GET",
        endpoint,
        "-H", f"Authorization: {auth_header}",
        "-H", "User-Agent: TopEventsGetter/1.0",
        "-w", "\\nHTTP_CODE:%{http_code}\\nTIME_TOTAL:%{time_total}\\n",
        "--silent",
        "--show-error"
    ]
    
    return execute_api_call(curl_cmd, "overall top events")

def execute_api_call(curl_cmd, description):
    """Execute API call and parse response"""
    
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
            
            # Show first 200 chars of response for debugging
            log(f"📄 Response preview: {response_text[:200]}...")
            
            # Try to parse as JSON
            try:
                response_data = json.loads(response_text)
                log("✅ Valid JSON response received")
                
                if "error" in response_data:
                    log(f"❌ API Error: {response_data['error']}")
                    return None
                        
                else:
                    log(f"✅ SUCCESS: Got {description}!")
                    return response_data
                    
            except json.JSONDecodeError:
                log("❌ Response is not valid JSON")
                log(f"📄 Raw response first 500 chars: {response_text[:500]}")
                
                # Check if it's NDJSON (newline-delimited JSON)
                if response_text.strip():
                    lines = response_text.strip().split('\n')
                    log(f"📄 Response has {len(lines)} lines, might be NDJSON")
                    
                    # Try to parse first line as JSON
                    if lines:
                        try:
                            first_event = json.loads(lines[0])
                            log("✅ First line is valid JSON (NDJSON format)")
                            return {"events": lines, "format": "ndjson"}
                        except json.JSONDecodeError:
                            log("❌ First line is not valid JSON either")
                
                return None
                
        else:
            log(f"❌ CURL failed with exit code: {result.returncode}")
            log(f"📄 Error: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        log("⏰ Request timed out after 30 seconds")
        return None
    except Exception as e:
        log(f"❌ Unexpected error: {e}")
        return None

def analyze_event_data(data, data_type):
    """Analyze and display event data"""
    
    log(f"\n📊 ANALYZING {data_type.upper()}:")
    log("=" * 50)
    
    if data_type == "top_events":
        if "events" in data:
            events = data["events"]
            log(f"📈 Found {len(events)} top events:")
            for i, event in enumerate(events[:10], 1):
                event_name = event.get("event", "Unknown")
                count = event.get("amount", 0)
                log(f"  {i}. {event_name}: {count} occurrences")
        else:
            log("📄 Unexpected data structure for top events")
            log(f"📄 Keys: {list(data.keys())}")
    
    elif data_type == "segmentation":
        log(f"📄 Segmentation data structure:")
        log(f"📄 Keys: {list(data.keys())}")
        
        # Try to extract event counts if available
        if "data" in data:
            event_data = data["data"]
            log(f"📈 Event data contains {len(event_data)} entries")
            
            # Show first few entries
            for key, value in list(event_data.items())[:5]:
                log(f"  📅 {key}: {value}")
    
    elif data_type == "exported_events":
        if data.get("format") == "ndjson":
            events = data.get("events", [])
            log(f"📈 Found {len(events)} event lines in NDJSON format")
            
            # Parse a few events to show structure
            for i, event_line in enumerate(events[:3]):
                try:
                    event = json.loads(event_line)
                    event_name = event.get("event", "Unknown")
                    log(f"  📅 Event {i+1}: {event_name}")
                except:
                    log(f"  ❌ Could not parse event line {i+1}")
        else:
            log(f"📄 Export data structure:")
            log(f"📄 Keys: {list(data.keys())}")
    
    elif data_type.startswith("profile"):
        log(f"📄 Profile data structure:")
        log(f"📄 Keys: {list(data.keys())}")
        
        if "results" in data:
            results = data["results"]
            log(f"👤 Found {len(results)} profile results")
    
    else:
        log(f"📄 Data structure for {data_type}:")
        log(f"📄 Keys: {list(data.keys())}")

def main():
    log("=" * 60)
    log("📈 REAL USER EVENTS FROM MIXPANEL STAGING - FIXED")
    log("=" * 60)
    
    # Check credentials
    if not all([MIXPANEL_PROJECT_ID_STAGING, MIXPANEL_USERNAME, MIXPANEL_PASSWORD]):
        log("❌ Missing staging credentials in .env file")
        sys.exit(1)
    
    log(f"📊 Using STAGING Project ID: {MIXPANEL_PROJECT_ID_STAGING}")
    log(f"👥 Real users available: {len(REAL_USERS)}")
    
    # 1. Get overall top events (this worked before)
    log("\n🎯 STEP 1: Getting overall top events...")
    top_events_data = get_top_events_overall()
    if top_events_data:
        analyze_event_data(top_events_data, "top_events")
    
    # 2. Try segmentation with specific event
    log("\n🎯 STEP 2: Getting Login events with segmentation...")
    segmentation_data = get_events_with_proper_segmentation()
    if segmentation_data:
        analyze_event_data(segmentation_data, "segmentation")
    
    # 3. Try to get user profile (instead of stream query)
    log(f"\n🎯 STEP 3: Getting profile for specific user...")
    sample_user = REAL_USERS[0]  # valeria.gonzalez@cabify.com
    user_profile_data = get_user_profile_activity(sample_user)
    if user_profile_data:
        analyze_event_data(user_profile_data, "profile")
    
    # 4. Try event export endpoint
    log(f"\n🎯 STEP 4: Getting exported events...")
    export_data = get_event_data_export()
    if export_data:
        analyze_event_data(export_data, "exported_events")
    
    log("\n" + "=" * 60)
    log("✅ Fixed real user events analysis complete!")
    log("=" * 60)

if __name__ == "__main__":
    main() 