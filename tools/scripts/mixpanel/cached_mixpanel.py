#!/usr/bin/env python3
"""
💾 CACHED MIXPANEL QUERIES
Reduces API calls by caching results locally

Usage: python3 cached_mixpanel.py --email jonetto@colppy.com
"""

import sys
import json
import os
import time
import argparse
import hashlib
from datetime import datetime, timedelta
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o"
CACHE_DIR = "../../outputs/mixpanel_cache"
DEFAULT_CACHE_HOURS = 1  # Default cache for 1 hour

def setup_cache_dir():
    """Create cache directory if it doesn't exist"""
    os.makedirs(CACHE_DIR, exist_ok=True)

def clear_cache():
    """Clear all cached data"""
    import glob
    cache_files = glob.glob(f"{CACHE_DIR}/*.json")
    for file in cache_files:
        os.remove(file)
    print(f"✅ Cleared {len(cache_files)} cached files")

def get_cache_key(query_type, params):
    """Generate a cache key from query parameters"""
    cache_string = f"{query_type}_{json.dumps(params, sort_keys=True)}"
    return hashlib.md5(cache_string.encode()).hexdigest()

def is_cache_valid(cache_file, cache_duration_hours):
    """Check if cache file is still valid"""
    if not os.path.exists(cache_file):
        return False
    
    file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
    cache_duration = timedelta(hours=cache_duration_hours)
    return datetime.now() - file_time < cache_duration

def save_to_cache(cache_key, data):
    """Save data to cache file"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    with open(cache_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "data": data
        }, f, indent=2)
    print(f"💾 Cached result: {cache_file}")

def load_from_cache(cache_key):
    """Load data from cache file"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    if is_cache_valid(cache_file, DEFAULT_CACHE_HOURS):
        with open(cache_file, 'r') as f:
            cached_data = json.load(f)
            print(f"📋 Using cached result from {cached_data['timestamp']}")
            return cached_data['data']
    
    return None

def setup_openai_client():
    """Setup the OpenAI client with API key"""
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY environment variable not set.")
        sys.exit(1)
    
    return openai.OpenAI(api_key=OPENAI_API_KEY)

def cached_mixpanel_query(query_type, params, client, force_refresh=False):
    """Execute Mixpanel query with caching"""
    setup_cache_dir()
    
    # Generate cache key
    cache_key = get_cache_key(query_type, params)
    
    # Try to load from cache first (unless force refresh)
    if not force_refresh:
        cached_result = load_from_cache(cache_key)
        if cached_result:
            return {"status": "success", "data": cached_result, "from_cache": True}
    
    # Execute actual query
    print(f"🌐 Making API call: {query_type}")
    
    try:
        # Build tool parameters string
        param_str = ", ".join([f'{k}="{v}"' if isinstance(v, str) else f'{k}={v}' for k, v in params.items()])
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that can execute MCP commands."},
                {"role": "user", "content": f"Execute: {query_type}({param_str})"}
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": query_type,
                    "description": "Execute Mixpanel query",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "where": {"type": "string"},
                            "distinct_id": {"type": "string"},
                            "distinct_ids": {"type": "string"},
                            "from_date": {"type": "string"},
                            "to_date": {"type": "string"},
                            "limit": {"type": "number"},
                            "output_properties": {"type": "string"}
                        }
                    }
                }
            }],
            tool_choice={"type": "function", "function": {"name": query_type}}
        )
        
        function_call = response.choices[0].message.tool_calls[0] if response.choices[0].message.tool_calls else None
        
        if function_call:
            result = json.loads(function_call.function.arguments)
            
            # Save to cache
            save_to_cache(cache_key, result)
            
            return {"status": "success", "data": result, "from_cache": False}
        else:
            return {"status": "error", "message": "No function call returned"}
            
    except Exception as e:
        print(f"❌ API Error: {e}")
        return {"status": "error", "message": str(e)}

def get_user_profile_cached(email, client, force_refresh=False):
    """Get user profile with caching"""
    params = {
        "where": f'properties["$email"] == "{email}"',
        "output_properties": '["$email", "$name", "distinct_id", "$last_seen"]'
    }
    
    result = cached_mixpanel_query("mcp_mixpanel_query_profiles", params, client, force_refresh)
    
    if result["status"] == "success":
        profiles = result["data"].get("profiles", [])
        cache_status = "🏆 (cached)" if result.get("from_cache") else "🌐 (fresh)"
        
        if profiles:
            profile = profiles[0]
            name = profile.get("properties", {}).get("$name", "N/A")
            distinct_id = profile.get("distinct_id", "N/A")
            print(f"📊 Found user: {name} (ID: {distinct_id}) {cache_status}")
            return profile
        else:
            print("❌ No profile found")
            return None
    else:
        print(f"❌ Failed: {result['message']}")
        return None

def get_user_events_cached(distinct_ids, from_date, to_date, client, force_refresh=False):
    """Get user events with caching"""
    params = {
        "distinct_ids": distinct_ids,
        "from_date": from_date,
        "to_date": to_date
    }
    
    result = cached_mixpanel_query("mcp_mixpanel_profile_event_activity", params, client, force_refresh)
    
    if result["status"] == "success":
        events = result["data"].get("events", [])
        cache_status = "🏆 (cached)" if result.get("from_cache") else "🌐 (fresh)"
        print(f"📊 Found {len(events)} events {cache_status}")
        return events
    else:
        print(f"❌ Failed: {result['message']}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Query Mixpanel user profiles with intelligent caching")
    parser.add_argument("--email", type=str, help="Email address to search for")
    parser.add_argument("--days", type=int, default=30, help="Number of days to search for events (default: 30)")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh cached data")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached data")
    
    args = parser.parse_args()
    
    # Clear cache if requested
    if args.clear_cache:
        clear_cache()
        return
    
    # Email is required for actual queries
    if not args.email:
        parser.error("--email is required unless using --clear-cache")
    
    setup_cache_dir()
    
    # Setup dates
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    
    # Setup client
    client = setup_openai_client()
    
    print("🚀 Starting cached Mixpanel query")
    print(f"📅 Date range: {start_date} to {end_date}")
    print(f"💾 Cache duration: {DEFAULT_CACHE_HOURS} hour(s)")
    print("=" * 60)
    
    # Get user profile
    profile = get_user_profile_cached(args.email, client, args.force_refresh)
    
    if profile:
        distinct_id = profile.get("distinct_id")
        
        if distinct_id:
            # Get user events
            events = get_user_events_cached(f'["{distinct_id}"]', start_date, end_date, client, args.force_refresh)
            
            if events:
                # Analyze events
                event_counts = {}
                for event in events:
                    event_name = event.get("event", "unknown")
                    event_counts[event_name] = event_counts.get(event_name, 0) + 1
                
                print(f"\n🏆 TOP EVENTS FOR {profile.get('properties', {}).get('$name', 'User')}:")
                for event, count in sorted(event_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"   {event}: {count} times")
    
    print(f"\n💾 Cache location: {os.path.abspath(CACHE_DIR)}")
    print("✅ Query completed!")

if __name__ == "__main__":
    main() 