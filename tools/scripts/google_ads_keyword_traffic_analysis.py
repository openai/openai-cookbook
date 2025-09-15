#!/usr/bin/env python3
"""
Google Ads Keyword Traffic Analysis
Analyzes keywords to identify sources of irrelevant traffic (money lending, elderly care, etc.)
"""

import json
import os
import argparse
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict
import re

def categorize_keyword(keyword_text: str) -> Dict[str, bool]:
    """
    Categorize keyword based on text patterns
    Returns dict with category flags
    """
    keyword_lower = keyword_text.lower()
    
    categories = {
        'money_lending': False,
        'financial_services': False,
        'elderly_care': False,
        'loan_related': False,
        'credit_related': False,
        'investment': False,
        'insurance': False,
        'gambling': False,
        'adult_content': False,
        'irrelevant_content': False,
        'suspicious_intent': False,
        'academic': False,
        'competitor': False,
        'legitimate_business': False
    }
    
    # Money lending patterns
    money_lending_patterns = [
        'prestamo', 'prestamos', 'credito', 'creditos', 'financiacion', 'financiamiento',
        'dinero', 'efectivo', 'cash', 'loan', 'loans', 'lending', 'lender',
        'rapido', 'urgente', 'inmediato', 'facil', 'sin', 'garantia', 'aval',
        'microcredito', 'microfinanza', 'payday', 'personal loan', 'prestamo personal',
        'credito rapido', 'dinero rapido', 'prestamo urgente', 'credito urgente',
        'prestamo sin garantia', 'credito sin garantia', 'prestamo facil',
        'credito facil', 'prestamo inmediato', 'credito inmediato'
    ]
    
    # Elderly care patterns
    elderly_patterns = [
        'jubilado', 'jubilados', 'pension', 'pensiones', 'adulto mayor', 'tercera edad',
        'retiro', 'retirado', 'anciano', 'ancianos', 'senior', 'seniors',
        'adultos mayores', 'mayores', 'vejez', 'jubilacion', 'pensionado',
        'pensionados', 'retirados', 'vejez', 'envejecimiento'
    ]
    
    # Loan and credit patterns
    loan_patterns = [
        'prestamo', 'prestamos', 'credito', 'creditos', 'financiacion', 'financiamiento',
        'hipoteca', 'hipotecas', 'prestamo hipotecario', 'credito hipotecario',
        'prestamo vehicular', 'credito vehicular', 'prestamo estudiantil',
        'credito estudiantil', 'prestamo comercial', 'credito comercial'
    ]
    
    # Investment patterns
    investment_patterns = [
        'inversion', 'inversiones', 'invertir', 'inversor', 'inversores',
        'bolsa', 'acciones', 'bonos', 'fondos', 'mutual', 'fideicomiso',
        'trading', 'trader', 'forex', 'bitcoin', 'criptomonedas', 'crypto'
    ]
    
    # Insurance patterns
    insurance_patterns = [
        'seguro', 'seguros', 'asegurar', 'aseguradora', 'poliza', 'polizas',
        'seguro de vida', 'seguro de salud', 'seguro de auto', 'seguro de hogar',
        'seguro medico', 'seguro dental', 'seguro de viaje'
    ]
    
    # Gambling patterns
    gambling_patterns = [
        'casino', 'casinos', 'apuesta', 'apuestas', 'juego', 'juegos',
        'poker', 'blackjack', 'ruleta', 'bingo', 'loteria', 'loterias',
        'quiniela', 'quinielas', 'tragamonedas', 'maquinas', 'tragaperras'
    ]
    
    # Academic patterns
    academic_patterns = [
        'curso', 'cursos', 'estudio', 'estudios', 'universidad', 'universidades',
        'carrera', 'carreras', 'titulo', 'titulos', 'diploma', 'diplomas',
        'maestria', 'maestrias', 'doctorado', 'doctorados', 'tesis', 'tesinas',
        'investigacion', 'investigaciones', 'academico', 'academicos'
    ]
    
    # Competitor patterns
    competitor_patterns = [
        'siigo', 'siigo.com', 'facturadores', 'facturador', 'facturacion electronica',
        'afip', 'mercadopago', 'mercadolibre', 'mercadolibre.com', 'nubox',
        'bind', 'bind.com', 'contador', 'contadores', 'estudio contable',
        'estudios contables', 'software contable', 'sistema contable'
    ]
    
    # Legitimate business patterns
    legitimate_patterns = [
        'facturacion', 'facturacion electronica', 'contabilidad', 'contable',
        'sistema', 'sistemas', 'software', 'gestion', 'administracion',
        'empresa', 'empresas', 'pyme', 'pymes', 'negocio', 'negocios',
        'ventas', 'compras', 'inventario', 'stock', 'clientes', 'proveedores',
        'nomina', 'nominas', 'sueldos', 'salarios', 'recursos humanos',
        'rrhh', 'hr', 'finanzas', 'financiero', 'presupuesto', 'presupuestos'
    ]
    
    # Check patterns
    for pattern in money_lending_patterns:
        if pattern in keyword_lower:
            categories['money_lending'] = True
            categories['loan_related'] = True
    
    for pattern in elderly_patterns:
        if pattern in keyword_lower:
            categories['elderly_care'] = True
    
    for pattern in loan_patterns:
        if pattern in keyword_lower:
            categories['loan_related'] = True
            categories['credit_related'] = True
    
    for pattern in investment_patterns:
        if pattern in keyword_lower:
            categories['investment'] = True
    
    for pattern in insurance_patterns:
        if pattern in keyword_lower:
            categories['insurance'] = True
    
    for pattern in gambling_patterns:
        if pattern in keyword_lower:
            categories['gambling'] = True
    
    for pattern in academic_patterns:
        if pattern in keyword_lower:
            categories['academic'] = True
    
    for pattern in competitor_patterns:
        if pattern in keyword_lower:
            categories['competitor'] = True
    
    for pattern in legitimate_patterns:
        if pattern in keyword_lower:
            categories['legitimate_business'] = True
    
    # Additional suspicious patterns
    suspicious_patterns = [
        'gratis', 'gratuito', 'free', 'sin costo', 'sin costos', 'regalo', 'regalos',
        'oferta', 'ofertas', 'descuento', 'descuentos', 'promocion', 'promociones',
        'trabajo', 'trabajos', 'empleo', 'empleos', 'salario', 'salarios',
        'sueldo', 'sueldos', 'dinero facil', 'dinero rapido', 'ganar dinero',
        'hacer dinero', 'dinero extra', 'ingresos extra', 'trabajo desde casa',
        'trabajo remoto', 'trabajo online', 'negocio desde casa', 'emprendimiento'
    ]
    
    for pattern in suspicious_patterns:
        if pattern in keyword_lower:
            categories['suspicious_intent'] = True
    
    return categories

