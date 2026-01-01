#!/usr/bin/env python3
"""
Analyze RNS dataset independently for TAM (Total Addressable Market) and PyME market analysis
Helps answer business plan questions about market size, segmentation, and trends
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from rns_dataset_lookup import RNSDatasetLookup

def parse_date(date_str):
    """Parse date string to datetime.date"""
    if not date_str or pd.isna(date_str):
        return None
    try:
        date_str = str(date_str).strip()
        if ' ' in date_str:
            date_str = date_str.split(' ')[0]
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return None

def analyze_rns_tam(dataset_dir=None, output_file=None):
    """
    Analyze RNS dataset for TAM and market insights
    
    Args:
        dataset_dir: Directory with RNS datasets (optional)
        output_file: Output CSV file path (optional)
    """
    print("=" * 80)
    print("RNS DATASET - TAM & MARKET ANALYSIS")
    print("=" * 80)
    print("\n🎯 Purpose: Analyze PyME market in Argentina for business plan")
    print("   - TAM (Total Addressable Market)")
    print("   - Market segmentation")
    print("   - Geographic distribution")
    print("   - Creation trends")
    print("   - Drivers for automation/onboarding")
    
    # Initialize lookup
    lookup = RNSDatasetLookup(dataset_dir=dataset_dir)
    
    # Check for datasets
    dataset_files = list(lookup.dataset_dir.glob('*.csv')) + list(lookup.dataset_dir.glob('*.zip'))
    if not dataset_files:
        print(f"\n❌ No RNS dataset files found in {lookup.dataset_dir}")
        print(f"   Please download datasets first")
        return None
    
    print(f"\n📂 Loading RNS datasets...")
    print(f"   Found {len(dataset_files)} dataset file(s)")
    
    # Load all datasets
    try:
        df = lookup.load_all_datasets()
        print(f"✓ Loaded {len(df):,} total company records")
    except Exception as e:
        print(f"❌ Error loading datasets: {e}")
        return None
    
    # Filter for PyMEs (exclude individuals and large enterprises)
    # PyMEs typically: SRL, SA, SAS, and other company types
    # Exclude: Personas físicas (CUITs starting with 20-27)
    print(f"\n🔍 Filtering for PyMEs (companies only)...")
    
    # Filter by CUIT prefix (companies start with 30, 33)
    if 'cuit' in df.columns:
        df['cuit_normalized'] = df['cuit'].astype(str).str.replace(r'[-\s\.]', '', regex=True)
        df['cuit_prefix'] = df['cuit_normalized'].str[:2]
        pyme_df = df[df['cuit_prefix'].isin(['30', '33'])].copy()
        print(f"   Companies (CUIT 30-XX or 33-XX): {len(pyme_df):,}")
    else:
        print("⚠️  CUIT column not found, using all records")
        pyme_df = df.copy()
    
    # Analyze by company type
    print(f"\n📊 MARKET SEGMENTATION ANALYSIS")
    print("=" * 80)
    
    # Company Type Distribution
    if 'tipo_societario' in pyme_df.columns:
        tipo_counts = pyme_df['tipo_societario'].value_counts()
        print(f"\n📋 COMPANY TYPE DISTRIBUTION (Top 15)")
        print("-" * 80)
        total_companies = len(pyme_df)
        for i, (tipo, count) in enumerate(tipo_counts.head(15).items(), 1):
            pct = (count / total_companies) * 100
            print(f"   {i:2d}. {tipo}: {count:,} ({pct:.2f}%)")
        
        # Focus on main PyME types
        pyme_types = [
            'SOCIEDAD DE RESPONSABILIDAD LIMITADA',
            'SOCIEDAD ANONIMA',
            'SOCIEDAD POR ACCION SIMPLIFICADA',
            'SOCIEDAD ANONIMA UNIPERSONAL'
        ]
        
        pyme_main = pyme_df[pyme_df['tipo_societario'].isin(pyme_types)]
        print(f"\n   🎯 Main PyME Types (SRL, SA, SAS, SAU): {len(pyme_main):,} ({len(pyme_main)/total_companies*100:.2f}%)")
    
    # Geographic Distribution
    if 'dom_legal_provincia' in pyme_df.columns:
        provincia_counts = pyme_df['dom_legal_provincia'].value_counts()
        print(f"\n🗺️  GEOGRAPHIC DISTRIBUTION (Top 15 Provinces)")
        print("-" * 80)
        for i, (provincia, count) in enumerate(provincia_counts.head(15).items(), 1):
            pct = (count / total_companies) * 100
            print(f"   {i:2d}. {provincia}: {count:,} ({pct:.2f}%)")
        
        # CABA + Buenos Aires concentration
        caba_ba = pyme_df[pyme_df['dom_legal_provincia'].isin([
            'CIUDAD AUTONOMA BUENOS AIRES', 
            'BUENOS AIRES'
        ])]
        if len(caba_ba) > 0:
            print(f"\n   🎯 CABA + Buenos Aires: {len(caba_ba):,} ({len(caba_ba)/total_companies*100:.2f}%)")
    
    # Sector/Industry Analysis
    if 'actividad_descripcion' in pyme_df.columns:
        print(f"\n🏭 SECTOR/INDUSTRY DISTRIBUTION (Top 15)")
        print("-" * 80)
        
        # Filter out null/empty descriptions
        actividades_df = pyme_df[pyme_df['actividad_descripcion'].notna() & 
                                 (pyme_df['actividad_descripcion'].astype(str).str.strip() != '')].copy()
        
        if len(actividades_df) > 0:
            actividad_counts = actividades_df['actividad_descripcion'].value_counts()
            
            for i, (actividad, count) in enumerate(actividad_counts.head(15).items(), 1):
                pct = (count / len(actividades_df)) * 100
                # Truncate long descriptions
                actividad_short = actividad[:70] + '...' if len(actividad) > 70 else actividad
                print(f"   {i:2d}. {actividad_short}: {count:,} ({pct:.2f}%)")
            
            print(f"\n   Total companies with activity description: {len(actividades_df):,}")
            
            # Also analyze by activity code (first 2 digits = main sector)
            if 'actividad_codigo' in actividades_df.columns:
                actividades_df['sector_code'] = actividades_df['actividad_codigo'].astype(str).str[:2]
                sector_counts = actividades_df['sector_code'].value_counts()
                
                print(f"\n   📊 TOP SECTORS BY CODE (First 2 digits of CIIU/NAICS)")
                print("-" * 80)
                for i, (sector_code, count) in enumerate(sector_counts.head(10).items(), 1):
                    pct = (count / len(actividades_df)) * 100
                    # Get most common description for this sector
                    sector_desc = actividades_df[actividades_df['sector_code'] == sector_code]['actividad_descripcion'].value_counts().index[0]
                    sector_desc_short = sector_desc[:50] + '...' if len(sector_desc) > 50 else sector_desc
                    print(f"   {i:2d}. Sector {sector_code}: {count:,} ({pct:.2f}%) - {sector_desc_short}")
        else:
            print("   ⚠️  No activity descriptions found in dataset")
    
    # Creation Date Analysis (Trends)
    date_column = None
    # Try to find date column (check various possible names)
    for col in pyme_df.columns:
        col_lower = str(col).lower()
        if 'fecha' in col_lower and 'contrato' in col_lower:
            date_column = col
            break
    
    # Fallback: any fecha column
    if not date_column:
        for col in pyme_df.columns:
            if 'fecha' in str(col).lower():
                date_column = col
                break
    
    if date_column:
        print(f"\n📅 COMPANY CREATION TRENDS")
        print("-" * 80)
        
        # Parse dates
        pyme_df['creation_date'] = pyme_df[date_column].apply(parse_date)
        pyme_df_with_dates = pyme_df[pyme_df['creation_date'].notna()].copy()
        
        if len(pyme_df_with_dates) > 0:
            # Extract year
            pyme_df_with_dates['creation_year'] = pyme_df_with_dates['creation_date'].apply(lambda x: x.year)
            
            # Count by year
            year_counts = pyme_df_with_dates['creation_year'].value_counts().sort_index()
            
            print(f"\n   Companies with valid creation dates: {len(pyme_df_with_dates):,}")
            print(f"   Date range: {year_counts.index.min()} - {year_counts.index.max()}")
            
            # Recent trends (last 10 years)
            current_year = datetime.now().year
            recent_years = [y for y in range(current_year - 10, current_year + 1) if y in year_counts.index]
            
            if recent_years:
                print(f"\n   📈 CREATION TREND (Last 10 Years)")
                for year in recent_years:
                    count = year_counts[year]
                    print(f"      {year}: {count:,} companies")
                
                # Calculate growth
                if len(recent_years) >= 2:
                    first_count = year_counts[recent_years[0]]
                    last_count = year_counts[recent_years[-1]]
                    if first_count > 0:
                        growth = ((last_count - first_count) / first_count) * 100
                        print(f"\n   📊 Growth ({recent_years[0]} → {recent_years[-1]}): {growth:+.1f}%")
            
            # Companies by age (for automation drivers)
            print(f"\n   🎯 COMPANIES BY AGE (as of {current_year})")
            pyme_df_with_dates['company_age'] = current_year - pyme_df_with_dates['creation_year']
            
            age_ranges = [
                (0, 1, "0-1 years (New companies)"),
                (1, 3, "1-3 years (Early stage)"),
                (3, 5, "3-5 years (Growing)"),
                (5, 10, "5-10 years (Established)"),
                (10, 20, "10-20 years (Mature)"),
                (20, float('inf'), "20+ years (Very mature)")
            ]
            
            for min_age, max_age, label in age_ranges:
                if max_age == float('inf'):
                    count = len(pyme_df_with_dates[pyme_df_with_dates['company_age'] >= min_age])
                else:
                    count = len(pyme_df_with_dates[
                        (pyme_df_with_dates['company_age'] >= min_age) & 
                        (pyme_df_with_dates['company_age'] < max_age)
                    ])
                pct = (count / len(pyme_df_with_dates)) * 100
                print(f"      {label}: {count:,} ({pct:.1f}%)")
    
    # Summary for Business Plan
    print(f"\n" + "=" * 80)
    print("📊 TAM SUMMARY FOR BUSINESS PLAN")
    print("=" * 80)
    
    print(f"\n✅ Total Addressable Market (TAM):")
    print(f"   - Total companies in RNS dataset: {len(pyme_df):,}")
    
    if 'tipo_societario' in pyme_df.columns and len(pyme_main) > 0:
        print(f"   - Main PyME types (SRL, SA, SAS, SAU): {len(pyme_main):,}")
    
    if 'dom_legal_provincia' in pyme_df.columns and len(caba_ba) > 0:
        print(f"   - CABA + Buenos Aires (primary market): {len(caba_ba):,}")
    
    print(f"\n✅ Market Segmentation:")
    if 'tipo_societario' in pyme_df.columns:
        print(f"   - SRL: {tipo_counts.get('SOCIEDAD DE RESPONSABILIDAD LIMITADA', 0):,}")
        print(f"   - SA: {tipo_counts.get('SOCIEDAD ANONIMA', 0):,}")
        print(f"   - SAS: {tipo_counts.get('SOCIEDAD POR ACCION SIMPLIFICADA', 0):,}")
    
    print(f"\n✅ Top Sectors/Industries:")
    if 'actividad_descripcion' in pyme_df.columns:
        actividades_df = pyme_df[pyme_df['actividad_descripcion'].notna() & 
                                 (pyme_df['actividad_descripcion'].astype(str).str.strip() != '')].copy()
        if len(actividades_df) > 0:
            actividad_counts = actividades_df['actividad_descripcion'].value_counts()
            for i, (actividad, count) in enumerate(actividad_counts.head(10).items(), 1):
                actividad_short = actividad[:60] + '...' if len(actividad) > 60 else actividad
                print(f"   {i:2d}. {actividad_short}: {count:,}")
    
    print(f"\n✅ Drivers for Automation & Onboarding:")
    if date_column and len(pyme_df_with_dates) > 0:
        new_companies = len(pyme_df_with_dates[pyme_df_with_dates['company_age'] <= 3])
        print(f"   - New/Early stage companies (0-3 years): {new_companies:,}")
        print(f"   - These companies need:")
        print(f"     • Digital onboarding")
        print(f"     • Automated data entry")
        print(f"     • Compliance management")
        print(f"     • Modern accounting solutions")
    
    print(f"\n✅ Why Argentina is Special:")
    print(f"   - Large PyME market: {len(pyme_df):,} companies")
    if 'dom_legal_provincia' in pyme_df.columns and len(caba_ba) > 0:
        concentration = (len(caba_ba) / len(pyme_df)) * 100
        print(f"   - High concentration in CABA+BA: {concentration:.1f}% (easier to reach)")
    if date_column and len(pyme_df_with_dates) > 0:
        recent = len(pyme_df_with_dates[pyme_df_with_dates['creation_year'] >= current_year - 5])
        print(f"   - {recent:,} companies created in last 5 years (growth opportunity)")
    
    # Export if requested
    if output_file:
        print(f"\n💾 Exporting summary to: {output_file}")
        summary_data = {
            'metric': [
                'Total Companies',
                'Main PyME Types (SRL+SA+SAS+SAU)',
                'CABA + Buenos Aires',
                'SRL',
                'SA',
                'SAS'
            ],
            'count': [
                len(pyme_df),
                len(pyme_main) if 'tipo_societario' in pyme_df.columns else 0,
                len(caba_ba) if 'dom_legal_provincia' in pyme_df.columns else 0,
                tipo_counts.get('SOCIEDAD DE RESPONSABILIDAD LIMITADA', 0) if 'tipo_societario' in pyme_df.columns else 0,
                tipo_counts.get('SOCIEDAD ANONIMA', 0) if 'tipo_societario' in pyme_df.columns else 0,
                tipo_counts.get('SOCIEDAD POR ACCION SIMPLIFICADA', 0) if 'tipo_societario' in pyme_df.columns else 0
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_csv(output_file, index=False)
        print(f"✓ Exported to: {output_file}")
    
    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 80)
    
    return pyme_df

def main():
    parser = argparse.ArgumentParser(
        description='Analyze RNS dataset for TAM and PyME market insights',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python analyze_rns_tam_market.py
  
  # With custom dataset directory
  python analyze_rns_tam_market.py --dataset-dir ./custom_rns_datasets
  
  # Export summary to CSV
  python analyze_rns_tam_market.py --output tam_summary.csv
        """
    )
    
    parser.add_argument(
        '--dataset-dir',
        help='Directory containing RNS dataset files (default: rns_datasets/)'
    )
    
    parser.add_argument(
        '--output',
        '-o',
        help='Output CSV file for summary statistics'
    )
    
    args = parser.parse_args()
    
    try:
        analyze_rns_tam(
            dataset_dir=args.dataset_dir,
            output_file=args.output
        )
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

