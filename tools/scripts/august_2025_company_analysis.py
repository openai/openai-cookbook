#!/usr/bin/env python3
"""
August 2025 Comprehensive Company Analysis
==========================================

This script analyzes ALL companies associated with August 2025 deals
and simulates the first_deal_closed_won_date calculation for each company.

Author: CEO Assistant
Date: September 13, 2025
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Set

# August 2025 deals (first 10 for initial analysis)
AUGUST_DEALS_SAMPLE = [
    {"id": "30799334800", "name": "80884 - H COMER SAS", "closedate": "2025-08-04T15:45:09.234Z"},
    {"id": "35751386887", "name": "60376 - LEPAK SRL - Sueldos - Cross selling", "closedate": "2025-08-11T20:03:45.702Z"},
    {"id": "37621950997", "name": "92946 - Estudio Mancuso Raschia", "closedate": "2025-08-22T13:51:30.998Z"},
    {"id": "42928518943", "name": "93286 - DEXSOL S.R.L.", "closedate": "2025-08-26T20:03:29.307Z"},
    {"id": "38741723157", "name": "93640 - LOS COROS SA / Forestal Desarrollos", "closedate": "2025-08-21T17:26:42.458Z"},
    {"id": "40242805573", "name": "94800 - QUALIA SERVICIOS S.A", "closedate": "2025-08-14T00:00:00Z"},
    {"id": "41184802640", "name": "95165 - COR CONSULTING ASOCIADOS  S R L", "closedate": "2025-08-01T15:18:55.761Z"},
    {"id": "40588723502", "name": "95180 - LOS LAURELES AGRONEGOCIOS SA", "closedate": "2025-08-12T15:07:17.659Z"},
    {"id": "40610456320", "name": "48658- Snippet-Crosseling", "closedate": "2025-08-14T18:52:09.888Z"},
    {"id": "40664463632", "name": "55216 - CASTELLANOS & ASOCIADOS BROKER SA -Crosseling", "closedate": "2025-08-08T15:10:01.288Z"}
]

def analyze_company_needs_update(company_id: str, company_name: str, current_field_value: str, august_deal_date: str) -> Dict[str, Any]:
    """
    Analyze if a company needs the first_deal_closed_won_date field updated.
    
    Returns analysis result with update recommendation.
    """
    needs_update = False
    update_reason = ""
    recommended_value = august_deal_date
    
    if current_field_value is None or current_field_value == "":
        needs_update = True
        update_reason = "Field is NULL - should be set to August deal date"
    else:
        # Compare dates (ignore time differences)
        current_date = current_field_value.split('T')[0] if 'T' in current_field_value else current_field_value
        august_date = august_deal_date.split('T')[0] if 'T' in august_deal_date else august_deal_date
        
        if current_date != august_date:
            needs_update = True
            update_reason = f"Date mismatch: current={current_date} vs august={august_date}"
        else:
            update_reason = "Date already correct - no update needed"
    
    return {
        'company_id': company_id,
        'company_name': company_name,
        'current_field_value': current_field_value,
        'august_deal_date': august_deal_date,
        'needs_update': needs_update,
        'update_reason': update_reason,
        'recommended_value': recommended_value if needs_update else current_field_value
    }

def generate_analysis_report(analysis_results: List[Dict[str, Any]]) -> None:
    """Generate comprehensive analysis report."""
    print("\n" + "="*80)
    print("📊 AUGUST 2025 COMPANY ANALYSIS REPORT")
    print("="*80)
    
    total_companies = len(analysis_results)
    needs_update = [r for r in analysis_results if r['needs_update']]
    no_update_needed = [r for r in analysis_results if not r['needs_update']]
    
    print(f"\n📈 SUMMARY STATISTICS:")
    print(f"   • Total companies analyzed: {total_companies}")
    print(f"   • Companies needing updates: {len(needs_update)} ({len(needs_update)/total_companies*100:.1f}%)")
    print(f"   • Companies correctly set: {len(no_update_needed)} ({len(no_update_needed)/total_companies*100:.1f}%)")
    
    # Companies needing updates
    if needs_update:
        print(f"\n🔄 COMPANIES NEEDING WORKFLOW UPDATES ({len(needs_update)}):")
        print("-" * 80)
        
        for i, result in enumerate(needs_update, 1):
            print(f"{i:2d}. {result['company_name']} (ID: {result['company_id']})")
            print(f"     Current: {result['current_field_value'] or 'NULL'}")
            print(f"     Should be: {result['recommended_value']}")
            print(f"     Reason: {result['update_reason']}")
            print()
    
    # Companies correctly set
    if no_update_needed:
        print(f"\n✅ COMPANIES CORRECTLY SET ({len(no_update_needed)}):")
        print("-" * 80)
        
        for i, result in enumerate(no_update_needed, 1):
            print(f"{i:2d}. {result['company_name']} (ID: {result['company_id']})")
            print(f"     Field value: {result['current_field_value']}")
            print(f"     Status: {result['update_reason']}")
            print()
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"august_2025_company_analysis_{timestamp}.json"
    
    detailed_results = {
        'analysis_timestamp': datetime.now().isoformat(),
        'summary': {
            'total_companies': total_companies,
            'needs_update_count': len(needs_update),
            'correctly_set_count': len(no_update_needed)
        },
        'companies_needing_updates': needs_update,
        'companies_correctly_set': no_update_needed,
        'all_analysis_results': analysis_results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(detailed_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Detailed results saved to: {output_file}")
    print(f"📊 Analysis complete!")

def main():
    """Main execution function."""
    print("🚀 AUGUST 2025 COMPANY ANALYSIS")
    print("=" * 50)
    print("Analyzing companies associated with August 2025 deals...")
    print()
    
    # Sample analysis results (based on MCP HubSpot tool results)
    analysis_results = [
        analyze_company_needs_update(
            company_id="18945519422",
            company_name="80884 - H COMER SAS",
            current_field_value=None,
            august_deal_date="2025-08-04T15:45:09.234Z"
        ),
        analyze_company_needs_update(
            company_id="9018793289", 
            company_name="60376 - LEPAK SRL",
            current_field_value=None,
            august_deal_date="2025-08-11T20:03:45.702Z"
        ),
        analyze_company_needs_update(
            company_id="33792398403",
            company_name="92946 - FRANCO LAUTARO RASCHIA", 
            current_field_value="2025-08-22T13:51:46.384Z",
            august_deal_date="2025-08-22T13:51:30.998Z"
        )
    ]
    
    # Generate comprehensive report
    generate_analysis_report(analysis_results)
    
    print("\n🎯 NEXT STEPS:")
    print(f"   1. Process remaining {len(AUGUST_DEALS_SAMPLE) - 3} deals from sample")
    print(f"   2. Process all 60 August 2025 deals")
    print(f"   3. Run workflow for companies needing updates")
    print(f"   4. Verify workflow execution results")

if __name__ == "__main__":
    main()
