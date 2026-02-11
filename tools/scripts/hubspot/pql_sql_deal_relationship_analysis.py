#!/usr/bin/env python3
"""
PQL → SQL → DEAL RELATIONSHIP ANALYSIS
======================================
Comprehensive analysis of how PQL (Product Qualified Leads) affects SQL (Sales Qualified Leads) 
and ultimately deal creation and close rates.

ANALYSIS GOALS:
1. Understand if PQL leads to more SQL conversions
2. Understand if PQL leads to more deal creation
3. Understand if PQL leads to higher deal close rates
4. Analyze timing relationships (PQL before/after SQL, PQL before/after deal creation)

KEY ASSUMPTIONS & QUESTIONS:
============================

1. COHORT DEFINITION:
   - Base Cohort: Contacts CREATED in the period (month-to-date)
   - This measures conversion rates for contacts created in the period
   - **MQL DEFINITION**: All contacts (excluding 'Usuario Invitado') are considered MQLs
     → They signed up for 7-day trial and validated their email
     → When email is validated, contact is created in HubSpot
     → Therefore: Contact created (excluding 'Usuario Invitado') = MQL
   - **EXCLUSION**: Contacts with `lead_source = 'Usuario Invitado'` are excluded
     → These are team member invitations from existing customers
     → They are NOT new contacts starting from trial period
     → They should NOT be counted in any analysis
   - Question: Should we also analyze deals created in the period vs deals associated with contacts created in period?
   → ASSUMPTION: We'll analyze deals associated with contacts created in the period (more relevant for attribution)

2. PQL DEFINITION:
   - PQL = Contact with activo='true' AND fecha_activo populated
   - Question: Should we consider PQL timing relative to contact creation or relative to SQL/deal creation?
   → ASSUMPTION: We'll analyze both - PQL timing relative to contact creation AND relative to SQL/deal creation

3. SQL DEFINITION:
   - **SQL = Contact associated to a deal, which triggers lifecycle stage change to 'Opportunity'**
   - **KEY INSIGHT**: When a contact (who starts as a "lead") gets associated to a deal, HubSpot automatically 
     changes their lifecycle stage to "Opportunity", which sets the `hs_v2_date_entered_opportunity` field
   - **SQL Conversion = Deal Association Event**: The association itself is the conversion event, regardless of 
     when the deal was created. The timing of deal creation vs association doesn't matter for funnel analysis.
   - Field: `hs_v2_date_entered_opportunity` = timestamp when contact was associated to deal (lifecycle stage changed)
   - Question: Should we only count SQLs that occurred in the period, or any SQL regardless of when?
   → ASSUMPTION: We'll show both - SQLs that occurred in the period AND all SQLs for contacts created in period

4. DEAL ASSOCIATION (SQL CONVERSION):
   - **Deal Association = SQL Conversion**: When a contact is associated to a deal, this triggers the SQL conversion
   - The deal may have been created at any point - what matters is when the contact was associated to it
   - Question: Should we count all deals or only deals created in the period?
   → ASSUMPTION: We'll analyze all deals associated with contacts created in period (for complete picture)
   - Question: Should we analyze deal creation date vs contact creation date?
   → ASSUMPTION: Deal creation timing is not relevant for funnel analysis - what matters is when contact was associated

5. DEAL CLOSE:
   - Deal Close = Deal with dealstage = 'closedwon' or specific won stage
   - Question: Should we only count deals closed in the period or all closed deals?
   → ASSUMPTION: We'll show both - deals closed in period AND all closed deals for contacts created in period

6. RELATIONSHIP ANALYSIS:
   - Question: How do we measure "PQL affects deal creation"?
   → ASSUMPTION: Compare deal creation rates, deal close rates, and revenue between PQL and non-PQL contacts
   - Question: Should we analyze PQL → SQL → Deal path separately from PQL → Deal (direct)?
   → ASSUMPTION: Yes, we'll analyze both paths to understand the full customer journey

Usage:
  python pql_sql_deal_relationship_analysis.py --month-mtd 2025-12
  python pql_sql_deal_relationship_analysis.py --start-date 2025-12-01 --end-date 2025-12-31
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import os
import sys
import argparse
import time
import requests
from dotenv import load_dotenv

# Add tools directory to path
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

HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
HUBSPOT_BASE_URL = 'https://api.hubapi.com'
# Delay (seconds) between HubSpot API calls to avoid 429; set HUBSPOT_RATE_LIMIT_DELAY in .env to increase
HUBSPOT_RATE_LIMIT_DELAY = float(os.getenv('HUBSPOT_RATE_LIMIT_DELAY', '0.5'))
# Longer delay for first N contact-search requests to avoid burst 429 at run start
HUBSPOT_INITIAL_DELAY = float(os.getenv('HUBSPOT_INITIAL_DELAY', '1.0'))
HUBSPOT_INITIAL_DELAY_REQUESTS = 5
MAX_429_RETRIES = 3

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

def get_contact_lifecycle_history(contact_id):
    """
    Fetch lifecycle stage history for a contact using propertiesWithHistory
    
    Returns:
        dict with:
        - sql_date_set_timestamp: When hs_v2_date_entered_opportunity was first set
        - lifecycle_stage_changes: List of lifecycle stage changes with timestamps
        - opportunity_stage_entry_timestamp: When contact first entered 'opportunity' stage
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {
        "propertiesWithHistory": "lifecyclestage,hs_v2_date_entered_opportunity"
    }
    
    result = {
        'sql_date_set_timestamp': None,
        'lifecycle_stage_changes': [],
        'opportunity_stage_entry_timestamp': None
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        props_history = data.get("propertiesWithHistory", {})
        
        # Get SQL date history
        if "hs_v2_date_entered_opportunity" in props_history:
            opp_history = props_history["hs_v2_date_entered_opportunity"]
            if isinstance(opp_history, list):
                versions = opp_history
            elif isinstance(opp_history, dict) and "versions" in opp_history:
                versions = opp_history["versions"]
            else:
                versions = []
            
            # Find the first time SQL date was set (first non-empty value)
            for version in versions:
                value = version.get("value", "")
                if value:  # First time it was set to a non-empty value
                    timestamp_str = version.get("timestamp", "")
                    if timestamp_str:
                        result['sql_date_set_timestamp'] = parse_datetime(timestamp_str)
                    break
        
        # Get lifecycle stage changes
        if "lifecyclestage" in props_history:
            lc_history = props_history["lifecyclestage"]
            if isinstance(lc_history, list):
                versions = lc_history
            elif isinstance(lc_history, dict) and "versions" in lc_history:
                versions = lc_history["versions"]
            else:
                versions = []
            
            # Find when contact entered 'opportunity' stage
            for version in versions:
                value = version.get("value", "")
                timestamp_str = version.get("timestamp", "")
                if value == "opportunity":
                    if timestamp_str:
                        timestamp = parse_datetime(timestamp_str)
                        if result['opportunity_stage_entry_timestamp'] is None or timestamp < result['opportunity_stage_entry_timestamp']:
                            result['opportunity_stage_entry_timestamp'] = timestamp
                
                # Store all stage changes
                if timestamp_str and value:
                    result['lifecycle_stage_changes'].append({
                        'stage': value,
                        'timestamp': parse_datetime(timestamp_str)
                    })
            
            # Sort stage changes by timestamp
            result['lifecycle_stage_changes'].sort(key=lambda x: x['timestamp'] if x['timestamp'] else datetime.max.replace(tzinfo=timezone.utc))
        
        return result
    except Exception as e:
        # Return empty result on error (don't fail the whole analysis)
        return result

def get_month_to_date(month_str=None):
    """Get month-to-date date range for specified month or current month"""
    now = datetime.now(timezone.utc)
    
    if month_str:
        year, month = map(int, month_str.split('-'))
        # If it's the current month, use today's date; otherwise use last day of that month
        if year == now.year and month == now.month:
            # Current month - use today's date
            end_day = now.day
        else:
            # Past or future month - use last day of that month for month-to-date
            if month == 12:
                last_day = (datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)).day
            else:
                last_day = (datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)).day
            end_day = last_day
        today = datetime(year, month, end_day, tzinfo=timezone.utc)
    else:
        today = now
        year, month = today.year, today.month
    
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    end_date = datetime(year, month, today.day, 23, 59, 59, tzinfo=timezone.utc)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def get_full_month(month_str):
    """Get full month date range for specified month"""
    year, month = map(int, month_str.split('-'))
    
    # Get first day of month
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    
    # Get last day of month
    if month == 12:
        end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    
    end_date = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def fetch_contacts_with_deals(start_date, end_date):
    """Fetch contacts created in period with PQL, SQL, and deal associations"""
    print(f"\n📥 FETCHING CONTACTS WITH DEAL ASSOCIATIONS")
    print(f"📅 Date Range: {start_date} to {end_date}")
    print("   ⚠️  Excluding 'Usuario Invitado' contacts")
    
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    properties = [
        'email', 'firstname', 'lastname', 'createdate',
        'lifecyclestage',  # Current lifecycle stage
        'hs_v2_date_entered_customer',  # Date entered customer stage (backup, but we'll use deal close date)
        'fit_score_contador',  # For scoring analysis
        'hs_v2_date_entered_opportunity',  # SQL date
        'activo',  # PQL flag
        'fecha_activo',  # PQL date
        'lead_source',  # To exclude "Usuario Invitado"
        'num_associated_deals'
    ]
    
    all_contacts = []
    after = None
    total_requests = 0
    
    # Filter groups
    filter_groups = [{
        "filters": [
            {
                "propertyName": "createdate",
                "operator": "GTE",
                "value": start_datetime
            },
            {
                "propertyName": "createdate",
                "operator": "LTE",
                "value": end_datetime
            },
            {
                "propertyName": "lead_source",
                "operator": "NEQ",
                "value": "Usuario Invitado"
            }
        ]
    }]
    
    while True:
        # Throttle: longer delay before first few requests to avoid burst 429
        if after is None and total_requests == 0:
            time.sleep(HUBSPOT_INITIAL_DELAY)
        search_request = {
            "filterGroups": filter_groups,
            "properties": properties,
            "associations": ["deals"],  # Get deal associations
            "limit": 100
        }
        
        if after:
            search_request["after"] = after
        
        url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search"
        headers = {
            'Authorization': f'Bearer {HUBSPOT_API_KEY}',
            'Content-Type': 'application/json'
        }
        result = None
        for attempt in range(MAX_429_RETRIES + 1):
            try:
                response = requests.post(url, headers=headers, json=search_request, timeout=30)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 10))
                    if attempt < MAX_429_RETRIES:
                        print(f"   ⚠️  Rate limited (429). Waiting {retry_after}s before retry {attempt + 1}/{MAX_429_RETRIES}...")
                        time.sleep(retry_after)
                        continue
                    else:
                        print(f"❌ Error fetching contacts: 429 Too Many Requests (retries exhausted)")
                        break
                response.raise_for_status()
                result = response.json()
                break
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 10))
                    if attempt < MAX_429_RETRIES:
                        print(f"   ⚠️  Rate limited (429). Waiting {retry_after}s before retry {attempt + 1}/{MAX_429_RETRIES}...")
                        time.sleep(retry_after)
                        continue
                print(f"❌ Error fetching contacts: {e}")
                break
            except Exception as e:
                print(f"❌ Error fetching contacts: {e}")
                break
        if result is None:
            break
        
        if not result or 'results' not in result:
            break
        
        batch_contacts = result['results']
        
        for contact in batch_contacts:
            props = contact.get('properties', {})
            associations = contact.get('associations', {})
            
            # Extract deal IDs
            deal_ids = []
            if 'deals' in associations:
                deals_data = associations['deals']
                if isinstance(deals_data, dict) and 'results' in deals_data:
                    # Handle both v3 and v4 API response formats
                    for deal in deals_data['results']:
                        # v4 API uses 'toObjectId', v3 API uses 'id'
                        deal_id = deal.get('toObjectId') or deal.get('id')
                        if deal_id:
                            deal_ids.append(str(deal_id))
                elif isinstance(deals_data, list):
                    # Sometimes associations come as a list directly
                    for deal in deals_data:
                        deal_id = deal.get('toObjectId') or deal.get('id')
                        if deal_id:
                            deal_ids.append(str(deal_id))
                # Note: HubSpot search API often returns empty associations even when requested
                # This is why we do reverse lookup as fallback
            
            contact_data = {
                'contact_id': contact['id'],
                'email': props.get('email'),
                'firstname': props.get('firstname'),
                'lastname': props.get('lastname'),
                'createdate': props.get('createdate'),
                'lifecyclestage': props.get('lifecyclestage'),
                'customer_date': props.get('hs_v2_date_entered_customer'),  # Date entered customer stage
                'fit_score_contador': props.get('fit_score_contador'),
                'sql_date': props.get('hs_v2_date_entered_opportunity'),
                'is_pql': props.get('activo') == 'true',
                'pql_date': props.get('fecha_activo'),
                'num_associated_deals': int(props.get('num_associated_deals', 0)) if props.get('num_associated_deals') else 0,
                'associated_deal_ids': deal_ids
            }
            
            all_contacts.append(contact_data)
        
        total_requests += 1
        if total_requests % 5 == 0:
            pql_count = sum(1 for c in all_contacts if c['is_pql'])
            sql_count = sum(1 for c in all_contacts if c['sql_date'])
            deal_count = sum(len(c['associated_deal_ids']) for c in all_contacts)
            print(f"📈 Progress: {total_requests} requests, {len(all_contacts)} contacts, {pql_count} PQLs, {sql_count} SQLs, {deal_count} deals")
        
        if 'paging' not in result or 'next' not in result['paging']:
            break
        after = result['paging']['next']['after']
        delay = HUBSPOT_INITIAL_DELAY if total_requests < HUBSPOT_INITIAL_DELAY_REQUESTS else HUBSPOT_RATE_LIMIT_DELAY
        time.sleep(delay)
    
    print(f"✅ Fetched {len(all_contacts)} contacts")
    if len(all_contacts) > 0:
        pql_count = sum(1 for c in all_contacts if c['is_pql'])
        sql_count = sum(1 for c in all_contacts if c['sql_date'])
        deal_count = sum(len(c['associated_deal_ids']) for c in all_contacts)
        print(f"   - PQL: {pql_count} ({pql_count/len(all_contacts)*100:.1f}%)")
        print(f"   - SQL: {sql_count} ({sql_count/len(all_contacts)*100:.1f}%)")
        print(f"   - Contacts with deals: {sum(1 for c in all_contacts if len(c['associated_deal_ids']) > 0)}")
        print(f"   - Total deal associations: {deal_count}")
    
    return all_contacts

