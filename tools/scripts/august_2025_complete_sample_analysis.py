#!/usr/bin/env python3
"""
August 2025 Complete Sample Analysis Report
==========================================

This script provides the complete analysis of the first 10 August 2025 deals
and their associated companies.

Author: CEO Assistant
Date: September 13, 2025
"""

import json
from datetime import datetime
from typing import List, Dict, Any

def analyze_company_field_status(company_id: str, company_name: str, current_field_value: str, august_deal_date: str) -> Dict[str, Any]:
    """Analyze if a company's first_deal_closed_won_date field needs updating."""
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

def main():
    """Main execution function."""
    print("🚀 AUGUST 2025 COMPLETE SAMPLE ANALYSIS")
    print("=" * 60)
    print("Analysis of first 10 August 2025 deals and their companies")
    print()
    
    # Complete analysis results for first 10 deals
    analysis_results = [
        # First batch
        analyze_company_field_status("18945519422", "80884 - H COMER SAS", None, "2025-08-04T15:45:09.234Z"),
        analyze_company_field_status("9018793289", "60376 - LEPAK SRL", None, "2025-08-11T20:03:45.702Z"),
        analyze_company_field_status("33792398403", "92946 - FRANCO LAUTARO RASCHIA", "2025-08-22T13:51:46.384Z", "2025-08-22T13:51:30.998Z"),
        analyze_company_field_status("34477048178", "93286 - DEXSOL S.R.L.", "2025-08-26T20:03:47.832Z", "2025-08-26T20:03:29.307Z"),
        analyze_company_field_status("34900438910", "FORESTAL DESARROLLOS", "2025-08-22T19:35:48.924Z", "2025-08-21T17:26:42.458Z"),
        analyze_company_field_status("36255585896", "94800 - QUALIA SERVICIOS S.A.", "2025-08-14T19:36:17.156Z", "2025-08-14T00:00:00Z"),
        
        # Second batch
        analyze_company_field_status("36527860848", "95165 - COR CONSULTING", "2025-08-01T15:18:55.761Z", "2025-08-01T15:18:55.761Z"),
        analyze_company_field_status("36551040007", "95180 - LOS LAURELES AGRONEGOCIOS SA", "2025-08-12T15:14:33.795Z", "2025-08-12T15:07:17.659Z"),
        analyze_company_field_status("9018874203", "48658 - Snippet", None, "2025-08-14T18:52:09.888Z"),
        analyze_company_field_status("9018890934", "55216 - CASTELLANOS & ASOCIADOS BROKER SA", "2021-08-05T11:00:00Z", "2025-08-08T15:10:01.288Z")
    ]
    
    total_companies = len(analysis_results)
    needs_update = [r for r in analysis_results if r['needs_update']]
    no_update_needed = [r for r in analysis_results if not r['needs_update']]
    
    print("="*80)
    print("📊 AUGUST 2025 COMPLETE SAMPLE ANALYSIS REPORT")
    print("="*80)
    
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
    output_file = f"august_2025_complete_sample_analysis_{timestamp}.json"
    
    detailed_results = {
        'analysis_timestamp': datetime.now().isoformat(),
        'sample_size': total_companies,
        'summary': {
            'total_companies': total_companies,
            'needs_update_count': len(needs_update),
            'correctly_set_count': len(no_update_needed),
            'update_percentage': len(needs_update)/total_companies*100 if total_companies > 0 else 0
        },
        'companies_needing_updates': needs_update,
        'companies_correctly_set': no_update_needed,
        'all_analysis_results': analysis_results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(detailed_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Detailed results saved to: {output_file}")
    print(f"📊 Complete sample analysis finished!")
    
    print(f"\n🎯 KEY INSIGHTS:")
    print(f"   • Sample shows {len(needs_update)/total_companies*100:.1f}% of companies need updates")
    print(f"   • Main issues: NULL fields and date mismatches")
    print(f"   • Workflow execution needed for {len(needs_update)} companies")
    
    print(f"\n🎯 NEXT STEPS:")
    print(f"   1. Process remaining 50 deals from August 2025")
    print(f"   2. Run workflow for companies needing updates")
    print(f"   3. Verify workflow execution results")

if __name__ == "__main__":
    main()
