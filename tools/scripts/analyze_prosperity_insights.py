#!/usr/bin/env python3
"""
Prosperity Insights Analysis Script

Analyzes prosperity metrics from the creation_to_close_analysis CSV output.
Compares Colppy customer data with Argentina company survival statistics.

This script is designed to be run periodically (e.g., annually) to track
prosperity trends and compare against Argentina market benchmarks.

Usage:
    python analyze_prosperity_insights.py --input creation_to_close_analysis.csv
    python analyze_prosperity_insights.py --input creation_to_close_analysis.csv --output prosperity_insights.csv
    python analyze_prosperity_insights.py --input creation_to_close_analysis.csv --argentina-survival-rate 0.54
"""

import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime
import statistics
from collections import defaultdict
import pandas as pd


def parse_date(date_str: str):
    """Parse date string to date object"""
    if not date_str or not str(date_str).strip() or str(date_str).strip().lower() == 'nan':
        return None
    
    date_str = str(date_str).strip()
    
    try:
        # Handle ISO format with time
        if 'T' in date_str:
            from datetime import datetime
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.date()
        
        # Handle date with time (space separator)
        if ' ' in date_str:
            date_str = date_str.split(' ')[0]
        
        # Try YYYY-MM-DD format
        from datetime import datetime
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return None


def calculate_prosperity_score(row, argentina_survival_rate: float = 0.54):
    """
    Calculate prosperity score for a company
    
    Criteria:
    1. Company age ≥ 5 years (survived critical period)
    2. Still ALIVE (no churn date in HubSpot)
    3. Colppy lifetime ≥ 5 years (long-term relationship)
    4. Still ACTIVE with Colppy (current customer)
    
    Args:
        row: Company data row
        argentina_survival_rate: Expected survival rate after 5 years (default: 0.54)
        
    Returns:
        Dictionary with prosperity metrics
    """
    # Parse data
    company_age_days = None
    if row.get('company_age_days') and str(row.get('company_age_days')).strip():
        try:
            company_age_days = float(row.get('company_age_days'))
        except:
            company_age_days = None
    
    colppy_age_days = None
    if row.get('colppy_age_days') and str(row.get('colppy_age_days')).strip():
        try:
            colppy_age_days = float(row.get('colppy_age_days'))
        except:
            colppy_age_days = None
    
    # Check if alive (no churn date)
    churn_date = row.get('Fecha de baja de la compañía', '').strip()
    is_alive = not churn_date or churn_date == '' or str(churn_date).lower() == 'nan'
    
    # Check if active with Colppy
    is_churned_colppy = str(row.get('is_churned', 'False')).strip().upper() == 'TRUE'
    is_active_colppy = not is_churned_colppy
    
    # Calculate criteria
    criteria_1_company_5_years = company_age_days is not None and company_age_days >= 1825  # 5 years
    criteria_2_still_alive = is_alive
    criteria_3_colppy_5_years = colppy_age_days is not None and colppy_age_days >= 1825
    criteria_4_active_colppy = is_active_colppy
    
    # Calculate prosperity score (0-100)
    score = 0
    if criteria_1_company_5_years:
        score += 25
    if criteria_2_still_alive:
        score += 25
    if criteria_3_colppy_5_years:
        score += 25
    if criteria_4_active_colppy:
        score += 25
    
    # Determine prosperity tier
    if score == 100:
        tier = "High Prosperity"
    elif score >= 75:
        tier = "Medium-High Prosperity"
    elif score >= 50:
        tier = "Medium Prosperity"
    elif score >= 25:
        tier = "Low-Medium Prosperity"
    else:
        tier = "Low Prosperity"
    
    # Calculate survival probability adjustment
    survival_probability = None
    if company_age_days is not None:
        company_age_years = company_age_days / 365.25
        if company_age_years < 5:
            # Companies < 5 years: apply Argentina survival rate
            survival_probability = argentina_survival_rate
        else:
            # Companies 5+ years: they've already survived
            survival_probability = 1.0 if is_alive else 0.0
    
    return {
        'prosperity_score': score,
        'prosperity_tier': tier,
        'criteria_1_company_5_years': criteria_1_company_5_years,
        'criteria_2_still_alive': criteria_2_still_alive,
        'criteria_3_colppy_5_years': criteria_3_colppy_5_years,
        'criteria_4_active_colppy': criteria_4_active_colppy,
        'is_prosperous': score == 100,
        'survival_probability': survival_probability,
        'company_age_years': company_age_days / 365.25 if company_age_days else None,
        'colppy_age_years': colppy_age_days / 365.25 if colppy_age_days else None
    }


