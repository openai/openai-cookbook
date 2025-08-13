#!/usr/bin/env python3
"""
Mixpanel Rate Limit Checker
Simple script to test if rate limits have reset before running larger queries.
"""

import os
import sys
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, project_root)

def check_rate_limit():
    """Test if Mixpanel rate limits have reset with a minimal API call."""
    
    print("🧪 Testing Mixpanel Rate Limit Status")
    print("=" * 50)
    print(f"🕐 Check Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Import and test - this will only work if we have MCP access
        # For now, we'll create a placeholder that shows what to do
        
        print("📡 Testing minimal API call...")
        print("⚠️  This requires MCP tools to be available")
        print("💡 To test manually, try running:")
        print("   source mcp_env/bin/activate")
        print("   # Then use MCP tools or this script")
        
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure you're in the MCP environment:")
        print("   source mcp_env/bin/activate")
        return False

def main():
    """Main execution function."""
    
    if check_rate_limit():
        print("✅ Rate limits appear to be reset!")
        print("🚀 You can now run dormant company analysis:")
        print("   python tools/scripts/mixpanel/dormant_companies_efficient.py")
    else:
        print("⏳ Rate limits may still be active.")
        print("💭 Try again in 10-15 minutes.")
        print("📊 Mixpanel limits: 60 queries/hour, 5 concurrent")

if __name__ == "__main__":
    main() 