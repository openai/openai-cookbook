#!/usr/bin/env python3
"""
Simple Mixpanel Production API Test
Tests a few basic API calls and stops immediately if rate limits are encountered.
"""

import os
import sys
import json
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, project_root)

from mcp import create_session, StdioServerParameters

def test_mixpanel_api():
    """Test a few basic Mixpanel API calls and check for rate limits."""
    
    print("🧪 Testing Mixpanel Production API...")
    print("=" * 50)
    
    try:
        # Create MCP session with Mixpanel server
        with create_session(StdioServerParameters(command="npx", args=["-y", "@mixpanel/mcp-server"])) as session:
            
            # Test 1: Get today's top events
            print("\n📊 Test 1: Getting today's top events...")
            try:
                result = session.call_tool(
                    "mcp_mixpanel_get_today_top_events",
                    {"limit": 10, "type": "general"}
                )
                
                if result and hasattr(result, 'content'):
                    content = result.content[0].text if result.content else "No content"
                    
                    # Check for rate limit errors
                    if "rate limit" in content.lower() or "limit exceeded" in content.lower():
                        print("❌ RATE LIMIT HIT! Stopping immediately.")
                        print(f"Response: {content}")
                        return False
                    
                    print("✅ Success - Today's top events retrieved")
                    print(f"Response size: {len(content)} characters")
                    
                    # Try to parse and show summary
                    try:
                        data = json.loads(content)
                        if isinstance(data, dict) and 'data' in data:
                            events = data['data']
                            print(f"Found {len(events)} events")
                            if events:
                                print(f"Top event: {list(events.keys())[0] if events else 'None'}")
                    except:
                        print("Response format: text/non-JSON")
                        
                else:
                    print("❌ No response received")
                    return False
                    
            except Exception as e:
                error_msg = str(e)
                if "rate limit" in error_msg.lower() or "limit exceeded" in error_msg.lower():
                    print(f"❌ RATE LIMIT HIT! Stopping immediately.")
                    print(f"Error: {error_msg}")
                    return False
                print(f"❌ Error in test 1: {error_msg}")
                return False
            
            # Test 2: Get top events (last 31 days)
            print("\n📈 Test 2: Getting top events (last 31 days)...")
            try:
                result = session.call_tool(
                    "mcp_mixpanel_get_top_events",
                    {"limit": 5, "type": "general"}
                )
                
                if result and hasattr(result, 'content'):
                    content = result.content[0].text if result.content else "No content"
                    
                    # Check for rate limit errors
                    if "rate limit" in content.lower() or "limit exceeded" in content.lower():
                        print("❌ RATE LIMIT HIT! Stopping immediately.")
                        print(f"Response: {content}")
                        return False
                    
                    print("✅ Success - Top events (31 days) retrieved")
                    print(f"Response size: {len(content)} characters")
                    
                    # Try to parse and show summary
                    try:
                        data = json.loads(content)
                        if isinstance(data, dict) and 'data' in data:
                            events = data['data']
                            print(f"Found {len(events)} events")
                    except:
                        print("Response format: text/non-JSON")
                        
                else:
                    print("❌ No response received")
                    return False
                    
            except Exception as e:
                error_msg = str(e)
                if "rate limit" in error_msg.lower() or "limit exceeded" in error_msg.lower():
                    print(f"❌ RATE LIMIT HIT! Stopping immediately.")
                    print(f"Error: {error_msg}")
                    return False
                print(f"❌ Error in test 2: {error_msg}")
                return False
            
            # Test 3: Simple profile query (if we made it this far)
            print("\n👤 Test 3: Testing profile query...")
            try:
                result = session.call_tool(
                    "mcp_mixpanel_query_profiles",
                    {
                        "where": 'properties["$email"] == "test@example.com"',
                        "output_properties": '["$email", "$name"]'
                    }
                )
                
                if result and hasattr(result, 'content'):
                    content = result.content[0].text if result.content else "No content"
                    
                    # Check for rate limit errors
                    if "rate limit" in content.lower() or "limit exceeded" in content.lower():
                        print("❌ RATE LIMIT HIT! Stopping immediately.")
                        print(f"Response: {content}")
                        return False
                    
                    print("✅ Success - Profile query completed")
                    print(f"Response size: {len(content)} characters")
                    
                else:
                    print("❌ No response received")
                    return False
                    
            except Exception as e:
                error_msg = str(e)
                if "rate limit" in error_msg.lower() or "limit exceeded" in error_msg.lower():
                    print(f"❌ RATE LIMIT HIT! Stopping immediately.")
                    print(f"Error: {error_msg}")
                    return False
                print(f"❌ Error in test 3: {error_msg}")
                return False
            
            print("\n🎉 All tests completed successfully!")
            print("✅ Production API is responding normally")
            print("✅ No rate limits encountered")
            return True
            
    except Exception as e:
        error_msg = str(e)
        if "rate limit" in error_msg.lower() or "limit exceeded" in error_msg.lower():
            print(f"❌ RATE LIMIT HIT! Stopping immediately.")
            print(f"Error: {error_msg}")
            return False
        print(f"❌ Session error: {error_msg}")
        return False

def main():
    """Main function."""
    print(f"🕐 Starting API test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    success = test_mixpanel_api()
    
    print(f"\n🕐 Test completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if success:
        print("🎯 Result: API is working normally")
        sys.exit(0)
    else:
        print("⚠️  Result: Rate limits hit or API issues encountered")
        sys.exit(1)

if __name__ == "__main__":
    main() 