def fetch_deal_details(deal_ids):
    """Fetch detailed information for deals"""
    if not deal_ids:
        return []
    
    print(f"\n💰 FETCHING DEAL DETAILS FOR {len(deal_ids)} DEALS")
    
    properties = [
        'dealname', 'amount', 'createdate', 'closedate', 'dealstage',
        'pipeline', 'hs_closed_won_date', 'hs_closed_lost_date',
        'hs_date_closed'  # Alternative close date field
    ]
    
    all_deals = []
    
    # Batch read deals (up to 100 at a time)
    for i in range(0, len(deal_ids), 100):
        batch_ids = deal_ids[i:i+100]
        
        inputs = [{"id": deal_id} for deal_id in batch_ids]
        
        request_data = {
            "properties": properties,
            "inputs": inputs
        }
        
        url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/batch/read"
        headers = {'Authorization': f'Bearer {HUBSPOT_API_KEY}', 'Content-Type': 'application/json'}
        result = None
        for attempt in range(MAX_429_RETRIES + 1):
            try:
                response = requests.post(url, headers=headers, json=request_data, timeout=30)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 10))
                    if attempt < MAX_429_RETRIES:
                        time.sleep(retry_after)
                        continue
                response.raise_for_status()
                result = response.json()
                break
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429 and attempt < MAX_429_RETRIES:
                    time.sleep(int(e.response.headers.get('Retry-After', 10)))
                    continue
                print(f"❌ Error fetching deals: {e}")
                result = None
                break
            except Exception as e:
                print(f"❌ Error fetching deals: {e}")
                result = None
                break
        if result is None:
            continue
        time.sleep(HUBSPOT_RATE_LIMIT_DELAY)
        if result and 'results' in result:
            for deal in result['results']:
                props = deal.get('properties', {})
                
                deal_data = {
                    'deal_id': deal['id'],
                    'dealname': props.get('dealname'),
                    'amount': float(props.get('amount', 0)) if props.get('amount') else 0,
                    'createdate': props.get('createdate'),
                    'closedate': props.get('closedate'),
                    'dealstage': props.get('dealstage'),
                    'pipeline': props.get('pipeline'),
                    'is_won': props.get('dealstage') in ['closedwon', '34692158'],  # Adjust stage IDs as needed
                    'is_closed': props.get('dealstage') in ['closedwon', '34692158', 'closedlost', '31849274'],
                    'hs_closed_won_date': props.get('hs_closed_won_date'),
                    'hs_closed_lost_date': props.get('hs_closed_lost_date')
                }
                
                all_deals.append(deal_data)
    
    won_deals = sum(1 for d in all_deals if d['is_won'])
    closed_deals = sum(1 for d in all_deals if d['is_closed'])
    total_revenue = sum(d['amount'] for d in all_deals if d['is_won'])
    
    print(f"✅ Fetched {len(all_deals)} deals")
    print(f"   - Won: {won_deals} ({won_deals/len(all_deals)*100:.1f}%)")
    print(f"   - Closed: {closed_deals} ({closed_deals/len(all_deals)*100:.1f}%)")
    print(f"   - Total Revenue: ${total_revenue:,.0f}")
    
    return all_deals

