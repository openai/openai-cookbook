#!/usr/bin/env python3
"""
🏢 TOP COMPANIES ANALYSIS - CURL API ONLY
Comprehensive analysis of top 10 companies using direct CURL API calls to avoid MCP rate limits

Usage: python3 top_companies_curl_analysis.py [--companies N] [--delay N]
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

def get_top_companies(from_date: str = "2024-01-01", to_date: str = "2025-01-15", limit: int = 20) -> List[Dict]:
    """Get top companies by event count using CURL JQL"""
    
    script = f'''
    function main() {{
        return Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
        }})
        .filter(function(event) {{
            return (
                event.properties["company_id"] || 
                event.properties["idEmpresa"] ||
                (event.properties["company"] && event.properties["company"].length > 0)
            );
        }})
        .groupBy([
            function(event) {{
                return event.properties["company_id"] || 
                       event.properties["idEmpresa"] ||
                       (Array.isArray(event.properties["company"]) ? event.properties["company"][0] : event.properties["company"]) ||
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
    
    companies = make_jql_call(script, f"Fetching top {limit} companies by activity")
    
    if companies and isinstance(companies, list):
        # Sort by total_events descending and take top N
        sorted_companies = sorted(companies, key=lambda x: x.get('total_events', 0), reverse=True)
        return sorted_companies[:limit]
    
    return []

def get_company_events(company_id: str, from_date: str = "2024-01-01", to_date: str = "2025-01-15") -> List[Dict]:
    """Get top events for a specific company"""
    
    script = f'''
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
                (event.properties["company"] === "{company_id}") ||
                (event.properties["$groups"] && event.properties["$groups"]["Company"] === "{company_id}")
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
    
    return make_jql_call(script, f"Fetching events for company {company_id}")

def get_company_users(company_id: str, from_date: str = "2024-01-01", to_date: str = "2025-01-15") -> List[Dict]:
    """Get users for a specific company"""
    
    script = f'''
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
                (event.properties["company"] === "{company_id}") ||
                (event.properties["$groups"] && event.properties["$groups"]["Company"] === "{company_id}")
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
    
    return make_jql_call(script, f"Fetching users for company {company_id}")

def analyze_company(company_data: Dict, delay: float = 2.0) -> Dict:
    """Complete analysis of a single company"""
    
    company_id = company_data.get('company_id', 'unknown')
    total_events = company_data.get('total_events', 0)
    
    log(f"\n📊 Analyzing Company {company_id}")
    log(f"   Total Events: {total_events:,}")
    
    # Get company events
    time.sleep(delay)  # Rate limiting delay
    events = get_company_events(company_id)
    
    if events and isinstance(events, list) and not (len(events) >= 1 and isinstance(events[0], dict) and events[0].get("error") == "rate_limit"):
        # Sort events by count descending
        sorted_events = sorted(events, key=lambda x: x.get('count', 0), reverse=True)
        
        # Get company users
        time.sleep(delay)  # Rate limiting delay
        users = get_company_users(company_id)
        
        if users and isinstance(users, list) and not (len(users) >= 1 and isinstance(users[0], dict) and users[0].get("error") == "rate_limit"):
            # Sort users by event count descending
            sorted_users = sorted(users, key=lambda x: x.get('event_count', 0), reverse=True)
            
            analysis = {
                "company_id": company_id,
                "total_events": total_events,
                "event_types_count": len(sorted_events),
                "users_count": len(sorted_users),
                "top_events": sorted_events[:10],  # Top 10 events
                "top_users": sorted_users[:10],    # Top 10 users
                "analysis_timestamp": datetime.now().isoformat()
            }
            
            # Log summary
            top_event = sorted_events[0] if sorted_events else {"event_name": "Unknown", "count": 0}
            top_user = sorted_users[0] if sorted_users else {"user_id": "Unknown", "event_count": 0}
            
            log(f"   🎯 Top Event: {top_event['event_name']} ({top_event['count']:,} times)")
            log(f"   🏆 Most Active User: {top_user['user_id']} ({top_user['event_count']:,} events)")
            log(f"   ✅ Found {len(sorted_events)} event types, {len(sorted_users)} users")
            
            return analysis
        else:
            if users and isinstance(users, dict) and users.get("error") == "rate_limit":
                log(f"   🚨 Rate limit hit getting users for company {company_id}")
                return {"company_id": company_id, "error": "rate_limit", "stage": "users"}
            elif users and isinstance(users, list) and len(users) >= 1 and isinstance(users[0], dict) and users[0].get("error") == "rate_limit":
                log(f"   🚨 Rate limit hit getting users for company {company_id}")
                return {"company_id": company_id, "error": "rate_limit", "stage": "users"}
            else:
                log(f"   ❌ No users data for company {company_id}")
                return {"company_id": company_id, "error": "no_users_data"}
    else:
        if events and isinstance(events, dict) and events.get("error") == "rate_limit":
            log(f"   🚨 Rate limit hit getting events for company {company_id}")
            return {"company_id": company_id, "error": "rate_limit", "stage": "events"}
        elif events and isinstance(events, list) and len(events) >= 1 and isinstance(events[0], dict) and events[0].get("error") == "rate_limit":
            log(f"   🚨 Rate limit hit getting events for company {company_id}")
            return {"company_id": company_id, "error": "rate_limit", "stage": "events"}
        else:
            log(f"   ❌ No events data for company {company_id}")
            return {"company_id": company_id, "error": "no_events_data"}

def save_results(companies_analysis: List[Dict], output_prefix: str = "top_companies_curl"):
    """Save analysis results to JSON and CSV files"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save full JSON
    json_file = f"../../outputs/mixpanel/{output_prefix}_{timestamp}.json"
    os.makedirs(os.path.dirname(json_file), exist_ok=True)
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(companies_analysis, f, indent=2, ensure_ascii=False)
    
    # Save CSV summary
    csv_file = f"../../outputs/mixpanel/{output_prefix}_summary_{timestamp}.csv"
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Company ID', 'Total Events', 'Event Types', 'Users', 
            'Top Event', 'Top Event Count', 'Top User', 'Top User Events'
        ])
        
        for analysis in companies_analysis:
            if analysis.get('error'):
                writer.writerow([
                    analysis.get('company_id', 'Unknown'),
                    'ERROR', analysis.get('error', ''), '', '', '', '', ''
                ])
            else:
                top_event = analysis.get('top_events', [{}])[0]
                top_user = analysis.get('top_users', [{}])[0]
                
                writer.writerow([
                    analysis.get('company_id', 'Unknown'),
                    analysis.get('total_events', 0),
                    analysis.get('event_types_count', 0),
                    analysis.get('users_count', 0),
                    top_event.get('event_name', ''),
                    top_event.get('count', 0),
                    top_user.get('user_id', ''),
                    top_user.get('event_count', 0)
                ])
    
    log(f"\n💾 Results saved:")
    log(f"   📄 JSON: {json_file}")
    log(f"   📊 CSV:  {csv_file}")
    
    return json_file, csv_file

