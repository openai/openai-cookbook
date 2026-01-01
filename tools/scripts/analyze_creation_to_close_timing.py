#!/usr/bin/env python3
"""
Analyze time from company creation to first Colppy deal close
Compares RNS creation dates with HubSpot first deal won dates
"""

import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import os

# Try to import HubSpot client
try:
    from hubspot_api.client import HubSpotClient
    HUBSPOT_AVAILABLE = True
except ImportError:
    HUBSPOT_AVAILABLE = False
    print("⚠️  HubSpot API not available. Will use deal IDs from CSV only.")


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
        # Parse dates
        if 'T' in creation_date:
            creation = datetime.fromisoformat(creation_date.replace('Z', '+00:00'))
            creation = creation.date()
        else:
            creation = datetime.strptime(creation_date, '%Y-%m-%d').date()
        
        if 'T' in close_date:
            close = datetime.fromisoformat(close_date.replace('Z', '+00:00'))
            close = close.date()
        else:
            close = datetime.strptime(close_date.split(' ')[0], '%Y-%m-%d').date()
        
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


def get_deal_close_date(deal_id: str, use_mcp: bool = True) -> str:
    """
    Get deal close date from HubSpot
    
    Args:
        deal_id: HubSpot deal ID
        use_mcp: Whether to use HubSpot MCP tools
        
    Returns:
        Close date string or None
    """
    if not deal_id:
        return None
    
    if use_mcp:
        try:
            # Use HubSpot MCP tool
            import subprocess
            import json
            
            # Call HubSpot MCP via Python (we'll handle this differently)
            # For now, return None and we'll fetch in batch
            return None
        except Exception as e:
            print(f"  ⚠️  Error fetching deal {deal_id}: {e}")
    
    return None


def fetch_deals_batch(deal_ids: list) -> dict:
    """
    Fetch multiple deals from HubSpot using MCP tools
    Returns dictionary mapping deal_id to close_date
    """
    if not deal_ids:
        return {}
    
    # This will be called externally via MCP tools
    # For now return empty dict
    return {}


def process_results(input_file: str, output_file: str = None, use_hubspot: bool = True, show_progress: bool = True):
    """
    Process CUIT lookup results and add creation-to-close timing analysis
    
    Args:
        input_file: Path to CUIT lookup results CSV
        output_file: Output file path (optional)
        use_hubspot: Whether to query HubSpot for deal close dates
    """
    print("=" * 70)
    print("Company Creation to Deal Close Timing Analysis")
    print("=" * 70)
    
    # Initialize HubSpot client if available
    hubspot_client = None
    if use_hubspot and HUBSPOT_AVAILABLE:
        try:
            hubspot_client = HubSpotClient()
            print("✓ HubSpot API connected")
        except Exception as e:
            print(f"⚠️  Could not connect to HubSpot: {e}")
            print("  Will use deal IDs from CSV only")
            hubspot_client = None
    
    # Read input file
    print(f"\n📂 Reading results from: {input_file}")
    results = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
    
    print(f"✓ Loaded {len(results)} records")
    
    # Process each result
    print(f"\n🔍 Analyzing creation-to-close timing...")
    print("=" * 70)
    
    processed_results = []
    found_count = 0
    with_deal_count = 0
    timing_calculated = 0
    total = len(results)
    
    for i, row in enumerate(results, 1):
        if show_progress:
            progress_pct = (i / total) * 100
            print(f"\r  Processing: {i}/{total} ({progress_pct:.1f}%)", end='', flush=True)
        cuit = row.get('cuit', '')
        company_name = row.get('Company name', 'N/A')
        found = row.get('found', 'False') == 'True'
        creation_date = row.get('creation_date', '')
        deal_id = row.get('Deal with Primary Company IDs', '').strip()
        
        # Initialize result row
        result_row = row.copy()
        result_row['deal_close_date'] = ''
        result_row['time_to_close_days'] = ''
        result_row['time_to_close_months'] = ''
        result_row['time_to_close_years'] = ''
        result_row['time_to_close_formatted'] = ''
        
        if found and creation_date:
            found_count += 1
            print(f"\n{i}. {company_name}")
            print(f"   CUIT: {cuit}")
            print(f"   📅 Creation Date: {creation_date}")
            
            # Try to get deal close date
            close_date = None
            
            if deal_id:
                with_deal_count += 1
                print(f"   🔗 Deal ID: {deal_id}")
                
                if hubspot_client:
                    print(f"   📡 Fetching deal close date from HubSpot...")
                    close_date = get_deal_close_date(deal_id, hubspot_client)
                else:
                    print(f"   ⚠️  HubSpot API not available - cannot fetch deal close date")
            
            if close_date:
                result_row['deal_close_date'] = close_date
                print(f"   ✅ Deal Close Date: {close_date}")
                
                # Calculate timing
                timing = calculate_time_difference(creation_date, close_date)
                result_row['time_to_close_days'] = str(timing['days']) if timing['days'] is not None else ''
                result_row['time_to_close_months'] = str(timing['months']) if timing['months'] is not None else ''
                result_row['time_to_close_years'] = str(timing['years']) if timing['years'] is not None else ''
                result_row['time_to_close_formatted'] = timing['formatted']
                
                timing_calculated += 1
                print(f"   ⏱️  Time to Close: {timing['formatted']}")
            else:
                print(f"   ⚠️  No deal close date available")
        
        processed_results.append(result_row)
    
    # Export results
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"../outputs/creation_to_close_timing_{timestamp}.csv"
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get all fieldnames
    fieldnames = list(processed_results[0].keys()) if processed_results else []
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed_results)
    
    # Summary
    print("\n" + "=" * 70)
    print("✅ Analysis Complete!")
    print(f"   Total records: {len(results)}")
    print(f"   Companies found in RNS: {found_count}")
    print(f"   Companies with deals: {with_deal_count}")
    print(f"   Timing calculated: {timing_calculated}")
    print(f"\n📁 Results exported to: {output_path}")
    print("=" * 70)
    
    # Show summary statistics
    if timing_calculated > 0:
        days_list = [int(r['time_to_close_days']) for r in processed_results 
                    if r.get('time_to_close_days') and r['time_to_close_days']]
        if days_list:
            avg_days = sum(days_list) / len(days_list)
            min_days = min(days_list)
            max_days = max(days_list)
            
            print(f"\n📊 Timing Statistics:")
            print(f"   Average: {avg_days:.0f} days ({avg_days/30.44:.1f} months)")
            print(f"   Minimum: {min_days} days ({min_days/30.44:.1f} months)")
            print(f"   Maximum: {max_days} days ({max_days/30.44:.1f} months)")
    
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze time from company creation to first Colppy deal close',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python analyze_creation_to_close_timing.py --input cuit_creation_dates_lookup_20251229_220104.csv
  
  # Without HubSpot API (use CSV data only)
  python analyze_creation_to_close_timing.py --input results.csv --no-hubspot
  
  # Specify output file
  python analyze_creation_to_close_timing.py --input results.csv --output timing_analysis.csv
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Input CSV file with CUIT lookup results'
    )
    parser.add_argument(
        '--output',
        help='Output CSV file (default: ../outputs/creation_to_close_timing_TIMESTAMP.csv)'
    )
    parser.add_argument(
        '--no-hubspot',
        action='store_true',
        help='Do not query HubSpot API (use CSV data only)'
    )
    
    args = parser.parse_args()
    
    # Check input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    try:
        output_path = process_results(
            args.input,
            args.output,
            use_hubspot=not args.no_hubspot
        )
        print(f"\n✓ Analysis complete. Results saved to: {output_path}")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

