#!/usr/bin/env python3
"""
Improved Company Name Matching Analysis
Better fuzzy matching with filtering of generic terms and enhanced similarity scoring
"""

import sys
import json
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# Add the current directory to the path
sys.path.append('.')

# Import HubSpot API package
from hubspot_api.query_builder import closed_won_deals_in_july_2025
from hubspot_api import get_client

# Import Colppy database package
from database.models import BaseModel

class Empresa(BaseModel):
    table_name = 'empresa'
    primary_key = 'IdEmpresa'

# Generic terms to filter out from matching
GENERIC_TERMS = {
    'fundacion', 'sociedad', 'anonima', 'limitada', 'responsabilidad',
    'estudio', 'contador', 'contadora', 'cdra', 'cdr', 'consultora',
    'consultoría', 'consultoria', 'asoc', 'asociados', 'hnos', 'hermanos',
    'sa', 'sas', 'srl', 'inc', 'corp', 'limited', 'ltd', 'llc',
    'empresa', 'compania', 'company', 'group', 'grupo', 'holding'
}

def advanced_clean_name(name: str) -> str:
    """Advanced cleaning and normalization of company names"""
    if not name:
        return ""
    
    # Convert to lowercase
    name = name.lower().strip()
    
    # Remove numeric prefixes (like "94334 - ")
    name = re.sub(r'^\d+\s*-\s*', '', name)
    
    # Remove common business suffixes more aggressively
    suffixes = [
        r'\s*s\.?a\.?s?\.?\s*$', r'\s*s\.?r\.?l\.?\s*$', r'\s*s\.?a\.?\s*$',
        r'\s*ltda\.?\s*$', r'\s*inc\.?\s*$', r'\s*corp\.?\s*$',
        r'\s*limited\s*$', r'\s*ltd\.?\s*$', r'\s*llc\.?\s*$',
        r'\s*sociedad\s+anonima\s*$', r'\s*sociedad\s+de\s+responsabilidad\s+limitada\s*$',
        r'\s*fundacion\s*$', r'\s*estudio\s*$', r'\s*contador\w*\s*$',
        r'\s*consultor\w*\s*$', r'\s*asoc\w*\s*$', r'\s*hnos?\.?\s*$',
        r'\s*y\s+asoc\w*\s*$', r'\s*&\s+asoc\w*\s*$'
    ]
    
    for suffix in suffixes:
        name = re.sub(suffix, '', name)
    
    # Remove everything after certain delimiters
    name = re.split(r'\s*[-–—]\s*', name)[0]  # Keep only part before dash
    
    # Remove special characters and normalize spaces
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def calculate_meaningful_similarity(hubspot_name: str, colppy_name: str) -> float:
    """Calculate similarity with emphasis on meaningful matches"""
    if not hubspot_name or not colppy_name:
        return 0.0
    
    # Clean both names
    h_clean = advanced_clean_name(hubspot_name)
    c_clean = advanced_clean_name(colppy_name)
    
    if not h_clean or not c_clean:
        return 0.0
    
    # Exact match after cleaning
    if h_clean == c_clean:
        return 1.0
    
    # One contains the other (high score)
    if h_clean in c_clean or c_clean in h_clean:
        return 0.95
    
    # Split into meaningful words (filter out generic terms)
    h_words = set(word for word in h_clean.split() if len(word) > 2 and word not in GENERIC_TERMS)
    c_words = set(word for word in c_clean.split() if len(word) > 2 and word not in GENERIC_TERMS)
    
    if not h_words or not c_words:
        return 0.0
    
    # Calculate word overlap
    intersection = h_words.intersection(c_words)
    union = h_words.union(c_words)
    
    if not union:
        return 0.0
    
    jaccard_similarity = len(intersection) / len(union)
    
    # Boost score if significant words match
    if len(intersection) >= 2:  # At least 2 meaningful words match
        jaccard_similarity *= 1.2
    
    # Penalize if one name is much longer (likely different companies)
    len_ratio = min(len(h_words), len(c_words)) / max(len(h_words), len(c_words))
    if len_ratio < 0.5:
        jaccard_similarity *= 0.7
    
    return min(jaccard_similarity, 1.0)

