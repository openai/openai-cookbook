#!/usr/bin/env python3
"""
PQL CAUSALITY TIMING SEGMENTATION ANALYSIS
==========================================

This script isolates causality by segmenting PQL contacts based on timing:
1. PQL conversion BEFORE deal creation vs AFTER deal creation
2. PQL conversion BEFORE deal won vs AFTER deal won

Measures influence on:
- Conversion rates
- Speed to deal (contact → deal creation)
- Speed to close (deal creation → deal close)

Features:
- Parameterizable date ranges via command-line arguments
- Auto-generated period names or custom period descriptions
- Configurable HubSpot API key
- Comprehensive timing-based causality analysis

Usage:
  python pql_causality_timing_segmentation_analysis.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD [options]

Scope: First-time deals only
Data: Real HubSpot data via API
"""

import os
import sys
import requests
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict
import time
import argparse

# Set up current date context
TODAY = datetime.now()
CURRENT_YEAR = TODAY.year  # 2025
ANALYSIS_DATE = TODAY.strftime("%Y-%m-%d")

print(f"🎯 PQL CAUSALITY TIMING SEGMENTATION ANALYSIS")
print(f"📅 Analysis Date: {ANALYSIS_DATE}")
print(f"🔬 Isolating causality through precise timing segmentation")
print("=" * 80)

# HubSpot API configuration
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    raise ValueError("HUBSPOT_API_KEY environment variable is required")
BASE_URL = "https://api.hubapi.com"

def make_hubspot_request(endpoint, params=None, search_data=None):
    """Make authenticated request to HubSpot API with retry logic"""
    headers = {
        'Authorization': f'Bearer {HUBSPOT_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    url = f"{BASE_URL}{endpoint}"
    
    for attempt in range(3):
        try:
            if search_data:
                response = requests.post(url, headers=headers, json=search_data, timeout=30)
            else:
                response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                print(f"⏳ Rate limit hit, waiting 2 seconds...")
                time.sleep(2)
                continue
            else:
                print(f"❌ API Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            print(f"🔄 Request attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(1)
    
    return None

def fetch_all_contacts_comprehensive(start_date, end_date, period_name):
    """Fetch ALL contacts for Q1+Q2 2025 with comprehensive PQL and deal data"""
    print(f"\n🔍 EXTRACTING COMPREHENSIVE CONTACT DATA - {period_name}")
    print(f"📅 Date Range: {start_date} to {end_date}")
    
    # Convert dates to proper format
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    # Properties to fetch
    properties = [
        'email', 'firstname', 'lastname', 'createdate', 'lifecyclestage',
        'fecha_activo',  # VERIFIED: PQL timestamp field
        'activo',        # VERIFIED: PQL boolean field
        'num_associated_deals',
        'hs_lifecyclestage_customer_date',
        'hs_lifecyclestage_opportunity_date',
        'lead_source',
        'utm_source',
        'utm_campaign',
        'total_associated_deals_count'
    ]
    
    # Search filter for date range
    search_request = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "createdate",
                "operator": "BETWEEN", 
                "value": start_datetime,
                "highValue": end_datetime
            }]
        }],
        "properties": properties,
        "associations": ["deals"],
        "limit": 100
    }
    
    all_contacts = []
    after = None
    total_requests = 0
    pql_count = 0
    customer_count = 0
    
    print("📡 Starting comprehensive data extraction with deal associations...")
    
    while True:
        if after:
            search_request["after"] = after
            
        result = make_hubspot_request('/crm/v3/objects/contacts/search', search_data=search_request)
        
        if not result or 'results' not in result:
            break
            
        batch_contacts = result['results']
        
        for contact in batch_contacts:
            props = contact.get('properties', {})
            associations = contact.get('associations', {})
            
            # Extract and process contact data
            contact_data = {
                'contact_id': contact['id'],
                'email': props.get('email'),
                'createdate': props.get('createdate'),
                'lifecyclestage': props.get('lifecyclestage'),
                'fecha_activo': props.get('fecha_activo'),  # PQL timestamp
                'activo': props.get('activo'),              # PQL boolean
                'num_associated_deals': props.get('num_associated_deals', '0'),
                'customer_date': props.get('hs_lifecyclestage_customer_date'),
                'opportunity_date': props.get('hs_lifecyclestage_opportunity_date'),
                'lead_source': props.get('lead_source'),
                'utm_source': props.get('utm_source'),
                'utm_campaign': props.get('utm_campaign'),
                'associated_deal_ids': []
            }
            
            # Extract associated deal IDs
            if 'deals' in associations and 'results' in associations['deals']:
                contact_data['associated_deal_ids'] = [
                    deal['id'] for deal in associations['deals']['results']
                ]
            
            # Determine PQL status
            is_pql = props.get('activo') == 'true'
            contact_data['is_pql'] = is_pql
            
            # Determine customer status
            is_customer = props.get('lifecyclestage') == 'customer'
            contact_data['is_customer'] = is_customer
            
            # Count for progress tracking
            if is_pql:
                pql_count += 1
            if is_customer:
                customer_count += 1
            
            all_contacts.append(contact_data)
        
        total_requests += 1
        
        # Progress update every 5 requests
        if total_requests % 5 == 0:
            print(f"📈 Progress: {total_requests} requests, {len(all_contacts):,} contacts, {pql_count:,} PQLs, {customer_count:,} customers")
        
        # Check for next page
        if 'paging' in result and 'next' in result['paging']:
            after = result['paging']['next']['after']
        else:
            break
        
        time.sleep(0.1)
    
    print(f"✅ COMPLETE CONTACT EXTRACTION - {period_name}")
    print(f"📊 Total Contacts: {len(all_contacts):,}")
    print(f"🎯 PQL Contacts: {pql_count:,} ({pql_count/len(all_contacts)*100:.1f}%)")
    print(f"👥 Customer Contacts: {customer_count:,} ({customer_count/len(all_contacts)*100:.1f}%)")
    
    return all_contacts

