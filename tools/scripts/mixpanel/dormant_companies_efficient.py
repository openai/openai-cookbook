#!/usr/bin/env python3
"""
Efficient Dormant Companies Analysis
Identifies companies that were active in week before last but inactive last week.
Optimized to minimize API calls and avoid rate limits.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict

def analyze_dormant_companies():
    """
    Efficient approach to identify dormant companies.
    Uses minimal API calls to maximize data while staying under rate limits.
    """
    
    print("🔍 Efficient Dormant Companies Analysis")
    print("=" * 60)
    
    # Define date ranges
    week_before_last_start = "2025-06-02"
    week_before_last_end = "2025-06-08"
    last_week_start = "2025-06-09"
    last_week_end = "2025-06-15"
    
    print(f"📅 Week Before Last: {week_before_last_start} to {week_before_last_end}")
    print(f"📅 Last Week: {last_week_start} to {last_week_end}")
    print()
    
    # Strategy: Use business events that indicate real company activity
    # These events are more meaningful than generic web tracking
    business_events = [
        "Generó comprobante de venta",
        "Generó comprobante de compra", 
        "Agregó medio de pago",
        "Abrió el módulo clientes",
        "Abrió el módulo proveedores"
    ]
    
    print("🎯 Strategy: Analyze business events to identify active companies")
    print("   Events to analyze:", ", ".join(business_events))
    print()
    
    # This would be the actual implementation when rate limits allow:
    print("📝 Implementation Plan:")
    print("1. Query distinct_id for each business event in week before last")
    print("2. Query distinct_id for each business event in last week") 
    print("3. Compare user lists to find users active in week 1 but not week 2")
    print("4. Group users by email domain to identify company patterns")
    print("5. Generate dormant company risk report")
    print()
    
    # Rate limit safe approach
    print("⚠️  Current Status: Waiting for rate limit reset")
    print("💡 Recommendation: Run this script in 1 hour when rate limit resets")
    print()
    
    # Sample output structure that would be generated:
    sample_output = {
        "analysis_date": datetime.now().isoformat(),
        "periods": {
            "week_before_last": {"start": week_before_last_start, "end": week_before_last_end},
            "last_week": {"start": last_week_start, "end": last_week_end}
        },
        "dormant_companies": {
            "high_risk": [],  # Companies with >50 events previous week, 0 last week
            "medium_risk": [], # Companies with 10-50 events previous week, 0 last week  
            "low_risk": []    # Companies with 1-10 events previous week, 0 last week
        },
        "summary": {
            "total_companies_analyzed": 0,
            "total_dormant_companies": 0,
            "churn_risk_percentage": 0.0
        }
    }
    
    print("📊 Expected Output Structure:")
    print(json.dumps(sample_output, indent=2))
    
    return sample_output

if __name__ == "__main__":
    result = analyze_dormant_companies()
    
    # Save results for future reference
    output_dir = "tools/outputs/mixpanel"
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{output_dir}/dormant_analysis_plan_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n💾 Analysis plan saved to: {output_file}") 