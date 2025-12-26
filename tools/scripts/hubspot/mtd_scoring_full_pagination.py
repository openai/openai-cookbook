#!/usr/bin/env python3
"""
MONTH-TO-DATE SCORING ANALYSIS (fit_score_contador ONLY)
=========================================================
Recalculates scoring analysis using ONLY fit_score_contador field
for November 1-18 vs December 1-18, 2025 (month-to-date) comparison.

Scoring Field: fit_score_contador (ONLY - no fallback)

CRITICAL: Automatically finds and loads ALL pages to ensure 100% coverage

IMPORTANT EXCLUSIONS:
- Contacts with lead_source = "Usuario Invitado" are EXCLUDED from analysis
  (These are internal users invited to Colppy and should not be counted)
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import sys
import os
import glob
import requests
import argparse
from dotenv import load_dotenv

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

def get_score(contact):
    """Extract scoring value using ONLY fit_score_contador"""
    props = contact.get('properties', {})
    score = props.get('fit_score_contador')
    
    if score and score != '':
        try:
            return float(score)
        except:
            pass
    
    return None

def find_all_pages_for_period(period_start, period_end):
    """Automatically find all JSON files for a given period"""
    agent_tools_dir = '/Users/virulana/.cursor/projects/Users-virulana-colppy-app-code-code-workspace/agent-tools/'
    all_files = glob.glob(os.path.join(agent_tools_dir, '*.txt'))
    
    period_files = []
    for file_path in all_files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                if data.get('results'):
                    # Check first contact's createdate
                    first_result = data['results'][0]
                    createdate = first_result.get('properties', {}).get('createdate', '')
                    if createdate.startswith(period_start[:7]):  # Match YYYY-MM
                        period_files.append(file_path)
        except:
            pass
    
    return period_files

def fetch_contacts_from_api(start_date, end_date):
    """
    Fetch contacts from HubSpot API if files don't exist
    
    EXCLUDES: Contacts with lead_source = "Usuario Invitado" (internal invited users)
    """
    print(f"📥 Fetching contacts from HubSpot API for {start_date} to {end_date}...")
    print("   ⚠️  Excluding 'Usuario Invitado' contacts (internal invited users)")
    
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    # Properties needed for scoring analysis
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
                    
            print(f"✅ Fetched {len(all_contacts)} contacts from HubSpot API (excluding 'Usuario Invitado')")
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
    
    print(f"✅ Fetched {len(all_contacts)} contacts from HubSpot API (excluding 'Usuario Invitado')")
    return all_contacts

def analyze_period(contacts, period_name, period_start_date, period_end_date):
    """Analyze contacts for a given period"""
    print(f"\n{'='*100}")
    print(f"ANALYZING: {period_name}")
    print(f"{'='*100}")
    
    period_start = parse_datetime(f"{period_start_date}T00:00:00.000Z")
    period_end = parse_datetime(f"{period_end_date}T23:59:59.999Z")
    
    # Process contacts
    processed = []
    for contact in contacts:
        props = contact.get('properties', {})
        
        createdate = parse_datetime(props.get('createdate'))
        sql_date = parse_datetime(props.get('hs_v2_date_entered_opportunity'))
        pql_date = parse_datetime(props.get('fecha_activo'))
        is_pql = props.get('activo') == 'true'
        
        # IMPORTANT: Count based on CREATION DATE only
        # - All metrics are based on when the contact was CREATED, not when conversions happened
        # - If a contact was created in October and converted to SQL in November, it counts as October SQL
        # - This gives a true picture of lead quality by creation period
        
        # Step 1: Filter by creation date (must be in period)
        # This is the PRIMARY filter - everything is based on creation date
        if not createdate or not (period_start <= createdate <= period_end):
            continue
        
        # Step 2: Check if contact converted to SQL (regardless of when conversion happened)
        # SQL Definition: Contact has hs_v2_date_entered_opportunity populated
        # Count SQL if contact was CREATED in period, even if conversion happened later
        is_sql = False
        if sql_date:  # SQL conversion happened (anytime, as long as contact was created in period)
            is_sql = True
        
        # Step 3: Check if contact converted to PQL (regardless of when conversion happened)
        # PQL Definition: activo='true' AND fecha_activo populated
        # Count PQL if contact was CREATED in period, even if activation happened later
        is_pql_in_period = False
        if is_pql and pql_date:  # PQL conversion happened (anytime, as long as contact was created in period)
            is_pql_in_period = True
        
        # Step 4: Include ALL contacts created in period (for conversion rate calculation)
        # Conversion rate = (contacts that converted, regardless of when) / (all contacts created in period)
        # - Total Contacts Created = Count where createdate in target period (denominator)
        # - SQL/PQL Conversions = Contacts created in period that eventually converted (numerator)
        #   Note: Conversion may have happened in the same period or later
        
        score = get_score(contact)
        
        # Calculate cycle times (for all contacts that converted, regardless of when)
        sql_cycle_days = None
        if is_sql and sql_date and createdate:
            sql_cycle_days = (sql_date - createdate).total_seconds() / 86400
        
        pql_cycle_days = None
        if is_pql_in_period and pql_date and createdate:
            pql_cycle_days = (pql_date - createdate).total_seconds() / 86400
        
        processed.append({
            'email': props.get('email'),
            'createdate': createdate,
            'score': score,
            'is_sql': is_sql,
            'is_pql': is_pql_in_period,
            'sql_date': sql_date,
            'pql_date': pql_date,
            'sql_cycle_days': sql_cycle_days,
            'pql_cycle_days': pql_cycle_days
        })
    
    df = pd.DataFrame(processed)
    
    # Handle empty dataframe
    if len(df) == 0:
        print(f"\n⚠️  No contacts found for this period")
        # Return empty results with proper structure
        empty_results = pd.DataFrame(columns=['score_range', 'total_leads', 'sql_count', 'sql_rate', 'pql_count', 'pql_rate', 'avg_sql_cycle_days', 'avg_pql_cycle_days'])
        return empty_results, df, df
    
    # Calculate total conversions (ALL contacts, with or without score)
    total_sql = df['is_sql'].sum() if 'is_sql' in df.columns else 0
    total_pql = df['is_pql'].sum() if 'is_pql' in df.columns else 0
    
    # Filter out contacts without scores for scoring analysis
    df_scored = df[df['score'].notna()].copy()
    
    print(f"\n📊 Total contacts created in period: {len(df)}")
    if len(df) > 0:
        print(f"📊 Contacts with score: {len(df_scored)} ({len(df_scored)/len(df)*100:.1f}%)")
    else:
        print(f"📊 Contacts with score: 0 (0.0%)")
    print(f"📊 SQL conversions (created in period, conversion may be later): {total_sql}")
    print(f"📊 PQL conversions (created in period, activation may be later): {total_pql}")
    if len(df) > 0:
        print(f"📊 Overall SQL conversion rate: {total_sql/len(df)*100:.2f}%")
        print(f"📊 Overall PQL conversion rate: {total_pql/len(df)*100:.2f}%")
    else:
        print(f"📊 Overall SQL conversion rate: 0.00%")
        print(f"📊 Overall PQL conversion rate: 0.00%")
    
    # Score ranges
    def categorize_score(score):
        if pd.isna(score):
            return 'No Score'
        elif score >= 40:
            return '40+'
        elif score >= 30:
            return '30-39'
        elif score >= 20:
            return '20-29'
        elif score >= 10:
            return '10-19'
        else:
            return '0-9'
    
    df_scored['score_range'] = df_scored['score'].apply(categorize_score)
    
    # Aggregate by score range
    # IMPORTANT: Conversion rate = (converted in period) / (all created in period)
    results = []
    for range_name in ['40+', '30-39', '20-29', '10-19', '0-9']:
        range_df = df_scored[df_scored['score_range'] == range_name]
        
        if len(range_df) == 0:
            continue
        
        # Total = ALL contacts created in period (with this score range)
        total = len(range_df)
        # Count = contacts that converted (SQL or PQL) - conversion may have happened later
        sql_count = range_df['is_sql'].sum()
        pql_count = range_df['is_pql'].sum()
        # Conversion rate = (contacts that eventually converted) / (total created in period)
        sql_rate = (sql_count / total * 100) if total > 0 else 0
        pql_rate = (pql_count / total * 100) if total > 0 else 0
        
        # Cycle times
        sql_cycles = range_df[range_df['is_sql']]['sql_cycle_days'].dropna()
        pql_cycles = range_df[range_df['is_pql']]['pql_cycle_days'].dropna()
        
        avg_sql_cycle = sql_cycles.mean() if len(sql_cycles) > 0 else None
        avg_pql_cycle = pql_cycles.mean() if len(pql_cycles) > 0 else None
        
        results.append({
            'score_range': range_name,
            'total_leads': total,
            'sql_count': sql_count,
            'sql_rate': sql_rate,
            'pql_count': pql_count,
            'pql_rate': pql_rate,
            'avg_sql_cycle_days': avg_sql_cycle,
            'avg_pql_cycle_days': avg_pql_cycle
        })
    
    return pd.DataFrame(results), df_scored, df

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Month-to-Date Scoring Analysis (fit_score_contador)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare two specific date ranges
  python mtd_scoring_full_pagination.py --period1-start 2025-11-01 --period1-end 2025-11-18 --period2-start 2025-12-01 --period2-end 2025-12-18
  
  # Compare two months (full months)
  python mtd_scoring_full_pagination.py --month1 2025-11 --month2 2025-12
  
  # Compare current month-to-date vs previous month-to-date
  python mtd_scoring_full_pagination.py --current-mtd
  
  # Compare specific month-to-date vs previous month-to-date
  python mtd_scoring_full_pagination.py --month-mtd 2025-12
        """
    )
    
    # Period 1 arguments
    parser.add_argument('--period1-start', help='Period 1 start date (YYYY-MM-DD)')
    parser.add_argument('--period1-end', help='Period 1 end date (YYYY-MM-DD)')
    
    # Period 2 arguments
    parser.add_argument('--period2-start', help='Period 2 start date (YYYY-MM-DD)')
    parser.add_argument('--period2-end', help='Period 2 end date (YYYY-MM-DD)')
    
    # Month-based arguments
    parser.add_argument('--month1', help='Period 1 month (YYYY-MM) - uses full month')
    parser.add_argument('--month2', help='Period 2 month (YYYY-MM) - uses full month')
    
    # Convenience arguments
    parser.add_argument('--current-mtd', action='store_true', 
                       help='Compare current month-to-date vs previous month-to-date')
    parser.add_argument('--month-mtd', help='Compare specified month-to-date vs previous month-to-date (YYYY-MM)')
    
    return parser.parse_args()

