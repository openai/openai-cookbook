#!/usr/bin/env python3
"""
🔍 PRODUCTION ANALYSIS: 20 MOST ACTIVE COMPANIES
Direct API analysis of the top 20 most active companies from production environment

Usage: python3 api_usage_comparison.py
"""

import sys
import json
import os
import subprocess
import base64
import time
import openai
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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Production companies - Top 20 most active companies from production environment
TEST_COMPANIES = [
    {"id": "13450", "name": "Company 1", "events": 326770},
    {"id": "36547", "name": "Company 2", "events": 315057}, 
    {"id": "69490", "name": "Company 3", "events": 288743},
    {"id": "49761", "name": "Company 4", "events": 286166},
    {"id": "24153", "name": "Company 5", "events": 275630},
    {"id": "21371", "name": "Company 6", "events": 258827},
    {"id": "55103", "name": "Company 7", "events": 251343},
    {"id": "42359", "name": "Company 8", "events": 238172},
    {"id": "21301", "name": "Company 9", "events": 230647},
    {"id": "87098", "name": "Company 10", "events": 227480},
    {"id": "51450", "name": "Company 11", "events": 205160},
    {"id": "9003", "name": "Company 12", "events": 192252},
    {"id": "74229", "name": "Company 13", "events": 187607},
    {"id": "53992", "name": "Company 14", "events": 181487},
    {"id": "69983", "name": "Company 15", "events": 181255},
    {"id": "50266", "name": "Company 16", "events": 178532},
    {"id": "16246", "name": "Company 17", "events": 177976},
    {"id": "69988", "name": "Company 18", "events": 176802},
    {"id": "38330", "name": "Company 19", "events": 176707},
    {"id": "51624", "name": "Company 20", "events": 175647}
]

class APICallTracker:
    def __init__(self, approach_name: str):
        self.approach_name = approach_name
        self.api_calls = []
        self.total_calls = 0
        self.start_time = None
        self.end_time = None
        
    def start_tracking(self):
        self.start_time = datetime.now()
        self.api_calls = []
        self.total_calls = 0
        log(f"🎯 Starting {self.approach_name} tracking...")
        
    def record_call(self, call_type: str, company_id: str, success: bool, duration: float):
        call_info = {
            "timestamp": datetime.now().isoformat(),
            "call_type": call_type,
            "company_id": company_id,
            "success": success,
            "duration_seconds": duration
        }
        self.api_calls.append(call_info)
        self.total_calls += 1
        
    def end_tracking(self):
        self.end_time = datetime.now()
        total_duration = (self.end_time - self.start_time).total_seconds()
        log(f"⏱️ {self.approach_name} completed in {total_duration:.1f}s")
        log(f"📊 Total API calls: {self.total_calls}")
        return {
            "approach": self.approach_name,
            "total_calls": self.total_calls,
            "total_duration": total_duration,
            "calls_per_second": self.total_calls / total_duration if total_duration > 0 else 0,
            "detailed_calls": self.api_calls
        }

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def create_auth_header():
    """Create basic auth header for API calls"""
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    return f"Basic {encoded_auth}"

