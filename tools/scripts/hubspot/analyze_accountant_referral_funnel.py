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
ACCOUNTANT REFERRAL FUNNEL ANALYSIS
===================================

Validates the referral funnel for deals referred by accountants.
This funnel filters deals that meet BOTH criteria:
1. lead_source = 'Referencia Externa Contador' (internal name in HubSpot)
2. Deal has accountant association (association type 8: "Estudio Contable / Asesor / Consultor Externo del negocio")

BUSINESS LOGIC ASSUMPTION:
- If a deal has lead_source = 'Referencia Externa Contador' AND has an accountant association (type 8),
  we infer that the accountant referred the deal.
- While association type 8 technically means "accountant involvement" (not necessarily referral),
  salespeople use type 8 correctly and consistently.
- Association type 2 (referrer) is NOT reliably used by salespeople, so we cannot depend on it.

FUNNEL LOGIC:
=============

STEP 1: Fetch Deals with Referral Criteria
-------------------------------------------
- Filter: lead_source = 'Referencia Externa Contador' (internal name in HubSpot)
- AND: Deal has accountant association (type 8: "Estudio Contable / Asesor / Consultor Externo del negocio")
- Period: Deals CREATED in the date range
- Note: We use type 8 (accountant involvement) as a proxy for referral, since salespeople use it correctly

STEP 2: Track Funnel Stages
----------------------------
- Deal Created: Count of deals meeting criteria (created in period)
- Deal Closed Won: Deals that closed won in period (both createdate and closedate in period)

STEP 3: Identify Accountant Referrers
--------------------------------------
- For each deal, identify which accountant company(ies) are associated (type 8)
- We infer these accountants referred the deal (business logic assumption)
- This shows "who referred to whom" based on accountant associations

STEP 4: Classify by ICP
------------------------
- ICP Operador: PRIMARY company type IN ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']
- ICP PYME: All other deals

STEP 5: Calculate Metrics
--------------------------
- Conversion Rate: Closed Won / Deal Created
- Revenue: Total, ICP Operador, ICP PYME
- Average Deal Size

Usage:
  python analyze_accountant_referral_funnel.py --month 2025-12
  python analyze_accountant_referral_funnel.py --months 2025-11 2025-12
  python analyze_accountant_referral_funnel.py --start-date 2025-12-01 --end-date 2026-01-01
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

# Lead source value we're filtering for
# Note: Internal name in HubSpot is "Referencia Externa Contador" (not "Referencia Externa Directa")
REFERRAL_LEAD_SOURCE = 'Referencia Externa Contador'

# Accountant association type ID
ACCOUNTANT_ASSOCIATION_TYPE_ID = 8