def fetch_all_deals_with_timing(start_date, end_date, period_name):
    """Fetch all deals (created or closed) for the period with comprehensive timing data"""
    print(f"\n💰 EXTRACTING ALL DEALS WITH TIMING DATA - {period_name}")
    print(f"📅 Date Range: {start_date} to {end_date}")
    
    # Convert dates for deal filters - we want deals created OR closed in this period
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    # Properties to fetch for deals
    properties = [
        'dealname', 'amount', 'createdate', 'closedate', 'dealstage',
        'pipeline', 'dealtype', 'hs_closed_won_date', 'hs_closed_lost_date',
        'hs_deal_stage_probability'
    ]
    
    # Search for deals created OR closed in the period
    search_request = {
        "filterGroups": [
            {
                "filters": [
                    {"propertyName": "createdate", "operator": "BETWEEN", "value": start_datetime, "highValue": end_datetime}
                ]
            },
            {
                "filters": [
                    {"propertyName": "closedate", "operator": "BETWEEN", "value": start_datetime, "highValue": end_datetime}
                ]
            }
        ],
        "properties": properties,
        "associations": ["contacts"],
        "limit": 100
    }
    
    all_deals = []
    after = None
    total_requests = 0
    won_count = 0
    closed_count = 0
    
    print("📡 Starting comprehensive deal extraction...")
    
    while True:
        if after:
            search_request["after"] = after
            
        result = make_hubspot_request('/crm/v3/objects/deals/search', search_data=search_request)
        
        if not result or 'results' not in result:
            break
            
        batch_deals = result['results']
        
        for deal in batch_deals:
            props = deal.get('properties', {})
            associations = deal.get('associations', {})
            
            # Extract deal data
            deal_data = {
                'deal_id': deal['id'],
                'dealname': props.get('dealname'),
                'amount': props.get('amount'),
                'closedate': props.get('closedate'),
                'createdate': props.get('createdate'),
                'dealstage': props.get('dealstage'),
                'pipeline': props.get('pipeline'),
                'is_won': props.get('dealstage') in ['closedwon', '34692158'],
                'is_closed': props.get('dealstage') in ['closedwon', '34692158', 'closedlost', '31849274'],
                'hs_closed_won_date': props.get('hs_closed_won_date'),
                'hs_closed_lost_date': props.get('hs_closed_lost_date'),
                'associated_contact_ids': []
            }
            
            # Extract associated contact IDs
            if 'contacts' in associations and 'results' in associations['contacts']:
                deal_data['associated_contact_ids'] = [
                    contact['id'] for contact in associations['contacts']['results']
                ]
            
            if deal_data['is_won']:
                won_count += 1
            if deal_data['is_closed']:
                closed_count += 1
            
            all_deals.append(deal_data)
        
        total_requests += 1
        
        if total_requests % 3 == 0:
            print(f"📈 Deal progress: {total_requests} requests, {len(all_deals):,} deals, {won_count:,} won, {closed_count:,} closed")
        
        # Check for next page
        if 'paging' in result and 'next' in result['paging']:
            after = result['paging']['next']['after']
        else:
            break
            
        time.sleep(0.1)
    
    print(f"✅ COMPLETE DEAL EXTRACTION - {period_name}")
    print(f"💰 Total Deals: {len(all_deals):,}")
    print(f"🏆 Won Deals: {won_count:,} ({won_count/len(all_deals)*100:.1f}%)")
    print(f"🔒 Closed Deals: {closed_count:,} ({closed_count/len(all_deals)*100:.1f}%)")
    
    return all_deals

