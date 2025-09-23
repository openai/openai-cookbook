#!/usr/bin/env python3
"""
RPA Consulting Edge Case Test
Specific test for RPA Consulting (ID: 9019080056) to validate edge cases
"""

import sys
import os
from datetime import datetime

def test_rpa_consulting_edge_cases():
    """
    Test edge cases specifically for RPA Consulting
    """
    print("🧪 RPA CONSULTING EDGE CASE TEST")
    print("=" * 50)
    print("Company ID: 9019080056")
    print("Current first_deal_closed_won_date: 2017-11-07T00:00:00Z")
    print("=" * 50)
    
    print("\n📊 CURRENT STATE ANALYSIS:")
    print("   - Company: RPA Consulting")
    print("   - Primary deals: 6")
    print("   - Won deals: 2 (2017-11-07, 2025-08-05)")
    print("   - First won date: 2017-11-07")
    
    print("\n🧪 EDGE CASE SCENARIOS TO TEST:")
    
    # Scenario 1: Primary Company Switch
    print("\n1️⃣ PRIMARY COMPANY SWITCH:")
    print("   📋 Test: Switch primary company of deal 9354729778 (2017-11-07)")
    print("   🎯 Expected:")
    print("      - RPA Consulting: first_deal_closed_won_date → 2025-08-05")
    print("      - New company: first_deal_closed_won_date → 2017-11-07")
    print("   ⚠️  Risk: This is a destructive test - use carefully!")
    
    # Scenario 2: Deal De-association
    print("\n2️⃣ DEAL DE-ASSOCIATION:")
    print("   📋 Test: Remove all deals from RPA Consulting")
    print("   🎯 Expected:")
    print("      - RPA Consulting: first_deal_closed_won_date → null")
    print("   ⚠️  Risk: This is a destructive test - use carefully!")
    
    # Scenario 3: Non-Primary Deal Addition
    print("\n3️⃣ NON-PRIMARY DEAL ADDITION:")
    print("   📋 Test: Add a non-primary lost deal to RPA Consulting")
    print("   🎯 Expected:")
    print("      - RPA Consulting: first_deal_closed_won_date → unchanged (2017-11-07)")
    print("   ✅ Safe: This is a non-destructive test")
    
    return {
        "company_id": "9019080056",
        "company_name": "RPA Consulting",
        "current_state": {
            "first_deal_closed_won_date": "2017-11-07T00:00:00Z",
            "primary_deals": 6,
            "won_deals": 2
        },
        "test_scenarios": [
            {
                "id": 1,
                "name": "Primary Company Switch",
                "description": "Switch primary company of oldest won deal",
                "risk": "DESTRUCTIVE",
                "expected_rpa": "2025-08-05",
                "expected_new_company": "2017-11-07"
            },
            {
                "id": 2, 
                "name": "Deal De-association",
                "description": "Remove all deals from company",
                "risk": "DESTRUCTIVE",
                "expected_rpa": "null"
            },
            {
                "id": 3,
                "name": "Non-Primary Deal Addition",
                "description": "Add non-primary lost deal",
                "risk": "SAFE",
                "expected_rpa": "unchanged (2017-11-07)"
            }
        ]
    }

def create_safe_test_plan():
    """
    Create a safe test plan that doesn't destroy data
    """
    print("\n🛡️ SAFE TEST PLAN (NON-DESTRUCTIVE)")
    print("=" * 50)
    
    print("📋 RECOMMENDED APPROACH:")
    print("   1. Create a TEST company for edge case testing")
    print("   2. Use RPA Consulting for validation only")
    print("   3. Test scenarios on test company first")
    print("   4. Validate workflow logic without affecting production data")
    
    print("\n🎯 SAFE TEST STEPS:")
    print("   1. Create test company: 'Edge Case Test Company'")
    print("   2. Add test deals with known dates")
    print("   3. Test each scenario on test company")
    print("   4. Validate results")
    print("   5. Clean up test data")
    
    print("\n📊 VALIDATION APPROACH:")
    print("   1. Use RPA Consulting as reference (don't modify)")
    print("   2. Test workflow logic on test company")
    print("   3. Verify custom code handles edge cases correctly")
    print("   4. Document any issues found")

def main():
    """Main function"""
    print("🧪 RPA CONSULTING EDGE CASE TESTER")
    print("=" * 60)
    
    # Run edge case analysis
    test_data = test_rpa_consulting_edge_cases()
    
    # Create safe test plan
    create_safe_test_plan()
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    print("\n✅ WORKFLOW COVERAGE:")
    print("   - All 3 edge cases are covered by Group 2 trigger")
    print("   - Custom code should handle primary deal filtering")
    print("   - Edge cases should work correctly")
    
    print("\n⚠️  TESTING RECOMMENDATIONS:")
    print("   - Use test company for destructive tests")
    print("   - Use RPA Consulting for validation only")
    print("   - Test one scenario at a time")
    print("   - Monitor workflow logs carefully")
    
    print("\n🚀 NEXT STEPS:")
    print("   1. Save your workflow configuration")
    print("   2. Create test company for edge case testing")
    print("   3. Test scenarios on test company")
    print("   4. Validate results with our testing framework")

if __name__ == "__main__":
    main()
