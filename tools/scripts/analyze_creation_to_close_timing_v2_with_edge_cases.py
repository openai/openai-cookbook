#!/usr/bin/env python3
"""
Analyze time from company creation to first Colppy deal close
WITH EDGE CASE DETECTION

Compares RNS creation dates with HubSpot "First deal closed won date"
and identifies edge cases where calculations may not make sense.
"""

import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from rns_dataset_lookup import RNSDatasetLookup
import pandas as pd
from collections import defaultdict


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


class EdgeCaseTracker:
    """Track edge cases and exceptions during processing"""
    
    def __init__(self):
        self.edge_cases = {
            'negative_time_to_close': [],
            'missing_first_deal_date': [],
            'missing_rns_creation_date': [],
            'invalid_first_deal_date': [],
            'invalid_rns_creation_date': [],
            'future_first_deal_date': [],
            'future_rns_creation_date': [],
            'churn_before_first_deal': [],
            'very_old_company': [],
            'very_short_time_to_close': [],
            'duplicate_cuit': [],
            'invalid_cuit_format': [],
            'rns_not_found': [],
            'multiple_rns_matches': []
        }
    
    def add_edge_case(self, category: str, company_name: str, details: dict):
        """Add an edge case to tracking"""
        if category in self.edge_cases:
            self.edge_cases[category].append({
                'company_name': company_name,
                **details
            })
    
    def print_summary(self):
        """Print summary of all edge cases found"""
        print("\n" + "=" * 80)
        print("⚠️  EDGE CASES & EXCEPTIONS DETECTED")
        print("=" * 80)
        
        total_edge_cases = sum(len(cases) for cases in self.edge_cases.values())
        
        if total_edge_cases == 0:
            print("\n✅ No edge cases detected! All calculations appear valid.")
            return
        
        print(f"\n📊 Total edge cases found: {total_edge_cases}")
        print()
        
        # Negative time to close (critical)
        if self.edge_cases['negative_time_to_close']:
            print("🚨 CRITICAL: Negative Time to Close")
            print("   (First deal date is BEFORE RNS creation date)")
            print(f"   Count: {len(self.edge_cases['negative_time_to_close'])}")
            for case in self.edge_cases['negative_time_to_close'][:5]:
                print(f"   - {case['company_name']}: RNS={case.get('rns_date')}, First Deal={case.get('first_deal_date')}, Diff={case.get('days_diff')} days")
            if len(self.edge_cases['negative_time_to_close']) > 5:
                print(f"   ... and {len(self.edge_cases['negative_time_to_close']) - 5} more")
            print()
        
        # Missing dates
        if self.edge_cases['missing_first_deal_date']:
            print("⚠️  Missing First Deal Date")
            print(f"   Count: {len(self.edge_cases['missing_first_deal_date'])}")
            for case in self.edge_cases['missing_first_deal_date'][:3]:
                print(f"   - {case['company_name']}")
            if len(self.edge_cases['missing_first_deal_date']) > 3:
                print(f"   ... and {len(self.edge_cases['missing_first_deal_date']) - 3} more")
            print()
        
        if self.edge_cases['missing_rns_creation_date']:
            print("⚠️  Missing RNS Creation Date (found in RNS but no date)")
            print(f"   Count: {len(self.edge_cases['missing_rns_creation_date'])}")
            for case in self.edge_cases['missing_rns_creation_date'][:3]:
                print(f"   - {case['company_name']} (CUIT: {case.get('cuit')})")
            if len(self.edge_cases['missing_rns_creation_date']) > 3:
                print(f"   ... and {len(self.edge_cases['missing_rns_creation_date']) - 3} more")
            print()
        
        # Invalid dates
        if self.edge_cases['invalid_first_deal_date']:
            print("⚠️  Invalid First Deal Date (cannot parse)")
            print(f"   Count: {len(self.edge_cases['invalid_first_deal_date'])}")
            for case in self.edge_cases['invalid_first_deal_date'][:3]:
                print(f"   - {case['company_name']}: '{case.get('date_value')}'")
            if len(self.edge_cases['invalid_first_deal_date']) > 3:
                print(f"   ... and {len(self.edge_cases['invalid_first_deal_date']) - 3} more")
            print()
        
        if self.edge_cases['invalid_rns_creation_date']:
            print("⚠️  Invalid RNS Creation Date (cannot parse)")
            print(f"   Count: {len(self.edge_cases['invalid_rns_creation_date'])}")
            for case in self.edge_cases['invalid_rns_creation_date'][:3]:
                print(f"   - {case['company_name']}: '{case.get('date_value')}'")
            if len(self.edge_cases['invalid_rns_creation_date']) > 3:
                print(f"   ... and {len(self.edge_cases['invalid_rns_creation_date']) - 3} more")
            print()
        
        # Future dates
        if self.edge_cases['future_first_deal_date']:
            print("⚠️  Future First Deal Date")
            print(f"   Count: {len(self.edge_cases['future_first_deal_date'])}")
            for case in self.edge_cases['future_first_deal_date'][:3]:
                print(f"   - {case['company_name']}: {case.get('date_value')} (days in future: {case.get('days_ahead')})")
            if len(self.edge_cases['future_first_deal_date']) > 3:
                print(f"   ... and {len(self.edge_cases['future_first_deal_date']) - 3} more")
            print()
        
        if self.edge_cases['future_rns_creation_date']:
            print("⚠️  Future RNS Creation Date")
            print(f"   Count: {len(self.edge_cases['future_rns_creation_date'])}")
            for case in self.edge_cases['future_rns_creation_date'][:3]:
                print(f"   - {case['company_name']}: {case.get('date_value')} (days in future: {case.get('days_ahead')})")
            if len(self.edge_cases['future_rns_creation_date']) > 3:
                print(f"   ... and {len(self.edge_cases['future_rns_creation_date']) - 3} more")
            print()
        
        # Churn date issues
        if self.edge_cases['churn_before_first_deal']:
            print("⚠️  Churn Date Before First Deal Date")
            print(f"   Count: {len(self.edge_cases['churn_before_first_deal'])}")
            for case in self.edge_cases['churn_before_first_deal'][:3]:
                print(f"   - {case['company_name']}: First Deal={case.get('first_deal_date')}, Churn={case.get('churn_date')}")
            if len(self.edge_cases['churn_before_first_deal']) > 3:
                print(f"   ... and {len(self.edge_cases['churn_before_first_deal']) - 3} more")
            print()
        
        # Very old companies
        if self.edge_cases['very_old_company']:
            print("⚠️  Very Old Company (created before 1900)")
            print(f"   Count: {len(self.edge_cases['very_old_company'])}")
            for case in self.edge_cases['very_old_company'][:3]:
                print(f"   - {case['company_name']}: Created {case.get('creation_date')} ({case.get('years_old')} years old)")
            if len(self.edge_cases['very_old_company']) > 3:
                print(f"   ... and {len(self.edge_cases['very_old_company']) - 3} more")
            print()
        
        # Very short time to close
        if self.edge_cases['very_short_time_to_close']:
            print("⚠️  Very Short Time to Close (< 1 day)")
            print(f"   Count: {len(self.edge_cases['very_short_time_to_close'])}")
            for case in self.edge_cases['very_short_time_to_close'][:3]:
                print(f"   - {case['company_name']}: {case.get('days')} days (RNS={case.get('rns_date')}, First Deal={case.get('first_deal_date')})")
            if len(self.edge_cases['very_short_time_to_close']) > 3:
                print(f"   ... and {len(self.edge_cases['very_short_time_to_close']) - 3} more")
            print()
        
        # Duplicate CUITs
        if self.edge_cases['duplicate_cuit']:
            print("⚠️  Duplicate CUITs (multiple companies with same CUIT)")
            print(f"   Count: {len(self.edge_cases['duplicate_cuit'])}")
            cuit_counts = defaultdict(list)
            for case in self.edge_cases['duplicate_cuit']:
                cuit_counts[case.get('cuit')].append(case['company_name'])
            for cuit, companies in list(cuit_counts.items())[:3]:
                print(f"   - CUIT {cuit}: {len(companies)} companies - {', '.join(companies[:2])}")
            if len(cuit_counts) > 3:
                print(f"   ... and {len(cuit_counts) - 3} more duplicate CUITs")
            print()
        
        # Invalid CUIT format
        if self.edge_cases['invalid_cuit_format']:
            print("⚠️  Invalid CUIT Format")
            print(f"   Count: {len(self.edge_cases['invalid_cuit_format'])}")
            for case in self.edge_cases['invalid_cuit_format'][:3]:
                print(f"   - {case['company_name']}: '{case.get('cuit')}' (length: {case.get('length')})")
            if len(self.edge_cases['invalid_cuit_format']) > 3:
                print(f"   ... and {len(self.edge_cases['invalid_cuit_format']) - 3} more")
            print()
        
        # RNS not found
        if self.edge_cases['rns_not_found']:
            print("ℹ️  RNS Not Found (expected for individual CUITs or unregistered companies)")
            print(f"   Count: {len(self.edge_cases['rns_not_found'])}")
            print("   (This is normal for CUITs starting with 20-27, which are individuals)")
            print()
        
        # Multiple RNS matches
        if self.edge_cases['multiple_rns_matches']:
            print("⚠️  Multiple RNS Matches (same CUIT appears multiple times in RNS)")
            print(f"   Count: {len(self.edge_cases['multiple_rns_matches'])}")
            for case in self.edge_cases['multiple_rns_matches'][:3]:
                print(f"   - {case['company_name']} (CUIT: {case.get('cuit')}, Matches: {case.get('match_count')})")
            if len(self.edge_cases['multiple_rns_matches']) > 3:
                print(f"   ... and {len(self.edge_cases['multiple_rns_matches']) - 3} more")
            print()
        
        print("=" * 80)
        print("\n💡 RECOMMENDATIONS:")
        print("   1. Review 'Negative Time to Close' cases - these indicate data inconsistencies")
        print("   2. Verify 'Future Dates' - may indicate timezone or data entry errors")
        print("   3. Check 'Very Short Time to Close' - may indicate data entry errors")
        print("   4. Investigate 'Duplicate CUITs' - may need manual review")
        print("   5. 'RNS Not Found' is normal for individual CUITs (20-27)")
        print("=" * 80)


