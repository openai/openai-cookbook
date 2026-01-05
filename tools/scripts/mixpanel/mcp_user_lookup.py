#!/usr/bin/env python3
"""
🎯 MCP USER LOOKUP - Command Line with MCP Tools
Executes MCP calls through the chat environment

Usage: python3 mcp_user_lookup.py jonetto@colppy.com
"""

import sys
import json
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 mcp_user_lookup.py <user_email>")
        print("Example: python3 mcp_user_lookup.py jonetto@colppy.com")
        sys.exit(1)
    
    user_email = sys.argv[1]
    
    print(f"🔍 Looking up user profile for: {user_email}")
    print("=" * 50)
    print("📋 Executing MCP call...")
    
    # This creates a command that can be executed in the MCP environment
    mcp_command = f'mcp_mixpanel_query_profiles(where=\'properties["$email"] == "{user_email}"\')'
    
    print("🔧 Copy and run this command in your MCP chat environment:")
    print("=" * 60)
    print(mcp_command)
    print("=" * 60)
    
    # Also try alternative methods
    print("\n🔄 Alternative commands to try:")
    print(f'mcp_mixpanel_query_profiles(distinct_id="{user_email}")')
    print('mcp_mixpanel_query_profiles(limit=10)  # Get sample profiles')
    
    print(f"\n💾 Save results to: tools/outputs/user_profile_{user_email.replace('@', '_at_').replace('.', '_')}.json")

if __name__ == "__main__":
    main() 