def get_filtered_empresa_records():
    """Get empresa records and filter out generic/test entries"""
    print('\n🔍 Getting Filtered Empresa Records from Colppy')
    print('='*50)
    
    try:
        # Get records with meaningful names
        query = """
        SELECT IdEmpresa, CUIT, Nombre, razonSocial, localidad
        FROM empresa 
        WHERE (Nombre IS NOT NULL AND LENGTH(Nombre) > 3) 
           OR (razonSocial IS NOT NULL AND LENGTH(razonSocial) > 3)
        ORDER BY IdEmpresa
        """
        
        print('   🔍 Querying empresa records...')
        results = Empresa.execute_custom_query(query)
        
        empresa_records = []
        for row in results:
            empresa_id = str(row.get('IdEmpresa', ''))
            nombre = row.get('Nombre', '') or ''
            razon_social = row.get('razonSocial', '') or ''
            
            # Filter out obvious generic/test entries
            skip_patterns = [
                r'^test\d*$', r'^prueba\d*$', r'^demo\d*$', r'^ejemplo\d*$',
                r'^cliente\d*$', r'^empresa\d*$', r'^xxx+$', r'^aaa+$',
                r'^\d+$',  # Pure numbers
                r'^[a-z]$'  # Single letters
            ]
            
            should_skip = False
            for pattern in skip_patterns:
                if re.match(pattern, nombre.lower()) or re.match(pattern, razon_social.lower()):
                    should_skip = True
                    break
            
            if not should_skip and (nombre.strip() or razon_social.strip()):
                empresa_records.append({
                    'empresa_id': empresa_id,
                    'nombre': nombre.strip(),
                    'razon_social': razon_social.strip(),
                    'cuit': row.get('CUIT', '') or '',
                    'localidad': row.get('localidad', '') or ''
                })
        
        print(f'✅ Retrieved {len(empresa_records)} filtered empresa records')
        return empresa_records
        
    except Exception as e:
        print(f'❌ Error querying Colppy: {e}')
        return []

def perform_improved_matching(companies_data: List[Dict], empresa_records: List[Dict], min_similarity: float = 0.6):
    """Perform improved fuzzy matching with better filtering"""
    print(f'\n🔍 Performing Improved Fuzzy Matching (minimum similarity: {min_similarity})')
    print('='*60)
    
    matches = []
    exact_matches = 0
    high_similarity_matches = 0
    moderate_similarity_matches = 0
    
    for i, company in enumerate(companies_data, 1):
        if i % 10 == 0:
            print(f'   Progress: {i}/{len(companies_data)} companies analyzed...')
        
        company_name = company['name']
        best_matches = []
        
        # Compare against both Nombre and razonSocial fields
        for empresa in empresa_records:
            # Check similarity with Nombre field
            if empresa['nombre']:
                similarity_nombre = calculate_meaningful_similarity(company_name, empresa['nombre'])
                if similarity_nombre >= min_similarity:
                    best_matches.append({
                        'empresa_id': empresa['empresa_id'],
                        'field_matched': 'nombre',
                        'empresa_value': empresa['nombre'],
                        'similarity': similarity_nombre,
                        'empresa_data': empresa,
                        'hubspot_clean': advanced_clean_name(company_name),
                        'colppy_clean': advanced_clean_name(empresa['nombre'])
                    })
            
            # Check similarity with razonSocial field
            if empresa['razon_social']:
                similarity_razon = calculate_meaningful_similarity(company_name, empresa['razon_social'])
                if similarity_razon >= min_similarity:
                    best_matches.append({
                        'empresa_id': empresa['empresa_id'],
                        'field_matched': 'razonSocial',
                        'empresa_value': empresa['razon_social'],
                        'similarity': similarity_razon,
                        'empresa_data': empresa,
                        'hubspot_clean': advanced_clean_name(company_name),
                        'colppy_clean': advanced_clean_name(empresa['razon_social'])
                    })
        
        # Sort by similarity and keep top matches
        best_matches.sort(key=lambda x: x['similarity'], reverse=True)
        top_matches = best_matches[:3]  # Keep top 3 matches
        
        if top_matches:
            match_data = {
                'hubspot_company': company,
                'matches': top_matches,
                'best_similarity': top_matches[0]['similarity']
            }
            matches.append(match_data)
            
            # Count match quality
            best_sim = top_matches[0]['similarity']
            if best_sim >= 0.95:
                exact_matches += 1
            elif best_sim >= 0.8:
                high_similarity_matches += 1
            elif best_sim >= 0.6:
                moderate_similarity_matches += 1
    
    print(f'\n📊 Improved Matching Results:')
    print(f'   • Companies with meaningful matches: {len(matches)}/{len(companies_data)}')
    print(f'   • Exact/Near-exact matches (≥95%): {exact_matches}')
    print(f'   • High similarity (≥80%): {high_similarity_matches}')
    print(f'   • Moderate similarity (≥60%): {moderate_similarity_matches}')
    
    return matches