# Note: We do NOT use association type 2 (referrer) because salespeople don't use it reliably.
# Instead, we use type 8 (accountant involvement) as a proxy for referral.

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
    
    Returns:
        (has_association, company_count, company_ids)
    """
    company_ids = get_deal_companies_with_association_type(deal_id, ACCOUNTANT_ASSOCIATION_TYPE_ID)
    return len(company_ids) > 0, len(company_ids), company_ids

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


def analyze_referral_funnel(start_date, end_date):
    """
    Analyze the referral funnel for deals referred by accountants.
    
    FUNNEL LOGIC:
    ============
    1. Fetch all deals created in period where:
       - lead_source = 'Referencia Externa Contador' (internal name in HubSpot)
       - AND deal has accountant association (type 8)
    2. Track: Deal Created → Deal Closed Won
    3. Identify accountant companies associated (type 8) - we infer they referred the deal
    4. Classify by ICP Operador vs ICP PYME
    5. Calculate revenue
    """
    # Validate date range
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    print(f"\n{'='*80}")
    print(f"ACCOUNTANT REFERRAL FUNNEL ANALYSIS")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    print("FILTERING CRITERIA:")
    print(f"1. lead_source = '{REFERRAL_LEAD_SOURCE}'")
    print(f"2. Deal has accountant association (type {ACCOUNTANT_ASSOCIATION_TYPE_ID}: 'Estudio Contable / Asesor / Consultor Externo del negocio')")
    print()
    print("BUSINESS LOGIC ASSUMPTION:")
    print("If a deal has lead_source = 'Referencia Externa Contador' AND has an accountant")
    print("association (type 8), we infer that the accountant referred the deal.")
    print()
    print("Note: Association type 2 (referrer) is NOT used because salespeople don't use")
    print("it reliably. Instead, we use type 8 (accountant involvement) as a proxy.")
    print()
    
    # ========================================================================
    # STEP 1: Fetch Deals with Referral Criteria
    # ========================================================================
    print("📊 STEP 1: Fetching deals with referral criteria...")
    print(f"   Filtering: lead_source = '{REFERRAL_LEAD_SOURCE}'")
    print(f"   AND: Deal has accountant association (type {ACCOUNTANT_ASSOCIATION_TYPE_ID})")
    print(f"   Period: Deals CREATED between {start_date} and {end_date}")
    print()
    
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    
    # First, fetch all deals with the lead source
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
            "properties": ["dealname", "createdate", "closedate", "dealstage", "amount", "lead_source", "primary_company_type"],
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
    
    print(f"   Found {len(all_deals_with_source)} deals with lead_source = '{REFERRAL_LEAD_SOURCE}'")
    print("   Checking which deals have accountant association (type 8)...")
    
    # Check each deal for accountant association
    deals_with_accountant = []
    deal_id_to_accountants = {}
    deal_id_to_deal = {deal.get('id'): deal for deal in all_deals_with_source}
    
    for i, deal in enumerate(all_deals_with_source, 1):
        if i % 50 == 0:
            print(f"      Checking deal {i}/{len(all_deals_with_source)}...")
        deal_id = deal.get('id')
        has_assoc, company_count, company_ids = has_accountant_company_association(deal_id)
        if has_assoc:
            deals_with_accountant.append(deal_id)
            # Fetch accountant company details
            accountant_companies = []
            for company_id in company_ids:
                company_name, company_type = get_company_details(company_id)
                accountant_companies.append({
                    'company_id': company_id,
                    'company_name': company_name or 'N/A',
                    'company_type': company_type or 'N/A'
                })
            deal_id_to_accountants[deal_id] = accountant_companies
        time.sleep(0.05)  # Rate limiting
    
    print(f"   Found {len(deals_with_accountant)} deals with BOTH criteria (lead_source + accountant association)")
    print(f"   Excluded {len(all_deals_with_source) - len(deals_with_accountant)} deals without accountant association")
    print()
    
    if len(deals_with_accountant) == 0:
        print("⚠️  No deals found matching both criteria in this period.")
        return None
    
    # Get deal details for deals with accountant association
    deals_meeting_criteria = [deal_id_to_deal[deal_id] for deal_id in deals_with_accountant if deal_id in deal_id_to_deal]
    
    # ========================================================================
    # STEP 2: Track Funnel Stages
    # ========================================================================
    print("📊 STEP 2: Tracking funnel stages...")
    
    deal_created_count = len(deals_meeting_criteria)
    
    # Filter for closed won deals (both createdate and closedate in period)
    closed_won_deals = []
    for deal in deals_meeting_criteria:
        props = deal.get('properties', {})
        dealstage = props.get('dealstage', '')
        createdate = props.get('createdate', '')
        closedate = props.get('closedate', '')
        
        if dealstage == 'closedwon':
            # Parse dates
            try:
                if createdate:
                    created_dt = datetime.fromisoformat(createdate.replace('Z', '+00:00'))
                else:
                    continue
                
                if closedate:
                    closed_dt = datetime.fromisoformat(closedate.replace('Z', '+00:00'))
                    # Check if both dates are in period
                    if start_dt <= created_dt < end_dt and start_dt <= closed_dt < end_dt:
                        closed_won_deals.append(deal)
            except:
                continue
    
    closed_won_count = len(closed_won_deals)
    print(f"   Deal Created: {deal_created_count}")
    print(f"   Deal Closed Won: {closed_won_count}")
    print()
    
    # ========================================================================
    # STEP 3: Identify Accountant Referrers (from Type 8)
    # ========================================================================
    print("📊 STEP 3: Identifying accountant referrers...")
    print("   Using accountant companies (type 8) - we infer these accountants referred the deal.")
    print()
    
    # Count unique accountant companies
    unique_accountant_companies = set()
    for deal_id in deals_with_accountant:
        accountants = deal_id_to_accountants.get(deal_id, [])
        for acc in accountants:
            unique_accountant_companies.add(acc['company_id'])
    
    print(f"   Unique accountant companies (inferred referrers): {len(unique_accountant_companies)}")
    
    # Calculate average accountant companies per deal
    total_accountant_associations = sum(len(deal_id_to_accountants.get(deal_id, [])) for deal_id in deals_with_accountant)
    avg_accountants_per_deal = total_accountant_associations / len(deals_with_accountant) if deals_with_accountant else 0
    print(f"   Average accountant companies per deal: {avg_accountants_per_deal:.2f}")
    print()
    
    # Show top referring accountants
    accountant_referral_count = {}
    for deal_id in deals_with_accountant:
        accountants = deal_id_to_accountants.get(deal_id, [])
        for acc in accountants:
            company_id = acc['company_id']
            if company_id not in accountant_referral_count:
                accountant_referral_count[company_id] = {
                    'count': 0,
                    'name': acc['company_name'],
                    'type': acc['company_type']
                }
            accountant_referral_count[company_id]['count'] += 1
    
    # Sort by count
    sorted_accountants = sorted(accountant_referral_count.items(), key=lambda x: x[1]['count'], reverse=True)
    
    print("   Top 10 accountant companies (inferred referrers):")
    for i, (company_id, info) in enumerate(sorted_accountants[:10], 1):
        print(f"      {i}. {info['name']} (Type: {info['type']}) - {info['count']} referral(s)")
    if len(sorted_accountants) > 10:
        print(f"      ... and {len(sorted_accountants) - 10} more")
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
    deal_to_won_rate = (closed_won_count / deal_created_count * 100) if deal_created_count > 0 else 0
    
    # ========================================================================
    # Print Results
    # ========================================================================
    print("="*80)
    print("FUNNEL RESULTS")
    print("="*80)
    print()
    print("**FILTERING CRITERIA:**")
    print(f"1. lead_source = '{REFERRAL_LEAD_SOURCE}'")
    print(f"2. Deal has accountant association (type {ACCOUNTANT_ASSOCIATION_TYPE_ID}: 'Estudio Contable / Asesor / Consultor Externo del negocio')")
    print()
    print("**BUSINESS LOGIC:** We infer that the accountant (type 8) referred the deal")
    print("when both criteria are met, even though type 8 technically means 'involvement'.")
    print()
    print("**FUNNEL PATH:** Deal Created → Deal Closed Won")
    print()
    print("| Stage | Count | Conversion Rate |")
    print("|-------|-------|-----------------|")
    print(f"| Deal Created | {deal_created_count} | - |")
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
    print(f"| **Total** | **{closed_won_count}** | **100.0%** | **${total_revenue:,.2f}** |")
    print()
    print("**Note:** ICP Operador classification is based on PRIMARY company type:")
    print(f"  - {', '.join(ACCOUNTANT_COMPANY_TYPES)}")
    print()
    
    # ========================================================================
    # Accountant Referrer Summary
    # ========================================================================
    print("="*80)
    print("ACCOUNTANT REFERRER SUMMARY")
    print("="*80)
    print()
    print(f"**Total Unique Accountant Companies (Inferred Referrers):** {len(unique_accountant_companies)}")
    print(f"**Total Deals with Accountant Association:** {len(deals_with_accountant)}")
    print()
    print("**Note:** We infer these accountants referred the deal based on:")
    print("  - lead_source = 'Referencia Externa Contador' (internal name in HubSpot)")
    print("  - AND accountant association (type 8)")
    print()
    
    # Prepare results dictionary
    results = {
        'deal_created_count': deal_created_count,
        'closed_won_count': closed_won_count,
        'deal_to_won_rate': deal_to_won_rate,
        'icp_operador_count': len(icp_operador_deals),
        'icp_pyme_count': len(icp_pyme_deals),
        'icp_operador_revenue': icp_operador_revenue,
        'icp_pyme_revenue': icp_pyme_revenue,
        'total_revenue': total_revenue,
        'average_deal_size': average_deal_size,
        'unique_accountant_companies': len(unique_accountant_companies),
        'average_time_to_close': avg_time_to_close,
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
        'Average_Deal_Size': [round(average_deal_size, 2)],
        'Unique_Accountant_Companies': [len(unique_accountant_companies)],
        'Average_Time_to_Close_Days': [round(avg_time_to_close, 2) if avg_time_to_close else None],
    }
    
    df = pd.DataFrame(df_data)
    
    # Generate filename with date range
    start_date_clean = start_date.replace('-', '')
    end_date_clean = end_date.replace('-', '')
    output_file = f"{output_dir}/accountant_referral_funnel_{start_date_clean}_{end_date_clean}.csv"
    
    df.to_csv(output_file, index=False)
    print(f"📄 Results saved to CSV: {output_file}")
    print()
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Analyze Accountant Referral Funnel')
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
            
            result = analyze_referral_funnel(start_date, end_date)
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
            print("**FILTERING CRITERIA:**")
            print(f"1. lead_source = '{REFERRAL_LEAD_SOURCE}'")
            print(f"2. Deal has accountant association (type {ACCOUNTANT_ASSOCIATION_TYPE_ID})")
            print()
            print("**FUNNEL PATH:** Deal Created → Deal Closed Won")
            print()
            print("| Month | Deal Created | Deal Closed Won | Deal→Won | ICP Operador | ICP PYME | Total Revenue |")
            print("|-------|--------------|-----------------|----------|--------------|----------|---------------|")
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
                'Average_Deal_Size': [round(r.get('average_deal_size', 0), 2) for r in all_results],
                'Unique_Accountant_Referrers': [r.get('unique_accountant_referrers', 0) for r in all_results],
                'Average_Time_to_Close_Days': [round(r.get('average_time_to_close', 0), 2) if r.get('average_time_to_close') else None for r in all_results],
            }
            
            df = pd.DataFrame(df_data)
            
            # Generate filename with month range
            months_str = "_".join([m.replace('-', '') for m in args.months])
            output_file = f"{output_dir}/accountant_referral_funnel_{months_str}.csv"
            
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
        parser.error("Must specify either --month, --months, or --start-date/--end-date")
    
    analyze_referral_funnel(start_date, end_date)

if __name__ == '__main__':
    main()
