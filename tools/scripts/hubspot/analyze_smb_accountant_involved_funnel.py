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
SMB ACCOUNTANT INVOLVED FUNNEL ANALYSIS
=======================================

Analyzes the funnel for SMB deals where an accountant is involved in the sales process.
This script starts directly from deals (not contacts) because accountant referrals often
skip the traditional MQL → SQL → Deal path.

FILTERING CRITERIA:
- Deal Created: Deals CREATED in the period where:
  1. Accountant involvement (meets EITHER criteria):
     a. tiene_cuenta_contador > 0 (Formula field - counts accountant companies)
     b. Has companies with association type 8 (Rollup field logic - "Estudio Contable / Asesor / Consultor Externo del negocio")
  2. Associated with contacts (all contact types included - SMB, accountant, or no rol_wizard)
- Deal Closed: Deals CLOSED WON in the period (both createdate and closedate in period)
- ICP Classification: Based on PRIMARY company type (same logic as ICP Operador billing)

FUNNEL LOGIC:
=============

STEP 1: Fetch Deals with Accountant Involvement
-------------------------------------------------
- Query: All deals created in period where:
  - tiene_cuenta_contador > 0 (Formula field method)
  - OR has companies with association type 8 (Rollup field method - "Estudio Contable" label)
- Analysis: Track overlap between both methods
- Filter: Deals must have at least one associated contact (all contact types included)
- Result: List of deals with accountant involvement (by either method) + contacts

STEP 2: Filter for SMB Contacts
--------------------------------
- For each deal, get all associated contacts
- Check each contact's rol_wizard field
- Include deal if ANY contact has SMB role (non-accountant)
- Exclude deals where ALL contacts are accountants or have no rol_wizard

STEP 3: Track Deal Conversion
------------------------------
- Deal Created: Count from STEP 2 (deals with accountant + SMB contacts)
- Deal Closed Won: Filter deals from STEP 2 where:
  - dealstage = 'closedwon'
  - createdate in period
  - closedate in period

STEP 4: Classify by ICP
------------------------
- ICP Operador: PRIMARY company type IN ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']
- ICP PYME: All other deals (billed to SMB, not accountant)

STEP 5: Calculate Revenue
---------------------------
- Total Revenue: Sum of amount from closed won deals
- ICP Operador Revenue: Sum from ICP Operador deals
- ICP PYME Revenue: Sum from ICP PYME deals

CONVERSION RATES:
----------------
- Deal Created to Won Rate: (Closed Won / Deal Created) × 100

Usage:
  python analyze_smb_accountant_involved_funnel.py --month 2025-12
  python analyze_smb_accountant_involved_funnel.py --months 2025-11 2025-12
  python analyze_smb_accountant_involved_funnel.py --start-date 2025-12-01 --end-date 2026-01-01
"""

import os
import sys
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import argparse
import time
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

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

# Accountant role values in rol_wizard (case-insensitive matching)
ACCOUNTANT_ROLES = ['contador', 'estudio contable', 'contador público', 'asesor contable']

def is_accountant_role(rol_wizard):
    """Check if rol_wizard indicates accountant role"""
    if not rol_wizard:
        return False
    rol_lower = str(rol_wizard).lower().strip()
    return any(accountant_role in rol_lower for accountant_role in ACCOUNTANT_ROLES)

def is_smb_role(rol_wizard):
    """
    Check if rol_wizard indicates SMB role (NOT accountant)
    IMPORTANT: Returns False for null/empty values
    """
    # If rol_wizard is null/empty, exclude from funnel
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    
    # SMB = any role that is NOT an accountant role
    return not is_accountant_role(rol_wizard)

def get_deal_contacts(deal_id):
    """Get all contacts associated with a deal"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/contacts"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            contact_ids = [assoc.get('toObjectId') for assoc in associations]
            
            # Fetch contact details
            contacts_data = []
            if contact_ids:
                for i in range(0, len(contact_ids), 100):
                    batch_ids = contact_ids[i:i+100]
                    url_batch = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/batch/read"
                    payload = {
                        "properties": ["email", "firstname", "lastname", "createdate", "rol_wizard", "lead_source"],
                        "inputs": [{"id": contact_id} for contact_id in batch_ids]
                    }
                    response = requests.post(url_batch, headers=HEADERS, json=payload, timeout=30)
                    if response.status_code == 200:
                        contacts = response.json().get('results', [])
                        for contact in contacts:
                            props = contact.get('properties', {})
                            # Exclude 'Usuario Invitado'
                            if props.get('lead_source') == 'Usuario Invitado':
                                continue
                            contacts_data.append({
                                'contact_id': contact.get('id'),
                                'email': props.get('email', ''),
                                'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                                'createdate': props.get('createdate', ''),
                                'rol_wizard': props.get('rol_wizard', '')
                            })
            return contacts_data
    except Exception as e:
        print(f"   ⚠️  Error fetching contacts for deal {deal_id}: {str(e)}")
    return []

def has_smb_contact(deal_id):
    """
    Check if deal should be included in SMB accountant-involved funnel.
    
    SIMPLIFIED LOGIC:
    - Deal is included if tiene_cuenta_contador > 0 AND has at least one contact
    - Contact types don't matter for inclusion (all are part of accountant influence):
      * Contacts with explicit SMB rol_wizard → SMB
      * Contacts with NO rol_wizard → TREATED AS SMB (assumed to be SMB, not accountants)
      * Contacts with accountant rol_wizard → Accountant (also part of accountant influence)
    - Only exclude deals with NO contacts at all
    
    Returns: (should_include, contact_count, smb_contact_count, contact_details)
    contact_details: dict with breakdown of contacts by type
    """
    contacts = get_deal_contacts(deal_id)
    if not contacts:
        return False, 0, 0, {
            'total': 0,
            'smb_explicit': 0,
            'smb_no_rol_wizard': 0,
            'smb_total': 0,
            'accountant': 0,
            'no_rol_wizard': 0,
            'usuario_invitado': 0,
            'contacts': []
        }
    
    contact_details = {
        'total': len(contacts),
        'smb_explicit': 0,  # Contacts with explicit SMB rol_wizard
        'smb_no_rol_wizard': 0,  # Contacts with no rol_wizard (treated as SMB)
        'smb_total': 0,  # Total SMB contacts (explicit + no rol_wizard)
        'accountant': 0,
        'no_rol_wizard': 0,  # Count of contacts without rol_wizard
        'usuario_invitado': 0,
        'contacts': []
    }
    
    for contact in contacts:
        rol_wizard = contact.get('rol_wizard', '')
        contact_info = {
            'contact_id': contact.get('contact_id'),
            'email': contact.get('email', ''),
            'name': contact.get('name', ''),
            'rol_wizard': rol_wizard if rol_wizard else '(empty)',
            'type': 'unknown'
        }
        
        if not rol_wizard or str(rol_wizard).strip() == '':
            # NO rol_wizard → TREATED AS SMB (assumed SMB, not accountant)
            contact_details['no_rol_wizard'] += 1
            contact_details['smb_no_rol_wizard'] += 1
            contact_details['smb_total'] += 1
            contact_info['type'] = 'no_rol_wizard_treated_as_smb'
        elif is_accountant_role(rol_wizard):
            contact_details['accountant'] += 1
            contact_info['type'] = 'accountant'
        elif is_smb_role(rol_wizard):
            contact_details['smb_explicit'] += 1
            contact_details['smb_total'] += 1
            contact_info['type'] = 'smb'
        else:
            # Unknown rol_wizard value → TREATED AS SMB
            contact_details['no_rol_wizard'] += 1
            contact_details['smb_no_rol_wizard'] += 1
            contact_details['smb_total'] += 1
            contact_info['type'] = 'no_rol_wizard_treated_as_smb'
        
        contact_details['contacts'].append(contact_info)
    
    # SIMPLIFIED: Deal is included if it has ANY contacts (all contact types indicate accountant influence)
    # Only exclude deals with NO contacts at all
    should_include = len(contacts) > 0
    
    return should_include, len(contacts), contact_details['smb_total'], contact_details

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