def analyze_pql_sql_deal_relationship(contacts, deals, start_date, end_date, contact_to_deal_mapping=None):
    """Comprehensive analysis of PQL → SQL → Deal relationship"""
    print(f"\n🎯 PQL → SQL → DEAL RELATIONSHIP ANALYSIS")
    print("=" * 80)
    print(f"\n📋 CUSTOMER DATE LOGIC:")
    print(f"  • Customer date is determined by DEAL CLOSE DATE, not contact-level field")
    print(f"  • For contacts with deals: Use deal closedate")
    print(f"  • For contacts without deals: Use hs_v2_date_entered_customer (fallback)")
    print(f"  • Customer must have: Contact created in period AND Deal closed in period")
    print("=" * 80)
    
    # Create deal lookup
    deal_lookup = {deal['deal_id']: deal for deal in deals}
    
    # Create a mapping of deal_id to contact_ids (from deals we fetched)
    # We'll use this to find which contacts have which deals
    deal_to_contact_ids = {}
    if contact_to_deal_mapping:
        for contact_id, deal_ids in contact_to_deal_mapping.items():
            for deal_id in deal_ids:
                if deal_id not in deal_to_contact_ids:
                    deal_to_contact_ids[deal_id] = []
                deal_to_contact_ids[deal_id].append(contact_id)
    
    # Parse date range for filtering
    start_dt = parse_datetime(f"{start_date}T00:00:00.000Z")
    end_dt = parse_datetime(f"{end_date}T23:59:59.999Z")
    
    # Analyze each contact
    analysis_data = []
    
    for contact in contacts:
        contact_created = parse_datetime(contact['createdate'])
        sql_date = parse_datetime(contact['sql_date'])
        pql_date = parse_datetime(contact['pql_date'])
        # Note: customer_date will be determined later from deal close dates
        # We'll initialize it here but update it after analyzing deals
        customer_date_contact_level = parse_datetime(contact.get('customer_date'))
        lifecyclestage = contact.get('lifecyclestage', '')
        is_pql = contact['is_pql']
        # is_customer will be determined after analyzing deals (see below)
        
        # Determine PQL timing relative to contact creation
        pql_timing_relative_to_contact = None
        days_pql_after_contact = None
        if is_pql and pql_date and contact_created:
            days_pql_after_contact = (pql_date - contact_created).days
            if days_pql_after_contact < 0:
                pql_timing_relative_to_contact = 'pql_before_contact'  # Data quality issue
            elif days_pql_after_contact <= 7:
                pql_timing_relative_to_contact = 'pql_within_7_days'
            elif days_pql_after_contact <= 30:
                pql_timing_relative_to_contact = 'pql_within_30_days'
            else:
                pql_timing_relative_to_contact = 'pql_after_30_days'
        
        # Determine PQL timing relative to SQL
        pql_timing_relative_to_sql = None
        days_pql_sql_diff = None
        if is_pql and pql_date and sql_date:
            days_pql_sql_diff = (sql_date - pql_date).days
            if days_pql_sql_diff < 0:
                pql_timing_relative_to_sql = 'pql_after_sql'
            else:
                pql_timing_relative_to_sql = 'pql_before_sql'
        
        # Determine SQL timing relative to contact creation
        sql_timing_relative_to_contact = None
        days_sql_after_contact = None
        if sql_date and contact_created:
            days_sql_after_contact = (sql_date - contact_created).days
            if days_sql_after_contact < 0:
                sql_timing_relative_to_contact = 'sql_before_contact'  # Data quality issue
            elif days_sql_after_contact <= 7:
                sql_timing_relative_to_contact = 'sql_within_7_days'
            elif days_sql_after_contact <= 30:
                sql_timing_relative_to_contact = 'sql_within_30_days'
            else:
                sql_timing_relative_to_contact = 'sql_after_30_days'
        
        # Analyze associated deals
        # SQL = Deal Creation, so if contact is SQL, we should have a deal
        # First check deals from contact associations
        associated_deals = [deal_lookup.get(deal_id) for deal_id in contact['associated_deal_ids'] if deal_id in deal_lookup]
        associated_deals = [d for d in associated_deals if d]  # Remove None values
        
        # Associated deals should already be populated from the reverse lookup
        # that we did in the main function (contact['associated_deal_ids'] was updated)
        # So we just need to use the deals we found
        
        is_sql = sql_date is not None
        
        # SQL = Deal Creation, so if contact is SQL, a deal was created
        # We should have the deal in associated_deals if the reverse lookup worked
        has_deals = len(associated_deals) > 0 or is_sql  # SQL = Deal Creation
        
        won_deals = [d for d in associated_deals if d['is_won']]
        closed_deals = [d for d in associated_deals if d['is_closed']]
        
        # Determine customer date from deal close date (primary) or contact field (fallback)
        # KEY LOGIC: Customer date = EARLIEST deal close date if deals exist, otherwise use contact-level field
        customer_date_from_deal = None
        customer_date_source = 'contact_field'  # Default source
        
        if len(associated_deals) > 0:
            # Find ALL close dates from ALL deals (not just closed deals)
            # We need to check all deals because a deal might be closed but not in closed_deals list
            all_deal_close_dates = []
            for deal in associated_deals:
                # Try multiple close date fields
                close_date_str = deal.get('closedate') or deal.get('hs_date_closed')
                if not close_date_str:
                    # Try won/lost dates
                    if deal.get('is_won'):
                        close_date_str = deal.get('hs_closed_won_date')
                    elif deal.get('is_closed'):
                        close_date_str = deal.get('hs_closed_lost_date')
                
                if close_date_str:
                    parsed_date = parse_datetime(close_date_str)
                    if parsed_date:
                        all_deal_close_dates.append(parsed_date)
            
            # Use the EARLIEST close date (as per user requirement)
            if all_deal_close_dates:
                customer_date_from_deal = min(all_deal_close_dates)
                customer_date_source = 'deal_close_date'
        
        # Use deal close date if available, otherwise fallback to contact-level field
        if customer_date_from_deal:
            customer_date = customer_date_from_deal
        else:
            customer_date = parse_datetime(contact.get('customer_date'))
            if customer_date:
                customer_date_source = 'contact_field'
        
        # Determine if contact is customer based on:
        # 1. Contact must be created in the period (already filtered)
        # 2. Customer date (from deal close date or contact field) must be in the period
        is_customer = False
        if customer_date:
            # Check if customer date (from deal or contact) is within the period
            if start_dt <= customer_date <= end_dt:
                is_customer = True
        elif lifecyclestage == 'customer' or lifecyclestage == 'Cliente':
            # Fallback: if lifecycle stage is customer but no date available
            # Only count if contact was created in period (already filtered)
            # This handles edge cases where deal close date might not be available
            if contact_created and start_dt <= contact_created <= end_dt:
                is_customer = True
                customer_date_source = 'lifecycle_stage_fallback'
        
        # Deal timing analysis
        deal_timing_relative_to_contact = None
        deal_timing_relative_to_pql = None
        deal_timing_relative_to_sql = None
        days_deal_sql_diff = None
        
        if len(associated_deals) > 0:
            # Use first deal for timing analysis
            first_deal = associated_deals[0]
            deal_created = parse_datetime(first_deal['createdate'])
            
            if deal_created and contact_created:
                days_deal_after_contact = (deal_created - contact_created).days
                if days_deal_after_contact < 0:
                    deal_timing_relative_to_contact = 'deal_before_contact'
                elif days_deal_after_contact <= 7:
                    deal_timing_relative_to_contact = 'deal_within_7_days'
                elif days_deal_after_contact <= 30:
                    deal_timing_relative_to_contact = 'deal_within_30_days'
                else:
                    deal_timing_relative_to_contact = 'deal_after_30_days'
            
            if deal_created and pql_date:
                days_deal_pql_diff = (deal_created - pql_date).days
                if days_deal_pql_diff < 0:
                    deal_timing_relative_to_pql = 'deal_before_pql'
                else:
                    deal_timing_relative_to_pql = 'deal_after_pql'
            
            if deal_created and sql_date:
                days_deal_sql_diff = (deal_created - sql_date).days
                if days_deal_sql_diff < 0:
                    deal_timing_relative_to_sql = 'deal_before_sql'
                else:
                    deal_timing_relative_to_sql = 'deal_after_sql'
        
        # Fetch lifecycle stage history for post-association cases
        # (deal created before SQL date - indicates post-association)
        sql_date_set_timestamp = None
        opportunity_stage_entry_timestamp = None
        lifecycle_history_available = False
        
        if (deal_timing_relative_to_sql == 'deal_before_sql' and 
            days_deal_sql_diff is not None and 
            days_deal_sql_diff < 0):
            # This is a potential post-association case - fetch history
            history = get_contact_lifecycle_history(contact['contact_id'])
            if history:
                lifecycle_history_available = True
                sql_date_set_timestamp = history['sql_date_set_timestamp']
                opportunity_stage_entry_timestamp = history['opportunity_stage_entry_timestamp']
                # Small delay to avoid rate limiting
                time.sleep(0.1)
        
        # Determine customer timing relative to other stages
        customer_timing_relative_to_contact = None
        customer_timing_relative_to_sql = None
        customer_timing_relative_to_deal = None
        days_customer_after_contact = None
        days_customer_after_sql = None
        
        if is_customer and customer_date:
            if contact_created:
                days_customer_after_contact = (customer_date - contact_created).days
                if days_customer_after_contact < 0:
                    customer_timing_relative_to_contact = 'customer_before_contact'
                elif days_customer_after_contact <= 7:
                    customer_timing_relative_to_contact = 'customer_within_7_days'
                elif days_customer_after_contact <= 30:
                    customer_timing_relative_to_contact = 'customer_within_30_days'
                else:
                    customer_timing_relative_to_contact = 'customer_after_30_days'
            
            if sql_date:
                days_customer_after_sql = (customer_date - sql_date).days
                if days_customer_after_sql < 0:
                    customer_timing_relative_to_sql = 'customer_before_sql'
                else:
                    customer_timing_relative_to_sql = 'customer_after_sql'
            
            if is_customer and customer_date and len(associated_deals) > 0:
                first_deal = associated_deals[0]
                deal_created = parse_datetime(first_deal.get('createdate'))
                if deal_created:
                    days_customer_deal_diff = (customer_date - deal_created).days
                    if days_customer_deal_diff < 0:
                        customer_timing_relative_to_deal = 'customer_before_deal'
                    else:
                        customer_timing_relative_to_deal = 'customer_after_deal'
        
        row = {
            'contact_id': contact['contact_id'],
            'email': contact['email'],
            'createdate': contact['createdate'],
            'lifecyclestage': lifecyclestage,
            'fit_score_contador': float(contact['fit_score_contador']) if contact['fit_score_contador'] else None,
            'is_pql': is_pql,
            'pql_date': contact['pql_date'],
            'is_sql': sql_date is not None,
            'sql_date': contact['sql_date'],
            'is_customer': is_customer,
            'customer_date': customer_date.isoformat() if customer_date else contact.get('customer_date'),
            'customer_date_source': customer_date_source,
            'has_deals': has_deals,
            'num_deals': len(associated_deals),
            'num_won_deals': len(won_deals),
            'num_closed_deals': len(closed_deals),
            'total_revenue': sum(d['amount'] for d in won_deals),
            'pql_timing_relative_to_contact': pql_timing_relative_to_contact,
            'days_pql_after_contact': days_pql_after_contact,
            'pql_timing_relative_to_sql': pql_timing_relative_to_sql,
            'days_pql_sql_diff': days_pql_sql_diff,
            'sql_timing_relative_to_contact': sql_timing_relative_to_contact,
            'days_sql_after_contact': days_sql_after_contact,
            'deal_timing_relative_to_contact': deal_timing_relative_to_contact,
            'deal_timing_relative_to_pql': deal_timing_relative_to_pql,
            'deal_timing_relative_to_sql': deal_timing_relative_to_sql,
            'days_deal_sql_diff': days_deal_sql_diff,
            'sql_date_set_timestamp': sql_date_set_timestamp.isoformat() if sql_date_set_timestamp else None,
            'opportunity_stage_entry_timestamp': opportunity_stage_entry_timestamp.isoformat() if opportunity_stage_entry_timestamp else None,
            'lifecycle_history_available': lifecycle_history_available,
            'customer_timing_relative_to_contact': customer_timing_relative_to_contact,
            'days_customer_after_contact': days_customer_after_contact,
            'customer_timing_relative_to_sql': customer_timing_relative_to_sql,
            'days_customer_after_sql': days_customer_after_sql,
            'customer_timing_relative_to_deal': customer_timing_relative_to_deal,
        }
        
        analysis_data.append(row)
    
    df = pd.DataFrame(analysis_data)
    
    return df

