#!/usr/bin/env python3
"""
JULY 2025 DEALS DETAILED LIST
============================
Lists all July 2025 deals with:
- Close date
- HubSpot URL
- Company association labels (or "No associations" if none)
- Deal name, amount, stage
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

def get_july_2025_deals_with_associations():
    """Get all July 2025 deals with their company associations"""
    print(f"\n📋 FETCHING JULY 2025 DEALS WITH ASSOCIATION DETAILS")
    
    start_datetime = "2025-07-01T00:00:00.000Z"
    end_datetime = "2025-07-31T23:59:59.999Z"
    
    properties = [
        'dealname', 'amount', 'createdate', 'closedate', 'dealstage',
        'pipeline', 'dealtype', 'hs_closed_won_date', 'hs_closed_lost_date',
        'dealowner'
    ]
    
    # Search for deals created OR closed in July 2025
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
            
            deal_data = {
                'deal_id': deal['id'],
                'dealname': props.get('dealname', 'Unnamed Deal'),
                'amount': amount,
                'createdate': props.get('createdate'),
                'closedate': props.get('closedate'),
                'dealstage': props.get('dealstage'),
                'is_won': props.get('dealstage') in ['closedwon', '34692158'],
                'is_closed': props.get('dealstage') in ['closedwon', '34692158', 'closedlost', '31849274'],
                'hubspot_url': f"https://app.hubspot.com/contacts/19877595/deal/{deal['id']}/"
            }
            
            all_deals.append(deal_data)
        
        total_requests += 1
        if total_requests % 5 == 0:
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
        if (i + 1) % 50 == 0:
            print(f"📈 Association fetch: {i + 1}/{len(all_deals)} deals processed")
    
    return all_deals

def format_close_date(date_string):
    """Format close date for display"""
    if not date_string:
        return "No close date"
    
    try:
        # Parse ISO format and return just the date part
        date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return date_obj.strftime('%Y-%m-%d')
    except:
        return date_string[:10] if len(date_string) >= 10 else date_string

def format_associations(deal):
    """Format association labels for display"""
    if not deal['association_labels']:
        return "❌ No company associations"
    
    # Group similar labels
    labels = deal['association_labels']
    
    # Simplify common labels
    simplified_labels = []
    for label in labels:
        if "Estudio Contable" in label or "Consultor Externo" in label:
            simplified_labels.append("🏢 Accountant Channel")
        elif "refiere al negocio" in label:
            simplified_labels.append("🤝 Referral Channel")
        elif "Primary" in label:
            simplified_labels.append("🎯 Primary Company")
        elif "Múltiples Negocios" in label:
            simplified_labels.append("🔗 Multiple Business Company")
        else:
            simplified_labels.append(f"📋 {label}")
    
    # Remove duplicates and return
    return " | ".join(list(set(simplified_labels)))

def generate_detailed_deals_list(deals):
    """Generate the detailed deals list report"""
    print(f"\n📋 JULY 2025 DEALS - DETAILED LIST WITH ASSOCIATIONS")
    print("=" * 80)
    
    # Sort deals by close date (won deals first, then by date)
    won_deals = [d for d in deals if d['is_won']]
    other_deals = [d for d in deals if not d['is_won']]
    
    # Sort each group by close date
    won_deals.sort(key=lambda x: x['closedate'] or '9999-12-31')
    other_deals.sort(key=lambda x: x['closedate'] or '9999-12-31')
    
    # Combine: won deals first, then others
    sorted_deals = won_deals + other_deals
    
    print(f"📊 SUMMARY:")
    print(f"   Total Deals: {len(deals)}")
    print(f"   Won Deals: {len(won_deals)}")
    print(f"   Other Deals: {len(other_deals)}")
    print(f"   Total Won Revenue: ${sum(d['amount'] for d in won_deals):,.2f}")
    print()
    
    print(f"🏆 WON DEALS ({len(won_deals)}):")
    print("=" * 60)
    
    for i, deal in enumerate(won_deals, 1):
        close_date = format_close_date(deal['closedate'])
        associations = format_associations(deal)
        
        print(f"{i}. **{deal['dealname']}**")
        print(f"   💰 Amount: ${deal['amount']:,.2f}")
        print(f"   📅 Close Date: {close_date}")
        print(f"   🔗 HubSpot URL: {deal['hubspot_url']}")
        print(f"   🏢 Associations: {associations}")
        print()
    
    print(f"\n📋 OTHER DEALS ({len(other_deals)}):")
    print("=" * 60)
    
    for i, deal in enumerate(other_deals, 1):
        close_date = format_close_date(deal['closedate'])
        associations = format_associations(deal)
        stage_emoji = "❌" if deal['is_closed'] else "⏳"
        
        print(f"{i}. {stage_emoji} **{deal['dealname']}**")
        print(f"   💰 Amount: ${deal['amount']:,.2f}")
        print(f"   📅 Close Date: {close_date}")
        print(f"   📊 Stage: {deal['dealstage']}")
        print(f"   🔗 HubSpot URL: {deal['hubspot_url']}")
        print(f"   🏢 Associations: {associations}")
        print()
        
        # Show only first 20 other deals to avoid overwhelming output
        if i >= 20:
            remaining = len(other_deals) - 20
            if remaining > 0:
                print(f"   ... and {remaining} more deals")
            break

def generate_csv_export(deals):
    """Generate CSV export of all deals"""
    print(f"\n💾 GENERATING CSV EXPORT")
    
    csv_data = []
    for deal in deals:
        csv_row = {
            'Deal ID': deal['deal_id'],
            'Deal Name': deal['dealname'],
            'Amount': deal['amount'],
            'Close Date': format_close_date(deal['closedate']),
            'Deal Stage': deal['dealstage'],
            'Is Won': 'Yes' if deal['is_won'] else 'No',
            'HubSpot URL': deal['hubspot_url'],
            'Association Labels': format_associations(deal),
            'Raw Association Labels': ', '.join(deal['association_labels']) if deal['association_labels'] else 'None'
        }
        csv_data.append(csv_row)
    
    # Create DataFrame and save
    df = pd.DataFrame(csv_data)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('tools/outputs', exist_ok=True)
    csv_file = f"tools/outputs/july_2025_deals_detailed_list_{timestamp}.csv"
    
    df.to_csv(csv_file, index=False)
    print(f"✅ CSV exported to: {csv_file}")
    
    return csv_file

def main():
    """Main execution function"""
    print(f"📋 JULY 2025 DEALS DETAILED LIST")
    print(f"📅 Period: July 1-31, 2025")
    print(f"🎯 Focus: Deal details with company association labels")
    print(f"🔑 Using HubSpot API Key: {HUBSPOT_API_KEY[:10]}...")
    print("=" * 80)
    
    # Get deals with associations
    deals = get_july_2025_deals_with_associations()
    
    if not deals:
        print("❌ No deals found for July 2025")
        return
    
    # Generate detailed list
    generate_detailed_deals_list(deals)
    
    # Generate CSV export
    csv_file = generate_csv_export(deals)
    
    # Save JSON data
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = f"tools/outputs/july_2025_deals_detailed_data_{timestamp}.json"
    
    with open(json_file, 'w') as f:
        json.dump(deals, f, indent=2, default=str)
    
    print(f"💾 JSON data saved to: {json_file}")
    
    return deals

if __name__ == "__main__":
    main()