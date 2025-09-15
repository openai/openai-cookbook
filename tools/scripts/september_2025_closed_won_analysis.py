#!/usr/bin/env python3
"""
September 2025 Closed Won Deals Analysis
Tests all companies that had deals closed won in September 2025
Simulates what their first_deal_closed_won_date would be
"""

import sys
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

def get_september_2025_closed_won_deals():
    """
    Get all deals closed won in September 2025 with full pagination
    """
    print("🔍 RETRIEVING SEPTEMBER 2025 CLOSED WON DEALS")
    print("=" * 60)
    
    # Search for deals closed won in September 2025
    search_filters = [
        {
            "filters": [
                {
                    "propertyName": "dealstage",
                    "operator": "EQ",
                    "value": "closedwon"
                },
                {
                    "propertyName": "closedate",
                    "operator": "GTE",
                    "value": "2025-09-01T00:00:00Z"
                },
                {
                    "propertyName": "closedate", 
                    "operator": "LT",
                    "value": "2025-10-01T00:00:00Z"
                }
            ]
        }
    ]
    
    print("📋 Search Criteria:")
    print("   - Deal stage: closedwon")
    print("   - Close date: >= 2025-09-01")
    print("   - Close date: < 2025-10-01")
    print("   - Properties: dealstage, closedate, dealname")
    
    return search_filters

def simulate_first_deal_won_date_calculation(company_id: str, company_name: str) -> Dict[str, Any]:
    """
    Simulate the first deal won date calculation for a company
    """
    print(f"\n🧪 SIMULATING FOR: {company_name} (ID: {company_id})")
    print("-" * 50)
    
    # This will be populated by the actual MCP calls
    return {
        "company_id": company_id,
        "company_name": company_name,
        "simulation_status": "pending",
        "primary_deals": [],
        "won_deals": [],
        "calculated_first_won_date": None,
        "current_field_value": None,
        "match_status": None
    }

def analyze_september_2025_results():
    """
    Analyze the results of September 2025 closed won deals test
    """
    print("\n📊 SEPTEMBER 2025 ANALYSIS RESULTS")
    print("=" * 60)
    
    print("🎯 TEST OBJECTIVES:")
    print("   1. Find all deals closed won in September 2025")
    print("   2. Get their associated companies")
    print("   3. Simulate first_deal_closed_won_date calculation")
    print("   4. Compare with current field values")
    print("   5. Identify any discrepancies")
    
    print("\n📋 EXPECTED OUTCOMES:")
    print("   - Companies with September 2025 won deals")
    print("   - Simulated first_deal_closed_won_date for each")
    print("   - Validation of workflow logic")
    print("   - Identification of any data inconsistencies")

def main():
    """Main function to run September 2025 analysis"""
    print("🧪 SEPTEMBER 2025 CLOSED WON DEALS ANALYSIS")
    print("=" * 70)
    print("Testing all companies with deals closed won in September 2025")
    print("Simulating first_deal_closed_won_date calculation")
    print("=" * 70)
    
    # Get search criteria
    search_filters = get_september_2025_closed_won_deals()
    
    # Analyze expected results
    analyze_september_2025_results()
    
    print("\n🚀 READY TO EXECUTE:")
    print("   1. Search for September 2025 closed won deals")
    print("   2. Get associated companies for each deal")
    print("   3. Simulate first_deal_closed_won_date calculation")
    print("   4. Generate comprehensive test report")
    
    print("\n📊 TEST SCOPE:")
    print("   - Time period: September 1-30, 2025")
    print("   - Deal stage: closedwon")
    print("   - Data source: HubSpot (full pagination)")
    print("   - Test type: Simulation (no data modification)")
    
    return {
        "test_name": "September 2025 Closed Won Deals Analysis",
        "test_date": datetime.now().isoformat(),
        "search_criteria": search_filters,
        "scope": {
            "time_period": "2025-09-01 to 2025-09-30",
            "deal_stage": "closedwon",
            "data_source": "HubSpot",
            "test_type": "simulation"
        }
    }

if __name__ == "__main__":
    main()