def generate_analysis_report(df, start_date, end_date):
    """Generate comprehensive analysis report with funnel visualization"""
    print(f"\n📊 COMPREHENSIVE RELATIONSHIP ANALYSIS REPORT")
    print("=" * 80)
    
    total_contacts = len(df)
    
    # FUNNEL ANALYSIS: Total Contacts → PQL → SQL (Deal Creation) → Deal Close
    print(f"\n🔍 FUNNEL: Total Contacts → PQL → SQL (Deal Creation) → Deal Close")
    print("=" * 80)
    print(f"\nKEY ASSUMPTION: SQL = Deal Association")
    print(f"  • When a contact (who starts as a 'lead') is associated to a deal, HubSpot automatically")
    print(f"    changes their lifecycle stage to 'Oportunidad' (Opportunity), which sets the SQL conversion date")
    print(f"  • Field: hs_v2_date_entered_opportunity = SQL conversion date = When contact was associated to deal")
    print(f"  • The deal may have been created at any point - what matters is when the contact was associated to it")
    print(f"  • This association event IS the SQL conversion, regardless of deal creation timing")
    print("-" * 80)
    
    # Stage 1: Total Contacts
    stage1_total = total_contacts
    
    # Stage 2: PQL (Product Qualified Leads)
    stage2_pql = df[df['is_pql'] == True]
    stage2_count = len(stage2_pql)
    stage2_pct = (stage2_count / stage1_total * 100) if stage1_total > 0 else 0
    
    # Stage 3: SQL (Deal Creation) - from PQL
    stage3_sql_from_pql = stage2_pql[stage2_pql['is_sql'] == True]
    stage3_sql_from_pql_count = len(stage3_sql_from_pql)
    stage3_sql_from_pql_pct = (stage3_sql_from_pql_count / stage2_count * 100) if stage2_count > 0 else 0
    
    # Stage 3: SQL (Deal Creation) - from Total (all SQLs)
    stage3_sql_total = df[df['is_sql'] == True]
    stage3_sql_total_count = len(stage3_sql_total)
    stage3_sql_total_pct = (stage3_sql_total_count / stage1_total * 100) if stage1_total > 0 else 0
    
    # Stage 4: Deal Close (won deals) - from SQL
    stage4_won = df[(df['is_sql'] == True) & (df['num_won_deals'] > 0)]
    stage4_won_count = len(stage4_won)
    stage4_won_pct = (stage4_won_count / stage3_sql_total_count * 100) if stage3_sql_total_count > 0 else 0
    
    # Stage 5: Customer - from Deal Won (or any SQL)
    stage5_customer = df[df['is_customer'] == True]
    stage5_count = len(stage5_customer)
    stage5_pct = (stage5_count / stage1_total * 100) if stage1_total > 0 else 0
    
    # Customer from Deal Won
    stage5_customer_from_won = df[(df['is_customer'] == True) & (df['is_sql'] == True) & (df['num_won_deals'] > 0)]
    stage5_customer_from_won_count = len(stage5_customer_from_won)
    stage5_customer_from_won_pct = (stage5_customer_from_won_count / stage4_won_count * 100) if stage4_won_count > 0 else 0
    
    # Customer from SQL (any SQL, not just won)
    stage5_customer_from_sql = df[(df['is_customer'] == True) & (df['is_sql'] == True)]
    stage5_customer_from_sql_count = len(stage5_customer_from_sql)
    stage5_customer_from_sql_pct = (stage5_customer_from_sql_count / stage3_sql_total_count * 100) if stage3_sql_total_count > 0 else 0
    
    print(f"\n{'Stage':<35} │ {'Count':<12} │ {'% of Previous':<18} │ {'% of Total':<15} │ {'Drop-off':<15}")
    print("─" * 35 + "┼" + "─" * 12 + "┼" + "─" * 18 + "┼" + "─" * 15 + "┼" + "─" * 15)
    print(f"{'1. Total Contacts':<35} │ {stage1_total:<12} │ {'—':<18} │ {'100.0%':<15} │ {'—':<15}")
    drop_off_1 = 100.0 - stage2_pct
    print(f"{'2. PQL':<35} │ {stage2_count:<12} │ {stage2_pct:<17.1f}% │ {stage2_pct:<14.1f}% │ {drop_off_1:<14.1f}%")
    # Calculate PQL → SQL conversion rate
    pql_to_sql_rate = (stage3_sql_from_pql_count / stage2_count * 100) if stage2_count > 0 else 0
    drop_off_from_pql = 100 - pql_to_sql_rate
    print(f"{'3. SQL (Deal Creation)':<35} │ {stage3_sql_total_count:<12} │ {stage3_sql_total_pct:<17.1f}% │ {stage3_sql_total_pct:<14.1f}% │ {'—':<15}")
    print(f"{'   └─ SQL from PQL':<35} │ {stage3_sql_from_pql_count:<12} │ {pql_to_sql_rate:<17.1f}% │ {(stage3_sql_from_pql_count/stage1_total*100):<14.1f}% │ {drop_off_from_pql:<14.1f}%")
    if stage4_won_count > 0:
        drop_off_3 = stage3_sql_total_pct - (stage4_won_count/stage1_total*100)
        print(f"{'4. Deal Close (Won)':<35} │ {stage4_won_count:<12} │ {stage4_won_pct:<17.1f}% │ {(stage4_won_count/stage1_total*100):<14.1f}% │ {drop_off_3:<14.1f}%")
    
    # Stage 5: Customer
    if stage5_count > 0:
        drop_off_4 = stage4_won_pct - (stage5_customer_from_won_count/stage4_won_count*100) if stage4_won_count > 0 else 0
        print(f"{'5. Customer':<35} │ {stage5_count:<12} │ {stage5_pct:<17.1f}% │ {stage5_pct:<14.1f}% │ {'—':<15}")
        print(f"{'   └─ Customer from Deal Won':<35} │ {stage5_customer_from_won_count:<12} │ {stage5_customer_from_won_pct:<17.1f}% │ {(stage5_customer_from_won_count/stage1_total*100):<14.1f}% │ {drop_off_4:<14.1f}%")
        print(f"{'   └─ Customer from SQL (any)':<35} │ {stage5_customer_from_sql_count:<12} │ {stage5_customer_from_sql_pct:<17.1f}% │ {(stage5_customer_from_sql_count/stage1_total*100):<14.1f}% │ {'—':<15}")
    
    # Calculate Deal Close Rate (of SQLs/deals created)
    all_sqls_df = df[df['is_sql'] == True]
    sqls_closed_df = all_sqls_df[all_sqls_df['num_closed_deals'] > 0]
    sqls_won_df = all_sqls_df[all_sqls_df['num_won_deals'] > 0]
    deal_close_rate_from_sql = (len(sqls_closed_df) / len(all_sqls_df) * 100) if len(all_sqls_df) > 0 else 0
    deal_win_rate_from_sql = (len(sqls_won_df) / len(all_sqls_df) * 100) if len(all_sqls_df) > 0 else 0
    
    print(f"\n📊 FUNNEL INSIGHTS:")
    print(f"  • PQL Conversion Rate: {stage2_pct:.1f}% of contacts became PQL")
    print(f"  • SQL (Deal Creation) Rate: {stage3_sql_total_pct:.1f}% of contacts created deals")
    print(f"  • PQL → SQL Conversion: {stage3_sql_from_pql_pct:.1f}% of PQLs created deals")
    print(f"  • SQL → Deal Close Rate: {deal_close_rate_from_sql:.1f}% of SQLs (deals created) closed")
    print(f"  • SQL → Deal Win Rate: {deal_win_rate_from_sql:.1f}% of SQLs (deals created) won" if len(sqls_won_df) > 0 else "  • SQL → Deal Win Rate: No won deals found")
    if stage5_count > 0:
        print(f"  • Customer Conversion Rate: {stage5_pct:.1f}% of contacts became customers")
        print(f"  • Deal Won → Customer: {stage5_customer_from_won_pct:.1f}% of won deals became customers")
        print(f"  • SQL → Customer: {stage5_customer_from_sql_pct:.1f}% of SQLs (deals created) became customers")
    
    # PQL Impact on Deal Creation
    print(f"\n🎯 PQL IMPACT ON DEAL CREATION:")
    print("-" * 80)
    pql_sql_rate = stage3_sql_from_pql_pct
    non_pql_sql_rate = ((stage3_sql_total_count - stage3_sql_from_pql_count) / (stage1_total - stage2_count) * 100) if (stage1_total - stage2_count) > 0 else 0
    pql_advantage = pql_sql_rate - non_pql_sql_rate
    print(f"  • PQL Deal Creation Rate: {pql_sql_rate:.1f}%")
    print(f"  • Non-PQL Deal Creation Rate: {non_pql_sql_rate:.1f}%")
    print(f"  • PQL Advantage: {pql_advantage:+.1f} percentage points")
    
    if pql_advantage > 0:
        print(f"  ✅ PQLs are {pql_advantage:.1f}pp more likely to create deals")
    else:
        print(f"  ⚠️  PQLs are {abs(pql_advantage):.1f}pp less likely to create deals")
    
    # PQL Impact on Deal Win Rate
    pql_sql_won_count = len(df[(df['is_pql'] == True) & (df['is_sql'] == True) & (df['num_won_deals'] > 0)])
    non_pql_sql_won_count = len(df[(df['is_pql'] == False) & (df['is_sql'] == True) & (df['num_won_deals'] > 0)])
    pql_win_rate = (pql_sql_won_count / stage2_count * 100) if stage2_count > 0 else 0
    non_pql_win_rate = (non_pql_sql_won_count / (stage1_total - stage2_count) * 100) if (stage1_total - stage2_count) > 0 else 0
    pql_win_advantage = pql_win_rate - non_pql_win_rate
    
    print(f"\n🎯 PQL IMPACT ON DEAL WIN RATE:")
    print("-" * 80)
    print(f"  • PQL Deal Win Rate: {pql_win_rate:.1f}% (PQLs that created deals AND won them)")
    print(f"  • Non-PQL Deal Win Rate: {non_pql_win_rate:.1f}% (Non-PQLs that created deals AND won them)")
    print(f"  • PQL Win Advantage: {pql_win_advantage:+.1f} percentage points")
    
    if pql_win_advantage > 0:
        print(f"  ✅ PQLs are {pql_win_advantage:.1f}pp more likely to win deals")
    else:
        print(f"  ⚠️  PQLs are {abs(pql_win_advantage):.1f}pp less likely to win deals")
    
    # 1. PQL vs Non-PQL Comparison (Updated to show SQL = Deal Creation)
    print(f"\n1️⃣  PQL vs NON-PQL COMPARISON (SQL = Deal Creation)")
    print("-" * 80)
    
    pql_df = df[df['is_pql'] == True]
    non_pql_df = df[df['is_pql'] == False]
    
    print(f"{'Metric':<40} │ {'PQL':<15} │ {'Non-PQL':<15} │ {'Difference':<15}")
    print("─" * 40 + "┼" + "─" * 15 + "┼" + "─" * 15 + "┼" + "─" * 15)
    
    # SQL Conversion Rate (SQL = Deal Creation)
    pql_sql_rate = (pql_df['is_sql'].sum() / len(pql_df) * 100) if len(pql_df) > 0 else 0
    non_pql_sql_rate = (non_pql_df['is_sql'].sum() / len(non_pql_df) * 100) if len(non_pql_df) > 0 else 0
    sql_diff = pql_sql_rate - non_pql_sql_rate
    print(f"{'SQL (Deal Creation) Rate':<40} │ {pql_sql_rate:<14.1f}% │ {non_pql_sql_rate:<14.1f}% │ {sql_diff:+.1f}pp")
    
    # Deal Creation Rate (using SQL as proxy)
    # Note: SQL = Deal Creation, so this is the same as above, but we show it for clarity
    pql_deal_rate = pql_sql_rate  # SQL = Deal Creation
    non_pql_deal_rate = non_pql_sql_rate  # SQL = Deal Creation
    deal_diff = sql_diff
    print(f"{'Deal Creation Rate (SQL proxy)':<40} │ {pql_deal_rate:<14.1f}% │ {non_pql_deal_rate:<14.1f}% │ {deal_diff:+.1f}pp")
    
    # Deal Win Rate: % of PQLs/Non-PQLs that created deals AND won them
    # Formula: (PQLs that are SQL AND have won deals) / (Total PQLs) × 100
    pql_sql_won = pql_df[(pql_df['is_sql'] == True) & (pql_df['num_won_deals'] > 0)]
    non_pql_sql_won = non_pql_df[(non_pql_df['is_sql'] == True) & (non_pql_df['num_won_deals'] > 0)]
    pql_win_rate = (len(pql_sql_won) / len(pql_df) * 100) if len(pql_df) > 0 else 0
    non_pql_win_rate = (len(non_pql_sql_won) / len(non_pql_df) * 100) if len(non_pql_df) > 0 else 0
    win_diff = pql_win_rate - non_pql_win_rate
    print(f"{'Deal Win Rate (created deals AND won)':<40} │ {pql_win_rate:<14.1f}% │ {non_pql_win_rate:<14.1f}% │ {win_diff:+.1f}pp")
    
    # Deal Close Rate: % of SQLs (deals created) that eventually closed (won or lost)
    # Formula: (SQLs with closed deals) / (Total SQLs) × 100
    all_sqls = df[df['is_sql'] == True]
    sqls_closed = all_sqls[all_sqls['num_closed_deals'] > 0]
    sqls_won = all_sqls[all_sqls['num_won_deals'] > 0]
    sqls_lost = sqls_closed[sqls_closed['num_won_deals'] == 0]
    
    deal_close_rate = (len(sqls_closed) / len(all_sqls) * 100) if len(all_sqls) > 0 else 0
    deal_win_rate_from_sql = (len(sqls_won) / len(all_sqls) * 100) if len(all_sqls) > 0 else 0
    deal_lost_rate_from_sql = (len(sqls_lost) / len(all_sqls) * 100) if len(all_sqls) > 0 else 0
    
    print(f"{'Deal Close Rate (of SQLs/deals created)':<40} │ {deal_close_rate:<14.1f}% │ {'—':<15} │ {'—':<15}")
    print(f"{'  └─ Deal Win Rate (of SQLs/deals created)':<40} │ {deal_win_rate_from_sql:<14.1f}% │ {'—':<15} │ {'—':<15}")
    print(f"{'  └─ Deal Lost Rate (of SQLs/deals created)':<40} │ {deal_lost_rate_from_sql:<14.1f}% │ {'—':<15} │ {'—':<15}")
    
    # Average Revenue per Contact
    pql_avg_revenue = pql_df['total_revenue'].mean() if len(pql_df) > 0 else 0
    non_pql_avg_revenue = non_pql_df['total_revenue'].mean() if len(non_pql_df) > 0 else 0
    revenue_diff = pql_avg_revenue - non_pql_avg_revenue
    print(f"{'Avg Revenue per Contact':<40} │ ${pql_avg_revenue:<13,.0f} │ ${non_pql_avg_revenue:<13,.0f} │ ${revenue_diff:+,.0f}")
    
    # 2. Customer Journey Paths
    print(f"\n2️⃣  CUSTOMER JOURNEY PATHS")
    print("-" * 80)
    
    # Path 1: PQL → SQL → Deal
    pql_sql_deal = df[(df['is_pql'] == True) & (df['is_sql'] == True) & (df['has_deals'] == True)]
    # Path 2: PQL → Deal (direct, no SQL)
    pql_deal_direct = df[(df['is_pql'] == True) & (df['is_sql'] == False) & (df['has_deals'] == True)]
    # Path 3: SQL → Deal (no PQL)
    sql_deal_no_pql = df[(df['is_pql'] == False) & (df['is_sql'] == True) & (df['has_deals'] == True)]
    # Path 4: Deal (no PQL, no SQL)
    deal_no_pql_sql = df[(df['is_pql'] == False) & (df['is_sql'] == False) & (df['has_deals'] == True)]
    
    print(f"{'Journey Path':<40} │ {'Count':<10} │ {'% of Total':<12} │ {'Avg Revenue':<15}")
    print("─" * 40 + "┼" + "─" * 10 + "┼" + "─" * 12 + "┼" + "─" * 15)
    print(f"{'PQL → SQL → Deal':<40} │ {len(pql_sql_deal):<10} │ {len(pql_sql_deal)/total_contacts*100:<11.1f}% │ ${pql_sql_deal['total_revenue'].mean():<14,.0f}")
    print(f"{'PQL → Deal (direct)':<40} │ {len(pql_deal_direct):<10} │ {len(pql_deal_direct)/total_contacts*100:<11.1f}% │ ${pql_deal_direct['total_revenue'].mean():<14,.0f}")
    print(f"{'SQL → Deal (no PQL)':<40} │ {len(sql_deal_no_pql):<10} │ {len(sql_deal_no_pql)/total_contacts*100:<11.1f}% │ ${sql_deal_no_pql['total_revenue'].mean():<14,.0f}")
    print(f"{'Deal (no PQL, no SQL)':<40} │ {len(deal_no_pql_sql):<10} │ {len(deal_no_pql_sql)/total_contacts*100:<11.1f}% │ ${deal_no_pql_sql['total_revenue'].mean():<14,.0f}")
    
    # 3. Timing Analysis
    print(f"\n3️⃣  TIMING ANALYSIS")
    print("-" * 80)
    
    # PQL timing relative to SQL
    pql_before_sql = df[df['pql_timing_relative_to_sql'] == 'pql_before_sql']
    pql_after_sql = df[df['pql_timing_relative_to_sql'] == 'pql_after_sql']
    
    if len(pql_before_sql) > 0 or len(pql_after_sql) > 0:
        print(f"\nPQL Timing Relative to SQL:")
        print(f"  • PQL BEFORE SQL: {len(pql_before_sql)} contacts")
        if len(pql_before_sql) > 0:
            avg_days = pql_before_sql['days_pql_sql_diff'].mean()
            print(f"    → Avg days between PQL and SQL: {avg_days:.1f} days")
            pql_before_sql_deal_rate = (pql_before_sql['has_deals'].sum() / len(pql_before_sql) * 100) if len(pql_before_sql) > 0 else 0
            print(f"    → Deal creation rate: {pql_before_sql_deal_rate:.1f}%")
        
        print(f"  • PQL AFTER SQL: {len(pql_after_sql)} contacts")
        if len(pql_after_sql) > 0:
            avg_days = abs(pql_after_sql['days_pql_sql_diff'].mean())
            print(f"    → Avg days between SQL and PQL: {avg_days:.1f} days")
            pql_after_sql_deal_rate = (pql_after_sql['has_deals'].sum() / len(pql_after_sql) * 100) if len(pql_after_sql) > 0 else 0
            print(f"    → Deal creation rate: {pql_after_sql_deal_rate:.1f}%")
    
    # Deal timing relative to PQL
    deal_after_pql = df[df['deal_timing_relative_to_pql'] == 'deal_after_pql']
    deal_before_pql = df[df['deal_timing_relative_to_pql'] == 'deal_before_pql']
    
    if len(deal_after_pql) > 0 or len(deal_before_pql) > 0:
        print(f"\nDeal Timing Relative to PQL:")
        print(f"  • Deal AFTER PQL: {len(deal_after_pql)} contacts")
        if len(deal_after_pql) > 0:
            deal_after_pql_win_rate = (deal_after_pql['num_won_deals'].sum() / len(deal_after_pql) * 100) if len(deal_after_pql) > 0 else 0
            print(f"    → Deal win rate: {deal_after_pql_win_rate:.1f}%")
        
        print(f"  • Deal BEFORE PQL: {len(deal_before_pql)} contacts")
        if len(deal_before_pql) > 0:
            deal_before_pql_win_rate = (deal_before_pql['num_won_deals'].sum() / len(deal_before_pql) * 100) if len(deal_before_pql) > 0 else 0
            print(f"    → Deal win rate: {deal_before_pql_win_rate:.1f}%")
    
    # SQL CONVERSION METHODOLOGY: Understanding that SQL = Deal Association
    contacts_with_deals_sql = df[(df['has_deals'] == True) & (df['is_sql'] == True)]
    
    if len(contacts_with_deals_sql) > 0:
        print(f"\n🔍 SQL CONVERSION METHODOLOGY:")
        print("=" * 80)
        print("Understanding SQL Conversion: Association to Deal = SQL Conversion")
        print("-" * 80)
        print()
        print("KEY INSIGHT:")
        print("  • When a contact (who starts as a 'lead') is associated to a deal,")
        print("    HubSpot automatically changes their lifecycle stage to 'Opportunity'")
        print("  • This lifecycle stage change sets the hs_v2_date_entered_opportunity field")
        print("  • The association event IS the SQL conversion, regardless of when the deal was created")
        print()
        print("FUNNEL FLOW:")
        print("  Lead → (Association to Deal) → Opportunity (SQL)")
        print()
        print(f"📊 SQL CONVERSION SUMMARY:")
        print(f"  • Total SQL contacts with deals: {len(contacts_with_deals_sql)}")
        print(f"  • All SQL conversions occur when contact is associated to a deal")
        print(f"  • Deal creation timing is not relevant for funnel analysis")
        
        # Show lifecycle history validation if available
        contacts_with_history = contacts_with_deals_sql[contacts_with_deals_sql['lifecycle_history_available'] == True]
        if len(contacts_with_history) > 0:
            print(f"\n📋 LIFECYCLE STAGE HISTORY VALIDATION:")
            print(f"  • Contacts with history data: {len(contacts_with_history)}")
            validated = 0
            for _, contact in contacts_with_history.iterrows():
                sql_set_ts = contact.get('sql_date_set_timestamp')
                opp_entry_ts = contact.get('opportunity_stage_entry_timestamp')
                
                if sql_set_ts and opp_entry_ts:
                    try:
                        sql_ts = parse_datetime(sql_set_ts) if isinstance(sql_set_ts, str) else sql_set_ts
                        opp_ts = parse_datetime(opp_entry_ts) if isinstance(opp_entry_ts, str) else opp_entry_ts
                        
                        if sql_ts and opp_ts:
                            # Check if timestamps are within 1 hour (same event)
                            time_diff = abs((sql_ts - opp_ts).total_seconds() / 3600)
                            if time_diff <= 1:
                                validated += 1
                    except:
                        pass
            
            print(f"  • Validated: SQL date matches opportunity stage entry: {validated} contacts")
            print(f"  • This confirms: Association to deal triggers lifecycle stage change to Opportunity")
    
    # 4. Key Insights
    print(f"\n4️⃣  KEY INSIGHTS")
    print("-" * 80)
    
    pql_count = len(pql_df)
    pql_deal_count = pql_df['has_deals'].sum()
    pql_sql_count = pql_df['is_sql'].sum()
    
    print(f"📊 PQL Effectiveness:")
    print(f"  • {pql_count} PQL contacts ({pql_count/total_contacts*100:.1f}% of total)")
    print(f"  • {pql_deal_count} PQL contacts created deals ({pql_deal_rate:.1f}% deal creation rate)")
    print(f"  • {pql_sql_count} PQL contacts became SQL ({pql_sql_rate:.1f}% SQL conversion rate)")
    
    if pql_deal_rate > non_pql_deal_rate:
        advantage = pql_deal_rate - non_pql_deal_rate
        print(f"\n✅ PQL ADVANTAGE: PQLs have {advantage:.1f}pp higher deal creation rate")
    else:
        print(f"\n⚠️  PQL DISADVANTAGE: PQLs have lower deal creation rate")
    
    if pql_win_rate > non_pql_win_rate:
        win_advantage = pql_win_rate - non_pql_win_rate
        print(f"✅ PQL ADVANTAGE: PQLs have {win_advantage:.1f}pp higher deal win rate")
    else:
        print(f"⚠️  PQL DISADVANTAGE: PQLs have lower deal win rate")
    
    return df

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='PQL → SQL → Deal Relationship Analysis')
    parser.add_argument('--month-mtd', help='Month in format YYYY-MM for month-to-date analysis (e.g., 2025-12)')
    parser.add_argument('--month', help='Month in format YYYY-MM for full month analysis (e.g., 2025-11)')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    args = parser.parse_args()
    
    # Determine date range
    if args.month:
        start_date, end_date = get_full_month(args.month)
        period_name = f"{args.month} (Full Month)"
    elif args.month_mtd:
        start_date, end_date = get_month_to_date(args.month_mtd)
        period_name = f"{args.month_mtd} (Month-to-Date)"
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
        period_name = f"{start_date} to {end_date}"
    else:
        print("❌ Error: Must provide either --month-mtd (YYYY-MM) or --start-date and --end-date")
        return
    
    print(f"🎯 PQL → SQL → DEAL RELATIONSHIP ANALYSIS")
    print(f"📅 Period: {period_name}")
    print(f"📊 Date Range: {start_date} to {end_date}")
    print("=" * 80)
    
    # Initialize HubSpot client if available
    global hubspot_client
    hubspot_client = None
    if HUBSPOT_CLIENT_AVAILABLE:
        try:
            hubspot_client = HubSpotClient()
        except Exception as e:
            print(f"⚠️  HubSpot client initialization failed: {e}")
            print("   Continuing with direct API requests...")
    
    # Step 1: Fetch contacts with deal associations
    contacts = fetch_contacts_with_deals(start_date, end_date)
    
    if not contacts:
        print("❌ No contacts found for the period")
        return
    
    # Step 2: Find deals for ALL contacts (not just SQL)
    # IMPORTANT: We need to check ALL contacts for deal associations to find customer dates
    # Customer date = earliest deal close date, so we need all deals for all contacts
    print(f"\n🔍 SEARCHING FOR DEALS ASSOCIATED WITH CONTACTS")
    print("   (Checking contacts for deal associations to find customer dates)")
    
    # Get all unique deal IDs from contact associations first
    # NOTE: HubSpot search API often doesn't return associations even when requested,
    # so we'll do a reverse lookup as fallback
    all_deal_ids = []
    for contact in contacts:
        all_deal_ids.extend(contact['associated_deal_ids'])
    
    unique_deal_ids_from_associations = list(set(all_deal_ids))
    if len(unique_deal_ids_from_associations) > 0:
        print(f"   ✓ Found {len(unique_deal_ids_from_associations)} deals from initial search associations")
    else:
        print(f"   ⚠️  Initial search returned 0 associations (HubSpot API limitation - using reverse lookup)")
    
    # Also search for deals by contact IDs (reverse lookup) for SQL contacts only
    # SQL = Deal Creation, so SQL contacts should have deals
    # This ensures we find all deals, even if associations didn't work
    deal_ids_from_contact_search = []
    contact_to_deal_ids_map = {}  # Map contact_id to list of deal_ids
    
    # Filter to SQL contacts first (SQL = Deal Creation)
    sql_contacts = [c for c in contacts if c.get('sql_date')]
    contacts_to_check = sql_contacts if sql_contacts else contacts  # Fallback to all if no SQLs
    
    print(f"   Searching for deals associated with {len(contacts_to_check)} contacts ({len(sql_contacts)} SQL contacts)...")
    headers = {'Authorization': f'Bearer {HUBSPOT_API_KEY}', 'Content-Type': 'application/json'}
    for i, contact in enumerate(contacts_to_check):
        if (i + 1) % 50 == 0:
            print(f"   Progress: {i + 1}/{len(contacts_to_check)} contacts checked")
        
        contact_id = contact['contact_id']
        contact_deal_ids = []
        
        for attempt in range(MAX_429_RETRIES + 1):
            try:
                response = requests.get(f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/deals", headers=headers, timeout=30)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 10))
                    if attempt < MAX_429_RETRIES:
                        time.sleep(retry_after)
                        continue
                    break
                if response.status_code == 200:
                    result = response.json()
                    if 'results' in result:
                        contact_deal_ids = [str(assoc.get('toObjectId') or assoc.get('id')) for assoc in result['results'] if assoc.get('toObjectId') or assoc.get('id')]
                        if contact_deal_ids:
                            deal_ids_from_contact_search.extend(contact_deal_ids)
                            contact_to_deal_ids_map[contact_id] = contact_deal_ids
                break
            except Exception:
                break
        
        if contact_deal_ids:
            time.sleep(HUBSPOT_RATE_LIMIT_DELAY)
            continue
        
        for attempt in range(MAX_429_RETRIES + 1):
            try:
                response = requests.get(f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}/associations/deals", headers=headers, timeout=30)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 10))
                    if attempt < MAX_429_RETRIES:
                        time.sleep(retry_after)
                        continue
                    break
                if response.status_code == 200:
                    result = response.json()
                    if 'results' in result:
                        contact_deal_ids = [str(assoc.get('id') or assoc.get('toObjectId')) for assoc in result['results'] if assoc.get('id') or assoc.get('toObjectId')]
                        if contact_deal_ids:
                            deal_ids_from_contact_search.extend(contact_deal_ids)
                            contact_to_deal_ids_map[contact_id] = contact_deal_ids
                break
            except Exception:
                break
        
        time.sleep(HUBSPOT_RATE_LIMIT_DELAY)
    
    # Update contacts with deal IDs found from reverse lookup
    for contact in contacts:
        contact_id = contact['contact_id']
        if contact_id in contact_to_deal_ids_map:
            # Add deals found from reverse lookup to contact's associated_deal_ids
            for deal_id in contact_to_deal_ids_map[contact_id]:
                if deal_id not in contact['associated_deal_ids']:
                    contact['associated_deal_ids'].append(deal_id)
    
    # Combine both methods
    all_unique_deal_ids = list(set(unique_deal_ids_from_associations + deal_ids_from_contact_search))
    print(f"\n📊 Found {len(all_unique_deal_ids)} unique deals total")
    print(f"   - From contact associations: {len(unique_deal_ids_from_associations)}")
    print(f"   - From contact search: {len(set(deal_ids_from_contact_search))}")
    
    # Step 3: Fetch deal details
    deals = fetch_deal_details(all_unique_deal_ids) if all_unique_deal_ids else []
    
    # Step 4: Create contact-to-deal mapping for analysis
    # Map deals found from reverse lookup back to contacts
    contact_to_deal_mapping = {}
    for contact in contacts:
        contact_id = contact['contact_id']
        # Start with deals from associations
        deal_ids = contact['associated_deal_ids'].copy()
        contact_to_deal_mapping[contact_id] = deal_ids
    
    # Step 5: Analyze relationship
    df = analyze_pql_sql_deal_relationship(contacts, deals, start_date, end_date, contact_to_deal_mapping)
    
    # Step 5: Generate report
    df = generate_analysis_report(df, start_date, end_date)
    
    # Step 6: Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('tools/outputs', exist_ok=True)
    
    safe_period = period_name.replace('-', '').replace(' ', '_').replace('(', '').replace(')', '')
    csv_file = f"tools/outputs/pql_sql_deal_relationship_{safe_period}_{timestamp}.csv"
    df.to_csv(csv_file, index=False)
    print(f"\n💾 Detailed results saved to: {csv_file}")
    
    return df

if __name__ == "__main__":
    main()

