"""
Monthly closing analysis script for Colppy.
Compares New customers and Churn customers with HubSpot consistency.

This script processes:
1. New customers file (first new deal)
2. Churn customers file (should have fecha de baja)
3. Links them via Empresa_Id (maps to HubSpot id_empresa property)
4. Prepares data for HubSpot comparison

Usage:
    python analyze_monthly_closing.py \\
        --new-file "path/to/new_customers.csv" \\
        --churn-file "path/to/churn_customers.csv" \\
        --month 12 \\
        --year 2025 \\
        [--output-dir "path/to/output"]
"""

import pandas as pd
import numpy as np
import argparse
from datetime import datetime
from pathlib import Path


def load_and_process_new_customers(file_path: str) -> pd.DataFrame:
    """
    Load and process the New customers CSV file.
    
    Args:
        file_path: Path to the New customers CSV file
        
    Returns:
        DataFrame with processed new customer data
    """
    df = pd.read_csv(file_path)
    
    # Clean column names (remove spaces, special characters)
    df.columns = df.columns.str.strip()
    
    # Convert date columns
    date_columns = ['Inicio_Inicial', 'Fecha_Reintegro']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', format='%Y-%m-%d %H:%M:%S')
    
    # Convert numeric columns
    numeric_columns = ['New Total', 'New Sin Descuento', 'Beginning']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Add data source flag
    df['data_source'] = 'New Customers'
    
    return df


