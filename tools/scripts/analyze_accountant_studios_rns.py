#!/usr/bin/env python3
"""
Analyze RNS Dataset to Count Accountant Studios (Estudios Contables)

Identifies accountant studios based on multiple criteria:
1. Company name (razon_social) containing accountant-related keywords
2. Activity description (actividad_descripcion) containing accountant-related keywords
   - This is the PRIMARY field for industry identification
3. Activity description containing accounting activity codes (AFIP codes)
4. Company type (tipo_societario) - shown for reference

A company is identified as an accountant studio if it matches ANY of the criteria above.
The activity_descripcion field is the most reliable indicator of industry/activity type.
"""

import pandas as pd
import sys
from pathlib import Path
import re

# Accountant-related keywords for company names (case-insensitive)
ACCOUNTANT_KEYWORDS = [
    'estudio contable',
    'estudio de contadores',
    'estudio contador',
    'contador público',
    'contadores públicos',
    'asesor contable',
    'asesores contables',
    'consultor contable',
    'consultores contables',
    'servicios contables',
    'servicio contable',
    'contaduría',
    'contaduria',
    'contador',
    'contadores'
]

# Accountant-related activity keywords (case-insensitive)
ACCOUNTANT_ACTIVITY_KEYWORDS = [
    'contable',
    'contador',
    'contadores',
    'contaduría',
    'contaduria',
    'asesoría contable',
    'asesoria contable',
    'servicios contables',
    'servicio contable',
    'auditoría',
    'auditoria',
    'consultoría contable',
    'consultoria contable',
    'tributaria',
    'tributario',
    'impuestos',
    'impuesto',
    'fiscal',
    'societaria',
    'societario',
    # Liquidación de sueldos
    'liquidaci',
    'sueldo',
    'sueldos',
    'nómina',
    'nomina',
    'jornales',
    'jornal',
    'cargas sociales',
    'carga social',
    'convenio colectivo',
    'convenios colectivos',
    'remuneraci',
    'haberes',
    'haber'
]

# Accounting activity codes (common AFIP activity codes for accounting services)
ACCOUNTING_ACTIVITY_CODES = [
    '692200',  # Servicios de contabilidad, auditoría y asesoría fiscal
    '692201',  # Servicios de contabilidad
    '692202',  # Servicios de auditoría
    '692203',  # Servicios de asesoría fiscal
    '692204',  # Servicios de asesoría contable
    '692205',  # Servicios de asesoría tributaria
    '692206',  # Servicios de asesoría societaria
]

# Activity descriptions to EXCLUDE (too broad, not specifically accountant-related)
EXCLUDED_ACTIVITY_PATTERNS = [
    'gestión de depósitos fiscal',  # Not accountant-related - fiscal deposit management
    'gestión de depósitos',  # Variant - deposit management
    # Exclude activities that contain "fiscal" but are not accounting-related
    'depósito fiscal',
    'deposito fiscal',
    # Exclude agricultural activities that might match "contable" in other contexts
    'cultivo',
    'cría de ganado',
    'apicultura',
    # Exclude other non-accounting activities
    'alquiler de automóviles',
    'transporte automotor',
    'producción de filmes',
    'venta al por',
    'construcción',
    'edificios residenciales',
    'edificios no residenciales',
]
# Note: 'asesoramiento, dirección' and related patterns are INCLUDED as they could be
# accountant studios or business consultants, which are relevant for our analysis

def normalize_text(text):
    """Normalize text for comparison"""
    if pd.isna(text) or text == '':
        return ''
    return str(text).lower().strip()

def contains_accountant_keyword(text, keywords_list=ACCOUNTANT_KEYWORDS):
    """Check if text contains any accountant-related keyword"""
    normalized = normalize_text(text)
    if not normalized:
        return False
    
    # Check for exact matches or word boundaries
    for keyword in keywords_list:
        keyword_lower = keyword.lower()
        # Check if keyword appears as a word (not just substring)
        pattern = r'\b' + re.escape(keyword_lower) + r'\b'
        if re.search(pattern, normalized):
            return True
        # Also check as substring for compound words
        if keyword_lower in normalized:
            return True
    
    return False

