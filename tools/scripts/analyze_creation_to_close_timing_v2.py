#!/usr/bin/env python3
"""
Analyze time from company creation to first Colppy deal close
Compares RNS creation dates with HubSpot "First deal closed won date"
"""

import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from rns_dataset_lookup import RNSDatasetLookup
import pandas as pd


def parse_date(date_str: str) -> datetime.date:
    """
    Parse a date string in various formats to a date object
    
    Args:
        date_str: Date string in various formats
        
    Returns:
        Date object or None if parsing fails
    """
    if not date_str or not date_str.strip():
        return None
    
    date_str = date_str.strip()
    
    try:
        # Handle ISO format with time
        if 'T' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.date()
        
        # Handle date with time (space separator)
        if ' ' in date_str:
            date_str = date_str.split(' ')[0]
        
        # Try YYYY-MM-DD format
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return None


def calculate_time_difference(creation_date: str, close_date: str) -> dict:
    """
    Calculate time difference between creation date and close date
    
    Args:
        creation_date: Company creation date (YYYY-MM-DD)
        close_date: Deal close date (YYYY-MM-DD or ISO format)
        
    Returns:
        Dictionary with time difference in days, months, years
    """
    if not creation_date or not close_date:
        return {
            'days': None,
            'months': None,
            'years': None,
            'formatted': 'N/A'
        }
    
    try:
        creation = parse_date(creation_date)
        close = parse_date(close_date)
        
        if not creation or not close:
            return {
                'days': None,
                'months': None,
                'years': None,
                'formatted': 'N/A'
            }
        
        # Calculate difference
        delta = close - creation
        days = delta.days
        
        # Calculate months and years
        years = days / 365.25
        months = days / 30.44
        
        # Format result
        if days < 0:
            formatted = f"Invalid (close before creation)"
        elif days < 30:
            formatted = f"{days} days"
        elif days < 365:
            formatted = f"{int(months)} months ({days} days)"
        else:
            formatted = f"{years:.1f} years ({int(months)} months, {days} days)"
        
        return {
            'days': days,
            'months': round(months, 1),
            'years': round(years, 2),
            'formatted': formatted
        }
    except Exception as e:
        return {
            'days': None,
            'months': None,
            'years': None,
            'formatted': f'Error: {str(e)}'
        }


def calculate_company_age(creation_date: str, reference_date: datetime.date = None) -> dict:
    """
    Calculate company age from creation date to today (or reference date)
    
    Args:
        creation_date: Company creation date (YYYY-MM-DD)
        reference_date: Reference date (default: today)
        
    Returns:
        Dictionary with age in days, months, years
    """
    if not creation_date:
        return {
            'days': None,
            'months': None,
            'years': None,
            'formatted': 'N/A'
        }
    
    try:
        creation = parse_date(creation_date)
        if not creation:
            return {
                'days': None,
                'months': None,
                'years': None,
                'formatted': 'N/A'
            }
        
        if reference_date is None:
            reference_date = datetime.now().date()
        
        # Calculate difference
        delta = reference_date - creation
        days = delta.days
        
        if days < 0:
            return {
                'days': None,
                'months': None,
                'years': None,
                'formatted': 'Invalid (creation in future)'
            }
        
        # Calculate months and years
        years = days / 365.25
        months = days / 30.44
        
        # Format result
        if days < 30:
            formatted = f"{days} days"
        elif days < 365:
            formatted = f"{int(months)} months ({days} days)"
        else:
            formatted = f"{years:.1f} years ({int(months)} months, {days} days)"
        
        return {
            'days': days,
            'months': round(months, 1),
            'years': round(years, 2),
            'formatted': formatted
        }
    except Exception as e:
        return {
            'days': None,
            'months': None,
            'years': None,
            'formatted': f'Error: {str(e)}'
        }