def load_and_process_churn_customers(file_path: str) -> pd.DataFrame:
    """
    Load and process the Churn customers CSV file.
    
    Args:
        file_path: Path to the Churn customers CSV file
        
    Returns:
        DataFrame with processed churn customer data
    """
    df = pd.read_csv(file_path)
    
    # Clean column names
    df.columns = df.columns.str.strip()
    
    # Handle the "1. Ending_Sin_Descuentos" column name
    if '1. Ending_Sin_Descuentos' in df.columns:
        df = df.rename(columns={'1. Ending_Sin_Descuentos': 'Ending_Sin_Descuentos'})
    
    # Convert date columns
    date_columns = ['promo_start_date_retencion']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', format='%Y-%m-%d %H:%M:%S')
    
    # Convert numeric columns
    numeric_columns = [
        'Churn Total', 'Churn Sin Descuento', 'Downsell Sin Descuento',
        'Churn Descuento', 'Descuento Retencion', 'Ending_Sin_Descuentos'
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Add data source flag
    df['data_source'] = 'Churn Customers'
    
    return df


def analyze_data_consistency(new_df: pd.DataFrame, churn_df: pd.DataFrame) -> dict:
    """
    Analyze consistency between New and Churn datasets.
    
    Args:
        new_df: DataFrame with new customers
        churn_df: DataFrame with churn customers
        
    Returns:
        Dictionary with analysis results
    """
    analysis = {}
    
    # Basic counts
    analysis['new_customers_count'] = len(new_df)
    analysis['churn_customers_count'] = len(churn_df)
    
    # Get unique Empresa_Id from both datasets
    new_ids = set(new_df['Empresa_Id'].astype(str))
    churn_ids = set(churn_df['Empresa_Id'].astype(str))
    
    # Find overlaps (companies that appear in both - shouldn't happen)
    overlap_ids = new_ids.intersection(churn_ids)
    analysis['overlap_count'] = len(overlap_ids)
    analysis['overlap_ids'] = sorted(list(overlap_ids))
    
    # Find companies only in new
    only_new = new_ids - churn_ids
    analysis['only_new_count'] = len(only_new)
    
    # Find companies only in churn
    only_churn = churn_ids - new_ids
    analysis['only_churn_count'] = len(only_churn)
    
    # Total unique companies
    all_ids = new_ids.union(churn_ids)
    analysis['total_unique_companies'] = len(all_ids)
    
    return analysis


def prepare_hubspot_comparison_data(new_df: pd.DataFrame, churn_df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare consolidated data for HubSpot comparison.
    
    Args:
        new_df: DataFrame with new customers
        churn_df: DataFrame with churn customers
        
    Returns:
        Consolidated DataFrame ready for HubSpot comparison
    """
    # Create a base dataframe with all unique Empresa_Id
    all_ids = set(new_df['Empresa_Id'].astype(str)) | set(churn_df['Empresa_Id'].astype(str))
    
    # Initialize consolidated dataframe
    consolidated = []
    
    # Process new customers
    for _, row in new_df.iterrows():
        consolidated.append({
            'Empresa_Id': str(row['Empresa_Id']),
            'id_empresa': str(row['Empresa_Id']),  # HubSpot property name
            'is_new_customer': True,
            'is_churn_customer': False,
            'New_Total': row.get('New Total', None),
            'New_Sin_Descuento': row.get('New Sin Descuento', None),
            'Beginning': row.get('Beginning', None),
            'Inicio_Inicial': row.get('Inicio_Inicial', None),
            'Fecha_Reintegro': row.get('Fecha_Reintegro', None),
            'Nuevo_Cliente': row.get('Nuevo Cliente ?', None),
            # Churn fields (will be None for new customers)
            'Churn_Total': None,
            'Churn_Sin_Descuento': None,
            'Downsell_Sin_Descuento': None,
            'Churn_Descuento': None,
            'Descuento_Retencion': None,
            'Ending_Sin_Descuentos': None,
            'promo_start_date_retencion': None,
        })
    
    # Process churn customers
    for _, row in churn_df.iterrows():
        empresa_id = str(row['Empresa_Id'])
        
        # Check if already exists (overlap case)
        existing = next((x for x in consolidated if x['Empresa_Id'] == empresa_id), None)
        
        if existing:
            # Update existing record (overlap - shouldn't happen but handle it)
            existing['is_churn_customer'] = True
            existing['Churn_Total'] = row.get('Churn Total', None)
            existing['Churn_Sin_Descuento'] = row.get('Churn Sin Descuento', None)
            existing['Downsell_Sin_Descuento'] = row.get('Downsell Sin Descuento', None)
            existing['Churn_Descuento'] = row.get('Churn Descuento', None)
            existing['Descuento_Retencion'] = row.get('Descuento Retencion', None)
            existing['Ending_Sin_Descuentos'] = row.get('Ending_Sin_Descuentos', None)
            existing['promo_start_date_retencion'] = row.get('promo_start_date_retencion', None)
        else:
            # New churn-only record
            consolidated.append({
                'Empresa_Id': empresa_id,
                'id_empresa': empresa_id,  # HubSpot property name
                'is_new_customer': False,
                'is_churn_customer': True,
                # New fields (will be None for churn-only customers)
                'New_Total': None,
                'New_Sin_Descuento': None,
                'Beginning': None,
                'Inicio_Inicial': None,
                'Fecha_Reintegro': None,
                'Nuevo_Cliente': None,
                # Churn fields
                'Churn_Total': row.get('Churn Total', None),
                'Churn_Sin_Descuento': row.get('Churn Sin Descuento', None),
                'Downsell_Sin_Descuento': row.get('Downsell Sin Descuento', None),
                'Churn_Descuento': row.get('Churn Descuento', None),
                'Descuento_Retencion': row.get('Descuento Retencion', None),
                'Ending_Sin_Descuentos': row.get('Ending_Sin_Descuentos', None),
                'promo_start_date_retencion': row.get('promo_start_date_retencion', None),
            })
    
    # Convert to DataFrame
    consolidated_df = pd.DataFrame(consolidated)
    
    # Add flags for HubSpot comparison
    consolidated_df['needs_hubspot_check'] = True
    consolidated_df['hubspot_company_churn_date'] = None  # To be filled from HubSpot
    consolidated_df['hubspot_first_deal_closed_won_date'] = None  # To be filled from HubSpot
    consolidated_df['hubspot_consistency_status'] = None  # To be filled after comparison
    
    return consolidated_df


def generate_summary_report(
    analysis: dict, 
    consolidated_df: pd.DataFrame, 
    month: int, 
    year: int,
    period_description: str = None
) -> str:
    """
    Generate a summary report of the analysis.
    
    Args:
        analysis: Dictionary with analysis results
        consolidated_df: Consolidated DataFrame
        month: Month number (1-12)
        year: Year number
        period_description: Optional custom period description
        
    Returns:
        Formatted summary report string
    """
    # Generate period description
    if period_description:
        period_str = period_description
    else:
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        period_str = f"{month_names[month - 1]} {year}"
    
    report = []
    report.append("=" * 80)
    report.append(f"{period_str.upper()} CLOSING ANALYSIS - SUMMARY REPORT")
    report.append("=" * 80)
    report.append("")
    
    # Basic Statistics
    report.append("📊 BASIC STATISTICS")
    report.append("-" * 80)
    report.append(f"New Customers Count: {analysis['new_customers_count']:,}")
    report.append(f"Churn Customers Count: {analysis['churn_customers_count']:,}")
    report.append(f"Total Unique Companies: {analysis['total_unique_companies']:,}")
    report.append("")
    
    # Overlap Analysis
    report.append("⚠️  OVERLAP ANALYSIS (Companies in Both Datasets)")
    report.append("-" * 80)
    report.append(f"Overlap Count: {analysis['overlap_count']}")
    if analysis['overlap_count'] > 0:
        report.append(f"⚠️  WARNING: {analysis['overlap_count']} companies appear in BOTH datasets!")
        report.append("   This shouldn't happen - a company cannot be both new and churned.")
        report.append(f"   Overlap IDs: {', '.join(analysis['overlap_ids'][:10])}")
        if len(analysis['overlap_ids']) > 10:
            report.append(f"   ... and {len(analysis['overlap_ids']) - 10} more")
    else:
        report.append("✅ No overlaps found - data is clean!")
    report.append("")
    
    # Dataset Coverage
    report.append("📈 DATASET COVERAGE")
    report.append("-" * 80)
    report.append(f"Only in New Customers: {analysis['only_new_count']:,}")
    report.append(f"Only in Churn Customers: {analysis['only_churn_count']:,}")
    report.append("")
    
    # Financial Summary
    report.append("💰 FINANCIAL SUMMARY")
    report.append("-" * 80)
    
    # New customers financials
    new_df = consolidated_df[consolidated_df['is_new_customer'] == True]
    if len(new_df) > 0:
        new_total_sum = new_df['New_Total'].sum()
        new_sin_descuento_sum = new_df['New_Sin_Descuento'].sum()
        report.append(f"New Customers Total Revenue: ${new_total_sum:,.2f}")
        report.append(f"New Customers (Sin Descuento): ${new_sin_descuento_sum:,.2f}")
    
    # Churn customers financials
    churn_df = consolidated_df[consolidated_df['is_churn_customer'] == True]
    if len(churn_df) > 0:
        churn_total_sum = abs(churn_df['Churn_Total'].sum())
        churn_sin_descuento_sum = abs(churn_df['Churn_Sin_Descuento'].sum())
        report.append(f"Churn Total Revenue Loss: ${churn_total_sum:,.2f}")
        report.append(f"Churn (Sin Descuento): ${churn_sin_descuento_sum:,.2f}")
    
    report.append("")
    
    # HubSpot Comparison Preparation
    report.append("🔗 HUBSPOT COMPARISON PREPARATION")
    report.append("-" * 80)
    report.append(f"Companies ready for HubSpot lookup: {len(consolidated_df):,}")
    report.append("")
    report.append("HubSpot Properties to Check:")
    report.append("  - id_empresa: Company identifier (maps from Empresa_Id)")
    report.append("  - company_churn_date: Fecha de baja (should exist for churn customers)")
    report.append("  - first_deal_closed_won_date: First deal closed won date")
    report.append("")
    report.append("Expected Behavior:")
    report.append(f"  - New customers: Should have first_deal_closed_won_date in {period_str}")
    report.append("  - Churn customers: Should have company_churn_date (fecha de baja)")
    report.append("")
    
    report.append("=" * 80)
    
    return "\n".join(report)


def parse_arguments():
    """
    Parse command-line arguments.
    
    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Monthly closing analysis for Colppy - Compare New and Churn customers with HubSpot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with required parameters
  python analyze_monthly_closing.py \\
      --new-file "outputs/New_Customers_December_2025.csv" \\
      --churn-file "outputs/Churn_Customers_December_2025.csv" \\
      --month 12 \\
      --year 2025

  # With custom output directory
  python analyze_monthly_closing.py \\
      --new-file "data/new.csv" \\
      --churn-file "data/churn.csv" \\
      --month 1 \\
      --year 2026 \\
      --output-dir "reports/january_2026"

  # With custom period description
  python analyze_monthly_closing.py \\
      --new-file "data/new.csv" \\
      --churn-file "data/churn.csv" \\
      --month 12 \\
      --year 2025 \\
      --period-description "Q4 2025 Closing"
        """
    )
    
    parser.add_argument(
        '--new-file',
        type=str,
        required=True,
        help='Path to the New customers CSV file'
    )
    
    parser.add_argument(
        '--churn-file',
        type=str,
        required=True,
        help='Path to the Churn customers CSV file'
    )
    
    parser.add_argument(
        '--month',
        type=int,
        required=True,
        choices=range(1, 13),
        metavar='[1-12]',
        help='Month number (1-12) for the analysis period'
    )
    
    parser.add_argument(
        '--year',
        type=int,
        required=True,
        help='Year number for the analysis period'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output directory for generated files (default: same directory as new-file)'
    )
    
    parser.add_argument(
        '--period-description',
        type=str,
        default=None,
        help='Custom period description for reports (e.g., "Q4 2025 Closing"). If not provided, uses month name and year.'
    )
    
    return parser.parse_args()


def validate_files(new_file_path: str, churn_file_path: str):
    """
    Validate that input files exist.
    
    Args:
        new_file_path: Path to new customers file
        churn_file_path: Path to churn customers file
        
    Raises:
        FileNotFoundError: If either file doesn't exist
    """
    new_path = Path(new_file_path)
    churn_path = Path(churn_file_path)
    
    if not new_path.exists():
        raise FileNotFoundError(f"New customers file not found: {new_file_path}")
    
    if not churn_path.exists():
        raise FileNotFoundError(f"Churn customers file not found: {churn_file_path}")


def generate_output_filename(prefix: str, month: int, year: int, suffix: str = "") -> str:
    """
    Generate standardized output filename.
    
    Args:
        prefix: Filename prefix
        month: Month number
        year: Year number
        suffix: Optional suffix before extension
        
    Returns:
        Generated filename string
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    month_str = f"{month:02d}"
    return f"{prefix}_{year}{month_str}_{timestamp}{suffix}"


def main():
    """Main execution function."""
    # Parse arguments
    args = parse_arguments()
    
    # Validate files exist
    validate_files(args.new_file, args.churn_file)
    
    # Determine output directory
    if args.output_dir:
        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        # Default to same directory as new-file
        output_path = Path(args.new_file).parent
    
    # Generate period description
    if args.period_description:
        period_description = args.period_description
    else:
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        period_description = f"{month_names[args.month - 1]} {args.year}"
    
    print("=" * 80)
    print(f"MONTHLY CLOSING ANALYSIS - {period_description.upper()}")
    print("=" * 80)
    print(f"New Customers File: {args.new_file}")
    print(f"Churn Customers File: {args.churn_file}")
    print(f"Output Directory: {output_path}")
    print("")
    
    print("🔄 Loading and processing data files...")
    
    # Load and process files
    new_df = load_and_process_new_customers(args.new_file)
    churn_df = load_and_process_churn_customers(args.churn_file)
    
    print(f"✅ Loaded {len(new_df):,} new customers")
    print(f"✅ Loaded {len(churn_df):,} churn customers")
    
    # Analyze consistency
    print("\n📊 Analyzing data consistency...")
    analysis = analyze_data_consistency(new_df, churn_df)
    
    # Prepare HubSpot comparison data
    print("🔗 Preparing HubSpot comparison data...")
    consolidated_df = prepare_hubspot_comparison_data(new_df, churn_df)
    
    # Generate summary report
    print("📝 Generating summary report...")
    report = generate_summary_report(
        analysis, 
        consolidated_df, 
        args.month, 
        args.year,
        args.period_description
    )
    
    # Print report
    print("\n" + report)
    
    # Generate output filenames
    consolidated_filename = generate_output_filename(
        "monthly_closing_consolidated", 
        args.month, 
        args.year
    ) + ".csv"
    
    summary_filename = generate_output_filename(
        "monthly_closing_summary", 
        args.month, 
        args.year
    ) + ".txt"
    
    # Save consolidated data for HubSpot comparison
    output_file = output_path / consolidated_filename
    consolidated_df.to_csv(output_file, index=False, encoding='utf-8')
    print(f"\n💾 Consolidated data saved to: {output_file}")
    
    # Save summary report
    report_file = output_path / summary_filename
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"💾 Summary report saved to: {report_file}")
    
    # Save overlap analysis if any
    if analysis['overlap_count'] > 0:
        overlap_df = consolidated_df[consolidated_df['Empresa_Id'].isin(analysis['overlap_ids'])]
        overlap_filename = generate_output_filename(
            "monthly_closing_overlaps", 
            args.month, 
            args.year
        ) + ".csv"
        overlap_file = output_path / overlap_filename
        overlap_df.to_csv(overlap_file, index=False, encoding='utf-8')
        print(f"⚠️  Overlap analysis saved to: {overlap_file}")
    
    print("\n✅ Analysis complete!")
    print(f"📊 Period analyzed: {period_description}")


if __name__ == "__main__":
    main()

