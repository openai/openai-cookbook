#!/usr/bin/env python3
"""
🏢 DETAILED ANALYSIS OF TOP 10 COLPPY COMPANIES
Comprehensive user and event analysis for the top 10 most active companies

Usage: python3 analyze_10_companies_detailed.py
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

# Top 10 companies identified from previous analysis
TOP_10_COMPANIES = [
    {"id": "69490", "total_events": 298945},
    {"id": "21371", "total_events": 230094},
    {"id": "42359", "total_events": 218870},
    {"id": "49761", "total_events": 169051},
    {"id": "74229", "total_events": 168393},
    {"id": "20999", "total_events": 153211},
    {"id": "53992", "total_events": 146110},
    {"id": "78862", "total_events": 136425},
    {"id": "9003", "total_events": 131873},
    {"id": "75095", "total_events": 125629}
]

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

def save_company_analysis(company_analyses: List[Dict]):
    """Save detailed analysis to files"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create output directory
    output_dir = "../../outputs/mixpanel"
    os.makedirs(output_dir, exist_ok=True)
    
    # Save full JSON
    json_file = f"{output_dir}/top_10_companies_detailed_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(company_analyses, f, indent=2, ensure_ascii=False)
    
    # Save CSV summary
    csv_file = f"{output_dir}/top_10_companies_summary_{timestamp}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Rank', 'Company ID', 'Total Events', 'Event Types', 'Users Count', 
            'Top Event', 'Top Event Count', 'Top User', 'Top User Events', 'Status'
        ])
        
        for i, analysis in enumerate(company_analyses, 1):
            company_id = analysis.get('company_id', 'Unknown')
            status = 'ERROR' if analysis.get('error') else 'SUCCESS'
            
            if analysis.get('error'):
                writer.writerow([
                    i, company_id, analysis.get('total_events', 0), 
                    'ERROR', analysis.get('error', ''), '', '', '', '', status
                ])
            else:
                top_event = analysis.get('top_events', [{}])[0] if analysis.get('top_events') else {}
                top_user = analysis.get('top_users', [{}])[0] if analysis.get('top_users') else {}
                
                writer.writerow([
                    i, company_id, analysis.get('total_events', 0),
                    analysis.get('event_types_count', 0),
                    analysis.get('users_count', 0),
                    top_event.get('event_name', ''),
                    top_event.get('count', 0),
                    top_user.get('user_id', ''),
                    top_user.get('event_count', 0),
                    status
                ])
    
    log(f"\n💾 Analysis saved:")
    log(f"   📄 JSON: {json_file}")
    log(f"   📊 CSV:  {csv_file}")

def main():
    """Main analysis function for top 10 companies"""
    
    log("🏢 DETAILED ANALYSIS OF TOP 10 COLPPY COMPANIES")
    log("=" * 60)
    log(f"🔑 Project ID: {MIXPANEL_PROJECT_ID}")
    log(f"📊 Companies to analyze: {len(TOP_10_COMPANIES)}")
    log(f"⏱️  API delay: 8 seconds between calls")
    
    companies_analysis = []
    successful_analyses = 0
    rate_limit_hits = 0
    
    for i, company_data in enumerate(TOP_10_COMPANIES, 1):
        company_id = company_data['id']
        total_events = company_data['total_events']
        
        log(f"\n📊 ANALYZING COMPANY {i}/10: {company_id}")
        log(f"   Expected Events: {total_events:,}")
        
        analysis = {
            "rank": i,
            "company_id": company_id,
            "total_events": total_events,
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        # Get company events
        events_data = analyze_company_events(company_id)
        
        if events_data and isinstance(events_data, dict) and events_data.get("error") == "rate_limit":
            log(f"   🚨 Rate limit hit getting events - pausing 30 seconds...")
            analysis["error"] = "rate_limit_events"
            rate_limit_hits += 1
            time.sleep(30)
            
        elif events_data and isinstance(events_data, list):
            # Sort events by count
            sorted_events = sorted(events_data, key=lambda x: x.get('count', 0), reverse=True)
            analysis["event_types_count"] = len(sorted_events)
            analysis["top_events"] = sorted_events[:10]  # Top 10 events
            
            top_event = sorted_events[0] if sorted_events else {"event_name": "Unknown", "count": 0}
            log(f"   🎯 Top Event: {top_event['event_name']} ({top_event['count']:,} times)")
            log(f"   📈 Event Types: {len(sorted_events)}")
            
            # Wait before getting users
            time.sleep(8)
            
            # Get company users
            users_data = analyze_company_users(company_id)
            
            if users_data and isinstance(users_data, dict) and users_data.get("error") == "rate_limit":
                log(f"   🚨 Rate limit hit getting users - pausing 30 seconds...")
                analysis["error"] = "rate_limit_users"
                rate_limit_hits += 1
                time.sleep(30)
                
            elif users_data and isinstance(users_data, list):
                # Sort users by event count
                sorted_users = sorted(users_data, key=lambda x: x.get('event_count', 0), reverse=True)
                analysis["users_count"] = len(sorted_users)
                analysis["top_users"] = sorted_users[:10]  # Top 10 users
                
                top_user = sorted_users[0] if sorted_users else {"user_id": "Unknown", "event_count": 0}
                log(f"   🏆 Most Active User: {top_user['user_id']} ({top_user['event_count']:,} events)")
                log(f"   👥 Total Users: {len(sorted_users)}")
                
                successful_analyses += 1
                log(f"   ✅ Analysis complete!")
                
            else:
                analysis["error"] = "no_users_data"
                log(f"   ❌ No users data available")
        else:
            analysis["error"] = "no_events_data" 
            log(f"   ❌ No events data available")
        
        companies_analysis.append(analysis)
        
        # Wait between companies (except last one)
        if i < len(TOP_10_COMPANIES):
            log(f"   ⏳ Waiting 8 seconds before next company...")
            time.sleep(8)
    
    # Save results
    save_company_analysis(companies_analysis)
    
    # Final summary
    log(f"\n" + "=" * 60)
    log("📈 FINAL ANALYSIS SUMMARY")
    log("=" * 60)
    log(f"🏢 Companies Analyzed: {len(TOP_10_COMPANIES)}")
    log(f"✅ Successful Analyses: {successful_analyses}")
    log(f"❌ Failed/Rate Limited: {len(TOP_10_COMPANIES) - successful_analyses}")
    log(f"🚨 Rate Limit Hits: {rate_limit_hits}")
    
    # Show top 5 successful analyses
    successful_companies = [c for c in companies_analysis if not c.get('error')]
    if successful_companies:
        log(f"\n🔝 TOP SUCCESSFULLY ANALYZED COMPANIES:")
        log("-" * 50)
        
        for company in successful_companies[:5]:
            top_event = company.get('top_events', [{}])[0]
            top_user = company.get('top_users', [{}])[0]
            
            log(f"#{company['rank']} Company {company['company_id']}")
            log(f"   📊 Total Events: {company['total_events']:,}")
            log(f"   🎯 Top Event: {top_event.get('event_name', 'N/A')} ({top_event.get('count', 0):,}×)")
            log(f"   👥 Users: {company.get('users_count', 0)}")
            log(f"   🏆 Top User: {top_user.get('user_id', 'N/A')} ({top_user.get('event_count', 0):,} events)")
            log("")

if __name__ == "__main__":
    main() 