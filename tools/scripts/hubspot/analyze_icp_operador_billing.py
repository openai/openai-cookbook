#!/usr/bin/env python3
"""
ICP OPERADOR BILLING ANALYSIS

Analyzes closed deals to determine "who we bill" (ICP Operador = Accountant billing).

FILTERING:
- Deals must be CLOSED WON
- Deals must be CREATED within the date range
- Deals must be CLOSED within the date range
(Matches HubSpot report filter: "Close date is This month" AND "Create date is This month")

VALIDATIONS:
- Validates that deals have a PRIMARY company association (Type ID 5)
- Reports deals without primary company (these need data quality attention)

DEFINITION OF "ICP OPERADOR" (Accountant Billing):
PRIMARY COMPANY METHOD (ONLY RELIABLE METHOD):
   - Find the primary company in deal-company associations (Type ID 5)
   - If company type is one of: "Cuenta Contador", "Cuenta Contador y Reseller", "Contador Robado"
   → Then we bill an accountant (ICP Operador)

NOTE: Plan name method is NOT reliable because PYMEs can have "ICP Contador" plans
when an accountant refers them, but we still bill the PYME (not the accountant).

Usage:
  python analyze_icp_operador_billing.py --month 2025-12
  python analyze_icp_operador_billing.py --start-date 2025-12-01 --end-date 2026-01-01
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

def fetch_closed_deals(start_date, end_date):
    """Fetch all closed won deals in date range"""
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    all_deals = []
    after = None
    
    while True:
        filters = [
            {"propertyName": "closedate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "closedate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
            {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": ["dealname", "dealstage", "closedate", "createdate", "amount", "nombre_del_plan_del_negocio"],
            "associations": ["companies"],
            "limit": 100
        }
        if after:
            payload["after"] = after
            
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        all_deals.extend(results)
        
        after = data.get('paging', {}).get('next', {}).get('after')
        if not after:
            break
        time.sleep(0.2)
    
    return all_deals

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

def get_contact_details(contact_id):
    """Get contact details (email, createdate, name, lead_source, rol_wizard)"""
    contact_url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}"
    contact_params = {'properties': 'email,createdate,firstname,lastname,lead_source,rol_wizard'}
    try:
        contact_response = requests.get(contact_url, headers=HEADERS, params=contact_params, timeout=30)
        if contact_response.status_code == 200:
            contact_props = contact_response.json().get('properties', {})
            email = contact_props.get('email', '')
            createdate = contact_props.get('createdate', '')
            firstname = contact_props.get('firstname', '')
            lastname = contact_props.get('lastname', '')
            lead_source = contact_props.get('lead_source', '')
            rol_wizard = contact_props.get('rol_wizard', '')
            name = f"{firstname} {lastname}".strip() if (firstname or lastname) else email
            return email, createdate, name, lead_source, rol_wizard
    except:
        pass
    return None, None, None, None, None

def get_initial_contact_for_deal(deal_id):
    """
    Get the initial MQL contact that started the funnel for a deal.
    
    Strategy 1 (Preferred): Uses Type ID 14: "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol"
    Strategy 2 (Fallback): Finds contact with earliest createdate (MQL = contact created, excluding 'Usuario Invitado')
    
    Returns: (contact_id, contact_email, contact_createdate, contact_name, method_used, rol_wizard) 
             or (None, None, None, None, None, None)
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/contacts"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            associations = response.json().get('results', [])
            
            if not associations:
                return None, None, None, None, None
            
            # STRATEGY 1: Look for Type ID 14: "Contacto Inicial que da el Alta del Negocio"
            for assoc in associations:
                association_types = assoc.get('associationTypes', [])
                for assoc_type in association_types:
                    if assoc_type.get('typeId') == 14:
                        contact_id = assoc.get('toObjectId')
                        email, createdate, name, lead_source, rol_wizard = get_contact_details(contact_id)
                        if contact_id:
                            return contact_id, email or '', createdate or '', name or '', 'Type_ID_14', rol_wizard or ''
            
            # STRATEGY 2 (Fallback): Find contact with earliest createdate (excluding 'Usuario Invitado')
            earliest_contact_id = None
            earliest_createdate = None
            earliest_email = None
            earliest_name = None
            earliest_rol_wizard = None
            
            # Track contacts without createdate (fallback if no contacts have createdate)
            contacts_without_date = []
            
            for assoc in associations:
                contact_id = assoc.get('toObjectId')
                email, createdate, name, lead_source, rol_wizard = get_contact_details(contact_id)
                
                # Exclude 'Usuario Invitado' (team member invitations, not MQLs) and contacts with no lead_source (null)
                if lead_source == 'Usuario Invitado' or not lead_source:
                    continue
                
                # If contact fetch failed, skip
                if email is None and createdate is None and name is None:
                    continue
                
                # Compare createdates (ISO format strings can be compared directly)
                if createdate:
                    if earliest_createdate is None or createdate < earliest_createdate:
                        earliest_createdate = createdate
                        earliest_contact_id = contact_id
                        earliest_email = email or ''
                        earliest_name = name or ''
                        earliest_rol_wizard = rol_wizard or ''
                else:
                    # Store contacts without createdate as fallback
                    contacts_without_date.append((contact_id, email or '', name or '', rol_wizard or ''))
            
            # If we found a contact with createdate, return it
            if earliest_contact_id:
                return earliest_contact_id, earliest_email, earliest_createdate, earliest_name, 'Earliest_Created', earliest_rol_wizard
            
            # Fallback: If no contacts have createdate but we have non-'Usuario Invitado' contacts, return the first one
            if contacts_without_date:
                contact_id, email, name, rol_wizard = contacts_without_date[0]
                return contact_id, email, '', name, 'Earliest_Created_No_Date', rol_wizard
            
    except Exception as e:
        # Silently fail - return None values
        pass
    
    return None, None, None, None, None, None