def get_month_dates(month_str):
    """Convert YYYY-MM to start/end dates for full month"""
    year, month = map(int, month_str.split('-'))
    start_date = datetime(year, month, 1)
    
    # Get last day of month
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def get_month_to_date(month_str=None):
    """Get month-to-date dates. If month_str is None, use current month"""
    if month_str:
        year, month = map(int, month_str.split('-'))
        start_date = datetime(year, month, 1)
        end_date = datetime.now()
        # If the month is in the future, use last day of that month
        if end_date.year < year or (end_date.year == year and end_date.month < month):
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        # If we're in the same month, use today
        elif end_date.year == year and end_date.month == month:
            end_date = datetime.now()
        else:
            # Past month, use last day of that month
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    else:
        # Current month
        today = datetime.now()
        start_date = datetime(today.year, today.month, 1)
        end_date = today
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def get_previous_month_to_date(month_str=None):
    """Get previous month-to-date dates for comparison"""
    if month_str:
        year, month = map(int, month_str.split('-'))
        # Previous month
        if month == 1:
            prev_year = year - 1
            prev_month = 12
        else:
            prev_year = year
            prev_month = month - 1
        
        start_date = datetime(prev_year, prev_month, 1)
        # Use same day of month as current period end, or last day of previous month if that day doesn't exist
        if month_str:
            # Get the end date of the current period to match the day
            _, current_end = get_month_to_date(month_str)
            current_end_dt = datetime.strptime(current_end, '%Y-%m-%d')
            day_of_month = current_end_dt.day
            
            # Last day of previous month
            if prev_month == 12:
                last_day = (datetime(prev_year + 1, 1, 1) - timedelta(days=1)).day
            else:
                last_day = (datetime(prev_year, prev_month + 1, 1) - timedelta(days=1)).day
            
            end_day = min(day_of_month, last_day)
            end_date = datetime(prev_year, prev_month, end_day)
        else:
            end_date = datetime(prev_year, prev_month, min(datetime.now().day, 
                (datetime(prev_year, prev_month + 1, 1) - timedelta(days=1)).day if prev_month < 12 
                else (datetime(prev_year + 1, 1, 1) - timedelta(days=1)).day))
    else:
        # Current month - get previous month
        today = datetime.now()
        if today.month == 1:
            prev_year = today.year - 1
            prev_month = 12
        else:
            prev_year = today.year
            prev_month = today.month - 1
        
        start_date = datetime(prev_year, prev_month, 1)
        # Use same day of month, or last day of previous month
        last_day_prev = (datetime(prev_year, prev_month + 1, 1) - timedelta(days=1)).day if prev_month < 12 else (datetime(prev_year + 1, 1, 1) - timedelta(days=1)).day
        end_day = min(today.day, last_day_prev)
        end_date = datetime(prev_year, prev_month, end_day)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def load_contacts_for_period(start_date, end_date, period_label):
    """Load contacts for a given period from HubSpot API only"""
    # Always fetch from API to ensure accurate date filtering
    print(f"\n📥 Fetching {period_label} data from HubSpot API ({start_date} to {end_date})...")
    contacts = fetch_contacts_from_api(start_date, end_date)
    if len(contacts) > 0:
        print(f"✅ Total {period_label} contacts fetched from API: {len(contacts)}")
    else:
        print(f"⚠️  Could not fetch {period_label} data from API.")
    return contacts

