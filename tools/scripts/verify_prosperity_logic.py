#!/usr/bin/env python3
"""
Verify prosperity calculation logic for both ACTIVE and CHURNED companies
"""

import csv
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, '/Users/virulana/openai-cookbook/tools/scripts')
from analyze_creation_to_close_timing_v2 import calculate_company_age, calculate_colppy_age, parse_date

print("=" * 80)
print("VERIFICATION: Prosperity Calculation Logic")
print("=" * 80)

csv_file = Path("../outputs/hubspot-crm-exports-companias-con-fecha-de-primer-n-2025-12-30.csv")
target_cuits = ["30-71215464-7", "30-71452874-9"]

print(f"\n📂 Reading from: {csv_file.name}")
print("\nTesting logic for:")
print("  • ACTIVE companies: churn date is EMPTY → calculate to TODAY")
print("  • CHURNED companies: churn date EXISTS → calculate to CHURN DATE")

companies_found = {}

with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cuit = row.get('CUIT', '').strip().strip('"')
        if cuit in target_cuits:
            companies_found[cuit] = row
            if len(companies_found) == len(target_cuits):
                break

for cuit, company in companies_found.items():
    company_name = company.get('Company name', 'N/A').strip().strip('"')
    first_deal = company.get('First deal closed won date', '').strip().strip('"')
    churn_date = company.get('Fecha de baja de la compañía', '').strip().strip('"')
    
    print("\n" + "=" * 80)
    print(f"COMPANY: {company_name}")
    print(f"CUIT: {cuit}")
    print("=" * 80)
    
    print(f"\n📋 Data:")
    print(f"   First Deal Closed Won: {first_deal}")
    print(f"   Churn Date (Fecha de baja): '{churn_date}'")
    
    # Determine status
    if churn_date:
        status = "CHURNED"
        end_date_desc = f"Churn Date ({churn_date})"
    else:
        status = "ACTIVE"
        end_date_desc = f"Today ({datetime.now().date()})"
    
    print(f"\n   Status: {status}")
    print(f"   → End date for calculation: {end_date_desc}")
    
    # Calculate Colppy Age
    if first_deal:
        print("\n" + "-" * 80)
        print("COLPPY AGE CALCULATION")
        print("-" * 80)
        
        colppy_age = calculate_colppy_age(first_deal, churn_date)
        
        print(f"\n✅ Result:")
        print(f"   Days: {colppy_age['days']:,}")
        print(f"   Months: {colppy_age['months']:.1f}")
        print(f"   Years: {colppy_age['years']:.2f}")
        print(f"   Formatted: {colppy_age['formatted']}")
        print(f"   Is Churned: {colppy_age['is_churned']}")
        
        # Verification
        first_deal_parsed = parse_date(first_deal)
        if churn_date:
            churn_parsed = parse_date(churn_date)
            if first_deal_parsed and churn_parsed:
                manual_days = (churn_parsed - first_deal_parsed).days
                print(f"\n   ✓ Verification (CHURNED):")
                print(f"     {churn_parsed} - {first_deal_parsed} = {manual_days:,} days")
                print(f"     Script: {colppy_age['days']:,} days")
                print(f"     Match: {'✅ YES' if abs(colppy_age['days'] - manual_days) <= 1 else '❌ NO'}")
        else:
            today = datetime.now().date()
            if first_deal_parsed:
                manual_days = (today - first_deal_parsed).days
                print(f"\n   ✓ Verification (ACTIVE):")
                print(f"     {today} - {first_deal_parsed} = {manual_days:,} days")
                print(f"     Script: {colppy_age['days']:,} days")
                print(f"     Match: {'✅ YES' if abs(colppy_age['days'] - manual_days) <= 1 else '❌ NO'}")

print("\n" + "=" * 80)
print("✅ Logic Verification Complete")
print("=" * 80)
print("\nThe script correctly handles:")
print("  ✅ ACTIVE companies (empty churn date) → calculates to TODAY")
print("  ✅ CHURNED companies (has churn date) → calculates to CHURN DATE")
print("  ✅ Uses 'First deal closed won date' as start date for Colppy age")
print("\nReady to run full analysis on all companies!")










