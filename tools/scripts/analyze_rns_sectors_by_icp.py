#!/usr/bin/env python3
"""
Analyze RNS sectors aligned with Colppy ICP criteria
Uses ICP characteristics to identify which sectors/industries best match Colppy's ideal customer profile
"""

import sys
import argparse
from pathlib import Path
from collections import Counter
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from rns_dataset_lookup import RNSDatasetLookup

# ICP Criteria from the presentation
ICP_CRITERIA = {
    'empresa': {
        'description': 'Empresas que compran o venden productos o servicios',
        'characteristics': [
            'Emite +20 compras y ventas mensuales',
            'Factura en promedio +$USD 100K anuales',
            'Requiere administración de punto de venta (opcional)',
            'Transforma materia prima en productos terminados (con integración S-Factory)'
        ],
        'exclusions': [
            'Empresas que hacen +18,000 comprobantes mensuales',
            'Micro empresas que emiten 10 o menos comprobantes mensuales'
        ]
    },
    'contador': {
        'description': 'Estudios contables y contadores independientes',
        'characteristics': [
            'Ofrecen tercerización de administración, contabilidad',
            'Liquidan impuestos y sueldos',
            'Tienen +20 clientes Fit-ICP Pyme',
            'Responsables del software con el que ofrecen servicios'
        ],
        'exclusions': [
            'Estudios con menos de 5 clientes FIT ICP Pyme'
        ]
    }
}

# Keywords that indicate ICP-fit sectors (based on ICP characteristics)
ICP_FIT_KEYWORDS = {
    'high_transaction_volume': [
        'comercio', 'venta', 'distribución', 'mayorista', 'minorista',
        'retail', 'wholesale', 'comercialización'
    ],
    'service_based': [
        'servicio', 'consultoría', 'asesoramiento', 'gestión',
        'administración', 'profesional'
    ],
    'manufacturing': [
        'fabricación', 'manufactura', 'producción', 'industrial',
        'transformación', 'elaboración'
    ],
    'construction': [
        'construcción', 'obra', 'edificación', 'reforma', 'reparación'
    ],
    'food_beverage': [
        'comida', 'bebida', 'gastronomía', 'restaurant', 'expendio',
        'alimentos', 'bebidas'
    ],
    'transport_logistics': [
        'transporte', 'logística', 'carga', 'distribución', 'flete'
    ],
    'real_estate': [
        'inmobiliario', 'inmobiliaria', 'propiedad', 'alquiler'
    ],
    'healthcare': [
        'salud', 'médico', 'farmacia', 'farmacéutico', 'hospital'
    ],
    'technology': [
        'informática', 'software', 'tecnología', 'sistemas', 'programa'
    ],
    'accounting_legal': [
        'contabilidad', 'impuesto', 'legal', 'jurídico', 'tributario'
    ]
}

def categorize_activity_by_icp(activity_desc):
    """Categorize activity description based on ICP fit keywords"""
    if not activity_desc or pd.isna(activity_desc):
        return None
    
    activity_lower = str(activity_desc).lower()
    categories = []
    
    for category, keywords in ICP_FIT_KEYWORDS.items():
        if any(kw in activity_lower for kw in keywords):
            categories.append(category)
    
    return categories if categories else ['other']