def has_accountant_company_association(deal_id):
    """
    Check if deal has companies associated with association type 8 
    ("Estudio Contable / Asesor / Consultor Externo del negocio").
    
    This is an alternative method to identify accountant involvement,
    using the Rollup field logic (counts companies with association label ID 8).
    
    Returns:
        (has_association, company_count, company_ids)
    """
    company_ids = get_deal_companies_with_association_type(deal_id, 8)
    return len(company_ids) > 0, len(company_ids), company_ids

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

def get_company_type(company_id):
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
            company_name, company_type = get_company_type(company_id)
            if company_type and company_type in ACCOUNTANT_COMPANY_TYPES:
                return True
    
    return False

def analyze_funnel_with_accountant(start_date, end_date):
    """
    Analyze the funnel for SMB deals WITH accountant involvement.
    
    FUNNEL LOGIC:
    ============
    1. Fetch all deals created in period where tiene_cuenta_contador > 0
    2. For each deal, check associated contacts - filter for contacts
    3. Track: Deal Created → Deal Closed Won
    4. Classify by ICP Operador vs ICP PYME
    5. Calculate revenue
    """
    # Validate date range
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    print(f"\n{'='*80}")
    print(f"SMB FUNNEL WITH ACCOUNTANT INVOLVEMENT")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    # ========================================================================
    # STEP 1: Fetch Deals with Accountant Involvement
    # ========================================================================
    print("📊 STEP 1: Fetching deals with accountant involvement...")
    print("   Using TWO criteria:")
    print("   1. tiene_cuenta_contador > 0 (Formula field - counts accountant companies)")
    print("   2. Has companies with association type 8 (Rollup field logic - 'Estudio Contable' label)")
    print()
    
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    
    # Method 1: Fetch deals with tiene_cuenta_contador > 0
    deals_by_formula = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "tiene_cuenta_contador", "operator": "GT", "value": "0"}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "primary_company_type", "tiene_cuenta_contador"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        deals_by_formula.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    print(f"   Method 1 (tiene_cuenta_contador > 0): Found {len(deals_by_formula)} deals")
    
    # Method 2: Fetch ALL deals in period, then check for association type 8
    print("   Method 2: Fetching all deals in period to check association type 8...")
    all_deals_in_period = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "primary_company_type", "tiene_cuenta_contador"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_deals_in_period.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    print(f"   Found {len(all_deals_in_period)} total deals in period")
    print("   Checking which deals have association type 8 (Estudio Contable)...")
    
    # Check each deal for association type 8
    deals_by_association = []
    deal_id_to_deal = {deal.get('id'): deal for deal in all_deals_in_period}
    
    for i, deal in enumerate(all_deals_in_period, 1):
        if i % 50 == 0:
            print(f"      Checking deal {i}/{len(all_deals_in_period)}...")
        deal_id = deal.get('id')
        has_assoc, company_count, company_ids = has_accountant_company_association(deal_id)
        if has_assoc:
            deals_by_association.append(deal_id)
        time.sleep(0.05)  # Rate limiting
    
    print(f"   Method 2 (association type 8): Found {len(deals_by_association)} deals")
    
    # Combine both methods (OR logic)
    deal_ids_by_formula = {deal.get('id') for deal in deals_by_formula}
    deal_ids_by_association = set(deals_by_association)
    
    all_deal_ids = deal_ids_by_formula | deal_ids_by_association
    all_deals_with_accountant = [deal_id_to_deal[deal_id] for deal_id in all_deal_ids if deal_id in deal_id_to_deal]
    
    # Track which method identified each deal
    deals_only_formula = deal_ids_by_formula - deal_ids_by_association
    deals_only_association = deal_ids_by_association - deal_ids_by_formula
    deals_both_methods = deal_ids_by_formula & deal_ids_by_association
    
    print()
    print(f"   📊 OVERLAP ANALYSIS:")
    print(f"   - Deals identified by BOTH methods: {len(deals_both_methods)}")
    print(f"   - Deals identified ONLY by tiene_cuenta_contador: {len(deals_only_formula)}")
    print(f"   - Deals identified ONLY by association type 8: {len(deals_only_association)}")
    print(f"   - TOTAL unique deals with accountant involvement: {len(all_deals_with_accountant)}")
    print()
    
    # ========================================================================
    # STEP 2: Filter for Deals with Contacts (Simplified Logic)
    # ========================================================================
    print("📊 STEP 2: Filtering for deals with contacts...")
    print("   SIMPLIFIED LOGIC: All contact types indicate accountant influence")
    print("   - SMB contacts → included")
    print("   - Accountant contacts → included (part of accountant influence)")
    print("   - No rol_wizard contacts → included (treated as SMB)")
    print("   - Only exclude deals with NO contacts at all\n")
    
    deals_with_contacts = []
    edge_cases = {
        'no_contacts': [],
        'only_accountant_contacts': [],
        'explicit_smb_only': [],
        'no_rol_wizard_only': [],
        'explicit_smb_and_no_rol': [],
        'accountant_and_smb': [],
        'accountant_and_no_rol_wizard': [],
        'only_accountant_contacts_included': []
    }
    
    for i, deal in enumerate(all_deals_with_accountant, 1):
        if i % 10 == 0:
            print(f"   Processing deal {i}/{len(all_deals_with_accountant)}...")
        
        deal_id = deal.get('id')
        deal_name = deal.get('properties', {}).get('dealname', 'N/A')
        should_include, total_contacts, smb_count, contact_details = has_smb_contact(deal_id)
        
        deal_edge_case = {
            'deal_id': deal_id,
            'deal_name': deal_name,
            'total_contacts': total_contacts,
            'contact_breakdown': contact_details
        }
        
        # Use breakdown from contact_details (with safe defaults)
        explicit_smb = contact_details.get('smb_explicit', 0)
        no_rol_wizard_count = contact_details.get('smb_no_rol_wizard', 0)
        accountant_count = contact_details.get('accountant', 0)
        
        if should_include:
            deals_with_contacts.append(deal)
            # Categorize included deals
            if accountant_count > 0 and explicit_smb > 0:
                edge_cases['accountant_and_smb'].append(deal_edge_case)
            elif accountant_count > 0 and no_rol_wizard_count > 0:
                edge_cases['accountant_and_no_rol_wizard'].append(deal_edge_case)
            elif accountant_count > 0 and explicit_smb == 0 and no_rol_wizard_count == 0:
                # Only accountant contacts - NOW INCLUDED (part of accountant influence)
                edge_cases['only_accountant_contacts_included'].append(deal_edge_case)
            elif explicit_smb > 0 and no_rol_wizard_count == 0 and accountant_count == 0:
                edge_cases['explicit_smb_only'].append(deal_edge_case)
            elif no_rol_wizard_count > 0 and explicit_smb == 0 and accountant_count == 0:
                edge_cases['no_rol_wizard_only'].append(deal_edge_case)
            elif explicit_smb > 0 and no_rol_wizard_count > 0:
                edge_cases['explicit_smb_and_no_rol'].append(deal_edge_case)
        else:
            # Only exclude deals with NO contacts
            if total_contacts == 0:
                edge_cases['no_contacts'].append(deal_edge_case)
        
        time.sleep(0.1)  # Rate limiting
    
    excluded_count = len(edge_cases['no_contacts'])
    print(f"   Found {len(deals_with_contacts)} deals with contacts (all contact types included)")
    print(f"   Excluded: {excluded_count} deals (no contacts at all)\n")
    
    # ========================================================================
    # EDGE CASE ANALYSIS REPORT
    # ========================================================================
    print("="*80)
    print("EDGE CASE ANALYSIS - Contact rol_wizard Status")
    print("="*80)
    print()
    print("**SIMPLIFIED LOGIC:**")
    print("  - All contact types indicate accountant influence → INCLUDED")
    print("  - Contacts with no rol_wizard are TREATED AS SMB")
    print("  - Only exclude deals with NO contacts at all")
    print()
    
    excluded_count = len(edge_cases['no_contacts'])
    
    print(f"**Summary:**")
    print(f"- Deals INCLUDED in funnel: {len(deals_with_contacts)}")
    print(f"  • Deals with explicit SMB contacts: {len(edge_cases['explicit_smb_only']) + len(edge_cases['explicit_smb_and_no_rol']) + len(edge_cases['accountant_and_smb'])}")
    print(f"  • Deals with no rol_wizard contacts (treated as SMB): {len(edge_cases['no_rol_wizard_only']) + len(edge_cases['explicit_smb_and_no_rol']) + len(edge_cases['accountant_and_no_rol_wizard'])}")
    print(f"  • Deals with ONLY accountant contacts (included - part of accountant influence): {len(edge_cases['only_accountant_contacts_included'])}")
    print(f"  • Deals with both explicit SMB + no rol_wizard: {len(edge_cases['explicit_smb_and_no_rol'])}")
    print(f"- Deals EXCLUDED: {excluded_count} (no contacts at all)")
    print()
    
    # No contacts
    if edge_cases['no_contacts']:
        print(f"**1. Deals with NO contacts ({len(edge_cases['no_contacts'])} deals) - EXCLUDED:**")
        print("   These deals have accountant involvement (tiene_cuenta_contador > 0) but no contacts associated.")
        print("   This could indicate:")
        print("   - Deal created directly without contact association")
        print("   - Contact association removed or never created")
        print("   - Data quality issue")
        print()
        for case in edge_cases['no_contacts'][:5]:
            print(f"   - Deal: {case['deal_name'][:60]}")
            print(f"     ID: {case['deal_id']}")
        if len(edge_cases['no_contacts']) > 5:
            print(f"   ... and {len(edge_cases['no_contacts']) - 5} more")
        print()
    
    # Included deals breakdown
    print("**INCLUDED DEALS BREAKDOWN:**")
    print()
    
    # Only accountant contacts - NOW INCLUDED
    if edge_cases['only_accountant_contacts_included']:
        print(f"**2. Deals with ONLY accountant contacts ({len(edge_cases['only_accountant_contacts_included'])} deals) - INCLUDED:**")
        print("   ✅ These deals are INCLUDED (accountant contacts are part of accountant influence).")
        print("   These deals have accountant involvement (tiene_cuenta_contador > 0) AND accountant contacts.")
        print("   This indicates strong accountant influence in the sales process.")
        print()
        for case in edge_cases['only_accountant_contacts_included'][:5]:
            print(f"   - Deal: {case['deal_name'][:60]}")
            print(f"     ID: {case['deal_id']}")
            print(f"     Contacts: {case['contact_breakdown'].get('accountant', 0)} accountant(s)")
            for contact in case['contact_breakdown']['contacts'][:3]:
                print(f"       • {contact['email']} ({contact['rol_wizard']})")
        if len(edge_cases['only_accountant_contacts_included']) > 5:
            print(f"   ... and {len(edge_cases['only_accountant_contacts_included']) - 5} more")
        print()
    
    # Explicit SMB only
    if edge_cases['explicit_smb_only']:
        print(f"**3. Deals with explicit SMB contacts only ({len(edge_cases['explicit_smb_only'])} deals) - INCLUDED:**")
        print("   These deals have contacts with explicit SMB rol_wizard (no accountant contacts).")
        print()
        for case in edge_cases['explicit_smb_only'][:3]:
            print(f"   - Deal: {case['deal_name'][:60]}")
            print(f"     ID: {case['deal_id']}")
        if len(edge_cases['explicit_smb_only']) > 3:
            print(f"   ... and {len(edge_cases['explicit_smb_only']) - 3} more")
        print()
    
    # No rol_wizard only (treated as SMB)
    if edge_cases['no_rol_wizard_only']:
        print(f"**4. Deals with contacts that have NO rol_wizard ({len(edge_cases['no_rol_wizard_only'])} deals) - INCLUDED:**")
        print("   ✅ These deals are INCLUDED (contacts with no rol_wizard are treated as SMB).")
        print("   These contacts may have:")
        print("   - Never gone through the wizard (older contacts, direct referrals)")
        print("   - rol_wizard field not populated (data quality issue)")
        print("   - Still valid SMB deals referred by accountants")
        print()
        for case in edge_cases['no_rol_wizard_only'][:5]:
            print(f"   - Deal: {case['deal_name'][:60]}")
            print(f"     ID: {case['deal_id']}")
            print(f"     Contacts: {case['contact_breakdown'].get('no_rol_wizard', 0)} contact(s) without rol_wizard (treated as SMB)")
            for contact in case['contact_breakdown']['contacts'][:3]:
                print(f"       • {contact['email']} ({contact['name']}) - rol_wizard: {contact['rol_wizard']}")
        if len(edge_cases['no_rol_wizard_only']) > 5:
            print(f"   ... and {len(edge_cases['no_rol_wizard_only']) - 5} more")
        print()
    
    # Accountant + no rol_wizard (treated as SMB)
    if edge_cases['accountant_and_no_rol_wizard']:
        print(f"**5. Deals with accountant contacts + contacts without rol_wizard ({len(edge_cases['accountant_and_no_rol_wizard'])} deals) - INCLUDED:**")
        print("   ✅ These deals are INCLUDED (contacts without rol_wizard are treated as SMB).")
        print("   These deals have both accountant contacts and contacts without rol_wizard.")
        print("   The contacts without rol_wizard are treated as SMB contacts.")
        print()
        for case in edge_cases['accountant_and_no_rol_wizard'][:5]:
            print(f"   - Deal: {case['deal_name'][:60]}")
            print(f"     ID: {case['deal_id']}")
            print(f"     Contacts: {case['contact_breakdown'].get('accountant', 0)} accountant(s), {case['contact_breakdown'].get('no_rol_wizard', 0)} without rol_wizard (treated as SMB)")
            for contact in case['contact_breakdown']['contacts'][:3]:
                print(f"       • {contact['email']} - Type: {contact['type']}, rol_wizard: {contact['rol_wizard']}")
        if len(edge_cases['accountant_and_no_rol_wizard']) > 5:
            print(f"   ... and {len(edge_cases['accountant_and_no_rol_wizard']) - 5} more")
        print()
    
    # Accountant + explicit SMB
    if edge_cases['accountant_and_smb']:
        print(f"**6. Deals with BOTH accountant AND explicit SMB contacts ({len(edge_cases['accountant_and_smb'])} deals) - INCLUDED:**")
        print("   These deals are included in the funnel (have explicit SMB contacts).")
        print("   They also have accountant contacts, which is normal for accountant-referred SMB deals.")
        print()
        for case in edge_cases['accountant_and_smb'][:5]:
            print(f"   - Deal: {case['deal_name'][:60]}")
            print(f"     ID: {case['deal_id']}")
            print(f"     Contacts: {case['contact_breakdown'].get('accountant', 0)} accountant(s), {case['contact_breakdown'].get('smb_explicit', 0)} explicit SMB")
            for contact in case['contact_breakdown']['contacts'][:3]:
                print(f"       • {contact['email']} - Type: {contact['type']}, rol_wizard: {contact['rol_wizard']}")
        if len(edge_cases['accountant_and_smb']) > 5:
            print(f"   ... and {len(edge_cases['accountant_and_smb']) - 5} more")
        print()
    
    # Explicit SMB + no rol_wizard
    if edge_cases['explicit_smb_and_no_rol']:
        print(f"**7. Deals with explicit SMB + no rol_wizard contacts ({len(edge_cases['explicit_smb_and_no_rol'])} deals) - INCLUDED:**")
        print("   These deals have both explicit SMB contacts and contacts without rol_wizard.")
        print()
        for case in edge_cases['explicit_smb_and_no_rol'][:3]:
            print(f"   - Deal: {case['deal_name'][:60]}")
            print(f"     ID: {case['deal_id']}")
        if len(edge_cases['explicit_smb_and_no_rol']) > 3:
            print(f"   ... and {len(edge_cases['explicit_smb_and_no_rol']) - 3} more")
        print()
    
    print("="*80)
    print()
    
    # ========================================================================
    # STEP 3: Filter for Closed Won Deals
    # ========================================================================
    print("📊 STEP 3: Filtering for closed won deals...")
    closed_won_deals = []
    
    for deal in deals_with_contacts:
        props = deal.get('properties', {})
        deal_createdate_str = props.get('createdate', '')
        deal_closedate_str = props.get('closedate', '')
        dealstage = props.get('dealstage', '')
        
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
    
    print(f"   Found {len(closed_won_deals)} closed won deals (created AND closed in period)\n")
    
    # ========================================================================
    # STEP 4: Classify by ICP Operador vs ICP PYME + Coverage Analysis
    # ========================================================================
    print("📊 STEP 4: Classifying by ICP and analyzing coverage...")
    icp_operador_deals = []
    icp_pyme_deals = []
    
    # Track ICP coverage (type field population)
    companies_analyzed = {}
    companies_with_type = 0
    companies_without_type = 0
    
    for deal in closed_won_deals:
        deal_id = deal.get('id')
        props = deal.get('properties', {})
        primary_company_type = props.get('primary_company_type', '')
        
        # Track company type coverage
        company_id = get_primary_company_id(deal_id)
        if company_id and company_id not in companies_analyzed:
            company_name, company_type = get_company_type(company_id)
            companies_analyzed[company_id] = {
                'name': company_name,
                'type': company_type,
                'deal_id': deal_id
            }
            if company_type and company_type.strip() and company_type.strip().lower() not in ['null', 'none', '']:
                companies_with_type += 1
            else:
                companies_without_type += 1
        
        # Classify deal by ICP
        if is_icp_operador(deal):
            icp_operador_deals.append(deal)
        else:
            icp_pyme_deals.append(deal)
    
    total_companies_analyzed = len(companies_analyzed)
    coverage_percentage = (companies_with_type / total_companies_analyzed * 100) if total_companies_analyzed > 0 else 0
    
    print(f"   ICP Operador: {len(icp_operador_deals)}")
    print(f"   ICP PYME: {len(icp_pyme_deals)}")
    print(f"   ICP Coverage: {companies_with_type}/{total_companies_analyzed} companies ({coverage_percentage:.1f}%) have type field populated\n")
    
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
    
    print(f"   Total Revenue: ${total_revenue:,.2f}")
    print(f"   ICP Operador Revenue: ${icp_operador_revenue:,.2f}")
    print(f"   ICP PYME Revenue: ${icp_pyme_revenue:,.2f}\n")
    
    # ========================================================================
    # Calculate Conversion Rates
    # ========================================================================
    deal_created_count = len(deals_with_contacts)
    closed_won_count = len(closed_won_deals)
    deal_to_won_rate = (closed_won_count / deal_created_count * 100) if deal_created_count > 0 else 0
    
    # ========================================================================
    # Print Results
    # ========================================================================
    print("="*80)
    print("FUNNEL RESULTS")
    print("="*80)
    print()
    print("**FUNNEL PATH:** Deal Created (with accountant + SMB contacts) → Deal Closed Won")
    print()
    print("| Stage | Count | Conversion Rate |")
    print("|-------|-------|-----------------|")
    print(f"| Deal Created | {deal_created_count} | - |")
    print(f"| Deal Closed Won | {closed_won_count} | {deal_to_won_rate:.1f}% |")
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
    print(f"| **Total** | **{closed_won_count}** | **100.0%** | **${total_revenue:,.2f}** |")
    print()
    print("**Note:** ICP Operador classification is based on PRIMARY company type:")
    print(f"  - {', '.join(ACCOUNTANT_COMPANY_TYPES)}")
    print()
    
    # ========================================================================
    # ICP COVERAGE ANALYSIS
    # ========================================================================
    print("="*80)
    print("ICP COVERAGE ANALYSIS (Primary Companies from Closed Won Deals)")
    print("="*80)
    print()
    print("This shows how many PRIMARY companies have their 'type' field populated,")
    print("which enables ICP classification. Industry enrichment workflow populates")
    print("this field based on industria field, improving coverage over time.")
    print()
    print("| Metric | Count | Percentage |")
    print("|--------|-------|------------|")
    print(f"| Total PRIMARY Companies Analyzed | {total_companies_analyzed} | 100.0% |")
    print(f"| Companies WITH Type Field Populated | {companies_with_type} | {coverage_percentage:.1f}% |")
    print(f"| Companies WITHOUT Type Field (NULL/Empty) | {companies_without_type} | {(companies_without_type / total_companies_analyzed * 100) if total_companies_analyzed > 0 else 0:.1f}% |")
    print()
    if companies_without_type > 0:
        print("**Companies without type field:**")
        print("These companies cannot be classified as ICP Operador or ICP PYME")
        print("until their 'type' field is populated (via industry enrichment workflow).")
        print()
        # Show sample companies without type
        companies_without_type_list = [
            (cid, info['name'], info['deal_id'])
            for cid, info in companies_analyzed.items()
            if not info['type'] or info['type'].strip() == '' or info['type'].strip().lower() in ['null', 'none']
        ]
        print(f"**Sample companies without type field (showing first 10 of {companies_without_type}):**")
        for company_id, company_name, deal_id in companies_without_type_list[:10]:
            print(f"  - {company_name} (Company ID: {company_id}, Deal ID: {deal_id})")
        if len(companies_without_type_list) > 10:
            print(f"  ... and {len(companies_without_type_list) - 10} more")
        print()
    print()
    
    # Prepare results dictionary
    results = {
        'deal_created_count': deal_created_count,
        'closed_won_count': closed_won_count,
        'icp_operador_count': len(icp_operador_deals),
        'icp_pyme_count': len(icp_pyme_deals),
        'deal_to_won_rate': deal_to_won_rate,
        'total_revenue': total_revenue,
        'icp_operador_revenue': icp_operador_revenue,
        'icp_pyme_revenue': icp_pyme_revenue,
        'icp_coverage_total_companies': total_companies_analyzed,
        'icp_coverage_with_type': companies_with_type,
        'icp_coverage_without_type': companies_without_type,
        'icp_coverage_percentage': round(coverage_percentage, 2),
        'start_date': start_date,
        'end_date': end_date
    }
    
    # Save to CSV
    output_dir = "tools/outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    df_data = {
        'Period': [f"{start_date} to {end_date}"],
        'Deal_Created': [deal_created_count],
        'Deal_Closed_Won': [closed_won_count],
        'Deal_to_Won_Rate_%': [round(deal_to_won_rate, 2)],
        'ICP_Operador_Count': [len(icp_operador_deals)],
        'ICP_Operador_Revenue': [round(icp_operador_revenue, 2)],
        'ICP_PYME_Count': [len(icp_pyme_deals)],
        'ICP_PYME_Revenue': [round(icp_pyme_revenue, 2)],
        'Total_Revenue': [round(total_revenue, 2)],
        'ICP_Coverage_Total_Companies': [total_companies_analyzed],
        'ICP_Coverage_With_Type': [companies_with_type],
        'ICP_Coverage_Without_Type': [companies_without_type],
        'ICP_Coverage_Percentage': [round(coverage_percentage, 2)],
    }
    
    df = pd.DataFrame(df_data)
    
    # Generate filename with date range
    start_date_clean = start_date.replace('-', '')
    end_date_clean = end_date.replace('-', '')
    output_file = f"{output_dir}/smb_accountant_involved_funnel_{start_date_clean}_{end_date_clean}.csv"
    
    df.to_csv(output_file, index=False)
    print(f"📄 Results saved to CSV: {output_file}")
    print()
    
    return results