def process_hubspot_csv(input_file: str, output_file: str = None, show_progress: bool = True):
    """
    Process HubSpot CSV with First deal closed won date and calculate timing
    WITH EDGE CASE DETECTION
    
    Args:
        input_file: Path to HubSpot CSV file
        output_file: Output file path (optional)
        show_progress: Whether to show progress updates
    """
    print("=" * 80)
    print("Company Creation to First Deal Close Analysis")
    print("WITH EDGE CASE DETECTION")
    print("=" * 80)
    
    # Initialize edge case tracker
    edge_tracker = EdgeCaseTracker()
    today = datetime.now().date()
    
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
    
    # Step 2: Extract CUITs and detect edge cases
    print(f"\n📋 Extracting CUITs and detecting edge cases...")
    cuits_to_lookup = []
    cuit_counts = defaultdict(int)
    
    for company in companies:
        cuit = company.get('CUIT', '').strip()
        company_name = company.get('Company name', 'N/A')
        
        if cuit:
            cuit_normalized = ''.join(filter(str.isdigit, cuit))
            
            # Check for invalid CUIT format
            if len(cuit_normalized) != 11:
                edge_tracker.add_edge_case(
                    'invalid_cuit_format',
                    company_name,
                    {'cuit': cuit, 'length': len(cuit_normalized)}
                )
                continue
            
            # Track duplicate CUITs
            cuit_counts[cuit_normalized] += 1
            if cuit_counts[cuit_normalized] > 1:
                edge_tracker.add_edge_case(
                    'duplicate_cuit',
                    company_name,
                    {'cuit': cuit_normalized}
                )
            
            cuits_to_lookup.append({
                'cuit': cuit_normalized,
                'cuit_original': cuit,
                'company': company
            })
        else:
            # No CUIT provided
            edge_tracker.add_edge_case(
                'invalid_cuit_format',
                company_name,
                {'cuit': '', 'length': 0}
            )
    
    print(f"✓ Found {len(cuits_to_lookup)} valid CUITs to lookup")
    
    if not cuits_to_lookup:
        print("⚠️  No valid CUITs found. Exiting.")
        return None
    
    # Step 3: Load RNS dataset
    print(f"\n📊 Loading RNS dataset (this may take a moment)...")
    lookup = RNSDatasetLookup()
    script_dir = Path(__file__).parent
    dataset_path = script_dir / "rns_datasets/registro-nacional-sociedades-202509.csv"
    
    if not dataset_path.exists():
        import zipfile
        zip_path = script_dir / "rns_datasets/rns_2025_semestre_2.zip"
        if zip_path.exists():
            if show_progress:
                print("  Extracting from ZIP...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                if 'registro-nacional-sociedades-202509.csv' in zip_ref.namelist():
                    zip_ref.extract('registro-nacional-sociedades-202509.csv', script_dir / 'rns_datasets/')
    
    if show_progress:
        print("  Loading CSV file...")
    df = lookup.load_dataset(str(dataset_path))
    print(f"✓ Loaded {len(df):,} records from RNS dataset")
    
    # Step 4: Lookup CUITs and calculate timing WITH EDGE CASE DETECTION
    print(f"\n🔍 Looking up CUITs and calculating timing...")
    print("=" * 80)
    
    results = []
    found_count = 0
    timing_calculated = 0
    total = len(cuits_to_lookup)
    
    for i, item in enumerate(cuits_to_lookup, 1):
        cuit = item['cuit']
        company = item['company']
        company_name = company.get('Company name', 'N/A')
        first_deal_date_str = company.get('First deal closed won date', '').strip().strip('"')
        churn_date_str = company.get('Fecha de baja de la compañía', '').strip().strip('"')
        
        # Progress update
        if show_progress:
            progress_pct = (i / total) * 100
            status = "🔍" if i < total else "✅"
            print(f"\r  {status} Processing {i}/{total} ({progress_pct:.1f}%) - {company_name[:40]}", end='', flush=True)
        
        # Check for missing first deal date
        if not first_deal_date_str:
            edge_tracker.add_edge_case(
                'missing_first_deal_date',
                company_name,
                {'cuit': cuit}
            )
        
        # Parse first deal date
        first_deal_date = parse_date(first_deal_date_str) if first_deal_date_str else None
        
        # Check for invalid first deal date
        if first_deal_date_str and not first_deal_date:
            edge_tracker.add_edge_case(
                'invalid_first_deal_date',
                company_name,
                {'date_value': first_deal_date_str, 'cuit': cuit}
            )
        
        # Check for future first deal date
        if first_deal_date and first_deal_date > today:
            days_ahead = (first_deal_date - today).days
            edge_tracker.add_edge_case(
                'future_first_deal_date',
                company_name,
                {'date_value': str(first_deal_date), 'days_ahead': days_ahead, 'cuit': cuit}
            )
        
        # Check churn date before first deal date
        if churn_date_str and first_deal_date:
            churn_date = parse_date(churn_date_str)
            if churn_date and churn_date < first_deal_date:
                edge_tracker.add_edge_case(
                    'churn_before_first_deal',
                    company_name,
                    {
                        'first_deal_date': str(first_deal_date),
                        'churn_date': str(churn_date),
                        'cuit': cuit
                    }
                )
        
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
        result['edge_case_flags'] = ''  # Track edge cases for this record
        
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
        
        edge_case_flags = []
        
        if matches.empty:
            # RNS not found
            edge_tracker.add_edge_case(
                'rns_not_found',
                company_name,
                {'cuit': cuit}
            )
            edge_case_flags.append('RNS_NOT_FOUND')
        else:
            found_count += 1
            
            # Check for multiple matches
            if len(matches) > 1:
                edge_tracker.add_edge_case(
                    'multiple_rns_matches',
                    company_name,
                    {'cuit': cuit, 'match_count': len(matches)}
                )
                edge_case_flags.append('MULTIPLE_RNS_MATCHES')
            
            row = matches.iloc[0]
            result['rns_found'] = 'True'
            
            # Get creation date
            rns_creation_date_str = None
            if 'fecha_hora_contrato_social' in row and pd.notna(row['fecha_hora_contrato_social']):
                rns_creation_date_str = str(row['fecha_hora_contrato_social'])
                creation_date = lookup._parse_date(rns_creation_date_str)
                result['rns_creation_date'] = creation_date or ''
            elif 'fecha_contrato_social' in row and pd.notna(row['fecha_contrato_social']):
                rns_creation_date_str = str(row['fecha_contrato_social'])
                creation_date = lookup._parse_date(rns_creation_date_str)
                result['rns_creation_date'] = creation_date or ''
            
            # Check for missing RNS creation date
            if not result['rns_creation_date']:
                edge_tracker.add_edge_case(
                    'missing_rns_creation_date',
                    company_name,
                    {'cuit': cuit, 'date_value': rns_creation_date_str or 'N/A'}
                )
                edge_case_flags.append('MISSING_RNS_DATE')
            else:
                # Check for invalid RNS creation date
                rns_creation_date_parsed = parse_date(result['rns_creation_date'])
                if not rns_creation_date_parsed:
                    edge_tracker.add_edge_case(
                        'invalid_rns_creation_date',
                        company_name,
                        {'date_value': result['rns_creation_date'], 'cuit': cuit}
                    )
                    edge_case_flags.append('INVALID_RNS_DATE')
                else:
                    # Check for future RNS creation date
                    if rns_creation_date_parsed > today:
                        days_ahead = (rns_creation_date_parsed - today).days
                        edge_tracker.add_edge_case(
                            'future_rns_creation_date',
                            company_name,
                            {'date_value': result['rns_creation_date'], 'days_ahead': days_ahead, 'cuit': cuit}
                        )
                        edge_case_flags.append('FUTURE_RNS_DATE')
                    
                    # Check for very old company
                    if rns_creation_date_parsed.year < 1900:
                        years_old = today.year - rns_creation_date_parsed.year
                        edge_tracker.add_edge_case(
                            'very_old_company',
                            company_name,
                            {'creation_date': result['rns_creation_date'], 'years_old': years_old, 'cuit': cuit}
                        )
                        edge_case_flags.append('VERY_OLD_COMPANY')
            
            if 'razon_social' in row:
                result['rns_razon_social'] = row['razon_social']
            if 'tipo_societario' in row:
                result['rns_tipo_societario'] = row['tipo_societario']
            if 'dom_legal_provincia' in row:
                result['rns_provincia'] = row['dom_legal_provincia']
            
            # Calculate timing if we have both dates
            if result['rns_creation_date'] and first_deal_date:
                timing = calculate_time_difference(result['rns_creation_date'], first_deal_date_str)
                
                if timing['days'] is not None:
                    # Check for negative time to close (CRITICAL)
                    if timing['days'] < 0:
                        edge_tracker.add_edge_case(
                            'negative_time_to_close',
                            company_name,
                            {
                                'rns_date': result['rns_creation_date'],
                                'first_deal_date': str(first_deal_date),
                                'days_diff': timing['days'],
                                'cuit': cuit
                            }
                        )
                        edge_case_flags.append('NEGATIVE_TIME_TO_CLOSE')
                    
                    # Check for very short time to close (< 1 day)
                    elif timing['days'] == 0:
                        edge_tracker.add_edge_case(
                            'very_short_time_to_close',
                            company_name,
                            {
                                'days': timing['days'],
                                'rns_date': result['rns_creation_date'],
                                'first_deal_date': str(first_deal_date),
                                'cuit': cuit
                            }
                        )
                        edge_case_flags.append('VERY_SHORT_TIME_TO_CLOSE')
                    
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
        first_deal_date_for_colppy = company.get('First deal closed won date', '').strip().strip('"')
        
        if first_deal_date_for_colppy:
            colppy_age = calculate_colppy_age(first_deal_date_for_colppy, churn_date_str)
            if colppy_age['days'] is not None:
                result['colppy_age_days'] = str(colppy_age['days'])
                result['colppy_age_months'] = str(colppy_age['months'])
                result['colppy_age_years'] = str(colppy_age['years'])
                result['colppy_age_formatted'] = colppy_age['formatted']
                result['is_churned'] = 'True' if colppy_age['is_churned'] else 'False'
        
        # Store edge case flags
        result['edge_case_flags'] = '; '.join(edge_case_flags) if edge_case_flags else ''
        
        results.append(result)
    
    if show_progress:
        print()  # New line after progress
    
    # Export results
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"../outputs/creation_to_close_analysis_with_edge_cases_{timestamp}.csv"
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = list(results[0].keys())
    
    print(f"\n💾 Exporting results...")
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    # Print edge case summary
    edge_tracker.print_summary()
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ Analysis Complete!")
    print(f"   Total companies: {len(companies)}")
    print(f"   Valid CUITs: {len(cuits_to_lookup)}")
    print(f"   CUITs found in RNS: {found_count} ({found_count/len(cuits_to_lookup)*100:.1f}%)")
    print(f"   Timing calculated: {timing_calculated} ({timing_calculated/len(cuits_to_lookup)*100:.1f}%)")
    print(f"\n📁 Results exported to: {output_path}")
    print("=" * 80)
    
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze time from company creation (RNS) to first Colppy deal close (HubSpot) WITH EDGE CASE DETECTION',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python analyze_creation_to_close_timing_v2_with_edge_cases.py --input hubspot-export.csv
  
  # Specify output file
  python analyze_creation_to_close_timing_v2_with_edge_cases.py --input hubspot-export.csv --output results.csv
  
  # Quiet mode (no progress updates)
  python analyze_creation_to_close_timing_v2_with_edge_cases.py --input hubspot-export.csv --quiet
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Input CSV file from HubSpot with CUIT and "First deal closed won date" columns'
    )
    parser.add_argument(
        '--output',
        help='Output CSV file (default: ../outputs/creation_to_close_analysis_with_edge_cases_TIMESTAMP.csv)'
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

