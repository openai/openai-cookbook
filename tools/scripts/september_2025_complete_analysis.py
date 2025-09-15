#!/usr/bin/env python3
"""
September 2025 Closed Won Deals - Complete Analysis
Processes all deals closed won in September 2025 and simulates first_deal_closed_won_date
"""

import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

def analyze_september_2025_deals():
    """
    Analyze all September 2025 closed won deals and simulate first_deal_closed_won_date
    """
    print("🧪 SEPTEMBER 2025 CLOSED WON DEALS ANALYSIS")
    print("=" * 70)
    print("Processing all deals closed won in September 2025")
    print("Simulating first_deal_closed_won_date calculation")
    print("=" * 70)
    
    # September 2025 deals data (from MCP search)
    september_deals = [
        {
            "id": "29918357252",
            "name": "21949 - MIGUEL ANGEL LOSADA",
            "close_date": "2025-09-01T00:00:00Z",
            "amount": "185900",
            "primary_company_id": "9018593872"
        },
        {
            "id": "34916282551", 
            "name": "90886 - NEXTVISION SRL",
            "close_date": "2025-09-09T14:12:33.351Z",
            "amount": "220900",
            "primary_company_id": "31285203237"
        },
        {
            "id": "41598996040",
            "name": "4151 Netbel Cross Selling Sueldos", 
            "close_date": "2025-09-11T15:28:17.332Z",
            "amount": "90500",
            "primary_company_id": "9019099666"
        },
        {
            "id": "42977732140",
            "name": "96475 - MUNDO ACERO",
            "close_date": "2025-09-03T18:04:32.438Z", 
            "amount": "170409",
            "primary_company_id": "TBD"
        },
        {
            "id": "43239957577",
            "name": "96589 - Estormin Comunicacion",
            "close_date": "2025-09-01T16:20:57.352Z",
            "amount": "134500", 
            "primary_company_id": "TBD"
        },
        {
            "id": "43214707883",
            "name": "96600 - L4BSEGURIDAD SAS",
            "close_date": "2025-09-01T19:39:04.796Z",
            "amount": "91500",
            "primary_company_id": "TBD"
        },
        {
            "id": "43235453018",
            "name": "96417 - CYNTIA ELISABETH OLIVERA", 
            "close_date": "2025-09-02T18:22:02.714Z",
            "amount": "220900",
            "primary_company_id": "TBD"
        },
        {
            "id": "43281146636",
            "name": "96622 - Yupana",
            "close_date": "2025-09-02T15:56:54.952Z",
            "amount": "220900",
            "primary_company_id": "TBD"
        },
        {
            "id": "43289469773",
            "name": "96642 - SISTRAN CONSULTORES S A",
            "close_date": "2025-09-02T21:08:05.781Z",
            "amount": "160153",
            "primary_company_id": "TBD"
        },
        {
            "id": "43369101837",
            "name": "96606 - TIQUES S.R.L.",
            "close_date": "2025-09-08T00:00:00Z",
            "amount": "185900",
            "primary_company_id": "TBD"
        },
        {
            "id": "43347730503",
            "name": "96698 - ALRAMA S.A.",
            "close_date": "2025-09-04T18:38:09.996Z",
            "amount": "134500",
            "primary_company_id": "TBD"
        },
        {
            "id": "43393331200",
            "name": "96717 - Tienda Babilonia",
            "close_date": "2025-09-08T12:40:11.332Z",
            "amount": "185900",
            "primary_company_id": "TBD"
        },
        {
            "id": "43420043058",
            "name": "96740 - ALEJANDRO HORACIO MONIS",
            "close_date": "2025-09-07T01:54:22.802Z",
            "amount": "220900",
            "primary_company_id": "TBD"
        },
        {
            "id": "43416155221",
            "name": "96744 - MAB Beauty Center",
            "close_date": "2025-09-05T20:26:43.792Z",
            "amount": "134500",
            "primary_company_id": "TBD"
        },
        {
            "id": "43514219069",
            "name": "96831 - Estudio Contable Luis Folgar - LOGISTICA NUEVO MUNDO SAS",
            "close_date": "2025-09-10T20:49:25.945Z",
            "amount": "64050",
            "primary_company_id": "TBD"
        },
        {
            "id": "43582301007",
            "name": "96845 - CASA ZUCO S.A",
            "close_date": "2025-09-10T19:56:15.022Z",
            "amount": "130130",
            "primary_company_id": "TBD"
        },
        {
            "id": "43542959183",
            "name": "96848 - GRUPO ZUCO S.A.",
            "close_date": "2025-09-10T19:56:35.017Z",
            "amount": "130130",
            "primary_company_id": "TBD"
        },
        {
            "id": "43576126556",
            "name": "96852 - VOY LIDERANDO",
            "close_date": "2025-09-10T19:50:28.699Z",
            "amount": "130130",
            "primary_company_id": "TBD"
        },
        {
            "id": "43576212909",
            "name": "96866 - Fideicomiso las Bardas",
            "close_date": "2025-09-11T16:58:50.535Z",
            "amount": "91500",
            "primary_company_id": "TBD"
        },
        {
            "id": "43588580425",
            "name": "96874 - Parking del Centro SA",
            "close_date": "2025-09-11T18:40:56.812Z",
            "amount": "91500",
            "primary_company_id": "TBD"
        }
    ]
    
    print(f"📊 Found {len(september_deals)} deals closed won in September 2025")
    print("\n📋 DEAL SUMMARY:")
    print("-" * 70)
    
    total_amount = 0
    companies_with_known_ids = 0
    
    for i, deal in enumerate(september_deals, 1):
        amount = float(deal['amount']) if deal['amount'] else 0
        total_amount += amount
        
        if deal['primary_company_id'] != 'TBD':
            companies_with_known_ids += 1
            
        print(f"{i:2d}. {deal['name']}")
        print(f"    Close Date: {deal['close_date'][:10]}")
        print(f"    Amount: ${amount:,.2f}")
        print(f"    Company ID: {deal['primary_company_id']}")
        print()
    
    print("📊 SUMMARY STATISTICS:")
    print("-" * 30)
    print(f"Total Deals: {len(september_deals)}")
    print(f"Total Amount: ${total_amount:,.2f}")
    print(f"Average Amount: ${total_amount/len(september_deals):,.2f}")
    print(f"Companies with Known IDs: {companies_with_known_ids}")
    print(f"Companies Need Association Lookup: {len(september_deals) - companies_with_known_ids}")
    
    return {
        "analysis_date": datetime.now().isoformat(),
        "total_deals": len(september_deals),
        "total_amount": total_amount,
        "average_amount": total_amount / len(september_deals),
        "companies_with_known_ids": companies_with_known_ids,
        "deals": september_deals
    }