def create_timing_segments(contacts, deals):
    """Create comprehensive timing segments for causality analysis"""
    print(f"\n🔬 CREATING TIMING SEGMENTS FOR CAUSALITY ANALYSIS")
    
    # Create DataFrames with timezone normalization
    contacts_df = pd.DataFrame(contacts)
    deals_df = pd.DataFrame(deals)
    
    if contacts_df.empty or deals_df.empty:
        print("❌ No data available for analysis")
        return {}
    
    # Convert dates to datetime with timezone normalization
    contacts_df['createdate_dt'] = pd.to_datetime(contacts_df['createdate'], errors='coerce').dt.tz_localize(None)
    contacts_df['fecha_activo_dt'] = pd.to_datetime(contacts_df['fecha_activo'], errors='coerce')
    contacts_df['customer_date_dt'] = pd.to_datetime(contacts_df['customer_date'], errors='coerce').dt.tz_localize(None)
    
    deals_df['createdate_dt'] = pd.to_datetime(deals_df['createdate'], errors='coerce').dt.tz_localize(None)
    deals_df['closedate_dt'] = pd.to_datetime(deals_df['closedate'], errors='coerce').dt.tz_localize(None)
    deals_df['won_date_dt'] = pd.to_datetime(deals_df['hs_closed_won_date'], errors='coerce').dt.tz_localize(None)
    
    # Create comprehensive contact-deal mapping
    contact_deal_mapping = []
    
    print("🔗 Creating contact-deal associations...")
    
    for _, contact in contacts_df.iterrows():
        contact_id = contact['contact_id']
        contact_deals = [deal_id for deal_id in contact['associated_deal_ids'] if deal_id]
        
        if not contact_deals:
            # Contact with no deals
            mapping_row = {
                'contact_id': contact_id,
                'email': contact['email'],
                'contact_createdate': contact['createdate_dt'],
                'fecha_activo': contact['fecha_activo_dt'],
                'is_pql': contact['is_pql'],
                'is_customer': contact['is_customer'],
                'has_deals': False,
                'deal_id': None,
                'deal_createdate': None,
                'deal_closedate': None,
                'deal_won_date': None,
                'is_won': False,
                'is_closed': False,
                'amount': None
            }
            contact_deal_mapping.append(mapping_row)
        else:
            # Contact with deals
            for deal_id in contact_deals:
                deal_match = deals_df[deals_df['deal_id'] == deal_id]
                
                if not deal_match.empty:
                    deal = deal_match.iloc[0]
                    
                    mapping_row = {
                        'contact_id': contact_id,
                        'email': contact['email'],
                        'contact_createdate': contact['createdate_dt'],
                        'fecha_activo': contact['fecha_activo_dt'],
                        'is_pql': contact['is_pql'],
                        'is_customer': contact['is_customer'],
                        'has_deals': True,
                        'deal_id': deal_id,
                        'deal_createdate': deal['createdate_dt'],
                        'deal_closedate': deal['closedate_dt'],
                        'deal_won_date': deal['won_date_dt'],
                        'is_won': deal['is_won'],
                        'is_closed': deal['is_closed'],
                        'amount': deal['amount']
                    }
                    contact_deal_mapping.append(mapping_row)
    
    # Create final mapping DataFrame
    mapping_df = pd.DataFrame(contact_deal_mapping)
    
    print(f"📊 Contact-Deal Mapping Created:")
    print(f"   Total Contact-Deal Records: {len(mapping_df):,}")
    print(f"   Contacts with Deals: {mapping_df['has_deals'].sum():,}")
    print(f"   PQL Records: {mapping_df['is_pql'].sum():,}")
    
    # Filter for first-time deals only (earliest deal per contact)
    print("\n🎯 FILTERING FOR FIRST-TIME DEALS ONLY")
    
    # For contacts with multiple deals, keep only the earliest deal
    contacts_with_deals = mapping_df[mapping_df['has_deals'] == True].copy()
    
    if not contacts_with_deals.empty:
        # Sort by contact_id and deal_createdate, keep first deal per contact
        contacts_with_deals = contacts_with_deals.sort_values(['contact_id', 'deal_createdate'])
        first_time_deals = contacts_with_deals.groupby('contact_id').first().reset_index()
        
        # Add back contacts with no deals
        contacts_no_deals = mapping_df[mapping_df['has_deals'] == False].copy()
        final_mapping = pd.concat([first_time_deals, contacts_no_deals], ignore_index=True)
    else:
        final_mapping = mapping_df.copy()
    
    print(f"📊 First-Time Deals Filter Applied:")
    print(f"   Total Records: {len(final_mapping):,}")
    print(f"   Unique Contacts: {final_mapping['contact_id'].nunique():,}")
    print(f"   First-Time Deals: {final_mapping['has_deals'].sum():,}")
    
    # Create timing segments for PQL contacts only
    pql_records = final_mapping[final_mapping['is_pql'] == True].copy()
    
    if pql_records.empty:
        print("❌ No PQL records found for timing analysis")
        return {}
    
    print(f"\n🔬 CREATING TIMING SEGMENTS FOR {len(pql_records):,} PQL RECORDS")
    
    # Segment 1: PQL timing relative to DEAL CREATION
    pql_records['pql_before_deal_creation'] = pd.NaT
    pql_records['days_pql_to_deal_creation'] = np.nan
    
    # Segment 2: PQL timing relative to DEAL WON/CLOSE
    pql_records['pql_before_deal_won'] = pd.NaT  
    pql_records['days_pql_to_deal_close'] = np.nan
    
    for idx, row in pql_records.iterrows():
        if pd.notna(row['fecha_activo']) and row['has_deals']:
            # Timing relative to deal creation
            if pd.notna(row['deal_createdate']):
                pql_records.loc[idx, 'pql_before_deal_creation'] = row['fecha_activo'] < row['deal_createdate']
                pql_records.loc[idx, 'days_pql_to_deal_creation'] = (row['deal_createdate'] - row['fecha_activo']).days
            
            # Timing relative to deal won/close
            if pd.notna(row['deal_closedate']) and row['is_closed']:
                pql_records.loc[idx, 'pql_before_deal_won'] = row['fecha_activo'] < row['deal_closedate']
                pql_records.loc[idx, 'days_pql_to_deal_close'] = (row['deal_closedate'] - row['fecha_activo']).days
    
    # Create timing segment groups
    timing_segments = {
        'pql_before_deal_creation': pql_records[pql_records['pql_before_deal_creation'] == True],
        'pql_after_deal_creation': pql_records[pql_records['pql_before_deal_creation'] == False],
        'pql_before_deal_won': pql_records[pql_records['pql_before_deal_won'] == True],
        'pql_after_deal_won': pql_records[pql_records['pql_before_deal_won'] == False],
        'pql_no_deals': pql_records[pql_records['has_deals'] == False],
        'all_pql': pql_records,
        'all_non_pql': final_mapping[final_mapping['is_pql'] == False]
    }
    
    # Print segment summary
    print(f"\n📊 TIMING SEGMENT SUMMARY:")
    for segment_name, segment_df in timing_segments.items():
        if not segment_df.empty:
            print(f"   {segment_name}: {len(segment_df):,} records")
    
    return timing_segments, final_mapping

