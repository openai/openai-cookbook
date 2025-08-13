#!/usr/bin/env python3
"""
Test to see the actual structure of deal objects returned by the API
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api.models import Deal

def test_deal_structure():
    """Check the structure of deal objects"""
    
    print("🔍 TESTING DEAL STRUCTURE")
    print("=" * 50)
    
    # Get one deal to see its structure
    filters = [
        {
            'propertyName': 'dealstage',
            'operator': 'EQ',
            'value': 'closedwon'
        },
        {
            'propertyName': 'lead_source',
            'operator': 'EQ',
            'value': 'Referencia Empresa Administrada'
        }
    ]
    
    properties = ['dealname', 'amount', 'closedate', 'id_empresa', 'lead_source']
    
    try:
        response = Deal.search(filters=filters, properties=properties, limit=1)
        deals = response.get('results', []) if isinstance(response, dict) else response
        
        if deals:
            deal = deals[0]
            print(f"Deal object type: {type(deal)}")
            print(f"Deal object keys: {deal.keys() if isinstance(deal, dict) else 'N/A'}")
            print(f"Full deal object: {deal}")
            
            # Check for different ID fields
            potential_id_fields = ['id', 'hs_object_id', 'objectId', 'dealId']
            for field in potential_id_fields:
                if field in deal:
                    print(f"Found ID field '{field}': {deal[field]}")
                    
        else:
            print("No deals found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_deal_structure()