#!/usr/bin/env python3
"""
COMPLETE SQL CONVERSION ANALYSIS (July to Today)
================================================
Comprehensive SQL conversion analysis using the NEW SQL definition:
- Contact created in period (MQL - excluding 'Usuario Invitado')
- hs_v2_date_entered_opportunity falls within the period
- Contact has a deal associated that was created between createdate and SQL date (within the period)

Runs analysis for each month from July 2025 to current month and provides aggregated results.
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import sys
import os
import requests
import argparse
from dotenv import load_dotenv
from calendar import monthrange

# Add tools directory to path to import HubSpot API client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Load environment variables
load_dotenv()

# Try to use HubSpot API client if available
try:
    from hubspot_api.client import HubSpotClient, HubSpotAPIError
    HUBSPOT_CLIENT_AVAILABLE = True
except ImportError:
    HUBSPOT_CLIENT_AVAILABLE = False
    print("⚠️  HubSpot API client not available, using direct requests")

# HubSpot portal configuration for link generation
PORTAL_ID = "19877595"
UI_DOMAIN = "app.hubspot.com"

def generate_contact_link(contact_id):
    """Generate HubSpot contact link"""
    return f"https://{UI_DOMAIN}/contacts/{PORTAL_ID}/contact/{contact_id}"

def parse_datetime(date_str):
    """Parse HubSpot datetime string to datetime object"""
    if not date_str:
        return None
    try:
        if 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            return datetime.fromisoformat(date_str + "T00:00:00+00:00")
    except (ValueError, AttributeError):
        return None

def fetch_deal_associations(contact_id, api_key):
    """
    Fetch deal associations for a contact using reverse lookup.
    Returns list of deal IDs.
    """
    HUBSPOT_BASE_URL = 'https://api.hubapi.com'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    deal_ids = []
    
    # Try v4 API first
    try:
        url = f'{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/deals'
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if 'results' in result:
                deal_ids = [item['id'] for item in result['results']]
                return deal_ids
    except:
        pass
    
    # Fallback to v3 API
    try:
        url = f'{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}/associations/deals'
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if 'results' in result:
                deal_ids = [item['id'] for item in result['results']]
                return deal_ids
    except:
        pass
    
    return deal_ids

def fetch_deal_details(deal_ids, api_key):
    """
    Fetch deal details for a list of deal IDs.
    Returns dict mapping deal_id to deal properties.
    """
    if not deal_ids:
        return {}
    
    HUBSPOT_BASE_URL = 'https://api.hubapi.com'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    deals_data = {}
    
    # Batch read deals (up to 100 at a time)
    for i in range(0, len(deal_ids), 100):
        batch_ids = deal_ids[i:i+100]
        inputs = [{'id': deal_id} for deal_id in batch_ids]
        
        url = f'{HUBSPOT_BASE_URL}/crm/v3/objects/deals/batch/read'
        payload = {
            'properties': ['dealname', 'createdate', 'closedate', 'dealstage'],
            'inputs': inputs
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'results' in result:
                    for deal in result['results']:
                        deals_data[deal['id']] = deal.get('properties', {})
        except:
            pass
    
    return deals_data

def fetch_contacts_from_api(start_date, end_date):
    """
    Fetch contacts from HubSpot API
    
    EXCLUDES: Contacts with lead_source = "Usuario Invitado" (internal invited users)
    """
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    properties = [
        'email', 'firstname', 'lastname', 'createdate',
        'fit_score_contador',
        'hs_v2_date_entered_opportunity',  # SQL conversion date
        'activo',  # PQL boolean flag
        'fecha_activo',  # PQL activation timestamp
        'lifecyclestage',
        'lead_source'  # Used to exclude "Usuario Invitado" contacts
    ]
    
    all_contacts = []
    
    # Try using HubSpot API client first
    if HUBSPOT_CLIENT_AVAILABLE:
        try:
            client = HubSpotClient()
            after = None
            page = 0
            
            while True:
                page += 1
                try:
                    result = client.search_objects(
                        object_type="contacts",
                        filter_groups=[{
                            "filters": [{
                                "propertyName": "createdate",
                                "operator": "GTE",
                                "value": start_datetime
                            }, {
                                "propertyName": "createdate",
                                "operator": "LTE",
                                "value": end_datetime
                            }, {
                                "propertyName": "lead_source",
                                "operator": "NEQ",
                                "value": "Usuario Invitado"
                            }]
                        }],
                        properties=properties,
                        limit=100,
                        after=after
                    )
                    
                    contacts = result.get("results", [])
                    all_contacts.extend(contacts)
                    
                    if page % 5 == 0:
                        print(f"   📊 Fetched {len(all_contacts)} contacts so far...")
                    
                    if 'paging' not in result or 'next' not in result['paging']:
                        break
                    after = result['paging']['next']['after']
                    
                except HubSpotAPIError as e:
                    print(f"   ⚠️  HubSpot API error: {e}")
                    break
                    
            return all_contacts
            
        except Exception as e:
            print(f"   ⚠️  Error with HubSpot client: {e}")
            print("   Falling back to direct API requests...")
    
    # Fallback to direct requests
    api_key = os.getenv("HUBSPOT_API_KEY")
    if not api_key:
        print("⚠️  HUBSPOT_API_KEY not found. Cannot fetch data from API.")
        return []
    
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    after = None
    page = 0
    
    while True:
        page += 1
        payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "createdate",
                    "operator": "GTE",
                    "value": start_datetime
                }, {
                    "propertyName": "createdate",
                    "operator": "LTE",
                    "value": end_datetime
                }, {
                    "propertyName": "lead_source",
                    "operator": "NEQ",
                    "value": "Usuario Invitado"
                }]
            }],
            "properties": properties,
            "limit": 100
        }
        
        if after:
            payload["after"] = after
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            contacts = data.get("results", [])
            all_contacts.extend(contacts)
            
            if page % 5 == 0:
                print(f"   📊 Fetched {len(all_contacts)} contacts so far...")
            
            if 'paging' not in data or 'next' not in data['paging']:
                break
            after = data['paging']['next']['after']
            
        except Exception as e:
            print(f"   ⚠️  Error fetching contacts: {e}")
            break
    
    return all_contacts

def analyze_month(contacts, period_name, period_start_date, period_end_date):
    """
    Analyze contacts for a given month using NEW SQL definition with deal validation
    """
    period_start = parse_datetime(f"{period_start_date}T00:00:00.000Z")
    period_end = parse_datetime(f"{period_end_date}T23:59:59.999Z")
    
    # Get API key for deal lookups
    api_key = os.getenv("HUBSPOT_API_KEY")
    if not api_key:
        print("⚠️  HUBSPOT_API_KEY not found. Cannot check deal associations for SQL validation.")
        api_key = None
    
    # Step 1: First pass - identify SQL candidates and collect contact IDs
    sql_candidates = []
    for contact in contacts:
        props = contact.get('properties', {})
        createdate = parse_datetime(props.get('createdate'))
        sql_date = parse_datetime(props.get('hs_v2_date_entered_opportunity'))
        
        # Filter by creation date (must be in period) - MQL definition
        if not createdate or not (period_start <= createdate <= period_end):
            continue
        
        # Check if SQL conversion happened in the same period
        if sql_date and (period_start <= sql_date <= period_end):
            sql_candidates.append({
                'contact': contact,
                'contact_id': contact.get('id'),
                'createdate': createdate,
                'sql_date': sql_date
            })
    
    # Step 2: Fetch deal associations for SQL candidates
    contact_to_deals = {}
    all_deal_ids = set()
    
    if api_key and len(sql_candidates) > 0:
        for i, candidate in enumerate(sql_candidates):
            contact_id = candidate['contact_id']
            deal_ids = fetch_deal_associations(contact_id, api_key)
            contact_to_deals[contact_id] = deal_ids
            all_deal_ids.update(deal_ids)
            
            if (i + 1) % 10 == 0:
                print(f"   📊 Progress: {i + 1}/{len(sql_candidates)} contacts checked for deals...")
        
        # Step 3: Fetch deal details
        deals_data = fetch_deal_details(list(all_deal_ids), api_key)
    else:
        deals_data = {}
    
    # Step 4: Process all contacts and validate SQL definition
    processed = []
    sql_contacts = []
    
    for contact in contacts:
        props = contact.get('properties', {})
        
        createdate = parse_datetime(props.get('createdate'))
        sql_date = parse_datetime(props.get('hs_v2_date_entered_opportunity'))
        pql_date = parse_datetime(props.get('fecha_activo'))
        is_pql = props.get('activo') == 'true'
        
        # Filter by creation date (must be in period) - MQL definition
        if not createdate or not (period_start <= createdate <= period_end):
            continue
        
        # NEW SQL DEFINITION: SQL = An MQL that has a deal associated during the period
        is_sql = False
        
        # Check if SQL conversion happened in the same period
        if sql_date and (period_start <= sql_date <= period_end):
            contact_id = contact.get('id')
            deal_ids = contact_to_deals.get(contact_id, [])
            
            if len(deal_ids) > 0:
                # Check if any deal was created between contact creation and SQL date (within the period)
                for deal_id in deal_ids:
                    if deal_id in deals_data:
                        deal_created = parse_datetime(deals_data[deal_id].get('createdate'))
                        if deal_created:
                            # Deal must be created between contact creation and SQL date
                            # AND within the analysis period
                            if (createdate <= deal_created <= sql_date) and (period_start <= deal_created <= period_end):
                                is_sql = True
                                if contact_id:
                                    score_str = props.get('fit_score_contador')
                                    try:
                                        score = float(score_str) if score_str and score_str != '' else None
                                    except:
                                        score = None
                                    # Calculate SQL cycle time (createdate to sql_date)
                                    sql_cycle_days = None
                                    if createdate and sql_date:
                                        sql_cycle_days = (sql_date - createdate).total_seconds() / 86400
                                    
                                    sql_contacts.append({
                                        'contact_id': contact_id,
                                        'email': props.get('email'),
                                        'score': score,
                                        'createdate': createdate,
                                        'sql_date': sql_date,
                                        'deal_created': deal_created,
                                        'sql_cycle_days': sql_cycle_days
                                    })
                                break
        
        # Check PQL
        is_pql_in_period = False
        if is_pql and pql_date:
            is_pql_in_period = True
        
        processed.append({
            'createdate': createdate,
            'is_sql': is_sql,
            'is_pql': is_pql_in_period,
            'sql_date': sql_date,
            'pql_date': pql_date
        })
    
    df = pd.DataFrame(processed)
    
    if len(df) == 0:
        return {
            'month': period_name,
            'total_mqls': 0,
            'sql_count': 0,
            'sql_rate': 0.0,
            'pql_count': 0,
            'pql_rate': 0.0,
            'sql_contacts': []
        }
    
    total_mqls = len(df)
    sql_count = df['is_sql'].sum()
    pql_count = df['is_pql'].sum()
    sql_rate = (sql_count / total_mqls * 100) if total_mqls > 0 else 0
    pql_rate = (pql_count / total_mqls * 100) if total_mqls > 0 else 0
    
    # Calculate SQL cycle time statistics
    sql_cycle_times = [c['sql_cycle_days'] for c in sql_contacts if c.get('sql_cycle_days') is not None]
    avg_sql_cycle = sum(sql_cycle_times) / len(sql_cycle_times) if len(sql_cycle_times) > 0 else None
    median_sql_cycle = sorted(sql_cycle_times)[len(sql_cycle_times) // 2] if len(sql_cycle_times) > 0 else None
    min_sql_cycle = min(sql_cycle_times) if len(sql_cycle_times) > 0 else None
    max_sql_cycle = max(sql_cycle_times) if len(sql_cycle_times) > 0 else None
    
    return {
        'month': period_name,
        'total_mqls': total_mqls,
        'sql_count': sql_count,
        'sql_rate': sql_rate,
        'pql_count': pql_count,
        'pql_rate': pql_rate,
        'sql_contacts': sql_contacts,
        'avg_sql_cycle_days': avg_sql_cycle,
        'median_sql_cycle_days': median_sql_cycle,
        'min_sql_cycle_days': min_sql_cycle,
        'max_sql_cycle_days': max_sql_cycle
    }

def get_month_dates(year, month):
    """Get start and end dates for a given month"""
    start_date = datetime(year, month, 1)
    last_day = monthrange(year, month)[1]
    end_date = datetime(year, month, last_day)
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description='Complete SQL Conversion Analysis (July to Today)')
    parser.add_argument('--start-month', default='2025-07', help='Start month in YYYY-MM format (default: 2025-07)')
    parser.add_argument('--end-month', help='End month in YYYY-MM format (default: current month)')
    args = parser.parse_args()
    
    # Determine date range
    start_year, start_month = map(int, args.start_month.split('-'))
    
    if args.end_month:
        end_year, end_month = map(int, args.end_month.split('-'))
    else:
        today = datetime.now()
        end_year = today.year
        end_month = today.month
    
    print("="*100)
    print("COMPLETE SQL CONVERSION ANALYSIS")
    print(f"Period: {args.start_month} to {end_year}-{end_month:02d}")
    print("NEW SQL DEFINITION: MQL + SQL Date in Period + Deal Association Validation")
    print("="*100)
    
    all_results = []
    all_sql_contacts = []
    
    # Analyze each month
    current_year = start_year
    current_month = start_month
    
    while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
        month_str = f"{current_year}-{current_month:02d}"
        start_date, end_date = get_month_dates(current_year, current_month)
        
        print(f"\n{'='*100}")
        print(f"ANALYZING: {month_str}")
        print(f"{'='*100}")
        print(f"📥 Fetching contacts from HubSpot API ({start_date} to {end_date})...")
        
        contacts = fetch_contacts_from_api(start_date, end_date)
        print(f"✅ Fetched {len(contacts)} contacts")
        
        if len(contacts) > 0:
            print(f"📊 Analyzing SQL conversions with deal validation...")
            result = analyze_month(contacts, month_str, start_date, end_date)
            all_results.append(result)
            all_sql_contacts.extend(result['sql_contacts'])
        else:
            print(f"⚠️  No contacts found for this month")
            all_results.append({
                'month': month_str,
                'total_mqls': 0,
                'sql_count': 0,
                'sql_rate': 0.0,
                'pql_count': 0,
                'pql_rate': 0.0,
                'sql_contacts': []
            })
        
        # Move to next month
        current_month += 1
        if current_month > 12:
            current_month = 1
            current_year += 1
    
    # Display results
    print("\n" + "="*100)
    print("MONTHLY RESULTS SUMMARY")
    print("="*100)
    
    results_df = pd.DataFrame(all_results)
    
    print(f"\n{'Month':<12} │ {'MQLs':<8} │ {'SQLs':<8} │ {'SQL %':<10} │ {'Avg Cycle':<12} │ {'PQLs':<8} │ {'PQL %':<10}")
    print(f"{'─'*12}┼{'─'*8}┼{'─'*8}┼{'─'*10}┼{'─'*12}┼{'─'*8}┼{'─'*10}")
    
    for _, row in results_df.iterrows():
        avg_cycle = f"{row.get('avg_sql_cycle_days', 0):.1f}d" if pd.notna(row.get('avg_sql_cycle_days')) else "N/A"
        print(f"{row['month']:<12} │ {int(row['total_mqls']):<8} │ {int(row['sql_count']):<8} │ {row['sql_rate']:<9.2f}% │ {avg_cycle:<12} │ {int(row['pql_count']):<8} │ {row['pql_rate']:<9.2f}%")
    
    # Totals
    total_mqls = results_df['total_mqls'].sum()
    total_sqls = results_df['sql_count'].sum()
    total_pqls = results_df['pql_count'].sum()
    overall_sql_rate = (total_sqls / total_mqls * 100) if total_mqls > 0 else 0
    overall_pql_rate = (total_pqls / total_mqls * 100) if total_mqls > 0 else 0
    
    # Calculate overall average cycle time from all SQL contacts
    all_sql_cycles = []
    for result in all_results:
        for contact in result.get('sql_contacts', []):
            if contact.get('sql_cycle_days') is not None:
                all_sql_cycles.append(contact['sql_cycle_days'])
    overall_avg_cycle = sum(all_sql_cycles) / len(all_sql_cycles) if len(all_sql_cycles) > 0 else None
    overall_avg_cycle_str = f"{overall_avg_cycle:.1f}d" if overall_avg_cycle is not None else "N/A"
    
    print(f"{'─'*12}┼{'─'*8}┼{'─'*8}┼{'─'*10}┼{'─'*12}┼{'─'*8}┼{'─'*10}")
    print(f"{'TOTAL':<12} │ {int(total_mqls):<8} │ {int(total_sqls):<8} │ {overall_sql_rate:<9.2f}% │ {overall_avg_cycle_str:<12} │ {int(total_pqls):<8} │ {overall_pql_rate:<9.2f}%")
    
    # Save results
    output_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'outputs')
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_df.to_csv(os.path.join(output_dir, f'complete_sql_analysis_{args.start_month}_to_{end_year}-{end_month:02d}_{timestamp}.csv'), index=False)
    
    # Save SQL contacts with links
    if all_sql_contacts:
        sql_contacts_df = pd.DataFrame(all_sql_contacts)
        sql_contacts_df['hubspot_link'] = sql_contacts_df['contact_id'].apply(generate_contact_link)
        sql_contacts_df = sql_contacts_df.sort_values(['score', 'email'], ascending=[False, True], na_position='last')
        sql_contacts_df.to_csv(os.path.join(output_dir, f'complete_sql_contacts_{args.start_month}_to_{end_year}-{end_month:02d}_{timestamp}.csv'), index=False)
    
    print(f"\n✅ Results saved to outputs/")
    print(f"   - complete_sql_analysis_{args.start_month}_to_{end_year}-{end_month:02d}_{timestamp}.csv")
    if all_sql_contacts:
        print(f"   - complete_sql_contacts_{args.start_month}_to_{end_year}-{end_month:02d}_{timestamp}.csv")
    
    # Display SQL cycle time statistics
    if all_sql_contacts:
        sql_cycles = [c['sql_cycle_days'] for c in all_sql_contacts if c.get('sql_cycle_days') is not None]
        if len(sql_cycles) > 0:
            sorted_cycles = sorted(sql_cycles)
            median_idx = len(sorted_cycles) // 2
            median = sorted_cycles[median_idx] if len(sorted_cycles) % 2 == 1 else (sorted_cycles[median_idx - 1] + sorted_cycles[median_idx]) / 2
            print(f"\n📊 SQL Cycle Time Statistics:")
            print(f"   Average: {sum(sql_cycles) / len(sql_cycles):.2f} days")
            print(f"   Median: {median:.2f} days")
            print(f"   Min: {min(sql_cycles):.2f} days")
            print(f"   Max: {max(sql_cycles):.2f} days")
            same_day = sum(1 for c in sql_cycles if c < 1.0)
            days_1_2 = sum(1 for c in sql_cycles if 1.0 <= c < 2.0)
            days_2_plus = sum(1 for c in sql_cycles if c >= 2.0)
            print(f"   Same-day conversions (< 1 day): {same_day} ({same_day/len(sql_cycles)*100:.1f}%)")
            print(f"   1-2 days: {days_1_2} ({days_1_2/len(sql_cycles)*100:.1f}%)")
            print(f"   2+ days: {days_2_plus} ({days_2_plus/len(sql_cycles)*100:.1f}%)")
    
    print(f"\n📊 Summary:")
    print(f"   Total MQLs: {int(total_mqls)}")
    print(f"   Total SQLs: {int(total_sqls)} ({overall_sql_rate:.2f}%)")
    print(f"   Total PQLs: {int(total_pqls)} ({overall_pql_rate:.2f}%)")

if __name__ == "__main__":
    main()