def is_icp_contador_plan(plan_name):
    """Check if plan name contains 'ICP' AND 'Contador'"""
    if not plan_name:
        return False
    plan_upper = plan_name.upper()
    return 'ICP' in plan_upper and 'CONTADOR' in plan_upper

def print_comparative_analysis(all_results, combined_df):
    """Print comparative analysis across multiple months"""
    months = [r['month'] for r in all_results]
    months_header = " | ".join([f"{m}" for m in months])
    months_separator = " | ".join(["---" for _ in months])
    
    print("\n" + "=" * 80)
    print(f"ICP OPERADOR BILLING ANALYSIS - COMPARATIVE ({', '.join(months)})")
    print("=" * 80)
    print()
    
    # Summary table
    print("## Summary")
    print()
    print(f"| Metric | {' | '.join(months)} |")
    print(f"|--------|{months_separator}|")
    
    for metric_name, metric_key in [
        ("Total Closed Deals", "total"),
        ("Deals WITH Primary Company", "total_with_primary"),
        ("Deals WITHOUT Primary Company ⚠️", "total_without_primary"),
        ("ICP Operador (Billed to Accountant)", "icp_total"),
        ("Non-ICP Operador (Billed to SMB)", "non_icp"),
    ]:
        values = [str(r[metric_key]) for r in all_results]
        print(f"| {metric_name} | {' | '.join(values)} |")
    
    # Percentages for ICP Operador
    print()
    print(f"| Metric | {' | '.join(months)} |")
    print(f"|--------|{months_separator}|")
    icp_pcts = []
    non_icp_pcts = []
    for r in all_results:
        if r['total_with_primary'] > 0:
            icp_pct = (r['icp_total'] / r['total_with_primary']) * 100
            non_icp_pct = (r['non_icp'] / r['total_with_primary']) * 100
        else:
            icp_pct = 0
            non_icp_pct = 0
        icp_pcts.append(f"{icp_pct:.1f}%")
        non_icp_pcts.append(f"{non_icp_pct:.1f}%")
    
    print(f"| ICP Operador % (of deals with primary company) | {' | '.join(icp_pcts)} |")
    print(f"| Non-ICP Operador % (of deals with primary company) | {' | '.join(non_icp_pcts)} |")
    print()
    print("**Method:** ICP Operador is determined by PRIMARY company type (Cuenta Contador, Cuenta Contador y Reseller, Contador Robado)")
    print()
    
    # Initial MQL Contact Information
    print("## Initial MQL Contact Information")
    print()
    print(f"| Metric | {' | '.join(months)} |")
    print(f"|--------|{months_separator}|")
    print(f"| Deals WITH Initial Contact Identified | {' | '.join([str(r['total_with_initial_contact']) for r in all_results])} |")
    print(f"| Deals WITHOUT Initial Contact | {' | '.join([str(r['total_without_initial_contact']) for r in all_results])} |")
    print()
    
    # Identification Method
    print(f"| Identification Method | {' | '.join(months)} |")
    print(f"|----------------------|{months_separator}|")
    print(f"| Type ID 14 (Preferred) | {' | '.join([str(r['type_id_14_count']) for r in all_results])} |")
    print(f"| Earliest Created (Fallback) | {' | '.join([str(r['earliest_created_count']) for r in all_results])} |")
    print()
    
    # rol_wizard Distribution
    print("## Initial Contact Role (rol_wizard) Distribution")
    print()
    print(f"| Metric | {' | '.join(months)} |")
    print(f"|--------|{months_separator}|")
    print(f"| Contacts with 'rol_wizard' populated | {' | '.join([str(r['total_with_rol_wizard']) for r in all_results])} |")
    print(f"| Contacts without 'rol_wizard' | {' | '.join([str(r['total_without_rol_wizard']) for r in all_results])} |")
    print()
    
    # Percentage of total deals
    print(f"| Metric | {' | '.join(months)} |")
    print(f"|--------|{months_separator}|")
    rol_pcts = []
    no_rol_pcts = []
    for r in all_results:
        if r['total'] > 0:
            rol_pct = (r['total_with_rol_wizard'] / r['total']) * 100
            no_rol_pct = (r['total_without_rol_wizard'] / r['total']) * 100
        else:
            rol_pct = 0
            no_rol_pct = 0
        rol_pcts.append(f"{rol_pct:.1f}%")
        no_rol_pcts.append(f"{no_rol_pct:.1f}%")
    
    print(f"| % with 'rol_wizard' (of total deals) | {' | '.join(rol_pcts)} |")
    print(f"| % without 'rol_wizard' (of total deals) | {' | '.join(no_rol_pcts)} |")
    print()
    
    # rol_wizard Role Distribution - Combined across all months
    print("### rol_wizard Role Distribution (Combined)")
    print()
    all_role_counts = {}
    for r in all_results:
        for role, count in r['role_counts'].items():
            if role not in all_role_counts:
                all_role_counts[role] = {}
            all_role_counts[role][r['month']] = count
    
    if all_role_counts:
        # Get all months for header
        header = "| Role | " + " | ".join(months) + " | Total |"
        separator = "|------|" + " | ".join(["---" for _ in months]) + " | --- |"
        print(header)
        print(separator)
        
        for role in sorted(all_role_counts.keys()):
            row_values = []
            total_count = 0
            for month in months:
                count = all_role_counts[role].get(month, 0)
                row_values.append(str(count))
                total_count += count
            row_values.append(str(total_count))
            print(f"| {role} | {' | '.join(row_values)} |")
        print()
    
    # Additional Information
    print("## Additional Information")
    print()
    print(f"| Metric | {' | '.join(months)} |")
    print(f"|--------|{months_separator}|")
    print(f"| Deals with 'ICP Contador' plan name | {' | '.join([str(r['by_plan']) for r in all_results])} |")
    print(f"| Accountant companies with non-ICP Contador plan | {' | '.join([str(r['case2']) for r in all_results])} |")
    print()