def calculate_colppy_age(creation_date: str, churn_date: str = None, reference_date: datetime.date = None) -> dict:
    """
    Calculate Colppy age (how long company was with Colppy)
    
    - If no churn date: from today to creation date
    - If churn date exists: from churn date to creation date (how long they were with Colppy)
    
    Args:
        creation_date: Company creation date (YYYY-MM-DD)
        churn_date: Churn date "Fecha de baja de la compañía" (YYYY-MM-DD or empty)
        reference_date: Reference date (default: today)
        
    Returns:
        Dictionary with Colppy age in days, months, years, and churn status
    """
    if not creation_date:
        return {
            'days': None,
            'months': None,
            'years': None,
            'formatted': 'N/A',
            'is_churned': False
        }
    
    try:
        creation = parse_date(creation_date)
        if not creation:
            return {
                'days': None,
                'months': None,
                'years': None,
                'formatted': 'N/A',
                'is_churned': False
            }
        
        # Determine end date: churn date if exists, otherwise today
        is_churned = bool(churn_date and churn_date.strip())
        
        if is_churned:
            end_date = parse_date(churn_date)
            if not end_date:
                # Invalid churn date, use today
                end_date = reference_date or datetime.now().date()
                is_churned = False
        else:
            end_date = reference_date or datetime.now().date()
        
        # Calculate difference
        delta = end_date - creation
        days = delta.days
        
        if days < 0:
            return {
                'days': None,
                'months': None,
                'years': None,
                'formatted': 'Invalid (end before creation)',
                'is_churned': is_churned
            }
        
        # Calculate months and years
        years = days / 365.25
        months = days / 30.44
        
        # Format result
        churn_label = " (churned)" if is_churned else ""
        if days < 30:
            formatted = f"{days} days{churn_label}"
        elif days < 365:
            formatted = f"{int(months)} months ({days} days){churn_label}"
        else:
            formatted = f"{years:.1f} years ({int(months)} months, {days} days){churn_label}"
        
        return {
            'days': days,
            'months': round(months, 1),
            'years': round(years, 2),
            'formatted': formatted,
            'is_churned': is_churned
        }
    except Exception as e:
        return {
            'days': None,
            'months': None,
            'years': None,
            'formatted': f'Error: {str(e)}',
            'is_churned': False
        }


