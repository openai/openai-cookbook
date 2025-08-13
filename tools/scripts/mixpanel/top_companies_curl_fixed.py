#!/usr/bin/env python3
"""
🏢 TOP COMPANIES ANALYSIS - CURL API ONLY (CORRECTED)
Comprehensive analysis of top 10 companies using direct CURL API calls

Usage: python3 top_companies_curl_fixed.py [--companies N] [--delay N]
"""

import sys
import json
import os
import subprocess
import base64
import time
import csv
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional

# Load environment variables
load_dotenv()

# Configuration
MIXPANEL_USERNAME = os.getenv("MIXPANEL_USERNAME")
MIXPANEL_PASSWORD = os.getenv("MIXPANEL_PASSWORD") 
MIXPANEL_PROJECT_ID = os.getenv("MIXPANEL_PROJECT_ID", "2201475")
BASE_URL = "https://mixpanel.com/api/query/jql"

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

def main():
    """Main analysis function"""
    
    parser = argparse.ArgumentParser(description='Analyze top companies using CURL API calls')
    parser.add_argument('--companies', type=int, default=5, help='Number of top companies to analyze')
    parser.add_argument('--delay', type=float, default=6.0, help='Delay between API calls (seconds)')
    
    args = parser.parse_args()
    
    log("🏢 COLPPY TOP COMPANIES ANALYSIS - CURL API (CORRECTED)")
    log("=" * 60)
    log(f"🔑 Project ID: {MIXPANEL_PROJECT_ID}")
    log(f"🏢 Companies to analyze: {args.companies}")
    log(f"⏱️  API delay: {args.delay}s")
    
    # Step 1: Get top companies
    log(f"\n🔍 Getting top companies...")
    script = '''
    function main() {
        return Events({
            from_date: "2024-01-01",
            to_date: "2025-01-15"
        })
        .filter(function(event) {
            return (
                event.properties["company_id"] || 
                event.properties["idEmpresa"] ||
                (event.properties["company"] && event.properties["company"].length > 0)
            );
        })
        .groupBy([
            function(event) {
                return event.properties["company_id"] || 
                       event.properties["idEmpresa"] ||
                       (Array.isArray(event.properties["company"]) ? event.properties["company"][0] : event.properties["company"]) ||
                       "unknown";
            }
        ], mixpanel.reducer.count())
        .map(function(result) {
            return {
                company_id: result.key[0],
                total_events: result.value
            };
        });
    }
    '''
    
    companies_data = make_jql_call(script, "Fetching top companies")
    
    if not companies_data or (isinstance(companies_data, dict) and companies_data.get("error") == "rate_limit"):
        log("❌ Failed to get companies data or hit rate limit")
        return
    
    # Sort and filter companies
    if isinstance(companies_data, list):
        valid_companies = [c for c in companies_data 
                          if c.get('company_id') not in ['unknown', '', None] 
                          and c.get('total_events', 0) > 0]
        
        sorted_companies = sorted(valid_companies, key=lambda x: x.get('total_events', 0), reverse=True)
        top_companies = sorted_companies[:args.companies]
        
        log(f"✅ Found {len(valid_companies)} valid companies")
        log(f"📊 Analyzing top {len(top_companies)} companies")
        
        # Show top companies summary
        log(f"\n🔝 TOP {len(top_companies)} COMPANIES BY ACTIVITY:")
        log("-" * 50)
        
        for i, company in enumerate(top_companies, 1):
            company_id = company.get('company_id', 'Unknown')
            total_events = company.get('total_events', 0)
            
            log(f"{i:2d}. Company {company_id}")
            log(f"     📊 Total Events: {total_events:,}")
            
            # Optional: Get basic event info for each company
            if i <= 3:  # Only get details for top 3 to avoid rate limits
                time.sleep(args.delay)
                
                events_script = f'''
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
                
                events_data = make_jql_call(events_script, f"Getting events for company {company_id}")
                
                if events_data and isinstance(events_data, list):
                    sorted_events = sorted(events_data, key=lambda x: x.get('count', 0), reverse=True)
                    if sorted_events:
                        top_event = sorted_events[0]
                        log(f"     🎯 Top Event: {top_event.get('event_name', 'Unknown')} ({top_event.get('count', 0):,} times)")
                        log(f"     📈 Event Types: {len(sorted_events)}")
                elif events_data and isinstance(events_data, dict) and events_data.get("error") == "rate_limit":
                    log(f"     🚨 Rate limit hit for company {company_id}")
                
            log("")
    
    log("\n📈 ANALYSIS COMPLETED!")
    log(f"Total companies found: {len(valid_companies) if 'valid_companies' in locals() else 'N/A'}")

if __name__ == "__main__":
    main() 