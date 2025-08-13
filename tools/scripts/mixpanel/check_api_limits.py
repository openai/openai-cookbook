#!/usr/bin/env python3
"""
📊 CHECK MIXPANEL API LIMITS AND USAGE
Analyzes API limits, rate limits, quotas, and current usage for staging environment

Usage: python3 check_api_limits.py
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

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def make_test_api_calls():
    """Make multiple test API calls to analyze rate limits and headers"""
    
    log("🔍 Testing API limits with multiple calls...")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    endpoints_to_test = [
        {
            "name": "Top Events",
            "url": f"https://mixpanel.com/api/query/events/top?project_id={MIXPANEL_PROJECT_ID_STAGING}&type=general&limit=5",
            "method": "GET"
        },
        {
            "name": "Segmentation",
            "url": f"https://mixpanel.com/api/query/segmentation?project_id={MIXPANEL_PROJECT_ID_STAGING}&event=Login&from_date=2025-06-09&to_date=2025-06-10&unit=day",
            "method": "GET"
        },
        {
            "name": "Event Properties",
            "url": f"https://mixpanel.com/api/query/events/properties/top?project_id={MIXPANEL_PROJECT_ID_STAGING}&event=Login&limit=5",
            "method": "GET"
        }
    ]
    
    api_stats = []
    
    for i, endpoint in enumerate(endpoints_to_test, 1):
        log(f"\n📡 TEST CALL {i}/3: {endpoint['name']}")
        log(f"🔗 URL: {endpoint['url']}")
        
        # Construct CURL command with detailed headers
        curl_cmd = [
            "curl",
            "-X", endpoint['method'],
            endpoint['url'],
            "-H", f"Authorization: {auth_header}",
            "-H", "User-Agent: LimitTester/1.0",
            "-w", """