def display_meaningful_matches(matches: List[Dict], show_count: int = 20):
    """Display meaningful matches with cleaned names for comparison"""
    print(f'\n📋 TOP {show_count} MEANINGFUL COMPANY MATCHES')
    print('='*130)
    print('HubSpot Company Name              | Colppy Match (Field)           | Similarity | Empresa ID | CUIT        | Cleaned Comparison')
    print('-'*130)
    
    # Sort by similarity
    sorted_matches = sorted(matches, key=lambda x: x['best_similarity'], reverse=True)
    
    for i, match in enumerate(sorted_matches[:show_count], 1):
        company = match['hubspot_company']
        best_match = match['matches'][0]
        
        hubspot_name = company['name'][:30]
        empresa_value = best_match['empresa_value'][:25]
        field_name = best_match['field_matched']
        similarity = best_match['similarity']
        empresa_id = best_match['empresa_id']
        cuit = best_match['empresa_data'].get('cuit', '')[:10] if best_match['empresa_data'].get('cuit') else 'N/A'
        
        print(f'{hubspot_name:<32} | {empresa_value:<25} ({field_name:>6}) | {similarity:>8.1%} | {empresa_id:>10} | {cuit:<11}')
        
        # Show cleaned comparison for high matches
        if similarity >= 0.8:
            h_clean = best_match['hubspot_clean']
            c_clean = best_match['colppy_clean']
            print(f'    Cleaned: "{h_clean}" ↔ "{c_clean}"')

def display_potential_data_links(matches: List[Dict]):
    """Display potential data relationships between systems"""
    print(f'\n🔗 POTENTIAL DATA RELATIONSHIPS')
    print('='*60)
    
    high_confidence_matches = [m for m in matches if m['best_similarity'] >= 0.8]
    
    if high_confidence_matches:
        print(f'\n📋 High-Confidence Matches ({len(high_confidence_matches)}):')
        
        for match in high_confidence_matches:
            company = match['hubspot_company']
            best_match = match['matches'][0]
            
            print(f'\n🎯 {company["name"]}')
            print(f'   📊 HubSpot ID: {company["hubspot_id"]} | Deals: {company["deal_count"]}')
            print(f'   🏦 Colppy Match: {best_match["empresa_value"]} (ID: {best_match["empresa_id"]})')
            print(f'   📈 Similarity: {best_match["similarity"]:.1%} | Field: {best_match["field_matched"]}')
            print(f'   💳 CUIT: {best_match["empresa_data"].get("cuit", "N/A")}')
            print(f'   📍 Location: {best_match["empresa_data"].get("localidad", "N/A")}')
            
            # Show deal empresa IDs if available
            if company['deals']:
                deal_empresa_ids = set(deal['empresa_id'] for deal in company['deals'] if deal['empresa_id'])
                if deal_empresa_ids:
                    print(f'   🔗 Deal Empresa IDs: {", ".join(deal_empresa_ids)}')
                    
                    # Check if there's a direct match
                    if best_match['empresa_id'] in deal_empresa_ids:
                        print(f'   ✅ DIRECT MATCH: Empresa ID {best_match["empresa_id"]} appears in deals!')
                    else:
                        print(f'   ⚠️  INDIRECT: Match empresa {best_match["empresa_id"]} ≠ deal empresas {deal_empresa_ids}')

