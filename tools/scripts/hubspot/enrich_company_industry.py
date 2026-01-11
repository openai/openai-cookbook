#!/usr/bin/env python3
"""
🎯 COLPPY COMPANY INDUSTRY ENRICHMENT
Enriches company Industry field based on company name and domain analysis

This script:
1. Fetches companies with NULL Industry from HubSpot
2. Analyzes company name and domain for industry keywords
3. Maps to HubSpot industry enum values
4. Updates HubSpot companies with inferred industry

Usage:
    python enrich_company_industry.py [--company-ids ID1 ID2 ...] [--limit N] [--dry-run]
"""

import pandas as pd
import requests
import os
import argparse
import time
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
import re

# Load environment variables
root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), '.env')
if os.path.exists(root_env):
    load_dotenv(root_env)
else:
    load_dotenv()

HUBSPOT_BASE_URL = "https://api.hubapi.com"

def get_hubspot_api_key():
    """Get HubSpot API key from environment variables"""
    return (
        os.getenv("HUBSPOT_API_KEY") or
        os.getenv("HUBSPOT_ACCESS_TOKEN") or
        os.getenv("HUBSPOT_TOKEN") or
        os.getenv("COLPPY_CRM_AUTOMATIONS") or
        os.getenv("ColppyCRMAutomations")
    )

# Industry keyword mapping to HubSpot industry enum values
INDUSTRY_KEYWORDS = {
    # Technology & IT
    'INFORMATION_TECHNOLOGY_AND_SERVICES': [
        'tech', 'software', 'sistemas', 'informatica', 'it', 'desarrollo', 'programacion',
        'digital', 'solutions', 'soluciones', 'tecnologia', 'tecnologico', 'tecnologica',
        'multimedia', 'comunicacion', 'comunicaciones', 'web', 'internet', 'online',
        'data', 'datos', 'analytics', 'cloud', 'saas', 'platform', 'plataforma'
    ],
    
    # Manufacturing & Industrial
    'MANUFACTURING': [
        'manufactura', 'fabrica', 'produccion', 'industrial', 'taller', 'talleres',
        'maquinaria', 'herramientas', 'equipos', 'manufacturing', 'production'
    ],
    
    # Logistics & Transportation
    'LOGISTICS_AND_SUPPLY_CHAIN': [
        'logistica', 'logistic', 'transporte', 'transport', 'distribucion', 'distribution',
        'envios', 'shipping', 'courier', 'mensajeria', 'almacen', 'warehouse', 'deposito'
    ],
    
    # Agriculture
    'AGRICULTURE': [
        'agro', 'agricola', 'agriculture', 'agropecuario', 'agroval', 'campo', 'rural'
    ],
    
    # Food & Beverage
    'FOOD_AND_BEVERAGE': [
        'alimentos', 'food', 'bebidas', 'beverage', 'restaurant', 'restaurante',
        'catering', 'gastronomia', 'gastronomico', 'comida', 'cocina'
    ],
    
    # Construction & Real Estate
    'CONSTRUCTION': [
        'construccion', 'construction', 'obra', 'obras', 'arquitectura', 'arquitecto',
        'ingenieria', 'ingeniero', 'inmobiliaria', 'real estate', 'desarrollo inmobiliario'
    ],
    
    # Retail & E-commerce
    'RETAIL': [
        'retail', 'comercio', 'tienda', 'store', 'shop', 'venta', 'sales', 'comercial',
        'distribuidor', 'distribuidora', 'mayorista', 'minorista'
    ],
    
    # Professional Services
    'PROFESSIONAL_SERVICES': [
        'servicios', 'services', 'consultoria', 'consulting', 'asesoria', 'asesor',
        'consultor', 'profesional', 'professional', 'estudio', 'estudios'
    ],
    
    # Healthcare
    'HEALTHCARE': [
        'salud', 'health', 'medico', 'medical', 'clinica', 'clinic', 'hospital',
        'farmaceutico', 'pharmaceutical', 'farmacia', 'pharmacy'
    ],
    
    # Education
    'EDUCATION': [
        'educacion', 'education', 'escuela', 'school', 'colegio', 'universidad',
        'universidad', 'academia', 'academy', 'instituto', 'institute'
    ],
    
    # Financial Services
    'FINANCIAL_SERVICES': [
        'financiero', 'financial', 'banco', 'bank', 'credito', 'credit', 'prestamo',
        'loan', 'inversion', 'investment', 'finanzas', 'finance'
    ],
    
    # Legal Services
    'LEGAL_SERVICES': [
        'legal', 'abogado', 'abogados', 'juridico', 'juridica', 'estudio juridico',
        'law', 'lawyer', 'attorney', 'justicia', 'legal services'
    ],
    
    # Marketing & Advertising
    'MARKETING_AND_ADVERTISING': [
        'marketing', 'publicidad', 'advertising', 'publicidad', 'comunicacion',
        'agencia', 'agency', 'publicitaria', 'advertising agency'
    ],
    
    # Hospitality & Tourism
    'HOSPITALITY': [
        'hotel', 'hospedaje', 'turismo', 'tourism', 'viajes', 'travel', 'turismo',
        'hospedaje', 'alojamiento', 'accommodation'
    ],
    
    # Automotive
    'AUTOMOTIVE': [
        'automotor', 'automotive', 'auto', 'vehiculo', 'vehicle', 'automovil',
        'concesionario', 'dealer', 'taller mecanico', 'repuestos'
    ],
    
    # Energy & Utilities
    'ENERGY': [
        'energia', 'energy', 'electricidad', 'electric', 'gas', 'petroleo', 'oil',
        'combustible', 'fuel', 'utilities', 'servicios publicos'
    ],
    
    # Textiles & Apparel
    'TEXTILES': [
        'textil', 'textile', 'moda', 'fashion', 'ropa', 'clothing', 'indumentaria',
        'confeccion', 'manufacturing'
    ],
    
    # Chemicals
    'CHEMICALS': [
        'quimico', 'chemical', 'quimica', 'chemistry', 'laboratorio', 'laboratory'
    ],
    
    # Media & Entertainment
    'MEDIA_PRODUCTION': [
        'media', 'produccion', 'production', 'entretenimiento', 'entertainment',
        'cine', 'cinema', 'television', 'tv', 'radio', 'musica', 'music'
    ],
    
    # Non-profit
    'NON_PROFIT': [
        'ong', 'fundacion', 'foundation', 'asociacion', 'association', 'cooperativa',
        'cooperative', 'sin fines de lucro', 'non profit'
    ]
}

