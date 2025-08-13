#!/usr/bin/env python3
"""
Check all deal properties to find the correct lead source field
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client

def check_deal_properties():
    """Get all available deal properties to find lead source"""
    
    print("🔍 CHECKING ALL DEAL PROPERTIES")
    print("=" * 50)
    
    client = get_client()
    
    try:
        # Get all properties for deals
        response = client.get('/crm/v3/properties/deals')
        properties = response.get('results', [])
        
        print(f"Found {len(properties)} deal properties")
        
        # Look for lead source related properties
        lead_source_props = []
        for prop in properties:
            prop_name = prop.get('name', '')
            prop_label = prop.get('label', '')
            
            if 'lead' in prop_name.lower() or 'source' in prop_name.lower() or 'referenc' in prop_name.lower():
                lead_source_props.append({
                    'name': prop_name,
                    'label': prop_label,
                    'type': prop.get('type', ''),
                    'description': prop.get('description', '')
                })
        
        print(f"\n📋 Lead Source Related Properties:")
        print("-" * 50)
        for prop in lead_source_props:
            print(f"Name: {prop['name']}")
            print(f"Label: {prop['label']}")
            print(f"Type: {prop['type']}")
            print(f"Description: {prop['description']}")
            print("-" * 30)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def get_sample_deal_with_all_properties():
    """Get one deal with ALL properties to see what's available"""
    
    print("\n\n🔍 SAMPLE DEAL WITH ALL PROPERTIES")
    print("=" * 50)
    
    from hubspot_api.models import Deal
    
    try:
        # Get one deal without specifying properties (should return all)
        filters = [
            {
                'propertyName': 'dealstage',
                'operator': 'EQ',
                'value': 'closedwon'
            },
            {
                'propertyName': 'closedate',
                'operator': 'GTE',
                'value': '2025-07-01'
            }
        ]
        
        response = Deal.search(filters=filters, limit=1)
        deals = response.get('results', [])
        
        if deals:
            deal = deals[0]
            props = deal.get('properties', {})
            
            print(f"Deal: {props.get('dealname', 'Unknown')}")
            print(f"Total properties: {len(props)}")
            
            # Look for properties with 'lead', 'source', or 'referenc' in the name
            relevant_props = {}
            for prop_name, prop_value in props.items():
                if any(keyword in prop_name.lower() for keyword in ['lead', 'source', 'referenc', 'origin']):
                    relevant_props[prop_name] = prop_value
            
            print(f"\n📋 Relevant Properties Found:")
            print("-" * 50)
            for prop_name, prop_value in relevant_props.items():
                print(f"{prop_name}: {prop_value}")
                
            # Also check for any non-empty source-like properties
            print(f"\n📋 All Non-Empty Properties (first 20):")
            print("-" * 50)
            count = 0
            for prop_name, prop_value in props.items():
                if prop_value and count < 20:
                    print(f"{prop_name}: {prop_value}")
                    count += 1
        else:
            print("No deals found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_deal_properties()
    get_sample_deal_with_all_properties()