def analyze_causality_metrics(timing_segments, final_mapping):
    """Analyze causality metrics across timing segments"""
    print(f"\n📈 CAUSALITY ANALYSIS ACROSS TIMING SEGMENTS")
    
    results = {}
    
    # Define analysis segments
    analysis_segments = {
        'PQL Before Deal Creation': timing_segments['pql_before_deal_creation'],
        'PQL After Deal Creation': timing_segments['pql_after_deal_creation'],
        'PQL Before Deal Won': timing_segments['pql_before_deal_won'],
        'PQL After Deal Won': timing_segments['pql_after_deal_won'],
        'All PQL': timing_segments['all_pql'],
        'All Non-PQL': timing_segments['all_non_pql']
    }
    
    print(f"🔍 Analyzing {len(analysis_segments)} timing segments...")
    
    for segment_name, segment_df in analysis_segments.items():
        if segment_df.empty:
            print(f"⚠️ {segment_name}: No data available")
            continue
            
        segment_metrics = {}
        
        # Basic counts
        total_contacts = len(segment_df)
        customers = segment_df['is_customer'].sum()
        deals = segment_df['has_deals'].sum()
        won_deals = segment_df['is_won'].sum()
        
        # Conversion rates
        customer_conversion_rate = (customers / total_contacts * 100) if total_contacts > 0 else 0
        deal_conversion_rate = (deals / total_contacts * 100) if total_contacts > 0 else 0
        win_rate = (won_deals / deals * 100) if deals > 0 else 0
        
        # Speed metrics (only for records with deals)
        deals_data = segment_df[segment_df['has_deals'] == True]
        
        if not deals_data.empty:
            # Speed to deal (contact creation → deal creation)
            deals_data = deals_data.copy()
            deals_data['days_to_deal'] = (deals_data['deal_createdate'] - deals_data['contact_createdate']).dt.days
            
            # Speed to close (deal creation → deal close, for closed deals only)
            closed_deals = deals_data[deals_data['is_closed'] == True]
            if not closed_deals.empty:
                closed_deals = closed_deals.copy()
                closed_deals['days_to_close'] = (closed_deals['deal_closedate'] - closed_deals['deal_createdate']).dt.days
                avg_days_to_close = closed_deals['days_to_close'].mean()
                median_days_to_close = closed_deals['days_to_close'].median()
            else:
                avg_days_to_close = np.nan
                median_days_to_close = np.nan
            
            avg_days_to_deal = deals_data['days_to_deal'].mean()
            median_days_to_deal = deals_data['days_to_deal'].median()
        else:
            avg_days_to_deal = np.nan
            median_days_to_deal = np.nan
            avg_days_to_close = np.nan
            median_days_to_close = np.nan
        
        # Revenue metrics
        if not deals_data.empty:
            # Convert amount to numeric, handle string amounts
            deals_data = deals_data.copy()
            deals_data['amount_numeric'] = pd.to_numeric(deals_data['amount'], errors='coerce')
            
            # Total revenue (won deals only)
            won_deals_data = deals_data[deals_data['is_won'] == True]
            total_revenue = won_deals_data['amount_numeric'].sum() if not won_deals_data.empty else 0
            avg_deal_size = won_deals_data['amount_numeric'].mean() if not won_deals_data.empty else 0
        else:
            total_revenue = 0
            avg_deal_size = 0
        
        segment_metrics = {
            'segment_name': segment_name,
            'total_contacts': total_contacts,
            'customers': customers,
            'deals': deals,
            'won_deals': won_deals,
            'customer_conversion_rate': customer_conversion_rate,
            'deal_conversion_rate': deal_conversion_rate,
            'win_rate': win_rate,
            'avg_days_to_deal': avg_days_to_deal,
            'median_days_to_deal': median_days_to_deal,
            'avg_days_to_close': avg_days_to_close,
            'median_days_to_close': median_days_to_close,
            'total_revenue': total_revenue,
            'avg_deal_size': avg_deal_size
        }
        
        results[segment_name] = segment_metrics
        
        print(f"\n📊 {segment_name.upper()}:")
        print(f"   Total Contacts: {total_contacts:,}")
        print(f"   Customer Conversion: {customer_conversion_rate:.1f}%")
        print(f"   Deal Conversion: {deal_conversion_rate:.1f}%")
        print(f"   Win Rate: {win_rate:.1f}%")
        if not np.isnan(avg_days_to_deal):
            print(f"   Avg Days to Deal: {avg_days_to_deal:.1f}")
        if not np.isnan(avg_days_to_close):
            print(f"   Avg Days to Close: {avg_days_to_close:.1f}")
        if total_revenue > 0:
            print(f"   Total Revenue: ${total_revenue:,.0f}")
    
    return results

