#!/usr/bin/env python3
"""
ACCOUNTANT MQL FUNNEL ANALYSIS
==============================

Analyzes the funnel from MQL (Marketing Qualified Lead) to Closed Won deals,
specifically for contacts identified as accountants by their rol_wizard field.

FILTERING CRITERIA:
- MQL: Contacts CREATED in the period with rol_wizard indicating accountant role
- SQL: Contacts with hs_v2_date_entered_opportunity in the period
- Deal Created: Deals CREATED in the period (associated with MQL contacts)
- Deal Closed: Deals CLOSED WON in the period (both createdate and closedate in period)
- ICP Classification: Based on PRIMARY company type (same logic as ICP Operador billing)

DEFINITION OF "ACCOUNTANT MQL":
- Contact created in the period
- rol_wizard field indicates accountant role (e.g., "Contador", "Estudio Contable", etc.)
- Excludes 'Usuario Invitado' contacts

FUNNEL STAGES:
1. MQL Contador: Contacts created in period with accountant rol_wizard
2. SQL: MQLs that entered opportunity stage (hs_v2_date_entered_opportunity) in period WITH validated deal association
   - Validation: Contact must have a deal created between contact creation and SQL date (within period)
3. Deal Created: Deals created in period (associated with MQL contacts)
4. Deal Closed Won: Deals closed won in period (createdate AND closedate in period)
5. ICP Operador vs ICP PYME: Classification based on PRIMARY company type

Usage:
  python analyze_accountant_mql_funnel.py --month 2025-12
  python analyze_accountant_mql_funnel.py --months 2025-11 2025-12
  python analyze_accountant_mql_funnel.py --start-date 2025-12-01 --end-date 2026-01-01
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

# Accountant role values in rol_wizard (case-insensitive matching)
ACCOUNTANT_ROLES = ['contador', 'estudio contable', 'contador público', 'asesor contable']

def is_accountant_role(rol_wizard):
    """
    Check if rol_wizard indicates accountant role
    IMPORTANT: Returns False for null/empty values (HubSpot excludes nulls in 'contains' filter)
    Uses HubSpot's "contains conta" logic to match their filter behavior
    """
    # If rol_wizard is null/empty, exclude from funnel (HubSpot behavior)
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    rol_lower = str(rol_wizard).lower().strip()
    # HubSpot uses "contains conta" filter - match any role containing "conta"
    return 'conta' in rol_lower

def fetch_accountant_mqls(start_date, end_date):
    """
    Fetch contacts created in period with accountant rol_wizard (excluding 'Usuario Invitado')
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search"
    all_contacts = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "lead_source", "operator": "NEQ", "value": "Usuario Invitado"}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["email", "createdate", "firstname", "lastname", "lead_source", "rol_wizard", 
                          "hs_v2_date_entered_opportunity"],
            "limit": 100
        }
        if after:
            payload["after"] = after
            
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_contacts.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    # Filter for accountant roles
    accountant_mqls = []
    for contact in all_contacts:
        props = contact.get('properties', {})
        rol_wizard = props.get('rol_wizard', '')
        if is_accountant_role(rol_wizard):
            accountant_mqls.append(contact)
    
    return accountant_mqls

def get_contact_deals(contact_id, start_date, end_date, include_all_deals=False):
    """
    Get deals associated with a contact.
    If include_all_deals=False: Only returns deals CREATED in the period
    If include_all_deals=True: Returns ALL deals (including outside period, archived, etc.)
    Returns list of deal objects with properties
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
            
            # Fetch deals in batches
            all_deals = []
            for i in range(0, len(deal_ids), 100):
                batch_ids = deal_ids[i:i+100]
                url_search = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/batch/read"
                payload = {
                    "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "primary_company_type", "hs_archived"],
                    "inputs": [{"id": deal_id} for deal_id in batch_ids]
                }
                response = requests.post(url_search, headers=HEADERS, json=payload, timeout=30)
                if response.status_code == 200:
                    deals = response.json().get('results', [])
                    all_deals.extend(deals)
            
            if include_all_deals:
                return all_deals
            
            # Filter by createdate in period
            deals_in_period = []
            start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
            end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
            for deal in all_deals:
                props = deal.get('properties', {})
                deal_createdate = props.get('createdate', '')
                if deal_createdate:
                    deal_created_dt = datetime.fromisoformat(deal_createdate.replace('Z', '+00:00'))
                    if start_dt <= deal_created_dt < end_dt:
                        deals_in_period.append(deal)
            
            return deals_in_period
    except:
        pass
    return []

def get_contact_companies(contact_id):
    """Get all companies associated with a contact"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/companies"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            company_ids = [assoc.get('toObjectId') for assoc in associations]
            return company_ids
    except:
        pass
    return []

def get_company_deals(company_id, start_date, end_date):
    """Get all deals associated with a company (to check if contact's company has deals)
    Note: start_date and end_date are used for filtering, but we return all deals for analysis
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/companies/{company_id}/associations/deals"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            deal_ids = [assoc.get('toObjectId') for assoc in associations]
            
            if not deal_ids:
                return []
            
            # Fetch deal details
            all_deals = []
            for i in range(0, len(deal_ids), 100):
                batch_ids = deal_ids[i:i+100]
                url_search = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/batch/read"
                payload = {
                    "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "hs_archived", "id_empresa"],
                    "inputs": [{"id": deal_id} for deal_id in batch_ids]
                }
                response = requests.post(url_search, headers=HEADERS, json=payload, timeout=30)
                if response.status_code == 200:
                    deals = response.json().get('results', [])
                    all_deals.extend(deals)
            
            # Filter by createdate if dates provided
            if start_date and end_date:
                start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
                end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
                filtered_deals = []
                for deal in all_deals:
                    deal_props = deal.get('properties', {})
                    deal_createdate_str = deal_props.get('createdate', '')
                    if deal_createdate_str:
                        deal_createdate_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                        if start_dt <= deal_createdate_dt < end_dt:
                            filtered_deals.append(deal)
                return filtered_deals
            
            return all_deals
    except:
        pass
    return []

def get_company_contacts(company_id):
    """Get all contacts associated with a company"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/companies/{company_id}/associations/contacts"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            contact_ids = [assoc.get('toObjectId') for assoc in associations]
            return contact_ids
    except:
        pass
    return []

