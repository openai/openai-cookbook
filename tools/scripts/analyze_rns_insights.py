#!/usr/bin/env python3
"""
Analyze RNS dataset insights from creation_to_close_analysis_full CSV
"""

import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime
import statistics

def main():
    parser = argparse.ArgumentParser(
        description='Analyze insights from creation_to_close_analysis CSV output',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python analyze_rns_insights.py --input ../outputs/creation_to_close_analysis_full_20251229.csv
  
  # With relative path
  python analyze_rns_insights.py --input creation_to_close_analysis_full_20251229.csv
  
  # With absolute path
  python analyze_rns_insights.py --input /path/to/analysis_file.csv
        """
    )
    
    parser.add_argument(
        '--input',
        '-i',
        required=True,
        help='Path to creation_to_close_analysis CSV file'
    )
    
    args = parser.parse_args()
    
    # Resolve input file path
    input_path = Path(args.input)
    if not input_path.is_absolute():
        # Try relative to script directory first, then project root
        script_dir = Path(__file__).parent
        if (script_dir / input_path).exists():
            csv_file = script_dir / input_path
        elif (script_dir.parent.parent / input_path).exists():
            csv_file = script_dir.parent.parent / input_path
        else:
            csv_file = Path(args.input).resolve()
    else:
        csv_file = input_path
    
    if not csv_file.exists():
        print(f"❌ Error: CSV file not found: {csv_file}")
        print(f"   Please check the path and try again.")
        return 1
    
    print("=" * 80)
    print("RNS DATASET ANALYSIS - INSIGHTS")
    print("=" * 80)
    print(f"\n📂 Reading from: {csv_file.name}")

    # Read data
    companies = []
    rns_found = []
    rns_not_found = []
    time_to_close_data = []

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append(row)
            
            # Track RNS matches
            rns_found_val = row.get('rns_found', '').strip()
            if rns_found_val.lower() == 'true':
                rns_found.append(row)
            else:
                rns_not_found.append(row)
            
            # Track time to close (only for companies found in RNS)
            if rns_found_val.lower() == 'true':
                time_to_close_days = row.get('time_to_close_days', '').strip()
                if time_to_close_days and time_to_close_days.isdigit():
                    time_to_close_data.append(int(time_to_close_days))

    print(f"\n📊 DATASET OVERVIEW")
    print(f"   Total companies: {len(companies):,}")
    print(f"   Found in RNS dataset: {len(rns_found):,} ({len(rns_found)/len(companies)*100:.1f}%)")
    print(f"   Not found in RNS: {len(rns_not_found):,} ({len(rns_not_found)/len(companies)*100:.1f}%)")

    # Time to Close Analysis
    if time_to_close_data:
        print(f"\n📈 TIME TO CLOSE ANALYSIS")
        print(f"   (Time from RNS creation date to first deal closed won)")
        print(f"   Companies with valid data: {len(time_to_close_data):,}")
        
        # Convert days to years for better understanding
        time_to_close_years = [d / 365.25 for d in time_to_close_data]
        
        print(f"\n   Statistics (in days):")
        print(f"   - Minimum: {min(time_to_close_data):,} days ({min(time_to_close_years):.2f} years)")
        print(f"   - Maximum: {max(time_to_close_data):,} days ({max(time_to_close_years):.2f} years)")
        print(f"   - Average: {statistics.mean(time_to_close_data):,.0f} days ({statistics.mean(time_to_close_years):.2f} years)")
        print(f"   - Median: {statistics.median(time_to_close_data):,.0f} days ({statistics.median(time_to_close_years):.2f} years)")
        
        # Percentiles
        sorted_data = sorted(time_to_close_data)
        p25 = sorted_data[len(sorted_data)//4]
        p75 = sorted_data[3*len(sorted_data)//4]
        print(f"   - 25th percentile: {p25:,} days ({p25/365.25:.2f} years)")
        print(f"   - 75th percentile: {p75:,} days ({p75/365.25:.2f} years)")
        
        # Distribution by time ranges
        print(f"\n   Distribution by time ranges:")
        ranges = [
            (0, 365, "< 1 year"),
            (365, 730, "1-2 years"),
            (730, 1095, "2-3 years"),
            (1095, 1825, "3-5 years"),
            (1825, 3650, "5-10 years"),
            (3650, float('inf'), "> 10 years")
        ]
        
        for min_days, max_days, label in ranges:
            count = sum(1 for d in time_to_close_data if min_days <= d < max_days)
            pct = count / len(time_to_close_data) * 100
            print(f"   - {label}: {count:,} companies ({pct:.1f}%)")

    # Company Type Analysis
    print(f"\n📋 COMPANY TYPE ANALYSIS (from RNS)")
    tipo_societario_count = {}
    for company in rns_found:
        tipo = company.get('rns_tipo_societario', '').strip()
        if tipo:
            tipo_societario_count[tipo] = tipo_societario_count.get(tipo, 0) + 1

    if tipo_societario_count:
        print(f"   Top company types:")
        sorted_types = sorted(tipo_societario_count.items(), key=lambda x: x[1], reverse=True)
        for tipo, count in sorted_types[:10]:
            pct = count / len(rns_found) * 100
            print(f"   - {tipo}: {count:,} ({pct:.1f}%)")

    # Province Analysis
    print(f"\n🗺️  PROVINCE ANALYSIS (from RNS)")
    provincia_count = {}
    for company in rns_found:
        provincia = company.get('rns_provincia', '').strip()
        if provincia:
            provincia_count[provincia] = provincia_count.get(provincia, 0) + 1

    if provincia_count:
        print(f"   Top provinces:")
        sorted_provincias = sorted(provincia_count.items(), key=lambda x: x[1], reverse=True)
        for provincia, count in sorted_provincias[:10]:
            pct = count / len(rns_found) * 100
            print(f"   - {provincia}: {count:,} ({pct:.1f}%)")

    # Industry Analysis (from HubSpot)
    print(f"\n🏭 INDUSTRY ANALYSIS (from HubSpot)")
    industria_count = {}
    for company in companies:
        industria = company.get('Industria (colppy)', '').strip()
        if industria:
            industria_count[industria] = industria_count.get(industria, 0) + 1

    if industria_count:
        print(f"   Top industries:")
        sorted_industrias = sorted(industria_count.items(), key=lambda x: x[1], reverse=True)
        for industria, count in sorted_industrias[:10]:
            pct = count / len(companies) * 100
            print(f"   - {industria}: {count:,} ({pct:.1f}%)")

    # Churn Analysis
    print(f"\n📉 CHURN ANALYSIS")
    churned_companies = [c for c in companies if c.get('Fecha de baja de la compañía', '').strip()]
    churned_with_rns = [c for c in churned_companies if c.get('rns_found', '').strip().lower() == 'true']
    churned_without_rns = [c for c in churned_companies if c.get('rns_found', '').strip().lower() != 'true']

    print(f"   Total churned companies: {len(churned_companies):,}")
    print(f"   Churned with RNS data: {len(churned_with_rns):,}")
    print(f"   Churned without RNS data: {len(churned_without_rns):,}")

    if churned_with_rns:
        churned_time_to_close = []
        for company in churned_with_rns:
            days = company.get('time_to_close_days', '').strip()
            if days and days.isdigit():
                churned_time_to_close.append(int(days))
        
        if churned_time_to_close:
            print(f"\n   Time to Close for Churned Companies:")
            churned_years = [d / 365.25 for d in churned_time_to_close]
            print(f"   - Average: {statistics.mean(churned_time_to_close):,.0f} days ({statistics.mean(churned_years):.2f} years)")
            print(f"   - Median: {statistics.median(churned_time_to_close):,.0f} days ({statistics.median(churned_years):.2f} years)")

    # Active vs Churned Comparison
    active_companies = [c for c in companies if not c.get('Fecha de baja de la compañía', '').strip()]
    active_with_rns = [c for c in active_companies if c.get('rns_found', '').strip().lower() == 'true']

    if active_with_rns and churned_with_rns:
        active_time_to_close = []
        for company in active_with_rns:
            days = company.get('time_to_close_days', '').strip()
            if days and days.isdigit():
                active_time_to_close.append(int(days))
        
        if active_time_to_close and churned_time_to_close:
            print(f"\n   Comparison: Active vs Churned")
            print(f"   - Active companies - Avg Time to Close: {statistics.mean(active_time_to_close):,.0f} days ({statistics.mean([d/365.25 for d in active_time_to_close]):.2f} years)")
            print(f"   - Churned companies - Avg Time to Close: {statistics.mean(churned_time_to_close):,.0f} days ({statistics.mean([d/365.25 for d in churned_time_to_close]):.2f} years)")
            
            diff = statistics.mean(churned_time_to_close) - statistics.mean(active_time_to_close)
            print(f"   - Difference: {diff:,.0f} days ({diff/365.25:.2f} years)")

    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

