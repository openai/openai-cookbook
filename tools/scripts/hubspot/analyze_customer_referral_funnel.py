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
CUSTOMER REFERRAL FUNNEL ANALYSIS
==================================

Analyzes TWO separate funnels for customer referrals:

1. CQL FUNNEL (Contact-Based - Traditional Process):
   - Starts from CQL (Lead objects that entered "Nuevo Lead de Customer (CQL)" stage in period)
   - Filters associated contacts by lead_source = 'CS'
   - Funnel: CQL Created → Deal Created → Deal Closed Won
   - Requires contact association and validation
   - Matches HubSpot report methodology (stage-based tracking)

2. DIRECT DEAL FUNNEL (Deal-Based - Shorter Process):
   - Starts directly from deals (no contact requirement)
   - Filters: lead_source = 'CS' (customer referrals) OR 'Referencia Externa Contador' (accountant referrals)
   - Funnel: Deal Created → Deal Closed Won
   - No contact association required - just deals with referral lead source

PROCESS SUMMARY:
================
When customer support identifies an accountant referral opportunity:
1. Customer support creates a CQL (Lead object) in HubSpot
2. Lead Source: "CS" (internal value for "REFERENCIA CUSTOMER")
3. Lead Stage: "Nueva Lead de Customer (CQL)"
4. Pipeline: "Pipeline de leads"
5. Sales team takes over and converts Lead → Deal
6. Deal also has lead_source = "CS"

OR sales team can create deals directly with lead_source = 'CS' or 'Referencia Externa Contador'

FUNNEL 1: CQL FUNNEL (Contact-Based)
====================================

STEP 1: Fetch CQLs (Leads that entered stage in period)
--------------------------------------------------------
- Filter: Lead objects that entered "Nuevo Lead de Customer (CQL)" stage in period
- Pipeline: "Pipeline de leads" (lead-pipeline-id)
- Get associated contacts
- Filter: lead_source = 'CS' (internal value for "REFERENCIA CUSTOMER")
- Period: Leads that ENTERED stage in the date range (matches HubSpot report)

STEP 2: Track Deal Creation (STRICT FUNNEL)
--------------------------------------------
- Filter: Deal created in period
- Filter: lead_source = 'CS'
- Requirement: Deal must be associated with CQL contact
- Validation: Contact created < Deal created

STEP 3: Track Deal Closed Won
-------------------------------
- Filter: Deals from STEP 2 that closed won in period
- Both createdate and closedate must be in period

FUNNEL 2: DIRECT DEAL FUNNEL (Deal-Based)
==========================================

STEP 1: Fetch Deals Created
-----------------------------
- Filter: Deal created in period
- Filter: lead_source = 'CS' (customer referrals) OR 'Referencia Externa Contador' (accountant referrals)
- No contact requirement

STEP 2: Track Deal Closed Won
-------------------------------
- Filter: Deals from STEP 1 that closed won in period
- Both createdate and closedate must be in period

BOTH FUNNELS:
- Classify by ICP (Operador vs PYME)
- Calculate revenue and conversion rates

Usage:
  python analyze_customer_referral_funnel.py --start-date 2025-12-01 --end-date 2026-01-01
  python analyze_customer_referral_funnel.py --month 2025-12
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

ACCOUNTANT_COMPANY_TYPES = ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']

# Lead source values for referrals
CUSTOMER_REFERRAL_LEAD_SOURCE = 'CS'  # Internal value for "REFERENCIA CUSTOMER"
ACCOUNTANT_REFERRAL_LEAD_SOURCE = 'Referencia Externa Contador'  # Internal value for accountant referrals

def get_primary_company_id(deal_id):
    """Get PRIMARY company ID from deal-company associations (Type ID 5)"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/companies"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            for assoc in associations:
                for assoc_type in assoc.get('associationTypes', []):
                    if assoc_type.get('typeId') == 5:
                        return assoc.get('toObjectId')
    except:
        pass
    return None

def get_company_details(company_id):
    """Get company name and type"""
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/{company_id}"
    params = {'properties': 'name,type'}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if response.status_code == 200:
            props = response.json().get('properties', {})
            return props.get('name'), props.get('type')
    except Exception as e:
        print(f"   ⚠️  Error fetching company {company_id}: {str(e)}")
    return None, None

def is_icp_operador(deal):
    """
    Determine if deal is ICP Operador based on PRIMARY company type.
    Uses primary_company_type field if available, otherwise fetches from company.
    """
    props = deal.get('properties', {})
    
    # Try to use primary_company_type field first (synced property)
    primary_company_type = props.get('primary_company_type', '')
    if primary_company_type and primary_company_type in ACCOUNTANT_COMPANY_TYPES:
        return True
    
    # Fallback: Fetch from company association
    deal_id = deal.get('id')
    if deal_id:
        company_id = get_primary_company_id(deal_id)
        if company_id:
            company_name, company_type = get_company_details(company_id)
            if company_type and company_type in ACCOUNTANT_COMPANY_TYPES:
                return True
    
    return False

def get_contact_deals(contact_id, start_date, end_date, include_all_deals=False):
    """
    Get deals associated with a contact.
    If include_all_deals=False: Only returns deals CREATED in the period with lead_source = 'CS'
    If include_all_deals=True: Returns ALL deals (including outside period, archived, etc.)
    Returns list of deal objects with properties
    
    MATCHES THE SAME PATTERN AS SMB/ACCOUNTANT FUNNELS
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/deals"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            deal_ids = [assoc.get('toObjectId') for assoc in associations]
            
            # Fetch deal details to filter by createdate
            if not deal_ids:
                return []
            
            # Fetch deals in batches (same pattern as SMB/Accountant funnels)
            all_deals = []
            for i in range(0, len(deal_ids), 100):
                batch_ids = deal_ids[i:i+100]
                url_search = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/batch/read"
                payload = {
                    "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "lead_source", "primary_company_type", "hs_archived"],
                    "inputs": [{"id": deal_id} for deal_id in batch_ids]
                }
                response = requests.post(url_search, headers=HEADERS, json=payload, timeout=30)
                if response.status_code == 200:
                    deals = response.json().get('results', [])
                    all_deals.extend(deals)
            
            if include_all_deals:
                return all_deals
            
            # Filter by createdate in period AND lead_source = 'CS' (CQL-specific filter)
            deals_in_period = []
            start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
            end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
            for deal in all_deals:
                props = deal.get('properties', {})
                deal_createdate = props.get('createdate', '')
                deal_lead_source = props.get('lead_source', '')
                
                # CQL-specific: Deal must have lead_source = 'CS'
                if deal_lead_source == CUSTOMER_REFERRAL_LEAD_SOURCE and deal_createdate:
                    try:
                        deal_created_dt = datetime.fromisoformat(deal_createdate.replace('Z', '+00:00'))
                        if start_dt <= deal_created_dt < end_dt:
                            deals_in_period.append(deal)
                    except:
                        pass
            
            return deals_in_period
    except:
        pass
    return []