# APPROACH 1: DIRECT CURL CALLS
def direct_curl_approach(companies: List[Dict], tracker: APICallTracker):
    """Test using direct CURL calls"""
    
    tracker.start_tracking()
    results = []
    
    for company in companies:
        company_id = company['id']
        company_name = company['name']
        
        log(f"📊 Direct CURL: Analyzing {company_name} (ID: {company_id})")
        
        # Call 1: Get Events
        events_script = f'''
        function main() {{
            return Events({{
                from_date: "2024-12-01",
                to_date: "2025-01-15"
            }})
            .filter(function(event) {{
                return (
                    event.properties["company_id"] === "{company_id}" ||
                    event.properties["idEmpresa"] === "{company_id}"
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
        
        start_time = time.time()
        events_result = make_direct_curl_call(events_script)
        end_time = time.time()
        
        tracker.record_call("events", company_id, events_result is not None, end_time - start_time)
        
        time.sleep(2)  # Brief pause between calls
        
        # Call 2: Get Users  
        users_script = f'''
        function main() {{
            return Events({{
                from_date: "2024-12-01", 
                to_date: "2025-01-15"
            }})
            .filter(function(event) {{
                return (
                    event.properties["company_id"] === "{company_id}" ||
                    event.properties["idEmpresa"] === "{company_id}"
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
        
        start_time = time.time()
        users_result = make_direct_curl_call(users_script)
        end_time = time.time()
        
        tracker.record_call("users", company_id, users_result is not None, end_time - start_time)
        
        results.append({
            "company_id": company_id,
            "company_name": company_name,
            "events_success": events_result is not None,
            "users_success": users_result is not None,
            "events_count": len(events_result) if events_result else 0,
            "users_count": len(users_result) if users_result else 0
        })
        
        time.sleep(3)  # Pause between companies
    
    return tracker.end_tracking(), results

def make_direct_curl_call(script: str):
    """Make a direct CURL call to Mixpanel JQL API"""
    
    payload = {
        "script": script,
        "project_id": MIXPANEL_PROJECT_ID
    }
    
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(payload, f)
        payload_file = f.name
    
    try:
        curl_cmd = [
            "curl", "-X", "POST", BASE_URL,
            "-H", f"Authorization: {create_auth_header()}",
            "-H", "Content-Type: application/json",
            "--data", f"@{payload_file}",
            "--silent", "--show-error",
            "-w", "HTTP_CODE:%{http_code}",
            "--max-time", "60"
        ]
        
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=65)
        os.unlink(payload_file)
        
        if result.returncode == 0:
            output = result.stdout
            if "HTTP_CODE:" in output:
                parts = output.rsplit("HTTP_CODE:", 1)
                response_data = parts[0].strip()
                http_code = parts[1].strip()
                
                if http_code == "200":
                    try:
                        return json.loads(response_data)
                    except json.JSONDecodeError:
                        return None
                        
        return None
        
    except Exception as e:
        log(f"❌ CURL Exception: {e}")
        return None

# APPROACH 2: MCP TOOLS
def mcp_approach(companies: List[Dict], tracker: APICallTracker):
    """Test using MCP tools via OpenAI API"""
    
    if not OPENAI_API_KEY:
        log("❌ No OpenAI API key - skipping MCP approach")
        return None, []
        
    tracker.start_tracking()
    results = []
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    for company in companies:
        company_id = company['id']
        company_name = company['name']
        
        log(f"🤖 MCP Tools: Analyzing {company_name} (ID: {company_id})")
        
        # MCP Call 1: Custom JQL for events
        start_time = time.time()
        events_success = make_mcp_jql_call(client, tracker, company_id, "events")
        end_time = time.time()
        
        time.sleep(3)  # Pause between calls
        
        # MCP Call 2: Custom JQL for users
        start_time = time.time()  
        users_success = make_mcp_jql_call(client, tracker, company_id, "users")
        end_time = time.time()
        
        results.append({
            "company_id": company_id,
            "company_name": company_name,
            "events_success": events_success,
            "users_success": users_success
        })
        
        time.sleep(3)  # Pause between companies
    
    return tracker.end_tracking(), results

def make_mcp_jql_call(client, tracker: APICallTracker, company_id: str, call_type: str):
    """Make an MCP JQL call and track it"""
    
    if call_type == "events":
        script = f'''
        function main() {{
            return Events({{
                from_date: "2024-12-01",
                to_date: "2025-01-15"
            }})
            .filter(function(event) {{
                return (
                    event.properties["company_id"] === "{company_id}" ||
                    event.properties["idEmpresa"] === "{company_id}"
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
    else:  # users
        script = f'''
        function main() {{
            return Events({{
                from_date: "2024-12-01", 
                to_date: "2025-01-15"
            }})
            .filter(function(event) {{
                return (
                    event.properties["company_id"] === "{company_id}" ||
                    event.properties["idEmpresa"] === "{company_id}"
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
    
    try:
        start_time = time.time()
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user", 
                    "content": f"Use MCP custom JQL to run this Mixpanel query: {script}"
                }
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_mixpanel_custom_jql",
                        "description": "Run a custom JQL script against Mixpanel data",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "script": {"type": "string"},
                                "project_id": {"type": "string"}
                            },
                            "required": ["script"]
                        }
                    }
                }
            ],
            tool_choice="auto"
        )
        
        end_time = time.time()
        tracker.record_call(call_type, company_id, True, end_time - start_time)
        
        return True
        
    except Exception as e:
        end_time = time.time()
        tracker.record_call(call_type, company_id, False, end_time - start_time)
        log(f"❌ MCP Error for {call_type}: {e}")
        return False

def save_direct_results(direct_stats: Dict, direct_results: List):
    """Save direct API results"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    analysis = {
        "analysis_timestamp": datetime.now().isoformat(),
        "test_companies": TEST_COMPANIES,
        "direct_curl_stats": direct_stats,
        "direct_results": direct_results,
        "summary": {
            "total_companies": len(TEST_COMPANIES),
            "calls_per_company": direct_stats["total_calls"] / len(TEST_COMPANIES),
            "successful_companies": len([r for r in direct_results if r['events_success'] and r['users_success']]),
            "success_rate": (len([r for r in direct_results if r['events_success'] and r['users_success']]) / len(TEST_COMPANIES)) * 100,
            "average_time_per_company": direct_stats["total_duration"] / len(TEST_COMPANIES)
        }
    }
    
    # Save results
    output_dir = "../../outputs/mixpanel"
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = f"{output_dir}/direct_api_analysis_20_companies_{timestamp}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    log(f"💾 Analysis saved: {output_file}")
    return output_file

def save_comparison_results(direct_stats: Dict, mcp_stats: Dict, direct_results: List, mcp_results: List):
    """Save detailed comparison results"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    comparison = {
        "comparison_timestamp": datetime.now().isoformat(),
        "test_companies": TEST_COMPANIES,
        "direct_curl_stats": direct_stats,
        "mcp_stats": mcp_stats,
        "direct_results": direct_results,
        "mcp_results": mcp_results,
        "efficiency_analysis": {
            "direct_calls_per_company": direct_stats["total_calls"] / len(TEST_COMPANIES) if direct_stats else 0,
            "mcp_calls_per_company": mcp_stats["total_calls"] / len(TEST_COMPANIES) if mcp_stats else 0,
            "api_call_difference": (mcp_stats["total_calls"] - direct_stats["total_calls"]) if (mcp_stats and direct_stats) else 0,
            "time_difference": (mcp_stats["total_duration"] - direct_stats["total_duration"]) if (mcp_stats and direct_stats) else 0
        }
    }
    
    # Save results
    output_dir = "../../outputs/mixpanel"
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = f"{output_dir}/api_usage_comparison_{timestamp}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    
    log(f"💾 Comparison saved: {output_file}")
    return output_file

def main():
    """Main function - Direct API approach with 20 companies"""
    
    log("🔍 PRODUCTION ANALYSIS: 20 MOST ACTIVE COMPANIES")
    log("=" * 60)
    log(f"🧪 Testing with {len(TEST_COMPANIES)} companies")
    log(f"📊 Companies: {', '.join([c['name'] + ' (' + c['id'] + ')' for c in TEST_COMPANIES[:5]])}... (+{len(TEST_COMPANIES)-5} more)")
    
    # Direct CURL approach only
    log(f"\n🎯 DIRECT CURL APPROACH")
    log("-" * 40)
    
    direct_tracker = APICallTracker("Direct CURL")
    direct_stats, direct_results = direct_curl_approach(TEST_COMPANIES, direct_tracker)
    
    log(f"\n📊 Direct CURL Results:")
    log(f"   📞 Total API Calls: {direct_stats['total_calls']}")
    log(f"   ⏱️ Total Duration: {direct_stats['total_duration']:.1f}s")
    log(f"   📈 Calls per Company: {direct_stats['total_calls'] / len(TEST_COMPANIES):.1f}")
    log(f"   🚀 Calls per Second: {direct_stats['calls_per_second']:.2f}")
    
    # Analyze success rates
    successful_companies = len([r for r in direct_results if r['events_success'] and r['users_success']])
    success_rate = (successful_companies / len(TEST_COMPANIES)) * 100
    
    log(f"   ✅ Successful Companies: {successful_companies}/{len(TEST_COMPANIES)} ({success_rate:.1f}%)")
    
    # Save detailed results
    output_file = save_direct_results(direct_stats, direct_results)
    
    log(f"\n🎯 ANALYSIS SUMMARY")
    log("=" * 60)
    log(f"✅ Total Companies Analyzed: {len(TEST_COMPANIES)}")
    log(f"📞 Total API Calls Made: {direct_stats['total_calls']}")
    log(f"⏱️ Total Time: {direct_stats['total_duration']:.1f}s")
    log(f"📁 Detailed results: {output_file}")

if __name__ == "__main__":
    main() 