def create_test_plan():
    """
    Create test plan for simulating first_deal_closed_won_date
    """
    print("\n🎯 TEST PLAN FOR FIRST DEAL WON DATE SIMULATION")
    print("=" * 60)
    
    print("📋 TESTING APPROACH:")
    print("   1. Get primary company for each September 2025 deal")
    print("   2. Get all deals associated with each company")
    print("   3. Filter for PRIMARY deals with stage 'closedwon'")
    print("   4. Calculate earliest close date")
    print("   5. Compare with current first_deal_closed_won_date field")
    print("   6. Identify any discrepancies")
    
    print("\n🔍 COMPANIES TO TEST:")
    print("   - Companies with September 2025 won deals")
    print("   - Focus on companies with multiple deals")
    print("   - Test edge cases (first deal, multiple won deals)")
    
    print("\n📊 EXPECTED OUTCOMES:")
    print("   - Simulated first_deal_closed_won_date for each company")
    print("   - Validation of workflow logic")
    print("   - Identification of data inconsistencies")
    print("   - Performance analysis of calculation")

def main():
    """Main function"""
    print("🧪 SEPTEMBER 2025 CLOSED WON DEALS - COMPLETE ANALYSIS")
    print("=" * 80)
    
    # Analyze the deals
    analysis_data = analyze_september_2025_deals()
    
    # Create test plan
    create_test_plan()
    
    print("\n🚀 READY TO EXECUTE SIMULATION:")
    print("   1. Process each company with September 2025 won deals")
    print("   2. Simulate first_deal_closed_won_date calculation")
    print("   3. Generate comprehensive test report")
    print("   4. Validate workflow logic with real data")
    
    # Save analysis data
    output_file = f"september_2025_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(analysis_data, f, indent=2, default=str)
    
    print(f"\n💾 Analysis data saved to: {output_file}")
    
    return analysis_data

if __name__ == "__main__":
    main()
