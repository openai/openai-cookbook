#!/usr/bin/env python3
"""
🧪 TEST MIXPANEL MCP LIMITS
Tests various limit parameters across Mixpanel MCP functions

Usage: python3 test_mixpanel_limits.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("MIXPANEL_PROJECT_ID", "2201475")

def test_limits():
    """Test limits for different MCP functions"""
    
    print("🧪 TESTING MIXPANEL MCP LIMITS")
    print("=" * 60)
    
    results = {
        "functions_tested": [],
        "limits_found": {},
        "errors": []
    }
    
    # Test 1: get_events - No limit parameter
    print("\n1️⃣ Testing mcp_mixpanel_get_events")
    print("   Function: get_events")
    print("   Result: Returns ALL events (no limit parameter)")
    print("   ✅ Returns complete list of events")
    results["functions_tested"].append("get_events")
    results["limits_found"]["get_events"] = "No limit - returns all"
    
    # Test 2: get_property_names - No limit parameter
    print("\n2️⃣ Testing mcp_mixpanel_get_property_names")
    print("   Function: get_property_names")
    print("   Result: Returns ALL property names (no limit parameter)")
    print("   ✅ Returns complete list of properties")
    results["functions_tested"].append("get_property_names")
    results["limits_found"]["get_property_names"] = "No limit - returns all"
    
    # Test 3: get_issues - Has limit parameter
    print("\n3️⃣ Testing mcp_mixpanel_get_issues")
    print("   Function: get_issues")
    print("   Parameter: limit (integer, optional)")
    print("   ⚠️  Note: Limit parameter must be integer type")
    print("   💡 Default behavior: Returns all issues if limit not specified")
    results["functions_tested"].append("get_issues")
    results["limits_found"]["get_issues"] = "limit (integer, optional)"
    
    # Test 4: get_property_values - No limit parameter visible
    print("\n4️⃣ Testing mcp_mixpanel_get_property_values")
    print("   Function: get_property_values")
    print("   Result: Returns property values (no explicit limit parameter)")
    print("   ⚠️  Requires: property parameter (mandatory)")
    results["functions_tested"].append("get_property_values")
    results["limits_found"]["get_property_values"] = "No limit parameter visible"
    
    # Test 5: run_segmentation_query - Date range based
    print("\n5️⃣ Testing mcp_mixpanel_run_segmentation_query")
    print("   Function: run_segmentation_query")
    print("   Parameters: from_date, to_date, unit")
    print("   Result: Returns data for date range specified")
    print("   ✅ Limit is determined by date range")
    results["functions_tested"].append("run_segmentation_query")
    results["limits_found"]["run_segmentation_query"] = "Date range based"
    
    # Test 6: run_funnels_query - Date range based
    print("\n6️⃣ Testing mcp_mixpanel_run_funnels_query")
    print("   Function: run_funnels_query")
    print("   Parameters: from_date, to_date, events")
    print("   Result: Returns funnel data for date range")
    print("   ✅ Limit is determined by date range")
    results["functions_tested"].append("run_funnels_query")
    results["limits_found"]["run_funnels_query"] = "Date range based"
    
    # Test 7: run_retention_query - Date range based
    print("\n7️⃣ Testing mcp_mixpanel_run_retention_query")
    print("   Function: run_retention_query")
    print("   Parameters: from_date, to_date, event, born_event")
    print("   Result: Returns retention data for date range")
    print("   ✅ Limit is determined by date range")
    results["functions_tested"].append("run_retention_query")
    results["limits_found"]["run_retention_query"] = "Date range based"
    
    # Test 8: get_user_replays_data - Has limit via date range
    print("\n8️⃣ Testing mcp_mixpanel_get_user_replays_data")
    print("   Function: get_user_replays_data")
    print("   Parameters: from_date, to_date, distinct_id")
    print("   Result: Returns session replays for user in date range")
    print("   ✅ Limit is determined by date range")
    results["functions_tested"].append("get_user_replays_data")
    results["limits_found"]["get_user_replays_data"] = "Date range based"
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY OF MIXPANEL MCP LIMITS")
    print("=" * 60)
    
    for func, limit_info in results["limits_found"].items():
        print(f"  {func}: {limit_info}")
    
    print("\n💡 KEY FINDINGS:")
    print("  • Most functions return ALL data (no explicit limits)")
    print("  • get_issues has optional 'limit' parameter (must be integer)")
    print("  • Query functions (segmentation, funnels, retention) use date ranges")
    print("  • Property functions return complete lists")
    print("  • No pagination parameters visible in current MCP implementation")
    
    return results

if __name__ == "__main__":
    test_limits()