# Main execution
if __name__ == "__main__":
    args = parse_arguments()
    
    # Determine period dates based on arguments
    period1_start = None
    period1_end = None
    period2_start = None
    period2_end = None
    period1_label = "PERIOD 1"
    period2_label = "PERIOD 2"
    
    if args.current_mtd:
        # Current month-to-date vs previous month-to-date
        period2_start, period2_end = get_month_to_date()
        period1_start, period1_end = get_previous_month_to_date()
        period1_label = f"{datetime.strptime(period1_start, '%Y-%m-%d').strftime('%B').upper()} {period1_start.split('-')[2]}-{period1_end.split('-')[2]}, {period1_start.split('-')[0]}"
        period2_label = f"{datetime.strptime(period2_start, '%Y-%m-%d').strftime('%B').upper()} {period2_start.split('-')[2]}-{period2_end.split('-')[2]}, {period2_start.split('-')[0]} (Month-to-Date)"
    elif args.month_mtd:
        # Specific month-to-date vs previous month-to-date
        period2_start, period2_end = get_month_to_date(args.month_mtd)
        period1_start, period1_end = get_previous_month_to_date(args.month_mtd)
        period1_label = f"{datetime.strptime(period1_start, '%Y-%m-%d').strftime('%B').upper()} {period1_start.split('-')[2]}-{period1_end.split('-')[2]}, {period1_start.split('-')[0]}"
        period2_label = f"{datetime.strptime(period2_start, '%Y-%m-%d').strftime('%B').upper()} {period2_start.split('-')[2]}-{period2_end.split('-')[2]}, {period2_start.split('-')[0]} (Month-to-Date)"
    elif args.month1 and args.month2:
        # Two full months
        period1_start, period1_end = get_month_dates(args.month1)
        period2_start, period2_end = get_month_dates(args.month2)
        period1_label = f"{datetime.strptime(period1_start, '%Y-%m-%d').strftime('%B').upper()} {period1_start.split('-')[0]}"
        period2_label = f"{datetime.strptime(period2_start, '%Y-%m-%d').strftime('%B').upper()} {period2_start.split('-')[0]}"
    elif args.period1_start and args.period1_end and args.period2_start and args.period2_end:
        # Two custom date ranges
        period1_start = args.period1_start
        period1_end = args.period1_end
        period2_start = args.period2_start
        period2_end = args.period2_end
        period1_label = f"{period1_start} to {period1_end}"
        period2_label = f"{period2_start} to {period2_end}"
    else:
        # Default: current month-to-date vs previous month-to-date
        period2_start, period2_end = get_month_to_date()
        period1_start, period1_end = get_previous_month_to_date()
        period1_label = f"{datetime.strptime(period1_start, '%Y-%m-%d').strftime('%B').upper()} {period1_start.split('-')[2]}-{period1_end.split('-')[2]}, {period1_start.split('-')[0]}"
        period2_label = f"{datetime.strptime(period2_start, '%Y-%m-%d').strftime('%B').upper()} {period2_start.split('-')[2]}-{period2_end.split('-')[2]}, {period2_start.split('-')[0]} (Month-to-Date)"
    