def analyze_prosperity(input_file: str, output_file: str = None, argentina_survival_rate: float = 0.54, show_progress: bool = True):
    """
    Analyze prosperity metrics from prosperity calculation CSV
    
    Args:
        input_file: Path to creation_to_close_analysis CSV file
        output_file: Output CSV file path (optional)
        argentina_survival_rate: Expected survival rate after 5 years (default: 0.54)
        show_progress: Whether to show progress updates
    """
    print("=" * 100)
    print("PROSPERITY INSIGHTS ANALYSIS")
    print("=" * 100)
    print()
    print(f"📊 Argentina Survival Statistics:")
    print(f"   - Expected survival rate after 5 years: {argentina_survival_rate*100:.1f}%")
    print(f"   - This means {((1-argentina_survival_rate)*100):.1f}% of companies die before 5 years")
    print()
    
    # Read input CSV
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    print(f"📂 Reading data from: {input_path.name}")
    
    companies = []
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean up quoted fields
            cleaned_row = {}
            for key, value in row.items():
                cleaned_row[key] = value.strip().strip('"') if value else ''
            companies.append(cleaned_row)
    
    print(f"✓ Loaded {len(companies):,} companies")
    print()
    
    # Filter valid data
    rns_found = [c for c in companies if str(c.get('rns_found', '')).strip().upper() == 'TRUE']
    print(f"📊 Companies found in RNS: {len(rns_found):,} ({len(rns_found)/len(companies)*100:.1f}%)")
    print()
    
    # Calculate prosperity metrics for each company
    if show_progress:
        print("🔍 Calculating prosperity metrics...")
    
    results = []
    for company in companies:
        prosperity = calculate_prosperity_score(company, argentina_survival_rate)
        
        # Add prosperity metrics to company data
        result = company.copy()
        result.update(prosperity)
        
        # Add is_alive flag for all companies
        churn_date = company.get('Fecha de baja de la compañía', '').strip()
        result['is_alive'] = not churn_date or churn_date == '' or str(churn_date).lower() == 'nan'
        
        results.append(result)
    
    if show_progress:
        print(f"✓ Calculated prosperity metrics for {len(results):,} companies")
        print()
    
    # Analysis
    print("=" * 100)
    print("1️⃣ COMPANY SURVIVAL ANALYSIS")
    print("=" * 100)
    print()
    
    # Filter companies with valid age data
    valid_company_age = [r for r in results 
                         if r.get('company_age_days') and str(r.get('company_age_days')).strip()]
    
    for r in valid_company_age:
        try:
            r['company_age_days'] = float(r['company_age_days'])
        except:
            r['company_age_days'] = None
    
    valid_company_age = [r for r in valid_company_age if r.get('company_age_days') is not None and r['company_age_days'] >= 0]
    
    # is_alive is already set in the main loop, just filter
    alive_companies = [r for r in valid_company_age if r.get('is_alive')]
    dead_companies = [r for r in valid_company_age if not r.get('is_alive')]
    
    print(f"Total companies with age data: {len(valid_company_age):,}")
    print(f"   - Known ALIVE (no churn date): {len(alive_companies):,} ({len(alive_companies)/len(valid_company_age)*100:.1f}%)")
    print(f"   - Known DEAD (has churn date): {len(dead_companies):,} ({len(dead_companies)/len(valid_company_age)*100:.1f}%)")
    print()
    
    # Age distribution for alive companies
    if alive_companies:
        alive_age_days = [r['company_age_days'] for r in alive_companies]
        alive_age_years = [d / 365.25 for d in alive_age_days]
        
        print("📊 SURVIVAL ANALYSIS - COMPANIES WE KNOW ARE ALIVE:")
        print()
        
        age_brackets = [
            (0, 365, '0-1 year'),
            (365, 730, '1-2 years'),
            (730, 1825, '2-5 years'),
            (1825, 3650, '5-10 years'),
            (3650, 7300, '10-20 years'),
            (7300, float('inf'), '20+ years')
        ]
        
        for min_days, max_days, label in age_brackets:
            if max_days == float('inf'):
                count = sum(1 for d in alive_age_days if d >= min_days)
            else:
                count = sum(1 for d in alive_age_days if min_days <= d < max_days)
            pct = count / len(alive_age_days) * 100 if alive_age_days else 0
            print(f"   {label:15s}: {count:5,} companies ({pct:5.1f}%)")
        
        print()
        alive_5_years = sum(1 for d in alive_age_days if d >= 1825)
        pct_alive_5_years = (alive_5_years / len(alive_age_days) * 100) if alive_age_days else 0
        print(f"   Companies 5+ years old (and ALIVE): {alive_5_years:,} ({pct_alive_5_years:.1f}%)")
        print(f"   vs. Argentina average: {argentina_survival_rate*100:.1f}% survive 5+ years")
        
        if pct_alive_5_years > argentina_survival_rate * 100:
            diff = pct_alive_5_years - (argentina_survival_rate * 100)
            print(f"   ✅ Colppy customers exceed Argentina average by {diff:.1f} percentage points")
        else:
            diff = (argentina_survival_rate * 100) - pct_alive_5_years
            print(f"   ⚠️  Colppy customers below Argentina average by {diff:.1f} percentage points")
        print()
        
        # Survival rate for 5+ years old companies
        all_5_plus = [r for r in valid_company_age if r['company_age_days'] >= 1825]
        alive_5_plus = [r for r in all_5_plus if r.get('is_alive')]
        
        if len(all_5_plus) > 0:
            actual_survival_rate = (len(alive_5_plus) / len(all_5_plus)) * 100
            print(f"📊 SURVIVAL RATE FOR 5+ YEARS OLD COMPANIES:")
            print(f"   Total companies 5+ years: {len(all_5_plus):,}")
            print(f"   Known alive: {len(alive_5_plus):,}")
            print(f"   Known dead: {len(all_5_plus) - len(alive_5_plus):,}")
            print(f"   Actual survival rate: {actual_survival_rate:.1f}%")
            print(f"   Argentina average: {argentina_survival_rate*100:.1f}%")
            if actual_survival_rate > argentina_survival_rate * 100:
                diff = actual_survival_rate - (argentina_survival_rate * 100)
                print(f"   ✅ Exceed Argentina average by {diff:.1f} percentage points")
            else:
                diff = (argentina_survival_rate * 100) - actual_survival_rate
                print(f"   ⚠️  Below Argentina average by {diff:.1f} percentage points")
            print()
    
    # Colppy Age Analysis
    print("=" * 100)
    print("2️⃣ COLPPY CUSTOMER LIFETIME ANALYSIS")
    print("=" * 100)
    print()
    
    valid_colppy_age = [r for r in results 
                       if r.get('colppy_age_days') and str(r.get('colppy_age_days')).strip()]
    
    for r in valid_colppy_age:
        try:
            r['colppy_age_days'] = float(r['colppy_age_days'])
        except:
            r['colppy_age_days'] = None
    
    valid_colppy_age = [r for r in valid_colppy_age if r.get('colppy_age_days') is not None and r['colppy_age_days'] >= 0]
    
    if valid_colppy_age:
        colppy_age_days = [r['colppy_age_days'] for r in valid_colppy_age]
        colppy_age_years = [d / 365.25 for d in colppy_age_days]
        
        print(f"Total customers with valid Colppy age: {len(colppy_age_days):,}")
        print(f"Average Colppy customer lifetime: {statistics.mean(colppy_age_days):,.0f} days ({statistics.mean(colppy_age_years):.2f} years)")
        print(f"Median Colppy customer lifetime: {statistics.median(colppy_age_days):,.0f} days ({statistics.median(colppy_age_years):.2f} years)")
        print()
        
        # Distribution
        print("📊 COLPPY CUSTOMER LIFETIME DISTRIBUTION:")
        print()
        
        lifetime_brackets = [
            (0, 365, '0-1 year'),
            (365, 730, '1-2 years'),
            (730, 1825, '2-5 years'),
            (1825, 3650, '5-10 years'),
            (3650, float('inf'), '10+ years')
        ]
        
        for min_days, max_days, label in lifetime_brackets:
            if max_days == float('inf'):
                count = sum(1 for d in colppy_age_days if d >= min_days)
            else:
                count = sum(1 for d in colppy_age_days if min_days <= d < max_days)
            pct = count / len(colppy_age_days) * 100 if colppy_age_days else 0
            print(f"   {label:15s}: {count:5,} customers ({pct:5.1f}%)")
        
        print()
        survived_5_years_colppy = sum(1 for d in colppy_age_days if d >= 1825)
        pct_survived_5_years_colppy = (survived_5_years_colppy / len(colppy_age_days) * 100) if colppy_age_days else 0
        print(f"   Customers with Colppy for 5+ years: {survived_5_years_colppy:,} ({pct_survived_5_years_colppy:.1f}%)")
        print()
        
        # Active vs Churned
        active = [r for r in valid_colppy_age if str(r.get('is_churned', 'False')).strip().upper() == 'FALSE']
        churned = [r for r in valid_colppy_age if str(r.get('is_churned', 'False')).strip().upper() == 'TRUE']
        
        print(f"📊 CUSTOMER STATUS:")
        print(f"   Active customers: {len(active):,} ({len(active)/len(valid_colppy_age)*100:.1f}%)")
        print(f"   Churned customers: {len(churned):,} ({len(churned)/len(valid_colppy_age)*100:.1f}%)")
        print()
        
        if active:
            active_days = [r['colppy_age_days'] for r in active]
            active_years = [d / 365.25 for d in active_days]
            print(f"   Active customers - Average: {statistics.mean(active_days):,.0f} days ({statistics.mean(active_years):.2f} years)")
            print(f"   Active customers - Median: {statistics.median(active_days):,.0f} days ({statistics.median(active_years):.2f} years)")
            print()
        
        if churned:
            churned_days = [r['colppy_age_days'] for r in churned]
            churned_years = [d / 365.25 for d in churned_days]
            print(f"   Churned customers - Average: {statistics.mean(churned_days):,.0f} days ({statistics.mean(churned_years):.2f} years)")
            print(f"   Churned customers - Median: {statistics.median(churned_days):,.0f} days ({statistics.median(churned_years):.2f} years)")
            print()
    
    # Prosperity Analysis
    print("=" * 100)
    print("3️⃣ PROSPERITY ANALYSIS")
    print("=" * 100)
    print()
    
    print("💡 PROSPERITY DEFINITION:")
    print("   A 'prosperous' Colppy customer must meet ALL criteria:")
    print("   1. ✅ Company age ≥ 5 years (survived critical survival period)")
    print("   2. ✅ Still ALIVE today (no churn date in HubSpot)")
    print("   3. ✅ Colppy lifetime ≥ 5 years (long-term relationship)")
    print("   4. ✅ Still ACTIVE with Colppy (current customer)")
    print()
    
    # Count prosperous companies
    prosperous_companies = [r for r in results if r.get('is_prosperous')]
    
    print(f"📊 PROSPERITY METRICS:")
    print(f"   Total companies analyzed: {len(results):,}")
    print(f"   True Prosperous Companies: {len(prosperous_companies):,} ({len(prosperous_companies)/len(results)*100:.1f}%)")
    print()
    
    if prosperous_companies:
        # Average metrics for prosperous companies
        prosperous_ages = [r.get('company_age_years') for r in prosperous_companies if r.get('company_age_years')]
        prosperous_colppy_ages = [r.get('colppy_age_years') for r in prosperous_companies if r.get('colppy_age_years')]
        
        if prosperous_ages:
            print(f"   Average company age: {statistics.mean(prosperous_ages):.2f} years")
            print(f"   Median company age: {statistics.median(prosperous_ages):.2f} years")
            print()
        
        if prosperous_colppy_ages:
            print(f"   Average Colppy lifetime: {statistics.mean(prosperous_colppy_ages):.2f} years")
            print(f"   Median Colppy lifetime: {statistics.median(prosperous_colppy_ages):.2f} years")
            print()
    
    # Prosperity tier distribution
    print("📊 PROSPERITY TIER DISTRIBUTION:")
    print()
    
    tier_counts = defaultdict(int)
    for r in results:
        tier = r.get('prosperity_tier', 'Unknown')
        tier_counts[tier] += 1
    
    for tier in ['High Prosperity', 'Medium-High Prosperity', 'Medium Prosperity', 
                 'Low-Medium Prosperity', 'Low Prosperity']:
        count = tier_counts.get(tier, 0)
        pct = count / len(results) * 100 if results else 0
        print(f"   {tier:30s}: {count:5,} companies ({pct:5.1f}%)")
    print()
    
    # Criteria breakdown
    print("📊 CRITERIA BREAKDOWN:")
    print()
    
    criteria_1_count = sum(1 for r in results if r.get('criteria_1_company_5_years'))
    criteria_2_count = sum(1 for r in results if r.get('criteria_2_still_alive'))
    criteria_3_count = sum(1 for r in results if r.get('criteria_3_colppy_5_years'))
    criteria_4_count = sum(1 for r in results if r.get('criteria_4_active_colppy'))
    
    print(f"   Companies 5+ years old: {criteria_1_count:,} ({criteria_1_count/len(results)*100:.1f}%)")
    print(f"   Still ALIVE: {criteria_2_count:,} ({criteria_2_count/len(results)*100:.1f}%)")
    print(f"   Colppy lifetime 5+ years: {criteria_3_count:,} ({criteria_3_count/len(results)*100:.1f}%)")
    print(f"   Still ACTIVE with Colppy: {criteria_4_count:,} ({criteria_4_count/len(results)*100:.1f}%)")
    print()
    
    # Export results
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"../outputs/prosperity_insights_{timestamp}.csv"
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Prepare fieldnames - preserve original order, add new fields at end
    if results:
        # Start with original company fields (from first company)
        fieldnames = list(companies[0].keys()) if companies else []
        
        # Add prosperity fields in order
        prosperity_fields = [
            'prosperity_score',
            'prosperity_tier',
            'criteria_1_company_5_years',
            'criteria_2_still_alive',
            'criteria_3_colppy_5_years',
            'criteria_4_active_colppy',
            'is_prosperous',
            'survival_probability',
            'company_age_years',
            'colppy_age_years',
            'is_alive'
        ]
        
        # Add prosperity fields that don't already exist
        for field in prosperity_fields:
            if field not in fieldnames:
                fieldnames.append(field)
        
        # Ensure all keys from results are included (in case we missed any)
        all_result_keys = set()
        for result in results:
            all_result_keys.update(result.keys())
        
        for key in all_result_keys:
            if key not in fieldnames:
                fieldnames.append(key)
    else:
        fieldnames = []
    
    print(f"💾 Exporting results to: {output_path}")
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print()
    print("=" * 100)
    print("✅ PROSPERITY ANALYSIS COMPLETE")
    print("=" * 100)
    print(f"📁 Results exported to: {output_path}")
    print()
    
    # Summary statistics
    print("📊 SUMMARY STATISTICS:")
    print()
    print(f"   Total companies: {len(results):,}")
    print(f"   Found in RNS: {len(rns_found):,} ({len(rns_found)/len(results)*100:.1f}%)")
    print(f"   Prosperous companies: {len(prosperous_companies):,} ({len(prosperous_companies)/len(results)*100:.1f}%)")
    if valid_colppy_age:
        print(f"   Average Colppy lifetime: {statistics.mean(colppy_age_days):,.0f} days ({statistics.mean(colppy_age_years):.2f} years)")
    if valid_company_age and alive_companies:
        alive_age_days = [r['company_age_days'] for r in alive_companies]
        print(f"   Average company age (alive): {statistics.mean(alive_age_days):,.0f} days ({statistics.mean([d/365.25 for d in alive_age_days]):.2f} years)")
    print()
    
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze prosperity insights from creation_to_close_analysis CSV output',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python analyze_prosperity_insights.py --input ../outputs/creation_to_close_analysis_with_edge_cases_20260102_101539.csv
  
  # Specify output file
  python analyze_prosperity_insights.py --input input.csv --output prosperity_insights.csv
  
  # Custom Argentina survival rate
  python analyze_prosperity_insights.py --input input.csv --argentina-survival-rate 0.54
  
  # Quiet mode
  python analyze_prosperity_insights.py --input input.csv --quiet
        """
    )
    
    parser.add_argument(
        '--input',
        '-i',
        required=True,
        help='Input CSV file from prosperity calculation (creation_to_close_analysis CSV)'
    )
    parser.add_argument(
        '--output',
        '-o',
        help='Output CSV file (default: ../outputs/prosperity_insights_TIMESTAMP.csv)'
    )
    parser.add_argument(
        '--argentina-survival-rate',
        type=float,
        default=0.54,
        help='Argentina survival rate after 5 years (default: 0.54 = 54%%)'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress updates'
    )
    
    args = parser.parse_args()
    
    # Resolve input file path
    input_path = Path(args.input)
    if not input_path.is_absolute():
        script_dir = Path(__file__).parent
        if (script_dir / input_path).exists():
            input_file = str(script_dir / input_path)
        elif (script_dir.parent / input_path).exists():
            input_file = str(script_dir.parent / input_path)
        else:
            input_file = str(Path(args.input).resolve())
    else:
        input_file = args.input
    
    try:
        output_path = analyze_prosperity(
            input_file,
            args.output,
            args.argentina_survival_rate,
            show_progress=not args.quiet
        )
        if output_path:
            print(f"✓ Analysis complete. Results saved to: {output_path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