def analyze_keywords(keywords_data: List[Dict]) -> Dict[str, Any]:
    """
    Analyze keywords for problematic traffic patterns
    """
    analysis = {
        'total_keywords': len(keywords_data),
        'problematic_keywords': [],
        'campaign_summary': defaultdict(lambda: {
            'total_keywords': 0,
            'problematic_keywords': 0,
            'total_clicks': 0,
            'problematic_clicks': 0,
            'total_cost': 0,
            'problematic_cost': 0,
            'categories': defaultdict(int)
        }),
        'category_summary': defaultdict(lambda: {
            'keywords': [],
            'total_clicks': 0,
            'total_cost': 0,
            'campaigns': set()
        }),
        'exclusion_recommendations': []
    }
    
    for keyword_data in keywords_data:
        campaign_name = keyword_data.get('campaign', {}).get('name', 'Unknown')
        ad_group_name = keyword_data.get('adGroup', {}).get('name', 'Unknown')
        keyword_text = keyword_data.get('adGroupCriterion', {}).get('keyword', {}).get('text', '')
        match_type = keyword_data.get('adGroupCriterion', {}).get('keyword', {}).get('matchType', '')
        clicks = int(keyword_data.get('metrics', {}).get('clicks', 0))
        cost_micros = int(keyword_data.get('metrics', {}).get('costMicros', 0))
        
        if not keyword_text:
            continue
        
        # Categorize the keyword
        categories = categorize_keyword(keyword_text)
        
        # Update campaign summary
        analysis['campaign_summary'][campaign_name]['total_keywords'] += 1
        analysis['campaign_summary'][campaign_name]['total_clicks'] += clicks
        analysis['campaign_summary'][campaign_name]['total_cost'] += cost_micros
        
        # Check if keyword is problematic
        is_problematic = any([
            categories['money_lending'],
            categories['elderly_care'],
            categories['gambling'],
            categories['adult_content'],
            categories['suspicious_intent'],
            categories['academic'] and not categories['legitimate_business']
        ])
        
        if is_problematic:
            analysis['problematic_keywords'].append({
                'keyword': keyword_text,
                'match_type': match_type,
                'campaign': campaign_name,
                'ad_group': ad_group_name,
                'clicks': clicks,
                'cost_micros': cost_micros,
                'categories': {k: v for k, v in categories.items() if v}
            })
            
            analysis['campaign_summary'][campaign_name]['problematic_keywords'] += 1
            analysis['campaign_summary'][campaign_name]['problematic_clicks'] += clicks
            analysis['campaign_summary'][campaign_name]['problematic_cost'] += cost_micros
            
            # Update category summary
            for category, is_active in categories.items():
                if is_active:
                    analysis['category_summary'][category]['keywords'].append(keyword_text)
                    analysis['category_summary'][category]['total_clicks'] += clicks
                    analysis['category_summary'][category]['total_cost'] += cost_micros
                    analysis['category_summary'][category]['campaigns'].add(campaign_name)
                    analysis['campaign_summary'][campaign_name]['categories'][category] += 1
    
    # Generate exclusion recommendations
    for category, data in analysis['category_summary'].items():
        if data['total_clicks'] > 0:
            analysis['exclusion_recommendations'].append({
                'category': category,
                'keywords': data['keywords'][:20],  # Top 20 keywords
                'total_clicks': data['total_clicks'],
                'total_cost': data['total_cost'],
                'campaigns_affected': list(data['campaigns'])
            })
    
    return analysis