print("="*100)
print("MONTH-TO-DATE SCORING ANALYSIS (fit_score_contador ONLY)")
print(f"{period1_label} vs {period2_label}")
print("FULL PAGINATION - 100% COVERAGE")
print("="*100)

# Load contacts for both periods
period1_contacts = load_contacts_for_period(period1_start, period1_end, period1_label)
period2_contacts = load_contacts_for_period(period2_start, period2_end, period2_label)

# Prepare output directory
output_dir = "tools/outputs"
os.makedirs(output_dir, exist_ok=True)

# Analyze periods
period1_results, period1_df_scored, period1_df_all = analyze_period(period1_contacts, period1_label, period1_start, period1_end)
period2_results, period2_df_scored, period2_df_all = analyze_period(period2_contacts, period2_label, period2_start, period2_end)

# Scoring Distribution Analysis (regardless of conversions)
print("\n" + "="*100)
print("SCORING DISTRIBUTION ANALYSIS (All Contacts Created in Period)")
print("="*100)
    
def get_score_distribution(df_all, period_name):
    """Calculate score distribution for all contacts"""
    if len(df_all) == 0:
        return pd.DataFrame()
    
    def categorize_score(score):
        if pd.isna(score):
            return 'No Score'
        elif score >= 40:
            return '40+'
        elif score >= 30:
            return '30-39'
        elif score >= 20:
            return '20-29'
        elif score >= 10:
            return '10-19'
        else:
            return '0-9'
    
    df_all['score_range'] = df_all['score'].apply(categorize_score)
    
    distribution = []
    total = len(df_all)
    
    for range_name in ['40+', '30-39', '20-29', '10-19', '0-9', 'No Score']:
        range_df = df_all[df_all['score_range'] == range_name]
        count = len(range_df)
        percentage = (count / total * 100) if total > 0 else 0
        
        distribution.append({
            'score_range': range_name,
            'count': count,
            'percentage': percentage
        })
    
    return pd.DataFrame(distribution)