def analyze_funnel_without_accountant(start_date, end_date):
    """
    Analyze the funnel for SMB deals WITHOUT accountant involvement.
    
    FUNNEL LOGIC:
    ============
    1. Fetch all deals created in period where tiene_cuenta_contador = 0 or null
    2. For each deal, check associated contacts - filter for contacts
    3. Track: Deal Created → Deal Closed Won
    4. Classify by ICP Operador vs ICP PYME
    5. Calculate revenue
    """
    # Validate date range
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    print(f"\n{'='*80}")
    print(f"SMB FUNNEL WITHOUT ACCOUNTANT INVOLVEMENT")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    # ========================================================================
    # STEP 1: Fetch Deals WITHOUT Accountant Involvement
    # ========================================================================
    print("📊 STEP 1: Fetching deals WITHOUT accountant involvement...")
    print("   Excluding deals that meet EITHER criteria:")
    print("   1. tiene_cuenta_contador > 0 (Formula field)")
    print("   2. Has companies with association type 8 (Rollup field logic)")
    print()
    
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    
    # Fetch all deals where tiene_cuenta_contador is 0 or null
    deals_by_formula = []
    after = None
    
    while True:
        # Filter for deals where tiene_cuenta_contador is 0 or null (OR logic)
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                        {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
                        {"propertyName": "tiene_cuenta_contador", "operator": "EQ", "value": "0"}
                    ]
                },
                {
                    "filters": [
                        {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                        {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
                        {"propertyName": "tiene_cuenta_contador", "operator": "NOT_HAS_PROPERTY"}
                    ]
                }
            ],
            "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "primary_company_type", "tiene_cuenta_contador"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        # Filter results to ensure tiene_cuenta_contador is 0 or null
        filtered_results = []
        for deal in results:
            tiene_cuenta = deal.get('properties', {}).get('tiene_cuenta_contador', '')
            if tiene_cuenta == '' or tiene_cuenta == '0' or tiene_cuenta is None:
                filtered_results.append(deal)
        deals_by_formula.extend(filtered_results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    print(f"   Found {len(deals_by_formula)} deals with tiene_cuenta_contador = 0 or null")
    print("   Now checking which of these also have NO association type 8...")
    
    # Check each deal to exclude those with association type 8
    all_deals_without_accountant = []
    for i, deal in enumerate(deals_by_formula, 1):
        if i % 50 == 0:
            print(f"      Checking deal {i}/{len(deals_by_formula)}...")
        deal_id = deal.get('id')
        has_assoc, company_count, company_ids = has_accountant_company_association(deal_id)
        if not has_assoc:  # Only include if NO association type 8
            all_deals_without_accountant.append(deal)
        time.sleep(0.05)  # Rate limiting
    
    print(f"   After excluding deals with association type 8: {len(all_deals_without_accountant)} deals")
    print()
    
    # ========================================================================
    # STEP 2: Filter for Deals with Contacts
    # ========================================================================
    print("📊 STEP 2: Filtering for deals with contacts...")
    deals_with_contacts = []
    
    for i, deal in enumerate(all_deals_without_accountant, 1):
        if i % 50 == 0:
            print(f"   Processing deal {i}/{len(all_deals_without_accountant)}...")
        
        deal_id = deal.get('id')
        should_include, total_contacts, smb_count, contact_details = has_smb_contact(deal_id)
        
        if should_include:
            deals_with_contacts.append(deal)
        
        time.sleep(0.05)  # Rate limiting
    
    print(f"   Found {len(deals_with_contacts)} deals with contacts\n")
    
    # ========================================================================
    # STEP 3: Filter for Closed Won Deals
    # ========================================================================
    print("📊 STEP 3: Filtering for closed won deals...")
    closed_won_deals = []
    
    for deal in deals_with_contacts:
        props = deal.get('properties', {})
        deal_createdate_str = props.get('createdate', '')
        deal_closedate_str = props.get('closedate', '')
        dealstage = props.get('dealstage', '')
        
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
    
    print(f"   Found {len(closed_won_deals)} closed won deals (created AND closed in period)\n")
    
    # ========================================================================
    # STEP 4: Classify by ICP Operador vs ICP PYME
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
    print(f"   ICP PYME: {len(icp_pyme_deals)}\n")
    
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
    
    print(f"   Total Revenue: ${total_revenue:,.2f}")
    print(f"   ICP Operador Revenue: ${icp_operador_revenue:,.2f}")
    print(f"   ICP PYME Revenue: ${icp_pyme_revenue:,.2f}\n")
    
    # ========================================================================
    # Calculate Conversion Rates
    # ========================================================================
    deal_created_count = len(deals_with_contacts)
    closed_won_count = len(closed_won_deals)
    deal_to_won_rate = (closed_won_count / deal_created_count * 100) if deal_created_count > 0 else 0
    
    # ========================================================================
    # Print Results
    # ========================================================================
    print("="*80)
    print("FUNNEL RESULTS (WITHOUT ACCOUNTANT)")
    print("="*80)
    print()
    print("**FUNNEL PATH:** Deal Created (no accountant involvement) → Deal Closed Won")
    print()
    print("| Stage | Count | Conversion Rate |")
    print("|-------|-------|-----------------|")
    print(f"| Deal Created | {deal_created_count} | - |")
    print(f"| Deal Closed Won | {closed_won_count} | {deal_to_won_rate:.1f}% |")
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
    print(f"| **Total** | **{closed_won_count}** | **100.0%** | **${total_revenue:,.2f}** |")
    print()
    
    # Prepare results dictionary
    results = {
        'deal_created_count': deal_created_count,
        'closed_won_count': closed_won_count,
        'icp_operador_count': len(icp_operador_deals),
        'icp_pyme_count': len(icp_pyme_deals),
        'deal_to_won_rate': deal_to_won_rate,
        'total_revenue': total_revenue,
        'icp_operador_revenue': icp_operador_revenue,
        'icp_pyme_revenue': icp_pyme_revenue,
        'start_date': start_date,
        'end_date': end_date
    }
    
    return results

def analyze_funnel(start_date, end_date):
    """
    Analyze both funnels (WITH and WITHOUT accountant involvement) and compare them.
    """
    # Analyze WITH accountant
    results_with = analyze_funnel_with_accountant(start_date, end_date)
    
    # Analyze WITHOUT accountant
    results_without = analyze_funnel_without_accountant(start_date, end_date)
    
    # ========================================================================
    # COMPARISON SUMMARY
    # ========================================================================
    print("\n" + "="*80)
    print("FUNNEL COMPARISON: WITH vs WITHOUT ACCOUNTANT INVOLVEMENT")
    print("="*80)
    print()
    
    print("| Metric | WITH Accountant | WITHOUT Accountant | Difference | % Difference |")
    print("|--------|-----------------|-------------------|------------|--------------|")
    
    # Deal Created
    deal_created_with = results_with.get('deal_created_count', 0)
    deal_created_without = results_without.get('deal_created_count', 0)
    deal_created_diff = deal_created_with - deal_created_without
    deal_created_pct_diff = (deal_created_diff / deal_created_without * 100) if deal_created_without > 0 else 0
    print(f"| Deal Created | {deal_created_with} | {deal_created_without} | {deal_created_diff:+d} | {deal_created_pct_diff:+.1f}% |")
    
    # Deal Closed Won
    closed_won_with = results_with.get('closed_won_count', 0)
    closed_won_without = results_without.get('closed_won_count', 0)
    closed_won_diff = closed_won_with - closed_won_without
    closed_won_pct_diff = (closed_won_diff / closed_won_without * 100) if closed_won_without > 0 else 0
    print(f"| Deal Closed Won | {closed_won_with} | {closed_won_without} | {closed_won_diff:+d} | {closed_won_pct_diff:+.1f}% |")
    
    # Deal to Won Rate
    rate_with = results_with.get('deal_to_won_rate', 0)
    rate_without = results_without.get('deal_to_won_rate', 0)
    rate_diff = rate_with - rate_without
    print(f"| Deal→Won Rate | {rate_with:.1f}% | {rate_without:.1f}% | {rate_diff:+.1f}pp | - |")
    
    # Total Revenue
    revenue_with = results_with.get('total_revenue', 0)
    revenue_without = results_without.get('total_revenue', 0)
    revenue_diff = revenue_with - revenue_without
    revenue_pct_diff = (revenue_diff / revenue_without * 100) if revenue_without > 0 else 0
    print(f"| Total Revenue | ${revenue_with:,.2f} | ${revenue_without:,.2f} | ${revenue_diff:+,.2f} | {revenue_pct_diff:+.1f}% |")
    
    # ICP Operador Count
    icp_operador_with = results_with.get('icp_operador_count', 0)
    icp_operador_without = results_without.get('icp_operador_count', 0)
    icp_operador_diff = icp_operador_with - icp_operador_without
    print(f"| ICP Operador Count | {icp_operador_with} | {icp_operador_without} | {icp_operador_diff:+d} | - |")
    
    # ICP PYME Count
    icp_pyme_with = results_with.get('icp_pyme_count', 0)
    icp_pyme_without = results_without.get('icp_pyme_count', 0)
    icp_pyme_diff = icp_pyme_with - icp_pyme_without
    print(f"| ICP PYME Count | {icp_pyme_with} | {icp_pyme_without} | {icp_pyme_diff:+d} | - |")
    
    print()
    
    # Save comparison to CSV
    output_dir = "tools/outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    df_data = {
        'Period': [f"{start_date} to {end_date}"],
        'With_Accountant_Deal_Created': [deal_created_with],
        'With_Accountant_Deal_Closed_Won': [closed_won_with],
        'With_Accountant_Deal_to_Won_Rate_%': [round(rate_with, 2)],
        'With_Accountant_ICP_Operador_Count': [results_with.get('icp_operador_count', 0)],
        'With_Accountant_ICP_Operador_Revenue': [round(results_with.get('icp_operador_revenue', 0), 2)],
        'With_Accountant_ICP_PYME_Count': [results_with.get('icp_pyme_count', 0)],
        'With_Accountant_ICP_PYME_Revenue': [round(results_with.get('icp_pyme_revenue', 0), 2)],
        'With_Accountant_Total_Revenue': [round(revenue_with, 2)],
        'Without_Accountant_Deal_Created': [deal_created_without],
        'Without_Accountant_Deal_Closed_Won': [closed_won_without],
        'Without_Accountant_Deal_to_Won_Rate_%': [round(rate_without, 2)],
        'Without_Accountant_ICP_Operador_Count': [results_without.get('icp_operador_count', 0)],
        'Without_Accountant_ICP_Operador_Revenue': [round(results_without.get('icp_operador_revenue', 0), 2)],
        'Without_Accountant_ICP_PYME_Count': [results_without.get('icp_pyme_count', 0)],
        'Without_Accountant_ICP_PYME_Revenue': [round(results_without.get('icp_pyme_revenue', 0), 2)],
        'Without_Accountant_Total_Revenue': [round(revenue_without, 2)],
        'Difference_Deal_Created': [deal_created_diff],
        'Difference_Deal_Closed_Won': [closed_won_diff],
        'Difference_Deal_to_Won_Rate_pp': [round(rate_diff, 2)],
        'Difference_Total_Revenue': [round(revenue_diff, 2)],
    }
    
    df = pd.DataFrame(df_data)
    
    # Generate filename with date range
    start_date_clean = start_date.replace('-', '')
    end_date_clean = end_date.replace('-', '')
    output_file = f"{output_dir}/smb_accountant_funnel_comparison_{start_date_clean}_{end_date_clean}.csv"
    
    df.to_csv(output_file, index=False)
    print(f"📄 Comparison results saved to CSV: {output_file}")
    print()
    
    return {
        'with_accountant': results_with,
        'without_accountant': results_without,
        'comparison': df_data,
        'csv_file': output_file
    }

def create_funnel_visualization(csv_file_path, output_dir=None):
    """
    Create comprehensive funnel comparison visualization from CSV output.
    
    Args:
        csv_file_path: Path to the CSV file generated by analyze_funnel
        output_dir: Directory to save visualization (defaults to same dir as CSV)
    
    Returns:
        Path to saved visualization file
    """
    # Read CSV data
    df = pd.read_csv(csv_file_path)
    
    # Check if this is a comparison CSV (has both WITH and WITHOUT columns)
    is_comparison = 'With_Accountant_Deal_Created' in df.columns
    
    if is_comparison:
        return create_comparison_visualization(df, csv_file_path, output_dir)
    else:
        # Single funnel visualization (legacy support)
        return create_single_funnel_visualization(df, csv_file_path, output_dir)

def create_comparison_visualization(df, csv_file_path, output_dir=None):
    """Create side-by-side comparison visualization for WITH vs WITHOUT accountant funnels"""
    row = df.iloc[0]
    
    # Extract values
    period = row.get('Period', 'N/A')
    
    # WITH Accountant
    with_deal_created = int(row.get('With_Accountant_Deal_Created', 0))
    with_deal_won = int(row.get('With_Accountant_Deal_Closed_Won', 0))
    with_deal_to_won = float(row.get('With_Accountant_Deal_to_Won_Rate_%', 0))
    with_revenue = float(row.get('With_Accountant_Total_Revenue', 0))
    with_icp_operador = int(row.get('With_Accountant_ICP_Operador_Count', 0))
    with_icp_pyme = int(row.get('With_Accountant_ICP_PYME_Count', 0))
    
    # WITHOUT Accountant
    without_deal_created = int(row.get('Without_Accountant_Deal_Created', 0))
    without_deal_won = int(row.get('Without_Accountant_Deal_Closed_Won', 0))
    without_deal_to_won = float(row.get('Without_Accountant_Deal_to_Won_Rate_%', 0))
    without_revenue = float(row.get('Without_Accountant_Total_Revenue', 0))
    without_icp_operador = int(row.get('Without_Accountant_ICP_Operador_Count', 0))
    without_icp_pyme = int(row.get('Without_Accountant_ICP_PYME_Count', 0))
    
    # Set style
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Create figure with larger size and better spacing for responsiveness
    fig = plt.figure(figsize=(20, 14))
    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35, 
                           height_ratios=[2, 1, 1], width_ratios=[1, 1],
                           left=0.08, right=0.95, top=0.92, bottom=0.08)
    
    # ===== SIDE-BY-SIDE FUNNEL CHARTS =====
    # WITH Accountant
    ax_with = fig.add_subplot(gs[0, 0])
    stages = ['Deal Created', 'Deal Closed Won']
    values_with = [with_deal_created, with_deal_won]
    percentages_with = [
        100,
        (with_deal_won/with_deal_created*100) if with_deal_created > 0 else 0
    ]
    
    colors = ['#4A90E2', '#9370DB']
    y_positions = [0, 1.5]
    max_width = max(values_with) if values_with and max(values_with) > 0 else 1
    
    for stage, value, pct, y_pos, color in zip(stages, values_with, percentages_with, y_positions, colors):
        width = (value / max_width) * 10 if max_width > 0 else 0.5
        ax_with.barh(y_pos, width, height=0.8, color=color, alpha=0.85, 
                     edgecolor='white', linewidth=2.5)
        ax_with.text(width/2, y_pos, f'{value:,}\n({pct:.1f}%)', 
                    ha='center', va='center', fontsize=12, fontweight='bold', 
                    color='white')
        ax_with.text(-1.0, y_pos, stage, ha='right', va='center', 
                    fontsize=12, fontweight='bold', color='#2c3e50')
    
    ax_with.set_xlim(-3, 12)
    ax_with.set_ylim(-0.5, 2.5)
    # Shorten period text if too long
    period_short = period if len(period) < 30 else period[:27] + "..."
    ax_with.set_title(f'WITH Accountant Involvement\n{period_short}', fontsize=14, fontweight='bold', pad=15)
    ax_with.axis('off')
    
    # WITHOUT Accountant
    ax_without = fig.add_subplot(gs[0, 1])
    values_without = [without_deal_created, without_deal_won]
    percentages_without = [
        100,
        (without_deal_won/without_deal_created*100) if without_deal_created > 0 else 0
    ]
    
    max_width_without = max(values_without) if values_without and max(values_without) > 0 else 1
    
    for stage, value, pct, y_pos, color in zip(stages, values_without, percentages_without, y_positions, colors):
        width = (value / max_width_without) * 10 if max_width_without > 0 else 0.5
        ax_without.barh(y_pos, width, height=0.8, color=color, alpha=0.85, 
                       edgecolor='white', linewidth=2.5)
        ax_without.text(width/2, y_pos, f'{value:,}\n({pct:.1f}%)', 
                       ha='center', va='center', fontsize=12, fontweight='bold', 
                       color='white')
        ax_without.text(-1.0, y_pos, stage, ha='right', va='center', 
                       fontsize=12, fontweight='bold', color='#2c3e50')
    
    ax_without.set_xlim(-3, 12)
    ax_without.set_ylim(-0.5, 2.5)
    # Shorten period text if too long
    period_short = period if len(period) < 30 else period[:27] + "..."
    ax_without.set_title(f'WITHOUT Accountant Involvement\n{period_short}', fontsize=14, fontweight='bold', pad=15)
    ax_without.axis('off')
    
    # ===== CONVERSION RATES COMPARISON =====
    ax1 = fig.add_subplot(gs[1, 0])
    categories = ['Deal→Won Rate']
    with_rates = [with_deal_to_won]
    without_rates = [without_deal_to_won]
    x = range(len(categories))
    width = 0.35
    
    bars1 = ax1.bar([i - width/2 for i in x], with_rates, width, label='WITH Accountant', color='#4A90E2', alpha=0.8)
    bars2 = ax1.bar([i + width/2 for i in x], without_rates, width, label='WITHOUT Accountant', color='#E74C3C', alpha=0.8)
    
    max_rate = max(max(with_rates), max(without_rates)) if with_rates and without_rates else 100
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + max_rate * 0.03,
                f'{height:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')
    for bar in bars2:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + max_rate * 0.03,
                f'{height:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    ax1.set_ylabel('Conversion Rate (%)', fontsize=11, fontweight='bold')
    ax1.set_title('Conversion Rates Comparison', fontsize=12, fontweight='bold', pad=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, fontsize=10)
    ax1.legend(fontsize=9, loc='upper right')
    ax1.grid(axis='y', alpha=0.3, linestyle='--')
    ax1.tick_params(labelsize=10)
    
    # ===== REVENUE COMPARISON =====
    ax2 = fig.add_subplot(gs[1, 1])
    revenue_categories = ['Total Revenue']
    with_rev = [with_revenue]
    without_rev = [without_revenue]
    x_rev = range(len(revenue_categories))
    
    bars1_rev = ax2.bar([i - width/2 for i in x_rev], with_rev, width, label='WITH Accountant', color='#27AE60', alpha=0.8)
    bars2_rev = ax2.bar([i + width/2 for i in x_rev], without_rev, width, label='WITHOUT Accountant', color='#E74C3C', alpha=0.8)
    
    max_rev = max(max(with_rev), max(without_rev)) if with_rev and without_rev else 1
    for bar in bars1_rev:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + max_rev * 0.03,
                f'${height:,.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    for bar in bars2_rev:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + max_rev * 0.03,
                f'${height:,.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax2.set_ylabel('Revenue ($)', fontsize=11, fontweight='bold')
    ax2.set_title('Revenue Comparison', fontsize=12, fontweight='bold', pad=12)
    ax2.set_xticks(x_rev)
    ax2.set_xticklabels(revenue_categories, fontsize=10)
    ax2.legend(fontsize=9, loc='upper right')
    ax2.grid(axis='y', alpha=0.3, linestyle='--')
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    ax2.tick_params(labelsize=10)
    
    # ===== ICP BREAKDOWN COMPARISON =====
    ax3 = fig.add_subplot(gs[2, 0])
    icp_categories = ['ICP Operador', 'ICP PYME']
    with_icp = [with_icp_operador, with_icp_pyme]
    without_icp = [without_icp_operador, without_icp_pyme]
    x_icp = range(len(icp_categories))
    
    bars1_icp = ax3.bar([i - width/2 for i in x_icp], with_icp, width, label='WITH Accountant', color='#4A90E2', alpha=0.8)
    bars2_icp = ax3.bar([i + width/2 for i in x_icp], without_icp, width, label='WITHOUT Accountant', color='#E74C3C', alpha=0.8)
    
    max_icp = max(max(with_icp), max(without_icp)) if with_icp and without_icp else 1
    for bar in bars1_icp:
        height = bar.get_height()
        if height > 0:
            ax3.text(bar.get_x() + bar.get_width()/2., height + max_icp * 0.03,
                    f'{int(height)}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars2_icp:
        height = bar.get_height()
        if height > 0:
            ax3.text(bar.get_x() + bar.get_width()/2., height + max_icp * 0.03,
                    f'{int(height)}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax3.set_ylabel('Count', fontsize=11, fontweight='bold')
    ax3.set_title('ICP Classification Comparison', fontsize=12, fontweight='bold', pad=12)
    ax3.set_xticks(x_icp)
    ax3.set_xticklabels(icp_categories, fontsize=10)
    ax3.legend(fontsize=9, loc='upper right')
    ax3.grid(axis='y', alpha=0.3, linestyle='--')
    ax3.tick_params(labelsize=10)
    
    # ===== FUNNEL STAGES COMPARISON =====
    ax4 = fig.add_subplot(gs[2, 1])
    stage_categories = ['Deal Created', 'Deal Closed Won']
    with_stages = [with_deal_created, with_deal_won]
    without_stages = [without_deal_created, without_deal_won]
    x_stages = range(len(stage_categories))
    
    bars1_stages = ax4.bar([i - width/2 for i in x_stages], with_stages, width, label='WITH Accountant', color='#4A90E2', alpha=0.8)
    bars2_stages = ax4.bar([i + width/2 for i in x_stages], without_stages, width, label='WITHOUT Accountant', color='#E74C3C', alpha=0.8)
    
    max_stages = max(max(with_stages), max(without_stages)) if with_stages and without_stages else 1
    for bar in bars1_stages:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height + max_stages * 0.03,
                f'{int(height)}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars2_stages:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height + max_stages * 0.03,
                f'{int(height)}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax4.set_ylabel('Count', fontsize=11, fontweight='bold')
    ax4.set_title('Funnel Stages Comparison', fontsize=12, fontweight='bold', pad=12)
    ax4.set_xticks(x_stages)
    ax4.set_xticklabels(stage_categories, fontsize=10)
    ax4.legend(fontsize=9, loc='upper right')
    ax4.grid(axis='y', alpha=0.3, linestyle='--')
    ax4.tick_params(labelsize=10)
    
    # Shorten period for main title if too long
    period_title = period if len(period) < 40 else period[:37] + "..."
    plt.suptitle(f'SMB Funnel Comparison: WITH vs WITHOUT Accountant Involvement\n{period_title}', 
                 fontsize=15, fontweight='bold', y=0.985, ha='center')
    
    # Adjust layout - already set in GridSpec, but ensure proper spacing
    # GridSpec parameters handle the layout, no need for additional subplots_adjust
    
    # Save visualization
    if output_dir is None:
        output_dir = os.path.dirname(csv_file_path)
    
    os.makedirs(output_dir, exist_ok=True)
    
    csv_basename = os.path.basename(csv_file_path)
    viz_filename = csv_basename.replace('.csv', '_visualization.png')
    viz_path = os.path.join(output_dir, viz_filename)
    
    plt.savefig(viz_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"📊 Comparison visualization saved to: {viz_path}")
    
    return viz_path

def create_single_funnel_visualization(df, csv_file_path, output_dir=None):
    """Create visualization for single funnel (legacy support)"""
    # This would be similar to the original single funnel visualization
    # For now, just return the path
    if output_dir is None:
        output_dir = os.path.dirname(csv_file_path)
    os.makedirs(output_dir, exist_ok=True)
    csv_basename = os.path.basename(csv_file_path)
    viz_filename = csv_basename.replace('.csv', '_visualization.png')
    viz_path = os.path.join(output_dir, viz_filename)
    return viz_path

def main():
    parser = argparse.ArgumentParser(description='Analyze SMB Funnel: WITH vs WITHOUT Accountant Involvement')
    parser.add_argument('--month', type=str, help='Month in YYYY-MM format (e.g., 2025-12)')
    parser.add_argument('--months', nargs='+', type=str, help='Multiple months in format YYYY-MM (e.g., --months 2025-11 2025-12)')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    parser.add_argument('--csv', type=str, help='Path to existing CSV file to generate visualization from (e.g., tools/outputs/smb_accountant_funnel_comparison_20251201_20260101.csv)')
    
    args = parser.parse_args()
    
    # Handle CSV-only visualization
    if args.csv:
        csv_path = args.csv
        if not os.path.exists(csv_path):
            # Try relative to outputs directory
            if not csv_path.startswith('tools/outputs/'):
                csv_path = f"tools/outputs/{csv_path}"
            if not os.path.exists(csv_path):
                print(f"❌ Error: CSV file not found: {csv_path}")
                print(f"   Please provide the full path or filename from tools/outputs/")
                return
        
        print(f"📊 Generating visualization from CSV: {csv_path}")
        print()
        try:
            viz_path = create_funnel_visualization(csv_path)
            print(f"✅ Visualization generated successfully: {viz_path}")
        except Exception as e:
            print(f"❌ Error generating visualization: {str(e)}")
            import traceback
            traceback.print_exc()
        return
    
    # Handle multiple months
    if args.months:
        print("="*80)
        print("MULTI-MONTH ANALYSIS")
        print("="*80)
        print()
        print(f"Analyzing {len(args.months)} month(s): {', '.join(args.months)}")
        print()
        
        all_results = []
        for month_str in args.months:
            year, month = month_str.split('-')
            start_date = f"{year}-{month}-01"
            if month == '12':
                end_date = f"{int(year)+1}-01-01"
            else:
                end_date = f"{year}-{int(month)+1:02d}-01"
            
            print("="*80)
            print(f"MONTH: {month_str}")
            print("="*80)
            print()
            
            result = analyze_funnel(start_date, end_date)
            if result:
                result['month'] = month_str
                all_results.append(result)
                
                # Generate visualization for each month
                if result.get('csv_file'):
                    try:
                        viz_path = create_funnel_visualization(result['csv_file'])
                        print(f"✅ Visualization generated: {viz_path}")
                        print()
                    except Exception as e:
                        print(f"⚠️  Warning: Could not generate visualization: {str(e)}")
                        print()
            print()
        
        # Print comparative summary
        if all_results:
            print("="*80)
            print("COMPARATIVE SUMMARY")
            print("="*80)
            print()
            print("| Month | Deal Created | Deal Closed Won | Deal→Won | ICP Operador | ICP PYME | Total Revenue |")
            print("|-------|-------------|-----------------|----------|--------------|----------|---------------|")
            for result in all_results:
                month = result.get('month', 'N/A')
                deal_created = result.get('deal_created_count', 0)
                closed_won = result.get('closed_won_count', 0)
                deal_to_won = result.get('deal_to_won_rate', 0)
                icp_operador = result.get('icp_operador_count', 0)
                icp_pyme = result.get('icp_pyme_count', 0)
                total_revenue = result.get('total_revenue', 0)
                print(f"| {month} | {deal_created} | {closed_won} | {deal_to_won:.1f}% | {icp_operador} | {icp_pyme} | ${total_revenue:,.2f} |")
            print()
            
            # Save comparative CSV
            output_dir = "tools/outputs"
            os.makedirs(output_dir, exist_ok=True)
            
            df_data = {
                'Month': [r.get('month', 'N/A') for r in all_results],
                'Deal_Created': [r.get('deal_created_count', 0) for r in all_results],
                'Deal_Closed_Won': [r.get('closed_won_count', 0) for r in all_results],
                'Deal_to_Won_Rate_%': [round(r.get('deal_to_won_rate', 0), 2) for r in all_results],
                'ICP_Operador_Count': [r.get('icp_operador_count', 0) for r in all_results],
                'ICP_Operador_Revenue': [round(r.get('icp_operador_revenue', 0), 2) for r in all_results],
                'ICP_PYME_Count': [r.get('icp_pyme_count', 0) for r in all_results],
                'ICP_PYME_Revenue': [round(r.get('icp_pyme_revenue', 0), 2) for r in all_results],
                'Total_Revenue': [round(r.get('total_revenue', 0), 2) for r in all_results],
            }
            
            df = pd.DataFrame(df_data)
            
            # Generate filename with month range
            months_str = "_".join([m.replace('-', '') for m in args.months])
            output_file = f"{output_dir}/smb_accountant_involved_funnel_{months_str}.csv"
            
            df.to_csv(output_file, index=False)
            print(f"📄 Comparative results saved to CSV: {output_file}")
            print()
        return
    
    # Single month or date range
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
        # Default to current month
        today = datetime.now()
        start_date = f"{today.year}-{today.month:02d}-01"
        if today.month == 12:
            end_date = f"{today.year+1}-01-01"
        else:
            end_date = f"{today.year}-{today.month+1:02d}-01"
    
    result = analyze_funnel(start_date, end_date)
    
    # Generate visualization
    if result and result.get('csv_file'):
        try:
            viz_path = create_funnel_visualization(result['csv_file'])
            print(f"✅ Visualization generated: {viz_path}")
            print()
        except Exception as e:
            print(f"⚠️  Warning: Could not generate visualization: {str(e)}")
            print()

if __name__ == '__main__':
    main()

