#!/usr/bin/env python3
"""
🔍 STAGING MIXPANEL API TEST
Makes exactly ONE API call using STAGING project ID

Usage: python3 staging_test.py
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

def make_single_api_call():
    """Make exactly ONE API call to Mixpanel STAGING"""
    
    log("🚀 Starting STAGING API test")
    log(f"📊 STAGING Project ID: {MIXPANEL_PROJECT_ID_STAGING}")
    log(f"👤 Username: {MIXPANEL_USERNAME}")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Simple request for top 3 events - STAGING PROJECT
    endpoint = f"https://mixpanel.com/api/query/events/top?project_id={MIXPANEL_PROJECT_ID_STAGING}&type=general&limit=3"
    
    log(f"🔗 Endpoint: {endpoint}")
    log("📡 Making API call to STAGING...")
    
    # Construct CURL command
    curl_cmd = [
        "curl",
        "-X", "GET",
        endpoint,
        "-H", f"Authorization: {auth_header}",
        "-H", "User-Agent: StagingTest/1.0",
        "-w", "\\nHTTP_CODE:%{http_code}\\nTIME_TOTAL:%{time_total}\\n",
        "--silent",
        "--show-error"
    ]
    
    start_time = time.time()
    
    try:
        # Execute the single API call
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
                    
                    # Check specifically for rate limit
                    if "rate limit" in response_data['error'].lower():
                        log("🚫 CONFIRMED: Rate limit exceeded on STAGING too")
                        log(f"📊 Full error: {response_data['error']}")
                        return False
                    else:
                        log("❌ Different error (not rate limit)")
                        return False
                        
                elif "results" in response_data:
                    log("✅ SUCCESS: Got results from STAGING!")
                    log(f"📊 Number of events: {len(response_data.get('results', {}))}")
                    
                    # Log the actual events
                    results = response_data.get('results', {})
                    for event_name, count in list(results.items())[:3]:
                        log(f"  📈 {event_name}: {count}")
                    
                    return True
                    
                else:
                    log(f"📄 Unexpected response structure: {response_data}")
                    return True  # Not an error, just unexpected
                    
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

def main():
    log("=" * 60)
    log("🔍 STAGING MIXPANEL API CALL TEST")
    log("=" * 60)
    
    # Check credentials
    if not all([MIXPANEL_PROJECT_ID_STAGING, MIXPANEL_USERNAME, MIXPANEL_PASSWORD]):
        log("❌ Missing staging credentials in .env file")
        log(f"MIXPANEL_PROJECT_ID_STAGING: {MIXPANEL_PROJECT_ID_STAGING}")
        log(f"MIXPANEL_USERNAME: {MIXPANEL_USERNAME}")
        sys.exit(1)
    
    # Make exactly one API call to staging
    success = make_single_api_call()
    
    log("=" * 60)
    if success:
        log("✅ RESULT: STAGING API call successful - No rate limit!")
        log("🎯 Staging environment is working fine")
    else:
        log("❌ RESULT: STAGING API call failed")
        log("🎯 Even staging environment has issues")
    log("=" * 60)

if __name__ == "__main__":
    main() 