def format_money_ars_micros(cost_micros: int) -> str:
    """Format cost in micros to Argentine peso format"""
    pesos = cost_micros / 1_000_000
    return f"${pesos:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def format_number_ar(n: float | int) -> str:
    """Format number in Argentine format"""
    if isinstance(n, int):
        return f"{n:,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def print_analysis_summary(analysis: Dict[str, Any]):
    """Print analysis summary to console"""
    print("🔍 GOOGLE ADS KEYWORD TRAFFIC ANALYSIS")
    print("=" * 60)
    
    print(f"\n📊 OVERVIEW:")
    print(f"   Total Keywords Analyzed: {format_number_ar(analysis['total_keywords'])}")
    print(f"   Problematic Keywords: {format_number_ar(len(analysis['problematic_keywords']))}")
    
    if analysis['problematic_keywords']:
        total_problematic_clicks = sum(k['clicks'] for k in analysis['problematic_keywords'])
        total_problematic_cost = sum(k['cost_micros'] for k in analysis['problematic_keywords'])
        
        print(f"   Problematic Clicks: {format_number_ar(total_problematic_clicks)}")
        print(f"   Problematic Cost: {format_money_ars_micros(total_problematic_cost)}")
    
    print(f"\n🚨 PROBLEMATIC KEYWORDS BY CATEGORY:")
    for category, data in analysis['category_summary'].items():
        if data['total_clicks'] > 0:
            print(f"\n   {category.upper().replace('_', ' ')}:")
            print(f"   - Keywords: {format_number_ar(len(data['keywords']))}")
            print(f"   - Clicks: {format_number_ar(data['total_clicks'])}")
            print(f"   - Cost: {format_money_ars_micros(data['total_cost'])}")
            print(f"   - Campaigns: {', '.join(data['campaigns'])}")
            
            # Show top keywords
            top_keywords = sorted(data['keywords'], key=lambda x: x.lower())[:10]
            print(f"   - Top Keywords: {', '.join(top_keywords)}")
    
    print(f"\n📈 CAMPAIGN IMPACT:")
    for campaign, data in analysis['campaign_summary'].items():
        if data['problematic_keywords'] > 0:
            problematic_pct = (data['problematic_keywords'] / data['total_keywords']) * 100
            print(f"\n   {campaign}:")
            print(f"   - Problematic Keywords: {format_number_ar(data['problematic_keywords'])}/{format_number_ar(data['total_keywords'])} ({problematic_pct:.1f}%)")
            print(f"   - Problematic Clicks: {format_number_ar(data['problematic_clicks'])}/{format_number_ar(data['total_clicks'])}")
            print(f"   - Problematic Cost: {format_money_ars_micros(data['problematic_cost'])}/{format_money_ars_micros(data['total_cost'])}")
            
            # Show categories
            if data['categories']:
                categories_str = ', '.join([f"{k}({v})" for k, v in data['categories'].items()])
                print(f"   - Categories: {categories_str}")

