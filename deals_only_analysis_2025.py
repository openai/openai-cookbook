#!/usr/bin/env python3
"""
DEALS-ONLY ANALYSIS 2025
========================
Direct analysis of deals created/closed in 2025 to understand if deals exist
but are simply not associated with contacts or companies.
"""

import requests
import json
import pandas as pd
from datetime import datetime
import os
import time

# HubSpot API Configuration
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
if not HUBSPOT_API_KEY:
    raise ValueError("HUBSPOT_API_KEY environment variable is required")
HUBSPOT_BASE_URL = 'https://api.hubapi.com'

def make_hubspot_request(endpoint, search_data=None, timeout=30):
    """Make authenticated request to HubSpot API"""
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

def fetch_deals_created_2025():
    """Fetch all deals created in 2025"""
    print(f"\n💰 FETCHING DEALS CREATED IN 2025")
    
    start_datetime = "2025-01-01T00:00:00.000Z"
    end_datetime = "2025-07-31T23:59:59.999Z"
    
    properties = [
        'dealname', 'amount', 'createdate', 'closedate', 'dealstage',
        'pipeline', 'dealtype', 'hs_closed_won_date', 'hs_closed_lost_date',
        'hs_deal_stage_probability'
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
        "associations": ["contacts", "companies"],  # Check for associations
        "limit": 100
    }
    
    all_deals = []
    after = None
    total_requests = 0
    won_count = 0
    closed_count = 0
    deals_with_contacts = 0
    deals_with_companies = 0
    
    print("📡 Starting deal extraction...")
    
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
            
            # Check associations
            has_contacts = 'contacts' in associations and associations['contacts'].get('results')
            has_companies = 'companies' in associations and associations['companies'].get('results')
            
            if has_contacts:
                deals_with_contacts += 1
            if has_companies:
                deals_with_companies += 1
            
            deal_data = {
                'deal_id': deal['id'],
                'dealname': props.get('dealname'),
                'amount': props.get('amount'),
                'createdate': props.get('createdate'),
                'closedate': props.get('closedate'),
                'dealstage': props.get('dealstage'),
                'pipeline': props.get('pipeline'),
                'dealtype': props.get('dealtype'),
                'is_won': props.get('dealstage') in ['closedwon', '34692158'],
                'is_closed': props.get('dealstage') in ['closedwon', '34692158', 'closedlost', '31849274'],
                'hs_closed_won_date': props.get('hs_closed_won_date'),
                'hs_closed_lost_date': props.get('hs_closed_lost_date'),
                'has_contact_associations': has_contacts,
                'has_company_associations': has_companies,
                'contact_count': len(associations.get('contacts', {}).get('results', [])),
                'company_count': len(associations.get('companies', {}).get('results', []))
            }
            
            if deal_data['is_won']:
                won_count += 1
            if deal_data['is_closed']:
                closed_count += 1
            
            all_deals.append(deal_data)
        
        total_requests += 1
        if total_requests % 10 == 0:
            print(f"📈 Progress: {total_requests} requests, {len(all_deals)} deals, {won_count} won, {deals_with_contacts} with contacts, {deals_with_companies} with companies")
        
        if 'paging' not in result or 'next' not in result['paging']:
            break
        after = result['paging']['next']['after']
    
    print(f"✅ DEALS EXTRACTED: {len(all_deals)} total")
    print(f"🏆 Won Deals: {won_count}")
    print(f"🔒 Closed Deals: {closed_count}")
    print(f"👥 Deals with Contact Associations: {deals_with_contacts}")
    print(f"🏢 Deals with Company Associations: {deals_with_companies}")
    
    return all_deals

def fetch_deals_closed_2025():
    """Fetch all deals closed in 2025 (in addition to created)"""
    print(f"\n💰 FETCHING DEALS CLOSED IN 2025")
    
    start_datetime = "2025-01-01T00:00:00.000Z"
    end_datetime = "2025-07-31T23:59:59.999Z"
    
    properties = [
        'dealname', 'amount', 'createdate', 'closedate', 'dealstage',
        'pipeline', 'dealtype', 'hs_closed_won_date', 'hs_closed_lost_date'
    ]
    
    search_request = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "closedate",
                "operator": "BETWEEN", 
                "value": start_datetime,
                "highValue": end_datetime
            }]
        }],
        "properties": properties,
        "associations": ["contacts", "companies"],
        "limit": 100
    }
    
    all_deals = []
    after = None
    total_requests = 0
    
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
            
            has_contacts = 'contacts' in associations and associations['contacts'].get('results')
            has_companies = 'companies' in associations and associations['companies'].get('results')
            
            deal_data = {
                'deal_id': deal['id'],
                'dealname': props.get('dealname'),
                'amount': props.get('amount'),
                'createdate': props.get('createdate'),
                'closedate': props.get('closedate'),
                'dealstage': props.get('dealstage'),
                'is_won': props.get('dealstage') in ['closedwon', '34692158'],
                'is_closed': props.get('dealstage') in ['closedwon', '34692158', 'closedlost', '31849274'],
                'has_contact_associations': has_contacts,
                'has_company_associations': has_companies,
                'contact_count': len(associations.get('contacts', {}).get('results', [])),
                'company_count': len(associations.get('companies', {}).get('results', []))
            }
            
            all_deals.append(deal_data)
        
        total_requests += 1
        if total_requests % 5 == 0:
            print(f"📈 Progress: {total_requests} requests, {len(all_deals)} deals")
        
        if 'paging' not in result or 'next' not in result['paging']:
            break
        after = result['paging']['next']['after']
    
    return all_deals

