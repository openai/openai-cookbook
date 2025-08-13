#!/usr/bin/env python3
"""
🎯 MIXPANEL USER LOOKUP - Command Line with MCP Tools
Directly executes MCP calls to query Mixpanel user profiles

Usage:
  python3 mcp_user_lookup.py --email jonetto@colppy.com
  python3 mcp_user_lookup.py --distinct-id 12345678
  python3 mcp_user_lookup.py --sample 10
  python3 mcp_user_lookup.py --where 'properties["plan"] == "premium"' --limit 5
"""

import sys
import json
import os
import time
import argparse
from datetime import datetime
import openai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
DEFAULT_OUTPUT_DIR = "../../outputs/csv_data/mixpanel/user_properties"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o"

def setup_openai_client():
    """Setup the OpenAI client with API key"""
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY environment variable not set.")
        print("Create a .env file with your OpenAI API key or set it as an environment variable.")
        sys.exit(1)
    
    # Initialize OpenAI client
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    return client

def execute_mcp_query(client, query_params):
    """Execute the MCP query using the OpenAI API"""
    query_str = ", ".join([f"{k}={v}" for k, v in query_params.items()])
    mcp_command = f"mcp_mixpanel_query_profiles({query_str})"
    
    print(f"Executing MCP command: {mcp_command}")
    
    try:
        # Create a chat completion that uses the MCP function
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that can execute MCP commands."},
                {"role": "user", "content": f"Please execute the following MCP command and return only the JSON results: {mcp_command}"}
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": "mcp_mixpanel_query_profiles",
                    "description": "Query Mixpanel profiles with filtering options",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "where": {
                                "type": "string",
                                "description": "An expression to filter users"
                            },
                            "distinct_id": {
                                "type": "string",
                                "description": "A unique identifier used to distinguish an individual profile"
                            },
                            "distinct_ids": {
                                "type": "string",
                                "description": "A JSON array of distinct_ids to retrieve profiles for"
                            },
                            "output_properties": {
                                "type": "string",
                                "description": "A JSON array of property names to return"
                            },
                            "limit": {
                                "type": "number",
                                "description": "Limit the number of profiles returned"
                            },
                            "page": {
                                "type": "number",
                                "description": "Page number for paginated results"
                            }
                        }
                    }
                }
            }],
            tool_choice={"type": "function", "function": {"name": "mcp_mixpanel_query_profiles"}}
        )
        
        # Extract the function call and results
        function_call = response.choices[0].message.tool_calls[0] if response.choices[0].message.tool_calls else None
        
        if function_call and function_call.function.name == "mcp_mixpanel_query_profiles":
            # Parse the function arguments (JSON string)
            result = json.loads(function_call.function.arguments)
            return {
                "status": "success",
                "results": result.get("profiles", []),
                "raw_response": result
            }
        else:
            return {
                "status": "error", 
                "message": "Function was not called or returned unexpected format",
                "raw_response": response.model_dump()
            }
    except Exception as e:
        print(f"❌ Error executing MCP query: {e}")
        return {"status": "error", "message": str(e)}

def save_results(results, filename_base):
    """Save results to a JSON file"""
    # Create output directory if it doesn't exist
    output_dir = os.path.abspath(DEFAULT_OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{output_dir}/{filename_base}_{timestamp}.json"
    
    # Save results
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"💾 Results saved to: {filename}")
    return filename

def display_profile_summary(profiles):
    """Display a summary of profile information"""
    print("\n📊 RESULTS SUMMARY:")
    print("=" * 50)
    
    if not profiles:
        print("No profiles found matching your criteria.")
        return
    
    print(f"Found {len(profiles)} profile(s).")
    
    for profile in profiles:
        props = profile.get('properties', {})
        print("-" * 50)
        print(f"Distinct ID: {profile.get('distinct_id', 'N/A')}")
        
        # Display common properties if they exist
        for prop in ['$email', '$name', '$last_seen', 'plan', 'company', 'last_login']:
            if prop in props:
                prop_display = prop.replace('$', '')
                print(f"{prop_display.capitalize()}: {props.get(prop, 'N/A')}")
        
        # Show total property count
        total_props = len(props)
        if total_props > 5:
            print(f"... and {total_props - 5} more properties")

