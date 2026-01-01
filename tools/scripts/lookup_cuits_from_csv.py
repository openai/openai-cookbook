#!/usr/bin/env python3
"""
Lookup CUIT creation dates from CSV file
Reads a CSV file with CUITs and searches them in the RNS dataset.
"""

import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd

# Import the RNS lookup service
try:
    from rns_dataset_lookup import RNSDatasetLookup
except ImportError:
    print("Error: Could not import rns_dataset_lookup module")
    print("Make sure rns_dataset_lookup.py is in the same directory")
    sys.exit(1)


def extract_cuits_from_csv(input_file: str, cuit_column: str = 'CUIT') -> list:
    """
    Extract CUITs from input CSV file
    
    Args:
        input_file: Path to input CSV file
        cuit_column: Name of the column containing CUITs
        
    Returns:
        List of dictionaries with CUIT and original row data
    """
    cuits_data = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # Find CUIT column (case-insensitive)
        fieldnames = reader.fieldnames
        cuit_col = None
        for col in fieldnames:
            if col.upper() == cuit_column.upper() or 'CUIT' in col.upper():
                cuit_col = col
                break
        
        if not cuit_col:
            raise ValueError(f"CUIT column not found. Available columns: {fieldnames}")
        
        for row in reader:
            cuit = row.get(cuit_col, '').strip()
            if cuit:
                # Normalize CUIT (remove dashes, spaces, dots)
                cuit_normalized = ''.join(filter(str.isdigit, cuit))
                if len(cuit_normalized) == 11:
                    cuits_data.append({
                        'cuit': cuit_normalized,
                        'cuit_original': cuit,
                        'original_row': row
                    })
    
    return cuits_data


