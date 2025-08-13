#!/usr/bin/env python3
"""
🔍 SEARCH MIXPANEL USERS
Search for users by email domain or pattern

Usage: python3 search_users.py
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

def search_users_by_domain():
    """Search for users with gmail or colppy domains"""
    client = setup_openai_client()
    
    print("🔍 Searching for users with gmail or colppy domains...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user", 
                "content": "Search Mixpanel for users with emails containing 'gmail' or 'colppy', limit to 10 users. Show their email, name, and distinct_id."
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
                            "where": {"type": "string"},
                            "output_properties": {"type": "string"}
                        }
                    }
                }
            }],
            tool_choice="auto"
        )
        
        print("\n📊 Results:")
        print(response.choices[0].message.content)
        
    except Exception as e:
        print(f"❌ Error: {e}")

def search_all_users():
    """Get all users to see what's available"""
    client = setup_openai_client()
    
    print("\n🔍 Getting first 10 users to see available data...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user", 
                "content": "Get the first 10 user profiles from Mixpanel, show email, name, and distinct_id"
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
        
        print("\n📊 Available Users:")
        print(response.choices[0].message.content)
        
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Main function"""
    print("🚀 Searching Mixpanel Users")
    print("=" * 50)
    
    # Search by domain
    search_users_by_domain()
    
    # Get all users
    search_all_users()
    
    print("\n✅ Search completed!")

if __name__ == "__main__":
    main() 