RESPONSE_CODE:%{http_code}
TIME_TOTAL:%{time_total}
SIZE_DOWNLOAD:%{size_download}
SPEED_DOWNLOAD:%{speed_download}
TIME_NAMELOOKUP:%{time_namelookup}
TIME_CONNECT:%{time_connect}
TIME_APPCONNECT:%{time_appconnect}
TIME_PRETRANSFER:%{time_pretransfer}
TIME_STARTTRANSFER:%{time_starttransfer}""",
            "-D", "-",  # Include response headers
            "--silent",
            "--show-error"
        ]
        
        start_time = time.time()
        
        try:
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
            end_time = time.time()
            
            if result.returncode == 0:
                # Parse response to extract headers and stats
                response_parts = result.stdout.split('\n\n', 1)
                headers_section = response_parts[0] if response_parts else ""
                body_section = response_parts[1] if len(response_parts) > 1 else ""
                
                # Extract rate limit headers
                rate_limit_info = extract_rate_limit_headers(headers_section)
                
                # Extract timing stats
                timing_stats = extract_timing_stats(result.stdout)
                
                stats = {
                    "endpoint": endpoint['name'],
                    "success": True,
                    "response_time": end_time - start_time,
                    "rate_limits": rate_limit_info,
                    "timing": timing_stats,
                    "response_size": len(body_section),
                    "timestamp": datetime.now().isoformat()
                }
                
                log(f"✅ {endpoint['name']}: {stats['response_time']:.2f}s")
                if rate_limit_info:
                    for key, value in rate_limit_info.items():
                        log(f"   📊 {key}: {value}")
                
            else:
                stats = {
                    "endpoint": endpoint['name'],
                    "success": False,
                    "error": result.stderr,
                    "timestamp": datetime.now().isoformat()
                }
                log(f"❌ {endpoint['name']}: Failed - {result.stderr}")
            
            api_stats.append(stats)
            
            # Small delay between requests to avoid hitting rate limits
            time.sleep(1)
            
        except Exception as e:
            log(f"❌ Error testing {endpoint['name']}: {e}")
            api_stats.append({
                "endpoint": endpoint['name'],
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    return api_stats

def extract_rate_limit_headers(headers_text):
    """Extract rate limiting information from response headers"""
    
    rate_limit_info = {}
    
    # Common rate limit header patterns
    header_patterns = {
        "X-RateLimit-Limit": "limit_total",
        "X-RateLimit-Remaining": "limit_remaining", 
        "X-RateLimit-Reset": "limit_reset",
        "X-Rate-Limit": "rate_limit",
        "Retry-After": "retry_after",
        "X-Quota-Limit": "quota_limit",
        "X-Quota-Remaining": "quota_remaining"
    }
    
    for line in headers_text.split('\n'):
        line = line.strip()
        if ':' in line:
            header, value = line.split(':', 1)
            header = header.strip()
            value = value.strip()
            
            if header in header_patterns:
                rate_limit_info[header_patterns[header]] = value
            elif 'rate' in header.lower() or 'limit' in header.lower() or 'quota' in header.lower():
                rate_limit_info[header.lower().replace('-', '_')] = value
    
    return rate_limit_info

def extract_timing_stats(curl_output):
    """Extract timing statistics from curl output"""
    
    timing_stats = {}
    
    for line in curl_output.split('\n'):
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            if key.startswith('TIME_') or key in ['RESPONSE_CODE', 'SIZE_DOWNLOAD', 'SPEED_DOWNLOAD']:
                try:
                    if key == 'RESPONSE_CODE':
                        timing_stats[key.lower()] = int(value)
                    else:
                        timing_stats[key.lower()] = float(value)
                except:
                    timing_stats[key.lower()] = value
    
    return timing_stats

def check_project_info():
    """Get project information and limits"""
    
    log("🔍 Getting project information...")
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Try to get project info (this might not be available via API)
    endpoint = f"https://mixpanel.com/api/app/projects/{MIXPANEL_PROJECT_ID_STAGING}"
    
    curl_cmd = [
        "curl",
        "-X", "GET",
        endpoint,
        "-H", f"Authorization: {auth_header}",
        "-H", "User-Agent: ProjectInfoGetter/1.0",
        "-w", "\\nHTTP_CODE:%{http_code}\\n",
        "-D", "-",  # Include headers
        "--silent",
        "--show-error"
    ]
    
    try:
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=15)
        
        if result.returncode == 0:
            log(f"📊 Project endpoint response code: {result.stdout.split('HTTP_CODE:')[-1].strip()}")
            
            # Check if we get meaningful response
            if "HTTP_CODE:200" in result.stdout:
                response_body = result.stdout.split('\n\n', 1)
                if len(response_body) > 1:
                    try:
                        project_data = json.loads(response_body[1])
                        log("✅ Got project information")
                        return project_data
                    except:
                        log("❌ Project response not JSON")
            else:
                log("❌ Project endpoint not accessible or requires different auth")
        
    except Exception as e:
        log(f"❌ Error getting project info: {e}")
    
    return None

def estimate_usage_patterns(api_stats):
    """Estimate usage patterns from our test calls"""
    
    log("\n📈 ESTIMATING USAGE PATTERNS:")
    log("=" * 50)
    
    successful_calls = [stat for stat in api_stats if stat.get('success', False)]
    
    if successful_calls:
        avg_response_time = sum(stat['response_time'] for stat in successful_calls) / len(successful_calls)
        total_data_transferred = sum(stat.get('response_size', 0) for stat in successful_calls)
        
        log(f"✅ Successful API calls: {len(successful_calls)}/{len(api_stats)}")
        log(f"⏱️  Average response time: {avg_response_time:.2f} seconds")
        log(f"📦 Total data transferred: {total_data_transferred:,} bytes ({total_data_transferred/1024:.1f} KB)")
        
        # Estimate theoretical limits
        if avg_response_time > 0:
            theoretical_max_calls_per_minute = 60 / avg_response_time
            log(f"🚀 Theoretical max calls/minute: {theoretical_max_calls_per_minute:.0f}")
            log(f"🚀 Theoretical max calls/hour: {theoretical_max_calls_per_minute * 60:.0f}")
    
    # Check for any rate limit indicators
    rate_limit_found = False
    for stat in successful_calls:
        if stat.get('rate_limits'):
            rate_limit_found = True
            log(f"\n📊 Rate limits found for {stat['endpoint']}:")
            for key, value in stat['rate_limits'].items():
                log(f"   {key}: {value}")
    
    if not rate_limit_found:
        log("\n⚠️  No explicit rate limit headers found")
        log("   This suggests either:")
        log("   • No rate limits are enforced")
        log("   • Rate limits are not exposed in headers")
        log("   • We're well below the limits")

def perform_stress_test():
    """Perform a small stress test to find actual limits"""
    
    log("\n🔥 PERFORMING LIGHT STRESS TEST:")
    log("=" * 50)
    
    # Create basic auth
    auth_string = f"{MIXPANEL_USERNAME}:{MIXPANEL_PASSWORD}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    auth_header = f"Basic {encoded_auth}"
    
    # Simple endpoint for rapid testing
    endpoint = f"https://mixpanel.com/api/query/events/top?project_id={MIXPANEL_PROJECT_ID_STAGING}&type=general&limit=1"
    
    log("🚀 Making 10 rapid API calls to detect rate limits...")
    
    results = []
    for i in range(10):
        start_time = time.time()
        
        curl_cmd = [
            "curl",
            "-X", "GET",
            endpoint,
            "-H", f"Authorization: {auth_header}",
            "-w", "%{http_code}",
            "--silent",
            "--output", "/dev/null"
        ]
        
        try:
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=10)
            end_time = time.time()
            
            response_code = result.stdout.strip()
            response_time = end_time - start_time
            
            results.append({
                "call": i + 1,
                "response_code": response_code,
                "response_time": response_time,
                "success": result.returncode == 0
            })
            
            status_emoji = "✅" if response_code == "200" else "❌"
            log(f"   {status_emoji} Call {i+1:2d}: {response_code} ({response_time:.2f}s)")
            
            # Small delay to not hammer the API
            time.sleep(0.1)
            
        except Exception as e:
            log(f"   ❌ Call {i+1:2d}: Error - {e}")
            results.append({
                "call": i + 1,
                "error": str(e),
                "success": False
            })
    
    # Analyze stress test results
    successful_calls = [r for r in results if r.get('response_code') == '200']
    failed_calls = [r for r in results if r.get('response_code') != '200']
    
    log(f"\n📊 Stress test results:")
    log(f"   ✅ Successful: {len(successful_calls)}/10")
    log(f"   ❌ Failed: {len(failed_calls)}/10")
    
    if successful_calls:
        avg_time = sum(r['response_time'] for r in successful_calls) / len(successful_calls)
        log(f"   ⏱️  Average response time: {avg_time:.2f}s")
    
    if failed_calls:
        error_codes = [r.get('response_code', 'N/A') for r in failed_calls]
        log(f"   📄 Error codes: {set(error_codes)}")
    
    return results

def main():
    log("=" * 60)
    log("📊 MIXPANEL API LIMITS & USAGE ANALYSIS")
    log("=" * 60)
    
    # Check credentials
    if not all([MIXPANEL_PROJECT_ID_STAGING, MIXPANEL_USERNAME, MIXPANEL_PASSWORD]):
        log("❌ Missing staging credentials in .env file")
        sys.exit(1)
    
    log(f"📊 Analyzing Project ID: {MIXPANEL_PROJECT_ID_STAGING}")
    log(f"🔑 Username: {MIXPANEL_USERNAME}")
    
    # 1. Check project information
    log("\n🎯 STEP 1: Project Information")
    project_info = check_project_info()
    
    # 2. Test API calls and analyze limits
    log("\n🎯 STEP 2: API Limits Testing")
    api_stats = make_test_api_calls()
    
    # 3. Estimate usage patterns
    estimate_usage_patterns(api_stats)
    
    # 4. Perform stress test
    stress_results = perform_stress_test()
    
    # 5. Summary
    log("\n" + "=" * 60)
    log("📋 SUMMARY & RECOMMENDATIONS")
    log("=" * 60)
    
    successful_normal_calls = len([s for s in api_stats if s.get('success', False)])
    successful_stress_calls = len([r for r in stress_results if r.get('response_code') == '200'])
    
    log(f"✅ Normal API calls successful: {successful_normal_calls}/{len(api_stats)}")
    log(f"✅ Stress test calls successful: {successful_stress_calls}/10")
    
    if successful_normal_calls == len(api_stats) and successful_stress_calls == 10:
        log("🚀 EXCELLENT: No rate limits detected in testing")
        log("   • API appears to have generous limits")
        log("   • Safe to make regular requests")
        log("   • Consider monitoring for production usage")
    elif successful_stress_calls < 10:
        log("⚠️  CAUTION: Some calls failed during stress test")
        log("   • May have hit rate limits or temporary issues")
        log("   • Recommend adding delays between requests")
    
    log("\n💡 Recommendations:")
    log("   • Add 1-2 second delays between API calls")
    log("   • Monitor response headers for rate limit info")
    log("   • Implement exponential backoff for failed requests")
    log("   • Cache frequently requested data")
    
    log("\n" + "=" * 60)

if __name__ == "__main__":
    main() 