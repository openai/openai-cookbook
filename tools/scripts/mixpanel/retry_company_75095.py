#!/usr/bin/env python3
"""
🏢 RETRY ANALYSIS FOR COMPANY 75095
Focused analysis for the company that hit rate limit

Usage: python3 retry_company_75095.py
"""

import sys
import json
import os
import subprocess
import base64
import time
import csv
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional

# Load environment variables
load_dotenv()

# Configuration
MIXPANEL_USERNAME = os.getenv("MIXPANEL_USERNAME")
MIXPANEL_PASSWORD = os.getenv("MIXPANEL_PASSWORD") 
MIXPANEL_PROJECT_ID = os.getenv("MIXPANEL_PROJECT_ID", "2201475")
BASE_URL = "https://mixpanel.com/api/query/jql"

# Company to retry
COMPANY_TO_RETRY = {"id": "75095", "total_events": 125629}

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def create_auth_header():
    """Create basic auth header for API calls"""
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    return f"Basic {encoded_auth}"

def make_jql_call(script: str, description: str = "", timeout: int = 60):
    """Make a JQL API call using CURL with improved error handling"""
    
    log(f"🔍 {description}")
    
    # Create the payload
    payload = {
        "script": script,
        "project_id": MIXPANEL_PROJECT_ID
    }
    
    # Create temporary file for payload
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(payload, f)
        payload_file = f.name
    
    try:
        # Construct CURL command
        curl_cmd = [
            "curl",
            "-X", "POST",
            BASE_URL,
            "-H", f"Authorization: {create_auth_header()}",
            "-H", "Content-Type: application/json",
            "-H", "User-Agent: ColppyAnalysis/1.0",
            "--data", f"@{payload_file}",
            "--silent",
            "--show-error",
            "-w", "HTTP_CODE:%{http_code}",
            "--max-time", str(timeout)
        ]
        
        start_time = time.time()
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=timeout + 5)
        end_time = time.time()
        
        # Clean up temp file
        os.unlink(payload_file)
        
        if result.returncode == 0:
            # Parse response
            output = result.stdout
            if "HTTP_CODE:" in output:
                parts = output.rsplit("HTTP_CODE:", 1)
                response_data = parts[0].strip()
                http_code = parts[1].strip()
                
                if http_code == "200":
                    try:
                        data = json.loads(response_data)
                        log(f"✅ Success: {len(data) if isinstance(data, list) else 'N/A'} results in {end_time - start_time:.2f}s")
                        return data
                    except json.JSONDecodeError as e:
                        log(f"❌ JSON decode error: {e}")
                        return None
                elif http_code == "429":
                    log(f"🚨 Rate limit exceeded (HTTP 429)")
                    return {"error": "rate_limit", "code": 429}
                else:
                    log(f"❌ HTTP Error: {http_code}")
                    return None
            else:
                log(f"❌ Unexpected response format")
                return None
        else:
            log(f"❌ CURL failed: {result.stderr}")
            return None
            
    except Exception as e:
        log(f"❌ Exception: {e}")
        return None

def analyze_company_events(company_id: str) -> Optional[Dict]:
    """Get top events for a specific company"""
    
    script = f'''
    function main() {{
        return Events({{
            from_date: "2024-01-01",
            to_date: "2025-01-15"
        }})
        .filter(function(event) {{
            return (
                event.properties["company_id"] === "{company_id}" ||
                event.properties["idEmpresa"] === "{company_id}" ||
                (Array.isArray(event.properties["company"]) && event.properties["company"].indexOf("{company_id}") >= 0) ||
                (event.properties["company"] === "{company_id}")
            );
        }})
        .groupBy(["name"], mixpanel.reducer.count())
        .map(function(result) {{
            return {{
                event_name: result.key[0],
                count: result.value
            }};
        }});
    }}
    '''
    
    return make_jql_call(script, f"Getting events for company {company_id}")

def analyze_company_users(company_id: str) -> Optional[Dict]:
    """Get users for a specific company"""
    
    script = f'''
    function main() {{
        return Events({{
            from_date: "2024-01-01",
            to_date: "2025-01-15"
        }})
        .filter(function(event) {{
            return (
                event.properties["company_id"] === "{company_id}" ||
                event.properties["idEmpresa"] === "{company_id}" ||
                (Array.isArray(event.properties["company"]) && event.properties["company"].indexOf("{company_id}") >= 0) ||
                (event.properties["company"] === "{company_id}")
            );
        }})
        .groupBy([
            function(event) {{
                return event.properties["$user_id"] || 
                       event.properties["Email"] || 
                       event.properties["email"] || 
                       event.properties["$email"] ||
                       event.properties["idUsuario"] || 
                       event.properties["usuario"] || 
                       event.distinct_id ||
                       "unknown";
            }}
        ], mixpanel.reducer.count())
        .map(function(result) {{
            return {{
                user_id: result.key[0],
                event_count: result.value
            }};
        }});
    }}
    '''
    
    return make_jql_call(script, f"Getting users for company {company_id}")