def main():
    """Main analysis function"""
    
    parser = argparse.ArgumentParser(description='Analyze top companies using CURL API calls')
    parser.add_argument('--companies', type=int, default=10, help='Number of top companies to analyze')
    parser.add_argument('--delay', type=float, default=3.0, help='Delay between API calls (seconds)')
    parser.add_argument('--from-date', default='2024-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', default='2025-01-15', help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    log("🏢 COLPPY TOP COMPANIES ANALYSIS - CURL API MODE")
    log("=" * 60)
    log(f"📊 Period: {args.from_date} to {args.to_date}")
    log(f"🏢 Companies to analyze: {args.companies}")
    log(f"⏱️  API delay: {args.delay}s")
    log(f"🔑 Project ID: {MIXPANEL_PROJECT_ID}")
    
    # Step 1: Get top companies
    log(f"\n🔍 Step 1: Getting top {args.companies} companies...")
    top_companies = get_top_companies(args.from_date, args.to_date, args.companies * 2)  # Get more to account for filtering
    
    if not top_companies:
        log("❌ Failed to get companies data")
        return
    
    # Filter out unknown/invalid companies
    valid_companies = [c for c in top_companies if c.get('company_id') not in ['unknown', '', None] and c.get('total_events', 0) > 0]
    companies_to_analyze = valid_companies[:args.companies]
    
    log(f"✅ Found {len(valid_companies)} valid companies")
    log(f"📊 Will analyze top {len(companies_to_analyze)} companies")
    
    # Step 2: Analyze each company
    log(f"\n🔍 Step 2: Analyzing individual companies...")
    companies_analysis = []
    successful_analyses = 0
    rate_limit_hits = 0
    
    for i, company_data in enumerate(companies_to_analyze, 1):
        log(f"\n📊 Analyzing Company {i}/{len(companies_to_analyze)}: {company_data['company_id']}")
        
        analysis = analyze_company(company_data, args.delay)
        companies_analysis.append(analysis)
        
        if analysis.get('error') == 'rate_limit':
            rate_limit_hits += 1
            log(f"🚨 Rate limit hit - pausing for 30 seconds...")
            time.sleep(30)
        elif not analysis.get('error'):
            successful_analyses += 1
    
    # Step 3: Save results
    log(f"\n💾 Step 3: Saving results...")
    json_file, csv_file = save_results(companies_analysis)
    
    # Step 4: Summary
    log(f"\n" + "=" * 60)
    log("📈 ANALYSIS SUMMARY")
    log("=" * 60)
    log(f"📊 Period: {args.from_date} to {args.to_date}")
    log(f"🏢 Companies Analyzed: {len(companies_to_analyze)}")
    log(f"✅ Successful Analyses: {successful_analyses}")
    log(f"❌ Failed/Rate Limited: {len(companies_to_analyze) - successful_analyses}")
    log(f"🚨 Rate Limit Hits: {rate_limit_hits}")
    
    if successful_analyses > 0:
        log(f"\n🔝 TOP COMPANIES BY ACTIVITY:")
        log("-" * 40)
        for i, analysis in enumerate([a for a in companies_analysis if not a.get('error')][:5], 1):
            top_event = analysis.get('top_events', [{}])[0]
            top_user = analysis.get('top_users', [{}])[0]
            
            log(f"{i}. Company {analysis['company_id']}")
            log(f"   📊 Total Events: {analysis['total_events']:,}")
            log(f"   👥 Total Users: {analysis['users_count']}")
            log(f"   🎯 Top Event: {top_event.get('event_name', 'N/A')} ({top_event.get('count', 0):,} times)")
            log(f"   🏆 Most Active User: {top_user.get('user_id', 'N/A')} ({top_user.get('event_count', 0):,} events)")
            log("")

if __name__ == "__main__":
    main() 