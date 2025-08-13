#!/usr/bin/env python3
"""
🎯 DIRECT USER LOOKUP FOR MIXPANEL
Simple function to be called where MCP tools are available

Usage:
1. Import this in your MCP environment
2. Call: lookup_user_profile("jonetto@colppy.com")
"""

import json
import os
from datetime import datetime

def _call_mcp_tool(user_email: str):
    """Try to call MCP tool - will work in MCP environment"""
    try:
        # This will work when globals() contains the MCP function
        if 'mcp_mixpanel_query_profiles' in globals():
            return mcp_mixpanel_query_profiles(
                where=f'properties["$email"] == "{user_email}"'
            )
        else:
            return None
    except Exception as e:
        print(f"❌ MCP call failed: {e}")
        return None

def lookup_user_profile(user_email: str):
    """
    Direct lookup function to be called in MCP environment
    """
    
    print(f"🔍 Looking up user profile for: {user_email}")
    print("=" * 50)
    
    # Try MCP tool call
    print("🔄 Attempting MCP tool call...")
    user_profile = _call_mcp_tool(user_email)
    
    if user_profile is None:
        print("❌ MCP tools not available in this environment")
        print("💡 Copy and paste this into your MCP chat environment:")
        print(f'mcp_mixpanel_query_profiles(where=\'properties["$email"] == "{user_email}"\')')
        return None
    
    try:
        
        # Process and display results
        if user_profile and "results" in user_profile:
            results = user_profile["results"]
            
            if results:
                print(f"✅ Found user profile!")
                print(f"📊 Total results: {len(results)}")
                
                for i, profile in enumerate(results):
                    print(f"\n--- Profile {i+1} ---")
                    
                    distinct_id = profile.get("$distinct_id", "N/A")
                    properties = profile.get("$properties", {})
                    
                    print(f"Distinct ID: {distinct_id}")
                    print("\n📋 All Properties:")
                    
                    # Sort properties for better readability
                    sorted_props = sorted(properties.items())
                    
                    for prop_name, prop_value in sorted_props:
                        # Format the display
                        if isinstance(prop_value, str) and len(prop_value) > 100:
                            prop_value = prop_value[:100] + "..."
                        
                        print(f"  {prop_name}: {prop_value}")
                    
                    print(f"\n📈 Total properties: {len(properties)}")
                
                # Save to file for reference
                output_dir = "tools/outputs"
                if not os.path.exists(output_dir):
                    output_dir = "outputs"
                    if not os.path.exists(output_dir):
                        output_dir = "."
                
                output_file = f"{output_dir}/user_profile_{user_email.replace('@', '_at_').replace('.', '_')}.json"
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                
                with open(output_file, 'w') as f:
                    json.dump(user_profile, f, indent=2, default=str)
                
                print(f"\n💾 Profile saved to: {output_file}")
                
                return user_profile
                
            else:
                print("❌ No user found with that email address")
                print("💡 Possible reasons:")
                print("  - Email not in Mixpanel as distinct_id")
                print("  - Email stored in different property")
                print("  - User might use different identifier")
                
                # Try alternative lookup methods
                print("\n🔍 Trying alternative lookup methods...")
                return try_alternative_lookups(user_email)
                
        else:
            print("❌ No results returned from Mixpanel")
            print(f"Raw response: {user_profile}")
            return None
            
    except NameError:
        print("❌ mcp_mixpanel_query_profiles not available in this environment")
        print("This function must be called where MCP tools are loaded")
        return None
    except Exception as e:
        print(f"❌ Error calling MCP tool: {e}")
        return None

def try_alternative_lookups(user_email: str):
    """Try alternative ways to find the user"""
    
    print("🔄 Trying direct distinct_id lookup...")
    try:
        user_profile = mcp_mixpanel_query_profiles(
            distinct_id=user_email
        )
        
        if user_profile and user_profile.get("results"):
            print("✅ Found via distinct_id lookup!")
            return user_profile
    except:
        pass
    
    print("🔄 Trying general profile search...")
    try:
        # Get a sample of profiles to see available email fields
        sample_profiles = mcp_mixpanel_query_profiles(limit=10)
        
        if sample_profiles and sample_profiles.get("results"):
            print("📋 Sample profiles found - checking email field formats...")
            for profile in sample_profiles["results"][:3]:
                properties = profile.get("$properties", {})
                email_fields = [k for k in properties.keys() if "email" in k.lower()]
                if email_fields:
                    print(f"  Found email fields: {email_fields}")
            
        return sample_profiles
        
    except Exception as e:
        print(f"❌ Alternative lookup failed: {e}")
        return None

def main():
    """Main function for command line usage"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python direct_user_lookup.py <user_email>")
        print("Example: python direct_user_lookup.py jonetto@colppy.com")
        print("\nOr import and call: lookup_user_profile('jonetto@colppy.com')")
        sys.exit(1)
    
    user_email = sys.argv[1]
    result = lookup_user_profile(user_email)
    
    if result:
        print("\n✅ Lookup completed successfully")
    else:
        print("\n❌ Lookup failed")

if __name__ == "__main__":
    main() 