def query_by_email(email, client):
    """Look up a user profile by email"""
    print(f"🔍 Looking up user profile by email: {email}")
    print("=" * 50)
    
    # Build query for looking up by email
    query_params = {
        "where": f'properties["$email"] == "{email}"',
        "output_properties": '["$email", "$name", "$last_seen", "plan", "company", "last_login"]'
    }
    
    # Execute query
    print("📋 Executing MCP call...")
    results = execute_mcp_query(client, query_params)
    
    if results.get("status") == "success":
        # Save results
        filename = save_results(results, f"user_profile_by_email_{email.replace('@', '_at_').replace('.', '_')}")
        
        # Display summary
        display_profile_summary(results.get("results", []))
        return results
    else:
        print(f"❌ Query failed: {results.get('message', 'Unknown error')}")
        return None

def query_by_distinct_id(distinct_id, client):
    """Look up a user profile by distinct ID"""
    print(f"🔍 Looking up user profile by distinct ID: {distinct_id}")
    print("=" * 50)
    
    # Build query
    query_params = {
        "distinct_id": f'"{distinct_id}"',
        "output_properties": '["$email", "$name", "$last_seen", "plan", "company", "last_login"]'
    }
    
    # Execute query
    print("📋 Executing MCP call...")
    results = execute_mcp_query(client, query_params)
    
    if results.get("status") == "success":
        # Save results
        filename = save_results(results, f"user_profile_by_id_{distinct_id}")
        
        # Display summary
        display_profile_summary(results.get("results", []))
        return results
    else:
        print(f"❌ Query failed: {results.get('message', 'Unknown error')}")
        return None

def query_sample_profiles(limit, client):
    """Get a sample of user profiles"""
    print(f"🔍 Fetching sample of {limit} user profiles")
    print("=" * 50)
    
    # Build query
    query_params = {
        "limit": limit,
        "output_properties": '["$email", "$name", "$last_seen", "plan", "company"]'
    }
    
    # Execute query
    print("📋 Executing MCP call...")
    results = execute_mcp_query(client, query_params)
    
    if results.get("status") == "success":
        # Save results
        filename = save_results(results, f"sample_profiles_{limit}")
        
        # Display summary
        display_profile_summary(results.get("results", []))
        return results
    else:
        print(f"❌ Query failed: {results.get('message', 'Unknown error')}")
        return None

def query_by_custom_where(where_clause, limit, client):
    """Query profiles using a custom where clause"""
    print(f"🔍 Querying profiles with custom filter: {where_clause}")
    print("=" * 50)
    
    # Build query
    query_params = {
        "where": f'{where_clause}',
        "limit": limit,
        "output_properties": '["$email", "$name", "$last_seen", "plan", "company"]'
    }
    
    # Execute query
    print("📋 Executing MCP call...")
    results = execute_mcp_query(client, query_params)
    
    if results.get("status") == "success":
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = save_results(results, f"custom_query_{timestamp}")
        
        # Display summary
        display_profile_summary(results.get("results", []))
        return results
    else:
        print(f"❌ Query failed: {results.get('message', 'Unknown error')}")
        return None

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Query Mixpanel user profiles via MCP')
    
    # Define mutually exclusive group for query type
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument('--email', type=str, help='Look up profile by email')
    query_group.add_argument('--distinct-id', type=str, help='Look up profile by distinct ID')
    query_group.add_argument('--sample', type=int, help='Get a sample of profiles')
    query_group.add_argument('--where', type=str, help='Custom where clause for filtering profiles')
    
    # Additional options
    parser.add_argument('--limit', type=int, default=10, help='Limit number of results (default: 10)')
    parser.add_argument('--output-dir', type=str, help='Custom output directory for results')
    parser.add_argument('--model', type=str, help='OpenAI model to use (default: gpt-4o)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Update global variables if needed
    global DEFAULT_OUTPUT_DIR, MODEL
    if args.output_dir:
        DEFAULT_OUTPUT_DIR = args.output_dir
    if args.model:
        MODEL = args.model
    
    return args

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    # Setup OpenAI client
    client = setup_openai_client()
    
    # Execute the appropriate query based on args
    if args.email:
        query_by_email(args.email, client)
    elif args.distinct_id:
        query_by_distinct_id(args.distinct_id, client)
    elif args.sample:
        query_sample_profiles(args.sample, client)
    elif args.where:
        query_by_custom_where(args.where, args.limit, client)

    print("\n✅ Query completed!")

if __name__ == "__main__":
    main() 