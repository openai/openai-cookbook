#!/usr/bin/env python3
"""
DEAL-FOCUSED PQL ANALYSIS
========================
Analyzes PQL effectiveness based on actual deal wins and revenue generation,
not lifecycle stage changes.

Key Metrics:
- Deal Attachment Rate: % of contacts associated with deals
- Deal Win Rate: % of contacts with won deals 
- Revenue per Contact: Average revenue generated per contact segment
- Sales Velocity: Time from contact → deal → win

Usage:
  python deal_focused_pql_analysis.py --start-date 2025-07-01 --end-date 2025-07-30
"""

import requests
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import argparse
import time

# HubSpot API Configuration
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    raise ValueError("HUBSPOT_API_KEY environment variable is required")
HUBSPOT_BASE_URL = 'https://api.hubapi.com'

def make_hubspot_request(endpoint, search_data=None, timeout=30):
    """Make authenticated request to HubSpot API with error handling"""
    url = f"{HUBSPOT_BASE_URL}{endpoint}"
    headers = {
        'Authorization': f'Bearer {HUBSPOT_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        if search_data:
            response = requests.post(url, headers=headers, json=search_data, timeout=timeout)
        else:
            response = requests.get(url, headers=headers, timeout=timeout)
        
        if response.status_code == 429:
            print("⏳ Rate limited, waiting 10 seconds...")
            time.sleep(10)
            return make_hubspot_request(endpoint, search_data, timeout)
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"❌ API request failed: {e}")
        return None

def fetch_contacts_with_pql(start_date, end_date):
    """Fetch contacts created in period with PQL and basic info"""
    print(f"\n📞 FETCHING CONTACTS - DEAL-FOCUSED ANALYSIS")
    print(f"📅 Date Range: {start_date} to {end_date}")
    
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    properties = [
        'email', 'firstname', 'lastname', 'createdate', 'lifecyclestage',
        'activo', 'fecha_activo', 'hs_lifecyclestage_customer_date'
    ]
    
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
        "associations": ["deals"],  # Key: get deal associations
        "limit": 100
    }
    
    all_contacts = []
    after = None
    total_requests = 0
    
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
            
            # Extract contact data
            contact_data = {
                'contact_id': contact['id'],
                'email': props.get('email'),
                'firstname': props.get('firstname'),
                'lastname': props.get('lastname'),
                'createdate': props.get('createdate'),
                'lifecyclestage': props.get('lifecyclestage'),
                'is_pql': props.get('activo') == 'true',
                'pql_date': props.get('fecha_activo'),
                'is_customer': props.get('lifecyclestage') == 'customer',
                'customer_date': props.get('hs_lifecyclestage_customer_date'),
                'associated_deal_ids': []
            }
            
            # Extract associated deal IDs (KEY DIFFERENCE)
            if 'deals' in associations and 'results' in associations['deals']:
                contact_data['associated_deal_ids'] = [
                    deal['id'] for deal in associations['deals']['results']
                ]
            
            all_contacts.append(contact_data)
        
        total_requests += 1
        if total_requests % 5 == 0:
            pql_count = sum(1 for c in all_contacts if c['is_pql'])
            print(f"📈 Progress: {total_requests} requests, {len(all_contacts)} contacts, {pql_count} PQLs")
        
        if 'paging' not in result or 'next' not in result['paging']:
            break
        after = result['paging']['next']['after']
    
    print(f"✅ CONTACTS EXTRACTED: {len(all_contacts)} total")
    pql_count = sum(1 for c in all_contacts if c['is_pql'])
    print(f"🎯 PQL Contacts: {pql_count} ({pql_count/len(all_contacts)*100:.1f}%)")
    
    return all_contacts