period1_dist = get_score_distribution(period1_df_all, period1_label)
period2_dist = get_score_distribution(period2_df_all, period2_label)

print(f"\n📊 {period1_label} - Score Distribution:")
print(f"{'Score Range':<12} │ {'Count':<8} │ {'Percentage':<12}")
print(f"{'─'*12}┼{'─'*8}┼{'─'*12}")
for _, row in period1_dist.iterrows():
    print(f"{row['score_range']:<12} │ {int(row['count']):<8} │ {row['percentage']:<11.2f}%")

print(f"\n📊 {period2_label} - Score Distribution:")
print(f"{'Score Range':<12} │ {'Count':<8} │ {'Percentage':<12}")
print(f"{'─'*12}┼{'─'*8}┼{'─'*12}")
for _, row in period2_dist.iterrows():
    print(f"{row['score_range']:<12} │ {int(row['count']):<8} │ {row['percentage']:<11.2f}%")

# Distribution Comparison
if len(period1_dist) > 0 and len(period2_dist) > 0:
    dist_comparison = period1_dist.merge(period2_dist, on='score_range', suffixes=('_p1', '_p2'), how='outer').fillna(0)
    
    print(f"\n📊 Score Distribution Comparison:")
    print(f"{'Score Range':<12} │ {'P1 Count':<10} │ {'P1 %':<8} │ {'P2 Count':<10} │ {'P2 %':<8} │ {'Δ Count':<10} │ {'Δ %':<8}")
    print(f"{'─'*12}┼{'─'*10}┼{'─'*8}┼{'─'*10}┼{'─'*8}┼{'─'*10}┼{'─'*8}")
    for _, row in dist_comparison.iterrows():
        p1_count = int(row.get('count_p1', 0))
        p2_count = int(row.get('count_p2', 0))
        p1_pct = row.get('percentage_p1', 0)
        p2_pct = row.get('percentage_p2', 0)
        delta_count = p2_count - p1_count
        delta_pct = p2_pct - p1_pct
        delta_count_str = f"{delta_count:+d}"
        delta_pct_str = f"{delta_pct:+.2f}%"
        print(f"{row['score_range']:<12} │ {p1_count:<10} │ {p1_pct:<7.2f}% │ {p2_count:<10} │ {p2_pct:<7.2f}% │ {delta_count_str:<10} │ {delta_pct_str:<8}")
    
    # Save distribution comparison
    period1_suffix = period1_start.replace('-', '_') + '_' + period1_start.replace('-', '_')
    period2_suffix = period2_start.replace('-', '_') + '_' + period2_end.replace('-', '_')
    dist_comparison.to_csv(os.path.join(output_dir, f'score_distribution_{period1_suffix}_vs_{period2_suffix}.csv'), index=False)
    print(f"\n✅ Score distribution saved to: tools/outputs/score_distribution_{period1_suffix}_vs_{period2_suffix}.csv")