def analyze_deal(deal):
    """Analyze if deal is ICP Operador (billed to accountant)"""
    deal_id = deal.get('id')
    props = deal.get('properties', {})
    plan_name = props.get('nombre_del_plan_del_negocio', '')
    
    # Get PRIMARY company
    primary_company_id = get_primary_company_id(deal_id)
    primary_company_name = None
    primary_company_type = None
    
    is_accountant_by_type = False
    is_accountant_by_plan = is_icp_contador_plan(plan_name)  # For informational purposes only
    
    if primary_company_id:
        primary_company_name, primary_company_type = get_company_type(primary_company_id)
        if primary_company_type in ACCOUNTANT_COMPANY_TYPES:
            is_accountant_by_type = True
    
    # ONLY use primary company type as reliable method
    # Plan name is not reliable because PYMEs can have ICP Contador plans when referred by accountants
    is_icp_operador = is_accountant_by_type
    
    # Validation: Check if deal has primary company
    has_primary_company = primary_company_id is not None and primary_company_name is not None
    
    # Get initial MQL contact that started the funnel (Type ID 14 or earliest created contact)
    initial_contact_id, initial_contact_email, initial_contact_createdate, initial_contact_name, contact_method, initial_contact_rol_wizard = get_initial_contact_for_deal(deal_id)
    has_initial_contact = initial_contact_id is not None
    
    return {
        'deal_id': deal_id,
        'deal_name': props.get('dealname', ''),
        'createdate': props.get('createdate', ''),
        'closedate': props.get('closedate', ''),
        'amount': props.get('amount', ''),
        'plan_name': plan_name,
        'primary_company_id': primary_company_id,
        'primary_company_name': primary_company_name or '',
        'primary_company_type': primary_company_type or '',
        'is_accountant_by_type': is_accountant_by_type,
        'is_accountant_by_plan': is_accountant_by_plan,
        'is_icp_operador': is_icp_operador,
        'has_primary_company': has_primary_company,
        'initial_contact_id': initial_contact_id or '',
        'initial_contact_email': initial_contact_email or '',
        'initial_contact_name': initial_contact_name or '',
        'initial_contact_createdate': initial_contact_createdate or '',
        'initial_contact_rol_wizard': initial_contact_rol_wizard or '',
        'has_initial_contact': has_initial_contact,
        'initial_contact_method': contact_method or ''
    }