def analyze_deal_empresa_coverage(matches: List[Dict], companies_data: List[Dict]):
    """Analyze how well we're covering the deal empresa relationships"""
    print(f'\n📊 DEAL-EMPRESA RELATIONSHIP ANALYSIS')
    print('='*50)
    
    # Get all empresa IDs from deals
    all_deal_empresa_ids = set()
    companies_with_deal_empresas = 0
    
    for company in companies_data:
        deal_empresa_ids = set(deal['empresa_id'] for deal in company['deals'] if deal['empresa_id'])
        if deal_empresa_ids:
            companies_with_deal_empresas += 1
            all_deal_empresa_ids.update(deal_empresa_ids)
    
    # Get empresa IDs from matches
    matched_empresa_ids = set()
    direct_matches = 0
    
    for match in matches:
        company = match['hubspot_company']
        deal_empresa_ids = set(deal['empresa_id'] for deal in company['deals'] if deal['empresa_id'])
        
        for m in match['matches']:
            matched_empresa_ids.add(m['empresa_id'])
            
            # Check for direct match
            if m['empresa_id'] in deal_empresa_ids:
                direct_matches += 1
                break
    
    print(f'   📈 Total companies with deal empresa IDs: {companies_with_deal_empresas}')
    print(f'   📈 Unique deal empresa IDs: {len(all_deal_empresa_ids)}')
    print(f'   📈 Companies with name matches: {len(matches)}')
    print(f'   📈 Direct deal-empresa matches: {direct_matches}')
    print(f'   📈 Coverage rate: {direct_matches/len(matches)*100:.1f}% of matched companies')

def main():
    """Main execution function"""
    print('🚀 Improved Company Name Matching Analysis')
    print('='*70)
    print('📊 Advanced fuzzy matching with filtering and better algorithms')
    print()
    
    # Reuse previous company data
    from company_name_matching_analysis import get_july_2025_companies
    
    # Step 1: Get HubSpot companies
    companies_data = get_july_2025_companies()
    if not companies_data:
        print('❌ No company data found')
        return False
    
    # Step 2: Get filtered empresa records
    empresa_records = get_filtered_empresa_records()
    if not empresa_records:
        print('❌ No empresa records found')
        return False
    
    # Step 3: Perform improved matching
    matches = perform_improved_matching(companies_data, empresa_records)
    
    # Step 4: Display results
    if matches:
        display_meaningful_matches(matches)
        display_potential_data_links(matches)
        analyze_deal_empresa_coverage(matches, companies_data)
        
        # Save improved report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'improved_company_matching_{timestamp}.json'
        
        report = {
            'analysis_timestamp': timestamp,
            'analysis_date': datetime.now().isoformat(),
            'methodology': 'Improved fuzzy matching with generic term filtering',
            'min_similarity_threshold': 0.6,
            'summary': {
                'total_hubspot_companies': len(companies_data),
                'companies_with_matches': len(matches),
                'exact_matches': len([m for m in matches if m['best_similarity'] >= 0.95]),
                'high_similarity_matches': len([m for m in matches if m['best_similarity'] >= 0.8])
            },
            'matches': matches
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f'\n📄 Improved matching report saved: {filename}')
        print('\n🎉 Improved company name matching analysis completed!')
    else:
        print('\n⚠️  No meaningful matches found')
    
    return True

if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print('\n⚠️  Analysis cancelled by user')
        sys.exit(1)
    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)