def get_edge_case_description(edge_case_type):
    """Get human-readable description for edge case types"""
    descriptions = {
        "NO_DEALS_ASSOCIATED": "Contact has SQL date but no deals are associated with the contact. This could indicate: (1) Deal was never created (sales process ongoing), (2) Deal exists on company but not associated with contact, (3) Deal was deleted or de-associated.",
        "DEAL_BEFORE_EARLIEST_CONTACT": "Deal was created before ANY contact associated with it. This suggests the deal was created manually or via integration without any contact context. May indicate data quality issue or self-serve product addition before user registration.",
        "SELF_SERVE_DEAL_PATTERN": "Deal was created before THIS contact, but after the earliest contact on the deal. This is the self-serve pattern: user adds product in Colppy (deal created), then contact is created/associated later. The earliest contact should be used for validation.",
        "DEAL_AFTER_SQL_DATE": "Deal was created after the contact entered SQL stage. This is unusual - typically deals should be created before or at SQL conversion. May indicate deal was created retroactively or there's a timing issue.",
        "DEAL_OUTSIDE_PERIOD": "Deal was created outside the analysis period. The contact has SQL date in period, but the associated deal was created in a different period. This is expected for contacts that converted in one period but deals created in another.",
        "DEAL_NO_CREATEDATE": "Deal exists but has no createdate property. This is a data quality issue - all deals should have a createdate.",
        "UNKNOWN": "Unknown edge case - needs investigation."
    }
    return descriptions.get(edge_case_type, "No description available")

def find_colppy_user_for_deal(deal_id, deal_createdate_str):
    """
    Try to identify the Colppy user who added the product by:
    1. Getting the deal's primary company
    2. Finding contacts associated with that company
    3. Looking for contacts created around the same time as the deal (self-serve users)
    Returns list of potential user contacts
    """
    # Get primary company for the deal
    company_id = get_primary_company_id(deal_id)
    if not company_id:
        return []
    
    # Get all contacts for the company
    contact_ids = get_company_contacts(company_id)
    if not contact_ids:
        return []
    
    # Fetch contact details to check createdate
    potential_users = []
    deal_createdate = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
    
    # Fetch contacts in batches
    for i in range(0, len(contact_ids), 100):
        batch_ids = contact_ids[i:i+100]
        url_search = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/batch/read"
        payload = {
            "properties": ["email", "firstname", "lastname", "createdate", "rol_wizard"],
            "inputs": [{"id": contact_id} for contact_id in batch_ids]
        }
        try:
            response = requests.post(url_search, headers=HEADERS, json=payload, timeout=30)
            if response.status_code == 200:
                contacts = response.json().get('results', [])
                for contact in contacts:
                    props = contact.get('properties', {})
                    contact_createdate_str = props.get('createdate', '')
                    if contact_createdate_str:
                        contact_createdate = datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))
                        # Check if contact was created within 7 days before or after deal (self-serve window)
                        time_diff = abs((deal_createdate - contact_createdate).total_seconds())
                        if time_diff <= 7 * 24 * 3600:  # 7 days in seconds
                            potential_users.append({
                                'contact_id': contact.get('id'),
                                'email': props.get('email', ''),
                                'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                                'createdate': contact_createdate_str,
                                'rol_wizard': props.get('rol_wizard', ''),
                                'time_diff_hours': time_diff / 3600
                            })
        except:
            pass
    
    # Sort by time difference (closest to deal creation first)
    potential_users.sort(key=lambda x: x['time_diff_hours'])
    return potential_users

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
                        "properties": ["email", "firstname", "lastname", "createdate", "hs_v2_date_entered_opportunity", "rol_wizard"],
                        "inputs": [{"id": contact_id} for contact_id in batch_ids]
                    }
                    response = requests.post(url_batch, headers=HEADERS, json=payload, timeout=30)
                    if response.status_code == 200:
                        contacts = response.json().get('results', [])
                        for contact in contacts:
                            props = contact.get('properties', {})
                            contacts_data.append({
                                'contact_id': contact.get('id'),
                                'email': props.get('email', ''),
                                'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                                'createdate': props.get('createdate', ''),
                                'sql_date': props.get('hs_v2_date_entered_opportunity', ''),
                                'rol_wizard': props.get('rol_wizard', '')
                            })
            return contacts_data
    except:
        pass
    return []

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