# Display comparison tables
print("\n" + "="*100)
print("VOLUME & CONVERSION RATES BY SCORE RANGE")
print("="*100)

print(f"\n📊 {period1_label}:")
print(f"{'Score Range':<12} │ {'Total':<8} │ {'SQL':<6} │ {'SQL %':<8} │ {'PQL':<6} │ {'PQL %':<8}")
print(f"{'─'*12}┼{'─'*8}┼{'─'*6}┼{'─'*8}┼{'─'*6}┼{'─'*8}")
for _, row in period1_results.iterrows():
    print(f"{row['score_range']:<12} │ {int(row['total_leads']):<8} │ {int(row['sql_count']):<6} │ {row['sql_rate']:<7.1f}% │ {int(row['pql_count']):<6} │ {row['pql_rate']:<7.1f}%")

print(f"\n📊 {period2_label}:")
print(f"{'Score Range':<12} │ {'Total':<8} │ {'SQL':<6} │ {'SQL %':<8} │ {'PQL':<6} │ {'PQL %':<8}")
print(f"{'─'*12}┼{'─'*8}┼{'─'*6}┼{'─'*8}┼{'─'*6}┼{'─'*8}")
for _, row in period2_results.iterrows():
    print(f"{row['score_range']:<12} │ {int(row['total_leads']):<8} │ {int(row['sql_count']):<6} │ {row['sql_rate']:<7.1f}% │ {int(row['pql_count']):<6} │ {row['pql_rate']:<7.1f}%")

print("\n" + "="*100)
print("CYCLE TIME BY SCORE RANGE (Days from Creation to Conversion)")
print("="*100)

print(f"\n📊 {period1_label}:")
print(f"{'Score Range':<12} │ {'Avg SQL Cycle':<15} │ {'Avg PQL Cycle':<15}")
print(f"{'─'*12}┼{'─'*15}┼{'─'*15}")
for _, row in period1_results.iterrows():
    sql_cycle = f"{row['avg_sql_cycle_days']:.1f} days" if pd.notna(row['avg_sql_cycle_days']) else "N/A"
    pql_cycle = f"{row['avg_pql_cycle_days']:.1f} days" if pd.notna(row['avg_pql_cycle_days']) else "N/A"
    print(f"{row['score_range']:<12} │ {sql_cycle:<15} │ {pql_cycle:<15}")

