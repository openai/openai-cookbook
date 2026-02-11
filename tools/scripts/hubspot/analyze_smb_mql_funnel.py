#!/usr/bin/env python3
"""
SMB MQL FUNNEL ANALYSIS
=======================

Analyzes the funnel from MQL (Marketing Qualified Lead) to Closed Won deals,
specifically for contacts identified as SMB (Small and Medium Business) by their rol_wizard field.
This is the opposite of the Accountant funnel - it includes all contacts that are NOT accountants.

FILTERING CRITERIA:
- MQL: Contacts CREATED in the period with rol_wizard indicating SMB role (NOT accountant)
- SQL: Contacts with hs_v2_date_entered_opportunity in the period with at least one deal (aligned with HubSpot funnel)
- Deal Created: Deals CREATED in the period (associated with MQL contacts)
- Deal Closed: Deals CLOSED WON in the period (both createdate and closedate in period)
- ICP Classification: Based on PRIMARY company type (same logic as ICP Operador billing)

DEFINITION OF "SMB MQL":
- Contact created in the period
- rol_wizard field does NOT indicate accountant role (e.g., NOT "Contador", "Estudio Contable", etc.)
- Excludes 'Usuario Invitado' contacts

FUNNEL STAGES:
1. MQL PYME: Contacts created in period with SMB rol_wizard (NOT accountant)
2. SQL: MQLs that entered opportunity stage (hs_v2_date_entered_opportunity) in period with at least one deal associated
3. Deal Created: Deals created in period (associated with MQL contacts)
4. Deal Closed Won: Deals closed won in period (createdate AND closedate in period)
5. ICP Operador vs ICP PYME: Classification based on PRIMARY company type

Usage:
  python analyze_smb_mql_funnel.py --month 2025-12
  python analyze_smb_mql_funnel.py --months 2025-11 2025-12
  python analyze_smb_mql_funnel.py --start-date 2025-12-01 --end-date 2026-01-01
"""

import os
import sys
import warnings
# Suppress urllib3 OpenSSL/LibreSSL compatibility warning (harmless) - MUST be before any imports
warnings.filterwarnings('ignore')
# Also suppress urllib3 warnings specifically
try:
    import urllib3
    urllib3.disable_warnings()
