#!/usr/bin/env python3
"""
Google Ads Refresh Analysis - Comprehensive Keywords and Placements Review
Analyzes all active keywords and placements to identify problematic traffic sources
that could be driving unwanted visitors (minors, lending, retired people, etc.)
"""

import json
import argparse
import re
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict

def load_gaql_data(data_text: str) -> List[Dict[str, Any]]:
    """Parse GAQL output (JSON or text) into structured data"""
    try:
        # Try to parse as JSON first
        data = json.loads(data_text)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'results' in data:
            return data['results']
        else:
            return [data] if data else []
    except json.JSONDecodeError:
        # Fall back to text parsing
        lines = data_text.strip().split('\n')
        if len(lines) < 2:
            return []
        
        # Skip header line
        data_lines = lines[1:]
        keywords_data = []
        
        for line in data_lines:
            if not line.strip():
                continue
                
            # Split by tab or multiple spaces
            parts = re.split(r'\s{2,}|\t', line.strip())
            if len(parts) >= 11:  # Expected number of columns
                try:
                    keyword_data = {
                        'campaign': {'name': parts[0]},
                        'adGroup': {'name': parts[3]},
                        'adGroupCriterion': {
                            'keyword': {
                                'text': parts[4],
                                'match_type': parts[5]
                            },
                            'status': parts[6]
                        },
                        'metrics': {
                            'impressions': int(parts[7]) if parts[7].isdigit() else 0,
                            'clicks': int(parts[8]) if parts[8].isdigit() else 0,
                            'costMicros': int(parts[9]) if parts[9].isdigit() else 0,
                            'conversions': float(parts[10]) if parts[10].replace('.', '').isdigit() else 0.0
                        }
                    }
                    keywords_data.append(keyword_data)
                except (ValueError, IndexError) as e:
                    print(f"⚠️  Error parsing line: {line[:50]}... - {e}")
                    continue
        
        return keywords_data

