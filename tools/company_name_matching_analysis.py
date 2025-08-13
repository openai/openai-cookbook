#!/usr/bin/env python3
"""
Company Name Matching Analysis for July 2025 Closed Won Deals
Performs fuzzy matching between HubSpot company names and Colppy empresa records
"""

import sys
import json
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict

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

def clean_company_name(name: str) -> str:
    """Clean and normalize company name for better matching"""
    if not name:
        return ""
    
    # Convert to lowercase and remove common business suffixes
    name = name.lower().strip()
    
    # Remove common business entity suffixes
    suffixes = [
        r'\s*s\.?a\.?s?\.?$',  # SAS, SA, S.A.S, etc.
        r'\s*s\.?r\.?l\.?$',   # SRL, S.R.L, etc.
        r'\s*s\.?a\.?$',       # SA, S.A.
        r'\s*ltda\.?$',        # LTDA
        r'\s*inc\.?$',         # Inc
        r'\s*corp\.?$',        # Corp
        r'\s*limited$',        # Limited
        r'\s*ltd\.?$',         # Ltd
        r'\s*llc\.?$',         # LLC
        r'\s*sociedad\s+anonima$',
        r'\s*sociedad\s+de\s+responsabilidad\s+limitada$',
        r'\s*fundacion$',
        r'\s*estudio$',
        r'\s*contador$',
        r'\s*contadora$',
        r'\s*cdra?\.?$',
        r'\s*-.*$',            # Remove everything after dash
    ]
    
    for suffix in suffixes:
        name = re.sub(suffix, '', name)
    
    # Remove special characters and extra spaces
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity between two strings using simple ratio"""
    if not str1 or not str2:
        return 0.0
    
    # Simple character-based similarity
    str1_clean = clean_company_name(str1)
    str2_clean = clean_company_name(str2)
    
    if str1_clean == str2_clean:
        return 1.0
    
    # Check if one is contained in the other
    if str1_clean in str2_clean or str2_clean in str1_clean:
        return 0.8
    
    # Check word overlap
    words1 = set(str1_clean.split())
    words2 = set(str2_clean.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    return intersection / union if union > 0 else 0.0

def get_july_2025_companies():
    """Get companies from July 2025 closed won deals"""
    print('🎯 Getting July 2025 Closed Won Deal Companies')
    print('='*50)
    
    try:
        # Get all July 2025 deals
        deals = closed_won_deals_in_july_2025().get_all()
        print(f'✅ Retrieved {len(deals)} closed won deals')
        
        # Get unique company associations
        client = get_client()
        company_deal_map = {}
        unique_company_ids = set()
        
        print('\n🔗 Getting company associations...')
        for i, deal in enumerate(deals, 1):
            deal_id = deal.get('id')
            properties = deal.get('properties', {})
            empresa_id = properties.get('id_empresa', '')
            deal_name = properties.get('dealname', '')
            
            if i % 20 == 0:
                print(f'   Progress: {i}/{len(deals)} deals processed...')
            
            try:
                # Get company association
                response = client.get(f'crm/v4/objects/deals/{deal_id}/associations/companies')
                
                if response and 'results' in response and response['results']:
                    company_id = response['results'][0]['toObjectId']
                    unique_company_ids.add(company_id)
                    
                    if company_id not in company_deal_map:
                        company_deal_map[company_id] = []
                    
                    company_deal_map[company_id].append({
                        'deal_id': deal_id,
                        'deal_name': deal_name,
                        'empresa_id': empresa_id
                    })
                    
            except Exception as e:
                # Silent error handling for efficiency
                pass
        
        print(f'✅ Found {len(unique_company_ids)} unique companies')
        
        # Get company details
        print('\n📋 Getting company details...')
        from hubspot_api.models import Company
        
        companies_data = []
        for i, company_id in enumerate(unique_company_ids, 1):
            if i % 10 == 0:
                print(f'   Progress: {i}/{len(unique_company_ids)} companies processed...')
            
            try:
                company = Company.find_by_id(company_id, properties=[
                    'name', 'cuit', 'domain', 'createdate'
                ])
                
                if company:
                    properties = company.get('properties', {})
                    company_name = properties.get('name', '')
                    
                    if company_name and company_name.strip():
                        companies_data.append({
                            'hubspot_id': company_id,
                            'name': company_name.strip(),
                            'cuit': properties.get('cuit', ''),
                            'domain': properties.get('domain', ''),
                            'deals': company_deal_map.get(company_id, []),
                            'deal_count': len(company_deal_map.get(company_id, []))
                        })
                        
            except Exception as e:
                # Silent error handling
                pass
        
        print(f'✅ Retrieved {len(companies_data)} companies with names')
        return companies_data
        
    except Exception as e:
        print(f'❌ Error: {e}')
        return []

def get_all_empresa_records():
    """Get all empresa records from Colppy database"""
    print('\n🔍 Getting All Empresa Records from Colppy')
    print('='*50)
    
    try:
        # First, let's check what columns are available
        print('   🔍 Checking available columns...')
        columns_query = "SHOW COLUMNS FROM empresa"
        column_results = Empresa.execute_custom_query(columns_query)
        
        available_columns = [row['Field'] for row in column_results]
        print(f'   📋 Available columns: {", ".join(available_columns[:10])}{"..." if len(available_columns) > 10 else ""}')
        
        # Build query with only available columns
        base_columns = ['IdEmpresa', 'CUIT', 'Nombre', 'razonSocial', 'localidad']
        optional_columns = ['telefono', 'email', 'direccion', 'domicilio', 'address']
        
        select_columns = []
        for col in base_columns:
            if col in available_columns:
                select_columns.append(col)
        
        for col in optional_columns:
            if col in available_columns:
                select_columns.append(col)
        
        query = f"""
        SELECT {', '.join(select_columns)}
        FROM empresa 
        WHERE Nombre IS NOT NULL OR razonSocial IS NOT NULL
        ORDER BY IdEmpresa
        """
        
        print('   🔍 Querying empresa records...')
        results = Empresa.execute_custom_query(query)
        
        empresa_records = []
        for row in results:
            empresa_id = str(row.get('IdEmpresa', ''))
            nombre = row.get('Nombre', '') or ''
            razon_social = row.get('razonSocial', '') or ''
            
            # Include record if it has at least one name field
            if nombre.strip() or razon_social.strip():
                # Build record with available fields
                record = {
                    'empresa_id': empresa_id,
                    'nombre': nombre.strip(),
                    'razon_social': razon_social.strip(),
                    'cuit': row.get('CUIT', '') or '',
                    'localidad': row.get('localidad', '') or '',
                }
                
                # Add optional fields if they exist
                for col in ['telefono', 'email', 'direccion', 'domicilio', 'address']:
                    if col in available_columns:
                        record[col] = row.get(col, '') or ''
                
                empresa_records.append(record)
        
        print(f'✅ Retrieved {len(empresa_records)} empresa records with names')
        return empresa_records
        
    except Exception as e:
        print(f'❌ Error querying Colppy: {e}')
        return []

def perform_fuzzy_matching(companies_data: List[Dict], empresa_records: List[Dict], min_similarity: float = 0.3):
    """Perform fuzzy matching between HubSpot companies and Colppy empresas"""
    print(f'\n🔍 Performing Fuzzy Matching (minimum similarity: {min_similarity})')
    print('='*60)
    
    matches = []
    exact_matches = 0
    high_similarity_matches = 0
    moderate_similarity_matches = 0
    
    for i, company in enumerate(companies_data, 1):
        if i % 20 == 0:
            print(f'   Progress: {i}/{len(companies_data)} companies analyzed...')
        
        company_name = company['name']
        best_matches = []
        
        # Compare against both Nombre and razonSocial fields
        for empresa in empresa_records:
            # Check similarity with Nombre field
            if empresa['nombre']:
                similarity_nombre = calculate_similarity(company_name, empresa['nombre'])
                if similarity_nombre >= min_similarity:
                    best_matches.append({
                        'empresa_id': empresa['empresa_id'],
                        'field_matched': 'nombre',
                        'empresa_value': empresa['nombre'],
                        'similarity': similarity_nombre,
                        'empresa_data': empresa
                    })
            
            # Check similarity with razonSocial field
            if empresa['razon_social']:
                similarity_razon = calculate_similarity(company_name, empresa['razon_social'])
                if similarity_razon >= min_similarity:
                    best_matches.append({
                        'empresa_id': empresa['empresa_id'],
                        'field_matched': 'razonSocial',
                        'empresa_value': empresa['razon_social'],
                        'similarity': similarity_razon,
                        'empresa_data': empresa
                    })
        
        # Sort by similarity and keep top matches
        best_matches.sort(key=lambda x: x['similarity'], reverse=True)
        top_matches = best_matches[:5]  # Keep top 5 matches
        
        if top_matches:
            match_data = {
                'hubspot_company': company,
                'matches': top_matches,
                'best_similarity': top_matches[0]['similarity']
            }
            matches.append(match_data)
            
            # Count match quality
            best_sim = top_matches[0]['similarity']
            if best_sim >= 0.9:
                exact_matches += 1
            elif best_sim >= 0.7:
                high_similarity_matches += 1
            elif best_sim >= 0.5:
                moderate_similarity_matches += 1
    
    print(f'\n📊 Matching Results:')
    print(f'   • Companies with matches: {len(matches)}/{len(companies_data)}')
    print(f'   • Exact matches (≥90%): {exact_matches}')
    print(f'   • High similarity (≥70%): {high_similarity_matches}')
    print(f'   • Moderate similarity (≥50%): {moderate_similarity_matches}')
    
    return matches

def display_top_matches(matches: List[Dict], show_count: int = 20):
    """Display top matches in a readable format"""
    print(f'\n📋 TOP {show_count} COMPANY NAME MATCHES')
    print('='*120)
    print('HubSpot Company Name              | Best Match (Field)            | Similarity | Empresa ID | CUIT        | Deals')
    print('-'*120)
    
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
        deal_count = company['deal_count']
        
        print(f'{hubspot_name:<32} | {empresa_value:<25} ({field_name:>6}) | {similarity:>8.1%} | {empresa_id:>10} | {cuit:<11} | {deal_count:>5}')

def display_exact_matches(matches: List[Dict]):
    """Display companies with exact or near-exact matches"""
    exact_matches = [m for m in matches if m['best_similarity'] >= 0.9]
    
    if exact_matches:
        print(f'\n🎯 EXACT/NEAR-EXACT MATCHES ({len(exact_matches)})')
        print('='*100)
        
        for match in exact_matches:
            company = match['hubspot_company']
            best_match = match['matches'][0]
            
            print(f'\n✅ {company["name"]}')
            print(f'   🏢 HubSpot ID: {company["hubspot_id"]} | Deals: {company["deal_count"]}')
            print(f'   🎯 Colppy Match: {best_match["empresa_value"]} (field: {best_match["field_matched"]})')
            print(f'   📊 Empresa ID: {best_match["empresa_id"]} | Similarity: {best_match["similarity"]:.1%}')
            print(f'   💳 CUIT: {best_match["empresa_data"].get("cuit", "N/A")}')
            
            if company['deals']:
                empresa_ids = set(deal['empresa_id'] for deal in company['deals'] if deal['empresa_id'])
                if empresa_ids:
                    print(f'   🔗 Deal Empresa IDs: {", ".join(empresa_ids)}')

def display_potential_issues(matches: List[Dict]):
    """Display potential data issues or interesting findings"""
    print(f'\n⚠️  POTENTIAL DATA ISSUES')
    print('='*60)
    
    # Companies with multiple high-similarity matches
    multi_matches = []
    for match in matches:
        high_sim_matches = [m for m in match['matches'] if m['similarity'] >= 0.7]
        if len(high_sim_matches) > 1:
            multi_matches.append(match)
    
    if multi_matches:
        print(f'\n📋 Companies with Multiple High-Similarity Matches ({len(multi_matches)}):')
        for match in multi_matches[:10]:  # Show top 10
            company = match['hubspot_company']
            print(f'\n🔍 {company["name"]}')
            
            for i, m in enumerate(match['matches'][:3], 1):  # Show top 3 matches
                print(f'   {i}. {m["empresa_value"]} ({m["field_matched"]}) - {m["similarity"]:.1%} - ID: {m["empresa_id"]}')

def save_matching_report(companies_data: List[Dict], matches: List[Dict]):
    """Save detailed matching report"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'company_name_matching_analysis_{timestamp}.json'
    
    report = {
        'analysis_timestamp': timestamp,
        'analysis_date': datetime.now().isoformat(),
        'summary': {
            'total_hubspot_companies': len(companies_data),
            'companies_with_matches': len(matches),
            'exact_matches': len([m for m in matches if m['best_similarity'] >= 0.9]),
            'high_similarity_matches': len([m for m in matches if m['best_similarity'] >= 0.7]),
            'moderate_similarity_matches': len([m for m in matches if m['best_similarity'] >= 0.5])
        },
        'detailed_matches': matches
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f'\n📄 Detailed matching report saved: {filename}')
    return filename

def main():
    """Main execution function"""
    print('🚀 Company Name Matching Analysis for July 2025')
    print('='*70)
    print('📊 Matching HubSpot company names with Colppy empresa records')
    print()
    
    # Step 1: Get HubSpot companies from July 2025 deals
    companies_data = get_july_2025_companies()
    if not companies_data:
        print('❌ No company data found')
        return False
    
    # Step 2: Get all empresa records from Colppy
    empresa_records = get_all_empresa_records()
    if not empresa_records:
        print('❌ No empresa records found')
        return False
    
    # Step 3: Perform fuzzy matching
    matches = perform_fuzzy_matching(companies_data, empresa_records)
    
    # Step 4: Display results
    if matches:
        display_top_matches(matches)
        display_exact_matches(matches)
        display_potential_issues(matches)
        
        # Save detailed report
        save_matching_report(companies_data, matches)
        
        print('\n🎉 Company name matching analysis completed!')
        print(f'📈 Found potential matches for {len(matches)} companies')
    else:
        print('\n⚠️  No matches found above the minimum similarity threshold')
    
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