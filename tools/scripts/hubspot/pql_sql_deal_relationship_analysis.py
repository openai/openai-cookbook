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
   - SQL = Contact with hs_v2_date_entered_opportunity populated WITH validated deal association
   - Monthly Analysis Standard: Contact must be CREATED AND converted to SQL in the same period
   - Validation: Contact must have a deal created between contact creation and SQL date (within the period)
   - Complete Definition: SQL = MQL (contact created in period) + hs_v2_date_entered_opportunity in period + deal created between createdate and SQL date (within period)
   - This matches the standard for deals (created AND closed in same period)

4. DEAL CREATION:
   - Deal Creation = Deal associated with contact
   - Question: Should we count all deals or only deals created in the period?
   → ASSUMPTION: We'll analyze all deals associated with contacts created in period (for complete picture)
   - Question: Should we analyze deal creation date vs contact creation date?
   → ASSUMPTION: We'll analyze timing relationship (deal created before/after contact creation, before/after PQL)

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
  python pql_sql_deal_relationship_analysis.py --start-date 2025-12-01 --end-date 2025-12-20
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import os
import sys
import argparse
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

def get_month_to_date(month_str=None):
    """Get month-to-date date range for specified month or current month"""
    if month_str:
        year, month = map(int, month_str.split('-'))
        today = datetime(year, month, min(datetime.now().day, 20), tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc)
        year, month = today.year, today.month
    
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    end_date = datetime(year, month, min(today.day, 20), 23, 59, 59, tzinfo=timezone.utc)
    
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
    """Fetch contacts created in period with PQL, SQL, and deal associations
    
    NOTE: For monthly analysis, conversions (PQL/SQL/Customer) are filtered to only include
    those that occurred in the same period as contact creation (matches deal analysis standard).
    """
    print(f"\n📥 FETCHING CONTACTS WITH DEAL ASSOCIATIONS")
    print(f"📅 Date Range: {start_date} to {end_date}")
    print("   ⚠️  Excluding 'Usuario Invitado' contacts")
    print("   📊 Filtering: Contacts created AND converted (PQL/SQL/Customer) in same period")
    
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
        search_request = {
            "filterGroups": filter_groups,
            "properties": properties,
            "associations": ["deals"],  # Get deal associations
            "limit": 100
        }
        
        if after:
            search_request["after"] = after
        
        try:
            # Always use direct API requests for associations support
            url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search"
            headers = {
                'Authorization': f'Bearer {HUBSPOT_API_KEY}',
                'Content-Type': 'application/json'
            }
            response = requests.post(url, headers=headers, json=search_request, timeout=30)
            response.raise_for_status()
            result = response.json()
        except Exception as e:
            print(f"❌ Error fetching contacts: {e}")
            break
        
        if not result or 'results' not in result:
            break
        
        batch_contacts = result['results']
        
        for contact in batch_contacts:
            props = contact.get('properties', {})
            associations = contact.get('associations', {})
            
            # Extract deal IDs
            deal_ids = []
            if 'deals' in associations and 'results' in associations['deals']:
                deal_ids = [deal['id'] for deal in associations['deals']['results']]
            
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
        
        try:
            url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/batch/read"
            headers = {
                'Authorization': f'Bearer {HUBSPOT_API_KEY}',
                'Content-Type': 'application/json'
            }
            response = requests.post(url, headers=headers, json=request_data, timeout=30)
            response.raise_for_status()
            result = response.json()
        except Exception as e:
            print(f"❌ Error fetching deals: {e}")
            continue
        
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
        
        # Filter PQL: Must be created AND activated (fecha_activo) in the same period (monthly analysis standard)
        # PQL Definition: activo='true' AND fecha_activo populated AND fecha_activo in period
        is_pql_flag = contact['is_pql']  # Original PQL flag from contact
        is_pql = False
        if is_pql_flag and pql_date and (start_dt <= pql_date <= end_dt):
            is_pql = True
        # is_customer will be determined after analyzing deals (see below)
        
        # Determine PQL timing relative to contact creation
        pql_timing_relative_to_contact = None
        days_pql_after_contact = None
        if is_pql and pql_date and contact_created:
            # IMPORTANT: fecha_activo is date-only (no time), while createdate has full timestamp
            # If both dates are on the same calendar day, consider as same day (0 days)
            if pql_date.date() == contact_created.date():
                days_pql_after_contact = 0  # Same day conversion
            else:
                days_pql_after_contact = (pql_date - contact_created).days
                # If still negative after same-day check, treat as same day
                if days_pql_after_contact < 0:
                    days_pql_after_contact = 0
            
            # Categorize timing
            if days_pql_after_contact == 0:
                pql_timing_relative_to_contact = 'pql_same_day'
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
        # First check deals from contact associations
        associated_deals = [deal_lookup.get(deal_id) for deal_id in contact['associated_deal_ids'] if deal_id in deal_lookup]
        associated_deals = [d for d in associated_deals if d]  # Remove None values
        
        # Associated deals should already be populated from the reverse lookup
        # that we did in the main function (contact['associated_deal_ids'] was updated)
        # So we just need to use the deals we found
        
        # NEW SQL DEFINITION: SQL = Contact with hs_v2_date_entered_opportunity in period 
        # AND has a deal created between contact creation and SQL date (within period)
        is_sql = False
        if sql_date and (start_dt <= sql_date <= end_dt):
            # Validate: Contact must have a deal created between contact creation and SQL date (within period)
            contact_createdate = contact.get('createdate')
            if contact_createdate:
                contact_createdate_dt = parse_datetime(contact_createdate)
                sql_date_dt = parse_datetime(sql_date)
                
                if contact_createdate_dt and sql_date_dt:
                    # Check if any deal was created between contact creation and SQL date (within period)
                    for deal in associated_deals:
                        deal_createdate_str = deal.get('createdate')
                        if deal_createdate_str:
                            deal_createdate = parse_datetime(deal_createdate_str)
                            if deal_createdate:
                                # Deal must be created between contact creation and SQL date, AND within the period
                                if (contact_createdate_dt <= deal_createdate <= sql_date_dt and 
                                    start_dt <= deal_createdate <= end_dt):
            is_sql = True
                                    break
        
        # SQL = Deal Creation, so if contact is SQL, a deal was created
        has_deals = len(associated_deals) > 0
        
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
    print(f"\nKEY ASSUMPTION: SQL = Deal Creation")
    print(f"  • When a contact becomes SQL (enters 'Oportunidad' stage), a deal is created")
    print(f"  • Field: hs_v2_date_entered_opportunity = SQL conversion date = Deal creation date")
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
    print(f"\n🔍 SEARCHING FOR DEALS ASSOCIATED WITH ALL CONTACTS")
    print("   (Checking all contacts for deal associations to find customer dates)")
    
    # Get all unique deal IDs from contact associations first
    all_deal_ids = []
    for contact in contacts:
        all_deal_ids.extend(contact['associated_deal_ids'])
    
    unique_deal_ids_from_associations = list(set(all_deal_ids))
    print(f"   Found {len(unique_deal_ids_from_associations)} deals from contact associations")
    
    # Also search for deals by contact IDs (reverse lookup) for ALL contacts
    # This ensures we find all deals, even if associations didn't work
    deal_ids_from_contact_search = []
    contact_to_deal_ids_map = {}  # Map contact_id to list of deal_ids
    
    print(f"   Searching for deals associated with {len(contacts)} contacts...")
    for i, contact in enumerate(contacts):
        if (i + 1) % 50 == 0:
            print(f"   Progress: {i + 1}/{len(contacts)} contacts checked")
        
        contact_id = contact['contact_id']
        contact_deal_ids = []
        
        # Search for deals associated with this contact
        try:
            url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/deals"
            headers = {
                'Authorization': f'Bearer {HUBSPOT_API_KEY}',
                'Content-Type': 'application/json'
            }
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'results' in result:
                    contact_deal_ids = [deal['id'] for deal in result['results']]
                    deal_ids_from_contact_search.extend(contact_deal_ids)
                    contact_to_deal_ids_map[contact_id] = contact_deal_ids
                    continue
        except:
            pass
        
        # If v4 API doesn't work, try v3 associations API
        try:
            url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/{contact_id}/associations/deals"
            headers = {
                'Authorization': f'Bearer {HUBSPOT_API_KEY}',
                'Content-Type': 'application/json'
            }
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'results' in result:
                    contact_deal_ids = [deal['id'] for deal in result['results']]
                    deal_ids_from_contact_search.extend(contact_deal_ids)
                    contact_to_deal_ids_map[contact_id] = contact_deal_ids
        except:
            pass
    
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

