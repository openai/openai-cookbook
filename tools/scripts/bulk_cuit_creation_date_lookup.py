#!/usr/bin/env python3
"""
Bulk CUIT Creation Date Lookup
Processes a list of CUITs from a CSV file and retrieves creation dates.

Usage:
    python bulk_cuit_creation_date_lookup.py --input cuits.csv --output results.csv

Input CSV format:
    cuit
    30712293841
    20123456789
    ...

Or with additional columns (will be preserved):
    cuit,company_name,other_field
    30712293841,Company A,value1
    20123456789,Company B,value2
"""

import os
import sys
import csv
import argparse
from typing import List, Dict
from datetime import datetime

# Import the lookup service
try:
    from cuit_creation_date_lookup import CUITCreationDateLookup, CreationDateResult
except ImportError:
    print("Error: Could not import cuit_creation_date_lookup module")
    print("Make sure cuit_creation_date_lookup.py is in the same directory")
    sys.exit(1)


def read_cuits_from_csv(filename: str) -> List[Dict]:
    """
    Read CUITs from CSV file
    
    Args:
        filename: Path to CSV file
        
    Returns:
        List of dictionaries with CUIT and any other columns
    """
    cuits = []
    
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # Check if 'cuit' column exists
        if 'cuit' not in reader.fieldnames:
            # Try common variations
            cuit_col = None
            for col in reader.fieldnames:
                if col.lower() in ['cuit', 'cuit_numero', 'tax_id', 'taxid']:
                    cuit_col = col
                    break
            
            if not cuit_col:
                raise ValueError("CSV file must contain a 'cuit' column (or similar)")
        else:
            cuit_col = 'cuit'
        
        for row in reader:
            cuit = row.get(cuit_col, '').strip()
            if cuit:
                # Preserve all original columns
                cuits.append({
                    'cuit': cuit,
                    'original_row': row
                })
    
    return cuits


def write_results_to_csv(results: Dict[str, CreationDateResult], 
                        original_data: List[Dict],
                        output_filename: str):
    """
    Write results to CSV, preserving original columns
    
    Args:
        results: Dictionary of lookup results
        original_data: Original data from input CSV
        output_filename: Output CSV filename
    """
    os.makedirs('../outputs', exist_ok=True)
    filepath = os.path.join('../outputs', output_filename)
    
    # Determine all fieldnames
    fieldnames = ['cuit', 'creation_date', 'source', 'razon_social', 'error', 'error_message']
    
    # Add original columns (except cuit which we already have)
    if original_data:
        original_cols = set(original_data[0]['original_row'].keys())
        original_cols.discard('cuit')
        fieldnames.extend(sorted(original_cols))
    
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in original_data:
            cuit = item['cuit']
            result = results.get(cuit, None)
            
            row = {
                'cuit': cuit,
                'creation_date': result.creation_date if result else '',
                'source': result.source if result else '',
                'razon_social': result.razon_social if result else '',
                'error': result.error if result else True,
                'error_message': result.error_message if result else 'Not processed'
            }
            
            # Add original columns
            for col in item['original_row']:
                if col != 'cuit':
                    row[col] = item['original_row'][col]
            
            writer.writerow(row)
    
    print(f"\n✓ Results exported to: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(
        description='Bulk lookup creation dates for CUITs from CSV file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python bulk_cuit_creation_date_lookup.py --input cuits.csv
  
  # Specify output file
  python bulk_cuit_creation_date_lookup.py --input cuits.csv --output results.csv
  
  # Disable Playwright (faster but may miss some data)
  python bulk_cuit_creation_date_lookup.py --input cuits.csv --no-playwright
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Input CSV file with CUITs (must have "cuit" column)'
    )
    parser.add_argument(
        '--output',
        help='Output CSV filename (default: cuit_creation_dates_TIMESTAMP.csv)'
    )
    parser.add_argument(
        '--no-playwright',
        action='store_true',
        help='Disable Playwright (use requests only, may not work for all sites)'
    )
    parser.add_argument(
        '--no-afip',
        action='store_true',
        help='Disable AFIP service (skip company name lookup)'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=2.0,
        help='Seconds between requests (default: 2.0)'
    )
    
    args = parser.parse_args()
    
    # Check input file exists
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return
    
    # Read CUITs from CSV
    print(f"Reading CUITs from: {args.input}")
    try:
        cuits_data = read_cuits_from_csv(args.input)
        print(f"Found {len(cuits_data)} CUITs to process")
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return
    
    if not cuits_data:
        print("No CUITs found in file")
        return
    
    # Initialize lookup service
    print("\nInitializing lookup service...")
    service = CUITCreationDateLookup(
        use_playwright=not args.no_playwright,
        use_afip=not args.no_afip
    )
    service.min_request_interval = args.rate_limit
    
    # Perform bulk lookup
    print("\nStarting bulk lookup...")
    cuits_list = [item['cuit'] for item in cuits_data]
    results = service.bulk_lookup(cuits_list)
    
    # Generate output filename if not provided
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"cuit_creation_dates_{timestamp}.csv"
    
    # Write results
    write_results_to_csv(results, cuits_data, args.output)
    
    # Print summary
    successful = sum(1 for r in results.values() if r.creation_date)
    failed = len(results) - successful
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Total CUITs processed: {len(results)}")
    print(f"  Successfully found: {successful}")
    print(f"  Not found: {failed}")
    print(f"  Success rate: {successful/len(results)*100:.1f}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()