def save_company_analysis(analysis: Dict):
    """Save analysis to file"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create output directory
    output_dir = "../../outputs/mixpanel"
    os.makedirs(output_dir, exist_ok=True)
    
    # Save JSON
    json_file = f"{output_dir}/company_75095_analysis_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    log(f"💾 Analysis saved: {json_file}")
    return json_file

def main():
    """Main analysis function for company 75095"""
    
    log("🏢 RETRY ANALYSIS FOR COMPANY 75095")
    log("=" * 50)
    log(f"🔑 Project ID: {MIXPANEL_PROJECT_ID}")
    log(f"🏢 Company ID: {COMPANY_TO_RETRY['id']}")
    log(f"📊 Expected Events: {COMPANY_TO_RETRY['total_events']:,}")
    
    company_id = COMPANY_TO_RETRY['id']
    
    analysis = {
        "company_id": company_id,
        "total_events": COMPANY_TO_RETRY['total_events'],
        "analysis_timestamp": datetime.now().isoformat(),
        "retry_attempt": True
    }
    
    # Get company events
    log(f"\n🎯 Step 1: Getting events for company {company_id}")
    events_data = analyze_company_events(company_id)
    
    if events_data and isinstance(events_data, dict) and events_data.get("error") == "rate_limit":
        log(f"🚨 Still hitting rate limit - need to wait longer")
        analysis["error"] = "rate_limit_events"
        analysis["status"] = "FAILED"
        
    elif events_data and isinstance(events_data, list):
        # Sort events by count
        sorted_events = sorted(events_data, key=lambda x: x.get('count', 0), reverse=True)
        analysis["event_types_count"] = len(sorted_events)
        analysis["top_events"] = sorted_events[:10]  # Top 10 events
        
        top_event = sorted_events[0] if sorted_events else {"event_name": "Unknown", "count": 0}
        log(f"✅ Events Analysis Complete!")
        log(f"   🎯 Top Event: {top_event['event_name']} ({top_event['count']:,} times)")
        log(f"   📈 Event Types: {len(sorted_events)}")
        
        # Wait before getting users
        log(f"\n⏳ Waiting 5 seconds before user analysis...")
        time.sleep(5)
        
        # Get company users
        log(f"👥 Step 2: Getting users for company {company_id}")
        users_data = analyze_company_users(company_id)
        
        if users_data and isinstance(users_data, dict) and users_data.get("error") == "rate_limit":
            log(f"🚨 Rate limit hit on users - partial success")
            analysis["error"] = "rate_limit_users" 
            analysis["status"] = "PARTIAL"
            
        elif users_data and isinstance(users_data, list):
            # Sort users by event count
            sorted_users = sorted(users_data, key=lambda x: x.get('event_count', 0), reverse=True)
            analysis["users_count"] = len(sorted_users)
            analysis["top_users"] = sorted_users[:10]  # Top 10 users
            
            top_user = sorted_users[0] if sorted_users else {"user_id": "Unknown", "event_count": 0}
            log(f"✅ Users Analysis Complete!")
            log(f"   🏆 Most Active User: {top_user['user_id']} ({top_user['event_count']:,} events)")
            log(f"   👥 Total Users: {len(sorted_users)}")
            
            analysis["status"] = "SUCCESS"
            
        else:
            analysis["error"] = "no_users_data"
            analysis["status"] = "PARTIAL"
            log(f"❌ No users data available")
    else:
        analysis["error"] = "no_events_data" 
        analysis["status"] = "FAILED"
        log(f"❌ No events data available")
    
    # Save results
    output_file = save_company_analysis(analysis)
    
    # Final summary
    log(f"\n" + "=" * 50)
    log("📈 COMPANY 75095 ANALYSIS SUMMARY")
    log("=" * 50)
    log(f"🏢 Company ID: {company_id}")
    log(f"📊 Status: {analysis.get('status', 'UNKNOWN')}")
    
    if analysis.get('status') == 'SUCCESS':
        top_event = analysis.get('top_events', [{}])[0]
        top_user = analysis.get('top_users', [{}])[0]
        log(f"🎯 Top Event: {top_event.get('event_name', 'N/A')} ({top_event.get('count', 0):,}×)")
        log(f"👥 Users: {analysis.get('users_count', 0)}")
        log(f"🏆 Top User: {top_user.get('user_id', 'N/A')} ({top_user.get('event_count', 0):,} events)")
        log(f"✅ COMPLETE SUCCESS! 🎉")
    elif analysis.get('status') == 'PARTIAL':
        log(f"⚠️ Partial success - events OK, users failed")
    else:
        log(f"❌ Analysis failed: {analysis.get('error', 'Unknown error')}")

if __name__ == "__main__":
    main() 