def generate_causality_report(results, analysis_period):
    """Generate comprehensive causality analysis report"""
    print(f"\n📋 COMPREHENSIVE CAUSALITY ANALYSIS REPORT")
    print("=" * 80)
    print(f"📅 Analysis Period: {analysis_period}")
    print(f"🔬 Analysis Type: PQL Timing Segmentation for Causality Isolation")
    print(f"📊 Data Scope: First-time deals only, Q1+Q2 2025 (excluding June 26+)")
    
    # Key findings summary
    print(f"\n🎯 KEY CAUSALITY FINDINGS:")
    
    # Compare PQL Before vs After Deal Creation
    if 'PQL Before Deal Creation' in results and 'PQL After Deal Creation' in results:
        before_creation = results['PQL Before Deal Creation']
        after_creation = results['PQL After Deal Creation']
        
        conversion_diff = before_creation['customer_conversion_rate'] - after_creation['customer_conversion_rate']
        deal_diff = before_creation['deal_conversion_rate'] - after_creation['deal_conversion_rate']
        
        print(f"\n📈 PQL TIMING vs DEAL CREATION:")
        print(f"   PQL Before Deal Creation: {before_creation['customer_conversion_rate']:.1f}% conversion")
        print(f"   PQL After Deal Creation: {after_creation['customer_conversion_rate']:.1f}% conversion")
        print(f"   → Difference: {conversion_diff:+.1f} percentage points")
        
        if not np.isnan(before_creation['avg_days_to_close']) and not np.isnan(after_creation['avg_days_to_close']):
            close_speed_diff = before_creation['avg_days_to_close'] - after_creation['avg_days_to_close']
            print(f"   → Speed to Close Difference: {close_speed_diff:+.1f} days")
    
    # Compare PQL Before vs After Deal Won
    if 'PQL Before Deal Won' in results and 'PQL After Deal Won' in results:
        before_won = results['PQL Before Deal Won']
        after_won = results['PQL After Deal Won']
        
        conversion_diff_won = before_won['customer_conversion_rate'] - after_won['customer_conversion_rate']
        
        print(f"\n🏆 PQL TIMING vs DEAL CLOSURE:")
        print(f"   PQL Before Deal Won: {before_won['customer_conversion_rate']:.1f}% conversion")
        print(f"   PQL After Deal Won: {after_won['customer_conversion_rate']:.1f}% conversion")
        print(f"   → Difference: {conversion_diff_won:+.1f} percentage points")
    
    # Compare All PQL vs Non-PQL
    if 'All PQL' in results and 'All Non-PQL' in results:
        all_pql = results['All PQL']
        all_non_pql = results['All Non-PQL']
        
        overall_diff = all_pql['customer_conversion_rate'] - all_non_pql['customer_conversion_rate']
        
        print(f"\n🎯 OVERALL PQL EFFECTIVENESS:")
        print(f"   All PQL: {all_pql['customer_conversion_rate']:.1f}% conversion")
        print(f"   All Non-PQL: {all_non_pql['customer_conversion_rate']:.1f}% conversion")
        print(f"   → Overall PQL Advantage: {overall_diff:+.1f} percentage points")
    
    # Detailed metrics table
    print(f"\n📊 DETAILED CAUSALITY METRICS TABLE:")
    print(f"{'Segment':<25} {'Contacts':<10} {'Conv%':<8} {'Deal%':<8} {'Win%':<8} {'Days2Deal':<10} {'Days2Close':<11} {'Revenue':<12}")
    print("-" * 110)
    
    for segment_name, metrics in results.items():
        days_to_deal = f"{metrics['avg_days_to_deal']:.1f}" if not np.isnan(metrics['avg_days_to_deal']) else "N/A"
        days_to_close = f"{metrics['avg_days_to_close']:.1f}" if not np.isnan(metrics['avg_days_to_close']) else "N/A"
        revenue = f"${metrics['total_revenue']:,.0f}" if metrics['total_revenue'] > 0 else "$0"
        
        print(f"{segment_name:<25} {metrics['total_contacts']:<10,} {metrics['customer_conversion_rate']:<8.1f} {metrics['deal_conversion_rate']:<8.1f} {metrics['win_rate']:<8.1f} {days_to_deal:<10} {days_to_close:<11} {revenue:<12}")
    
    # Causality conclusions
    print(f"\n🔬 CAUSALITY CONCLUSIONS:")
    
    if 'PQL Before Deal Creation' in results and 'PQL After Deal Creation' in results:
        before_creation = results['PQL Before Deal Creation']
        after_creation = results['PQL After Deal Creation']
        
        if before_creation['customer_conversion_rate'] > after_creation['customer_conversion_rate']:
            print(f"   ✅ PQL events BEFORE deal creation show higher conversion rates")
            print(f"      → Supports causal relationship (PQL drives deal creation)")
        else:
            print(f"   ⚠️ PQL events AFTER deal creation show higher conversion rates")
            print(f"      → May indicate deal creation drives PQL behavior")
    
    if 'PQL Before Deal Won' in results and 'PQL After Deal Won' in results:
        before_won = results['PQL Before Deal Won']
        after_won = results['PQL After Deal Won']
        
        if before_won['customer_conversion_rate'] > after_won['customer_conversion_rate']:
            print(f"   ✅ PQL events BEFORE deal closure show higher conversion rates")
            print(f"      → Supports causal relationship (PQL drives conversion)")
        else:
            print(f"   ⚠️ PQL events AFTER deal closure show higher conversion rates")
            print(f"      → May indicate reverse causation")
    
    # Strategic recommendations
    print(f"\n📋 STRATEGIC RECOMMENDATIONS:")
    print(f"   🎯 Use timing analysis for lead qualification")
    print(f"   ⏰ Prioritize PQL events that precede deal milestones")
    print(f"   🔧 Implement PQL-triggered sales automation")
    print(f"   📊 Monitor causality patterns over time")
    
    return results