def analyze_deals_comprehensive(created_deals, closed_deals):
    """Comprehensive analysis of deal data"""
    print(f"\n🎯 COMPREHENSIVE DEAL ANALYSIS")
    print("=" * 40)
    
    # Combine and deduplicate deals
    all_deals_dict = {}
    
    for deal in created_deals:
        all_deals_dict[deal['deal_id']] = deal
    
    for deal in closed_deals:
        if deal['deal_id'] not in all_deals_dict:
            all_deals_dict[deal['deal_id']] = deal
    
    all_deals = list(all_deals_dict.values())
    
    # Analysis
    total_deals = len(all_deals)
    won_deals = [d for d in all_deals if d['is_won']]
    closed_deals = [d for d in all_deals if d['is_closed']]
    
    deals_with_contacts = [d for d in all_deals if d['has_contact_associations']]
    deals_with_companies = [d for d in all_deals if d['has_company_associations']]
    deals_with_both = [d for d in all_deals if d['has_contact_associations'] and d['has_company_associations']]
    deals_with_neither = [d for d in all_deals if not d['has_contact_associations'] and not d['has_company_associations']]
    
    # Revenue calculation
    total_revenue = 0
    won_revenue = 0
    
    for deal in all_deals:
        if deal['amount']:
            try:
                amount = float(deal['amount'])
                total_revenue += amount
                if deal['is_won']:
                    won_revenue += amount
            except (ValueError, TypeError):
                pass
    
    print(f"📊 DEAL ANALYSIS SUMMARY:")
    print(f"   Total Deals (2025): {total_deals}")
    print(f"   Won Deals: {len(won_deals)} ({len(won_deals)/total_deals*100:.1f}%)")
    print(f"   Closed Deals: {len(closed_deals)} ({len(closed_deals)/total_deals*100:.1f}%)")
    print(f"   Total Deal Value: ${total_revenue:,.0f}")
    print(f"   Won Deal Value: ${won_revenue:,.0f}")
    print()
    
    print(f"🔗 ASSOCIATION ANALYSIS:")
    print(f"   Deals with Contact Associations: {len(deals_with_contacts)} ({len(deals_with_contacts)/total_deals*100:.1f}%)")
    print(f"   Deals with Company Associations: {len(deals_with_companies)} ({len(deals_with_companies)/total_deals*100:.1f}%)")
    print(f"   Deals with Both Associations: {len(deals_with_both)} ({len(deals_with_both)/total_deals*100:.1f}%)")
    print(f"   Deals with NO Associations: {len(deals_with_neither)} ({len(deals_with_neither)/total_deals*100:.1f}%)")
    print()
    
    # Sample deals analysis
    print(f"📋 SAMPLE DEAL EXAMPLES:")
    print("=" * 25)
    
    if deals_with_both:
        print(f"🟢 DEALS WITH FULL ASSOCIATIONS ({len(deals_with_both)}):")
        for deal in deals_with_both[:3]:
            print(f"   • {deal['dealname'] or 'Unnamed Deal'} (ID: {deal['deal_id']})")
            print(f"     Amount: ${float(deal['amount']):,.0f}" if deal['amount'] else "     Amount: N/A")
            print(f"     Stage: {deal['dealstage']}")
            print(f"     Contacts: {deal['contact_count']}, Companies: {deal['company_count']}")
            print(f"     HubSpot: https://app.hubspot.com/contacts/19877595/deal/{deal['deal_id']}/")
            print()
    
    if deals_with_neither:
        print(f"🔴 DEALS WITH NO ASSOCIATIONS ({len(deals_with_neither)}):")
        for deal in deals_with_neither[:3]:
            print(f"   • {deal['dealname'] or 'Unnamed Deal'} (ID: {deal['deal_id']})")
            print(f"     Amount: ${float(deal['amount']):,.0f}" if deal['amount'] else "     Amount: N/A")
            print(f"     Stage: {deal['dealstage']}")
            print(f"     HubSpot: https://app.hubspot.com/contacts/19877595/deal/{deal['deal_id']}/")
            print()
    
    return {
        'total_deals': total_deals,
        'won_deals': len(won_deals),
        'deals_with_contacts': len(deals_with_contacts),
        'deals_with_companies': len(deals_with_companies),
        'deals_with_both': len(deals_with_both),
        'deals_with_neither': len(deals_with_neither),
        'total_revenue': total_revenue,
        'won_revenue': won_revenue,
        'sample_deals_with_associations': deals_with_both[:5],
        'sample_deals_without_associations': deals_with_neither[:5]
    }

def main():
    """Main execution function"""
    print(f"💰 DEALS-ONLY ANALYSIS 2025")
    print(f"📅 Period: January - July 2025")
    print(f"🔑 Using HubSpot API Key: {HUBSPOT_API_KEY[:10]}...")
    print("=" * 50)
    
    # Fetch deals created in 2025
    created_deals = fetch_deals_created_2025()
    
    # Fetch deals closed in 2025
    closed_deals = fetch_deals_closed_2025()
    
    # Comprehensive analysis
    results = analyze_deals_comprehensive(created_deals, closed_deals)
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('tools/outputs', exist_ok=True)
    
    output_data = {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'period': 'January - July 2025',
        'methodology': 'Direct Deals Analysis',
        'results': results
    }
    
    output_file = f"tools/outputs/deals_only_analysis_2025_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    return results

if __name__ == "__main__":
    main()