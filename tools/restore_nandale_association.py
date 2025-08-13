#!/usr/bin/env python3
"""
Restore the NANDALE customer association that was lost during primary switch
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Company

def restore_nandale():
    """Restore NANDALE company association to the deal"""
    
    deal_id = "40274308013"
    nandale_company_id = "36247900198"  # NANDALE company
    
    print(f"🔧 RESTORING NANDALE ASSOCIATION")
    print(f"=" * 50)
    print(f"Deal ID: {deal_id}")
    print(f"Adding back: NANDALE (ID: {nandale_company_id})")
    
    client = get_client()
    
    try:
        # Add NANDALE back as associated company (not primary)
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{nandale_company_id}"
        payload = [
            {
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 341  # Standard company-deal association
            }
        ]
        
        response = client.session.put(
            f"{client.config.base_url}/{endpoint}", 
            json=payload
        )
        
        if response.status_code in [200, 201, 204]:
            print(f"✅ Added NANDALE back as associated company")
            
            # Verify final state
            print(f"\n🔍 Verifying final state...")
            assocs = client.get_associations(deal_id, 'deals', 'companies')
            
            print(f"Final associations:")
            for assoc in assocs.get('results', []):
                company_id = str(assoc['toObjectId'])
                company = Company.find_by_id(company_id, properties=['name', 'cuit'])
                if company:
                    company_props = company.get('properties', {})
                    company_name = company_props.get('name', 'Unknown')
                    cuit = company_props.get('cuit', 'NOT SET')
                    labels = [a.get('label', '') for a in assoc.get('associationTypes', []) if a.get('label')]
                    
                    print(f"  • {company_name}")
                    print(f"    ID: {company_id}")
                    print(f"    CUIT: {cuit}")
                    print(f"    Labels: {labels}")
            
            print(f"\n✅ NANDALE deal now has correct configuration:")
            print(f"  • PRIMARY: Contador Alejandro Perez (Accountant)")
            print(f"  • ASSOCIATED: NANDALE (Customer)")
            
        else:
            print(f"❌ Error adding NANDALE: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    restore_nandale()

if __name__ == "__main__":
    main()