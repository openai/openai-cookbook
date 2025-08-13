pro#!/usr/bin/env python3
"""
Make the accountant primary for GORUKA deal
This is the correct configuration for Referencia Empresa Administrada
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client

def make_accountant_primary():
    """Make Contador Alejandro Perez the primary company"""
    
    deal_id = "40272444002"
    accountant_id = "36234110609"  # Contador Alejandro Perez
    
    print(f"🎯 MAKING ACCOUNTANT PRIMARY")
    print(f"=" * 50)
    print(f"Deal: 94848 - GORUKA")
    print(f"Making: Contador Alejandro Perez PRIMARY")
    print(f"Keeping: GORUKA as associated customer")
    
    client = get_client()
    
    try:
        # Add PRIMARY label to accountant
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{accountant_id}"
        payload = [
            {
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 5  # Primary association type
            }
        ]
        
        response = client.session.put(
            f"{client.config.base_url}/{endpoint}", 
            json=payload
        )
        
        if response.status_code in [200, 201, 204]:
            print(f"✅ Contador Alejandro Perez is now PRIMARY")
            
            # Verify
            print(f"\n🔍 Verifying...")
            assocs = client.get_associations(deal_id, 'deals', 'companies')
            
            for assoc in assocs.get('results', []):
                company_id = str(assoc['toObjectId'])
                labels = [a.get('label', '') for a in assoc.get('associationTypes', []) if a.get('label')]
                
                if company_id == accountant_id:
                    if 'Primary' in labels:
                        print(f"✅ VERIFIED: Accountant is primary")
                        print(f"✅ CORRECT: Referencia Empresa Administrada → Accountant primary")
                        
                        return True
            
            print(f"⚠️  Could not verify primary status")
            return False
            
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    success = make_accountant_primary()
    
    if success:
        print(f"\n🎉 SUCCESS!")
        print(f"The GORUKA deal now has correct configuration:")
        print(f"• PRIMARY: Contador Alejandro Perez (Accountant)")
        print(f"• ASSOCIATED: GORUKA (Customer)")
        print(f"• REASON: Lead Source = 'Referencia Empresa Administrada'")
    else:
        print(f"\n❌ Failed to update")

if __name__ == "__main__":
    main()