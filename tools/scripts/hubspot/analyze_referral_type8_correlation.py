#!/usr/bin/env python3
# Suppress urllib3 OpenSSL/LibreSSL compatibility warning (harmless) - MUST be before any imports
import warnings
warnings.filterwarnings('ignore')
# Also suppress urllib3 warnings specifically
try:
    import urllib3
    urllib3.disable_warnings()
except ImportError:
    pass

"""
REFERRAL LEAD SOURCE AND TYPE 8 CORRELATION ANALYSIS
====================================================

Analyzes the correlation between:
1. lead_source = 'Referencia Externa Contador' (internal name in HubSpot)
2. Association Type 8 (Accountant association: "Estudio Contable / Asesor / Consultor Externo del negocio")

This analysis helps validate the business logic assumption that deals with
'Referencia Externa Contador' lead source are referred by accountants (type 8).

The script also checks association type 2 (referrer) for comparison, even though
it's not reliably used by salespeople.

Usage:
  python analyze_referral_type8_correlation.py --month 2025-12
  python analyze_referral_type8_correlation.py --start-date 2025-12-01 --end-date 2026-01-01
"""

import os
import sys
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import argparse
import time

load_dotenv()

HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    raise ValueError("HUBSPOT_API_KEY environment variable is required")

HUBSPOT_BASE_URL = 'https://api.hubapi.com'
HEADERS = {
    'Authorization': f'Bearer {HUBSPOT_API_KEY}',
    'Content-Type': 'application/json'
}

# Lead source value we're analyzing
# Note: Internal name is "Referencia Externa Contador" (not "Referencia Externa Directa")
REFERRAL_LEAD_SOURCE = 'Referencia Externa Contador'

# Association type IDs
ACCOUNTANT_ASSOCIATION_TYPE_ID = 8  # "Estudio Contable / Asesor / Consultor Externo del negocio"
REFERRER_ASSOCIATION_TYPE_ID = 2    # "Compañía que refiere al negocio" (for comparison)

