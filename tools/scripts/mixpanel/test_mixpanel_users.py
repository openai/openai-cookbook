#!/usr/bin/env python3
"""
🔍 MIXPANEL USER TEST
Test script to explore available users and data structure

Usage: python3 test_mixpanel_users.py
"""

import sys
import json
import os
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o"

def setup_openai_client():
    """Setup the OpenAI client with API key"""
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY environment variable not set.")
        sys.exit(1)
    
    return openai.OpenAI(api_key=OPENAI_API_KEY)

def test_sample_users():
    """Get a sample of users to understand data structure"""
    client = setup_openai_client()
    
    print("🔍 Getting sample of users...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user", 
                "content": "Get a sample of 3 user profiles from Mixpanel to see the data structure"
            }],
            tools=[{
                "type": "function",
                "function": {
                    "name": "mcp_mixpanel_query_profiles",
                    "description": "Query Mixpanel user profiles",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "number"},
                            "output_properties": {"type": "string"}
                        }
                    }
                }
            }],
            tool_choice="auto"
        )
        
        if response.choices[0].message.tool_calls:
            tool_call = response.choices[0].message.tool_calls[0]
            print(f"Tool call: {tool_call.function.name}")
            print(f"Arguments: {tool_call.function.arguments}")
            
            # Execute the tool call
            tool_response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "user", "content": "Get sample users"},
                    response.choices[0].message,
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({"limit": 3, "output_properties": '["$email", "$name", "distinct_id"]'})
                    }
                ]
            )
            
            print("\n📊 Results:")
            print(tool_response.choices[0].message.content)
        else:
            print(response.choices[0].message.content)
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_search_by_email_variations():
    """Try different ways to search for the user"""
    client = setup_openai_client()
    
    email_variations = [
        "jonetto@colppy.com",
        "properties[\"$email\"] == \"jonetto@colppy.com\"",
        "properties[\"email\"] == \"jonetto@colppy.com\""
    ]
    
    for variation in email_variations:
        print(f"\n🔍 Trying: {variation}")
        
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{
                    "role": "user", 
                    "content": f"Search for user with: {variation}"
                }],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "mcp_mixpanel_query_profiles",
                        "description": "Query Mixpanel user profiles",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "where": {"type": "string"},
                                "distinct_id": {"type": "string"},
                                "output_properties": {"type": "string"}
                            }
                        }
                    }
                }],
                tool_choice="auto"
            )
            
            print(f"✅ Response: {response.choices[0].message.content[:200]}...")
            
        except Exception as e:
            print(f"❌ Error: {e}")

def main():
    """Main function"""
    print("🚀 Testing Mixpanel User Queries")
    print("=" * 50)
    
    # Test 1: Get sample users
    test_sample_users()
    
    # Test 2: Try different search methods
    test_search_by_email_variations()
    
    print("\n✅ Testing completed!")

if __name__ == "__main__":
    main() 