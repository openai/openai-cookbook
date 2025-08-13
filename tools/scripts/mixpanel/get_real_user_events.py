#!/usr/bin/env python3
"""
📈 GET REAL USER EVENTS FROM MIXPANEL
Gets top events for real users using direct CURL API calls

Usage: python3 get_real_user_events.py
"""

import sys
import json
import os
import subprocess
import base64
import time
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

def get_user_event_activity(distinct_id, days=30):
    """Get event activity for a specific user"""
    
    log(f"🚀 Getting events for user: {distinct_id}")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    from_date = start_date.strftime("%Y-%m-%d")
    to_date = end_date.strftime("%Y-%m-%d")
    
    # Create the engage endpoint URL for event activity
    # Using the stream endpoint to get user activity
    endpoint = f"https://mixpanel.com/api/stream/query?project_id={MIXPANEL_PROJECT_ID_STAGING}&distinct_ids=[%22{distinct_id}%22]&from_date={from_date}&to_date={to_date}"
    
    log(f"🔗 Endpoint: {endpoint}")
    log(f"📅 Date range: {from_date} to {to_date}")
    log("📡 Making API call...")
    
    # Construct CURL command
    curl_cmd = [
        "curl",
        "-X", "GET",
        endpoint,
        "-H", f"Authorization: {auth_header}",
        "-H", "User-Agent: UserEventGetter/1.0",
        "-w", "\\nHTTP_CODE:%{http_code}\\nTIME_TOTAL:%{time_total}\\n",
        "--silent",
        "--show-error"
    ]
    
    return execute_api_call(curl_cmd, f"events for {distinct_id}")

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

def get_events_with_filters():
    """Get events using segmentation with user filters"""
    
    log("🚀 Getting events with user segmentation...")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    from_date = start_date.strftime("%Y-%m-%d")
    to_date = end_date.strftime("%Y-%m-%d")
    
    # Using segmentation endpoint to get events
    endpoint = f"https://mixpanel.com/api/query/segmentation?project_id={MIXPANEL_PROJECT_ID_STAGING}&event=*&from_date={from_date}&to_date={to_date}&unit=day"
    
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
    
    return execute_api_call(curl_cmd, "segmented events")

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
                log(f"📄 Raw response: {response_text[:300]}...")
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
    
    else:
        log(f"📄 Data structure for {data_type}:")
        log(f"📄 Keys: {list(data.keys())}")

def main():
    log("=" * 60)
    log("📈 REAL USER EVENTS FROM MIXPANEL STAGING")
    log("=" * 60)
    
    # Check credentials
    if not all([MIXPANEL_PROJECT_ID_STAGING, MIXPANEL_USERNAME, MIXPANEL_PASSWORD]):
        log("❌ Missing staging credentials in .env file")
        sys.exit(1)
    
    log(f"📊 Using STAGING Project ID: {MIXPANEL_PROJECT_ID_STAGING}")
    log(f"👥 Real users available: {len(REAL_USERS)}")
    
    # 1. Get overall top events
    log("\n🎯 STEP 1: Getting overall top events...")
    top_events_data = get_top_events_overall()
    if top_events_data:
        analyze_event_data(top_events_data, "top_events")
    
    # 2. Try to get events with segmentation
    log("\n🎯 STEP 2: Getting events with segmentation...")
    segmentation_data = get_events_with_filters()
    if segmentation_data:
        analyze_event_data(segmentation_data, "segmentation")
    
    # 3. Try to get activity for a specific user
    log(f"\n🎯 STEP 3: Getting events for specific user...")
    sample_user = REAL_USERS[0]  # valeria.gonzalez@cabify.com
    user_events_data = get_user_event_activity(sample_user)
    if user_events_data:
        analyze_event_data(user_events_data, "user_events")
    
    log("\n" + "=" * 60)
    log("✅ Real user events analysis complete!")
    log("=" * 60)

if __name__ == "__main__":
    main() 