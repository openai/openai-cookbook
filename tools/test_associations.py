#!/usr/bin/env python3
"""
Test the associations API
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client

def test_associations():
    """Test getting associations for a deal"""
    
    print("🔍 TESTING ASSOCIATIONS API")
    print("=" * 50)
    
    client = get_client()
    
    # Use a deal ID that we know exists
    deal_id = "9354548363"  # From previous test
    
    try:
        print(f"Getting associations for deal {deal_id}...")
        
        # Test the associations endpoint
        response = client.get_associations(deal_id, 'deals', 'companies')
        
        print(f"Response type: {type(response)}")
        print(f"Response: {response}")
        
        if isinstance(response, dict):
            print(f"Response keys: {response.keys()}")
            
            # Check for results
            if 'results' in response:
                associations = response['results']
                print(f"Found {len(associations)} associations")
                
                for i, assoc in enumerate(associations[:3], 1):  # Show first 3
                    print(f"Association {i}: {assoc}")
            else:
                print("No 'results' key in response")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_associations()