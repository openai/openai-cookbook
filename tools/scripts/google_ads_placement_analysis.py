#!/usr/bin/env python3
"""
Google Ads Placement Analysis - Identify Problematic Traffic Sources
Analyzes Google Ads placements to identify money lending and irrelevant traffic sources
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Set

def load_placement_data(file_path: str) -> List[Dict]:
    """Load placement data from JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('results', [])
    except Exception as e:
        print(f"❌ Error loading placement data: {e}")
        return []

def categorize_placement(placement_url: str) -> Dict[str, bool]:
    """
    Categorize placement based on URL patterns
    Returns dict with category flags
    """
    url_lower = placement_url.lower()
    
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
        'suspicious_domain': False
    }
    
    # Money lending patterns
    money_lending_patterns = [
        'prestamo', 'prestamos', 'credito', 'creditos', 'financiacion', 'financiamiento',
        'dinero', 'efectivo', 'cash', 'loan', 'loans', 'lending', 'lender',
        'rapido', 'urgente', 'inmediato', 'facil', 'sin', 'garantia', 'aval',
        'microcredito', 'microfinanza', 'payday', 'personal loan'
    ]
    
    # Elderly care patterns
    elderly_patterns = [
        'jubilado', 'jubilados', 'pension', 'pensiones', 'adulto mayor', 'tercera edad',
        'retiro', 'retirado', 'anciano', 'ancianos', 'senior', 'seniors',
        'adultos mayores', 'mayores', 'vejez'
    ]
    
    # Financial services patterns
    financial_patterns = [
        'banco', 'bancos', 'bancario', 'financiera', 'financiero', 'finanzas',
        'inversion', 'inversiones', 'bolsa', 'trading', 'forex', 'bitcoin',
        'crypto', 'cripto', 'moneda', 'divisa'
    ]
    
    # Loan related patterns
    loan_patterns = [
        'hipoteca', 'hipotecario', 'auto', 'vehiculo', 'casa', 'vivienda',
        'consumo', 'comercial', 'empresarial', 'estudiantil'
    ]
    
    # Suspicious domain patterns
    suspicious_patterns = [
        'free', 'gratis', 'sin costo', 'ganar dinero', 'dinero facil',
        'trabajo desde casa', 'empleo', 'trabajo', 'oportunidad',
        'ganancias', 'rentable', 'inversion segura'
    ]
    
    # Check patterns
    for pattern in money_lending_patterns:
        if pattern in url_lower:
            categories['money_lending'] = True
            categories['loan_related'] = True
    
    for pattern in elderly_patterns:
        if pattern in url_lower:
            categories['elderly_care'] = True
    
    for pattern in financial_patterns:
        if pattern in url_lower:
            categories['financial_services'] = True
    
    for pattern in loan_patterns:
        if pattern in url_lower:
            categories['loan_related'] = True
    
    for pattern in suspicious_patterns:
        if pattern in url_lower:
            categories['suspicious_domain'] = True
    
    # Additional checks
    if any(word in url_lower for word in ['casino', 'apuesta', 'bet', 'gambling']):
        categories['gambling'] = True
    
    if any(word in url_lower for word in ['adult', 'xxx', 'porn', 'sex']):
        categories['adult_content'] = True
    
    # Check for irrelevant content
    irrelevant_patterns = [
        'juego', 'juegos', 'game', 'games', 'entretenimiento', 'deporte', 'deportes',
        'musica', 'pelicula', 'peliculas', 'cine', 'television', 'tv',
        'noticia', 'noticias', 'news', 'blog', 'foro', 'comunidad'
    ]
    
    for pattern in irrelevant_patterns:
        if pattern in url_lower:
            categories['irrelevant_content'] = True
    
    return categories