def parse_arguments():
    """Parse command-line arguments for PQL analysis parameters"""
    parser = argparse.ArgumentParser(
        description='PQL Causality Timing Segmentation Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze Q1 2025
  python pql_causality_timing_segmentation_analysis.py --start-date 2025-01-01 --end-date 2025-03-31

  # Analyze specific month
  python pql_causality_timing_segmentation_analysis.py --start-date 2025-06-01 --end-date 2025-06-30

  # Analyze year-to-date
  python pql_causality_timing_segmentation_analysis.py --start-date 2025-01-01 --end-date 2025-07-18

  # Use custom period name
  python pql_causality_timing_segmentation_analysis.py --start-date 2025-04-01 --end-date 2025-06-30 --period-name "Q2 2025"
        """
    )
    
    parser.add_argument(
        '--start-date', 
        required=True,
        help='Start date for analysis in YYYY-MM-DD format (e.g., 2025-01-01)'
    )
    
    parser.add_argument(
        '--end-date', 
        required=True,
        help='End date for analysis in YYYY-MM-DD format (e.g., 2025-06-30)'
    )
    
    parser.add_argument(
        '--period-name',
        help='Custom name for the analysis period (e.g., "Q1 2025" or "January 2025"). If not provided, will be auto-generated from dates.'
    )
    
    parser.add_argument(
        '--api-key',
        help='HubSpot API key. If not provided, will use HUBSPOT_API_KEY environment variable.'
    )
    
    args = parser.parse_args()
    
    # Validate date format
    try:
        start_dt = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(args.end_date, '%Y-%m-%d')
        
        if start_dt >= end_dt:
            parser.error("Start date must be before end date")
            
    except ValueError as e:
        parser.error(f"Invalid date format: {e}. Use YYYY-MM-DD format.")
    
    # Generate period name if not provided
    if not args.period_name:
        start_month = start_dt.strftime('%b')
        end_month = end_dt.strftime('%b')
        year = start_dt.year
        
        if start_dt.year != end_dt.year:
            args.period_name = f"{start_month} {start_dt.year} - {end_month} {end_dt.year}"
        elif start_month == end_month:
            args.period_name = f"{start_month} {year}"
        else:
            args.period_name = f"{start_month} - {end_month} {year}"
    
    return args

def main():
    """Main execution function for causality timing analysis"""
    # Parse command-line arguments
    args = parse_arguments()
    
    # Override API key if provided
    global HUBSPOT_API_KEY
    if args.api_key:
        HUBSPOT_API_KEY = args.api_key
    
    print(f"🚀 Starting PQL Causality Timing Segmentation Analysis")
    print(f"🔑 Using HubSpot API Key: {HUBSPOT_API_KEY[:10]}...")
    
    try:
        # Use provided dates and period name
        start_date = args.start_date
        end_date = args.end_date
        analysis_period = args.period_name
        
        print(f"\n📅 Analysis Period: {analysis_period}")
        print(f"🎯 Scope: First-time deals only")
        print(f"🔬 Method: Timing segmentation for causality isolation")
        
        # Fetch comprehensive contact data
        contacts = fetch_all_contacts_comprehensive(start_date, end_date, analysis_period)
        
        # Fetch comprehensive deal data
        deals = fetch_all_deals_with_timing(start_date, end_date, analysis_period)
        
        # Create timing segments
        timing_segments, final_mapping = create_timing_segments(contacts, deals)
        
        # Analyze causality metrics
        results = analyze_causality_metrics(timing_segments, final_mapping)
        
        # Generate comprehensive report
        final_report = generate_causality_report(results, analysis_period)
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Create a safe filename from the date range
        safe_start = start_date.replace('-', '')
        safe_end = end_date.replace('-', '')
        
        # Ensure tools/outputs directory exists
        os.makedirs("tools/outputs", exist_ok=True)
        output_file = f"tools/outputs/pql_causality_timing_analysis_{safe_start}_{safe_end}_{timestamp}.json"
        
        # Prepare results for JSON serialization
        json_results = {}
        for segment_name, metrics in results.items():
            json_results[segment_name] = {
                k: float(v) if isinstance(v, (np.integer, np.floating)) and not np.isnan(v) else 
                   None if (isinstance(v, (np.integer, np.floating)) and np.isnan(v)) else v
                for k, v in metrics.items()
            }
        
        final_output = {
            'analysis_date': ANALYSIS_DATE,
            'analysis_period': analysis_period,
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            },
            'methodology': 'PQL Timing Segmentation for Causality Isolation',
            'scope': 'First-time deals only',
            'results': json_results,
            'summary': {
                'total_contacts_analyzed': len(final_mapping),
                'pql_contacts': final_mapping['is_pql'].sum(),
                'contacts_with_deals': final_mapping['has_deals'].sum(),
                'unique_contacts': final_mapping['contact_id'].nunique()
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(final_output, f, indent=2, default=str)
        
        print(f"\n💾 Causality analysis results saved to: {output_file}")
        print(f"📊 Analysis Parameters:")
        print(f"   📅 Date Range: {start_date} to {end_date}")
        print(f"   🏷️  Period Name: {analysis_period}")
        print(f"   📈 Contacts Analyzed: {len(final_mapping):,}")
        
        return final_output
        
    except Exception as e:
        print(f"❌ Error during causality analysis: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    results = main() 