print(f"\n📊 {period2_label}:")
print(f"{'Score Range':<12} │ {'Avg SQL Cycle':<15} │ {'Avg PQL Cycle':<15}")
print(f"{'─'*12}┼{'─'*15}┼{'─'*15}")
for _, row in period2_results.iterrows():
    sql_cycle = f"{row['avg_sql_cycle_days']:.1f} days" if pd.notna(row['avg_sql_cycle_days']) else "N/A"
    pql_cycle = f"{row['avg_pql_cycle_days']:.1f} days" if pd.notna(row['avg_pql_cycle_days']) else "N/A"
    print(f"{row['score_range']:<12} │ {sql_cycle:<15} │ {pql_cycle:<15}")

# Prepare output directory
output_dir = "tools/outputs"
os.makedirs(output_dir, exist_ok=True)

# Comparison Analysis
print("\n" + "="*100)
print(f"PERIOD COMPARISON ({period1_label} vs {period2_label})")
print("="*100)

# Merge results for comparison
comparison_df = period1_results.merge(period2_results, on='score_range', suffixes=('_p1', '_p2'), how='outer').fillna(0)

print("\n📊 VOLUME & CONVERSION RATE COMPARISON:")
print(f"{'Score Range':<12} │ {'P1 Total':<10} │ {'P2 Total':<10} │ {'Change':<10} │ {'P1 SQL %':<10} │ {'P2 SQL %':<10} │ {'Δ SQL %':<10}")
print(f"{'─'*12}┼{'─'*10}┼{'─'*10}┼{'─'*10}┼{'─'*10}┼{'─'*10}┼{'─'*10}")
for _, row in comparison_df.iterrows():
    p1_total = int(row.get('total_leads_p1', 0))
    p2_total = int(row.get('total_leads_p2', 0))
    change = p2_total - p1_total
    change_pct = ((p2_total - p1_total) / p1_total * 100) if p1_total > 0 else 0
    change_str = f"{change:+d} ({change_pct:+.1f}%)"
    
    p1_sql_rate = row.get('sql_rate_p1', 0)
    p2_sql_rate = row.get('sql_rate_p2', 0)
    delta_sql = p2_sql_rate - p1_sql_rate
    
    print(f"{row['score_range']:<12} │ {p1_total:<10} │ {p2_total:<10} │ {change_str:<10} │ {p1_sql_rate:<9.1f}% │ {p2_sql_rate:<9.1f}% │ {delta_sql:+.1f}%")

print("\n📊 PQL CONVERSION RATE COMPARISON:")
print(f"{'Score Range':<12} │ {'P1 PQL %':<10} │ {'P2 PQL %':<10} │ {'Δ PQL %':<10}")
print(f"{'─'*12}┼{'─'*10}┼{'─'*10}┼{'─'*10}")
for _, row in comparison_df.iterrows():
    p1_pql_rate = row.get('pql_rate_p1', 0)
    p2_pql_rate = row.get('pql_rate_p2', 0)
    delta_pql = p2_pql_rate - p1_pql_rate
    print(f"{row['score_range']:<12} │ {p1_pql_rate:<9.1f}% │ {p2_pql_rate:<9.1f}% │ {delta_pql:+.1f}%")

# Save comparison and results
period1_suffix = period1_start.replace('-', '_') + '_' + period1_end.replace('-', '_')
period2_suffix = period2_start.replace('-', '_') + '_' + period2_end.replace('-', '_')

comparison_df.to_csv(os.path.join(output_dir, f'comparison_scoring_{period1_suffix}_vs_{period2_suffix}.csv'), index=False)
period1_results.to_csv(os.path.join(output_dir, f'period1_scoring_{period1_suffix}.csv'), index=False)
period2_results.to_csv(os.path.join(output_dir, f'period2_scoring_{period2_suffix}.csv'), index=False)

print(f"\n✅ Results saved to tools/outputs/")
print(f"   - period1_scoring_{period1_suffix}.csv")
print(f"   - period2_scoring_{period2_suffix}.csv")
print(f"   - comparison_scoring_{period1_suffix}_vs_{period2_suffix}.csv")