def fetch_deal_details(deal_ids):
    """Fetch detailed information for specific deals"""
    if not deal_ids:
        return []
    
    print(f"\n💰 FETCHING DEAL DETAILS FOR {len(deal_ids)} DEALS")
    
    properties = [
        'dealname', 'amount', 'createdate', 'closedate', 'dealstage',
        'pipeline', 'hs_closed_won_date', 'hs_closed_lost_date'
    ]
    
    # Batch read deals (up to 100 at a time)
    all_deals = []
    
    for i in range(0, len(deal_ids), 100):
        batch_ids = deal_ids[i:i+100]
        
        inputs = [{"id": deal_id} for deal_id in batch_ids]
        
        request_data = {
            "properties": properties,
            "inputs": inputs
        }
        
        result = make_hubspot_request('/crm/v3/objects/deals/batch/read', search_data=request_data)
        
        if result and 'results' in result:
            for deal in result['results']:
                props = deal.get('properties', {})
                
                deal_data = {
                    'deal_id': deal['id'],
                    'dealname': props.get('dealname'),
                    'amount': props.get('amount'),
                    'createdate': props.get('createdate'),
                    'closedate': props.get('closedate'),
                    'dealstage': props.get('dealstage'),
                    'pipeline': props.get('pipeline'),
                    'is_won': props.get('dealstage') in ['closedwon', '34692158'],
                    'is_closed': props.get('dealstage') in ['closedwon', '34692158', 'closedlost', '31849274'],
                    'hs_closed_won_date': props.get('hs_closed_won_date'),
                    'hs_closed_lost_date': props.get('hs_closed_lost_date')
                }
                
                all_deals.append(deal_data)
    
    won_deals = sum(1 for d in all_deals if d['is_won'])
    print(f"💰 Deals Details Extracted: {len(all_deals)} total, {won_deals} won")
    
    return all_deals