def categorize_problematic_keywords(keywords_data: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    """Categorize keywords by problematic patterns"""
    
    # Define problematic patterns
    problematic_patterns = {
        'money_lending': [
            r'\b(prestamo|prestamos|credito|creditos|dinero|efectivo|plata)\b',
            r'\b(emprestito|emprestitos|prestamo personal|credito personal)\b',
            r'\b(pedir dinero|necesito dinero|dinero urgente|dinero rapido)\b',
            r'\b(prestamo rapido|credito rapido|dinero facil)\b'
        ],
        'elderly_retired': [
            r'\b(jubilado|jubilados|pensionado|pensionados|adulto mayor|adultos mayores)\b',
            r'\b(retirado|retirados|vejez|anciano|ancianos)\b',
            r'\b(pension|pensiones|jubilacion|jubilaciones)\b'
        ],
        'minors_children': [
            r'\b(niño|niños|niña|niñas|menor|menores|infantil|infantiles)\b',
            r'\b(adolescente|adolescentes|joven|jovenes|estudiante|estudiantes)\b',
            r'\b(escuela|colegio|universidad|educacion|educativo)\b'
        ],
        'suspicious_intent': [
            r'\b(gratis|gratuito|sin costo|sin cargo|regalo|regalos)\b',
            r'\b(ganar dinero|hacer dinero|dinero facil|dinero rapido)\b',
            r'\b(inversion|inversiones|trading|forex|cripto)\b',
            r'\b(apuesta|apuestas|casino|juego|juegos de azar)\b'
        ],
        'salary_payroll_confusion': [
            r'\b(sueldo|sueldos|salario|salarios|pago|pagos)\b',
            r'\b(nomina|nominas|liquidacion|liquidaciones)\b',
            r'\b(cobrar|cobro|cobros|recibir dinero)\b'
        ]
    }
    
    categorized = defaultdict(list)
    
    for keyword_data in keywords_data:
        keyword_text = keyword_data.get('adGroupCriterion', {}).get('keyword', {}).get('text', '').lower()
        
        # Check each category
        for category, patterns in problematic_patterns.items():
            for pattern in patterns:
                if re.search(pattern, keyword_text, re.IGNORECASE):
                    categorized[category].append(keyword_data)
                    break  # Only add to first matching category
    
    return dict(categorized)

def analyze_keyword_performance(keywords_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze overall keyword performance"""
    
    def safe_int(value, default=0):
        """Safely convert value to int"""
        if isinstance(value, str):
            return int(value) if value.isdigit() else default
        return int(value) if value else default
    
    def safe_float(value, default=0.0):
        """Safely convert value to float"""
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return default
        return float(value) if value else default
    
    total_keywords = len(keywords_data)
    total_impressions = sum(safe_int(k.get('metrics', {}).get('impressions', 0)) for k in keywords_data)
    total_clicks = sum(safe_int(k.get('metrics', {}).get('clicks', 0)) for k in keywords_data)
    total_cost = sum(safe_int(k.get('metrics', {}).get('costMicros', 0)) for k in keywords_data)
    total_conversions = sum(safe_float(k.get('metrics', {}).get('conversions', 0)) for k in keywords_data)
    
    # Calculate metrics
    ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    cpc = (total_cost / total_clicks / 1_000_000) if total_clicks > 0 else 0
    cpa = (total_cost / total_conversions / 1_000_000) if total_conversions > 0 else 0
    
    return {
        'total_keywords': total_keywords,
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'total_cost_micros': total_cost,
        'total_conversions': total_conversions,
        'ctr': ctr,
        'cpc': cpc,
        'cpa': cpa
    }

def generate_exclusion_recommendations(categorized_keywords: Dict[str, List[Dict]]) -> List[str]:
    """Generate negative keyword recommendations"""
    
    recommendations = []
    
    for category, keywords in categorized_keywords.items():
        if not keywords:
            continue
            
        # Get unique keyword texts
        unique_keywords = set()
        for kw in keywords:
            keyword_text = kw.get('adGroupCriterion', {}).get('keyword', {}).get('text', '')
            if keyword_text:
                unique_keywords.add(keyword_text.lower())
        
        # Generate negative keyword suggestions
        if category == 'money_lending':
            recommendations.extend([
                'prestamo', 'prestamos', 'credito', 'creditos',
                'dinero urgente', 'dinero rapido', 'prestamo personal',
                'credito personal', 'emprestito', 'emprestitos'
            ])
        elif category == 'elderly_retired':
            recommendations.extend([
                'jubilado', 'jubilados', 'pensionado', 'pensionados',
                'adulto mayor', 'adultos mayores', 'retirado', 'retirados'
            ])
        elif category == 'minors_children':
            recommendations.extend([
                'niño', 'niños', 'niña', 'niñas', 'menor', 'menores',
                'adolescente', 'adolescentes', 'estudiante', 'estudiantes'
            ])
        elif category == 'suspicious_intent':
            recommendations.extend([
                'gratis', 'gratuito', 'sin costo', 'ganar dinero',
                'hacer dinero', 'dinero facil', 'apuesta', 'apuestas'
            ])
        elif category == 'salary_payroll_confusion':
            recommendations.extend([
                'sueldo', 'sueldos', 'salario', 'salarios',
                'pago', 'pagos', 'cobrar', 'cobro'
            ])
    
    # Remove duplicates and return
    return list(set(recommendations))

def format_money_ars_micros(cost_micros: int) -> str:
    """Format cost in Argentine pesos"""
    pesos = cost_micros / 1_000_000
    return f"${pesos:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def safe_int_global(value, default=0):
    """Safely convert value to int"""
    if isinstance(value, str):
        return int(value) if value.isdigit() else default
    return int(value) if value else default

def safe_float_global(value, default=0.0):
    """Safely convert value to float"""
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return float(value) if value else default

def main():
    parser = argparse.ArgumentParser(description='Google Ads Refresh Analysis')
    parser.add_argument('--input-file', required=True, help='Input GAQL data file')
    parser.add_argument('--output-dir', default='tools/outputs', help='Output directory')
    args = parser.parse_args()
    
    print("🔍 Google Ads Refresh Analysis - Keywords & Placements")
    print("=" * 60)
    
    # Load and parse GAQL data
    print(f"📂 Loading GAQL data from: {args.input_file}")
    
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            data_content = f.read()
        
        # Parse the GAQL output
        keywords_data = load_gaql_data(data_content)
        
        if not keywords_data:
            print("❌ No keyword data found in input file")
            return
        
        print(f"✅ Loaded {len(keywords_data)} keyword records")
        
    except FileNotFoundError:
        print(f"❌ Input file not found: {args.input_file}")
        return
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return
    
    # Analyze overall performance
    print("\n📊 Overall Keyword Performance Analysis")
    print("-" * 40)
    
    performance = analyze_keyword_performance(keywords_data)
    
    print(f"Total Keywords: {performance['total_keywords']:,}")
    print(f"Total Impressions: {performance['total_impressions']:,}")
    print(f"Total Clicks: {performance['total_clicks']:,}")
    print(f"Total Cost: {format_money_ars_micros(performance['total_cost_micros'])}")
    print(f"Total Conversions: {performance['total_conversions']:.0f}")
    print(f"CTR: {performance['ctr']:.2f}%")
    print(f"CPC: {format_money_ars_micros(int(performance['cpc'] * 1_000_000))}")
    print(f"CPA: {format_money_ars_micros(int(performance['cpa'] * 1_000_000))}")
    
    # Categorize problematic keywords
    print("\n🚨 Problematic Keywords Analysis")
    print("-" * 40)
    
    categorized = categorize_problematic_keywords(keywords_data)
    
    total_problematic = 0
    for category, keywords in categorized.items():
        if keywords:
            total_problematic += len(keywords)
            print(f"\n{category.upper().replace('_', ' ')} ({len(keywords)} keywords):")
            
            # Show top problematic keywords by cost
            sorted_keywords = sorted(keywords, key=lambda x: safe_int_global(x.get('metrics', {}).get('costMicros', 0)), reverse=True)
            for kw in sorted_keywords[:5]:  # Top 5 by cost
                cost_micros = kw.get('metrics', {}).get('costMicros', 0)
                cost_str = format_money_ars_micros(safe_int_global(cost_micros))
                keyword_text = kw.get('adGroupCriterion', {}).get('keyword', {}).get('text', 'N/A')
                campaign_name = kw.get('campaign', {}).get('name', 'N/A')
                print(f"  • {keyword_text} | {campaign_name} | Cost: {cost_str}")
    
    print(f"\n🎯 Total Problematic Keywords: {total_problematic}")
    
    # Generate exclusion recommendations
    print("\n📝 Negative Keyword Recommendations")
    print("-" * 40)
    
    recommendations = generate_exclusion_recommendations(categorized)
    
    if recommendations:
        print("Recommended negative keywords to add:")
        for rec in sorted(recommendations):
            print(f"  • {rec}")
    else:
        print("✅ No problematic keywords found requiring exclusions")
    
    # Save detailed analysis
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    analysis_file = f"{args.output_dir}/refresh_analysis_{timestamp}.json"
    
    analysis_data = {
        'timestamp': timestamp,
        'analysis_type': 'refresh_keywords_placements',
        'performance_summary': performance,
        'categorized_keywords': categorized,
        'recommendations': recommendations,
        'total_problematic_keywords': total_problematic
    }
    
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Analysis saved to: {analysis_file}")
    
    # Generate exclusion list file
    if recommendations:
        exclusion_file = f"{args.output_dir}/negative_keywords_refresh_{timestamp}.txt"
        with open(exclusion_file, 'w', encoding='utf-8') as f:
            f.write("# Negative Keywords - Refresh Analysis\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("# Add these as negative keywords to prevent unwanted traffic\n\n")
            for rec in sorted(recommendations):
                f.write(f"{rec}\n")
        
        print(f"📋 Exclusion list saved to: {exclusion_file}")
    
    print("\n✅ Refresh analysis completed!")
    print("\n🔍 Next Steps:")
    print("1. Review the problematic keywords identified")
    print("2. Add recommended negative keywords to campaigns")
    print("3. Monitor traffic quality after implementing exclusions")
    print("4. Run placement analysis for Display campaigns")

if __name__ == "__main__":
    main()