def lookup_cuits_in_dataset(cuits_data: list, dataset_file: str = None) -> list:
    """
    Lookup CUITs in the RNS dataset
    
    Args:
        cuits_data: List of CUIT dictionaries
        dataset_file: Optional path to specific dataset file
        
    Returns:
        List of results with creation dates
    """
    lookup = RNSDatasetLookup()
    
    # Load dataset
    if dataset_file:
        print(f"Loading dataset: {dataset_file}")
        df = lookup.load_dataset(dataset_file)
    else:
        # Use the 202509 dataset we processed
        dataset_path = Path("rns_datasets/registro-nacional-sociedades-202509.csv")
        if not dataset_path.exists():
            # Try to extract from ZIP
            import zipfile
            zip_path = Path("rns_datasets/rns_2025_semestre_2.zip")
            if zip_path.exists():
                print("Extracting dataset from ZIP...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    if 'registro-nacional-sociedades-202509.csv' in zip_ref.namelist():
                        zip_ref.extract('registro-nacional-sociedades-202509.csv', 'rns_datasets/')
        
        print(f"Loading dataset: {dataset_path}")
        df = lookup.load_dataset(str(dataset_path))
    
    print(f"✓ Loaded {len(df):,} records")
    
    # Normalize CUIT column in dataset
    if 'cuit' not in df.columns:
        raise ValueError(f"CUIT column not found in dataset. Available: {list(df.columns)}")
    
    df_cuit_normalized = df['cuit'].astype(str).str.replace(r'[-\s\.]', '', regex=True)
    
    # Perform lookups
    results = []
    for i, item in enumerate(cuits_data, 1):
        cuit = item['cuit']
        matches = df[df_cuit_normalized == cuit]
        
        if not matches.empty:
            row = matches.iloc[0]
            creation_date = None
            if 'fecha_hora_contrato_social' in row and pd.notna(row['fecha_hora_contrato_social']):
                date_str = str(row['fecha_hora_contrato_social'])
                creation_date = lookup._parse_date(date_str)
            
            result = {
                'cuit': cuit,
                'cuit_original': item['cuit_original'],
                'found': True,
                'creation_date': creation_date or '',
                'razon_social_rns': row.get('razon_social', '') if 'razon_social' in row else '',
                'tipo_societario': row.get('tipo_societario', '') if 'tipo_societario' in row else '',
                'provincia': row.get('dom_legal_provincia', '') if 'dom_legal_provincia' in row else '',
                'original_row': item['original_row']
            }
        else:
            result = {
                'cuit': cuit,
                'cuit_original': item['cuit_original'],
                'found': False,
                'creation_date': '',
                'razon_social_rns': '',
                'tipo_societario': '',
                'provincia': '',
                'original_row': item['original_row']
            }
        
        results.append(result)
        
        if (i % 10 == 0) or (i == len(cuits_data)):
            status = "✓" if result['found'] else "✗"
            date_str = result['creation_date'] if result['creation_date'] else 'Not found'
            print(f"  {i}/{len(cuits_data)}: {cuit} {status} {date_str}")
    
    return results


def export_results(results: list, output_file: str = None):
    """
    Export results to CSV
    
    Args:
        results: List of lookup results
        output_file: Output file path (optional)
    """
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"../outputs/cuit_creation_dates_lookup_{timestamp}.csv"
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get all fieldnames from original rows + new fields
    fieldnames = ['cuit', 'cuit_original', 'found', 'creation_date', 'razon_social_rns', 'tipo_societario', 'provincia']
    
    # Add original columns (except CUIT which we already have)
    if results and results[0].get('original_row'):
        original_cols = set(results[0]['original_row'].keys())
        original_cols.discard('CUIT')  # Remove CUIT as we have cuit and cuit_original
        fieldnames.extend(sorted(original_cols))
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for result in results:
            row = {
                'cuit': result['cuit'],
                'cuit_original': result['cuit_original'],
                'found': result['found'],
                'creation_date': result['creation_date'],
                'razon_social_rns': result['razon_social_rns'],
                'tipo_societario': result['tipo_societario'],
                'provincia': result['provincia']
            }
            
            # Add original columns
            if result.get('original_row'):
                for col in result['original_row']:
                    if col.upper() != 'CUIT':
                        row[col] = result['original_row'][col]
            
            writer.writerow(row)
    
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description='Lookup CUIT creation dates from CSV file using RNS dataset',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python lookup_cuits_from_csv.py --input hubspot-crm-exports-contadores-sin-actividad-2025-12-29.csv
  
  # Specify output file
  python lookup_cuits_from_csv.py --input input.csv --output results.csv
  
  # Use specific dataset file
  python lookup_cuits_from_csv.py --input input.csv --dataset rns_datasets/registro-nacional-sociedades-202509.csv
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Input CSV file with CUITs'
    )
    parser.add_argument(
        '--output',
        help='Output CSV file (default: ../outputs/cuit_creation_dates_lookup_TIMESTAMP.csv)'
    )
    parser.add_argument(
        '--cuit-column',
        default='CUIT',
        help='Name of CUIT column in input CSV (default: CUIT)'
    )
    parser.add_argument(
        '--dataset',
        help='Path to specific RNS dataset file (default: uses 202509 dataset)'
    )
    
    args = parser.parse_args()
    
    # Check input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    print("=" * 70)
    print("CUIT Creation Date Lookup from CSV")
    print("=" * 70)
    print(f"\n📂 Input file: {args.input}")
    
    # Extract CUITs
    try:
        print(f"\n📋 Extracting CUITs from CSV...")
        cuits_data = extract_cuits_from_csv(args.input, args.cuit_column)
        print(f"✓ Found {len(cuits_data)} valid CUITs")
    except Exception as e:
        print(f"❌ Error extracting CUITs: {e}")
        return 1
    
    if not cuits_data:
        print("No valid CUITs found in file")
        return 1
    
    # Lookup in dataset
    try:
        print(f"\n🔍 Looking up CUITs in RNS dataset...")
        results = lookup_cuits_in_dataset(cuits_data, args.dataset)
    except Exception as e:
        print(f"❌ Error during lookup: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Export results
    try:
        output_path = export_results(results, args.output)
        
        # Summary
        found = sum(1 for r in results if r['found'])
        not_found = len(results) - found
        
        print("\n" + "=" * 70)
        print("✅ Lookup Complete!")
        print(f"   Total CUITs processed: {len(results)}")
        print(f"   Found: {found} ({found/len(results)*100:.1f}%)")
        print(f"   Not found: {not_found} ({not_found/len(results)*100:.1f}%)")
        print(f"\n📁 Results exported to: {output_path}")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ Error exporting results: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