def process_month(month_str):
    """Process a single month and return analysis results"""
    year, month = month_str.split('-')
    start_date = f"{year}-{month}-01"
    if month == '12':
        end_date = f"{int(year)+1}-01-01"
    else:
        end_date = f"{year}-{int(month)+1:02d}-01"
    
    print(f"Fetching closed deals for {month_str} (created AND closed between {start_date} and {end_date})...")
    deals = fetch_closed_deals(start_date, end_date)
    print(f"Found {len(deals)} closed deals for {month_str}\n")
    
    # Analyze each deal
    results = []
    for i, deal in enumerate(deals, 1):
        print(f"Processing {month_str}: {i}/{len(deals)}...", end='\r')
        result = analyze_deal(deal)
        result['month'] = month_str
        results.append(result)
        time.sleep(0.1)
    
    df = pd.DataFrame(results)
    return df, start_date, end_date

def analyze_single_month(df, month_str):
    """Analyze a single month's data and return metrics"""
    deals_without_primary = df[~df['has_primary_company']]
    deals_with_primary = df[df['has_primary_company']]
    
    total = len(df)
    total_with_primary = len(deals_with_primary)
    total_without_primary = len(deals_without_primary)
    
    icp_total = deals_with_primary['is_icp_operador'].sum()
    non_icp = total_with_primary - icp_total
    
    by_plan = df['is_accountant_by_plan'].sum()
    case2 = len(df[(df['is_accountant_by_type'] == True) & (df['is_accountant_by_plan'] == False)])
    
    total_with_initial_contact = df['has_initial_contact'].sum()
    total_without_initial_contact = len(df[~df['has_initial_contact']])
    
    type_id_14_count = len(df[df['initial_contact_method'] == 'Type_ID_14'])
    earliest_created_count = len(df[df['initial_contact_method'] == 'Earliest_Created'])
    
    deals_with_rol_wizard = df[df['initial_contact_rol_wizard'].notna() & (df['initial_contact_rol_wizard'] != '')]
    total_with_rol_wizard = len(deals_with_rol_wizard)
    total_without_rol_wizard = total_with_initial_contact - total_with_rol_wizard
    
    from collections import Counter
    role_counts = Counter(deals_with_rol_wizard['initial_contact_rol_wizard'])
    
    return {
        'month': month_str,
        'total': total,
        'total_with_primary': total_with_primary,
        'total_without_primary': total_without_primary,
        'icp_total': icp_total,
        'non_icp': non_icp,
        'by_plan': by_plan,
        'case2': case2,
        'total_with_initial_contact': total_with_initial_contact,
        'total_without_initial_contact': total_without_initial_contact,
        'type_id_14_count': type_id_14_count,
        'earliest_created_count': earliest_created_count,
        'total_with_rol_wizard': total_with_rol_wizard,
        'total_without_rol_wizard': total_without_rol_wizard,
        'role_counts': role_counts,
        'df': df
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze ICP Operador billing for closed deals')
    parser.add_argument('--month', type=str, help='Month in format YYYY-MM')
    parser.add_argument('--months', nargs='+', type=str, help='Multiple months in format YYYY-MM (e.g., --months 2025-11 2025-12)')
    parser.add_argument('--start-date', type=str, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='End date YYYY-MM-DD')
    
    args = parser.parse_args()
    
    # Handle multiple months
    if args.months:
        all_results = []
        all_dfs = []
        
        for month_str in args.months:
            df, start_date, end_date = process_month(month_str)
            all_dfs.append(df)
            all_results.append(analyze_single_month(df, month_str))
        
        # Combine all dataframes
        combined_df = pd.concat(all_dfs, ignore_index=True)
        
        # Print comparative analysis
        print_comparative_analysis(all_results, combined_df)
        
        # Save combined CSV
        output_dir = "tools/outputs"
        os.makedirs(output_dir, exist_ok=True)
        months_str = "_".join([m.replace('-', '') for m in args.months])
        output_file = f"{output_dir}/icp_operador_analysis_{months_str}.csv"
        combined_df.to_csv(output_file, index=False)
        print(f"\nDetailed results saved to: {output_file}")
        return
    
    # Single month or date range (original logic)
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
        parser.error("Either --month, --months, or both --start-date and --end-date must be provided")
    
    # Fetch deals
    print(f"Fetching closed deals created AND closed between {start_date} and {end_date}...")
    deals = fetch_closed_deals(start_date, end_date)
    print(f"Found {len(deals)} closed deals (created and closed in period)\n")
    
    # Analyze each deal
    print("Analyzing ICP Operador billing...")
    results = []
    for i, deal in enumerate(deals, 1):
        print(f"Processing {i}/{len(deals)}...", end='\r')
        result = analyze_deal(deal)
        results.append(result)
        time.sleep(0.1)
    
    df = pd.DataFrame(results)
    
    # VALIDATION: Check for deals without primary company
    deals_without_primary = df[~df['has_primary_company']]
    deals_with_primary = df[df['has_primary_company']]
    
    # Calculate summary statistics (only for deals WITH primary company for accuracy)
    total = len(df)
    total_with_primary = len(deals_with_primary)
    total_without_primary = len(deals_without_primary)
    
    icp_total = deals_with_primary['is_icp_operador'].sum()  # Now only uses primary company type
    non_icp = total_with_primary - icp_total
    
    # Informational: count deals with ICP Contador plan (for reference only)
    by_plan = df['is_accountant_by_plan'].sum()
    
    # Case 2: Accountant companies with non-ICP Contador plans (informational)
    case2 = len(df[(df['is_accountant_by_type'] == True) & (df['is_accountant_by_plan'] == False)])
    
    # Print summary
    print("\n" + "=" * 80)
    month_str = args.month if args.month else f"{start_date} to {end_date}"
    print(f"ICP OPERADOR BILLING ANALYSIS - {month_str}")
    print("=" * 80)
    print()
    print("## Summary")
    print()
    print("| Metric | Count | Percentage |")
    print("|--------|-------|------------|")
    print(f"| Total Closed Deals | {total} | 100.0% |")
    print(f"| Deals WITH Primary Company | {total_with_primary} | {total_with_primary/total*100:.1f}% |")
    print(f"| Deals WITHOUT Primary Company ⚠️ | {total_without_primary} | {total_without_primary/total*100:.1f}% |")
    print(f"| ICP Operador (Billed to Accountant) | {icp_total} | {icp_total/total_with_primary*100:.1f}% of deals with primary company |")
    print(f"| Non-ICP Operador (Billed to SMB) | {non_icp} | {non_icp/total_with_primary*100:.1f}% of deals with primary company |")
    print()
    print("**Method:** ICP Operador is determined by PRIMARY company type (Cuenta Contador, Cuenta Contador y Reseller, Contador Robado)")
    print()
    
    # VALIDATION REPORT: Deals without primary company
    if total_without_primary > 0:
        print("## ⚠️ VALIDATION ISSUES: Deals Without Primary Company")
        print()
        print(f"**{total_without_primary} deal(s) found without primary company association.**")
        print("These deals need attention - they cannot be classified for billing purposes.")
        print()
        print("| Deal Name | Deal ID | Plan | Created Date | Closed Date |")
        print("|-----------|---------|------|--------------|-------------|")
        for idx, row in deals_without_primary.iterrows():
            deal_name = row['deal_name']
            deal_id = row['deal_id']
            plan = row['plan_name'] if row['plan_name'] else '(No plan)'
            created = row['createdate'][:10] if row['createdate'] else 'N/A'
            closed = row['closedate'][:10] if row['closedate'] else 'N/A'
            print(f"| {deal_name} | {deal_id} | {plan} | {created} | {closed} |")
        print()
    
    # REPORT: Initial MQL Contact Information
    deals_without_initial_contact = df[~df['has_initial_contact']]
    total_without_initial_contact = len(deals_without_initial_contact)
    total_with_initial_contact = df['has_initial_contact'].sum()
    
    # Count by method used
    type_id_14_count = len(df[df['initial_contact_method'] == 'Type_ID_14'])
    earliest_created_count = len(df[df['initial_contact_method'] == 'Earliest_Created'])
    
    print("## Initial MQL Contact Information")
    print()
    print(f"**Initial contact identification uses two strategies:**")
    print(f"1. Strategy 1 (Preferred): Type ID 14 association ('Contacto Inicial')")
    print(f"2. Strategy 2 (Fallback): Earliest created contact (excluding 'Usuario Invitado')")
    print()
    print("| Metric | Count | Percentage |")
    print("|--------|-------|------------|")
    print(f"| Deals WITH Initial Contact Identified | {total_with_initial_contact} | {total_with_initial_contact/total*100:.1f}% |")
    print(f"| Deals WITHOUT Initial Contact | {total_without_initial_contact} | {total_without_initial_contact/total*100:.1f}% |")
    print()
    if total_with_initial_contact > 0:
        print("| Identification Method | Count | Percentage of deals with contact |")
        print("|----------------------|-------|-----------------------------------|")
        print(f"| Type ID 14 (Preferred) | {type_id_14_count} | {type_id_14_count/total_with_initial_contact*100:.1f}% |")
        print(f"| Earliest Created (Fallback) | {earliest_created_count} | {earliest_created_count/total_with_initial_contact*100:.1f}% |")
        print()
    
    if total_without_initial_contact > 0:
        print("**⚠️ Note:** Deals without initial contact either:")
        print("  - Have no associated contacts, OR")
        print("  - All associated contacts are 'Usuario Invitado' (team invitations, not MQLs)")
        print()
        print("**Exception Case:** Cross-selling/additional product deals may only have 'Usuario Invitado' contacts")
        print("because the original MQL contact may not be associated with the additional product deal.")
        print("This is expected behavior for cross-selling deals.")
        print()
        
        # Show which deal(s) don't have initial contact
        print("Deal(s) without initial contact:")
        print("| Deal Name | Deal ID | Reason |")
        print("|----------|---------|--------|")
        for idx, row in deals_without_initial_contact.iterrows():
            deal_name = row['deal_name']
            deal_id = row['deal_id']
            # Check if it's a cross-selling deal
            if 'Cross Selling' in deal_name or 'cross' in deal_name.lower():
                reason = "Cross-selling deal - only 'Usuario Invitado' contacts"
            else:
                reason = "No MQL contacts associated"
            print(f"| {deal_name} | {deal_id} | {reason} |")
        print()
    
    # REPORT: rol_wizard field statistics
    deals_with_rol_wizard = df[df['initial_contact_rol_wizard'].notna() & (df['initial_contact_rol_wizard'] != '')]
    total_with_rol_wizard = len(deals_with_rol_wizard)
    total_without_rol_wizard = total_with_initial_contact - total_with_rol_wizard
    
    if total_with_initial_contact > 0:
        print("## Initial Contact Role (rol_wizard) Distribution")
        print()
        print("| Metric | Count | Percentage of Total Deals |")
        print("|--------|-------|---------------------------|")
        print(f"| Contacts with 'rol_wizard' populated | {total_with_rol_wizard} | {total_with_rol_wizard/total*100:.1f}% |")
        print(f"| Contacts without 'rol_wizard' | {total_without_rol_wizard} | {total_without_rol_wizard/total*100:.1f}% |")
        print()
        
        if total_with_rol_wizard > 0:
            from collections import Counter
            role_counts = Counter(deals_with_rol_wizard['initial_contact_rol_wizard'])
            print("### rol_wizard Role Distribution")
            print()
            print("| Role | Count | % of Total Deals | % of Deals with rol_wizard |")
            print("|------|-------|------------------|----------------------------|")
            # Sort by count descending
            for role, count in role_counts.most_common():
                pct_total = (count / total) * 100
                pct_with_role = (count / total_with_rol_wizard) * 100
                print(f"| {role} | {count} | {pct_total:.1f}% | {pct_with_role:.1f}% |")
            print()
    
    print("## Additional Information")
    print()
    print("| Metric | Count | Notes |")
    print("|--------|-------|-------|")
    print(f"| Deals with 'ICP Contador' plan name | {by_plan} | Informational only - not used for classification |")
    print(f"| Accountant companies with non-ICP Contador plan | {case2} | Accountant company but plan name doesn't contain 'ICP Contador' |")
    
    # Save to CSV
    output_dir = "tools/outputs"
    os.makedirs(output_dir, exist_ok=True)
    output_file = f"{output_dir}/icp_operador_analysis_{start_date.replace('-', '')}_{end_date.replace('-', '')}.csv"
    df.to_csv(output_file, index=False)
    print()
    print(f"Detailed results saved to: {output_file}")

if __name__ == "__main__":
    main()

