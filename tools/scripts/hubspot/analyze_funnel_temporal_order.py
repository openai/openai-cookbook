#!/usr/bin/env python3
"""
Analyze Funnel Temporal Order
==============================
Analyzes the conversion funnel to understand if stages are strictly sequential in time
and what fields determine the temporal order.
"""

import pandas as pd
import sys
import os
import argparse

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def analyze_funnel_temporal_order(csv_file):
    """Analyze if funnel stages are sequential in time"""
    print("=" * 100)
    print("ANÁLISIS DE ORDEN TEMPORAL DEL EMBUDO DE CONVERSIÓN")
    print("=" * 100)
    
    df = pd.read_csv(csv_file)
    
    print(f"\n📊 Total contactos analizados: {len(df)}")
    
    # Fields used for temporal analysis
    print("\n" + "=" * 100)
    print("CAMPOS UTILIZADOS PARA ORDEN TEMPORAL")
    print("=" * 100)
    
    print("\n1. CREACIÓN DEL CONTACTO:")
    print("   Campo: `createdate`")
    print("   Descripción: Fecha de creación del contacto en HubSpot")
    print("   Uso: Punto de referencia inicial para todos los cálculos temporales")
    
    print("\n2. CONTACTO (Contacted):")
    print("   Campos evaluados (en orden de prioridad):")
    print("   a) `hs_first_outreach_date` - Primera fecha de outreach")
    print("   b) `hs_sa_first_engagement_date` - Primera fecha de engagement")
    print("   c) `last_lead_status_date` - Última fecha de cambio de Lead Status")
    print("   Condición: Solo si `hs_lead_status` != 'new-stage-id' o '938333957'")
    print("   Resultado: `contact_date` (la primera fecha disponible según prioridad)")
    print("   Cálculo: `days_to_contact = contact_date - createdate`")
    
    print("\n3. SQL (Sales Qualified Lead):")
    print("   Campo: `hs_v2_date_entered_opportunity`")
    print("   Descripción: Fecha en que el contacto entró a la etapa 'opportunity'")
    print("   Condición: Campo debe estar poblado (no null)")
    print("   Resultado: `sql_date`")
    
    print("\n4. PQL (Product Qualified Lead):")
    print("   Campos: `activo` = 'true' AND `fecha_activo` está poblado")
    print("   Descripción: Fecha en que el contacto activó su cuenta")
    print("   Resultado: `pql_date`")
    
    # Analyze temporal order
    print("\n" + "=" * 100)
    print("ANÁLISIS DE ORDEN TEMPORAL")
    print("=" * 100)
    
    # Convert dates
    df['createdate'] = pd.to_datetime(df['createdate'], errors='coerce')
    df['contact_date'] = pd.to_datetime(df['contact_date'], errors='coerce')
    df['sql_date'] = pd.to_datetime(df['sql_date'], errors='coerce')
    df['pql_date'] = pd.to_datetime(df['pql_date'], errors='coerce')
    
    # Filter contacts with all dates
    has_all_dates = df[
        df['createdate'].notna() & 
        df['contact_date'].notna() & 
        df['sql_date'].notna() & 
        df['pql_date'].notna()
    ]
    
    print(f"\n📊 Contactos con todas las fechas disponibles: {len(has_all_dates)}")
    
    if len(has_all_dates) > 0:
        # Check temporal order
        sequential_order = []
        violations = []
        
        for idx, row in has_all_dates.iterrows():
            created = row['createdate']
            contacted = row['contact_date']
            sql = row['sql_date']
            pql = row['pql_date']
            
            # Expected order: created < contacted < sql < pql
            is_sequential = (created <= contacted <= sql <= pql)
            
            if is_sequential:
                sequential_order.append(row)
            else:
                violations.append({
                    'contact_id': row['contact_id'],
                    'email': row['email'],
                    'createdate': created,
                    'contact_date': contacted,
                    'sql_date': sql,
                    'pql_date': pql,
                    'violation': []
                })
                
                # Identify which order is violated
                if contacted < created:
                    violations[-1]['violation'].append('Contacted before Created')
                if sql < contacted:
                    violations[-1]['violation'].append('SQL before Contacted')
                if sql < created:
                    violations[-1]['violation'].append('SQL before Created')
                if pql < sql:
                    violations[-1]['violation'].append('PQL before SQL')
                if pql < contacted:
                    violations[-1]['violation'].append('PQL before Contacted')
                if pql < created:
                    violations[-1]['violation'].append('PQL before Created')
        
        print(f"   ✅ Orden secuencial correcto: {len(sequential_order)} ({len(sequential_order)/len(has_all_dates)*100:.1f}%)")
        print(f"   ❌ Violaciones de orden temporal: {len(violations)} ({len(violations)/len(has_all_dates)*100:.1f}%)")
        
        if len(violations) > 0:
            print(f"\n⚠️  EJEMPLOS DE VIOLACIONES DE ORDEN TEMPORAL:")
            print(f"{'Email':<40} │ {'Created':<12} │ {'Contacted':<12} │ {'SQL':<12} │ {'PQL':<12} │ {'Violación'}")
            print("─" * 40 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 30)
            for v in violations[:10]:  # Show first 10
                violations_str = ', '.join(v['violation'])
                print(f"{v['email']:<40} │ {v['createdate'].strftime('%Y-%m-%d'):<12} │ "
                      f"{v['contact_date'].strftime('%Y-%m-%d'):<12} │ "
                      f"{v['sql_date'].strftime('%Y-%m-%d'):<12} │ "
                      f"{v['pql_date'].strftime('%Y-%m-%d'):<12} │ {violations_str}")
    
    # Current funnel logic
    print("\n" + "=" * 100)
    print("LÓGICA ACTUAL DEL EMBUDO")
    print("=" * 100)
    
    total = len(df)
    contacted = df['is_contacted'].sum()
    sql = df['is_sql'].sum()
    pql = df['is_pql'].sum()
    
    print(f"\n📊 Embudo Actual (NO verifica orden temporal):")
    print(f"   1. Total Contactos: {total}")
    print(f"   2. Contactados: {contacted} (tiene `contact_date` o `days_to_contact` != null)")
    print(f"   3. SQL: {sql} (tiene `hs_v2_date_entered_opportunity` != null)")
    print(f"   4. PQL: {pql} (tiene `activo = 'true'` AND `fecha_activo` != null)")
    
    print(f"\n⚠️  IMPORTANTE:")
    print(f"   - El embudo actual NO verifica si los eventos ocurrieron en orden temporal")
    print(f"   - Solo cuenta cuántos contactos alcanzaron cada etapa")
    print(f"   - Un contacto puede ser SQL sin haber sido contactado (si las fechas lo permiten)")
    print(f"   - Un contacto puede ser PQL antes de SQL (si las fechas lo permiten)")
    
    # Analyze contacts that are SQL/PQL but not contacted
    sql_not_contacted = df[(df['is_sql'] == True) & (df['is_contacted'] == False)]
    pql_not_contacted = df[(df['is_pql'] == True) & (df['is_contacted'] == False)]
    pql_before_sql = df[(df['is_pql'] == True) & (df['is_sql'] == True) & 
                        (df['pql_date'].notna()) & (df['sql_date'].notna())]
    
    if len(pql_before_sql) > 0:
        pql_before_sql_dates = pql_before_sql[
            pd.to_datetime(pql_before_sql['pql_date'], errors='coerce') < 
            pd.to_datetime(pql_before_sql['sql_date'], errors='coerce')
        ]
        print(f"\n📊 Análisis Adicional:")
        print(f"   - SQL sin contactar: {len(sql_not_contacted)}")
        print(f"   - PQL sin contactar: {len(pql_not_contacted)}")
        print(f"   - PQL antes de SQL: {len(pql_before_sql_dates)}")
    
    return {
        'total': total,
        'contacted': contacted,
        'sql': sql,
        'pql': pql,
        'sequential_count': len(sequential_order) if len(has_all_dates) > 0 else 0,
        'violations_count': len(violations) if len(has_all_dates) > 0 else 0
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze funnel temporal order')
    parser.add_argument('--contacts-file',
                       default='tools/outputs/high_score_contacts_2025_12_01_2025_12_20.csv',
                       help='Path to contacts CSV file')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.contacts_file):
        print(f"❌ Error: File not found: {args.contacts_file}")
        sys.exit(1)
    
    analyze_funnel_temporal_order(args.contacts_file)

if __name__ == '__main__':
    main()