def get_deal_companies_with_association_type(deal_id, association_type_id):
    """
    Get companies associated with a deal that have a specific association type.
    
    Returns:
        List of company IDs with the specified association type
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/companies"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            company_ids = []
            for assoc in associations:
                for assoc_type in assoc.get('associationTypes', []):
                    if assoc_type.get('typeId') == association_type_id:
                        company_ids.append(assoc.get('toObjectId'))
            return company_ids
    except Exception as e:
        print(f"   ⚠️  Error fetching companies for deal {deal_id}: {str(e)}")
    return []

def get_company_details(company_id):
    """Get company name and type"""
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/{company_id}"
    params = {'properties': 'name,type'}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if response.status_code == 200:
            props = response.json().get('properties', {})
            return props.get('name'), props.get('type')
    except:
        pass
    return None, None

def analyze_correlation(start_date, end_date):
    """
    Analyze correlation between lead_source = 'Referencia Externa Contador' and type 8 association.
    
    TEMPORARY: Also includes analysis of lead sources for all deals with Type 8 association
    (to be removed after review - see TODO comments in code)
    """
    # Validate date range
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    print(f"\n{'='*80}")
    print(f"CORRELATION ANALYSIS: Referencia Externa Contador vs Type 8 Association")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    # ========================================================================
    # STEP 1: Fetch All Deals with 'Referencia Externa Contador'
    # ========================================================================
    print("📊 STEP 1: Fetching deals with lead_source = 'Referencia Externa Contador'...")
    print(f"   Period: Deals CREATED between {start_date} and {end_date}")
    print()
    
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    
    all_deals_with_source = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "lead_source", "operator": "EQ", "value": REFERRAL_LEAD_SOURCE}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "lead_source"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_deals_with_source.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    total_deals = len(all_deals_with_source)
    print(f"   Found {total_deals} deals with lead_source = '{REFERRAL_LEAD_SOURCE}'")
    print()
    
    if total_deals == 0:
        print("⚠️  No deals found with this lead source in this period.")
        return None
    
    # ========================================================================
    # STEP 2: Check Association Types for Each Deal
    # ========================================================================
    print("📊 STEP 2: Checking association types for each deal...")
    print("   Checking Type 8 (Accountant) and Type 2 (Referrer) associations...")
    print()
    
    deal_id_to_deal = {deal.get('id'): deal for deal in all_deals_with_source}
    
    deals_with_type8 = []
    deals_with_type2 = []
    deals_with_both_types = []
    deals_with_neither = []
    
    deal_details = []
    
    for i, deal in enumerate(all_deals_with_source, 1):
        if i % 50 == 0:
            print(f"      Processing deal {i}/{total_deals}...")
        
        deal_id = deal.get('id')
        props = deal.get('properties', {})
        deal_name = props.get('dealname', 'N/A')
        
        # Check Type 8 (Accountant)
        type8_companies = get_deal_companies_with_association_type(deal_id, ACCOUNTANT_ASSOCIATION_TYPE_ID)
        has_type8 = len(type8_companies) > 0
        
        # Check Type 2 (Referrer)
        type2_companies = get_deal_companies_with_association_type(deal_id, REFERRER_ASSOCIATION_TYPE_ID)
        has_type2 = len(type2_companies) > 0
        
        # Classify deal
        if has_type8 and has_type2:
            deals_with_both_types.append(deal_id)
            category = 'BOTH'
        elif has_type8:
            deals_with_type8.append(deal_id)
            category = 'TYPE_8_ONLY'
        elif has_type2:
            deals_with_type2.append(deal_id)
            category = 'TYPE_2_ONLY'
        else:
            deals_with_neither.append(deal_id)
            category = 'NEITHER'
        
        deal_details.append({
            'deal_id': deal_id,
            'deal_name': deal_name,
            'has_type8': has_type8,
            'has_type2': has_type2,
            'type8_count': len(type8_companies),
            'type2_count': len(type2_companies),
            'category': category
        })
        
        time.sleep(0.05)  # Rate limiting
    
    print()
    
    # ========================================================================
    # STEP 3: Calculate Statistics
    # ========================================================================
    print("📊 STEP 3: Calculating correlation statistics...")
    print()
    
    type8_only_count = len(deals_with_type8)
    type2_only_count = len(deals_with_type2)
    both_count = len(deals_with_both_types)
    neither_count = len(deals_with_neither)
    
    total_with_type8 = type8_only_count + both_count
    total_with_type2 = type2_only_count + both_count
    
    type8_percentage = (total_with_type8 / total_deals * 100) if total_deals > 0 else 0
    type2_percentage = (total_with_type2 / total_deals * 100) if total_deals > 0 else 0
    both_percentage = (both_count / total_deals * 100) if total_deals > 0 else 0
    neither_percentage = (neither_count / total_deals * 100) if total_deals > 0 else 0
    
    # ========================================================================
    # ADDITIONAL ANALYSIS: Lead Sources for Deals with Type 8 (All Lead Sources)
    # ========================================================================
    # TODO: TEMPORARY ANALYSIS - REMOVE AFTER REVIEW
    # This section analyzes what lead sources are used for deals with Type 8 association
    # (regardless of whether they have 'Referencia Externa Contador' or not)
    # This is a temporary analysis to understand lead source distribution for accountant deals
    # ========================================================================
    print("="*80)
    print("ADDITIONAL ANALYSIS: Lead Sources for Deals with Type 8 Association")
    print("(TEMPORARY - TO BE REMOVED)")
    print("="*80)
    print()
    print("This section shows what lead sources are used for deals that have")
    print("Type 8 (accountant association), regardless of whether they have")
    print("'Referencia Externa Contador' or not.")
    print()
    
    # Fetch all deals with Type 8 in the period
    print("📊 Fetching all deals with Type 8 association in period...")
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    
    all_deals_with_type8 = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "createdate", "lead_source"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_deals_with_type8.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    print(f"   Found {len(all_deals_with_type8)} total deals in period")
    print("   Checking which ones have Type 8 association...")
    
    # Check each deal for Type 8
    deals_with_type8_all = []
    lead_source_distribution = {}
    
    for i, deal in enumerate(all_deals_with_type8, 1):
        if i % 100 == 0:
            print(f"      Checking deal {i}/{len(all_deals_with_type8)}...")
        deal_id = deal.get('id')
        type8_companies = get_deal_companies_with_association_type(deal_id, ACCOUNTANT_ASSOCIATION_TYPE_ID)
        
        if len(type8_companies) > 0:
            deals_with_type8_all.append(deal)
            props = deal.get('properties', {})
            lead_source = props.get('lead_source', 'NULL/EMPTY')
            if lead_source and lead_source.strip():
                lead_source = lead_source.strip()
            else:
                lead_source = 'NULL/EMPTY'
            
            if lead_source not in lead_source_distribution:
                lead_source_distribution[lead_source] = 0
            lead_source_distribution[lead_source] += 1
        
        time.sleep(0.05)  # Rate limiting
    
    print(f"   Found {len(deals_with_type8_all)} deals with Type 8 association")
    print()
    
    # Sort by count
    sorted_sources = sorted(lead_source_distribution.items(), key=lambda x: x[1], reverse=True)
    total_type8_deals = len(deals_with_type8_all)
    
    print("="*80)
    print("LEAD SOURCE DISTRIBUTION FOR DEALS WITH TYPE 8 ASSOCIATION")
    print("="*80)
    print()
    print(f"**Total Deals with Type 8 (Accountant) Association:** {total_type8_deals}")
    print()
    print("| Lead Source | Count | Percentage |")
    print("|-------------|-------|------------|")
    for lead_source, count in sorted_sources:
        percentage = (count / total_type8_deals * 100) if total_type8_deals > 0 else 0
        print(f"| {lead_source} | {count} | {percentage:.1f}% |")
    print()
    
    # Show Referencia Externa Contador vs Others
    referencia_contador_count = lead_source_distribution.get('Referencia Externa Contador', 0)
    other_count = total_type8_deals - referencia_contador_count
    referencia_contador_pct = (referencia_contador_count / total_type8_deals * 100) if total_type8_deals > 0 else 0
    other_pct = (other_count / total_type8_deals * 100) if total_type8_deals > 0 else 0
    
    print("**Summary:**")
    print(f"- 'Referencia Externa Contador': {referencia_contador_count} deals ({referencia_contador_pct:.1f}%)")
    print(f"- Other lead sources: {other_count} deals ({other_pct:.1f}%)")
    print()
    
    # ========================================================================
    # ADDITIONAL ANALYSIS: Other Indicators for Accountant Referral
    # ========================================================================
    # TODO: TEMPORARY ANALYSIS - REMOVE AFTER REVIEW
    # This section analyzes other deal properties and contact associations
    # that could indicate accountant referral (beyond association labels)
    # ========================================================================
    print("="*80)
    print("ADDITIONAL ANALYSIS: Other Indicators for Accountant Referral")
    print("(TEMPORARY - TO BE REMOVED)")
    print("="*80)
    print()
    print("For deals with lead_source = 'Referencia Externa Contador',")
    print("this section analyzes other properties/associations that could")
    print("indicate the referral is from an accountant.")
    print()
    
    # Analyze deals with 'Referencia Externa Contador'
    print("📊 Analyzing deals with 'Referencia Externa Contador' lead source...")
    
    # We already have all_deals_with_source from earlier
    referral_deal_indicators = {
        'colppy_es_referido_del_contador': {'true': 0, 'false': 0, 'null': 0},
        'colppy_quien_lo_refirio': {'has_value': 0, 'null': 0},
        'accountant_channel_involucrado_en_la_venta': {'true': 0, 'false': 0, 'null': 0},
        'tiene_cuenta_contador': {'has_value_gt_0': 0, 'zero': 0, 'null': 0},
        'contact_influenciador_contador': 0,  # Type 54
        'contact_refiere': 0,  # Type 4
        'contact_es_contador': 0,  # Contact has es_contador = true
        'contact_rol_wizard_contador': 0,  # Contact has rol_wizard containing "contador"
    }
    
    # Contact association type IDs
    INFLUENCIADOR_CONTADOR_TYPE_ID = 54  # "Influenciador Contador"
    REFIERE_TYPE_ID = 4  # "Refiere"
    
    def get_deal_contacts_with_association_type(deal_id, association_type_id):
        """Get contacts associated with a deal that have a specific association type."""
        url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/contacts"
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            if response.status_code == 200:
                associations = response.json().get('results', [])
                contact_ids = []
                for assoc in associations:
                    for assoc_type in assoc.get('associationTypes', []):
                        if assoc_type.get('typeId') == association_type_id:
                            contact_ids.append(assoc.get('toObjectId'))
                return contact_ids
        except:
            pass
        return []
    
    def get_contact_properties(contact_id):
        """Get contact properties: es_contador, rol_wizard"""
        url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}"
        params = {'properties': 'es_contador,rol_wizard'}
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=30)
            if response.status_code == 200:
                props = response.json().get('properties', {})
                return props.get('es_contador'), props.get('rol_wizard')
        except:
            pass
        return None, None
    
    for i, deal in enumerate(all_deals_with_source, 1):
        if i % 20 == 0:
            print(f"      Analyzing deal {i}/{total_deals}...")
        
        props = deal.get('properties', {})
        deal_id = deal.get('id')
        
        # Check deal properties
        colppy_es_referido = props.get('colppy_es_referido_del_contador', '')
        if colppy_es_referido == 'true':
            referral_deal_indicators['colppy_es_referido_del_contador']['true'] += 1
        elif colppy_es_referido == 'false' or colppy_es_referido == '':
            referral_deal_indicators['colppy_es_referido_del_contador']['false'] += 1
        else:
            referral_deal_indicators['colppy_es_referido_del_contador']['null'] += 1
        
        colppy_quien_refirio = props.get('colppy_quien_lo_refirio', '')
        if colppy_quien_refirio and colppy_quien_refirio.strip():
            referral_deal_indicators['colppy_quien_lo_refirio']['has_value'] += 1
        else:
            referral_deal_indicators['colppy_quien_lo_refirio']['null'] += 1
        
        accountant_channel = props.get('accountant_channel_involucrado_en_la_venta', '')
        if accountant_channel == 'true':
            referral_deal_indicators['accountant_channel_involucrado_en_la_venta']['true'] += 1
        elif accountant_channel == 'false':
            referral_deal_indicators['accountant_channel_involucrado_en_la_venta']['false'] += 1
        else:
            referral_deal_indicators['accountant_channel_involucrado_en_la_venta']['null'] += 1
        
        tiene_cuenta = props.get('tiene_cuenta_contador', '')
        try:
            tiene_cuenta_num = int(tiene_cuenta) if tiene_cuenta else 0
            if tiene_cuenta_num > 0:
                referral_deal_indicators['tiene_cuenta_contador']['has_value_gt_0'] += 1
            else:
                referral_deal_indicators['tiene_cuenta_contador']['zero'] += 1
        except:
            referral_deal_indicators['tiene_cuenta_contador']['null'] += 1
        
        # Check contact associations
        influenciador_contador_contacts = get_deal_contacts_with_association_type(deal_id, INFLUENCIADOR_CONTADOR_TYPE_ID)
        if influenciador_contador_contacts:
            referral_deal_indicators['contact_influenciador_contador'] += 1
        
        refiere_contacts = get_deal_contacts_with_association_type(deal_id, REFIERE_TYPE_ID)
        if refiere_contacts:
            referral_deal_indicators['contact_refiere'] += 1
        
        # Check all associated contacts for es_contador and rol_wizard
        all_contact_ids = []
        url_contacts = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/contacts"
        try:
            response = requests.get(url_contacts, headers=HEADERS, timeout=30)
            if response.status_code == 200:
                associations = response.json().get('results', [])
                all_contact_ids = [assoc.get('toObjectId') for assoc in associations]
        except:
            pass
        
        # Check first few contacts for accountant indicators (to avoid too many API calls)
        for contact_id in all_contact_ids[:5]:  # Limit to first 5 contacts per deal
            es_contador, rol_wizard = get_contact_properties(contact_id)
            if es_contador == 'true':
                referral_deal_indicators['contact_es_contador'] += 1
                break  # Count once per deal
            if rol_wizard and 'contador' in str(rol_wizard).lower():
                referral_deal_indicators['contact_rol_wizard_contador'] += 1
                break  # Count once per deal
        
        time.sleep(0.05)  # Rate limiting
    
    print()
    
    # Print results
    print("="*80)
    print("OTHER INDICATORS FOR ACCOUNTANT REFERRAL")
    print("="*80)
    print()
    print(f"**Total Deals with 'Referencia Externa Contador': {total_deals}**")
    print()
    
    print("**Deal Properties:**")
    print()
    print("| Property | Indicator | Count | Percentage |")
    print("|----------|-----------|-------|------------|")
    
    colppy_ref = referral_deal_indicators['colppy_es_referido_del_contador']
    colppy_ref_true_pct = (colppy_ref['true'] / total_deals * 100) if total_deals > 0 else 0
    print(f"| colppy_es_referido_del_contador | = 'true' | {colppy_ref['true']} | {colppy_ref_true_pct:.1f}% |")
    print(f"| colppy_es_referido_del_contador | = 'false' or empty | {colppy_ref['false']} | {(colppy_ref['false'] / total_deals * 100) if total_deals > 0 else 0:.1f}% |")
    
    quien_ref = referral_deal_indicators['colppy_quien_lo_refirio']
    quien_ref_pct = (quien_ref['has_value'] / total_deals * 100) if total_deals > 0 else 0
    print(f"| colppy_quien_lo_refirio | Has value | {quien_ref['has_value']} | {quien_ref_pct:.1f}% |")
    
    acc_channel = referral_deal_indicators['accountant_channel_involucrado_en_la_venta']
    acc_channel_true_pct = (acc_channel['true'] / total_deals * 100) if total_deals > 0 else 0
    print(f"| accountant_channel_involucrado_en_la_venta | = 'true' | {acc_channel['true']} | {acc_channel_true_pct:.1f}% |")
    
    tiene_cuenta = referral_deal_indicators['tiene_cuenta_contador']
    tiene_cuenta_gt0_pct = (tiene_cuenta['has_value_gt_0'] / total_deals * 100) if total_deals > 0 else 0
    print(f"| tiene_cuenta_contador | > 0 | {tiene_cuenta['has_value_gt_0']} | {tiene_cuenta_gt0_pct:.1f}% |")
    
    print()
    print("**Contact Associations:**")
    print()
    print("| Association Type | Count | Percentage |")
    print("|------------------|-------|------------|")
    
    influ_pct = (referral_deal_indicators['contact_influenciador_contador'] / total_deals * 100) if total_deals > 0 else 0
    print(f"| Influenciador Contador (Type 54) | {referral_deal_indicators['contact_influenciador_contador']} | {influ_pct:.1f}% |")
    
    refiere_pct = (referral_deal_indicators['contact_refiere'] / total_deals * 100) if total_deals > 0 else 0
    print(f"| Refiere (Type 4) | {referral_deal_indicators['contact_refiere']} | {refiere_pct:.1f}% |")
    
    print()
    print("**Contact Properties (from associated contacts):**")
    print()
    print("| Contact Property | Count | Percentage |")
    print("|------------------|-------|------------|")
    
    es_cont_pct = (referral_deal_indicators['contact_es_contador'] / total_deals * 100) if total_deals > 0 else 0
    print(f"| es_contador = true | {referral_deal_indicators['contact_es_contador']} | {es_cont_pct:.1f}% |")
    
    rol_wiz_pct = (referral_deal_indicators['contact_rol_wizard_contador'] / total_deals * 100) if total_deals > 0 else 0
    print(f"| rol_wizard contains 'contador' | {referral_deal_indicators['contact_rol_wizard_contador']} | {rol_wiz_pct:.1f}% |")
    
    print()
    print("**Key Findings:**")
    print()
    
    # Find the most reliable indicators
    indicators_ranked = [
        ('colppy_es_referido_del_contador = true', colppy_ref['true'], colppy_ref_true_pct),
        ('colppy_quien_lo_refirio has value', quien_ref['has_value'], quien_ref_pct),
        ('accountant_channel_involucrado_en_la_venta = true', acc_channel['true'], acc_channel_true_pct),
        ('tiene_cuenta_contador > 0', tiene_cuenta['has_value_gt_0'], tiene_cuenta_gt0_pct),
        ('Contact: Influenciador Contador (Type 54)', referral_deal_indicators['contact_influenciador_contador'], influ_pct),
        ('Contact: Refiere (Type 4)', referral_deal_indicators['contact_refiere'], refiere_pct),
        ('Contact: es_contador = true', referral_deal_indicators['contact_es_contador'], es_cont_pct),
        ('Contact: rol_wizard contains contador', referral_deal_indicators['contact_rol_wizard_contador'], rol_wiz_pct),
    ]
    
    indicators_ranked.sort(key=lambda x: x[1], reverse=True)
    
    print("Most common indicators (by count):")
    for indicator, count, pct in indicators_ranked[:5]:
        if count > 0:
            print(f"  - {indicator}: {count} deals ({pct:.1f}%)")
    print()
    
    # ========================================================================
    # Print Results (Original Analysis)
    # ========================================================================
    print("="*80)
    print("CORRELATION RESULTS")
    print("="*80)
    print()
    print(f"**Total Deals with lead_source = 'Referencia Externa Contador': {total_deals}**")
    print()
    
    print("| Association Type | Count | Percentage |")
    print("|------------------|-------|------------|")
    print(f"| Type 8 (Accountant) | {total_with_type8} | {type8_percentage:.1f}% |")
    print(f"| Type 2 (Referrer) | {total_with_type2} | {type2_percentage:.1f}% |")
    print(f"| **BOTH (Type 8 + Type 2)** | **{both_count}** | **{both_percentage:.1f}%** |")
    print(f"| **NEITHER** | **{neither_count}** | **{neither_percentage:.1f}%** |")
    print()
    
    print("="*80)
    print("BREAKDOWN BY COMBINATION")
    print("="*80)
    print()
    print("| Combination | Count | Percentage |")
    print("|-------------|-------|------------|")
    type8_only_pct = (type8_only_count / total_deals * 100) if total_deals > 0 else 0
    type2_only_pct = (type2_only_count / total_deals * 100) if total_deals > 0 else 0
    print(f"| Type 8 ONLY (no Type 2) | {type8_only_count} | {type8_only_pct:.1f}% |")
    print(f"| Type 2 ONLY (no Type 8) | {type2_only_count} | {type2_only_pct:.1f}% |")
    print(f"| BOTH Type 8 AND Type 2 | {both_count} | {both_percentage:.1f}% |")
    print(f"| NEITHER Type 8 nor Type 2 | {neither_count} | {neither_percentage:.1f}% |")
    print()
    
    # ========================================================================
    # Key Insights
    # ========================================================================
    print("="*80)
    print("KEY INSIGHTS")
    print("="*80)
    print()
    print(f"✅ **Type 8 Alignment:** {type8_percentage:.1f}% of deals with 'Referencia Externa Contador'")
    print(f"   have Type 8 (Accountant) association")
    print()
    print(f"❌ **Type 2 Alignment:** {type2_percentage:.1f}% of deals with 'Referencia Externa Contador'")
    print(f"   have Type 2 (Referrer) association")
    print()
    
    if type8_percentage >= 70:
        print("✅ **STRONG CORRELATION:** Type 8 is strongly aligned with 'Referencia Externa Contador'")
        print("   This supports using Type 8 as a proxy for accountant referrals.")
    elif type8_percentage >= 50:
        print("⚠️  **MODERATE CORRELATION:** Type 8 is moderately aligned with 'Referencia Externa Contador'")
        print("   There's some support for using Type 8 as a proxy, but not all deals have it.")
    else:
        print("❌ **WEAK CORRELATION:** Type 8 is weakly aligned with 'Referencia Externa Contador'")
        print("   Using Type 8 as a proxy may miss many referral deals.")
    print()
    
    if type2_percentage < 30:
        print(f"⚠️  **Type 2 Usage is Low:** {type2_percentage:.1f}% confirms that Type 2 is not")
        print("   reliably used by salespeople, supporting the decision to use Type 8 instead.")
    print()
    
    # ========================================================================
    # Sample Deals (for inspection)
    # ========================================================================
    print("="*80)
    print("SAMPLE DEALS (First 10 of each category)")
    print("="*80)
    print()
    
    df_deals = pd.DataFrame(deal_details)
    
    # Type 8 only
    type8_only_deals = df_deals[df_deals['category'] == 'TYPE_8_ONLY'].head(10)
    if len(type8_only_deals) > 0:
        print(f"**Type 8 ONLY ({len(type8_only_deals)} shown of {type8_only_count} total):**")
        for idx, row in type8_only_deals.iterrows():
            print(f"  - {row['deal_name']} (Deal ID: {row['deal_id']}, Type 8 companies: {row['type8_count']})")
        print()
    
    # Type 2 only
    type2_only_deals = df_deals[df_deals['category'] == 'TYPE_2_ONLY'].head(10)
    if len(type2_only_deals) > 0:
        print(f"**Type 2 ONLY ({len(type2_only_deals)} shown of {type2_only_count} total):**")
        for idx, row in type2_only_deals.iterrows():
            print(f"  - {row['deal_name']} (Deal ID: {row['deal_id']}, Type 2 companies: {row['type2_count']})")
        print()
    
    # Both
    both_deals = df_deals[df_deals['category'] == 'BOTH'].head(10)
    if len(both_deals) > 0:
        print(f"**BOTH Type 8 AND Type 2 ({len(both_deals)} shown of {both_count} total):**")
        for idx, row in both_deals.iterrows():
            print(f"  - {row['deal_name']} (Deal ID: {row['deal_id']}, Type 8: {row['type8_count']}, Type 2: {row['type2_count']})")
        print()
    
    # Neither
    neither_deals = df_deals[df_deals['category'] == 'NEITHER'].head(10)
    if len(neither_deals) > 0:
        print(f"**NEITHER ({len(neither_deals)} shown of {neither_count} total):**")
        for idx, row in neither_deals.iterrows():
            print(f"  - {row['deal_name']} (Deal ID: {row['deal_id']})")
        print()
    
    # ========================================================================
    # Save to CSV
    # ========================================================================
    output_dir = "tools/outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    # Summary CSV
    summary_data = {
        'Period': [f"{start_date} to {end_date}"],
        'Total_Deals_Referencia_Externa_Directa': [total_deals],
        'With_Type8_Count': [total_with_type8],
        'With_Type8_Percentage': [round(type8_percentage, 2)],
        'With_Type2_Count': [total_with_type2],
        'With_Type2_Percentage': [round(type2_percentage, 2)],
        'With_BOTH_Count': [both_count],
        'With_BOTH_Percentage': [round(both_percentage, 2)],
        'With_NEITHER_Count': [neither_count],
        'With_NEITHER_Percentage': [round(neither_percentage, 2)],
        'Type8_Only_Count': [type8_only_count],
        'Type8_Only_Percentage': [round(type8_only_pct, 2)],
        'Type2_Only_Count': [type2_only_count],
        'Type2_Only_Percentage': [round(type2_only_pct, 2)],
    }
    
    df_summary = pd.DataFrame(summary_data)
    start_date_clean = start_date.replace('-', '')
    end_date_clean = end_date.replace('-', '')
    summary_file = f"{output_dir}/referral_type8_correlation_summary_{start_date_clean}_{end_date_clean}.csv"
    df_summary.to_csv(summary_file, index=False)
    print(f"📄 Summary saved to CSV: {summary_file}")
    
    # Detailed CSV
    df_deals['start_date'] = start_date
    df_deals['end_date'] = end_date
    detail_file = f"{output_dir}/referral_type8_correlation_detail_{start_date_clean}_{end_date_clean}.csv"
    df_deals.to_csv(detail_file, index=False)
    print(f"📄 Detailed results saved to CSV: {detail_file}")
    
    # Lead Source Distribution CSV (TEMPORARY ANALYSIS - to be removed later)
    if sorted_sources:
        leadsource_data = {
            'Lead_Source': [source for source, count in sorted_sources],
            'Count': [count for source, count in sorted_sources],
            'Percentage': [round((count / total_type8_deals * 100), 2) for source, count in sorted_sources]
        }
        df_leadsource = pd.DataFrame(leadsource_data)
        leadsource_file = f"{output_dir}/referral_type8_leadsource_distribution_{start_date_clean}_{end_date_clean}.csv"
        df_leadsource.to_csv(leadsource_file, index=False)
        print(f"📄 Lead source distribution (TEMPORARY) saved to CSV: {leadsource_file}")
    
    # Other Indicators CSV (TEMPORARY ANALYSIS - to be removed later)
    indicators_data = {
        'Indicator': [
            'colppy_es_referido_del_contador_true',
            'colppy_quien_lo_refirio_has_value',
            'accountant_channel_involucrado_en_la_venta_true',
            'tiene_cuenta_contador_gt_0',
            'contact_influenciador_contador_type54',
            'contact_refiere_type4',
            'contact_es_contador_true',
            'contact_rol_wizard_contador'
        ],
        'Count': [
            referral_deal_indicators['colppy_es_referido_del_contador']['true'],
            referral_deal_indicators['colppy_quien_lo_refirio']['has_value'],
            referral_deal_indicators['accountant_channel_involucrado_en_la_venta']['true'],
            referral_deal_indicators['tiene_cuenta_contador']['has_value_gt_0'],
            referral_deal_indicators['contact_influenciador_contador'],
            referral_deal_indicators['contact_refiere'],
            referral_deal_indicators['contact_es_contador'],
            referral_deal_indicators['contact_rol_wizard_contador']
        ],
        'Percentage': [
            round((referral_deal_indicators['colppy_es_referido_del_contador']['true'] / total_deals * 100), 2) if total_deals > 0 else 0,
            round((referral_deal_indicators['colppy_quien_lo_refirio']['has_value'] / total_deals * 100), 2) if total_deals > 0 else 0,
            round((referral_deal_indicators['accountant_channel_involucrado_en_la_venta']['true'] / total_deals * 100), 2) if total_deals > 0 else 0,
            round((referral_deal_indicators['tiene_cuenta_contador']['has_value_gt_0'] / total_deals * 100), 2) if total_deals > 0 else 0,
            round((referral_deal_indicators['contact_influenciador_contador'] / total_deals * 100), 2) if total_deals > 0 else 0,
            round((referral_deal_indicators['contact_refiere'] / total_deals * 100), 2) if total_deals > 0 else 0,
            round((referral_deal_indicators['contact_es_contador'] / total_deals * 100), 2) if total_deals > 0 else 0,
            round((referral_deal_indicators['contact_rol_wizard_contador'] / total_deals * 100), 2) if total_deals > 0 else 0,
        ]
    }
    df_indicators = pd.DataFrame(indicators_data)
    indicators_file = f"{output_dir}/referral_other_indicators_{start_date_clean}_{end_date_clean}.csv"
    df_indicators.to_csv(indicators_file, index=False)
    print(f"📄 Other indicators analysis (TEMPORARY) saved to CSV: {indicators_file}")
    
    print()
    
    return {
        'total_deals': total_deals,
        'type8_count': total_with_type8,
        'type8_percentage': type8_percentage,
        'type2_count': total_with_type2,
        'type2_percentage': type2_percentage,
        'both_count': both_count,
        'both_percentage': both_percentage,
        'neither_count': neither_count,
        'neither_percentage': neither_percentage,
        'start_date': start_date,
        'end_date': end_date
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze Correlation: Referencia Externa Directa vs Type 8')
    parser.add_argument('--month', type=str, help='Month in YYYY-MM format (e.g., 2025-12)')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    
    args = parser.parse_args()
    
    # Parse dates
    if args.month:
        year, month = args.month.split('-')
        start_date = f"{year}-{month}-01"
        if month == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            end_date = f"{year}-{int(month)+1:02d}-01"
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        parser.error("Must specify either --month or --start-date/--end-date")
    
    analyze_correlation(start_date, end_date)

if __name__ == '__main__':
    main()