def process_hubspot_csv(input_file: str, output_file: str = None, show_progress: bool = True):
    """
    Process HubSpot CSV with First deal closed won date and calculate timing
    
    Args:
        input_file: Path to HubSpot CSV file
        output_file: Output file path (optional)
        show_progress: Whether to show progress updates
    """
    print("=" * 70)
    print("Company Creation to First Deal Close Analysis")
    print("=" * 70)
    
    # Step 1: Read HubSpot CSV
    print(f"\n📂 Reading HubSpot data from: {input_file}")
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    companies = []
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean up quoted fields
            cleaned_row = {}
            for key, value in row.items():
                cleaned_row[key] = value.strip().strip('"') if value else ''
            companies.append(cleaned_row)
    
    print(f"✓ Loaded {len(companies)} companies")
    
    # Step 2: Extract CUITs
    print(f"\n📋 Extracting CUITs...")
    cuits_to_lookup = []
    for company in companies:
        cuit = company.get('CUIT', '').strip()
        if cuit:
            cuit_normalized = ''.join(filter(str.isdigit, cuit))
            if len(cuit_normalized) == 11:
                cuits_to_lookup.append({
                    'cuit': cuit_normalized,
                    'cuit_original': cuit,
                    'company': company
                })
    
    print(f"✓ Found {len(cuits_to_lookup)} valid CUITs to lookup")
    
    if not cuits_to_lookup:
        print("⚠️  No valid CUITs found. Exiting.")
        return None
    
    # Step 3: Load RNS dataset
    print(f"\n📊 Loading RNS dataset (this may take a moment)...")
    lookup = RNSDatasetLookup()
    dataset_path = Path("rns_datasets/registro-nacional-sociedades-202509.csv")
    
    if not dataset_path.exists():
        import zipfile
        zip_path = Path("rns_datasets/rns_2025_semestre_2.zip")
        if zip_path.exists():
            if show_progress:
                print("  Extracting from ZIP...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                if 'registro-nacional-sociedades-202509.csv' in zip_ref.namelist():
                    zip_ref.extract('registro-nacional-sociedades-202509.csv', 'rns_datasets/')
    
    if show_progress:
        print("  Loading CSV file...")
    df = lookup.load_dataset(str(dataset_path))
    print(f"✓ Loaded {len(df):,} records from RNS dataset")
    
    # Step 4: Lookup CUITs and calculate timing
    print(f"\n🔍 Looking up CUITs and calculating timing...")
    print("=" * 70)
    
    results = []
    found_count = 0
    timing_calculated = 0
    total = len(cuits_to_lookup)
    
    for i, item in enumerate(cuits_to_lookup, 1):
        cuit = item['cuit']
        company = item['company']
        company_name = company.get('Company name', 'N/A')
        first_deal_date = company.get('First deal closed won date', '').strip().strip('"')
        
        # Progress update
        if show_progress:
            progress_pct = (i / total) * 100
            status = "🔍" if i < total else "✅"
            print(f"\r  {status} Processing {i}/{total} ({progress_pct:.1f}%) - {company_name[:40]}", end='', flush=True)
        
        # Search in RNS dataset
        df_cuit_normalized = df['cuit'].astype(str).str.replace(r'[-\s\.]', '', regex=True)
        matches = df[df_cuit_normalized == cuit]
        
        result = company.copy()
        result['cuit_normalized'] = cuit
        result['cuit_original'] = item['cuit_original']
        result['rns_found'] = 'False'
        result['rns_creation_date'] = ''
        result['rns_razon_social'] = ''
        result['rns_tipo_societario'] = ''
        result['rns_provincia'] = ''
        result['time_to_close_days'] = ''
        result['time_to_close_months'] = ''
        result['time_to_close_years'] = ''
        result['time_to_close_formatted'] = ''
        
        # Initialize new prosperity fields
        result['company_age_days'] = ''
        result['company_age_months'] = ''
        result['company_age_years'] = ''
        result['company_age_formatted'] = ''
        result['colppy_age_days'] = ''
        result['colppy_age_months'] = ''
        result['colppy_age_years'] = ''
        result['colppy_age_formatted'] = ''
        result['is_churned'] = ''
        
        # Get churn date from HubSpot
        # Empty churn date = ACTIVE customer, Non-empty = CHURNED customer
        churn_date = company.get('Fecha de baja de la compañía', '').strip().strip('"')
        
        if not matches.empty:
            found_count += 1
            row = matches.iloc[0]
            result['rns_found'] = 'True'
            
            # Get creation date
            if 'fecha_hora_contrato_social' in row and pd.notna(row['fecha_hora_contrato_social']):
                date_str = str(row['fecha_hora_contrato_social'])
                creation_date = lookup._parse_date(date_str)
                result['rns_creation_date'] = creation_date or ''
            
            if 'razon_social' in row:
                result['rns_razon_social'] = row['razon_social']
            if 'tipo_societario' in row:
                result['rns_tipo_societario'] = row['tipo_societario']
            if 'dom_legal_provincia' in row:
                result['rns_provincia'] = row['dom_legal_provincia']
            
            # Calculate timing if we have both dates
            if result['rns_creation_date'] and first_deal_date:
                timing = calculate_time_difference(result['rns_creation_date'], first_deal_date)
                
                if timing['days'] is not None:
                    result['time_to_close_days'] = str(timing['days'])
                    result['time_to_close_months'] = str(timing['months'])
                    result['time_to_close_years'] = str(timing['years'])
                    result['time_to_close_formatted'] = timing['formatted']
                    timing_calculated += 1
            
            # Calculate company age (from today to creation date) - only for matched companies
            if result['rns_creation_date']:
                company_age = calculate_company_age(result['rns_creation_date'])
                if company_age['days'] is not None:
                    result['company_age_days'] = str(company_age['days'])
                    result['company_age_months'] = str(company_age['months'])
                    result['company_age_years'] = str(company_age['years'])
                    result['company_age_formatted'] = company_age['formatted']
        
        # Calculate Colppy age (for all companies in HubSpot)
        # Use "First deal closed won date" as the start date for Colppy age calculation
        # This represents when the company actually started using Colppy (first closed deal)
        # Logic:
        #   - If churn_date is empty → company is ACTIVE → calculate to TODAY
        #   - If churn_date exists → company is CHURNED → calculate to CHURN DATE
        first_deal_date_for_colppy = company.get('First deal closed won date', '').strip().strip('"')
        
        if first_deal_date_for_colppy:
            colppy_age = calculate_colppy_age(first_deal_date_for_colppy, churn_date)
            if colppy_age['days'] is not None:
                result['colppy_age_days'] = str(colppy_age['days'])
                result['colppy_age_months'] = str(colppy_age['months'])
                result['colppy_age_years'] = str(colppy_age['years'])
                result['colppy_age_formatted'] = colppy_age['formatted']
                result['is_churned'] = 'True' if colppy_age['is_churned'] else 'False'
        
        results.append(result)
    
    if show_progress:
        print()  # New line after progress
    
    # Export results
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"../outputs/creation_to_close_analysis_{timestamp}.csv"
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = list(results[0].keys())
    
    print(f"\n💾 Exporting results...")
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    # Summary
    print("\n" + "=" * 70)
    print("✅ Analysis Complete!")
    print(f"   Total companies: {len(companies)}")
    print(f"   Valid CUITs: {len(cuits_to_lookup)}")
    print(f"   CUITs found in RNS: {found_count} ({found_count/len(cuits_to_lookup)*100:.1f}%)")
    print(f"   Timing calculated: {timing_calculated} ({timing_calculated/len(cuits_to_lookup)*100:.1f}%)")
    print(f"\n📁 Results exported to: {output_path}")
    print("=" * 70)
    
    # Statistics
    if timing_calculated > 0:
        days_list = [int(r['time_to_close_days']) for r in results 
                    if r.get('time_to_close_days') and r['time_to_close_days'] and r['time_to_close_days'].isdigit()]
        if days_list:
            avg_days = sum(days_list) / len(days_list)
            min_days = min(days_list)
            max_days = max(days_list)
            
            print(f"\n📊 Time to Close Statistics:")
            print(f"   Average: {avg_days:.0f} days ({avg_days/30.44:.1f} months, {avg_days/365.25:.2f} years)")
            print(f"   Minimum: {min_days} days ({min_days/30.44:.1f} months)")
            print(f"   Maximum: {max_days} days ({max_days/30.44:.1f} months, {max_days/365.25:.1f} years)")
            print(f"   Median: {sorted(days_list)[len(days_list)//2]} days")
    
    # Company Age Statistics (for matched companies)
    company_age_days_list = [int(r['company_age_days']) for r in results 
                            if r.get('company_age_days') and r['company_age_days'] and r['company_age_days'].isdigit()]
    if company_age_days_list:
        avg_age = sum(company_age_days_list) / len(company_age_days_list)
        min_age = min(company_age_days_list)
        max_age = max(company_age_days_list)
        
        print(f"\n📊 Company Age Statistics (RNS matched):")
        print(f"   Companies with age: {len(company_age_days_list)}")
        print(f"   Average age: {avg_age:.0f} days ({avg_age/30.44:.1f} months, {avg_age/365.25:.2f} years)")
        print(f"   Minimum age: {min_age} days ({min_age/30.44:.1f} months)")
        print(f"   Maximum age: {max_age} days ({max_age/30.44:.1f} months, {max_age/365.25:.1f} years)")
        print(f"   Median age: {sorted(company_age_days_list)[len(company_age_days_list)//2]} days")
    
    # Colppy Age Statistics
    colppy_age_days_list = [int(r['colppy_age_days']) for r in results 
                            if r.get('colppy_age_days') and r['colppy_age_days'] and r['colppy_age_days'].isdigit()]
    if colppy_age_days_list:
        avg_colppy_age = sum(colppy_age_days_list) / len(colppy_age_days_list)
        min_colppy_age = min(colppy_age_days_list)
        max_colppy_age = max(colppy_age_days_list)
        
        # Count churned vs active
        churned_count = sum(1 for r in results if r.get('is_churned') == 'True')
        active_count = len(colppy_age_days_list) - churned_count
        
        print(f"\n📊 Colppy Age Statistics:")
        print(f"   Companies with Colppy age: {len(colppy_age_days_list)}")
        print(f"   Active: {active_count} | Churned: {churned_count}")
        print(f"   Average Colppy age: {avg_colppy_age:.0f} days ({avg_colppy_age/30.44:.1f} months, {avg_colppy_age/365.25:.2f} years)")
        print(f"   Minimum Colppy age: {min_colppy_age} days ({min_colppy_age/30.44:.1f} months)")
        print(f"   Maximum Colppy age: {max_colppy_age} days ({max_colppy_age/30.44:.1f} months, {max_colppy_age/365.25:.1f} years)")
        print(f"   Median Colppy age: {sorted(colppy_age_days_list)[len(colppy_age_days_list)//2]} days")
    
    # Show sample results
    print(f"\n📋 Sample Results (first 5 with RNS match):")
    print("=" * 70)
    sample_count = 0
    for r in results:
        if r.get('rns_found') == 'True' and r.get('rns_creation_date'):
            sample_count += 1
            company_name = r.get('Company name', 'N/A')[:50]
            creation_date = r.get('rns_creation_date', 'N/A')
            company_age = r.get('company_age_formatted', 'N/A')
            colppy_age = r.get('colppy_age_formatted', 'N/A')
            is_churned = r.get('is_churned', 'False')
            churn_status = " (CHURNED)" if is_churned == 'True' else " (ACTIVE)"
            
            print(f"\n  {sample_count}. {company_name}")
            print(f"     Creation Date: {creation_date}")
            print(f"     Company Age: {company_age}")
            print(f"     Colppy Age: {colppy_age}{churn_status}")
            
            if sample_count >= 5:
                break
    
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze time from company creation (RNS) to first Colppy deal close (HubSpot)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv
  
  # Specify output file
  python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv --output results.csv
  
  # Quiet mode (no progress updates)
  python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv --quiet
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Input CSV file from HubSpot with CUIT and "First deal closed won date" columns'
    )
    parser.add_argument(
        '--output',
        help='Output CSV file (default: ../outputs/creation_to_close_analysis_TIMESTAMP.csv)'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress updates'
    )
    
    args = parser.parse_args()
    
    try:
        output_path = process_hubspot_csv(
            args.input,
            args.output,
            show_progress=not args.quiet
        )
        if output_path:
            print(f"\n✓ Analysis complete. Results saved to: {output_path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

