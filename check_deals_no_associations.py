#!/usr/bin/env python3
"""
Check for deals with no company associations in July 2025
"""

import json
import os
from datetime import datetime

def check_deals_no_associations():
    """Check the JSON data file for deals with no associations"""
    
    # Find the most recent JSON file
    files = [f for f in os.listdir('tools/outputs') if f.startswith('july_2025_deals_detailed_data_') and f.endswith('.json')]
    if not files:
        print("❌ No JSON data file found")
        return
    
    latest_file = sorted(files)[-1]
    json_file = f"tools/outputs/{latest_file}"
    
    print(f"📋 CHECKING DEALS WITH NO COMPANY ASSOCIATIONS")
    print(f"📂 Data file: {latest_file}")
    print("=" * 80)
    
    # Load the data
    with open(json_file, 'r') as f:
        deals = json.load(f)
    
    # Find deals with no associations
    no_associations = []
    for deal in deals:
        if not deal.get('company_associations') or len(deal.get('company_associations', [])) == 0:
            no_associations.append(deal)
    
    print(f"📊 SUMMARY:")
    print(f"   Total Deals: {len(deals)}")
    print(f"   Deals with NO Associations: {len(no_associations)}")
    print(f"   Deals with Associations: {len(deals) - len(no_associations)}")
    print()
    
    if no_associations:
        print(f"❌ DEALS WITH NO COMPANY ASSOCIATIONS ({len(no_associations)}):")
        print("=" * 60)
        
        for i, deal in enumerate(no_associations, 1):
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
    
    # Also check for deals with empty association labels specifically
    empty_labels = []
    for deal in deals:
        if not deal.get('association_labels') or len(deal.get('association_labels', [])) == 0:
            # But they might still have raw associations
            if deal.get('company_associations') and len(deal.get('company_associations', [])) > 0:
                empty_labels.append(deal)
    
    if empty_labels:
        print(f"\n⚠️  DEALS WITH ASSOCIATIONS BUT NO READABLE LABELS ({len(empty_labels)}):")
        print("=" * 60)
        for i, deal in enumerate(empty_labels, 1):
            print(f"{i}. **{deal['dealname']}** (${deal['amount']:,.2f})")
            print(f"   Raw associations: {len(deal.get('company_associations', []))}")
            print(f"   🔗 {deal['hubspot_url']}")
            # Show raw association details
            for assoc in deal.get('company_associations', [])[:3]:  # Show first 3
                print(f"      - Company: {assoc.get('company_id')}, Label: {assoc.get('label')}, Category: {assoc.get('category')}")
            print()

if __name__ == "__main__":
    check_deals_no_associations()