def analyze_placements(placements: List[Dict]) -> Dict:
    """Analyze all placements and categorize them"""
    analysis = {
        'total_placements': len(placements),
        'problematic_placements': [],
        'categories': defaultdict(list),
        'campaign_summary': defaultdict(int),
        'recommendations': []
    }
    
    for placement in placements:
        display_name = placement.get('adGroupCriterion', {}).get('displayName', '')
        campaign_data = placement.get('campaign', {})
        campaign_name = campaign_data.get('name', '') if isinstance(campaign_data, dict) else str(campaign_data)
        
        if not display_name:
            continue
        
        categories = categorize_placement(display_name)
        
        # Check if placement is problematic
        is_problematic = any([
            categories['money_lending'],
            categories['elderly_care'],
            categories['gambling'],
            categories['adult_content'],
            categories['suspicious_domain']
        ])
        
        if is_problematic:
            problematic_placement = {
                'placement_url': display_name,
                'campaign': campaign_name,
                'categories': categories,
                'severity': 'HIGH' if categories['money_lending'] or categories['elderly_care'] else 'MEDIUM'
            }
            analysis['problematic_placements'].append(problematic_placement)
        
        # Categorize for summary
        for category, is_match in categories.items():
            if is_match:
                analysis['categories'][category].append({
                    'placement': display_name,
                    'campaign': campaign_name
                })
        
        # Campaign summary
        analysis['campaign_summary'][campaign_name] += 1
    
    return analysis

def generate_exclusions_list(analysis: Dict) -> List[str]:
    """Generate list of placements to exclude"""
    exclusions = []
    
    # High priority exclusions (money lending, elderly care)
    high_priority = [p for p in analysis['problematic_placements'] if p['severity'] == 'HIGH']
    
    for placement in high_priority:
        exclusions.append(placement['placement_url'])
    
    # Medium priority exclusions (gambling, adult content, suspicious)
    medium_priority = [p for p in analysis['problematic_placements'] if p['severity'] == 'MEDIUM']
    
    for placement in medium_priority:
        exclusions.append(placement['placement_url'])
    
    return exclusions

def generate_recommendations(analysis: Dict) -> List[str]:
    """Generate actionable recommendations"""
    recommendations = []
    
    total_problematic = len(analysis['problematic_placements'])
    total_placements = analysis['total_placements']
    
    if total_problematic > 0:
        percentage = (total_problematic / total_placements) * 100
        recommendations.append(f"🚨 URGENT: {total_problematic} problematic placements identified ({percentage:.1f}% of total)")
    
    # Money lending specific
    money_lending_count = len(analysis['categories']['money_lending'])
    if money_lending_count > 0:
        recommendations.append(f"💰 Money lending sites: {money_lending_count} placements need immediate exclusion")
    
    # Elderly care specific
    elderly_count = len(analysis['categories']['elderly_care'])
    if elderly_count > 0:
        recommendations.append(f"👴 Elderly care sites: {elderly_count} placements targeting wrong demographic")
    
    # Campaign-specific recommendations
    campaign_issues = defaultdict(int)
    for placement in analysis['problematic_placements']:
        campaign_issues[placement['campaign']] += 1
    
    for campaign, count in campaign_issues.items():
        if count > 0:
            recommendations.append(f"📊 Campaign '{campaign}': {count} problematic placements")
    
    # General recommendations
    recommendations.extend([
        "🔧 Implement placement exclusions immediately",
        "📋 Set up automated placement monitoring",
        "🎯 Review audience targeting settings",
        "📈 Monitor conversion quality after exclusions"
    ])
    
    return recommendations