except ImportError:
    pass
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
    IMPORTANT: Returns False for null/empty values (HubSpot excludes nulls in 'doesn't contain' filter)
    """
    # If rol_wizard is null/empty, exclude from funnel (HubSpot behavior)
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    
    # SMB = any role that is NOT an accountant role
    return not is_accountant_role(rol_wizard)

def fetch_smb_mqls(start_date, end_date):
    """
    Fetch contacts created in period with SMB rol_wizard (NOT accountant, excluding 'Usuario Invitado')
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search"
    all_contacts = []
    after = None
    max_retries = 3
    retry_delay = 2
    
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "lead_source", "operator": "HAS_PROPERTY"},
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
        
        # Retry logic for API calls
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=HEADERS, json=payload, timeout=60)
                
                # Handle different error types
                if response.status_code == 400:
                    # Bad Request - don't retry, this is a client error
                    error_data = {}
                    try:
                        error_data = response.json()
                    except:
                        pass
                    error_msg = error_data.get('message', 'Bad Request')
                    print(f"❌ API Error 400: {error_msg}")
                    print(f"   This may be due to:")
                    print(f"   - Date range too large (try using --months instead)")
                    print(f"   - Invalid filter parameters")
                    print(f"   - API query limits exceeded")
                    # Create HTTPError with response attached
                    http_error = requests.exceptions.HTTPError(f"400 Client Error: {error_msg}")
                    http_error.response = response
                    raise http_error
                
                elif response.status_code == 429:
                    # Rate limiting - retry with backoff
                    retry_after = int(response.headers.get('Retry-After', retry_delay * (attempt + 1)))
                    if attempt < max_retries - 1:
                        print(f"⚠️  Rate limit hit. Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}...")
                        time.sleep(retry_after)
                        continue
                    else:
                        response.raise_for_status()
                
                elif response.status_code >= 500:
                    # Server errors - retry
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        print(f"⚠️  Server error {response.status_code}. Retrying in {wait_time} seconds ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    else:
                        response.raise_for_status()
                
                # Success
                response.raise_for_status()
                data = response.json()
                break
                
            except requests.exceptions.HTTPError as e:
                # Don't retry on client errors (4xx), only retry on server errors (5xx)
                if e.response is not None:
                    status_code = e.response.status_code
                    if 400 <= status_code < 500:
                        # Client error - don't retry, just raise
                        if status_code != 400:  # 400 already has detailed message
                            print(f"❌ Client error {status_code}: {e}")
                        raise
                    elif status_code >= 500:
                        # Server error - retry
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1)
                            print(f"⚠️  Server error {status_code}. Retrying in {wait_time} seconds ({attempt + 1}/{max_retries})...")
                            time.sleep(wait_time)
                            continue
                        else:
                            raise
                # If no response, treat as network error and retry
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    print(f"⚠️  HTTP error (no response). Retrying in {wait_time} seconds ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    raise
                    
            except requests.exceptions.RequestException as e:
                # Network errors - retry
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    print(f"⚠️  Request error: {str(e)}. Retrying in {wait_time} seconds ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ Error fetching contacts after {max_retries} attempts: {str(e)}")
                    raise
        
        results = data.get('results', [])
        all_contacts.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    # Filter for SMB roles (NOT accountant)
    smb_mqls = []
    for contact in all_contacts:
        props = contact.get('properties', {})
        rol_wizard = props.get('rol_wizard', '')
        if is_smb_role(rol_wizard):
            smb_mqls.append(contact)
    
    return smb_mqls

# Copy all helper functions from accountant funnel script
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

def create_funnel_visualization(csv_file_path, output_dir=None):
    """
    Create comprehensive funnel visualization from CSV output.
    Handles both single-period and multi-month comparative data.
    
    Args:
        csv_file_path: Path to the CSV file generated by analyze_funnel
        output_dir: Directory to save visualization (defaults to same dir as CSV)
    
    Returns:
        Path to saved visualization file
    """
    # Read CSV data
    df = pd.read_csv(csv_file_path)
    
    # Check if this is a multi-month comparison (has 'Month' column)
    if 'Month' in df.columns and len(df) > 1:
        # Multi-month comparison - create comparative visualization
        return create_comparative_visualization(df, csv_file_path, output_dir)
    
    # Single period visualization
    row = df.iloc[0]
    
    # Extract values
    period = row.get('Period', 'N/A')
    mql = int(row.get('MQL_PYME', 0))
    deal_created = int(row.get('Deal_Created', 0))
    deal_won = int(row.get('Deal_Closed_Won', 0))
    mql_to_deal = float(row.get('MQL_to_Deal_Rate_%', 0))
    deal_to_won = float(row.get('Deal_to_Won_Rate_%', 0))
    mql_to_won = float(row.get('MQL_to_Won_Rate_%', 0))
    sql_info = int(row.get('SQL_Informational', 0))
    mql_to_sql = float(row.get('MQL_to_SQL_Rate_%', 0))
    icp_operador_count = int(row.get('ICP_Operador_Count', 0))
    icp_pyme_count = int(row.get('ICP_PYME_Count', 0))
    total_revenue = float(row.get('Total_Revenue', 0))
    icp_operador_revenue = float(row.get('ICP_Operador_Revenue', 0))
    icp_pyme_revenue = float(row.get('ICP_PYME_Revenue', 0))
    
    # Set style
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Create figure with grid layout
    fig = plt.figure(figsize=(16, 12))
    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.35, wspace=0.3, 
                           height_ratios=[2, 1, 1], width_ratios=[1.2, 1])
    
    # ===== MAIN FUNNEL CHART =====
    ax1 = fig.add_subplot(gs[0, :])
    
    stages = ['MQL PYME', 'Deal Created', 'Deal Closed Won']
    values = [mql, deal_created, deal_won]
    percentages = [
        100,
        (deal_created/mql*100) if mql > 0 else 0,
        (deal_won/mql*100) if mql > 0 else 0
    ]
    
    # Color gradient for funnel
    colors = ['#4A90E2', '#7B68EE', '#9370DB']
    y_positions = [0, 1.5, 3]
    
    # Draw funnel bars
    max_width = max(values) if values else 1
    for stage, value, pct, y_pos, color in zip(stages, values, percentages, y_positions, colors):
        # Proportional width based on max value
        width = (value / max_width) * 10 if max_width > 0 else 0.5
        bar = ax1.barh(y_pos, width, height=0.8, color=color, alpha=0.85, 
                      edgecolor='white', linewidth=2.5)
        
        # Add value and percentage labels
        ax1.text(width/2, y_pos, f'{value:,}\n({pct:.1f}%)', 
                ha='center', va='center', fontsize=13, fontweight='bold', 
                color='white')
        
        # Add stage label
        ax1.text(-0.8, y_pos, stage, ha='right', va='center', 
                fontsize=13, fontweight='bold', color='#2c3e50')
    
    ax1.set_xlim(-3, 12)
    ax1.set_ylim(-0.5, 4.5)
    ax1.set_title(f'SMB MQL Funnel - {period}', fontsize=16, fontweight='bold', pad=20)
    ax1.axis('off')
    
    # ===== CONVERSION RATES BAR CHART =====
    ax2 = fig.add_subplot(gs[1, 0])
    
    paths = ['MQL→Deal', 'Deal→Won', 'MQL→Won']
    rates = [mql_to_deal, deal_to_won, mql_to_won]
    x_pos = range(len(paths))
    bars = ax2.bar(x_pos, rates, color='#4A90E2', alpha=0.8, edgecolor='white', linewidth=2)
    
    for bar, rate in zip(bars, rates):
        ax2.text(bar.get_x() + bar.get_width()/2., bar.get_height() + max(rates)*0.02,
                f'{rate:.1f}%', ha='center', va='bottom', fontsize=12, fontweight='bold')
    
    ax2.set_ylabel('Conversion Rate (%)', fontsize=11, fontweight='bold')
    ax2.set_title('Conversion Rates', fontsize=13, fontweight='bold', pad=15)
    ax2.set_ylim(0, max(rates) * 1.25 if rates and max(rates) > 0 else 50)
    ax2.grid(axis='y', alpha=0.3, linestyle='--')
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(paths, rotation=15, ha='right')
    
    # ===== ICP BREAKDOWN =====
    ax3 = fig.add_subplot(gs[1, 1])
    
    icp_types = ['ICP Operador', 'ICP PYME']
    icp_counts = [icp_operador_count, icp_pyme_count]
    icp_colors = ['#E74C3C', '#27AE60']
    
    if sum(icp_counts) > 0:
        bars = ax3.bar(icp_types, icp_counts, color=icp_colors, alpha=0.8, 
                      edgecolor='white', linewidth=2)
        
        for bar, count in zip(bars, icp_counts):
            pct = (count / sum(icp_counts) * 100) if sum(icp_counts) > 0 else 0
            ax3.text(bar.get_x() + bar.get_width()/2., bar.get_height() + max(icp_counts)*0.02,
                    f'{count}\n({pct:.1f}%)', ha='center', va='bottom', 
                    fontsize=11, fontweight='bold')
        
        ax3.set_ylabel('Count', fontsize=11, fontweight='bold')
        ax3.set_title('ICP Classification (Closed Won)', fontsize=13, fontweight='bold', pad=15)
        ax3.set_ylim(0, max(icp_counts) * 1.25 if icp_counts else 10)
        ax3.grid(axis='y', alpha=0.3, linestyle='--')
    else:
        ax3.text(0.5, 0.5, 'No Closed Won Deals', ha='center', va='center',
                fontsize=12, transform=ax3.transAxes)
        ax3.set_title('ICP Classification (Closed Won)', fontsize=13, fontweight='bold', pad=15)
    
    # ===== REVENUE BREAKDOWN =====
    ax4 = fig.add_subplot(gs[2, 0])
    
    if total_revenue > 0:
        revenue_types = ['ICP Operador', 'ICP PYME']
        revenues = [icp_operador_revenue, icp_pyme_revenue]
        
        bars = ax4.bar(revenue_types, revenues, color=icp_colors, alpha=0.8,
                      edgecolor='white', linewidth=2)
        
        for bar, rev in zip(bars, revenues):
            pct = (rev / total_revenue * 100) if total_revenue > 0 else 0
            ax4.text(bar.get_x() + bar.get_width()/2., bar.get_height() + total_revenue*0.02,
                    f'${rev:,.0f}\n({pct:.1f}%)', ha='center', va='bottom',
                    fontsize=11, fontweight='bold')
        
        ax4.set_ylabel('Revenue ($)', fontsize=11, fontweight='bold')
        ax4.set_title('Revenue by ICP Type', fontsize=13, fontweight='bold', pad=15)
        ax4.set_ylim(0, total_revenue * 1.25)
        ax4.grid(axis='y', alpha=0.3, linestyle='--')
        
        # Format y-axis as currency
        ax4.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    else:
        ax4.text(0.5, 0.5, 'No Revenue Data', ha='center', va='center',
                fontsize=12, transform=ax4.transAxes)
        ax4.set_title('Revenue by ICP Type', fontsize=13, fontweight='bold', pad=15)
    
    # ===== SQL INFORMATIONAL METRICS =====
    ax5 = fig.add_subplot(gs[2, 1])
    
    sql_metrics = ['MQL→SQL', 'SQL→Deal']
    sql_rates = [mql_to_sql, 
                 float(row.get('SQL_to_Deal_Rate_%', 0)) if sql_info > 0 else 0]
    
    x_pos_sql = range(len(sql_metrics))
    bars = ax5.bar(x_pos_sql, sql_rates, color='#F39C12', alpha=0.8,
                  edgecolor='white', linewidth=2)
    
    for bar, rate in zip(bars, sql_rates):
        ax5.text(bar.get_x() + bar.get_width()/2., bar.get_height() + max(sql_rates)*0.02,
                f'{rate:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    ax5.set_ylabel('Rate (%)', fontsize=11, fontweight='bold')
    ax5.set_title('SQL Metrics (Informational)', fontsize=13, fontweight='bold', pad=15)
    ax5.set_ylim(0, max(sql_rates) * 1.25 if sql_rates and max(sql_rates) > 0 else 50)
    ax5.grid(axis='y', alpha=0.3, linestyle='--')
    ax5.set_xticks(x_pos_sql)
    ax5.set_xticklabels(sql_metrics, rotation=15, ha='right')
    
    # Add summary text box
    summary_text = (
        f"Summary:\n"
        f"MQL PYME: {mql:,} | "
        f"Deal Created: {deal_created:,} ({mql_to_deal:.1f}%) | "
        f"Won: {deal_won:,} ({mql_to_won:.1f}%)\n"
        f"Total Revenue: ${total_revenue:,.2f} | "
        f"ICP Operador: {icp_operador_count} (${icp_operador_revenue:,.2f}) | "
        f"ICP PYME: {icp_pyme_count} (${icp_pyme_revenue:,.2f})"
    )
    
    fig.text(0.5, 0.02, summary_text, ha='center', fontsize=10,
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    plt.suptitle('SMB MQL Funnel Analysis Dashboard', fontsize=18, fontweight='bold', y=0.98)
    
    # Save visualization
    if output_dir is None:
        output_dir = os.path.dirname(csv_file_path)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate visualization filename from CSV filename
    csv_basename = os.path.basename(csv_file_path)
    viz_filename = csv_basename.replace('.csv', '_visualization.png')
    viz_path = os.path.join(output_dir, viz_filename)
    
    plt.savefig(viz_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"📊 Visualization saved to: {viz_path}")
    
    return viz_path

def create_comparative_visualization(df, csv_file_path, output_dir=None):
    """
    Create comparative visualization for multi-month analysis.
    
    Args:
        df: DataFrame with multiple months of data
        csv_file_path: Path to the CSV file
        output_dir: Directory to save visualization
    
    Returns:
        Path to saved visualization file
    """
    # Set style
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Create figure with gridspec for better layout control
    fig = plt.figure(figsize=(18, 14))
    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.4, wspace=0.3, 
                           height_ratios=[1.5, 1, 1], width_ratios=[1, 1])
    fig.suptitle('SMB MQL Funnel - Multi-Month Comparison', fontsize=18, fontweight='bold', y=0.98)
    
    months = df['Month'].tolist()
    
    # Extract metrics
    mql_values = df['MQL_PYME'].tolist()
    deal_created_values = df['Deal_Created'].tolist()
    deal_won_values = df['Deal_Closed_Won'].tolist()
    mql_to_deal_rates = df['MQL_to_Deal_Rate_%'].tolist()
    deal_to_won_rates = df['Deal_to_Won_Rate_%'].tolist()
    mql_to_won_rates = df['MQL_to_Won_Rate_%'].tolist()
    total_revenue_values = df['Total_Revenue'].tolist()
    
    # Calculate aggregated totals for funnel
    total_mql = sum(mql_values)
    total_deal_created = sum(deal_created_values)
    total_deal_won = sum(deal_won_values)
    total_revenue = sum(total_revenue_values)
    total_icp_operador = sum(df['ICP_Operador_Count'].tolist()) if 'ICP_Operador_Count' in df.columns else 0
    total_icp_pyme = sum(df['ICP_PYME_Count'].tolist()) if 'ICP_PYME_Count' in df.columns else 0
    
    # Calculate overall conversion rates
    overall_mql_to_deal = (total_deal_created / total_mql * 100) if total_mql > 0 else 0
    overall_deal_to_won = (total_deal_won / total_deal_created * 100) if total_deal_created > 0 else 0
    overall_mql_to_won = (total_deal_won / total_mql * 100) if total_mql > 0 else 0
    
    # ===== AGGREGATED FUNNEL CHART =====
    ax_funnel = fig.add_subplot(gs[0, :])
    
    stages = ['MQL PYME', 'Deal Created', 'Deal Closed Won']
    values = [total_mql, total_deal_created, total_deal_won]
    percentages = [
        100,
        (total_deal_created/total_mql*100) if total_mql > 0 else 0,
        (total_deal_won/total_mql*100) if total_mql > 0 else 0
    ]
    
    # Color gradient for funnel
    colors = ['#4A90E2', '#7B68EE', '#9370DB']
    y_positions = [0, 1.5, 3]
    
    # Draw funnel bars
    max_width = max(values) if values else 1
    for stage, value, pct, y_pos, color in zip(stages, values, percentages, y_positions, colors):
        # Proportional width based on max value
        width = (value / max_width) * 12 if max_width > 0 else 0.5
        bar = ax_funnel.barh(y_pos, width, height=0.8, color=color, alpha=0.85, 
                             edgecolor='white', linewidth=2.5)
        
        # Add value and percentage labels
        ax_funnel.text(width/2, y_pos, f'{value:,}\n({pct:.1f}%)', 
                      ha='center', va='center', fontsize=14, fontweight='bold', 
                      color='white')
        
        # Add stage label
        ax_funnel.text(-1.0, y_pos, stage, ha='right', va='center', 
                      fontsize=14, fontweight='bold', color='#2c3e50')
    
    ax_funnel.set_xlim(-2, 14)
    ax_funnel.set_ylim(-0.5, 4.5)
    period_label = f"{months[0]} to {months[-1]}" if len(months) > 1 else months[0]
    ax_funnel.set_title(f'Aggregated Funnel - {period_label} (Total: {len(months)} months)', 
                       fontsize=15, fontweight='bold', pad=20)
    ax_funnel.axis('off')
    
    # Add summary text on funnel chart
    funnel_summary = (
        f"Overall Rates: MQL→Deal: {overall_mql_to_deal:.1f}% | "
        f"Deal→Won: {overall_deal_to_won:.1f}% | "
        f"MQL→Won: {overall_mql_to_won:.1f}% | "
        f"Total Revenue: ${total_revenue:,.0f}"
    )
    ax_funnel.text(0.5, -0.3, funnel_summary, ha='center', fontsize=11,
                   transform=ax_funnel.transAxes, 
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    # ===== FUNNEL VALUES OVER TIME =====
    ax1 = fig.add_subplot(gs[1, 0])
    x = range(len(months))
    width = 0.25
    
    ax1.bar([i - width for i in x], mql_values, width, label='MQL PYME', color='#4A90E2', alpha=0.8)
    ax1.bar(x, deal_created_values, width, label='Deal Created', color='#7B68EE', alpha=0.8)
    ax1.bar([i + width for i in x], deal_won_values, width, label='Deal Closed Won', color='#9370DB', alpha=0.8)
    
    ax1.set_xlabel('Month', fontweight='bold')
    ax1.set_ylabel('Count', fontweight='bold')
    ax1.set_title('Funnel Stages Over Time', fontsize=13, fontweight='bold', pad=15)
    ax1.set_xticks(x)
    ax1.set_xticklabels(months, rotation=45, ha='right')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3, linestyle='--')
    
    # ===== CONVERSION RATES OVER TIME =====
    ax2 = fig.add_subplot(gs[1, 1])
    x_pos = range(len(months))
    ax2.plot(x_pos, mql_to_deal_rates, marker='o', linewidth=2.5, label='MQL→Deal', color='#4A90E2')
    ax2.plot(x_pos, deal_to_won_rates, marker='s', linewidth=2.5, label='Deal→Won', color='#7B68EE')
    ax2.plot(x_pos, mql_to_won_rates, marker='^', linewidth=2.5, label='MQL→Won', color='#9370DB')
    
    ax2.set_xlabel('Month', fontweight='bold')
    ax2.set_ylabel('Conversion Rate (%)', fontweight='bold')
    ax2.set_title('Conversion Rates Over Time', fontsize=13, fontweight='bold', pad=15)
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(months, rotation=45, ha='right')
    ax2.legend()
    ax2.grid(alpha=0.3, linestyle='--')
    
    # ===== REVENUE OVER TIME =====
    ax3 = fig.add_subplot(gs[2, 0])
    x_pos_rev = range(len(months))
    bars = ax3.bar(x_pos_rev, total_revenue_values, color='#27AE60', alpha=0.8, edgecolor='white', linewidth=2)
    
    for bar, rev in zip(bars, total_revenue_values):
        ax3.text(bar.get_x() + bar.get_width()/2., bar.get_height() + max(total_revenue_values)*0.02,
                f'${rev:,.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax3.set_xlabel('Month', fontweight='bold')
    ax3.set_ylabel('Revenue ($)', fontsize=11, fontweight='bold')
    ax3.set_title('Total Revenue Over Time', fontsize=13, fontweight='bold', pad=15)
    ax3.set_xticks(x_pos_rev)
    ax3.set_xticklabels(months, rotation=45, ha='right')
    ax3.grid(axis='y', alpha=0.3, linestyle='--')
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # ===== ICP BREAKDOWN COMPARISON =====
    ax4 = fig.add_subplot(gs[2, 1])
    if 'ICP_Operador_Count' in df.columns and 'ICP_PYME_Count' in df.columns:
        icp_operador_counts = df['ICP_Operador_Count'].tolist()
        icp_pyme_counts = df['ICP_PYME_Count'].tolist()
        
        x = range(len(months))
        width = 0.35
        
        ax4.bar([i - width/2 for i in x], icp_operador_counts, width, 
               label='ICP Operador', color='#E74C3C', alpha=0.8)
        ax4.bar([i + width/2 for i in x], icp_pyme_counts, width,
               label='ICP PYME', color='#27AE60', alpha=0.8)
        
        ax4.set_xlabel('Month', fontweight='bold')
        ax4.set_ylabel('Count', fontweight='bold')
        ax4.set_title('ICP Classification Over Time', fontsize=13, fontweight='bold', pad=15)
        ax4.set_xticks(x)
        ax4.set_xticklabels(months, rotation=45, ha='right')
        ax4.legend()
        ax4.grid(axis='y', alpha=0.3, linestyle='--')
    else:
        ax4.text(0.5, 0.5, 'No ICP Data Available', ha='center', va='center',
                fontsize=12, transform=ax4.transAxes)
        ax4.set_title('ICP Classification Over Time', fontsize=13, fontweight='bold', pad=15)
    
    plt.tight_layout(rect=[0, 0.02, 1, 0.96], pad=2.0)
    
    # Save visualization
    if output_dir is None:
        output_dir = os.path.dirname(csv_file_path)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate visualization filename
    csv_basename = os.path.basename(csv_file_path)
    viz_filename = csv_basename.replace('.csv', '_visualization.png')
    viz_path = os.path.join(output_dir, viz_filename)
    
    plt.savefig(viz_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"📊 Comparative visualization saved to: {viz_path}")
    
    return viz_path

def analyze_funnel(start_date, end_date):
    """
    Analyze the funnel from MQL PYME to Closed Won deals
    """
    # Validate date range
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    days_diff = (end_dt - start_dt).days
    
    if days_diff > 365:
        print(f"⚠️  Warning: Large date range detected ({days_diff} days).")
        print(f"   This may take a long time and could hit API rate limits or query limits.")
        print(f"   For full year analysis, consider using --months instead:")
        print(f"   Example: --months 2025-01 2025-02 2025-03 ... 2025-12")
        print(f"   Or analyze in smaller chunks (e.g., quarterly).\n")
    
    print(f"\n{'='*80}")
    print(f"SMB MQL FUNNEL ANALYSIS")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    # STAGE 1: Fetch MQL PYME (contacts created in period with SMB rol_wizard - NOT accountant)
    print("📊 Stage 1: Fetching MQL PYME...")
    mql_contacts = fetch_smb_mqls(start_date, end_date)
    print(f"   Found {len(mql_contacts)} MQL PYME\n")
    
    # STAGE 2: Identify SQLs (MQLs that entered opportunity in period with at least one deal)
    print("📊 Stage 2: Identifying SQLs (sql_date in period + at least one deal)...")
    sql_contacts = []
    sql_without_valid_deal = []  # Track contacts with SQL date but no deals returned by API
    
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
                    contact_id = contact.get('id')
                    # Fetch ALL deals for contact (not only created in period) to align with HubSpot funnel
                    deals = get_contact_deals(contact_id, start_date, end_date, include_all_deals=True)
                    has_valid_deal = len(deals) > 0
                    deal_validation_reasons = []
                    edge_case_type = None
                    if not deals:
                        deal_validation_reasons.append("No deals associated with contact (API returned empty)")
                        edge_case_type = "NO_DEALS_ASSOCIATED"
                    
                    if has_valid_deal:
                        sql_contacts.append(contact)
                    else:
                        sql_without_valid_deal.append({
                            'contact_id': contact_id,
                            'email': props.get('email', ''),
                            'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                            'createdate': contact_createdate_str,
                            'sql_date': sql_date_str,
                            'num_deals': 0,
                            'reasons': deal_validation_reasons,
                            'edge_case_type': edge_case_type
                        })
            except Exception as e:
                pass
    
    print(f"   Found {len(sql_contacts)} SQLs ({len(sql_contacts)/len(mql_contacts)*100:.1f}% of MQLs)" if mql_contacts else "   Found 0 SQLs")
    print(f"   Found {len(sql_without_valid_deal)} contacts with SQL date but NO deals from API\n")
    
    # Analyze reasons for SQL without valid deal (simplified version - same logic as accountant funnel)
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
    
    # STAGE 3: Get deals created in period (associated with MQL contacts)
    # STRICT FUNNEL: MQL → Deal Created → Won
    # This ensures that only deals associated with MQL contacts are considered
    # IMPORTANT: Contact must be created before or on the same day as the deal (HubSpot logic)
    print("📊 Stage 3: Fetching deals created in period (STRICT FUNNEL: MQL → Deal Created)...")
    all_deals_created = []
    contact_to_deals = {}
    
    for contact in mql_contacts:
        contact_id = contact.get('id')
        contact_props = contact.get('properties', {})
        contact_createdate_str = contact_props.get('createdate', '')
        
        if not contact_createdate_str:
            continue
        
        try:
            contact_created_dt = datetime.fromisoformat(contact_createdate_str.replace('Z', '+00:00'))
        except:
            continue
        
        deals = get_contact_deals(contact_id, start_date, end_date)
        if deals:
            # Validate: Contact must be created before or on the same day as the deal
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
    
    deals_created = list(unique_deals_created.values())
    print(f"   Found {len(deals_created)} unique deals created in period (associated with MQL contacts, contact created < deal created)\n")
    
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
    print(f"| MQL PYME | {len(mql_contacts)} | - |")
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
        'MQL_PYME': [len(mql_contacts)],
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
    output_file = f"{output_dir}/smb_mql_funnel_{start_date_clean}_{end_date_clean}.csv"
    
    df.to_csv(output_file, index=False)
    print(f"📄 Results saved to CSV: {output_file}")
    print()
    
    # Generate visualization automatically
    try:
        viz_path = create_funnel_visualization(output_file, output_dir)
        print()
    except Exception as e:
        print(f"⚠️  Warning: Could not generate visualization: {str(e)}")
        print()
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Analyze SMB MQL Funnel')
    parser.add_argument('--month', type=str, help='Month in YYYY-MM format (e.g., 2025-12)')
    parser.add_argument('--months', nargs='+', type=str, help='Multiple months in format YYYY-MM (e.g., --months 2025-11 2025-12)')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    parser.add_argument('--csv', type=str, help='Path to existing CSV file to generate visualization from (e.g., tools/outputs/smb_mql_funnel_20251201_20260101.csv)')
    
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
            print()
        
        # Print comparative summary
        if all_results:
            print("="*80)
            print("COMPARATIVE SUMMARY")
            print("="*80)
            print()
            print("**STRICT FUNNEL PATH:** MQL → Deal Created → Won")
            print()
            print("| Month | MQL PYME | Deal Created | Deal Closed Won | MQL→Deal | Deal→Won | MQL→Won | ICP Operador | ICP PYME |")
            print("|-------|----------|-------------|-----------------|----------|---------|---------|--------------|----------|")
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
                'MQL_PYME': [r.get('mql_count', 0) for r in all_results],
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
            output_file = f"{output_dir}/smb_mql_funnel_{months_str}.csv"
            
            df.to_csv(output_file, index=False)
            print(f"📄 Comparative results saved to CSV: {output_file}")
            print()
            
            # Generate visualization for comparative data
            try:
                viz_path = create_funnel_visualization(output_file, output_dir)
                print()
            except Exception as e:
                print(f"⚠️  Warning: Could not generate visualization: {str(e)}")
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

