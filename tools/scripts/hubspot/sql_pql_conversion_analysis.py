#!/usr/bin/env python3
"""
SQL PQL CONVERSION ANALYSIS
===========================
Analyzes Sales Qualified Leads (SQL) to determine if they were Product Qualified Leads (PQL)
BEFORE converting to SQL (becoming an opportunity).

SQL Definition: Contact that converted from Lead to Opportunity WITH validated deal association
- Field: hs_v2_date_entered_opportunity (when contact entered 'Oportunidad' lifecycle stage)
- Validation: Contact must have a deal created between contact creation and SQL date (within the period)
- Complete Definition: SQL = MQL (contact created in period) + hs_v2_date_entered_opportunity in period + deal created between createdate and SQL date (within period)

PQL Definition: Contact that activated during trial
- Field: activo = 'true' (boolean flag)
- Field: fecha_activo (timestamp when activation occurred)

Analysis Goal: For contacts that became SQL in a given month, determine:
- How many were PQL BEFORE becoming SQL (fecha_activo < hs_v2_date_entered_opportunity)
- How many became PQL AFTER becoming SQL (fecha_activo >= hs_v2_date_entered_opportunity)
- How many were never PQL (activo != 'true' or fecha_activo is null)

SQL Conversion Cohort Definition: Contacts CREATED in the period that ALSO converted to SQL in the same period WITH validated deal association
- BOTH createdate AND hs_v2_date_entered_opportunity must be within the date range
- Contact must have a deal created between createdate and SQL date (within the same period)
- This measures conversion rate within the period (e.g., monthly conversion rate) with deal validation

Usage:
  python sql_pql_conversion_analysis.py --month 2025-11
  python sql_pql_conversion_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
import argparse
import time
import requests
from dotenv import load_dotenv

# Add tools directory to path to import HubSpot API client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from hubspot_api.client import HubSpotClient, HubSpotAPIError
from hubspot_api.config import get_config

load_dotenv()

# Initialize HubSpot client
try:
    hubspot_client = HubSpotClient()
except Exception as e:
    print(f"❌ Failed to initialize HubSpot client: {e}")
    print("   Make sure HUBSPOT_API_KEY is set in .env file")
    sys.exit(1)

# Get API key for deal lookups
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
HUBSPOT_BASE_URL = 'https://api.hubapi.com'

def parse_datetime(date_str):
    """Parse HubSpot datetime string to datetime object"""
    if not date_str:
        return None
    try:
        # HubSpot datetime format: "2025-11-15T10:30:00.000Z"
        if 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        # fecha_activo is just a date: "2025-11-07"
        else:
            return datetime.fromisoformat(date_str + "T00:00:00+00:00")
    except (ValueError, AttributeError):
        return None

def fetch_deal_associations(contact_id):
    """
    Fetch deal associations for a contact using reverse lookup.
    Returns list of deal IDs.
    """
    if not HUBSPOT_API_KEY:
        return []
    
    headers = {
        'Authorization': f'Bearer {HUBSPOT_API_KEY}',
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
                # v4 API returns results with 'toObjectId'
                deal_ids = [item.get('toObjectId') or item.get('id') for item in result['results']]
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
                deal_ids = [item.get('id') for item in result['results']]
                return deal_ids
    except:
        pass
    
    return deal_ids

def fetch_deal_details(deal_ids):
    """
    Fetch deal details for a list of deal IDs.
    Returns dict mapping deal_id to deal data with createdate.
    """
    if not deal_ids or not HUBSPOT_API_KEY:
        return {}
    
    headers = {
        'Authorization': f'Bearer {HUBSPOT_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    deals_data = {}
    
    # Batch read deals (up to 100 at a time)
    for i in range(0, len(deal_ids), 100):
        batch_ids = deal_ids[i:i+100]
        inputs = [{'id': deal_id} for deal_id in batch_ids]
        
        try:
            url = f'{HUBSPOT_BASE_URL}/crm/v3/objects/deals/batch/read'
            payload = {
                'properties': ['dealname', 'createdate'],
                'inputs': inputs
            }
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'results' in result:
                    for deal in result['results']:
                        deal_id = deal.get('id')
                        props = deal.get('properties', {})
                        deals_data[deal_id] = {
                            'createdate': props.get('createdate')
                        }
        except:
            pass
    
    return deals_data

def validate_sql_with_deal(contact, start_dt, end_dt):
    """
    Validate that a contact is SQL by checking:
    1. Has hs_v2_date_entered_opportunity in period
    2. Has a deal created between contact creation and SQL date (within period)
    
    Returns True if valid SQL, False otherwise.
    """
    props = contact.get('properties', {})
    contact_createdate_str = contact.get('createdate')
    sql_date_str = contact.get('sql_date')  # This is hs_v2_date_entered_opportunity
    
    if not sql_date_str or not contact_createdate_str:
        return False
    
    contact_createdate = parse_datetime(contact_createdate_str)
    sql_date = parse_datetime(sql_date_str)
    
    if not contact_createdate or not sql_date:
        return False
    
    # SQL conversion must be in period
    if not (start_dt <= sql_date <= end_dt):
        return False
    
    # Fetch deal associations
    contact_id = contact.get('contact_id')
    if not contact_id:
        return False
    
    deal_ids = fetch_deal_associations(contact_id)
    if not deal_ids:
        return False
    
    # Fetch deal details
    deals_data = fetch_deal_details(deal_ids)
    
    # Check if any deal was created between contact creation and SQL date (within period)
    for deal_id in deal_ids:
        if deal_id in deals_data:
            deal_createdate_str = deals_data[deal_id].get('createdate')
            if deal_createdate_str:
                deal_createdate = parse_datetime(deal_createdate_str)
                if deal_createdate:
                    # Deal must be created between contact creation and SQL date, AND within the period
                    if (contact_createdate <= deal_createdate <= sql_date and 
                        start_dt <= deal_createdate <= end_dt):
                        return True
    
    return False

def fetch_sql_contacts(start_date, end_date):
    """
    Fetch contacts CREATED in the given date range that ALSO converted to SQL in the same range.
    SQL Conversion = Contact entered 'Oportunidad' lifecycle stage (hs_v2_date_entered_opportunity)
    
    Cohort Definition:
    - BOTH createdate AND hs_v2_date_entered_opportunity must be in the date range
    - This measures conversion rate within the month
    """
    print(f"\n📞 FETCHING SQL CONVERSIONS (Contacts created AND converted in period)")
    print(f"📅 Date Range: {start_date} to {end_date}")
    
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    # Properties needed for SQL and PQL analysis
    properties = [
        'email', 'firstname', 'lastname', 'createdate',
        'lifecyclestage',
        'hs_v2_date_entered_lead',
        'hs_v2_date_entered_opportunity',  # SQL conversion date (CORRECT FIELD)
        'hs_v2_date_entered_customer',
        'activo',  # PQL boolean flag
        'fecha_activo',  # PQL activation timestamp
        'num_associated_deals'
    ]
    
    # Step 1: Fetch all contacts CREATED in the date range
    search_request = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "createdate",
                "operator": "GTE",
                "value": start_datetime
            }, {
                "propertyName": "createdate",
                "operator": "LTE",
                "value": end_datetime
            }]
        }],
        "properties": properties,
        "limit": 100
    }
    
    all_contacts = []
    after = None
    total_requests = 0
    
    while True:
        if after:
            search_request["after"] = after
        
        try:
            result = hubspot_client.search_objects(
                object_type="contacts",
                filter_groups=search_request["filterGroups"],
                properties=properties,
                limit=100,
                after=after
            )
        except HubSpotAPIError as e:
            print(f"❌ HubSpot API error: {e}")
            break
        
        if not result or 'results' not in result:
            break
            
        batch_contacts = result['results']
        
        for contact in batch_contacts:
            props = contact.get('properties', {})
            
            # Extract contact data - initially add all contacts created in period
            contact_data = {
                'contact_id': contact['id'],
                'email': props.get('email'),
                'firstname': props.get('firstname'),
                'lastname': props.get('lastname'),
                'createdate': props.get('createdate'),
                'lifecyclestage': props.get('lifecyclestage'),
                'sql_date': props.get('hs_v2_date_entered_opportunity'),  # When became SQL
                'lead_date': props.get('hs_v2_date_entered_lead'),
                'customer_date': props.get('hs_v2_date_entered_customer'),
                'is_pql': props.get('activo') == 'true',
                'pql_date': props.get('fecha_activo'),  # When became PQL
                'num_associated_deals': props.get('num_associated_deals', '0')
            }
            
            all_contacts.append(contact_data)
        
        total_requests += 1
        if total_requests % 5 == 0:
            pql_count = sum(1 for c in all_contacts if c['is_pql'])
            print(f"📈 Progress: {total_requests} requests, {len(all_contacts)} SQLs, {pql_count} PQLs")
        
        if 'paging' not in result or 'next' not in result['paging']:
            break
        after = result['paging']['next']['after']
    
    print(f"✅ CONTACTS CREATED IN PERIOD: {len(all_contacts)} total")
    
    # Step 2: Filter to only contacts that ALSO converted to SQL in the same period WITH validated deal association
    start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
    
    sql_conversions = []
    total_created = len(all_contacts)
    
    print(f"🔍 Validating SQL conversions with deal associations...")
    for i, contact in enumerate(all_contacts):
        if (i + 1) % 50 == 0:
            print(f"   Progress: {i + 1}/{total_created} contacts checked...")
        
        # Validate SQL with deal association
        if validate_sql_with_deal(contact, start_dt, end_dt):
            # This contact was created AND converted to SQL in the period WITH validated deal
            sql_conversions.append(contact)
    
    print(f"🎯 SQL CONVERSIONS (created AND converted in period WITH validated deal): {len(sql_conversions)}")
    print(f"📊 Conversion Rate: {len(sql_conversions)/total_created*100:.2f}%" if total_created > 0 else "N/A")
    
    if len(sql_conversions) > 0:
        pql_count = sum(1 for c in sql_conversions if c['is_pql'])
        print(f"✅ PQL Contacts in SQL cohort: {pql_count} ({pql_count/len(sql_conversions)*100:.1f}%)")
    else:
        print("⚠️  No SQL conversions found for this period")
    
    return sql_conversions, total_created

def analyze_sql_pql_timing(contacts):
    """
    Analyze SQL contacts to determine if they were PQL before or after SQL conversion.
    
    Returns:
    - pql_before_sql: Contacts that were PQL BEFORE becoming SQL
    - pql_after_sql: Contacts that became PQL AFTER becoming SQL
    - never_pql: Contacts that were never PQL
    - pql_no_date: Contacts marked as PQL but missing fecha_activo
    """
    print(f"\n🎯 ANALYZING SQL → PQL TIMING RELATIONSHIP")
    print("=" * 60)
    
    analysis_data = []
    
    for contact in contacts:
        sql_date = parse_datetime(contact['sql_date'])
        pql_date = parse_datetime(contact['pql_date'])
        is_pql = contact['is_pql']
        
        # Determine PQL timing relative to SQL conversion
        if not is_pql or not pql_date:
            # Never PQL or PQL flag but no date
            if is_pql and not pql_date:
                pql_timing = 'pql_no_date'
            else:
                pql_timing = 'never_pql'
        elif sql_date and pql_date:
            # Compare dates
            if pql_date < sql_date:
                pql_timing = 'pql_before_sql'
            elif pql_date >= sql_date:
                pql_timing = 'pql_after_sql'
            else:
                pql_timing = 'unknown'
        else:
            pql_timing = 'unknown'
        
        # Calculate time difference if both dates exist
        days_diff = None
        if sql_date and pql_date:
            days_diff = (sql_date - pql_date).days
        
        row = {
            'contact_id': contact['contact_id'],
            'email': contact['email'],
            'firstname': contact['firstname'],
            'lastname': contact['lastname'],
            'createdate': contact['createdate'],
            'sql_date': contact['sql_date'],
            'pql_date': contact['pql_date'],
            'is_pql': is_pql,
            'pql_timing': pql_timing,
            'days_between_pql_sql': days_diff,
            'lifecyclestage': contact['lifecyclestage'],
            'num_associated_deals': int(contact['num_associated_deals']) if contact['num_associated_deals'] else 0
        }
        
        analysis_data.append(row)
    
    df = pd.DataFrame(analysis_data)
    
    # Summary statistics
    total_sqls = len(df)
    
    pql_before_sql = df[df['pql_timing'] == 'pql_before_sql']
    pql_after_sql = df[df['pql_timing'] == 'pql_after_sql']
    never_pql = df[df['pql_timing'] == 'never_pql']
    pql_no_date = df[df['pql_timing'] == 'pql_no_date']
    
    print(f"\n📊 SQL → PQL TIMING ANALYSIS RESULTS:")
    print("=" * 50)
    print(f"Total SQLs Analyzed: {total_sqls:,}")
    print(f"\n🎯 PQL BEFORE SQL: {len(pql_before_sql):,} ({len(pql_before_sql)/total_sqls*100:.1f}%)")
    print(f"   → These contacts activated in product BEFORE sales engagement")
    if len(pql_before_sql) > 0:
        avg_days = pql_before_sql['days_between_pql_sql'].mean()
        print(f"   → Average days between PQL and SQL: {avg_days:.1f} days")
    
    print(f"\n⏰ PQL AFTER SQL: {len(pql_after_sql):,} ({len(pql_after_sql)/total_sqls*100:.1f}%)")
    print(f"   → These contacts activated AFTER sales engagement started")
    if len(pql_after_sql) > 0:
        avg_days = pql_after_sql['days_between_pql_sql'].abs().mean()
        print(f"   → Average days between SQL and PQL: {avg_days:.1f} days")
    
    print(f"\n❌ NEVER PQL: {len(never_pql):,} ({len(never_pql)/total_sqls*100:.1f}%)")
    print(f"   → These contacts never activated in product")
    
    if len(pql_no_date) > 0:
        print(f"\n⚠️  PQL NO DATE: {len(pql_no_date):,} ({len(pql_no_date)/total_sqls*100:.1f}%)")
        print(f"   → Data quality issue: marked as PQL but fecha_activo is missing")
    
    # Additional insights
    print(f"\n💡 KEY INSIGHTS:")
    print("=" * 50)
    pql_before_rate = len(pql_before_sql) / total_sqls * 100 if total_sqls > 0 else 0
    print(f"• {pql_before_rate:.1f}% of SQLs were PQL BEFORE sales engagement")
    print(f"• This indicates product-led growth effectiveness")
    
    if len(pql_before_sql) > 0 and len(pql_after_sql) > 0:
        ratio = len(pql_before_sql) / len(pql_after_sql)
        print(f"• PQL-before-SQL vs PQL-after-SQL ratio: {ratio:.2f}:1")
    
    return df, {
        'total_sqls': total_sqls,
        'pql_before_sql': len(pql_before_sql),
        'pql_after_sql': len(pql_after_sql),
        'never_pql': len(never_pql),
        'pql_no_date': len(pql_no_date),
        'pql_before_rate': pql_before_rate
    }

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='SQL PQL Conversion Analysis')
    parser.add_argument('--month', help='Month in format YYYY-MM (e.g., 2025-11)')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    args = parser.parse_args()
    
    # Determine date range
    if args.month:
        # Parse month (YYYY-MM)
        year, month = map(int, args.month.split('-'))
        start_date = datetime(year, month, 1).strftime('%Y-%m-%d')
        # Last day of month
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        end_date = end_date.strftime('%Y-%m-%d')
        period_name = f"{args.month}"
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
        period_name = f"{start_date} to {end_date}"
    else:
        print("❌ Error: Must provide either --month (YYYY-MM) or --start-date and --end-date")
        return
    
    print(f"🎯 SQL PQL CONVERSION ANALYSIS")
    print(f"📅 Period: {period_name}")
    print(f"📋 Cohort: Contacts CREATED in period that ALSO converted to SQL in period")
    print(f"📊 Date Range: {start_date} to {end_date}")
    print("=" * 60)
    
    # Step 1: Fetch contacts created in period and filter to SQL conversions
    sql_contacts, total_created = fetch_sql_contacts(start_date, end_date)
    
    if not sql_contacts:
        print("❌ No SQL conversions found for the period")
        print(f"   (Total contacts created: {total_created})")
        return
    
    # Step 2: Analyze PQL timing relative to SQL conversion
    df, summary = analyze_sql_pql_timing(sql_contacts)
    
    # Add conversion rate to summary
    summary['total_contacts_created'] = total_created
    summary['sql_conversion_rate'] = len(sql_contacts) / total_created * 100 if total_created > 0 else 0
    
    # Step 3: Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('tools/outputs', exist_ok=True)
    
    # Save detailed CSV
    safe_period = period_name.replace('-', '').replace(' ', '_')
    csv_file = f"tools/outputs/sql_pql_analysis_{safe_period}_{timestamp}.csv"
    df.to_csv(csv_file, index=False)
    print(f"\n💾 Detailed results saved to: {csv_file}")
    
    # Save summary JSON
    output_data = {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'period': period_name,
        'date_range': {
            'start_date': start_date,
            'end_date': end_date
        },
        'methodology': {
            'sql_definition': 'Contact that converted to Opportunity (hs_v2_date_entered_opportunity populated)',
            'pql_definition': 'Contact that activated during trial (activo=true, fecha_activo populated)',
            'analysis': 'Compare fecha_activo with hs_v2_date_entered_opportunity to determine if PQL happened before SQL',
            'cohort_definition': 'Contacts CREATED in period that ALSO converted to SQL in the same period',
            'cohort_fields': {
                'createdate': 'Must be within date range',
                'hs_v2_date_entered_opportunity': 'Must be within date range'
            },
            'conversion_rate': 'SQL conversions / Total contacts created in period'
        },
        'summary': summary,
        'cohort_stats': {
            'total_contacts_created': summary.get('total_contacts_created', 0),
            'sql_conversions': summary['total_sqls'],
            'sql_conversion_rate': round(summary.get('sql_conversion_rate', 0), 2)
        },
        'data_quality': {
            'total_sqls': summary['total_sqls'],
            'pql_no_date_count': summary['pql_no_date'],
            'pql_no_date_rate': summary['pql_no_date'] / summary['total_sqls'] * 100 if summary['total_sqls'] > 0 else 0
        }
    }
    
    json_file = f"tools/outputs/sql_pql_analysis_{safe_period}_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(output_data, f, indent=2, default=str)
    
    print(f"💾 Summary results saved to: {json_file}")
    
    return df, summary

if __name__ == "__main__":
    main()