def contains_accounting_activity_code(text):
    """Check if text contains accounting activity codes"""
    normalized = normalize_text(text)
    if not normalized:
        return False
    
    # Check for activity codes
    for code in ACCOUNTING_ACTIVITY_CODES:
        if code in normalized:
            return True
    
    return False

def should_exclude_activity(activity_text):
    """Check if activity should be excluded (too broad, not accountant-specific)"""
    if not activity_text or pd.isna(activity_text):
        return False
    
    normalized = normalize_text(activity_text)
    
    # Check against exclusion patterns
    for pattern in EXCLUDED_ACTIVITY_PATTERNS:
        if pattern.lower() in normalized:
            return True
    
    return False

def analyze_accountant_studios(dataset_path):
    """Analyze RNS dataset to count accountant studios"""
    
    print("=" * 80)
    print("ACCOUNTANT STUDIOS ANALYSIS - RNS DATASET")
    print("=" * 80)
    print()
    
    # Load dataset
    print(f"📂 Loading dataset: {dataset_path}")
    try:
        # Try to read with C engine first (faster, but requires low_memory=False)
        try:
            df = pd.read_csv(
                dataset_path,
                encoding='utf-8',
                low_memory=False,
                on_bad_lines='skip',
                engine='c'
            )
            print(f"✓ Loaded {len(df):,} records (using C engine)")
        except (TypeError, ValueError, Exception) as e1:
            # Fallback to python engine (slower but more forgiving)
            # Note: python engine doesn't support low_memory parameter
            df = pd.read_csv(
                dataset_path,
                encoding='utf-8',
                on_bad_lines='skip',
                engine='python',
                sep=',',
                quotechar='"'
            )
            print(f"✓ Loaded {len(df):,} records (using Python engine)")
    except Exception as e:
        print(f"❌ Error loading dataset: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Normalize column names
    df.columns = df.columns.str.lower().str.strip()
    
    # Find relevant columns
    razon_social_col = None
    tipo_societario_col = None
    actividades_col = None
    
    for col in df.columns:
        if 'razon_social' in col or 'denominacion' in col:
            razon_social_col = col
        if 'tipo_societario' in col or ('tipo' in col and 'societario' in col):
            tipo_societario_col = col
        # Prioritize actividad_descripcion (industry description field)
        if 'actividad_descripcion' in col:
            actividades_col = col
        elif ('actividades' in col or 'actividad' in col) and actividades_col is None:
            actividades_col = col
    
    print(f"\n📋 Dataset columns found:")
    print(f"   - Company name column: {razon_social_col or 'NOT FOUND'}")
    print(f"   - Company type column: {tipo_societario_col or 'NOT FOUND'}")
    print(f"   - Activity description column: {actividades_col or 'NOT FOUND'}")
    if actividades_col:
        # Show sample activity descriptions
        sample_activities = df[actividades_col].dropna().unique()[:5]
        print(f"   - Sample activities: {', '.join([str(a)[:40] for a in sample_activities])}")
    print()
    
    if not razon_social_col:
        print("❌ Could not find company name column (razon_social)")
        return
    
    # Filter for accountant studios based on multiple criteria
    print("🔍 Identifying accountant studios...")
    print("   Criteria:")
    print("   1. Company name (razon_social) contains accountant-related keywords")
    if actividades_col:
        print(f"   2. Activity description ({actividades_col}) contains accountant-related keywords")
        print(f"   3. Activity description ({actividades_col}) contains accounting activity codes")
    print()
    
    # Check company name
    df['match_by_name'] = df[razon_social_col].apply(contains_accountant_keyword, keywords_list=ACCOUNTANT_KEYWORDS)
    
    # Check activity description field if available
    df['match_by_activity'] = False
    df['match_by_activity_code'] = False
    
    if actividades_col:
        # First, mark activities that should be excluded
        df['excluded_activity'] = df[actividades_col].apply(should_exclude_activity)
        
        # Check for accountant keywords in activity descriptions
        # This is the primary field for industry identification
        # BUT exclude if it matches exclusion patterns
        df['match_by_activity'] = df.apply(
            lambda row: (
                not row['excluded_activity'] and 
                pd.notna(row[actividades_col]) and
                contains_accountant_keyword(row[actividades_col], keywords_list=ACCOUNTANT_ACTIVITY_KEYWORDS)
            ),
            axis=1
        )
        # Check for activity codes in activity descriptions
        # Also exclude if it matches exclusion patterns
        df['match_by_activity_code'] = df.apply(
            lambda row: (
                not row['excluded_activity'] and 
                pd.notna(row[actividades_col]) and
                contains_accounting_activity_code(row[actividades_col])
            ),
            axis=1
        )
    
    # Combine all criteria: match if ANY field indicates accountant studio
    df['is_accountant_studio'] = (
        df['match_by_name'] | 
        df['match_by_activity'] | 
        df['match_by_activity_code']
    )
    
    accountant_studios = df[df['is_accountant_studio'] == True].copy()
    
    # Count excluded activities
    excluded_count = df['excluded_activity'].sum() if 'excluded_activity' in df.columns else 0
    if excluded_count > 0:
        print(f"⚠️  Excluded {excluded_count:,} companies with non-accountant activity patterns")
        print()
    
    # Track match sources for analysis
    accountant_studios['match_source'] = accountant_studios.apply(
        lambda row: ', '.join([
            'Name' if row['match_by_name'] else '',
            'Activity' if row['match_by_activity'] else '',
            'Activity Code' if row['match_by_activity_code'] else ''
        ]).strip().replace('  ', ' ').replace(' ,', ',').strip(','),
        axis=1
    )
    
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    print(f"📊 Total companies in dataset: {len(df):,}")
    print(f"🏢 Accountant studios identified: {len(accountant_studios):,}")
    print(f"📈 Percentage: {(len(accountant_studios) / len(df) * 100):.2f}%")
    print()
    
    # Show breakdown by match source
    print("=" * 80)
    print("BREAKDOWN BY MATCH SOURCE")
    print("=" * 80)
    print()
    match_source_counts = accountant_studios['match_source'].value_counts()
    print(f"{'Match Source':<50} {'Count':<10} {'%':<10}")
    print("-" * 80)
    for source, count in match_source_counts.head(10).items():
        pct = (count / len(accountant_studios) * 100)
        print(f"{str(source)[:48]:<50} {count:<10} {pct:.2f}%")
    print()
    
    # Show detailed breakdown
    print("=" * 80)
    print("DETAILED BREAKDOWN")
    print("=" * 80)
    print()
    match_by_name_count = accountant_studios['match_by_name'].sum()
    match_by_activity_count = accountant_studios['match_by_activity'].sum() if actividades_col else 0
    match_by_activity_code_count = accountant_studios['match_by_activity_code'].sum() if actividades_col else 0
    
    print(f"   Matched by company name: {match_by_name_count:,} ({(match_by_name_count / len(accountant_studios) * 100):.1f}%)")
    if actividades_col:
        print(f"   Matched by activity description keywords: {match_by_activity_count:,} ({(match_by_activity_count / len(accountant_studios) * 100):.1f}%)")
        print(f"   Matched by activity codes: {match_by_activity_code_count:,} ({(match_by_activity_code_count / len(accountant_studios) * 100):.1f}%)")
        print()
        print(f"   Note: Activity description field ({actividades_col}) is the primary field for industry identification")
    print()
    
    # Show breakdown by company type if available
    if tipo_societario_col:
        print("=" * 80)
        print("BREAKDOWN BY COMPANY TYPE")
        print("=" * 80)
        print()
        type_counts = accountant_studios[tipo_societario_col].value_counts()
        print(f"{'Company Type':<50} {'Count':<10} {'%':<10}")
        print("-" * 80)
        for company_type, count in type_counts.head(15).items():
            pct = (count / len(accountant_studios) * 100)
            print(f"{str(company_type)[:48]:<50} {count:<10} {pct:.2f}%")
        print()
    
    # Show list of ALL unique activity descriptions that matched
    print("=" * 80)
    print("ALL UNIQUE ACTIVITY DESCRIPTIONS THAT MATCHED")
    print("=" * 80)
    print()
    print("Review this list to identify activities that should be excluded:")
    print()
    
    if actividades_col:
        # Get all unique activity descriptions from matched accountant studios
        matched_activities = accountant_studios[actividades_col].dropna().unique()
        matched_activities = sorted([str(a) for a in matched_activities])
        
        print(f"Total unique activity descriptions: {len(matched_activities)}")
        print()
        print(f"{'#':<5} {'Activity Description':<80}")
        print("-" * 80)
        for idx, activity in enumerate(matched_activities, 1):
            print(f"{idx:<5} {activity[:78]}")
        print()
        print("=" * 80)
        print()
    
    # Show detailed matching examples with activity strings for verification
    print("=" * 80)
    print("DETAILED MATCHING EXAMPLES - VERIFICATION (First 100)")
    print("=" * 80)
    print()
    print("Showing exactly which activity description strings matched and why:")
    print("(Showing 100 examples to verify if filters need adjustment)")
    print()
    
    sample = accountant_studios.head(100)
    for idx, (_, row) in enumerate(sample.iterrows(), 1):
        name = str(row[razon_social_col])[:70]
        company_type = str(row[tipo_societario_col])[:30] if tipo_societario_col and pd.notna(row.get(tipo_societario_col)) else 'N/A'
        match_source = str(row['match_source'])
        
        print(f"{'='*80}")
        print(f"Example {idx}: {name}")
        print(f"{'='*80}")
        print(f"Company Type: {company_type}")
        print(f"Match Source: {match_source}")
        print()
        
        # Show what matched in company name
        if row['match_by_name']:
            name_text = str(row[razon_social_col])
            matched_keywords = []
            for keyword in ACCOUNTANT_KEYWORDS:
                if keyword.lower() in name_text.lower():
                    matched_keywords.append(keyword)
            if matched_keywords:
                print(f"✓ MATCHED BY COMPANY NAME")
                print(f"  Company Name: {name_text}")
                print(f"  Matched Keywords: {', '.join(matched_keywords[:5])}")
                print()
        
        # Show what matched in activity description - FULL TEXT
        if actividades_col and pd.notna(row.get(actividades_col)):
            activity_text = str(row[actividades_col])
            print(f"ACTIVITY DESCRIPTION (FULL TEXT):")
            print(f"  {activity_text}")
            print()
            
            if row['match_by_activity']:
                matched_activity_keywords = []
                for keyword in ACCOUNTANT_ACTIVITY_KEYWORDS:
                    if keyword.lower() in activity_text.lower():
                        matched_activity_keywords.append(keyword)
                if matched_activity_keywords:
                    print(f"✓ MATCHED BY ACTIVITY KEYWORDS")
                    print(f"  Matched Keywords: {', '.join(matched_activity_keywords[:5])}")
                    print()
            
            if row['match_by_activity_code']:
                matched_codes = []
                for code in ACCOUNTING_ACTIVITY_CODES:
                    if code in activity_text:
                        matched_codes.append(code)
                if matched_codes:
                    print(f"✓ MATCHED BY ACTIVITY CODE")
                    print(f"  Matched Codes: {', '.join(matched_codes)}")
                    print()
        else:
            print(f"ACTIVITY DESCRIPTION: N/A (field not found or empty)")
            print()
        
        print()
    
    if len(accountant_studios) > 100:
        print(f"{'='*80}")
        print(f"Total accountant studios found: {len(accountant_studios):,}")
        print(f"Showing first 100 examples above. {len(accountant_studios) - 100:,} more in dataset.")
        print(f"{'='*80}")
        print()
    else:
        print(f"{'='*80}")
        print(f"Total accountant studios found: {len(accountant_studios):,}")
        print(f"All examples shown above.")
        print(f"{'='*80}")
        print()
    
    # Geographic Distribution Analysis
    print("=" * 80)
    print("GEOGRAPHIC DISTRIBUTION - ESTUDIOS CONTABLES")
    print("=" * 80)
    print()
    
    provincia_col = None
    for col in df.columns:
        if 'dom_legal_provincia' in col or ('provincia' in col and 'legal' in col):
            provincia_col = col
            break
    
    if provincia_col and provincia_col in accountant_studios.columns:
        provincia_counts = accountant_studios[provincia_col].value_counts()
        print(f"🗺️  DISTRIBUTION BY PROVINCE (Top 20)")
        print("-" * 80)
        print(f"{'Province':<50} {'Count':<10} {'%':<10}")
        print("-" * 80)
        
        for i, (provincia, count) in enumerate(provincia_counts.head(20).items(), 1):
            pct = (count / len(accountant_studios)) * 100
            provincia_str = str(provincia)[:48] if pd.notna(provincia) else 'N/A'
            print(f"{i:2d}. {provincia_str:<48} {count:<10} {pct:.2f}%")
        
        # CABA + Buenos Aires concentration
        caba_ba = accountant_studios[
            accountant_studios[provincia_col].isin([
                'CIUDAD AUTONOMA BUENOS AIRES', 
                'BUENOS AIRES'
            ])
        ]
        if len(caba_ba) > 0:
            print()
            print(f"🎯 CABA + Buenos Aires: {len(caba_ba):,} ({len(caba_ba)/len(accountant_studios)*100:.2f}%)")
        
        # Other provinces
        other_provinces = len(accountant_studios) - len(caba_ba)
        print(f"   Other provinces: {other_provinces:,} ({(other_provinces/len(accountant_studios)*100):.2f}%)")
        print()
    
    # Activity Description Analysis
    if actividades_col:
        print("=" * 80)
        print("ACTIVITY DESCRIPTION ANALYSIS")
        print("=" * 80)
        print()
        
        activity_counts = accountant_studios[actividades_col].value_counts()
        print(f"📋 TOP 20 ACTIVITY DESCRIPTIONS")
        print("-" * 80)
        for i, (actividad, count) in enumerate(activity_counts.head(20).items(), 1):
            actividad_short = str(actividad)[:70] + '...' if len(str(actividad)) > 70 else str(actividad)
            pct = (count / len(accountant_studios)) * 100
            print(f"   {i:2d}. {actividad_short}: {count:,} ({pct:.2f}%)")
        print()
    
    # Creation Date Analysis (if available)
    date_col = None
    for col in df.columns:
        if 'fecha' in col.lower() and 'contrato' in col.lower():
            date_col = col
            break
    
    if date_col and date_col in accountant_studios.columns:
        print("=" * 80)
        print("CREATION TREND ANALYSIS")
        print("=" * 80)
        print()
        
        # Parse dates
        def parse_date_safe(date_str):
            if pd.isna(date_str) or not date_str:
                return None
            try:
                date_str = str(date_str).strip()
                if ' ' in date_str:
                    date_str = date_str.split(' ')[0]
                from datetime import datetime
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                return None
        
        accountant_studios['creation_date'] = accountant_studios[date_col].apply(parse_date_safe)
        studios_with_dates = accountant_studios[accountant_studios['creation_date'].notna()].copy()
        
        if len(studios_with_dates) > 0:
            studios_with_dates['creation_year'] = studios_with_dates['creation_date'].apply(lambda x: x.year)
            year_counts = studios_with_dates['creation_year'].value_counts().sort_index()
            
            print(f"📅 Companies with valid creation dates: {len(studios_with_dates):,}")
            print(f"   Date range: {year_counts.index.min()} - {year_counts.index.max()}")
            
            # Recent trends (last 10 years)
            current_year = 2025
            recent_years = [y for y in range(current_year - 10, current_year + 1) if y in year_counts.index]
            
            if recent_years:
                print(f"\n   📈 CREATION TREND (Last 10 Years)")
                for year in recent_years:
                    count = year_counts[year]
                    print(f"      {year}: {count:,} estudios contables")
            
            # Age distribution
            studios_with_dates['age'] = current_year - studios_with_dates['creation_year']
            print(f"\n   🎯 AGE DISTRIBUTION (as of {current_year})")
            age_ranges = [
                (0, 5, "0-5 years (New)"),
                (5, 10, "5-10 years"),
                (10, 20, "10-20 years"),
                (20, 30, "20-30 years"),
                (30, float('inf'), "30+ years (Established)")
            ]
            
            for min_age, max_age, label in age_ranges:
                if max_age == float('inf'):
                    count = len(studios_with_dates[studios_with_dates['age'] >= min_age])
                else:
                    count = len(studios_with_dates[
                        (studios_with_dates['age'] >= min_age) & 
                        (studios_with_dates['age'] < max_age)
                    ])
                pct = (count / len(studios_with_dates)) * 100
                print(f"      {label}: {count:,} ({pct:.1f}%)")
        print()
    
    # Summary Insights
    print("=" * 80)
    print("KEY INSIGHTS - ESTUDIOS CONTABLES")
    print("=" * 80)
    print()
    
    print(f"✅ Market Size:")
    print(f"   - Total estudios contables en Argentina: {len(accountant_studios):,}")
    print(f"   - Representan {len(accountant_studios)/len(df)*100:.2f}% del total de empresas en RNS")
    
    if provincia_col and provincia_col in accountant_studios.columns:
        caba_ba_count = len(caba_ba) if 'caba_ba' in locals() else 0
        if caba_ba_count > 0:
            print(f"\n✅ Geographic Concentration:")
            print(f"   - CABA + Buenos Aires: {caba_ba_count:,} ({caba_ba_count/len(accountant_studios)*100:.2f}%)")
            print(f"   - Alta concentración geográfica facilita el alcance")
    
    if tipo_societario_col:
        top_type = accountant_studios[tipo_societario_col].value_counts().index[0]
        top_count = accountant_studios[tipo_societario_col].value_counts().iloc[0]
        print(f"\n✅ Company Structure:")
        print(f"   - Tipo más común: {top_type} ({top_count:,} - {top_count/len(accountant_studios)*100:.2f}%)")
    
    if actividades_col:
        top_activity = accountant_studios[actividades_col].value_counts().index[0]
        top_activity_count = accountant_studios[actividades_col].value_counts().iloc[0]
        print(f"\n✅ Primary Activity:")
        print(f"   - Actividad más común: {str(top_activity)[:60]}")
        print(f"   - {top_activity_count:,} estudios ({top_activity_count/len(accountant_studios)*100:.2f}%)")
    
    print(f"\n✅ Match Quality:")
    print(f"   - Matched by activity description: {match_by_activity_count:,} ({match_by_activity_count/len(accountant_studios)*100:.1f}%)")
    print(f"   - Matched by company name: {match_by_name_count:,} ({match_by_name_count/len(accountant_studios)*100:.1f}%)")
    print(f"   - High confidence matches (both name and activity): {len(accountant_studios[accountant_studios['match_by_name'] & accountant_studios['match_by_activity']]):,}")
    
    # Export results
    output_file = Path("tools/outputs/accountant_studios_rns_analysis.csv")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Select relevant columns for export
    export_cols = [razon_social_col, 'match_source', 'match_by_name']
    if tipo_societario_col:
        export_cols.append(tipo_societario_col)
    if actividades_col:
        export_cols.append(actividades_col)
        export_cols.append('match_by_activity')
        export_cols.append('match_by_activity_code')
    if 'cuit' in df.columns:
        export_cols.append('cuit')
    if provincia_col:
        export_cols.append(provincia_col)
    if date_col and date_col in accountant_studios.columns:
        export_cols.append(date_col)
        if 'creation_date' in accountant_studios.columns:
            export_cols.append('creation_date')
        if 'creation_year' in accountant_studios.columns:
            export_cols.append('creation_year')
    
    accountant_studios[export_cols].to_csv(output_file, index=False, encoding='utf-8')
    print(f"\n💾 Results exported to: {output_file}")
    print()
    
    return len(accountant_studios)

if __name__ == "__main__":
    import os
    # Get script directory
    script_dir = Path(__file__).parent.absolute()
    
    # Try to find the dataset
    dataset_paths = [
        script_dir / "rns_datasets/registro-nacional-sociedades-202509.csv",
        script_dir / "registro-nacional-sociedades-202509.csv",
        script_dir.parent / "scripts/rns_datasets/registro-nacional-sociedades-202509.csv"
    ]
    
    dataset_path = None
    for path in dataset_paths:
        if path.exists():
            dataset_path = str(path)
            break
    
    if not dataset_path:
        print("❌ Could not find RNS dataset file")
        print("   Looking for: registro-nacional-sociedades-202509.csv")
        print("   Tried paths:")
        for path in dataset_paths:
            exists = "✓" if path.exists() else "✗"
            print(f"     {exists} {path}")
        sys.exit(1)
    
    count = analyze_accountant_studios(dataset_path)
    
    if count:
        print("=" * 80)
        print("✅ ANALYSIS COMPLETE")
        print("=" * 80)
        print(f"\n🎯 Total Accountant Studios in RNS Dataset: {count:,}")
        print()

