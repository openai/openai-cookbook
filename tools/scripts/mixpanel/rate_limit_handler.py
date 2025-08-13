#!/usr/bin/env python3
"""
🔄 MIXPANEL RATE LIMIT HANDLER
Handles Mixpanel API rate limits with intelligent retry logic

Usage: python3 rate_limit_handler.py --email jonetto@colppy.com
"""

import sys
import json
import time
import argparse
from datetime import datetime, timedelta
import openai
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o"

# Rate limiting settings
MAX_RETRIES = 5
INITIAL_DELAY = 60  # Start with 60 seconds
MAX_DELAY = 3600    # Maximum 1 hour delay
BACKOFF_MULTIPLIER = 2

def setup_openai_client():
    """Setup the OpenAI client with API key"""
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY environment variable not set.")
        sys.exit(1)
    
    return openai.OpenAI(api_key=OPENAI_API_KEY)

def execute_with_retry(client, tool_name, tool_params, max_retries=MAX_RETRIES):
    """Execute MCP call with intelligent retry logic"""
    delay = INITIAL_DELAY
    
    for attempt in range(max_retries):
        try:
            print(f"🔄 Attempt {attempt + 1}/{max_retries}")
            
            # Create the tool call
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that can execute MCP commands."},
                    {"role": "user", "content": f"Execute this MCP command: {tool_name}({tool_params})"}
                ],
                tools=[{
                    "type": "function", 
                    "function": {
                        "name": tool_name,
                        "description": "Execute Mixpanel query",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "where": {"type": "string"},
                                "distinct_id": {"type": "string"},
                                "distinct_ids": {"type": "string"},
                                "from_date": {"type": "string"},
                                "to_date": {"type": "string"},
                                "limit": {"type": "number"}
                            }
                        }
                    }
                }],
                tool_choice={"type": "function", "function": {"name": tool_name}}
            )
            
            # Parse response
            function_call = response.choices[0].message.tool_calls[0] if response.choices[0].message.tool_calls else None
            
            if function_call:
                result = json.loads(function_call.function.arguments)
                print("✅ Query successful!")
                return {"status": "success", "data": result}
            else:
                return {"status": "error", "message": "No function call returned"}
                
        except Exception as e:
            error_str = str(e)
            
            # Check if it's a rate limit error
            if "rate limit" in error_str.lower() or "429" in error_str:
                if attempt < max_retries - 1:
                    print(f"⚠️ Rate limit hit. Waiting {delay} seconds before retry...")
                    print(f"   Next attempt in: {datetime.now() + timedelta(seconds=delay)}")
                    time.sleep(delay)
                    delay = min(delay * BACKOFF_MULTIPLIER, MAX_DELAY)
                    continue
                else:
                    print(f"❌ Max retries exceeded. Rate limit still active.")
                    return {"status": "error", "message": "Rate limit exceeded after max retries"}
            else:
                print(f"❌ Non-rate limit error: {e}")
                return {"status": "error", "message": str(e)}
    
    return {"status": "error", "message": "Max retries exceeded"}

def get_user_profile_with_retry(email, client):
    """Get user profile with retry logic"""
    print(f"🔍 Looking up profile for: {email}")
    
    tool_params = f'where=\'properties["$email"] == "{email}"\''
    result = execute_with_retry(client, "mcp_mixpanel_query_profiles", tool_params)
    
    if result["status"] == "success":
        profiles = result["data"].get("profiles", [])
        if profiles:
            name = profiles[0].get("properties", {}).get("$name", "N/A")
            distinct_id = profiles[0].get("distinct_id", "N/A")
            print(f"📊 Found user: {name} (ID: {distinct_id})")
            return profiles[0]
        else:
            print("❌ No profile found")
            return None
    else:
        print(f"❌ Failed: {result['message']}")
        return None

def get_user_events_with_retry(distinct_ids, from_date, to_date, client):
    """Get user events with retry logic"""
    print(f"🔍 Getting events for user from {from_date} to {to_date}")
    
    tool_params = f'distinct_ids="{distinct_ids}", from_date="{from_date}", to_date="{to_date}"'
    result = execute_with_retry(client, "mcp_mixpanel_profile_event_activity", tool_params)
    
    if result["status"] == "success":
        events = result["data"].get("events", [])
        print(f"📊 Found {len(events)} events")
        return events
    else:
        print(f"❌ Failed: {result['message']}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Get Mixpanel data with rate limit handling')
    parser.add_argument('--email', required=True, help='User email to lookup')
    parser.add_argument('--days', type=int, default=30, help='Number of days back to get events')
    parser.add_argument('--max-retries', type=int, default=MAX_RETRIES, help='Maximum retry attempts')
    
    args = parser.parse_args()
    
    # Setup dates
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    
    # Setup client
    client = setup_openai_client()
    
    print("🚀 Starting Mixpanel query with rate limit handling")
    print(f"📅 Date range: {start_date} to {end_date}")
    print("=" * 60)
    
    # Step 1: Get user profile
    profile = get_user_profile_with_retry(args.email, client)
    
    if profile:
        distinct_id = profile.get("distinct_id")
        
        # Step 2: Get user events  
        if distinct_id:
            events = get_user_events_with_retry(f'["{distinct_id}"]', start_date, end_date, client)
            
            if events:
                # Analyze top events
                event_counts = {}
                for event in events:
                    event_name = event.get("event", "unknown")
                    event_counts[event_name] = event_counts.get(event_name, 0) + 1
                
                print("\n🏆 TOP EVENTS:")
                for event, count in sorted(event_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"   {event}: {count} times")
    
    print("\n✅ Query completed!")

if __name__ == "__main__":
    main() 