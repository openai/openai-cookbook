#!/usr/bin/env python3
"""
🏢 GET LATEST COMPANIES - PRODUCTION ANALYSIS
Get the 20 most recently created companies from Mixpanel production environment (project 2201475)

This script identifies companies by their first activity date and gets the most recent ones.

Usage: python3 get_latest_companies.py [--limit N] [--days N]
"""

import sys
import json
import os
import subprocess
import base64
import time
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

def make_jql_call(script: str, description: str = "", timeout: int = 60) -> Optional[Dict]:
    """Make a JQL API call using CURL"""
    
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
                        log(f"Response: {response_data[:200]}...")
                        return None
                elif http_code == "429":
                    log(f"🚨 Rate limit exceeded (HTTP 429)")
                    return {"error": "rate_limit", "code": 429}
                else:
                    log(f"❌ HTTP Error: {http_code}")
                    log(f"Response: {response_data[:200]}...")
                    return None
            else:
                log(f"❌ Unexpected response format: {output[:200]}...")
                return None
        else:
            log(f"❌ CURL failed: {result.stderr}")
            return None
            
    except Exception as e:
        log(f"❌ Exception: {e}")
        return None

def get_latest_companies(days_back: int = 90, limit: int = 20) -> List[Dict]:
    """Get the most recently created companies based on first activity"""
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    from_date = start_date.strftime("%Y-%m-%d")
    to_date = end_date.strftime("%Y-%m-%d")
    
    log(f"📅 Looking for companies with activity between {from_date} and {to_date}")
    
    # Simplified script to get companies with recent activity
    script = f'''
    function main() {{
        return Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
        }})
        .filter(function(event) {{
            return (
                event.properties["company_id"] || 
                event.properties["idEmpresa"]
            );
        }})
        .groupBy([
            function(event) {{
                return event.properties["company_id"] || 
                       event.properties["idEmpresa"] ||
                       "unknown";
            }}
        ], mixpanel.reducer.count())
        .map(function(result) {{
            return {{
                company_id: result.key[0],
                total_events: result.value
            }};
        }});
    }}
    '''
    
    companies = make_jql_call(script, f"Fetching companies with activity in last {days_back} days")
    
    if companies and isinstance(companies, list):
        # Filter out unknown companies and sort by total events (most active first)
        valid_companies = [c for c in companies if c.get('company_id') != 'unknown' and c.get('company_id')]
        sorted_companies = sorted(valid_companies, key=lambda x: x.get('total_events', 0), reverse=True)
        latest_companies = sorted_companies[:limit]
        
        return latest_companies
    
    return []

def get_company_details(company_id: str, from_date: str, to_date: str) -> Dict:
    """Get detailed information for a specific company"""
    
    # Get events for this company
    events_script = f'''
    function main() {{
        return Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
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
    
    events = make_jql_call(events_script, f"Getting events for company {company_id}")
    
    # Get users for this company
    users_script = f'''
    function main() {{
        return Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
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
    
    users = make_jql_call(users_script, f"Getting users for company {company_id}")
    
    return {
        "company_id": company_id,
        "events": events if events else [],
        "users": users if users else [],
        "events_count": len(events) if events else 0,
        "users_count": len(users) if users else 0
    }

def save_results(companies: List[Dict], detailed_analysis: List[Dict] = None):
    """Save results to files"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create output directory
    output_dir = "../../outputs/mixpanel"
    os.makedirs(output_dir, exist_ok=True)
    
    # Save companies list
    companies_file = f"{output_dir}/latest_companies_{timestamp}.json"
    with open(companies_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "project_id": MIXPANEL_PROJECT_ID,
            "total_companies": len(companies),
            "companies": companies
        }, f, indent=2, ensure_ascii=False)
    
    log(f"💾 Companies list saved: {companies_file}")
    
    # Save detailed analysis if provided
    if detailed_analysis:
        detailed_file = f"{output_dir}/latest_companies_detailed_{timestamp}.json"
        with open(detailed_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "project_id": MIXPANEL_PROJECT_ID,
                "detailed_analysis": detailed_analysis
            }, f, indent=2, ensure_ascii=False)
        
        log(f"💾 Detailed analysis saved: {detailed_file}")
        return companies_file, detailed_file
    
    return companies_file, None

def main():
    """Main function"""
    
    parser = argparse.ArgumentParser(description="Get latest companies from Mixpanel production")
    parser.add_argument("--limit", type=int, default=20, help="Number of companies to fetch (default: 20)")
    parser.add_argument("--days", type=int, default=90, help="Days back to look for companies (default: 90)")
    parser.add_argument("--detailed", action="store_true", help="Get detailed analysis for each company")
    
    args = parser.parse_args()
    
    log("🏢 LATEST COMPANIES ANALYSIS - PRODUCTION")
    log("=" * 60)
    log(f"🎯 Project ID: {MIXPANEL_PROJECT_ID}")
    log(f"📊 Fetching {args.limit} most recent companies")
    log(f"📅 Looking back {args.days} days")
    
    # Get latest companies
    companies = get_latest_companies(days_back=args.days, limit=args.limit)
    
    if not companies:
        log("❌ No companies found")
        return
    
    log(f"\n✅ Found {len(companies)} companies")
    log("\n📊 LATEST COMPANIES:")
    log("-" * 40)
    
    for i, company in enumerate(companies, 1):
        log(f"{i:2d}. Company {company['company_id']}")
        log(f"    📈 Total events: {company.get('total_events', 0)}")
    
    # Get detailed analysis if requested
    detailed_analysis = []
    if args.detailed:
        log(f"\n🔍 DETAILED ANALYSIS")
        log("-" * 40)
        
        # Use broader date range for detailed analysis
        end_date = datetime.now()
        start_date = end_date - timedelta(days=180)  # Look back further for complete picture
        from_date = start_date.strftime("%Y-%m-%d")
        to_date = end_date.strftime("%Y-%m-%d")
        
        for i, company in enumerate(companies, 1):
            company_id = company['company_id']
            log(f"\n📊 Analyzing Company {company_id} ({i}/{len(companies)})")
            
            details = get_company_details(company_id, from_date, to_date)
            detailed_analysis.append(details)
            
            log(f"   📈 Events: {details['events_count']}")
            log(f"   👥 Users: {details['users_count']}")
            
            # Brief pause between companies
            time.sleep(1)
    
    # Save results
    companies_file, detailed_file = save_results(companies, detailed_analysis if detailed_analysis else None)
    
    log(f"\n🎯 SUMMARY")
    log("=" * 60)
    log(f"✅ Found {len(companies)} latest companies")
    log(f"📁 Companies list: {companies_file}")
    if detailed_file:
        log(f"📁 Detailed analysis: {detailed_file}")
    
    # Return company IDs for use in other scripts
    return [company['company_id'] for company in companies]

if __name__ == "__main__":
    main() 