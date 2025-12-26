#!/usr/bin/env python3
"""
Mixpanel PQL Funnel Analysis by Role
Analyzes funnel conversion rates segmented by accountants vs non-accountants

This script queries Mixpanel funnel data and segments by user role to compare
conversion rates between accountants and non-accountants at each funnel step.

The funnel ends with PQL (Product Qualified Lead) conversion.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

def analyze_funnel_by_role(funnel_data: Dict, role_property: str = "Rol") -> Dict:
    """
    Analyze funnel data segmented by role (accountants vs non-accountants)
    
    Args:
        funnel_data: Raw funnel query results from Mixpanel
        role_property: Property name to use for role segmentation
        
    Returns:
        Dictionary with role-segmented analysis
    """
    # Categorize roles
    accountant_roles = ["contador", "accountant", "asesor", "consultor"]
    
    # Group by role category
    accountants = {}
    non_accountants = {}
    unknown = {}
    
    # Process funnel data
    # Expected structure: funnel steps with user counts segmented by role
    # This will depend on the actual Mixpanel API response format
    
    return {
        "accountants": accountants,
        "non_accountants": non_accountants,
        "unknown": unknown,
        "summary": {
            "total_accountants": sum(accountants.values()) if accountants else 0,
            "total_non_accountants": sum(non_accountants.values()) if non_accountants else 0,
            "conversion_rate_accountants": 0,
            "conversion_rate_non_accountants": 0
        }
    }

def format_role_analysis(analysis: Dict) -> str:
    """
    Format role analysis results for display
    """
    output = []
    output.append("=" * 80)
    output.append("PQL FUNNEL ANALYSIS BY ROLE")
    output.append("=" * 80)
    output.append("")
    
    summary = analysis.get("summary", {})
    
    output.append("SUMMARY:")
    output.append("-" * 80)
    output.append(f"Accountants: {summary.get('total_accountants', 0)}")
    output.append(f"Non-Accountants: {summary.get('total_non_accountants', 0)}")
    output.append(f"Accountant Conversion Rate: {summary.get('conversion_rate_accountants', 0):.1f}%")
    output.append(f"Non-Accountant Conversion Rate: {summary.get('conversion_rate_non_accountants', 0):.1f}%")
    output.append("")
    
    return "\n".join(output)

if __name__ == "__main__":
    print("Mixpanel PQL Funnel Role Analysis")
    print("=" * 80)
    print("\nThis script analyzes funnel conversion by role.")
    print("To use:")
    print("1. Query Mixpanel funnel with role segmentation")
    print("2. Pass results to analyze_funnel_by_role()")
    print("3. Display formatted results")
    print("\nNote: Mixpanel API has rate limits (60 queries/hour)")
    print("Wait for rate limit reset before running queries.")


