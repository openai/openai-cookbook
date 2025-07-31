#!/usr/bin/env python3
"""
Check for deals with no company associations from January to June 2025
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

def get_deals_jan_june_2025():
    """Get all deals from January to June 2025 with their company associations"""
    print(f"\n📋 FETCHING DEALS FROM JANUARY TO JUNE 2025")
    
    start_datetime = "2025-01-01T00:00:00.000Z"
    end_datetime = "2025-06-30T23:59:59.999Z"
    
    properties = [
        'dealname', 'amount', 'createdate', 'closedate', 'dealstage',
        'pipeline', 'dealtype', 'hs_closed_won_date', 'hs_closed_lost_date',
        'dealowner'
    ]
    
    # Search for deals created OR closed in Jan-June 2025
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
        "limit": 100
    }
    
    all_deals = []
    after = None
    total_requests = 0
    
    print("📡 Fetching deals...")
    
    while True:
        if after:
            search_request["after"] = after
            
        result = make_hubspot_request('/crm/v3/objects/deals/search', search_data=search_request)
        
        if not result or 'results' not in result:
            break
            
        batch_deals = result['results']
        
        for deal in batch_deals:
            props = deal.get('properties', {})
            
            # Parse amount safely
            amount_str = props.get('amount', '0')
            try:
                amount = float(amount_str) if amount_str else 0.0
            except (ValueError, TypeError):
                amount = 0.0
            
            # Determine month from creation or close date
            create_date = props.get('createdate', '')
            close_date = props.get('closedate', '')
            
            # Use close date if available, otherwise create date
            date_for_month = close_date if close_date else create_date
            month = "Unknown"
            if date_for_month:
                try:
                    date_obj = datetime.fromisoformat(date_for_month.replace('Z', '+00:00'))
                    month = date_obj.strftime('%Y-%m')  # Format: 2025-01
                except:
                    month = "Unknown"
            
            deal_data = {
                'deal_id': deal['id'],
                'dealname': props.get('dealname', 'Unnamed Deal'),
                'amount': amount,
                'createdate': props.get('createdate'),
                'closedate': props.get('closedate'),
                'dealstage': props.get('dealstage'),
                'is_won': props.get('dealstage') in ['closedwon', '34692158'],
                'is_closed': props.get('dealstage') in ['closedwon', '34692158', 'closedlost', '31849274'],
                'hubspot_url': f"https://app.hubspot.com/contacts/19877595/deal/{deal['id']}/",
                'month': month
            }
            
            all_deals.append(deal_data)
        
        total_requests += 1
        if total_requests % 10 == 0:
            print(f"📈 Progress: {total_requests} requests, {len(all_deals)} deals fetched")
        
        if 'paging' not in result or 'next' not in result['paging']:
            break
        after = result['paging']['next']['after']
    
    print(f"✅ DEALS FETCHED: {len(all_deals)}")
    
    # Now get company associations for each deal
    print("🔗 Getting company associations for each deal...")
    
    for i, deal in enumerate(all_deals):
        deal_id = deal['deal_id']
        
        # Get company associations for this deal
        assoc_url = f"/crm/v4/objects/deals/{deal_id}/associations/companies"
        assoc_result = make_hubspot_request(assoc_url)
        
        deal['company_associations'] = []
        deal['association_labels'] = []
        
        if assoc_result and 'results' in assoc_result:
            for assoc in assoc_result['results']:
                company_id = assoc.get('toObjectId')
                assoc_types = assoc.get('associationTypes', [])
                
                for assoc_type in assoc_types:
                    label = assoc_type.get('label', 'Unknown Label')
                    category = assoc_type.get('category', 'Unknown Category')
                    type_id = assoc_type.get('typeId', 'Unknown Type')
                    
                    association_info = {
                        'company_id': company_id,
                        'category': category,
                        'type_id': type_id,
                        'label': label
                    }
                    deal['company_associations'].append(association_info)
                    
                    # Create readable label
                    if label and label != 'Unknown Label':
                        deal['association_labels'].append(label)
                    else:
                        deal['association_labels'].append(f"{category}_{type_id}")
        
        # Remove duplicates from labels
        deal['association_labels'] = list(set(deal['association_labels']))
        
        # Progress update
        if (i + 1) % 100 == 0:
            print(f"📈 Association fetch: {i + 1}/{len(all_deals)} deals processed")
    
    return all_deals

def analyze_deals_no_associations(deals):
    """Analyze deals with no company associations"""
    print(f"\n📋 DEALS WITH NO COMPANY ASSOCIATIONS - JANUARY TO JUNE 2025")
    print("=" * 80)
    
    # Find deals with no associations
    no_associations = []
    for deal in deals:
        if not deal.get('company_associations') or len(deal.get('company_associations', [])) == 0:
            no_associations.append(deal)
    
    # Group by month
    monthly_stats = {}
    monthly_no_assoc = {}
    
    for deal in deals:
        month = deal['month']
        if month not in monthly_stats:
            monthly_stats[month] = {'total': 0, 'won': 0, 'revenue': 0.0}
            monthly_no_assoc[month] = {'total': 0, 'won': 0, 'revenue': 0.0, 'deals': []}
        
        monthly_stats[month]['total'] += 1
        if deal['is_won']:
            monthly_stats[month]['won'] += 1
            monthly_stats[month]['revenue'] += deal['amount']
    
    for deal in no_associations:
        month = deal['month']
        monthly_no_assoc[month]['total'] += 1
        monthly_no_assoc[month]['deals'].append(deal)
        if deal['is_won']:
            monthly_no_assoc[month]['won'] += 1
            monthly_no_assoc[month]['revenue'] += deal['amount']
    
    print(f"📊 OVERALL SUMMARY:")
    print(f"   Total Deals (Jan-June): {len(deals)}")
    print(f"   Deals with NO Associations: {len(no_associations)}")
    print(f"   Deals with Associations: {len(deals) - len(no_associations)}")
    print(f"   Association Rate: {((len(deals) - len(no_associations)) / len(deals) * 100):.1f}%")
    print()
    
    # Monthly breakdown
    print(f"📅 MONTHLY BREAKDOWN:")
    print("=" * 60)
    
    months = ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06']
    
    for month in months:
        if month in monthly_stats:
            total = monthly_stats[month]['total']
            no_assoc = monthly_no_assoc.get(month, {'total': 0, 'won': 0, 'revenue': 0.0})['total']
            no_assoc_won = monthly_no_assoc.get(month, {'total': 0, 'won': 0, 'revenue': 0.0})['won']
            no_assoc_revenue = monthly_no_assoc.get(month, {'total': 0, 'won': 0, 'revenue': 0.0})['revenue']
            
            association_rate = ((total - no_assoc) / total * 100) if total > 0 else 0
            
            print(f"**{month}:**")
            print(f"   Total Deals: {total}")
            print(f"   No Associations: {no_assoc} ({association_rate:.1f}% have associations)")
            print(f"   No Assoc Won: {no_assoc_won} deals, ${no_assoc_revenue:,.2f}")
            print()
    
    # Detailed list of deals with no associations
    if no_associations:
        print(f"❌ DETAILED LIST - DEALS WITH NO ASSOCIATIONS ({len(no_associations)}):")
        print("=" * 80)
        
        # Sort by month and then by close date
        no_associations.sort(key=lambda x: (x['month'], x['closedate'] or '9999-12-31'))
        
        current_month = None
        for i, deal in enumerate(no_associations, 1):
            if deal['month'] != current_month:
                current_month = deal['month']
                print(f"\n📅 **{current_month}:**")
                print("-" * 40)
            
            close_date = deal['closedate'][:10] if deal['closedate'] else "No close date"
            status = "🏆 WON" if deal['is_won'] else ("❌ LOST" if deal['is_closed'] else "⏳ OPEN")
            
            print(f"{i}. {status} **{deal['dealname']}**")
            print(f"   💰 Amount: ${deal['amount']:,.2f}")
            print(f"   📅 Close Date: {close_date}")
            print(f"   📊 Stage: {deal['dealstage']}")
            print(f"   🔗 HubSpot URL: {deal['hubspot_url']}")
            print(f"   🆔 Deal ID: {deal['deal_id']}")
            print()
    else:
        print("✅ ALL DEALS HAVE COMPANY ASSOCIATIONS!")
        print("🎉 Perfect attribution tracking!")
    
    return no_associations

def main():
    """Main execution function"""
    print(f"📋 DEALS WITH NO COMPANY ASSOCIATIONS - JAN TO JUNE 2025")
    print(f"📅 Period: January 1 - June 30, 2025")
    print(f"🎯 Focus: Identify attribution gaps")
    print(f"🔑 Using HubSpot API Key: {HUBSPOT_API_KEY[:10]}...")
    print("=" * 80)
    
    # Get deals with associations
    deals = get_deals_jan_june_2025()
    
    if not deals:
        print("❌ No deals found for January-June 2025")
        return
    
    # Analyze deals with no associations
    no_associations = analyze_deals_no_associations(deals)
    
    # Save data
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('tools/outputs', exist_ok=True)
    
    # Save JSON data
    json_file = f"tools/outputs/jan_june_2025_deals_no_associations_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(no_associations, f, indent=2, default=str)
    
    # Save CSV summary
    if no_associations:
        csv_data = []
        for deal in no_associations:
            csv_row = {
                'Month': deal['month'],
                'Deal ID': deal['deal_id'],
                'Deal Name': deal['dealname'],
                'Amount': deal['amount'],
                'Close Date': deal['closedate'][:10] if deal['closedate'] else 'No close date',
                'Deal Stage': deal['dealstage'],
                'Is Won': 'Yes' if deal['is_won'] else 'No',
                'HubSpot URL': deal['hubspot_url']
            }
            csv_data.append(csv_row)
        
        df = pd.DataFrame(csv_data)
        csv_file = f"tools/outputs/jan_june_2025_deals_no_associations_{timestamp}.csv"
        df.to_csv(csv_file, index=False)
        print(f"💾 CSV exported to: {csv_file}")
    
    print(f"💾 JSON data saved to: {json_file}")
    
    return no_associations

if __name__ == "__main__":
    main()