def analyze_funnel(start_date, end_date):
    """
    Analyze the funnel from MQL Contador to Closed Won deals
    """
    print(f"\n{'='*80}")
    print(f"ACCOUNTANT MQL FUNNEL ANALYSIS")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    # STAGE 1: Fetch MQL Contadores (contacts created in period with accountant rol_wizard)
    print("📊 Stage 1: Fetching MQL Contadores...")
    mql_contacts = fetch_accountant_mqls(start_date, end_date)
    print(f"   Found {len(mql_contacts)} MQL Contadores\n")
    
    # STAGE 2: Identify SQLs (MQLs that entered opportunity in period WITH validated deal association)
    print("📊 Stage 2: Identifying SQLs (with deal validation)...")
    sql_contacts = []
    sql_without_valid_deal = []  # Track contacts with SQL date but no valid deal
    
    for contact in mql_contacts:
        props = contact.get('properties', {})
        contact_createdate_str = props.get('createdate', '')
        sql_date_str = props.get('hs_v2_date_entered_opportunity', '')
        
        if sql_date_str and contact_createdate_str:
            try:
                contact_createdate = datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))
                sql_date = datetime.fromisoformat(sql_date_str.replace('Z', '+00:00'))
                
                # SQL conversion must be in period
                if start_dt <= sql_date < end_dt:
                    # Validate: Contact must have a deal created between contact creation and SQL date (within period)
                    contact_id = contact.get('id')
                    deals = get_contact_deals(contact_id, start_date, end_date)
                    
                    # Check if any deal was created between contact creation and SQL date (within period)
                    # IMPORTANT: For deals with multiple contacts, use the EARLIEST contact's createdate
                    has_valid_deal = False
                    deal_validation_reasons = []
                    edge_case_type = None
                    
                    if not deals:
                        deal_validation_reasons.append("No deals associated with contact")
                        edge_case_type = "NO_DEALS_ASSOCIATED"
                    else:
                        for deal in deals:
                            deal_id = deal.get('id')
                            deal_props = deal.get('properties', {})
                            deal_createdate_str = deal_props.get('createdate', '')
                            if deal_createdate_str:
                                deal_createdate = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                                
                                # Get ALL contacts for this deal to find the earliest one
                                deal_contacts = get_deal_contacts(deal_id)
                                earliest_contact_createdate = contact_createdate  # Default to current contact
                                
                                if deal_contacts:
                                    # Find earliest contact createdate
                                    earliest_contact = min(
                                        deal_contacts,
                                        key=lambda x: datetime.fromisoformat(x.get('createdate', contact_createdate_str).replace('Z', '+00:00')) if x.get('createdate') else contact_createdate
                                    )
                                    earliest_contact_createdate_str = earliest_contact.get('createdate', contact_createdate_str)
                                    if earliest_contact_createdate_str:
                                        earliest_contact_createdate = datetime.fromisoformat(earliest_contact_createdate_str.replace('Z', '+00:00'))
                                
                                # Check each validation criterion
                                reason_parts = []
                                if deal_createdate < earliest_contact_createdate:
                                    reason_parts.append(f"Deal created BEFORE earliest contact ({deal_createdate.date()} < {earliest_contact_createdate.date()})")
                                    edge_case_type = "DEAL_BEFORE_EARLIEST_CONTACT"
                                elif deal_createdate < contact_createdate:
                                    # Deal created before THIS contact, but after earliest contact (self-serve pattern)
                                    reason_parts.append(f"Deal created BEFORE this contact ({deal_createdate.date()} < {contact_createdate.date()}) but after earliest contact")
                                    edge_case_type = "SELF_SERVE_DEAL_PATTERN"
                                if deal_createdate > sql_date:
                                    reason_parts.append(f"Deal created AFTER SQL date ({deal_createdate.date()} > {sql_date.date()})")
                                    if not edge_case_type:
                                        edge_case_type = "DEAL_AFTER_SQL_DATE"
                                if deal_createdate < start_dt or deal_createdate >= end_dt:
                                    reason_parts.append(f"Deal created OUTSIDE period ({deal_createdate.date()} not in [{start_date}, {end_date}])")
                                    if not edge_case_type:
                                        edge_case_type = "DEAL_OUTSIDE_PERIOD"
                                
                                # Deal must be created between EARLIEST contact creation and SQL date, AND within the period
                                if (earliest_contact_createdate <= deal_createdate <= sql_date and 
                                    start_dt <= deal_createdate < end_dt):
                                    has_valid_deal = True
                                    break
                                else:
                                    if reason_parts:
                                        deal_validation_reasons.append(f"Deal {deal_id}: {', '.join(reason_parts)}")
                            else:
                                deal_validation_reasons.append(f"Deal {deal_id}: No createdate")
                                if not edge_case_type:
                                    edge_case_type = "DEAL_NO_CREATEDATE"
                    
                    if has_valid_deal:
                        sql_contacts.append(contact)
                    else:
                        # Contact has SQL date but no valid deal
                        sql_without_valid_deal.append({
                            'contact_id': contact_id,
                            'email': props.get('email', ''),
                            'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                            'createdate': contact_createdate_str,
                            'sql_date': sql_date_str,
                            'num_deals': len(deals),
                            'reasons': deal_validation_reasons,
                            'edge_case_type': edge_case_type
                        })
            except Exception as e:
                pass
    
    print(f"   Found {len(sql_contacts)} SQLs ({len(sql_contacts)/len(mql_contacts)*100:.1f}% of MQLs)")
    print(f"   Found {len(sql_without_valid_deal)} contacts with SQL date but NO valid deal\n")
    
    # Analyze reasons for SQL without valid deal
    if sql_without_valid_deal:
        print("="*80)
        print("ANALYSIS: Contacts with SQL Date but NO Valid Deal")
        print("="*80)
        print()
        
        # Track edge cases by type
        edge_cases_summary = {}
        for contact_info in sql_without_valid_deal:
            edge_case = contact_info.get('edge_case_type', 'UNKNOWN')
            if edge_case not in edge_cases_summary:
                edge_cases_summary[edge_case] = []
            edge_cases_summary[edge_case].append(contact_info)
        
        print("**EDGE CASES SUMMARY:**")
        print()
        for edge_case_type, contacts in edge_cases_summary.items():
            print(f"  **{edge_case_type}**: {len(contacts)} contact(s)")
            print(f"    Description: {get_edge_case_description(edge_case_type)}")
            print(f"    Examples:")
            for contact in contacts[:3]:  # Show first 3 examples
                print(f"      - {contact['email']} (SQL: {contact['sql_date'][:10] if contact['sql_date'] else 'N/A'})")
            if len(contacts) > 3:
                print(f"      ... and {len(contacts) - 3} more")
            print()
        
        print("-" * 80)
        print()
        
        # Count by reason
        no_deals_count = sum(1 for c in sql_without_valid_deal if c['num_deals'] == 0)
        has_deals_but_invalid_count = sum(1 for c in sql_without_valid_deal if c['num_deals'] > 0)
        
        print(f"**Summary:**")
        print(f"- Contacts with SQL date but NO deals: {no_deals_count}")
        print(f"- Contacts with SQL date but INVALID deals: {has_deals_but_invalid_count}")
        print()
        
        # Deep investigation for contacts with NO deals
        print("="*80)
        print("DEEP INVESTIGATION: Contacts with SQL Date but NO Deals")
        print("="*80)
        print()
        
        contacts_no_deals = [c for c in sql_without_valid_deal if c['num_deals'] == 0]
        
        for contact_info in contacts_no_deals:
            contact_id = contact_info['contact_id']
            email = contact_info['email']
            contact_createdate = contact_info['createdate']
            sql_date = contact_info['sql_date']
            
            print(f"**Contact: {email}**")
            print(f"  - Contact Created: {contact_createdate[:10] if contact_createdate else 'N/A'}")
            print(f"  - SQL Date: {sql_date[:10] if sql_date else 'N/A'}")
            print()
            
            # 1. Check ALL deals (including outside period and archived)
            print(f"  **1. Checking ALL deals associated (including outside period, archived, etc.):**")
            all_deals = get_contact_deals(contact_id, start_date, end_date, include_all_deals=True)
            
            if all_deals:
                print(f"    ✅ Found {len(all_deals)} deal(s) associated with contact:")
                for deal in all_deals:
                    deal_id = deal.get('id')
                    deal_props = deal.get('properties', {})
                    deal_name = deal_props.get('dealname', 'N/A')
                    deal_createdate_str = deal_props.get('createdate', '')
                    deal_closedate_str = deal_props.get('closedate', '')
                    deal_stage = deal_props.get('dealstage', 'N/A')
                    deal_archived = deal_props.get('hs_archived', 'false')
                    
                    print(f"    - Deal: {deal_name} (ID: {deal_id})")
                    print(f"      Created: {deal_createdate_str[:10] if deal_createdate_str else 'N/A'}")
                    print(f"      Closed: {deal_closedate_str[:10] if deal_closedate_str else 'N/A'}")
                    print(f"      Stage: {deal_stage}")
                    print(f"      Archived: {deal_archived}")
                    
                    if deal_createdate_str:
                        deal_createdate_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                        contact_createdate_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                        sql_date_dt = datetime.fromisoformat(sql_date.replace('Z', '+00:00'))
                        
                        # Check why it's not valid
                        reasons = []
                        if deal_createdate_dt < contact_createdate_dt:
                            reasons.append(f"Created BEFORE contact ({deal_createdate_dt.date()} < {contact_createdate_dt.date()})")
                        if deal_createdate_dt > sql_date_dt:
                            reasons.append(f"Created AFTER SQL date ({deal_createdate_dt.date()} > {sql_date_dt.date()})")
                        if deal_createdate_dt < start_dt or deal_createdate_dt >= end_dt:
                            reasons.append(f"Created OUTSIDE December period")
                        if deal_archived == 'true':
                            reasons.append("Deal is ARCHIVED")
                        
                        if reasons:
                            print(f"      ⚠️  Not valid because: {', '.join(reasons)}")
                        else:
                            print(f"      ✅ Should be valid!")
            else:
                print(f"    ❌ No deals found associated with contact")
            
            print()
            
            # 2. Check if contact is associated with companies that have deals
            print(f"  **2. Checking if contact's companies have deals:**")
            company_ids = get_contact_companies(contact_id)
            
            if company_ids:
                print(f"    Found {len(company_ids)} company/companies associated:")
                for company_id in company_ids:
                    # Get ALL deals for company (not just in period)
                    company_deals_all = get_company_deals(company_id, "2020-01-01", "2026-12-31")  # Wide range to get all
                    company_deals = get_company_deals(company_id, start_date, end_date)
                    
                    if company_deals_all:
                        print(f"    - Company ID {company_id}: {len(company_deals_all)} total deal(s), {len(company_deals)} in December")
                        
                        # Check if any deal in December matches contact/SQL timing
                        contact_createdate_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                        sql_date_dt = datetime.fromisoformat(sql_date.replace('Z', '+00:00'))
                        
                        for deal in company_deals_all:
                            deal_id = deal.get('id')
                            deal_props = deal.get('properties', {})
                            deal_name = deal_props.get('dealname', 'N/A')
                            deal_createdate_str = deal_props.get('createdate', '')
                            deal_closedate_str = deal_props.get('closedate', '')
                            deal_stage = deal_props.get('dealstage', 'N/A')
                            deal_archived = deal_props.get('hs_archived', 'false')
                            id_empresa = deal_props.get('id_empresa', '')
                            
                            # Check if this deal is associated with the contact
                            deal_contacts = get_deal_contacts(deal_id)
                            is_associated = any(dc.get('contact_id') == contact_id for dc in deal_contacts)
                            
                            print(f"      • {deal_name} (ID: {deal_id})")
                            print(f"        Created: {deal_createdate_str[:10] if deal_createdate_str else 'N/A'}")
                            print(f"        Closed: {deal_closedate_str[:10] if deal_closedate_str else 'N/A'}")
                            print(f"        Stage: {deal_stage}, Archived: {deal_archived}")
                            print(f"        ID Empresa (Colppy): {id_empresa if id_empresa else 'N/A'}")
                            print(f"        Associated with this contact: {'✅ YES' if is_associated else '❌ NO'}")
                            
                            if deal_createdate_str:
                                deal_createdate_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                                
                                # Check if this deal would validate SQL if associated
                                if (contact_createdate_dt <= deal_createdate_dt <= sql_date_dt and 
                                    start_dt <= deal_createdate_dt < end_dt):
                                    print(f"        ✅ This deal WOULD validate SQL if associated with contact!")
                                elif deal_createdate_dt < contact_createdate_dt:
                                    print(f"        ⚠️  Deal created BEFORE contact ({deal_createdate_dt.date()} < {contact_createdate_dt.date()})")
                                    print(f"        🔍 This might be a SELF-SERVE deal (product added in Colppy before contact association)")
                                    
                                    # Try to find the Colppy user who added the product
                                    print(f"        **Attempting to identify Colppy user who added product:**")
                                    potential_users = find_colppy_user_for_deal(deal_id, deal_createdate_str)
                                    
                                    if potential_users:
                                        print(f"        Found {len(potential_users)} potential user(s) (contacts created within 7 days of deal):")
                                        for user in potential_users[:3]:  # Show top 3
                                            print(f"          - {user['email']} ({user['name']})")
                                            print(f"            Created: {user['createdate'][:10]}, Time diff: {user['time_diff_hours']:.1f} hours")
                                            print(f"            Rol Wizard: {user['rol_wizard']}")
                                            if user['contact_id'] == contact_id:
                                                print(f"            ✅ THIS IS THE CURRENT CONTACT!")
                                    else:
                                        print(f"        ❌ No contacts found on company created around deal time")
                                    
                                elif deal_createdate_dt > sql_date_dt:
                                    print(f"        ⚠️  Deal created AFTER SQL date ({deal_createdate_dt.date()} > {sql_date_dt.date()})")
                                elif deal_createdate_dt < start_dt or deal_createdate_dt >= end_dt:
                                    print(f"        ⚠️  Deal created OUTSIDE December period")
                    else:
                        print(f"    - Company ID {company_id}: No deals")
            else:
                print(f"    ❌ Contact not associated with any companies")
            
            print()
            print("-" * 80)
            print()
        
        # Show details and analyze deals created before contacts
        print("**Details:**")
        print("| Contact Email | Created Date | SQL Date | # Deals | Reason |")
        print("|---------------|--------------|----------|---------|--------|")
        for contact_info in sql_without_valid_deal[:20]:  # Show first 20
            email = contact_info['email'] or 'N/A'
            created = contact_info['createdate'][:10] if contact_info['createdate'] else 'N/A'
            sql = contact_info['sql_date'][:10] if contact_info['sql_date'] else 'N/A'
            num_deals = contact_info['num_deals']
            reasons = '; '.join(contact_info['reasons'][:2]) if contact_info['reasons'] else 'Unknown'
            if len(reasons) > 80:
                reasons = reasons[:77] + '...'
            print(f"| {email[:30]:<30} | {created} | {sql} | {num_deals} | {reasons} |")
        
        if len(sql_without_valid_deal) > 20:
            print(f"\n... and {len(sql_without_valid_deal) - 20} more contacts")
        print()
        
        # Analyze deals created before contacts - check all contacts on those deals
        print("="*80)
        print("DETAILED ANALYSIS: Deals Created Before Contacts")
        print("="*80)
        print()
        print("Analyzing deals that were created before the contact to find earlier contacts...")
        print()
        
        deals_before_contacts = [c for c in sql_without_valid_deal if 'Deal created BEFORE contact' in '; '.join(c['reasons'])]
        
        for contact_info in deals_before_contacts:
            contact_id = contact_info['contact_id']
            email = contact_info['email']
            contact_createdate = contact_info['createdate']
            
            # Get deals for this contact
            deals = get_contact_deals(contact_id, start_date, end_date)
            
            print(f"**Contact: {email}**")
            print(f"  - Contact Created: {contact_createdate[:10] if contact_createdate else 'N/A'}")
            print(f"  - SQL Date: {contact_info['sql_date'][:10] if contact_info['sql_date'] else 'N/A'}")
            print()
            
            for deal in deals:
                deal_id = deal.get('id')
                deal_props = deal.get('properties', {})
                deal_name = deal_props.get('dealname', 'N/A')
                deal_createdate_str = deal_props.get('createdate', '')
                
                if deal_createdate_str:
                    deal_createdate = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
                    contact_createdate_dt = datetime.fromisoformat(contact_createdate.replace('Z', '+00:00'))
                    
                    if deal_createdate < contact_createdate_dt:
                        print(f"  **Deal: {deal_name} (ID: {deal_id})**")
                        print(f"    - Deal Created: {deal_createdate_str[:10]} {deal_createdate_str[11:19]}")
                        print(f"    - Contact Created: {contact_createdate[:10]} {contact_createdate[11:19]}")
                        print(f"    - Time Difference: Deal created {(contact_createdate_dt - deal_createdate).total_seconds() / 3600:.1f} hours BEFORE contact")
                        print()
                        
                        # Try to identify the Colppy user who added the product
                        print(f"    **🔍 Attempting to identify Colppy user who added product:**")
                        potential_users = find_colppy_user_for_deal(deal_id, deal_createdate_str)
                        
                        if potential_users:
                            print(f"    Found {len(potential_users)} potential user(s) (contacts created within 7 days of deal):")
                            for user in potential_users[:5]:  # Show top 5
                                marker = "← CURRENT CONTACT" if user['contact_id'] == contact_id else ""
                                print(f"      - {user['email']} ({user['name']}) {marker}")
                                print(f"        Created: {user['createdate'][:10]}, Time diff: {user['time_diff_hours']:.1f} hours")
                                print(f"        Rol Wizard: {user['rol_wizard'] if user['rol_wizard'] else 'N/A'}")
                        else:
                            print(f"    ❌ No contacts found on company created around deal time")
                        print()
                        
                        # Get all contacts associated with this deal
                        print(f"    **All Contacts Associated with This Deal:**")
                        deal_contacts = get_deal_contacts(deal_id)
                        
                        if deal_contacts:
                            # Sort by createdate
                            deal_contacts_sorted = sorted(deal_contacts, key=lambda x: x.get('createdate', ''))
                            
                            print(f"    | Contact Email | Created Date | SQL Date | Is Accountant (rol_wizard) |")
                            print(f"    |---------------|--------------|----------|----------------------------|")
                            for dc in deal_contacts_sorted:
                                dc_email = dc.get('email') or 'N/A'
                                dc_email_display = dc_email[:30] if dc_email and len(dc_email) > 0 else 'N/A'
                                dc_created = dc.get('createdate', '')[:10] if dc.get('createdate') else 'N/A'
                                dc_sql = dc.get('sql_date', '')[:10] if dc.get('sql_date') else 'N/A'
                                dc_rol = dc.get('rol_wizard') or ''
                                dc_rol_display = (dc_rol[:20] if dc_rol and len(dc_rol) > 0 else 'N/A')
                                is_accountant = is_accountant_role(dc_rol) if dc_rol else False
                                accountant_marker = "✓" if is_accountant else ""
                                
                                # Highlight if this is the contact we're analyzing
                                marker = "← CURRENT" if dc.get('contact_id') == contact_id else ""
                                print(f"    | {dc_email_display:<30} | {dc_created} | {dc_sql} | {dc_rol_display:<20} {accountant_marker} {marker} |")
                            
                            # Check if any earlier contact would validate SQL
                            earliest_contact = deal_contacts_sorted[0] if deal_contacts_sorted else None
                            if earliest_contact:
                                earliest_createdate = earliest_contact.get('createdate', '')
                                if earliest_createdate:
                                    earliest_createdate_dt = datetime.fromisoformat(earliest_createdate.replace('Z', '+00:00'))
                                    if earliest_createdate_dt <= deal_createdate:
                                        print(f"    ✅ **Earliest contact ({earliest_contact.get('email')}) was created BEFORE or AT deal creation**")
                                        print(f"       This contact would validate SQL if it has SQL date in period")
                                    else:
                                        print(f"    ⚠️  **Earliest contact was created AFTER deal**")
                        else:
                            print(f"    No contacts found associated with this deal")
                        print()
    
    # STAGE 3: Get deals created in period (associated with MQL contacts)
    # STRICT FUNNEL: MQL → Deal Created → Won
    # APPROACH: Deal-first (match HubSpot's perspective) - get all deals, then check for accountant MQL contacts
    print("📊 Stage 3: Fetching deals created in period (STRICT FUNNEL: MQL → Deal Created)...")
    
    # Create lookup for MQL contacts
    mql_contact_ids = {contact.get('id') for contact in mql_contacts}
    mql_contact_createdates = {}
    for contact in mql_contacts:
        contact_id = contact.get('id')
        contact_props = contact.get('properties', {})
        contact_createdate_str = contact_props.get('createdate', '')
        if contact_createdate_str:
            try:
                mql_contact_createdates[contact_id] = datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))
            except:
                pass
    
    # Fetch all deals created in period (deal-first approach)
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    all_deals_in_period = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"}
        ]
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "primary_company_type"],
            "associations": ["contacts"],
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
    
    print(f"   Found {len(all_deals_in_period)} total deals created in period")
    
    # Filter deals that have accountant MQL contact created before deal
    deals_created = []
    contact_to_deals = {}
    
    for deal in all_deals_in_period:
        deal_id = deal.get('id')
        deal_props = deal.get('properties', {})
        deal_createdate_str = deal_props.get('createdate', '')
        
        if not deal_createdate_str:
            continue
        
        try:
            deal_created_dt = datetime.fromisoformat(deal_createdate_str.replace('Z', '+00:00'))
        except:
            continue
        
        # Get associated contacts using v4 associations API (more reliable than v3 search associations)
        # This matches the approach used in SMB script
        deal_contacts = get_deal_contacts(deal_id)
        
        # Check if any contact is an accountant MQL created before the deal
        has_valid_mql_contact = False
        matching_contact_id = None
        
        for contact_data in deal_contacts:
            contact_id = contact_data.get('contact_id')
            contact_createdate_str = contact_data.get('createdate', '')
            
            if not contact_id or not contact_createdate_str:
                continue
            
            # Check if this contact is in our MQL list
            if contact_id in mql_contact_ids:
                try:
                    contact_created_dt = datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))
                    # Contact must be created before deal (HubSpot logic)
                    if contact_created_dt < deal_created_dt:
                        has_valid_mql_contact = True
                        matching_contact_id = contact_id
                        break
                except:
                    pass
        
        if has_valid_mql_contact:
            deals_created.append(deal)
            if matching_contact_id not in contact_to_deals:
                contact_to_deals[matching_contact_id] = []
            contact_to_deals[matching_contact_id].append(deal)
    
    print(f"   Found {len(deals_created)} deals with accountant MQL contacts (created before deal)\n")
    
    # STAGE 4: Filter for closed won deals (STRICT FUNNEL: Deal Created → Won)
    # Only deals that were created in period AND associated with MQL contacts can be closed won
    print("📊 Stage 4: Filtering closed won deals (STRICT FUNNEL: Deal Created → Won)...")
    closed_won_deals = []
    for deal in deals_created:
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
    
    # STAGE 5: Classify by ICP Operador vs ICP PYME
    print("📊 Stage 5: Classifying by ICP...")
    icp_operador_deals = []
    icp_pyme_deals = []
    
    for deal in closed_won_deals:
        if is_icp_operador(deal):
            icp_operador_deals.append(deal)
        else:
            icp_pyme_deals.append(deal)
    
    print(f"   ICP Operador: {len(icp_operador_deals)}")
    print(f"   ICP PYME: {len(icp_pyme_deals)}\n")
    
    # Calculate conversion rates
    # STRICT FUNNEL CALCULATION: MQL → Deal Created → Won
    # mql_to_won_rate: Only counts closed won deals that are:
    #   1. Associated with MQL contacts (from deals_created)
    #   2. Created in period (from deals_created)
    #   3. Closed won in period (filtered in STAGE 4)
    
    # Strict funnel rates (MQL → Deal Created → Won)
    mql_to_deal_rate = (len(deals_created) / len(mql_contacts) * 100) if mql_contacts else 0
    deal_to_won_rate = (len(closed_won_deals) / len(deals_created) * 100) if deals_created else 0
    mql_to_won_rate = (len(closed_won_deals) / len(mql_contacts) * 100) if mql_contacts else 0
    
    # Informational SQL rates (for reference only, not part of strict funnel)
    mql_to_sql_rate = (len(sql_contacts) / len(mql_contacts) * 100) if mql_contacts else 0
    sql_to_deal_rate = (len(deals_created) / len(sql_contacts) * 100) if sql_contacts else 0
    
    # Calculate revenue
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
    
    # Print results
    print("="*80)
    print("STRICT FUNNEL RESULTS")
    print("="*80)
    print()
    print("**STRICT FUNNEL PATH:** MQL → Deal Created → Won")
    print("(Only deals that went through the complete path are counted)")
    print()
    print("| Stage | Count | Conversion Rate |")
    print("|-------|-------|-----------------|")
    print(f"| MQL Contador | {len(mql_contacts)} | - |")
    print(f"| Deal Created | {len(deals_created)} | {mql_to_deal_rate:.1f}% |")
    print(f"| Deal Closed Won | {len(closed_won_deals)} | {deal_to_won_rate:.1f}% |")
    print(f"| **MQL to Won** | **{len(closed_won_deals)}** | **{mql_to_won_rate:.1f}%** |")
    print()
    print("="*80)
    print("INFORMATIONAL METRICS")
    print("="*80)
    print()
    print("**SQL (Sales Qualified Lead) - Informational Only**")
    print("(Not part of strict funnel calculation, shown for reference)")
    print()
    print("| Metric | Count | % of MQL |")
    print("|--------|-------|----------|")
    print(f"| SQL | {len(sql_contacts)} | {mql_to_sql_rate:.1f}% |")
    print(f"| SQL to Deal Created | {len(deals_created)} | {sql_to_deal_rate:.1f}% |")
    print()
    if sql_without_valid_deal:
        print(f"⚠️  Note: {len(sql_without_valid_deal)} contacts have SQL date but NO valid deal (excluded from SQL count)")
        print()
    
    print("="*80)
    print("ICP CLASSIFICATION (Closed Won Deals)")
    print("="*80)
    print()
    print("| ICP Type | Count | % of Closed Won | Revenue |")
    print("|----------|-------|-----------------|---------|")
    icp_operador_pct = (len(icp_operador_deals) / len(closed_won_deals) * 100) if closed_won_deals else 0
    icp_pyme_pct = (len(icp_pyme_deals) / len(closed_won_deals) * 100) if closed_won_deals else 0
    print(f"| ICP Operador | {len(icp_operador_deals)} | {icp_operador_pct:.1f}% | ${icp_operador_revenue:,.2f} |")
    print(f"| ICP PYME | {len(icp_pyme_deals)} | {icp_pyme_pct:.1f}% | ${icp_pyme_revenue:,.2f} |")
    print(f"| **Total** | **{len(closed_won_deals)}** | **100.0%** | **${total_revenue:,.2f}** |")
    print()
    
    print("**Note:** ICP Operador classification is based on PRIMARY company type:")
    print(f"  - {', '.join(ACCOUNTANT_COMPANY_TYPES)}")
    print()
    
    # Prepare results dictionary
    results = {
        'mql_count': len(mql_contacts),
        'sql_count': len(sql_contacts),
        'deal_created_count': len(deals_created),
        'closed_won_count': len(closed_won_deals),
        'icp_operador_count': len(icp_operador_deals),
        'icp_pyme_count': len(icp_pyme_deals),
        'mql_to_deal_rate': mql_to_deal_rate,
        'deal_to_won_rate': deal_to_won_rate,
        'mql_to_won_rate': mql_to_won_rate,
        # Informational SQL rates (for reference)
        'mql_to_sql_rate': mql_to_sql_rate,
        'sql_to_deal_rate': sql_to_deal_rate,
        'total_revenue': total_revenue,
        'icp_operador_revenue': icp_operador_revenue,
        'icp_pyme_revenue': icp_pyme_revenue,
        'start_date': start_date,
        'end_date': end_date,
        'edge_cases': {}
    }
    
    # Add edge cases summary to results
    if sql_without_valid_deal:
        edge_cases_summary = {}
        for contact_info in sql_without_valid_deal:
            edge_case = contact_info.get('edge_case_type', 'UNKNOWN')
            if edge_case not in edge_cases_summary:
                edge_cases_summary[edge_case] = 0
            edge_cases_summary[edge_case] += 1
        results['edge_cases'] = edge_cases_summary
    
    # Save to CSV
    output_dir = "tools/outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    # Create DataFrame with main metrics
    df_data = {
        'Period': [f"{start_date} to {end_date}"],
        'MQL_Contador': [len(mql_contacts)],
        'Deal_Created': [len(deals_created)],
        'Deal_Closed_Won': [len(closed_won_deals)],
        'MQL_to_Deal_Rate_%': [round(mql_to_deal_rate, 2)],
        'Deal_to_Won_Rate_%': [round(deal_to_won_rate, 2)],
        'MQL_to_Won_Rate_%': [round(mql_to_won_rate, 2)],
        # Informational SQL metrics (for reference)
        'SQL_Informational': [len(sql_contacts)],
        'MQL_to_SQL_Rate_%': [round(mql_to_sql_rate, 2)],
        'SQL_to_Deal_Rate_%': [round(sql_to_deal_rate, 2)],
        'ICP_Operador_Count': [len(icp_operador_deals)],
        'ICP_Operador_Revenue': [round(icp_operador_revenue, 2)],
        'ICP_PYME_Count': [len(icp_pyme_deals)],
        'ICP_PYME_Revenue': [round(icp_pyme_revenue, 2)],
        'Total_Revenue': [round(total_revenue, 2)],
        'Edge_Cases_Total': [len(sql_without_valid_deal)],
    }
    
    # Add edge case columns
    if sql_without_valid_deal:
        edge_cases_summary = {}
        for contact_info in sql_without_valid_deal:
            edge_case = contact_info.get('edge_case_type', 'UNKNOWN')
            if edge_case not in edge_cases_summary:
                edge_cases_summary[edge_case] = 0
            edge_cases_summary[edge_case] += 1
        
        for edge_case_type, count in edge_cases_summary.items():
            df_data[f'Edge_Case_{edge_case_type}'] = [count]
    
    df = pd.DataFrame(df_data)
    
    # Generate filename with date range
    start_date_clean = start_date.replace('-', '')
    end_date_clean = end_date.replace('-', '')
    output_file = f"{output_dir}/accountant_mql_funnel_{start_date_clean}_{end_date_clean}.csv"
    
    df.to_csv(output_file, index=False)
    print(f"📄 Results saved to CSV: {output_file}")
    print()
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Analyze Accountant MQL Funnel')
    parser.add_argument('--month', type=str, help='Month in YYYY-MM format (e.g., 2025-12)')
    parser.add_argument('--months', nargs='+', type=str, help='Multiple months in format YYYY-MM (e.g., --months 2025-11 2025-12)')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    
    args = parser.parse_args()
    
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
            print()
        
        # Print comparative summary
        if all_results:
            print("="*80)
            print("COMPARATIVE SUMMARY")
            print("="*80)
            print()
            print("**STRICT FUNNEL PATH:** MQL → Deal Created → Won")
            print()
            print("| Month | MQL Contador | Deal Created | Deal Closed Won | MQL→Deal | Deal→Won | MQL→Won | ICP Operador | ICP PYME |")
            print("|-------|--------------|-------------|-----------------|----------|---------|---------|--------------|----------|")
            for result in all_results:
                month = result.get('month', 'N/A')
                mql = result.get('mql_count', 0)
                deal_created = result.get('deal_created_count', 0)
                closed_won = result.get('closed_won_count', 0)
                mql_to_deal = result.get('mql_to_deal_rate', 0)
                deal_to_won = result.get('deal_to_won_rate', 0)
                mql_to_won = result.get('mql_to_won_rate', 0)
                icp_operador = result.get('icp_operador_count', 0)
                icp_pyme = result.get('icp_pyme_count', 0)
                print(f"| {month} | {mql} | {deal_created} | {closed_won} | {mql_to_deal:.1f}% | {deal_to_won:.1f}% | {mql_to_won:.1f}% | {icp_operador} | {icp_pyme} |")
            print()
            print("**INFORMATIONAL - SQL Metrics (for reference only):**")
            print("| Month | SQL | MQL→SQL | SQL→Deal |")
            print("|-------|-----|---------|----------|")
            for result in all_results:
                month = result.get('month', 'N/A')
                sql = result.get('sql_count', 0)
                mql_to_sql = result.get('mql_to_sql_rate', 0)
                sql_to_deal = result.get('sql_to_deal_rate', 0)
                print(f"| {month} | {sql} | {mql_to_sql:.1f}% | {sql_to_deal:.1f}% |")
            print()
            
            # Save comparative CSV
            output_dir = "tools/outputs"
            os.makedirs(output_dir, exist_ok=True)
            
            # Create DataFrame with all months
            df_data = {
                'Month': [r.get('month', 'N/A') for r in all_results],
                'MQL_Contador': [r.get('mql_count', 0) for r in all_results],
                'Deal_Created': [r.get('deal_created_count', 0) for r in all_results],
                'Deal_Closed_Won': [r.get('closed_won_count', 0) for r in all_results],
                'MQL_to_Deal_Rate_%': [round(r.get('mql_to_deal_rate', 0), 2) for r in all_results],
                'Deal_to_Won_Rate_%': [round(r.get('deal_to_won_rate', 0), 2) for r in all_results],
                'MQL_to_Won_Rate_%': [round(r.get('mql_to_won_rate', 0), 2) for r in all_results],
                # Informational SQL metrics
                'SQL_Informational': [r.get('sql_count', 0) for r in all_results],
                'MQL_to_SQL_Rate_%': [round(r.get('mql_to_sql_rate', 0), 2) for r in all_results],
                'SQL_to_Deal_Rate_%': [round(r.get('sql_to_deal_rate', 0), 2) for r in all_results],
                'ICP_Operador_Count': [r.get('icp_operador_count', 0) for r in all_results],
                'ICP_Operador_Revenue': [round(r.get('icp_operador_revenue', 0), 2) for r in all_results],
                'ICP_PYME_Count': [r.get('icp_pyme_count', 0) for r in all_results],
                'ICP_PYME_Revenue': [round(r.get('icp_pyme_revenue', 0), 2) for r in all_results],
                'Total_Revenue': [round(r.get('total_revenue', 0), 2) for r in all_results],
            }
            
            # Add edge cases columns if any
            all_edge_case_types = set()
            for result in all_results:
                edge_cases = result.get('edge_cases', {})
                all_edge_case_types.update(edge_cases.keys())
            
            for edge_case_type in all_edge_case_types:
                df_data[f'Edge_Case_{edge_case_type}'] = [
                    r.get('edge_cases', {}).get(edge_case_type, 0) for r in all_results
                ]
            
            df = pd.DataFrame(df_data)
            
            # Generate filename with month range
            months_str = "_".join([m.replace('-', '') for m in args.months])
            output_file = f"{output_dir}/accountant_mql_funnel_{months_str}.csv"
            
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
    
    analyze_funnel(start_date, end_date)

if __name__ == '__main__':
    main()