def analyze_deal_focused_metrics(contacts, deals):
    """Analyze PQL effectiveness using deal-focused metrics"""
    print(f"\n🎯 DEAL-FOCUSED CAUSALITY ANALYSIS")
    print("=" * 50)
    
    # Create deal lookup for fast access
    deal_lookup = {deal['deal_id']: deal for deal in deals}
    
    # Create contact analysis dataframe
    contact_data = []
    
    for contact in contacts:
        # Basic contact info
        row = {
            'contact_id': contact['contact_id'],
            'email': contact['email'],
            'is_pql': contact['is_pql'],
            'is_customer': contact['is_customer'],
            'associated_deal_count': len(contact['associated_deal_ids'])
        }
        
        # Deal-focused metrics
        associated_deals = [deal_lookup.get(deal_id) for deal_id in contact['associated_deal_ids'] if deal_id in deal_lookup]
        
        row['has_deals'] = len(associated_deals) > 0
        row['won_deals_count'] = sum(1 for deal in associated_deals if deal and deal['is_won'])
        row['has_won_deals'] = row['won_deals_count'] > 0
        
        # Revenue calculation
        won_deals = [deal for deal in associated_deals if deal and deal['is_won']]
        row['total_revenue'] = 0
        
        for deal in won_deals:
            if deal['amount']:
                try:
                    row['total_revenue'] += float(deal['amount'])
                except (ValueError, TypeError):
                    pass
        
        contact_data.append(row)
    
    df = pd.DataFrame(contact_data)
    
    # Segment analysis
    segments = {
        'PQL': df[df['is_pql'] == True],
        'Non-PQL': df[df['is_pql'] == False]
    }
    
    results = {}
    
    print("📊 DEAL-FOCUSED PERFORMANCE METRICS:")
    print("=" * 40)
    
    for segment_name, segment_df in segments.items():
        if segment_df.empty:
            continue
        
        total_contacts = len(segment_df)
        
        # DEAL-FOCUSED METRICS
        contacts_with_deals = segment_df['has_deals'].sum()
        contacts_with_won_deals = segment_df['has_won_deals'].sum()
        total_won_deals = segment_df['won_deals_count'].sum()
        total_revenue = segment_df['total_revenue'].sum()
        
        # DEAL-FOCUSED RATES
        deal_attachment_rate = (contacts_with_deals / total_contacts * 100) if total_contacts > 0 else 0
        deal_win_rate = (contacts_with_won_deals / total_contacts * 100) if total_contacts > 0 else 0
        revenue_per_contact = total_revenue / total_contacts if total_contacts > 0 else 0
        
        # LEGACY METRICS (for comparison)
        legacy_customers = segment_df['is_customer'].sum()
        legacy_customer_rate = (legacy_customers / total_contacts * 100) if total_contacts > 0 else 0
        
        # Store results
        results[segment_name] = {
            'total_contacts': total_contacts,
            'contacts_with_deals': contacts_with_deals,
            'contacts_with_won_deals': contacts_with_won_deals,
            'total_won_deals': total_won_deals,
            'deal_attachment_rate': deal_attachment_rate,
            'deal_win_rate': deal_win_rate,
            'revenue_per_contact': revenue_per_contact,
            'total_revenue': total_revenue,
            'legacy_customers': legacy_customers,
            'legacy_customer_rate': legacy_customer_rate
        }
        
        # Print results
        print(f"\n🎯 {segment_name.upper()}:")
        print(f"   Total Contacts: {total_contacts:,}")
        print(f"   📊 Deal Attachment Rate: {deal_attachment_rate:.1f}% ({contacts_with_deals} contacts with deals)")
        print(f"   🏆 Deal Win Rate: {deal_win_rate:.1f}% ({contacts_with_won_deals} contacts with won deals)")
        print(f"   💰 Total Won Deals: {total_won_deals}")
        print(f"   💲 Revenue per Contact: ${revenue_per_contact:,.0f}")
        print(f"   💵 Total Revenue: ${total_revenue:,.0f}")
        print(f"   📋 Legacy Customer Rate: {legacy_customer_rate:.1f}% (for comparison)")
    
    # Calculate advantage
    if 'PQL' in results and 'Non-PQL' in results:
        pql_data = results['PQL']
        non_pql_data = results['Non-PQL']
        
        deal_attachment_advantage = pql_data['deal_attachment_rate'] - non_pql_data['deal_attachment_rate']
        deal_win_advantage = pql_data['deal_win_rate'] - non_pql_data['deal_win_rate']
        revenue_advantage = pql_data['revenue_per_contact'] - non_pql_data['revenue_per_contact']
        
        print(f"\n🎯 PQL ADVANTAGE ANALYSIS:")
        print("=" * 30)
        print(f"📊 Deal Attachment Advantage: {deal_attachment_advantage:+.1f}pp")
        print(f"🏆 Deal Win Advantage: {deal_win_advantage:+.1f}pp")
        print(f"💰 Revenue per Contact Advantage: ${revenue_advantage:+,.0f}")
        
        results['advantage_metrics'] = {
            'deal_attachment_advantage': deal_attachment_advantage,
            'deal_win_advantage': deal_win_advantage,
            'revenue_advantage': revenue_advantage
        }
    
    return results, df

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='Deal-Focused PQL Analysis')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--period-name', help='Custom period name')
    parser.add_argument('--api-key', help='HubSpot API key. If not provided, will use HUBSPOT_API_KEY environment variable.')
    
    args = parser.parse_args()
    
    global HUBSPOT_API_KEY
    if args.api_key:
        HUBSPOT_API_KEY = args.api_key
    
    period_name = args.period_name or f"{args.start_date} to {args.end_date}"
    
    print(f"🎯 DEAL-FOCUSED PQL ANALYSIS")
    print(f"📅 Period: {period_name}")
    print(f"🔑 Using HubSpot API Key: {HUBSPOT_API_KEY[:10]}...")
    print("=" * 60)
    
    # Step 1: Fetch contacts with deal associations
    contacts = fetch_contacts_with_pql(args.start_date, args.end_date)
    
    if not contacts:
        print("❌ No contacts found for the period")
        return
    
    # Step 2: Get all unique deal IDs
    all_deal_ids = []
    for contact in contacts:
        all_deal_ids.extend(contact['associated_deal_ids'])
    
    unique_deal_ids = list(set(all_deal_ids))
    print(f"\n📊 Found {len(unique_deal_ids)} unique deals associated with contacts")
    
    # Step 3: Fetch deal details
    deals = fetch_deal_details(unique_deal_ids) if unique_deal_ids else []
    
    # Step 4: Analyze deal-focused metrics
    results, contact_df = analyze_deal_focused_metrics(contacts, deals)
    
    # Step 5: Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('tools/outputs', exist_ok=True)
    
    output_data = {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'period': period_name,
        'date_range': {
            'start_date': args.start_date,
            'end_date': args.end_date
        },
        'methodology': 'Deal-Focused PQL Analysis',
        'total_contacts_analyzed': len(contacts),
        'total_deals_found': len(deals),
        'results': results
    }
    
    safe_start = args.start_date.replace('-', '')
    safe_end = args.end_date.replace('-', '')
    output_file = f"tools/outputs/deal_focused_pql_analysis_{safe_start}_{safe_end}_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    return results

if __name__ == "__main__":
    main()