def get_deal_companies_with_association_type(deal_id, association_type_id):
    """
    Get companies associated with a deal that have a specific association type.
    
    Args:
        deal_id: Deal ID
        association_type_id: Association type ID to filter (e.g., 8 for "Estudio Contable")
    
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

def analyze_direct_deal_funnel(start_date, end_date):
    """
    Analyze the DIRECT DEAL funnel (deal-based, no contact requirement).
    
    FUNNEL LOGIC (Matching HubSpot Report):
    ============
    1. Fetch all Deals created in period where:
       - lead_source = 'Referencia Externa Contador' (accountant referrals) OR 'CS' (customer referrals)
       - AND tiene_cuenta_contador > 0 (accountant involvement - matching HubSpot report filter)
    2. Track: Deal Created → Deal Closed Won
    3. Classify by ICP Operador vs ICP PYME
    4. Calculate revenue
    
    NOTE: This matches the HubSpot report filter:
    - "Cantidad de cuentas contador asociadas is greater than 0"
    - "Lead Source is any of Referencia Externa Directa" (which is 'Referencia Externa Contador' internally)
    """
    # Validate date range
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    print(f"\n{'='*80}")
    print(f"DIRECT DEAL FUNNEL ANALYSIS (Deal-Based)")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    print("FILTERING CRITERIA (Matching HubSpot Report):")
    print(f"1. Lead Source: '{CUSTOMER_REFERRAL_LEAD_SOURCE}' (customer referrals)")
    print(f"   OR Lead Source: '{ACCOUNTANT_REFERRAL_LEAD_SOURCE}' (accountant referrals)")
    print("2. Accountant involvement (DUAL-CRITERIA - OR logic):")
    print("   - tiene_cuenta_contador > 0 (Formula field method) OR")
    print("   - Has association type 8 (Rollup field method)")
    print("3. No contact requirement - direct deal creation")
    print()
    
    # ========================================================================
    # STEP 1: Fetch Deals Created
    # ========================================================================
    print("📊 STEP 1: Fetching deals created...")
    print(f"   Filtering: lead_source = '{CUSTOMER_REFERRAL_LEAD_SOURCE}' OR '{ACCOUNTANT_REFERRAL_LEAD_SOURCE}'")
    print(f"   AND: Accountant involvement (tiene_cuenta_contador > 0 OR association type 8)")
    print(f"   Period: Deals CREATED between {start_date} and {end_date}")
    print()
    
    url_deals = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    
    # First, fetch all deals with the lead sources (without tiene_cuenta_contador filter)
    all_deals_with_source = []
    after = None
    
    # Fetch deals with customer referral lead source
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "lead_source", "operator": "EQ", "value": CUSTOMER_REFERRAL_LEAD_SOURCE}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "lead_source", "primary_company_type", "tiene_cuenta_contador"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url_deals, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_deals_with_source.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    # Fetch deals with accountant referral lead source
    after = None
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "lead_source", "operator": "EQ", "value": ACCOUNTANT_REFERRAL_LEAD_SOURCE}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "lead_source", "primary_company_type", "tiene_cuenta_contador"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url_deals, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_deals_with_source.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    # Remove duplicates
    unique_deals = {}
    for deal in all_deals_with_source:
        deal_id = deal.get('id')
        if deal_id not in unique_deals:
            unique_deals[deal_id] = deal
    
    all_deals_with_source = list(unique_deals.values())
    
    print(f"   Found {len(all_deals_with_source)} total deals with referral lead sources")
    print("   Now checking accountant involvement (tiene_cuenta_contador > 0 OR association type 8)...")
    
    # Check each deal for accountant involvement (DUAL-CRITERIA: OR logic)
    deals_with_accountant = []
    deal_id_to_deal = {deal.get('id'): deal for deal in all_deals_with_source}
    
    ACCOUNTANT_ASSOCIATION_TYPE_ID = 8  # "Estudio Contable / Asesor / Consultor Externo del negocio"
    
    for i, deal in enumerate(all_deals_with_source, 1):
        if i % 20 == 0:
            print(f"      Checking deal {i}/{len(all_deals_with_source)}...")
        
        deal_id = deal.get('id')
        props = deal.get('properties', {})
        
        # Method 1: Check tiene_cuenta_contador > 0
        tiene_cuenta = props.get('tiene_cuenta_contador', '')
        try:
            tiene_cuenta_num = int(tiene_cuenta) if tiene_cuenta else 0
            has_tiene_cuenta = tiene_cuenta_num > 0
        except:
            has_tiene_cuenta = False
        
        # Method 2: Check association type 8
        company_ids = get_deal_companies_with_association_type(deal_id, ACCOUNTANT_ASSOCIATION_TYPE_ID)
        has_association_type8 = len(company_ids) > 0
        
        # OR logic: Include if EITHER method is true
        if has_tiene_cuenta or has_association_type8:
            deals_with_accountant.append(deal_id)
        
        time.sleep(0.05)  # Rate limiting
    
    deals_created = [deal_id_to_deal[deal_id] for deal_id in deals_with_accountant if deal_id in deal_id_to_deal]
    
    # Count by lead source
    customer_deals = [d for d in deals_created if d.get('properties', {}).get('lead_source') == CUSTOMER_REFERRAL_LEAD_SOURCE]
    accountant_deals = [d for d in deals_created if d.get('properties', {}).get('lead_source') == ACCOUNTANT_REFERRAL_LEAD_SOURCE]
    
    print(f"   Found {len(deals_created)} total deals created in period (with accountant involvement)")
    print(f"   - Customer referrals (CS): {len(customer_deals)}")
    print(f"   - Accountant referrals (Referencia Externa Contador): {len(accountant_deals)}")
    print()
    
    # ========================================================================
    # STEP 2: Track Deal Closed Won
    # ========================================================================
    print("📊 STEP 2: Filtering closed won deals...")
    print("   MATCHING HUBSPOT REPORT BEHAVIOR:")
    print("   - Filters by createdate only (not both dates)")
    print("   - Includes all deals with createdate in period")
    print("   - HubSpot report shows 'Cerrado Ganado' stage")
    print()
    
    closed_won_deals = []
    excluded_deals = {
        'no_createdate': []
    }
    
    for deal in deals_created:
        props = deal.get('properties', {})
        dealstage = props.get('dealstage', '')
        deal_createdate_str = props.get('createdate', '')
        deal_name = props.get('dealname', 'N/A')
        deal_id = deal.get('id')
        
        # MATCHING HUBSPOT REPORT: Include deals with createdate in period
        # HubSpot report shows "Cerrado Ganado" which is dealstage = 'closedwon'
        # But we include all deals created in period (HubSpot counts all 30)
        if deal_createdate_str:
            try:
                deal_created_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                
                # Only createdate must be in period (matching HubSpot report behavior)
                if start_dt <= deal_created_dt < end_dt:
                    # Count as "Closed Won" if dealstage is 'closedwon'
                    # Note: HubSpot report may include other stages, but we match the "Cerrado Ganado" filter
                    if dealstage == 'closedwon':
                        closed_won_deals.append(deal)
            except Exception as e:
                excluded_deals['no_createdate'].append({
                    'id': deal_id, 
                    'name': deal_name, 
                    'error': str(e)
                })
        else:
            excluded_deals['no_createdate'].append({'id': deal_id, 'name': deal_name})
    
    closed_won_count = len(closed_won_deals)
    print(f"   Deal Created: {len(deals_created)}")
    print(f"   Deal Closed Won: {closed_won_count} (dealstage = 'closedwon', created in period)")
    
    if excluded_deals['no_createdate']:
        print(f"   ⚠️  Excluded {len(excluded_deals['no_createdate'])} deal(s) with missing/invalid createdate")
    print()
    
    # ========================================================================
    # Classify by ICP
    # ========================================================================
    print("📊 Classifying by ICP...")
    icp_operador_deals = []
    icp_pyme_deals = []
    
    for deal in closed_won_deals:
        if is_icp_operador(deal):
            icp_operador_deals.append(deal)
        else:
            icp_pyme_deals.append(deal)
    
    print(f"   ICP Operador: {len(icp_operador_deals)}")
    print(f"   ICP PYME: {len(icp_pyme_deals)}")
    print()
    
    # ========================================================================
    # Calculate Revenue
    # ========================================================================
    print("📊 Calculating revenue...")
    total_revenue = 0
    icp_operador_revenue = 0
    icp_pyme_revenue = 0
    
    for deal in closed_won_deals:
        props = deal.get('properties', {})
        amount_str = props.get('amount', '')
        if amount_str:
            try:
                amount = float(amount_str)
                total_revenue += amount
                if is_icp_operador(deal):
                    icp_operador_revenue += amount
                else:
                    icp_pyme_revenue += amount
            except:
                pass
    
    average_deal_size = total_revenue / closed_won_count if closed_won_count > 0 else 0
    
    print(f"   Total Revenue: ${total_revenue:,.2f}")
    print(f"   ICP Operador Revenue: ${icp_operador_revenue:,.2f}")
    print(f"   ICP PYME Revenue: ${icp_pyme_revenue:,.2f}")
    print(f"   Average Deal Size: ${average_deal_size:,.2f}")
    print()
    
    # ========================================================================
    # Calculate Conversion Rates
    # ========================================================================
    deal_to_won_rate = (closed_won_count / len(deals_created) * 100) if deals_created else 0
    
    # ========================================================================
    # Print Results
    # ========================================================================
    print("="*80)
    print("DIRECT DEAL FUNNEL RESULTS")
    print("="*80)
    print()
    print("**FILTERING CRITERIA:**")
    print(f"1. Lead Source: '{CUSTOMER_REFERRAL_LEAD_SOURCE}' (customer referrals)")
    print(f"   OR Lead Source: '{ACCOUNTANT_REFERRAL_LEAD_SOURCE}' (accountant referrals)")
    print("2. No contact requirement - direct deal creation")
    print()
    print("**FUNNEL PATH:** Deal Created → Deal Closed Won")
    print()
    print("| Stage | Count | Conversion Rate |")
    print("|-------|-------|-----------------|")
    print(f"| Deal Created | {len(deals_created)} | - |")
    print(f"| Deal Closed Won | {closed_won_count} | {deal_to_won_rate:.2f}% |")
    print()
    
    # Calculate average time to close
    avg_time_to_close = None
    if closed_won_deals:
        time_differences = []
        for deal in closed_won_deals:
            props = deal.get('properties', {})
            createdate = props.get('createdate', '')
            closedate = props.get('closedate', '')
            try:
                if createdate and closedate:
                    created_dt = datetime.fromisoformat(createdate.replace('Z', '+00:00'))
                    closed_dt = datetime.fromisoformat(closedate.replace('Z', '+00:00'))
                    diff = (closed_dt - created_dt).days
                    time_differences.append(diff)
            except:
                pass
        if time_differences:
            avg_time_to_close = sum(time_differences) / len(time_differences)
    
    if avg_time_to_close is not None:
        print(f"**Average Time to Close:** {avg_time_to_close:.1f} days")
        print()
    
    print("="*80)
    print("ICP CLASSIFICATION (Closed Won Deals)")
    print("="*80)
    print()
    print("| ICP Type | Count | % of Closed Won | Revenue |")
    print("|----------|-------|-----------------|---------|")
    icp_operador_pct = (len(icp_operador_deals) / closed_won_count * 100) if closed_won_count > 0 else 0
    icp_pyme_pct = (len(icp_pyme_deals) / closed_won_count * 100) if closed_won_count > 0 else 0
    print(f"| ICP Operador | {len(icp_operador_deals)} | {icp_operador_pct:.1f}% | ${icp_operador_revenue:,.2f} |")
    print(f"| ICP PYME | {len(icp_pyme_deals)} | {icp_pyme_pct:.1f}% | ${icp_pyme_revenue:,.2f} |")
    print()
    
    return {
        'deal_created': len(deals_created),
        'closed_won': closed_won_count,
        'deal_to_won_rate': deal_to_won_rate,
        'total_revenue': total_revenue,
        'icp_operador_revenue': icp_operador_revenue,
        'icp_pyme_revenue': icp_pyme_revenue,
        'customer_deals': len(customer_deals),
        'accountant_deals': len(accountant_deals)
    }

def get_leads_entered_stage_in_period(start_date, end_date, stage_name, pipeline_id='lead-pipeline-id'):
    """
    Fetch Lead objects that entered a specific stage in the period.
    Uses property history to determine when the lead entered the stage.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        stage_name: Stage name (e.g., "Nuevo Lead de Customer (CQL)")
        pipeline_id: Pipeline ID (default: 'lead-pipeline-id' for "Pipeline de leads")
    
    Returns:
        List of contact IDs that have leads that entered the stage in the period
    """
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    # First, fetch all leads with the target stage and pipeline
    url_leads = f"{HUBSPOT_BASE_URL}/crm/v3/objects/leads/search"
    
    all_leads = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": stage_name},
            {"propertyName": "hs_pipeline", "operator": "EQ", "value": pipeline_id}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["hs_pipeline_stage", "hs_pipeline", "createdate"],
            "propertiesWithHistory": ["hs_pipeline_stage"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        try:
            response = requests.post(url_leads, headers=HEADERS, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            all_leads.extend(results)
            
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after:
                break
            time.sleep(0.2)
        except Exception as e:
            print(f"   ⚠️  Error fetching leads: {str(e)}")
            break
    
    # Filter leads that entered the stage in the period using property history
    contact_ids = []
    leads_checked = 0
    
    for lead in all_leads:
        leads_checked += 1
        lead_id = lead.get('id')
        props_history = lead.get('propertiesWithHistory', {})
        
        if isinstance(props_history, dict):
            stage_history = props_history.get('hs_pipeline_stage', {})
            if isinstance(stage_history, dict):
                versions = stage_history.get('versions', [])
                if versions:
                    # Find when this lead entered the target stage
                    # Versions are typically ordered chronologically, but we'll check all
                    entered_in_period = False
                    for version in versions:
                        if isinstance(version, dict):
                            stage_value = version.get('value', '')
                            timestamp = version.get('timestamp', '')
                            
                            # Match stage by name (case-insensitive partial match for flexibility)
                            if stage_value and stage_name.lower() in str(stage_value).lower() and timestamp:
                                try:
                                    stage_dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
                                    if start_dt <= stage_dt < end_dt:
                                        entered_in_period = True
                                        break  # Found the entry date in period
                                except Exception as e:
                                    # Skip invalid timestamps
                                    pass
                    
                    # If lead entered stage in period, get associated contacts
                    if entered_in_period:
                        try:
                            url_assoc = f"{HUBSPOT_BASE_URL}/crm/v4/objects/leads/{lead_id}/associations/contacts"
                            assoc_response = requests.get(url_assoc, headers=HEADERS, timeout=30)
                            if assoc_response.status_code == 200:
                                associations = assoc_response.json().get('results', [])
                                for assoc in associations:
                                    contact_id = assoc.get('toObjectId')
                                    if contact_id and contact_id not in contact_ids:
                                        contact_ids.append(contact_id)
                            time.sleep(0.1)  # Rate limiting
                        except Exception as e:
                            # Skip if association fetch fails
                            pass
    
    return contact_ids

def analyze_cql_funnel(start_date, end_date):
    """
    Analyze the CQL funnel (contact-based, traditional process).
    
    FUNNEL LOGIC (UPDATED TO MATCH HUBSPOT REPORT):
    ============
    1. Fetch Lead objects that entered "Nuevo Lead de Customer (CQL)" stage in period
    2. Get associated contacts (filter by lead_source = 'CS')
    3. Fetch all Deals created in period where lead_source = 'CS'
    4. Link: Deals associated with CQL contacts (Contact created < Deal created)
    5. Track: CQL Created → Deal Created → Deal Closed Won
    6. Classify by ICP Operador vs ICP PYME
    7. Calculate revenue
    """
    # Validate date range
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    print(f"\n{'='*80}")
    print(f"CUSTOMER REFERRAL (CQL) FUNNEL ANALYSIS")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    print("FILTERING CRITERIA:")
    print(f"1. Lead Source: '{CUSTOMER_REFERRAL_LEAD_SOURCE}' (internal value for 'REFERENCIA CUSTOMER')")
    print("2. CQL Process: Customer support creates Lead, sales converts to Deal")
    print("3. Stage Tracking: Contacts that entered 'Nuevo Lead de Customer (CQL)' stage in period")
    print()
    
    # ========================================================================
    # STEP 1: Fetch CQLs (Leads) that entered stage in period
    # ========================================================================
    print("📊 STEP 1: Fetching CQLs (Leads) that entered stage in period...")
    print(f"   Stage: 'Nuevo Lead de Customer (CQL)' (Pipeline de leads)")
    print(f"   Period: Leads that ENTERED stage between {start_date} and {end_date}")
    print()
    
    # Get contact IDs from leads that entered the stage in period
    stage_name = "Nuevo Lead de Customer (CQL)"
    pipeline_id = "lead-pipeline-id"  # "Pipeline de leads"
    
    contact_ids_from_leads = get_leads_entered_stage_in_period(start_date, end_date, stage_name, pipeline_id)
    
    print(f"   Found {len(contact_ids_from_leads)} contact(s) with leads that entered stage in period")
    print()
    
    # Now fetch these contacts and filter by lead_source = 'CS'
    all_cql_contacts = []
    if contact_ids_from_leads:
        # Batch read contacts
        url_batch = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/batch/read"
        
        # Process in batches of 100
        for i in range(0, len(contact_ids_from_leads), 100):
            batch_ids = contact_ids_from_leads[i:i+100]
            batch_payload = {
                "properties": ["email", "firstname", "lastname", "createdate", "lead_source"],
                "inputs": [{"id": contact_id} for contact_id in batch_ids]
            }
            
            try:
                batch_response = requests.post(url_batch, headers=HEADERS, json=batch_payload, timeout=30)
                if batch_response.status_code == 200:
                    contacts = batch_response.json().get('results', [])
                    # Filter by lead_source = 'CS'
                    for contact in contacts:
                        props = contact.get('properties', {})
                        if props.get('lead_source') == CUSTOMER_REFERRAL_LEAD_SOURCE:
                            all_cql_contacts.append(contact)
                time.sleep(0.2)
            except Exception as e:
                print(f"   ⚠️  Error fetching contact batch: {str(e)}")
    
    print(f"   Found {len(all_cql_contacts)} contacts with lead_source = '{CUSTOMER_REFERRAL_LEAD_SOURCE}'")
    print()
    
    # ========================================================================
    # STEP 2: Fetch Deals Created (STRICT FUNNEL: CQL → Deal Created)
    # ========================================================================
    # STRICT FUNNEL: CQL → Deal Created → Won
    # This ensures that only deals associated with CQL contacts are considered
    # IMPORTANT: Contact must be created before deal (HubSpot logic - contact must exist when deal is created)
    print("📊 STEP 2: Fetching deals created in period (STRICT FUNNEL: CQL → Deal Created)...")
    print(f"   Filtering: lead_source = '{CUSTOMER_REFERRAL_LEAD_SOURCE}'")
    print(f"   Period: Deals CREATED between {start_date} and {end_date}")
    print("   Requirement: Deal must be associated with CQL contact AND contact created < deal created")
    print()
    
    all_deals_created = []
    contact_to_deals = {}
    
    for contact in all_cql_contacts:
        contact_id = contact.get('id')
        contact_props = contact.get('properties', {})
        contact_createdate_str = contact_props.get('createdate', '')
        
        if not contact_createdate_str:
            continue
        
        try:
            contact_created_dt = datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))
        except:
            continue
        
        # Use the same helper function pattern as SMB/Accountant funnels
        deals = get_contact_deals(contact_id, start_date, end_date)
        if deals:
            # Validate: Contact must be created before deal (HubSpot logic - contact must exist when deal is created)
            # Using < instead of <= to match HubSpot's strict association logic (same as SMB funnel)
            validated_deals = []
            for deal in deals:
                deal_props = deal.get('properties', {})
                deal_createdate_str = deal_props.get('createdate', '')
                if deal_createdate_str:
                    try:
                        deal_created_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                        # Contact must be created before deal (HubSpot logic - contact must exist when deal is created)
                        # Using < instead of <= to match HubSpot's strict association logic
                        if contact_created_dt < deal_created_dt:
                            validated_deals.append(deal)
                    except:
                        pass
            
            if validated_deals:
                contact_to_deals[contact_id] = validated_deals
                all_deals_created.extend(validated_deals)
    
    # Remove duplicates (same deal associated with multiple contacts)
    unique_deals_created = {}
    for deal in all_deals_created:
        deal_id = deal.get('id')
        if deal_id not in unique_deals_created:
            unique_deals_created[deal_id] = deal
    
    deals_meeting_criteria = list(unique_deals_created.values())
    
    print(f"   Found {len(deals_meeting_criteria)} unique deals created in period (associated with CQL contacts, contact created < deal created)")
    print()
    
    # ========================================================================
    # STEP 3: Track Funnel Stages (STRICT FUNNEL: Deal Created → Won)
    # ========================================================================
    print("📊 STEP 3: Filtering closed won deals (STRICT FUNNEL: Deal Created → Won)...")
    print("   Only deals that were created in period AND associated with CQL contacts can be closed won")
    print()
    
    cql_created_count = len(all_cql_contacts)
    deal_created_count = len(deals_meeting_criteria)
    
    # STRICT FUNNEL: Filter for closed won deals from deals_meeting_criteria
    # Both createdate AND closedate must be in period
    closed_won_deals = []
    for deal in deals_meeting_criteria:
        props = deal.get('properties', {})
        dealstage = props.get('dealstage', '')
        deal_createdate_str = props.get('createdate', '')
        deal_closedate_str = props.get('closedate', '')
        
        if dealstage == 'closedwon' and deal_createdate_str and deal_closedate_str:
            try:
                deal_created_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                deal_closed_dt = datetime.fromisoformat(deal_closedate_str.replace('Z', '+00:00'))
                
                # Both dates must be in period
                if (start_dt <= deal_created_dt < end_dt and 
                    start_dt <= deal_closed_dt < end_dt):
                    closed_won_deals.append(deal)
            except:
                pass
    
    closed_won_count = len(closed_won_deals)
    print(f"   CQL Created: {cql_created_count}")
    print(f"   Deal Created: {deal_created_count}")
    print(f"   Deal Closed Won: {closed_won_count} (created AND closed in period)")
    print()
    
    # ========================================================================
    # STEP 4: Classify by ICP
    # ========================================================================
    print("📊 STEP 4: Classifying by ICP...")
    icp_operador_deals = []
    icp_pyme_deals = []
    
    for deal in closed_won_deals:
        if is_icp_operador(deal):
            icp_operador_deals.append(deal)
        else:
            icp_pyme_deals.append(deal)
    
    print(f"   ICP Operador: {len(icp_operador_deals)}")
    print(f"   ICP PYME: {len(icp_pyme_deals)}")
    print()
    
    # ========================================================================
    # STEP 5: Calculate Revenue
    # ========================================================================
    print("📊 STEP 5: Calculating revenue...")
    total_revenue = 0
    icp_operador_revenue = 0
    icp_pyme_revenue = 0
    
    for deal in closed_won_deals:
        props = deal.get('properties', {})
        amount_str = props.get('amount', '')
        if amount_str:
            try:
                amount = float(amount_str)
                total_revenue += amount
                if is_icp_operador(deal):
                    icp_operador_revenue += amount
                else:
                    icp_pyme_revenue += amount
            except:
                pass
    
    average_deal_size = total_revenue / closed_won_count if closed_won_count > 0 else 0
    
    print(f"   Total Revenue: ${total_revenue:,.2f}")
    print(f"   ICP Operador Revenue: ${icp_operador_revenue:,.2f}")
    print(f"   ICP PYME Revenue: ${icp_pyme_revenue:,.2f}")
    print(f"   Average Deal Size: ${average_deal_size:,.2f}")
    print()
    
    # ========================================================================
    # Calculate Conversion Rates
    # ========================================================================
    cql_to_deal_rate = (deal_created_count / cql_created_count * 100) if cql_created_count > 0 else 0
    deal_to_won_rate = (closed_won_count / deal_created_count * 100) if deal_created_count > 0 else 0
    cql_to_won_rate = (closed_won_count / cql_created_count * 100) if cql_created_count > 0 else 0
    
    # ========================================================================
    # Print Results
    # ========================================================================
    print("="*80)
    print("FUNNEL RESULTS")
    print("="*80)
    print()
    print("**FILTERING CRITERIA:**")
    print(f"1. Lead Source: '{CUSTOMER_REFERRAL_LEAD_SOURCE}' (internal value for 'REFERENCIA CUSTOMER')")
    print("2. CQL Process: Customer support creates Lead, sales converts to Deal")
    print()
    print("**STRICT FUNNEL PATH:** CQL Created → Deal Created → Deal Closed Won")
    print()
    print("**STRICT FUNNEL LOGIC:**")
    print("- CQL Created: Contacts with lead_source = 'CS' created in period")
    print("- Deal Created: Deals with lead_source = 'CS' created in period, associated with CQL contacts")
    print("  (Contact created < Deal created)")
    print("- Deal Closed Won: Deals from 'Deal Created' that closed won in period")
    print("  (Both createdate AND closedate in period)")
    print()
    print("| Stage | Count | Conversion Rate |")
    print("|-------|-------|-----------------|")
    print(f"| CQL Created | {cql_created_count} | - |")
    print(f"| Deal Created | {deal_created_count} | {cql_to_deal_rate:.2f}% |")
    print(f"| Deal Closed Won | {closed_won_count} | {deal_to_won_rate:.2f}% |")
    print()
    print(f"**Overall CQL → Won Rate:** {cql_to_won_rate:.2f}%")
    print()
    
    # Calculate average time to close
    avg_time_to_close = None
    if closed_won_deals:
        time_differences = []
        for deal in closed_won_deals:
            props = deal.get('properties', {})
            createdate = props.get('createdate', '')
            closedate = props.get('closedate', '')
            try:
                if createdate and closedate:
                    created_dt = datetime.fromisoformat(createdate.replace('Z', '+00:00'))
                    closed_dt = datetime.fromisoformat(closedate.replace('Z', '+00:00'))
                    diff = (closed_dt - created_dt).days
                    time_differences.append(diff)
            except:
                pass
        if time_differences:
            avg_time_to_close = sum(time_differences) / len(time_differences)
    
    if avg_time_to_close is not None:
        print(f"**Average Time to Close:** {avg_time_to_close:.1f} days")
        print()
    
    print("="*80)
    print("ICP CLASSIFICATION (Closed Won Deals)")
    print("="*80)
    print()
    print("| ICP Type | Count | % of Closed Won | Revenue |")
    print("|----------|-------|-----------------|---------|")
    icp_operador_pct = (len(icp_operador_deals) / closed_won_count * 100) if closed_won_count > 0 else 0
    icp_pyme_pct = (len(icp_pyme_deals) / closed_won_count * 100) if closed_won_count > 0 else 0
    print(f"| ICP Operador | {len(icp_operador_deals)} | {icp_operador_pct:.1f}% | ${icp_operador_revenue:,.2f} |")
    print(f"| ICP PYME | {len(icp_pyme_deals)} | {icp_pyme_pct:.1f}% | ${icp_pyme_revenue:,.2f} |")
    print()
    
    # ========================================================================
    # Export to CSV
    # ========================================================================
    output_dir = "tools/outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    start_date_clean = start_date.replace('-', '')
    end_date_clean = end_date.replace('-', '')
    
    # Summary data
    summary_data = {
        'Metric': [
            'CQL Created',
            'Deal Created',
            'Deal Closed Won',
            'CQL to Deal Rate (%)',
            'Deal to Won Rate (%)',
            'CQL to Won Rate (%)',
            'Total Revenue',
            'ICP Operador Revenue',
            'ICP PYME Revenue',
            'Average Deal Size',
            'Average Time to Close (days)'
        ],
        'Value': [
            cql_created_count,
            deal_created_count,
            closed_won_count,
            round(cql_to_deal_rate, 2),
            round(deal_to_won_rate, 2),
            round(cql_to_won_rate, 2),
            round(total_revenue, 2),
            round(icp_operador_revenue, 2),
            round(icp_pyme_revenue, 2),
            round(average_deal_size, 2),
            round(avg_time_to_close, 1) if avg_time_to_close is not None else None
        ]
    }
    df_summary = pd.DataFrame(summary_data)
    summary_file = f"{output_dir}/customer_referral_funnel_summary_{start_date_clean}_{end_date_clean}.csv"
    df_summary.to_csv(summary_file, index=False)
    print(f"📄 Summary saved to CSV: {summary_file}")
    
    # Detailed deal data
    deal_data = []
    for deal in closed_won_deals:
        props = deal.get('properties', {})
        deal_data.append({
            'deal_id': deal.get('id'),
            'deal_name': props.get('dealname', ''),
            'createdate': props.get('createdate', ''),
            'closedate': props.get('closedate', ''),
            'amount': props.get('amount', ''),
            'dealstage': props.get('dealstage', ''),
            'primary_company_type': props.get('primary_company_type', ''),
            'icp_type': 'ICP Operador' if is_icp_operador(deal) else 'ICP PYME'
        })
    
    if deal_data:
        df_deals = pd.DataFrame(deal_data)
        detail_file = f"{output_dir}/customer_referral_funnel_detail_{start_date_clean}_{end_date_clean}.csv"
        df_deals.to_csv(detail_file, index=False)
        print(f"📄 Detailed results saved to CSV: {detail_file}")
    
    print()
    print("="*80)
    print("CQL FUNNEL ANALYSIS COMPLETE")
    print("="*80)
    
    return {
        'cql_created': cql_created_count,
        'deal_created': deal_created_count,
        'closed_won': closed_won_count,
        'cql_to_deal_rate': cql_to_deal_rate,
        'deal_to_won_rate': deal_to_won_rate,
        'cql_to_won_rate': cql_to_won_rate,
        'total_revenue': total_revenue,
        'icp_operador_revenue': icp_operador_revenue,
        'icp_pyme_revenue': icp_pyme_revenue
    }

def analyze_customer_referral_funnel(start_date, end_date):
    """
    Analyze BOTH funnels: CQL funnel (contact-based) and Direct Deal funnel (deal-based).
    """
    # Only print header if not in multi-month mode (will be printed in main())
    # Check if we're being called from main() with months parameter
    import inspect
    frame = inspect.currentframe()
    try:
        caller_frame = frame.f_back
        if caller_frame and 'args' in caller_frame.f_locals:
            caller_args = caller_frame.f_locals.get('args')
            if caller_args and hasattr(caller_args, 'months') and caller_args.months:
                # Multi-month mode - skip header
                pass
            else:
                # Single analysis - print header
                print("="*80)
                print("CUSTOMER REFERRAL FUNNEL ANALYSIS - COMPLETE")
                print("="*80)
                print()
                print("This analysis includes TWO separate funnels:")
                print("1. CQL FUNNEL (Contact-Based): Traditional process starting from CQL contacts")
                print("2. DIRECT DEAL FUNNEL (Deal-Based): Shorter process starting directly from deals")
                print()
        else:
            # Single analysis - print header
            print("="*80)
            print("CUSTOMER REFERRAL FUNNEL ANALYSIS - COMPLETE")
            print("="*80)
            print()
            print("This analysis includes TWO separate funnels:")
            print("1. CQL FUNNEL (Contact-Based): Traditional process starting from CQL contacts")
            print("2. DIRECT DEAL FUNNEL (Deal-Based): Shorter process starting directly from deals")
            print()
    except:
        # Fallback - print header
        print("="*80)
        print("CUSTOMER REFERRAL FUNNEL ANALYSIS - COMPLETE")
        print("="*80)
        print()
        print("This analysis includes TWO separate funnels:")
        print("1. CQL FUNNEL (Contact-Based): Traditional process starting from CQL contacts")
        print("2. DIRECT DEAL FUNNEL (Deal-Based): Shorter process starting directly from deals")
        print()
    finally:
        del frame
    
    # Run CQL Funnel
    cql_results = analyze_cql_funnel(start_date, end_date)
    
    print()
    print("="*80)
    print()
    
    # Run Direct Deal Funnel
    direct_deal_results = analyze_direct_deal_funnel(start_date, end_date)
    
    # ========================================================================
    # Export Combined Results to CSV
    # ========================================================================
    output_dir = "tools/outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    start_date_clean = start_date.replace('-', '')
    end_date_clean = end_date.replace('-', '')
    
    # Combined summary
    summary_data = {
        'Funnel': [
            'CQL Funnel (Contact-Based)',
            'CQL Funnel (Contact-Based)',
            'CQL Funnel (Contact-Based)',
            'Direct Deal Funnel (Deal-Based)',
            'Direct Deal Funnel (Deal-Based)'
        ],
        'Stage': [
            'CQL Created',
            'Deal Created',
            'Deal Closed Won',
            'Deal Created',
            'Deal Closed Won'
        ],
        'Count': [
            cql_results['cql_created'],
            cql_results['deal_created'],
            cql_results['closed_won'],
            direct_deal_results['deal_created'],
            direct_deal_results['closed_won']
        ],
        'Conversion_Rate_%': [
            None,
            round(cql_results['cql_to_deal_rate'], 2),
            round(cql_results['deal_to_won_rate'], 2),
            None,
            round(direct_deal_results['deal_to_won_rate'], 2)
        ],
        'Revenue': [
            None,
            None,
            round(cql_results['total_revenue'], 2),
            None,
            round(direct_deal_results['total_revenue'], 2)
        ]
    }
    df_summary = pd.DataFrame(summary_data)
    summary_file = f"{output_dir}/customer_referral_funnel_combined_{start_date_clean}_{end_date_clean}.csv"
    df_summary.to_csv(summary_file, index=False)
    print(f"📄 Combined summary saved to CSV: {summary_file}")
    
    print()
    print("="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
    
    return {
        'cql_funnel': cql_results,
        'direct_deal_funnel': direct_deal_results
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze customer referral funnels (CQL and Direct Deal)')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--month', type=str, help='Month to analyze (YYYY-MM)')
    parser.add_argument('--months', nargs='+', type=str, help='Multiple months to analyze (YYYY-MM format, e.g., --months 2025-11 2025-12)')
    
    args = parser.parse_args()
    
    # Handle multiple months
    if args.months:
        print("="*80)
        print("MULTI-MONTH ANALYSIS")
        print("="*80)
        print()
        print(f"Analyzing {len(args.months)} month(s): {', '.join(args.months)}")
        print()
        
        all_cql_results = []
        all_direct_deal_results = []
        
        for month_str in args.months:
            year, month = month_str.split('-')
            start_date = f"{year}-{month}-01"
            if month == '12':
                end_date = f"{int(year)+1}-01-01"
            else:
                next_month = int(month) + 1
                end_date = f"{year}-{next_month:02d}-01"
            
            print("="*80)
            print(f"MONTH: {month_str}")
            print("="*80)
            print()
            
            results = analyze_customer_referral_funnel(start_date, end_date)
            if results:
                cql_result = results.get('cql_funnel', {})
                direct_deal_result = results.get('direct_deal_funnel', {})
                
                cql_result['month'] = month_str
                direct_deal_result['month'] = month_str
                
                all_cql_results.append(cql_result)
                all_direct_deal_results.append(direct_deal_result)
            print()
        
        # Print comparative summary
        if all_cql_results and all_direct_deal_results:
            print("="*80)
            print("COMPARATIVE SUMMARY - CQL FUNNEL (Contact-Based)")
            print("="*80)
            print()
            print("**FILTERING CRITERIA:**")
            print(f"1. Lead Source: '{CUSTOMER_REFERRAL_LEAD_SOURCE}' (internal value for 'REFERENCIA CUSTOMER')")
            print("2. CQL Process: Customer support creates Lead, sales converts to Deal")
            print()
            print("**FUNNEL PATH:** CQL Created → Deal Created → Deal Closed Won")
            print()
            print("| Month | CQL Created | Deal Created | Deal Closed Won | CQL→Deal | Deal→Won | CQL→Won | Revenue |")
            print("|-------|-------------|--------------|-----------------|----------|----------|---------|---------|")
            for result in all_cql_results:
                month = result.get('month', 'N/A')
                cql_created = result.get('cql_created', 0)
                deal_created = result.get('deal_created', 0)
                closed_won = result.get('closed_won', 0)
                cql_to_deal = result.get('cql_to_deal_rate', 0)
                deal_to_won = result.get('deal_to_won_rate', 0)
                cql_to_won = result.get('cql_to_won_rate', 0)
                revenue = result.get('total_revenue', 0)
                print(f"| {month} | {cql_created} | {deal_created} | {closed_won} | {cql_to_deal:.1f}% | {deal_to_won:.1f}% | {cql_to_won:.1f}% | ${revenue:,.2f} |")
            print()
            
            print("="*80)
            print("COMPARATIVE SUMMARY - DIRECT DEAL FUNNEL (Deal-Based)")
            print("="*80)
            print()
            print("**FILTERING CRITERIA:**")
            print(f"1. Lead Source: '{CUSTOMER_REFERRAL_LEAD_SOURCE}' (customer referrals)")
            print(f"   OR Lead Source: '{ACCOUNTANT_REFERRAL_LEAD_SOURCE}' (accountant referrals)")
            print("2. No contact requirement - direct deal creation")
            print()
            print("**FUNNEL PATH:** Deal Created → Deal Closed Won")
            print()
            print("| Month | Deal Created | Deal Closed Won | Deal→Won | Customer (CS) | Accountant | Revenue |")
            print("|-------|--------------|-----------------|----------|---------------|------------|---------|")
            for result in all_direct_deal_results:
                month = result.get('month', 'N/A')
                deal_created = result.get('deal_created', 0)
                closed_won = result.get('closed_won', 0)
                deal_to_won = result.get('deal_to_won_rate', 0)
                customer_deals = result.get('customer_deals', 0)
                accountant_deals = result.get('accountant_deals', 0)
                revenue = result.get('total_revenue', 0)
                print(f"| {month} | {deal_created} | {closed_won} | {deal_to_won:.1f}% | {customer_deals} | {accountant_deals} | ${revenue:,.2f} |")
            print()
            
            # Save comparative CSV
            output_dir = "tools/outputs"
            os.makedirs(output_dir, exist_ok=True)
            
            # CQL Funnel comparative data
            cql_df_data = {
                'Month': [r.get('month', 'N/A') for r in all_cql_results],
                'CQL_Created': [r.get('cql_created', 0) for r in all_cql_results],
                'Deal_Created': [r.get('deal_created', 0) for r in all_cql_results],
                'Deal_Closed_Won': [r.get('closed_won', 0) for r in all_cql_results],
                'CQL_to_Deal_Rate_%': [round(r.get('cql_to_deal_rate', 0), 2) for r in all_cql_results],
                'Deal_to_Won_Rate_%': [round(r.get('deal_to_won_rate', 0), 2) for r in all_cql_results],
                'CQL_to_Won_Rate_%': [round(r.get('cql_to_won_rate', 0), 2) for r in all_cql_results],
                'Total_Revenue': [round(r.get('total_revenue', 0), 2) for r in all_cql_results],
                'ICP_Operador_Revenue': [round(r.get('icp_operador_revenue', 0), 2) for r in all_cql_results],
                'ICP_PYME_Revenue': [round(r.get('icp_pyme_revenue', 0), 2) for r in all_cql_results]
            }
            df_cql = pd.DataFrame(cql_df_data)
            months_str = "_".join([m.replace('-', '') for m in args.months])
            cql_file = f"{output_dir}/customer_referral_cql_funnel_comparative_{months_str}.csv"
            df_cql.to_csv(cql_file, index=False)
            print(f"📄 CQL Funnel comparative results saved to CSV: {cql_file}")
            
            # Direct Deal Funnel comparative data
            direct_deal_df_data = {
                'Month': [r.get('month', 'N/A') for r in all_direct_deal_results],
                'Deal_Created': [r.get('deal_created', 0) for r in all_direct_deal_results],
                'Deal_Closed_Won': [r.get('closed_won', 0) for r in all_direct_deal_results],
                'Deal_to_Won_Rate_%': [round(r.get('deal_to_won_rate', 0), 2) for r in all_direct_deal_results],
                'Customer_Referrals_CS': [r.get('customer_deals', 0) for r in all_direct_deal_results],
                'Accountant_Referrals': [r.get('accountant_deals', 0) for r in all_direct_deal_results],
                'Total_Revenue': [round(r.get('total_revenue', 0), 2) for r in all_direct_deal_results],
                'ICP_Operador_Revenue': [round(r.get('icp_operador_revenue', 0), 2) for r in all_direct_deal_results],
                'ICP_PYME_Revenue': [round(r.get('icp_pyme_revenue', 0), 2) for r in all_direct_deal_results]
            }
            df_direct = pd.DataFrame(direct_deal_df_data)
            direct_file = f"{output_dir}/customer_referral_direct_deal_funnel_comparative_{months_str}.csv"
            df_direct.to_csv(direct_file, index=False)
            print(f"📄 Direct Deal Funnel comparative results saved to CSV: {direct_file}")
            print()
        return
    
    # Single month or date range
    if args.month:
        year, month = args.month.split('-')
        start_date = f"{year}-{month}-01"
        if month == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            next_month = int(month) + 1
            end_date = f"{year}-{next_month:02d}-01"
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        parser.print_help()
        sys.exit(1)
    
    analyze_customer_referral_funnel(start_date, end_date)

if __name__ == '__main__':
    main()
