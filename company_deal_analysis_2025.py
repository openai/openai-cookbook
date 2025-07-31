#!/usr/bin/env python3
"""
COMPANY DEAL ANALYSIS 2025
==========================
Analyzes companies created in 2025 (Jan-Jul) and their associated deal activity.
Identifies companies with multiple vs single won/closed deals.

This analysis focuses on company-deal relationships to understand actual business impact.
"""

import requests
import json
import pandas as pd
import numpy as np
from datetime import datetime
import os
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

def fetch_companies_2025():
    """Fetch companies created in 2025 (Jan-Jul) with deal associations"""
    print(f"\n🏢 FETCHING COMPANIES CREATED JAN-JUL 2025")
    
    start_datetime = "2025-01-01T00:00:00.000Z"
    end_datetime = "2025-07-31T23:59:59.999Z"
    
    properties = [
        'name', 'domain', 'industry', 'city', 'state', 'country',
        'createdate', 'hs_lastmodifieddate', 'numberofemployees',
        'annualrevenue', 'lifecyclestage', 'hs_lead_status'
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
        "associations": ["deals"],  # Get deal associations
        "limit": 100
    }
    
    all_companies = []
    after = None
    total_requests = 0
    
    print("📡 Starting company extraction...")
    
    while True:
        if after:
            search_request["after"] = after
            
        result = make_hubspot_request('/crm/v3/objects/companies/search', search_data=search_request)
        
        if not result or 'results' not in result:
            break
            
        batch_companies = result['results']
        
        for company in batch_companies:
            props = company.get('properties', {})
            associations = company.get('associations', {})
            
            # Extract company data
            company_data = {
                'company_id': company['id'],
                'name': props.get('name'),
                'domain': props.get('domain'),
                'industry': props.get('industry'),
                'city': props.get('city'),
                'state': props.get('state'),
                'country': props.get('country'),
                'createdate': props.get('createdate'),
                'numberofemployees': props.get('numberofemployees'),
                'annualrevenue': props.get('annualrevenue'),
                'lifecyclestage': props.get('lifecyclestage'),
                'hs_lead_status': props.get('hs_lead_status'),
                'associated_deal_ids': []
            }
            
            # Extract associated deal IDs
            if 'deals' in associations and 'results' in associations['deals']:
                company_data['associated_deal_ids'] = [
                    deal['id'] for deal in associations['deals']['results']
                ]
            
            all_companies.append(company_data)
        
        total_requests += 1
        if total_requests % 5 == 0:
            companies_with_deals = sum(1 for c in all_companies if c['associated_deal_ids'])
            print(f"📈 Progress: {total_requests} requests, {len(all_companies)} companies, {companies_with_deals} with deals")
        
        if 'paging' not in result or 'next' not in result['paging']:
            break
        after = result['paging']['next']['after']
    
    companies_with_deals = sum(1 for c in all_companies if c['associated_deal_ids'])
    print(f"✅ COMPANIES EXTRACTED: {len(all_companies)} total, {companies_with_deals} with associated deals")
    
    return all_companies