def analyze_sectors_by_icp(dataset_dir=None, output_file=None):
    """
    Analyze RNS sectors aligned with Colppy ICP
    """
    print("=" * 80)
    print("RNS SECTORS ANALYSIS - ALIGNED WITH COLPPY ICP")
    print("=" * 80)
    print("\n🎯 Purpose: Identify sectors that best match Colppy's ICP")
    print("\n📋 ICP Criteria:")
    print("   Empresa ICP:")
    for char in ICP_CRITERIA['empresa']['characteristics']:
        print(f"     • {char}")
    print("\n   Contador ICP:")
    for char in ICP_CRITERIA['contador']['characteristics']:
        print(f"     • {char}")
    
    # Initialize lookup
    lookup = RNSDatasetLookup(dataset_dir=dataset_dir)
    
    # Check for datasets
    dataset_files = list(lookup.dataset_dir.glob('*.csv')) + list(lookup.dataset_dir.glob('*.zip'))
    if not dataset_files:
        print(f"\n❌ No RNS dataset files found in {lookup.dataset_dir}")
        return None
    
    print(f"\n📂 Loading RNS datasets...")
    
    # Load all datasets
    try:
        df = lookup.load_all_datasets()
        print(f"✓ Loaded {len(df):,} total company records")
    except Exception as e:
        print(f"❌ Error loading datasets: {e}")
        return None
    
    # Filter for PyMEs (companies only)
    if 'cuit' in df.columns:
        df['cuit_normalized'] = df['cuit'].astype(str).str.replace(r'[-\s\.]', '', regex=True)
        df['cuit_prefix'] = df['cuit_normalized'].str[:2]
        pyme_df = df[df['cuit_prefix'].isin(['30', '33'])].copy()
        print(f"✓ Companies (CUIT 30-XX or 33-XX): {len(pyme_df):,}")
    else:
        pyme_df = df.copy()
    
    # Analyze by activity/sector
    if 'actividad_descripcion' not in pyme_df.columns:
        print("\n❌ No 'actividad_descripcion' column found in dataset")
        return None
    
    print(f"\n🔍 Analyzing sectors by ICP alignment...")
    
    # Filter companies with activity descriptions
    actividades_df = pyme_df[
        pyme_df['actividad_descripcion'].notna() & 
        (pyme_df['actividad_descripcion'].astype(str).str.strip() != '')
    ].copy()
    
    print(f"✓ Companies with activity description: {len(actividades_df):,}")
    
    # Categorize each activity by ICP fit
    actividades_df['icp_categories'] = actividades_df['actividad_descripcion'].apply(categorize_activity_by_icp)
    
    # Count by ICP category
    print(f"\n📊 SECTORS BY ICP CATEGORY")
    print("=" * 80)
    
    category_counts = Counter()
    for categories in actividades_df['icp_categories']:
        if categories:
            for cat in categories:
                category_counts[cat] += 1
    
    print(f"\n   ICP Category Distribution:")
    for category, count in category_counts.most_common():
        pct = (count / len(actividades_df)) * 100
        category_name = category.replace('_', ' ').title()
        print(f"   - {category_name}: {count:,} ({pct:.2f}%)")
    
    # Top activities by ICP category
    print(f"\n📈 TOP ACTIVITIES BY ICP CATEGORY")
    print("=" * 80)
    
    for category in category_counts.most_common(10):
        cat_name = category[0]
        print(f"\n   🎯 {cat_name.replace('_', ' ').title()}:")
        print("-" * 80)
        
        # Get activities in this category
        cat_activities = actividades_df[
            actividades_df['icp_categories'].apply(lambda x: cat_name in x if x else False)
        ]
        
        activity_counts = cat_activities['actividad_descripcion'].value_counts().head(10)
        
        for i, (actividad, count) in enumerate(activity_counts.items(), 1):
            actividad_short = actividad[:65] + '...' if len(actividad) > 65 else actividad
            pct = (count / len(cat_activities)) * 100
            print(f"      {i:2d}. {actividad_short}: {count:,} ({pct:.2f}%)")
    
    # Overall top activities (all companies)
    print(f"\n📊 TOP 15 ACTIVITIES (All Companies)")
    print("=" * 80)
    
    activity_counts = actividades_df['actividad_descripcion'].value_counts()
    for i, (actividad, count) in enumerate(activity_counts.head(15).items(), 1):
        actividad_short = actividad[:65] + '...' if len(actividad) > 65 else actividad
        pct = (count / len(actividades_df)) * 100
        
        # Check ICP fit
        categories = categorize_activity_by_icp(actividad)
        icp_fit = "✅ ICP-FIT" if categories and categories != ['other'] else "⚠️  Other"
        
        print(f"   {i:2d}. {actividad_short}: {count:,} ({pct:.2f}%) {icp_fit}")
    
    # Summary for Business Plan
    print(f"\n" + "=" * 80)
    print("📊 ICP-ALIGNED SECTORS SUMMARY")
    print("=" * 80)
    
    icp_fit_total = sum(count for cat, count in category_counts.items() if cat != 'other')
    print(f"\n✅ ICP-Fit Companies: {icp_fit_total:,} ({icp_fit_total/len(actividades_df)*100:.2f}%)")
    print(f"✅ Other Companies: {category_counts.get('other', 0):,} ({category_counts.get('other', 0)/len(actividades_df)*100:.2f}%)")
    
    print(f"\n✅ Top ICP-Fit Categories:")
    for category, count in category_counts.most_common(5):
        if category != 'other':
            category_name = category.replace('_', ' ').title()
            print(f"   - {category_name}: {count:,}")
    
    # Export if requested
    if output_file:
        print(f"\n💾 Exporting analysis to: {output_file}")
        summary_data = []
        
        for actividad, count in activity_counts.head(50).items():
            categories = categorize_activity_by_icp(actividad)
            summary_data.append({
                'actividad': actividad,
                'count': count,
                'percentage': (count / len(actividades_df)) * 100,
                'icp_categories': ', '.join(categories) if categories else 'other',
                'icp_fit': 'Yes' if categories and categories != ['other'] else 'No'
            })
        
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_csv(output_file, index=False, encoding='utf-8')
        print(f"✓ Exported to: {output_file}")
    
    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 80)
    
    return actividades_df

def main():
    parser = argparse.ArgumentParser(
        description='Analyze RNS sectors aligned with Colppy ICP criteria',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python analyze_rns_sectors_by_icp.py
  
  # Export results to CSV
  python analyze_rns_sectors_by_icp.py --output icp_sectors_analysis.csv
        """
    )
    
    parser.add_argument(
        '--dataset-dir',
        help='Directory containing RNS dataset files (default: rns_datasets/)'
    )
    
    parser.add_argument(
        '--output',
        '-o',
        help='Output CSV file for sector analysis'
    )
    
    args = parser.parse_args()
    
    try:
        analyze_sectors_by_icp(
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