def infer_industry_from_text(text: str) -> Optional[str]:
    """
    Infer industry from company name or domain using keyword matching
    
    Args:
        text: Company name or domain to analyze
        
    Returns:
        HubSpot industry enum value or None
    """
    if not text or not isinstance(text, str):
        return None
    
    text_lower = text.lower().strip()
    
    # Score each industry based on keyword matches
    industry_scores = {}
    
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in text_lower:
                score += 1
        
        if score > 0:
            industry_scores[industry] = score
    
    if not industry_scores:
        return None
    
    # Return industry with highest score
    best_industry = max(industry_scores.items(), key=lambda x: x[1])
    return best_industry[0] if best_industry[1] > 0 else None

def get_companies_with_null_industry(api_key: str, limit: int = 100) -> List[Dict]:
    """
    Fetch companies with NULL Industry field from HubSpot
    
    Args:
        api_key: HubSpot API key
        limit: Maximum number of companies to fetch
        
    Returns:
        List of company dictionaries
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Search for companies with NULL or empty industry
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/search"
    
    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "industry",
                        "operator": "NOT_HAS_PROPERTY"
                    }
                ]
            },
            {
                "filters": [
                    {
                        "propertyName": "industry",
                        "operator": "EQ",
                        "value": ""
                    }
                ]
            }
        ],
        "properties": ["name", "domain", "industry", "type"],
        "limit": limit
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data.get('results', [])
        else:
            print(f"⚠️  Error fetching companies: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return []

def get_companies_by_ids(company_ids: List[str], api_key: str) -> List[Dict]:
    """
    Fetch specific companies by IDs
    
    Args:
        company_ids: List of company IDs
        api_key: HubSpot API key
        
    Returns:
        List of company dictionaries
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    companies = []
    
    for company_id in company_ids:
        url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/{company_id}"
        params = {"properties": "name,domain,industry,type"}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                companies.append(response.json())
            time.sleep(0.1)  # Rate limiting
        except Exception as e:
            print(f"⚠️  Error fetching company {company_id}: {str(e)}")
    
    return companies