def fetch_deal_details_for_companies(companies):
    """Fetch detailed information for all deals associated with companies"""
    # Collect all unique deal IDs
    all_deal_ids = []
    for company in companies:
        all_deal_ids.extend(company['associated_deal_ids'])
    
    unique_deal_ids = list(set(all_deal_ids))
    
    if not unique_deal_ids:
        print("❌ No deals found associated with companies")
        return []
    
    print(f"\n💰 FETCHING DETAILS FOR {len(unique_deal_ids)} UNIQUE DEALS")
    
    properties = [
        'dealname', 'amount', 'createdate', 'closedate', 'dealstage',
        'pipeline', 'hs_closed_won_date', 'hs_closed_lost_date',
        'hs_deal_stage_probability'
    ]
    
    all_deals = []
    
    # Batch read deals (up to 100 at a time)
    for i in range(0, len(unique_deal_ids), 100):
        batch_ids = unique_deal_ids[i:i+100]
        
        inputs = [{"id": deal_id} for deal_id in batch_ids]
        
        request_data = {
            "properties": properties,
            "inputs": inputs
        }
        
        result = make_hubspot_request('/crm/v3/objects/deals/batch/read', search_data=request_data)
        
        if result and 'results' in result:
            for deal in result['results']:
                props = deal.get('properties', {})
                
                # Parse dates
                createdate = props.get('createdate')
                closedate = props.get('closedate')
                
                # Check if deal was created in 2025
                created_in_2025 = False
                if createdate:
                    try:
                        create_year = datetime.fromisoformat(createdate.replace('Z', '+00:00')).year
                        created_in_2025 = create_year == 2025
                    except:
                        pass
                
                # Check if deal was closed in 2025
                closed_in_2025 = False
                if closedate:
                    try:
                        close_year = datetime.fromisoformat(closedate.replace('Z', '+00:00')).year
                        closed_in_2025 = close_year == 2025
                    except:
                        pass
                
                deal_data = {
                    'deal_id': deal['id'],
                    'dealname': props.get('dealname'),
                    'amount': props.get('amount'),
                    'createdate': createdate,
                    'closedate': closedate,
                    'dealstage': props.get('dealstage'),
                    'pipeline': props.get('pipeline'),
                    'is_won': props.get('dealstage') in ['closedwon', '34692158'],
                    'is_closed': props.get('dealstage') in ['closedwon', '34692158', 'closedlost', '31849274'],
                    'created_in_2025': created_in_2025,
                    'closed_in_2025': closed_in_2025,
                    'hs_closed_won_date': props.get('hs_closed_won_date'),
                    'hs_closed_lost_date': props.get('hs_closed_lost_date')
                }
                
                all_deals.append(deal_data)
        
        if (i // 100 + 1) % 3 == 0:
            print(f"📈 Deal batch progress: {i // 100 + 1} batches processed")
    
    # Filter for deals created/closed in 2025
    deals_2025 = [d for d in all_deals if d['created_in_2025'] or d['closed_in_2025']]
    won_deals_2025 = [d for d in deals_2025 if d['is_won']]
    closed_deals_2025 = [d for d in deals_2025 if d['is_closed']]
    
    print(f"💰 Deal Details Summary:")
    print(f"   Total Deals: {len(all_deals)}")
    print(f"   2025 Deals: {len(deals_2025)}")
    print(f"   2025 Won Deals: {len(won_deals_2025)}")
    print(f"   2025 Closed Deals: {len(closed_deals_2025)}")
    
    return all_deals

def analyze_company_deal_performance(companies, deals):
    """Analyze company performance based on deal activity"""
    print(f"\n🎯 COMPANY DEAL PERFORMANCE ANALYSIS")
    print("=" * 50)
    
    # Create deal lookup
    deal_lookup = {deal['deal_id']: deal for deal in deals}
    
    # Analyze each company
    company_analysis = []
    
    for company in companies:
        company_deals = []
        for deal_id in company['associated_deal_ids']:
            if deal_id in deal_lookup:
                deal = deal_lookup[deal_id]
                # Only include deals created or closed in 2025
                if deal['created_in_2025'] or deal['closed_in_2025']:
                    company_deals.append(deal)
        
        # Calculate metrics
        total_deals_2025 = len(company_deals)
        won_deals_2025 = [d for d in company_deals if d['is_won']]
        closed_deals_2025 = [d for d in company_deals if d['is_closed']]
        
        total_won = len(won_deals_2025)
        total_closed = len(closed_deals_2025)
        
        # Calculate revenue
        total_revenue = 0
        for deal in won_deals_2025:
            if deal['amount']:
                try:
                    total_revenue += float(deal['amount'])
                except (ValueError, TypeError):
                    pass
        
        company_analysis.append({
            'company_id': company['company_id'],
            'name': company['name'],
            'domain': company['domain'],
            'industry': company['industry'],
            'city': company['city'],
            'state': company['state'],
            'createdate': company['createdate'],
            'total_deals_2025': total_deals_2025,
            'won_deals_2025': total_won,
            'closed_deals_2025': total_closed,
            'total_revenue': total_revenue,
            'won_deal_names': [d['dealname'] for d in won_deals_2025 if d['dealname']],
            'closed_deal_names': [d['dealname'] for d in closed_deals_2025 if d['dealname']]
        })
    
    # Filter companies with deal activity
    companies_with_deals = [c for c in company_analysis if c['total_deals_2025'] > 0]
    companies_with_won_deals = [c for c in company_analysis if c['won_deals_2025'] > 0]
    
    # Categorize companies
    multiple_won_deals = [c for c in companies_with_won_deals if c['won_deals_2025'] > 1]
    single_won_deal = [c for c in companies_with_won_deals if c['won_deals_2025'] == 1]
    
    print(f"📊 COMPANY DEAL ACTIVITY SUMMARY:")
    print(f"   Total Companies Created 2025: {len(companies)}")
    print(f"   Companies with 2025 Deals: {len(companies_with_deals)}")
    print(f"   Companies with Won Deals: {len(companies_with_won_deals)}")
    print(f"   Companies with Multiple Won Deals: {len(multiple_won_deals)}")
    print(f"   Companies with Single Won Deal: {len(single_won_deal)}")
    
    return {
        'all_companies': company_analysis,
        'companies_with_deals': companies_with_deals,
        'multiple_won_deals': multiple_won_deals,
        'single_won_deal': single_won_deal
    }

def generate_detailed_report(analysis_results):
    """Generate detailed report of company deal performance"""
    print(f"\n📋 DETAILED COMPANY DEAL ANALYSIS REPORT")
    print("=" * 60)
    
    multiple_won = analysis_results['multiple_won_deals']
    single_won = analysis_results['single_won_deal']
    
    # Sort by revenue for better insights
    multiple_won.sort(key=lambda x: x['total_revenue'], reverse=True)
    single_won.sort(key=lambda x: x['total_revenue'], reverse=True)
    
    print(f"\n🏆 COMPANIES WITH MULTIPLE WON DEALS ({len(multiple_won)}):")
    print("=" * 55)
    
    if multiple_won:
        total_multi_revenue = sum(c['total_revenue'] for c in multiple_won)
        print(f"💰 Total Revenue: ${total_multi_revenue:,.0f}")
        print()
        
        for i, company in enumerate(multiple_won, 1):
            print(f"{i}. {company['name'] or 'Unnamed Company'}")
            print(f"   🆔 Company ID: {company['company_id']}")
            print(f"   🌐 Domain: {company['domain'] or 'N/A'}")
            print(f"   🏭 Industry: {company['industry'] or 'N/A'}")
            print(f"   📍 Location: {company['city'] or 'N/A'}, {company['state'] or 'N/A'}")
            print(f"   📅 Created: {company['createdate'][:10] if company['createdate'] else 'N/A'}")
            print(f"   🎯 Won Deals: {company['won_deals_2025']} deals")
            print(f"   💰 Revenue: ${company['total_revenue']:,.0f}")
            print(f"   📝 Won Deal Names: {', '.join(company['won_deal_names'][:3])}{'...' if len(company['won_deal_names']) > 3 else ''}")
            print(f"   🔗 HubSpot URL: https://app.hubspot.com/contacts/19877595/company/{company['company_id']}/")
            print()
    else:
        print("   No companies found with multiple won deals")
    
    print(f"\n🎯 COMPANIES WITH SINGLE WON DEAL ({len(single_won)}):")
    print("=" * 50)
    
    if single_won:
        total_single_revenue = sum(c['total_revenue'] for c in single_won)
        print(f"💰 Total Revenue: ${total_single_revenue:,.0f}")
        print()
        
        # Show top 10 by revenue
        top_single = single_won[:10]
        
        for i, company in enumerate(top_single, 1):
            print(f"{i}. {company['name'] or 'Unnamed Company'}")
            print(f"   🆔 Company ID: {company['company_id']}")
            print(f"   🌐 Domain: {company['domain'] or 'N/A'}")
            print(f"   🏭 Industry: {company['industry'] or 'N/A'}")
            print(f"   📍 Location: {company['city'] or 'N/A'}, {company['state'] or 'N/A'}")
            print(f"   📅 Created: {company['createdate'][:10] if company['createdate'] else 'N/A'}")
            print(f"   💰 Revenue: ${company['total_revenue']:,.0f}")
            print(f"   📝 Deal Name: {company['won_deal_names'][0] if company['won_deal_names'] else 'N/A'}")
            print(f"   🔗 HubSpot URL: https://app.hubspot.com/contacts/19877595/company/{company['company_id']}/")
            print()
        
        if len(single_won) > 10:
            print(f"   ... and {len(single_won) - 10} more companies with single won deals")
    else:
        print("   No companies found with single won deals")
    
    # Summary statistics
    print(f"\n📊 SUMMARY STATISTICS:")
    print("=" * 25)
    
    if multiple_won:
        avg_deals_multi = sum(c['won_deals_2025'] for c in multiple_won) / len(multiple_won)
        avg_revenue_multi = sum(c['total_revenue'] for c in multiple_won) / len(multiple_won)
        print(f"Multiple Won Deal Companies:")
        print(f"   Average Deals per Company: {avg_deals_multi:.1f}")
        print(f"   Average Revenue per Company: ${avg_revenue_multi:,.0f}")
    
    if single_won:
        avg_revenue_single = sum(c['total_revenue'] for c in single_won) / len(single_won)
        print(f"Single Won Deal Companies:")
        print(f"   Average Revenue per Company: ${avg_revenue_single:,.0f}")
    
    if multiple_won and single_won:
        total_revenue = sum(c['total_revenue'] for c in multiple_won + single_won)
        print(f"Overall:")
        print(f"   Total Companies with Won Deals: {len(multiple_won) + len(single_won)}")
        print(f"   Total Revenue: ${total_revenue:,.0f}")

def main():
    """Main execution function"""
    print(f"🏢 COMPANY DEAL ANALYSIS 2025")
    print(f"📅 Period: January - July 2025")
    print(f"🔑 Using HubSpot API Key: {HUBSPOT_API_KEY[:10]}...")
    print("=" * 60)
    
    # Step 1: Fetch companies created in 2025
    companies = fetch_companies_2025()
    
    if not companies:
        print("❌ No companies found for the period")
        return
    
    # Step 2: Fetch deal details for all associated deals
    deals = fetch_deal_details_for_companies(companies)
    
    # Step 3: Analyze company deal performance
    analysis_results = analyze_company_deal_performance(companies, deals)
    
    # Step 4: Generate detailed report
    generate_detailed_report(analysis_results)
    
    # Step 5: Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('tools/outputs', exist_ok=True)
    
    output_data = {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'period': 'January - July 2025',
        'methodology': 'Company Deal Performance Analysis',
        'total_companies_analyzed': len(companies),
        'total_deals_found': len(deals),
        'summary': {
            'companies_with_multiple_won_deals': len(analysis_results['multiple_won_deals']),
            'companies_with_single_won_deal': len(analysis_results['single_won_deal']),
            'total_companies_with_won_deals': len(analysis_results['multiple_won_deals']) + len(analysis_results['single_won_deal'])
        },
        'multiple_won_deals': analysis_results['multiple_won_deals'],
        'single_won_deal': analysis_results['single_won_deal']
    }
    
    output_file = f"tools/outputs/company_deal_analysis_2025_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    return analysis_results

if __name__ == "__main__":
    main()