def save_exclusion_list(analysis: Dict[str, Any], output_path: str):
    """Save exclusion recommendations to file"""
    exclusion_file = os.path.join(output_path, f"keyword_exclusions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    
    with open(exclusion_file, 'w', encoding='utf-8') as f:
        f.write("GOOGLE ADS KEYWORD EXCLUSION RECOMMENDATIONS\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Problematic Keywords: {len(analysis['problematic_keywords'])}\n\n")
        
        for rec in analysis['exclusion_recommendations']:
            f.write(f"\n{rec['category'].upper().replace('_', ' ')}:\n")
            f.write(f"Clicks: {rec['total_clicks']}, Cost: {format_money_ars_micros(rec['total_cost'])}\n")
            f.write(f"Campaigns: {', '.join(rec['campaigns_affected'])}\n")
            f.write("Keywords to exclude:\n")
            for keyword in rec['keywords']:
                f.write(f"  - {keyword}\n")
            f.write("\n")
    
    print(f"\n💾 Exclusion list saved to: {exclusion_file}")
    return exclusion_file

def main():
    parser = argparse.ArgumentParser(description="Analyze Google Ads keywords for problematic traffic patterns")
    parser.add_argument("--input-file", required=True, help="Path to keywords JSON file")
    parser.add_argument("--output-dir", default="tools/outputs", help="Output directory")
    
    args = parser.parse_args()
    
    # Load keywords data
    print(f"📂 Loading keywords data from: {args.input_file}")
    with open(args.input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle both direct list and wrapped in 'results' structure
    if isinstance(data, dict) and 'results' in data:
        keywords_data = data['results']
    elif isinstance(data, list):
        keywords_data = data
    else:
        keywords_data = [data]
    
    print(f"✅ Loaded {len(keywords_data)} keyword records")
    
    # Analyze keywords
    print("\n🔍 Analyzing keywords for problematic patterns...")
    analysis = analyze_keywords(keywords_data)
    
    # Print summary
    print_analysis_summary(analysis)
    
    # Save exclusion list
    if analysis['problematic_keywords']:
        exclusion_file = save_exclusion_list(analysis, args.output_dir)
        
        # Save full analysis
        analysis_file = os.path.join(args.output_dir, f"keyword_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"💾 Full analysis saved to: {analysis_file}")
        
        print(f"\n🚨 IMMEDIATE ACTION REQUIRED:")
        print(f"   Review exclusion list: {exclusion_file}")
        print(f"   Add negative keywords to affected campaigns")
        print(f"   Monitor traffic quality after exclusions")
    else:
        print(f"\n✅ No problematic keywords found in current data")
        print(f"   Traffic issues may be coming from other sources")

if __name__ == "__main__":
    main()
