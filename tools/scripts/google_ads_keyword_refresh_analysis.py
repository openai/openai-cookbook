#!/usr/bin/env python3
"""
Google Ads Keyword Refresh Analysis
Analyzes all active keywords to identify problematic traffic sources
"""

import json
import argparse
from datetime import datetime
from typing import List, Dict, Any
import re

def load_keyword_data(file_path: str) -> List[Dict]:
    """Load keyword data from JSON file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle both direct list and wrapped in 'results' structure
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    elif isinstance(data, list):
        return data
    else:
        return [data]

def categorize_keywords(keywords_data: List[Dict]) -> Dict[str, List[Dict]]:
    """Categorize keywords by potential problematic patterns"""
    categories = {
        'money_lending': [],
        'elderly_retired': [],
        'minors_children': [],
        'suspicious_intent': [],
        'legitimate_business': [],
        'brand_related': []
    }
    
    # Define problematic patterns
    money_lending_patterns = [
        r'\b(prestamo|prestamos|credito|creditos|dinero|plata|efectivo|cash|loan|loans|credit|money|cash)\b',
        r'\b(emprestito|emprestitos|prestamo personal|prestamo rapido|dinero rapido|plata rapida)\b',
        r'\b(necesito dinero|necesito plata|necesito efectivo|urgente dinero|urgente plata)\b'
    ]
    
    elderly_patterns = [
        r'\b(jubilado|jubilados|pensionado|pensionados|adulto mayor|adultos mayores|anciano|ancianos)\b',
        r'\b(retirado|retirados|pension|pensiones|jubilacion|jubilaciones)\b',
        r'\b(vejez|tercera edad|adulto mayor|adultos mayores)\b'
    ]
    
    minors_patterns = [
        r'\b(menor|menores|niño|niños|niña|niñas|infantil|infantiles|adolescente|adolescentes)\b',
        r'\b(estudiante|estudiantes|colegio|colegios|escuela|escuelas|universidad|universidades)\b',
        r'\b(juventud|joven|jovenes|teen|teens|adolescent)\b'
    ]
    
    suspicious_patterns = [
        r'\b(gratis|gratuito|gratuitos|sin costo|sin costos|regalo|regalos|oferta|ofertas)\b',
        r'\b(rapido|rapida|rapidos|rapidas|urgente|urgentes|inmediato|inmediata)\b',
        r'\b(ganar dinero|ganar plata|trabajo desde casa|trabajo remoto|empleo|empleos)\b'
    ]
    
    brand_patterns = [
        r'\b(colppy|colpy|colpi|colpii)\b'
    ]
    
    for keyword_record in keywords_data:
        keyword_text = keyword_record.get('adGroupCriterion', {}).get('keyword', {}).get('text', '').lower()
        campaign_name = keyword_record.get('campaign', {}).get('name', '')
        
        if not keyword_text:
            continue
            
        keyword_info = {
            'keyword': keyword_text,
            'campaign': campaign_name,
            'match_type': keyword_record.get('adGroupCriterion', {}).get('keyword', {}).get('matchType', ''),
            'status': keyword_record.get('adGroupCriterion', {}).get('status', ''),
            'impressions': keyword_record.get('metrics', {}).get('impressions', 0),
            'clicks': keyword_record.get('metrics', {}).get('clicks', 0),
            'cost_micros': keyword_record.get('metrics', {}).get('costMicros', 0),
            'conversions': keyword_record.get('metrics', {}).get('conversions', 0)
        }
        
        # Check for money lending patterns
        if any(re.search(pattern, keyword_text, re.IGNORECASE) for pattern in money_lending_patterns):
            categories['money_lending'].append(keyword_info)
        # Check for elderly/retired patterns
        elif any(re.search(pattern, keyword_text, re.IGNORECASE) for pattern in elderly_patterns):
            categories['elderly_retired'].append(keyword_info)
        # Check for minors/children patterns
        elif any(re.search(pattern, keyword_text, re.IGNORECASE) for pattern in minors_patterns):
            categories['minors_children'].append(keyword_info)
        # Check for suspicious intent patterns
        elif any(re.search(pattern, keyword_text, re.IGNORECASE) for pattern in suspicious_patterns):
            categories['suspicious_intent'].append(keyword_info)
        # Check for brand patterns
        elif any(re.search(pattern, keyword_text, re.IGNORECASE) for pattern in brand_patterns):
            categories['brand_related'].append(keyword_info)
        else:
            categories['legitimate_business'].append(keyword_info)
    
    return categories

def analyze_performance(keywords: List[Dict]) -> Dict[str, Any]:
    """Analyze performance metrics for a list of keywords"""
    if not keywords:
        return {
            'total_keywords': 0,
            'total_impressions': 0,
            'total_clicks': 0,
            'total_cost_micros': 0,
            'total_conversions': 0,
            'avg_ctr': 0,
            'avg_cpc_micros': 0,
            'avg_cpa_micros': 0
        }
    
    total_impressions = sum(k.get('impressions', 0) for k in keywords)
    total_clicks = sum(k.get('clicks', 0) for k in keywords)
    total_cost_micros = sum(k.get('cost_micros', 0) for k in keywords)
    total_conversions = sum(k.get('conversions', 0) for k in keywords)
    
    avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    avg_cpc_micros = (total_cost_micros / total_clicks) if total_clicks > 0 else 0
    avg_cpa_micros = (total_cost_micros / total_conversions) if total_conversions > 0 else 0
    
    return {
        'total_keywords': len(keywords),
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'total_cost_micros': total_cost_micros,
        'total_conversions': total_conversions,
        'avg_ctr': avg_ctr,
        'avg_cpc_micros': avg_cpc_micros,
        'avg_cpa_micros': avg_cpa_micros
    }

def format_money_ars_micros(cost_micros: int) -> str:
    """Format cost in micros to Argentine peso format"""
    pesos = cost_micros / 1_000_000
    return f"${pesos:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def format_number_ar(n: float | int) -> str:
    """Format number in Argentine format"""
    if isinstance(n, int):
        return f"{n:,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def generate_exclusion_recommendations(categories: Dict[str, List[Dict]]) -> List[str]:
    """Generate negative keyword recommendations based on problematic categories"""
    recommendations = []
    
    # Money lending keywords
    if categories['money_lending']:
        recommendations.extend([
            "prestamo",
            "prestamos", 
            "credito",
            "creditos",
            "dinero",
            "plata",
            "efectivo",
            "cash",
            "loan",
            "loans",
            "credit",
            "money",
            "emprestito",
            "emprestitos",
            "prestamo personal",
            "prestamo rapido",
            "dinero rapido",
            "plata rapida",
            "necesito dinero",
            "necesito plata",
            "necesito efectivo",
            "urgente dinero",
            "urgente plata"
        ])
    
    # Elderly/retired keywords
    if categories['elderly_retired']:
        recommendations.extend([
            "jubilado",
            "jubilados",
            "pensionado",
            "pensionados",
            "adulto mayor",
            "adultos mayores",
            "anciano",
            "ancianos",
            "retirado",
            "retirados",
            "pension",
            "pensiones",
            "jubilacion",
            "jubilaciones",
            "vejez",
            "tercera edad"
        ])
    
    # Minors/children keywords
    if categories['minors_children']:
        recommendations.extend([
            "menor",
            "menores",
            "niño",
            "niños",
            "niña",
            "niñas",
            "infantil",
            "infantiles",
            "adolescente",
            "adolescentes",
            "estudiante",
            "estudiantes",
            "colegio",
            "colegios",
            "escuela",
            "escuelas",
            "universidad",
            "universidades",
            "juventud",
            "joven",
            "jovenes",
            "teen",
            "teens",
            "adolescent"
        ])
    
    # Suspicious intent keywords
    if categories['suspicious_intent']:
        recommendations.extend([
            "gratis",
            "gratuito",
            "gratuitos",
            "sin costo",
            "sin costos",
            "regalo",
            "regalos",
            "oferta",
            "ofertas",
            "rapido",
            "rapida",
            "rapidos",
            "rapidas",
            "urgente",
            "urgentes",
            "inmediato",
            "inmediata",
            "ganar dinero",
            "ganar plata",
            "trabajo desde casa",
            "trabajo remoto",
            "empleo",
            "empleos"
        ])
    
    return list(set(recommendations))  # Remove duplicates

def main():
    parser = argparse.ArgumentParser(description='Analyze Google Ads keywords for problematic traffic')
    parser.add_argument('--input-file', required=True, help='Path to keyword data JSON file')
    parser.add_argument('--output-dir', default='tools/outputs', help='Output directory for reports')
    
    args = parser.parse_args()
    
    print("🔍 Google Ads Keyword Refresh Analysis")
    print("=" * 50)
    
    # Load keyword data
    print(f"📂 Loading keyword data from: {args.input_file}")
    keywords_data = load_keyword_data(args.input_file)
    print(f"✅ Loaded {len(keywords_data)} keyword records")
    
    # Categorize keywords
    print("\n📊 Categorizing keywords...")
    categories = categorize_keywords(keywords_data)
    
    # Analyze each category
    print("\n📈 Performance Analysis by Category:")
    print("=" * 50)
    
    for category_name, keywords in categories.items():
        if not keywords:
            continue
            
        print(f"\n🔸 {category_name.upper().replace('_', ' ')}")
        print("-" * 30)
        
        performance = analyze_performance(keywords)
        
        print(f"Keywords: {performance['total_keywords']}")
        print(f"Impressions: {format_number_ar(performance['total_impressions'])}")
        print(f"Clicks: {format_number_ar(performance['total_clicks'])}")
        print(f"Cost: {format_money_ars_micros(performance['total_cost_micros'])}")
        print(f"Conversions: {format_number_ar(performance['total_conversions'])}")
        print(f"Avg CTR: {performance['avg_ctr']:.2f}%")
        print(f"Avg CPC: {format_money_ars_micros(performance['avg_cpc_micros'])}")
        print(f"Avg CPA: {format_money_ars_micros(performance['avg_cpa_micros'])}")
        
        # Show top keywords by impressions
        if keywords:
            top_keywords = sorted(keywords, key=lambda x: x.get('impressions', 0), reverse=True)[:5]
            print(f"\nTop keywords by impressions:")
            for i, kw in enumerate(top_keywords, 1):
                print(f"  {i}. {kw['keyword']} ({kw['match_type']}) - {format_number_ar(kw['impressions'])} impressions")
    
    # Generate exclusion recommendations
    print("\n🚫 Negative Keyword Recommendations:")
    print("=" * 50)
    
    recommendations = generate_exclusion_recommendations(categories)
    
    if recommendations:
        print(f"Found {len(recommendations)} recommended negative keywords:")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
    else:
        print("No problematic keywords found requiring exclusions.")
    
    # Save recommendations to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    recommendations_file = f"{args.output_dir}/keyword_exclusions_refresh_{timestamp}.txt"
    
    with open(recommendations_file, 'w', encoding='utf-8') as f:
        f.write("Google Ads Negative Keyword Recommendations (Refresh Analysis)\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total keywords analyzed: {len(keywords_data)}\n\n")
        
        f.write("Recommended Negative Keywords:\n")
        f.write("-" * 30 + "\n")
        for rec in recommendations:
            f.write(f"- {rec}\n")
        
        f.write("\n\nCategory Analysis:\n")
        f.write("-" * 20 + "\n")
        for category_name, keywords in categories.items():
            if keywords:
                performance = analyze_performance(keywords)
                f.write(f"\n{category_name.upper().replace('_', ' ')}:\n")
                f.write(f"  Keywords: {performance['total_keywords']}\n")
                f.write(f"  Impressions: {format_number_ar(performance['total_impressions'])}\n")
                f.write(f"  Clicks: {format_number_ar(performance['total_clicks'])}\n")
                f.write(f"  Cost: {format_money_ars_micros(performance['total_cost_micros'])}\n")
                f.write(f"  Conversions: {format_number_ar(performance['total_conversions'])}\n")
                f.write(f"  Avg CTR: {performance['avg_ctr']:.2f}%\n")
                f.write(f"  Avg CPC: {format_money_ars_micros(performance['avg_cpc_micros'])}\n")
                f.write(f"  Avg CPA: {format_money_ars_micros(performance['avg_cpa_micros'])}\n")
    
    print(f"\n💾 Recommendations saved to: {recommendations_file}")
    
    # Summary
    print("\n📋 Summary:")
    print("=" * 20)
    total_problematic = (len(categories['money_lending']) + 
                        len(categories['elderly_retired']) + 
                        len(categories['minors_children']) + 
                        len(categories['suspicious_intent']))
    
    print(f"Total keywords analyzed: {len(keywords_data)}")
    print(f"Problematic keywords found: {total_problematic}")
    print(f"Legitimate business keywords: {len(categories['legitimate_business'])}")
    print(f"Brand-related keywords: {len(categories['brand_related'])}")
    print(f"Negative keyword recommendations: {len(recommendations)}")

if __name__ == "__main__":
    main()