def update_company_industry(company_id: str, industry: str, api_key: str, dry_run: bool = False) -> bool:
    """
    Update company Industry field in HubSpot
    
    Args:
        company_id: HubSpot company ID
        industry: Industry enum value to set
        api_key: HubSpot API key
        dry_run: If True, don't actually update
        
    Returns:
        True if successful, False otherwise
    """
    if dry_run:
        print(f"   [DRY RUN] Would update company {company_id} with industry: {industry}")
        return True
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/{company_id}"
    payload = {
        "properties": {
            "industry": industry
        }
    }
    
    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return True
        else:
            print(f"   ⚠️  Error updating company {company_id}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"   ⚠️  Error updating company {company_id}: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Enrich company Industry field in HubSpot')
    parser.add_argument('--company-ids', nargs='+', help='Specific company IDs to process')
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of companies to process')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (don\'t update HubSpot)')
    
    args = parser.parse_args()
    
    api_key = get_hubspot_api_key()
    if not api_key:
        print("❌ HubSpot API key not found")
        return
    
    print("=" * 70)
    print("COMPANY INDUSTRY ENRICHMENT")
    print("=" * 70)
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made to HubSpot\n")
    
    # Get companies to process
    if args.company_ids:
        print(f"📋 Processing {len(args.company_ids)} specific companies...")
        companies = get_companies_by_ids(args.company_ids, api_key)
    else:
        print(f"📋 Fetching companies with NULL Industry (limit: {args.limit})...")
        companies = get_companies_with_null_industry(api_key, args.limit)
    
    if not companies:
        print("✅ No companies found to process")
        return
    
    print(f"✅ Found {len(companies)} companies to process\n")
    
    # Process each company
    results = {
        'updated': 0,
        'skipped': 0,
        'failed': 0,
        'details': []
    }
    
    for company in companies:
        company_id = company.get('id')
        props = company.get('properties', {})
        company_name = props.get('name', 'Unknown')
        domain = props.get('domain', '')
        current_industry = props.get('industry', '')
        
        # Skip if already has industry
        if current_industry and current_industry.strip() != '':
            results['skipped'] += 1
            continue
        
        # Infer industry from name and domain
        inferred_industry = None
        
        # Try company name first
        if company_name:
            inferred_industry = infer_industry_from_text(company_name)
        
        # If not found, try domain
        if not inferred_industry and domain:
            inferred_industry = infer_industry_from_text(domain)
        
        if inferred_industry:
            print(f"🏢 {company_name}")
            print(f"   📋 Company ID: {company_id}")
            print(f"   🏭 Inferred Industry: {inferred_industry}")
            print(f"   🌐 Domain: {domain if domain else 'N/A'}")
            
            success = update_company_industry(company_id, inferred_industry, api_key, args.dry_run)
            
            if success:
                results['updated'] += 1
                results['details'].append({
                    'company_id': company_id,
                    'company_name': company_name,
                    'inferred_industry': inferred_industry,
                    'status': 'updated'
                })
                print(f"   ✅ Updated successfully\n")
            else:
                results['failed'] += 1
                results['details'].append({
                    'company_id': company_id,
                    'company_name': company_name,
                    'inferred_industry': inferred_industry,
                    'status': 'failed'
                })
                print(f"   ❌ Update failed\n")
        else:
            results['skipped'] += 1
            results['details'].append({
                'company_id': company_id,
                'company_name': company_name,
                'inferred_industry': None,
                'status': 'could_not_infer'
            })
            print(f"🏢 {company_name}")
            print(f"   ⚠️  Could not infer industry from name/domain\n")
        
        time.sleep(0.1)  # Rate limiting
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\n✅ Updated: {results['updated']}")
    print(f"⚠️  Skipped: {results['skipped']}")
    print(f"❌ Failed: {results['failed']}")
    print(f"\n💾 Total processed: {len(companies)}")
    
    # Save results to CSV
    if results['details']:
        df_results = pd.DataFrame(results['details'])
        output_file = f"tools/outputs/company_industry_enrichment_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        df_results.to_csv(output_file, index=False)
        print(f"\n💾 Results saved to: {output_file}")

if __name__ == "__main__":
    main()

