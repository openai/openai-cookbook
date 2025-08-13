#!/usr/bin/env python3
"""
Test script to check available Lead Source values in HubSpot
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Deal

def check_lead_source_values():
    """Check what Lead Source values exist in July 2025 deals"""
    
    print("🔍 CHECKING LEAD SOURCE VALUES")
    print("=" * 50)
    
    # First, let's get some July 2025 deals to see lead source values
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
    
    properties = ['dealname', 'hs_lead_source', 'closedate']
    
    try:
        response = Deal.search(filters=filters, properties=properties, limit=50)
        
        print(f"Response type: {type(response)}")
        print(f"Response keys: {response.keys() if isinstance(response, dict) else 'N/A'}")
        
        # Extract deals from response
        if isinstance(response, dict):
            deals = response.get('results', [])
        else:
            deals = response
            
        print(f"Found {len(deals)} July 2025 closed won deals")
        
        # Collect unique lead source values
        lead_sources = set()
        
        for deal in deals:
            # Check the actual structure
            if isinstance(deal, dict):
                props = deal.get('properties', {})
            else:
                print(f"Unexpected deal format: {type(deal)} - {deal}")
                continue
                
            lead_source = props.get('hs_lead_source', '')
            if lead_source:
                lead_sources.add(lead_source)
                
        print(f"\n📋 Unique Lead Source Values Found:")
        print("-" * 50)
        for i, source in enumerate(sorted(lead_sources), 1):
            print(f"{i}. '{source}'")
            
        # Show some examples
        print(f"\n📄 Example Deals:")
        print("-" * 50)
        for i, deal in enumerate(deals[:10], 1):
            props = deal.get('properties', {})
            print(f"{i}. {props.get('dealname', 'Unknown')}")
            print(f"   Lead Source: '{props.get('hs_lead_source', 'NOT SET')}'")
            print(f"   Close Date: {props.get('closedate', '')}")
            print()
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_lead_source_values()