def main():
    """Main analysis function"""
    print("🔍 Google Ads Placement Analysis - Identifying Problematic Traffic Sources")
    print("=" * 80)
    
    # Find the most recent placement data file
    output_dir = "tools/outputs"
    placement_files = [f for f in os.listdir(output_dir) if f.startswith('google_ads_placements_') and f.endswith('.json')]
    
    if not placement_files:
        print("❌ No placement data files found in tools/outputs/")
        return
    
    # Use the most recent file
    latest_file = sorted(placement_files)[-1]
    file_path = os.path.join(output_dir, latest_file)
    
    print(f"📁 Loading placement data from: {latest_file}")
    
    # Load and analyze data
    placements = load_placement_data(file_path)
    if not placements:
        print("❌ No placement data loaded")
        return
    
    print(f"📊 Analyzing {len(placements)} placements...")
    
    # Perform analysis
    analysis = analyze_placements(placements)
    
    # Generate exclusions list
    exclusions = generate_exclusions_list(analysis)
    
    # Generate recommendations
    recommendations = generate_recommendations(analysis)
    
    # Print results
    print("\n" + "=" * 80)
    print("🚨 PROBLEMATIC PLACEMENTS ANALYSIS")
    print("=" * 80)
    
    print(f"\n📈 SUMMARY:")
    print(f"   Total placements analyzed: {analysis['total_placements']}")
    print(f"   Problematic placements: {len(analysis['problematic_placements'])}")
    print(f"   Percentage problematic: {(len(analysis['problematic_placements']) / analysis['total_placements']) * 100:.1f}%")
    
    # Category breakdown
    print(f"\n📊 CATEGORY BREAKDOWN:")
    for category, placements_list in analysis['categories'].items():
        if placements_list:
            print(f"   {category}: {len(placements_list)} placements")
    
    # High priority issues
    high_priority = [p for p in analysis['problematic_placements'] if p['severity'] == 'HIGH']
    if high_priority:
        print(f"\n🚨 HIGH PRIORITY EXCLUSIONS ({len(high_priority)} placements):")
        for i, placement in enumerate(high_priority[:10], 1):  # Show top 10
            print(f"   {i}. {placement['placement_url']}")
            print(f"      Campaign: {placement['campaign']}")
            active_categories = [cat for cat, active in placement['categories'].items() if active]
            print(f"      Categories: {', '.join(active_categories)}")
            print()
    
    # Medium priority issues
    medium_priority = [p for p in analysis['problematic_placements'] if p['severity'] == 'MEDIUM']
    if medium_priority:
        print(f"\n⚠️  MEDIUM PRIORITY EXCLUSIONS ({len(medium_priority)} placements):")
        for i, placement in enumerate(medium_priority[:5], 1):  # Show top 5
            print(f"   {i}. {placement['placement_url']}")
            print(f"      Campaign: {placement['campaign']}")
            active_categories = [cat for cat, active in placement['categories'].items() if active]
            print(f"      Categories: {', '.join(active_categories)}")
            print()
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS:")
    for i, rec in enumerate(recommendations, 1):
        print(f"   {i}. {rec}")
    
    # Save exclusions list
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exclusions_file = f"tools/outputs/placement_exclusions_{timestamp}.txt"
    
    with open(exclusions_file, 'w', encoding='utf-8') as f:
        f.write("# Google Ads Placement Exclusions - Generated by Analysis\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total exclusions: {len(exclusions)}\n\n")
        
        f.write("# HIGH PRIORITY EXCLUSIONS (Money lending, Elderly care)\n")
        high_priority_urls = [p['placement_url'] for p in high_priority]
        for url in high_priority_urls:
            f.write(f"{url}\n")
        
        f.write("\n# MEDIUM PRIORITY EXCLUSIONS (Gambling, Adult content, Suspicious)\n")
        medium_priority_urls = [p['placement_url'] for p in medium_priority]
        for url in medium_priority_urls:
            f.write(f"{url}\n")
    
    print(f"\n💾 Exclusions list saved to: {exclusions_file}")
    print(f"📋 Total placements to exclude: {len(exclusions)}")
    
    # Save detailed analysis
    analysis_file = f"tools/outputs/placement_analysis_{timestamp}.json"
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    print(f"📊 Detailed analysis saved to: {analysis_file}")
    
    print(f"\n✅ Analysis complete! Review the exclusions list and implement immediately.")

if __name__ == "__main__":
    main()
