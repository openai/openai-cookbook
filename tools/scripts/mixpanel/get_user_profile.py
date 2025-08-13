#!/usr/bin/env python3
"""
🎯 GET SPECIFIC USER PROFILE FROM MIXPANEL
Uses MCP Mixpanel tools to fetch a specific user's properties

Usage: python get_user_profile.py jonetto@colppy.com
"""

import os
import sys
import json
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path to enable MCP tool access
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../'))

def process_profile_result(user_profile: dict, user_email: str):
    """Process and display the profile result"""
    
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
            output_file = f"tools/outputs/user_profile_{user_email.replace('@', '_at_').replace('.', '_')}.json"
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            with open(output_file, 'w') as f:
                json.dump(user_profile, f, indent=2, default=str)
            
            print(f"\n💾 Profile saved to: {output_file}")
            
        else:
            print("❌ No user found with that email address")
            print("💡 Possible reasons:")
            print("  - Email not in Mixpanel as distinct_id")
            print("  - Email stored in different property")
            print("  - User might use different identifier")
            
    else:
        print("❌ No results returned from Mixpanel")
        print(f"Raw response: {user_profile}")

def get_user_profile(user_email: str):
    """
    Get user profile using MCP Mixpanel tools
    Uses method 2: Email filter approach
    """
    
    print(f"🔍 Looking up user profile for: {user_email}")
    print("=" * 50)
    
    try:
        # Method 2: Email Filter (More Reliable)
        print("📋 Using email filter approach...")
        print(f"Filter: properties[\"$email\"] == \"{user_email}\"")
        
        # Try to call MCP tools through Python subprocess using the same environment
        python_code = f'''
import os
import sys

# Try to make the MCP call using the available functions in the environment
try:
    # This should work if MCP tools are available in the current environment
    result = mcp_mixpanel_query_profiles(where='properties["$email"] == "{user_email}"')
    print("SUCCESS:", result)
except NameError:
    print("ERROR: MCP tools not available as direct functions")
    try:
        # Alternative: try to import from global context
        from __main__ import mcp_mixpanel_query_profiles
        result = mcp_mixpanel_query_profiles(where='properties["$email"] == "{user_email}"')
        print("SUCCESS:", result)
    except:
        print("ERROR: Cannot access MCP tools")
except Exception as e:
    print("ERROR:", str(e))
'''
        
        print("🔄 Attempting to call MCP tools...")
        
        # Try to execute the MCP call
        try:
            # Execute in the same Python environment
            result = subprocess.run([
                sys.executable, "-c", python_code
            ], capture_output=True, text=True, timeout=30)
            
            if "SUCCESS:" in result.stdout:
                # Extract the result
                success_line = [line for line in result.stdout.split('\n') if line.startswith('SUCCESS:')][0]
                result_str = success_line.replace('SUCCESS: ', '')
                user_profile = eval(result_str)  # Parse the result
                
                # Process the successful result
                process_profile_result(user_profile, user_email)
                
            else:
                print("❌ MCP call failed")
                print(f"stdout: {result.stdout}")
                print(f"stderr: {result.stderr}")
                
                # Fallback to manual instructions
                print("\n🔧 Manual approach needed:")
                print("Run this in your main environment where MCP tools are available:")
                print(f'mcp_mixpanel_query_profiles(where=\'properties["$email"] == "{user_email}"\')')
                
        except subprocess.TimeoutExpired:
            print("❌ MCP call timed out")
        except Exception as e:
            print(f"❌ Error executing MCP call: {e}")
            
            # Fallback to manual instructions
            print("\n🔧 Manual approach needed:")
            print("Run this in your main environment where MCP tools are available:")
            print(f'mcp_mixpanel_query_profiles(where=\'properties["$email"] == "{user_email}"\')')
                    
    except Exception as e:
        print(f"❌ Error in main execution: {e}")
        print("\n🔧 Fallback: Use direct MCP call")
        print("You can call this directly in your environment:")
        print(f'mcp_mixpanel_query_profiles(where=\'properties["$email"] == "{user_email}"\')')
                


def main():
    """Main function"""
    
    if len(sys.argv) < 2:
        print("Usage: python get_user_profile.py <user_email>")
        print("Example: python get_user_profile.py jonetto@colppy.com")
        sys.exit(1)
    
    user_email = sys.argv[1]
    get_user_profile(user_email)

if __name__ == "__main__":
    main() 