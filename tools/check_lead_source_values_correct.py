#!/usr/bin/env python3
"""
Check what Lead Source values exist in July 2025 deals using correct field name
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api.models import Deal

def check_lead_source_values():
    """Check what Lead Source values exist in July 2025 deals"""
    
    print("🔍 CHECKING LEAD SOURCE VALUES (CORRECT FIELD)")
    print("=" * 60)
    
    # Get July 2025 closed won deals
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
        },
        {
            'propertyName': 'closedate',
            'operator': 'LTE',
            'value': '2025-07-31'
        }
    ]
    
    properties = ['dealname', 'lead_source', 'closedate', 'id_empresa']
    
    try:
        response = Deal.search(filters=filters, properties=properties, limit=100)
        deals = response.get('results', []) if isinstance(response, dict) else response
        
        print(f"Found {len(deals)} July 2025 closed won deals")
        
        # Collect unique lead source values
        lead_sources = {}
        
        for deal in deals:
            props = deal.get('properties', {})
            lead_source = props.get('lead_source', '')
            
            if lead_source:
                if lead_source not in lead_sources:
                    lead_sources[lead_source] = 0
                lead_sources[lead_source] += 1
                
        print(f"\n📋 Lead Source Values Found:")
        print("-" * 60)
        
        if lead_sources:
            for source, count in sorted(lead_sources.items(), key=lambda x: x[1], reverse=True):
                print(f"{count:3d} deals: '{source}'")
        else:
            print("No lead source values found (all empty)")
            
        # Show deals with "Referencia" in lead source
        referencia_deals = []
        for deal in deals:
            props = deal.get('properties', {})
            lead_source = props.get('lead_source', '').lower()
            if 'referencia' in lead_source:
                referencia_deals.append(deal)
        
        print(f"\n📄 Deals with 'Referencia' in Lead Source: {len(referencia_deals)}")
        print("-" * 60)
        
        for deal in referencia_deals:
            props = deal.get('properties', {})
            print(f"Deal: {props.get('dealname', 'Unknown')}")
            print(f"Lead Source: '{props.get('lead_source', 'NOT SET')}'")
            print(f"ID Empresa: {props.get('id_empresa', 'NOT SET')}")
            print(f"Close Date: {props.get('closedate', '')}")
            print()
            
        # Show first 10 deals with their lead sources
        print(f"\n📄 Sample Deals with Lead Sources:")
        print("-" * 60)
        
        for i, deal in enumerate(deals[:10], 1):
            props = deal.get('properties', {})
            print(f"{i:2d}. {props.get('dealname', 'Unknown')}")
            print(f"    Lead Source: '{props.get('lead_source', 'NOT SET')}'")
            print(f"    ID Empresa: {props.get('id_empresa', 'NOT SET')}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_lead_source_values()