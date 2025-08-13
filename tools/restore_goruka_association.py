#!/usr/bin/env python3
"""
Restore the GORUKA association that was accidentally removed
and fix the accountant's labels
"""

import sys
import os
from typing import Dict, Optional

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Deal, Company

def restore_goruka_deal():
    """Restore the GORUKA deal to proper state with both companies"""
    
    deal_id = "40272444002"
    goruka_company_id = "36280577679"  # From the original preview
    accountant_id = "36234110609"
    
    print(f"🔧 RESTORING GORUKA DEAL ASSOCIATIONS")
    print(f"=" * 60)
    print(f"Deal ID: {deal_id}")
    print(f"GORUKA Company ID: {goruka_company_id}")
    print(f"Accountant ID: {accountant_id}")
    
    client = get_client()
    
    # Step 1: Check current state
    print(f"\n📋 Checking current state...")
    current_assocs = client.get_associations(deal_id, 'deals', 'companies')
    
    print(f"Current associations:")
    for assoc in current_assocs.get('results', []):
        company_id = str(assoc['toObjectId'])
        company = Company.find_by_id(company_id, properties=['name'])
        if company:
            company_name = company.get('properties', {}).get('name', 'Unknown')
            labels = [a.get('label', '') for a in assoc.get('associationTypes', [])]
            print(f"  - {company_name} (ID: {company_id}) - Labels: {labels}")
    
    # Step 2: Add GORUKA back as associated company (not primary)
    print(f"\n🔄 Adding GORUKA back as associated company...")
    
    try:
        # Add basic association (not primary) - using correct association type
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{goruka_company_id}"
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
            print(f"   ✅ Added GORUKA back as associated company")
        else:
            print(f"   ❌ Error adding GORUKA: {response.status_code}")
            print(f"   Response: {response.text}")
            
            # Try with POST method instead
            print(f"   🔄 Trying with POST method...")
            response = client.session.post(
                f"{client.config.base_url}/{endpoint}", 
                json=payload
            )
            
            if response.status_code in [200, 201, 204]:
                print(f"   ✅ Added GORUKA with POST method")
            else:
                print(f"   ❌ POST also failed: {response.status_code}")
                print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Step 3: Restore accountant's "Estudio Contable" label
    print(f"\n🔄 Restoring accountant's Estudio Contable label...")
    
    try:
        # Add the accountant label back
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{accountant_id}"
        payload = [
            {
                "associationCategory": "USER_DEFINED",
                "associationTypeId": 8  # "Estudio Contable / Asesor / Consultor Externo del negocio"
            }
        ]
        
        response = client.session.put(
            f"{client.config.base_url}/{endpoint}", 
            json=payload
        )
        
        if response.status_code in [200, 201, 204]:
            print(f"   ✅ Restored accountant's Estudio Contable label")
        else:
            print(f"   ❌ Error restoring label: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Step 4: Verify final state
    print(f"\n🔍 Verifying final state...")
    final_assocs = client.get_associations(deal_id, 'deals', 'companies')
    
    print(f"\nFinal associations:")
    for assoc in final_assocs.get('results', []):
        company_id = str(assoc['toObjectId'])
        company = Company.find_by_id(company_id, properties=['name', 'cuit'])
        if company:
            company_props = company.get('properties', {})
            company_name = company_props.get('name', 'Unknown')
            cuit = company_props.get('cuit', 'NOT SET')
            labels = [a.get('label', '') for a in assoc.get('associationTypes', [])]
            
            print(f"  - {company_name}")
            print(f"    ID: {company_id}")
            print(f"    CUIT: {cuit}")
            print(f"    Labels: {labels}")
    
    print(f"\n✅ Restoration completed!")
    print(f"Now the deal should have:")
    print(f"  1. Contador Alejandro Perez (Primary + Accountant labels)")
    print(f"  2. GORUKA (Associated company)")

def main():
    """Main function"""
    
    print("🚀 GORUKA DEAL RESTORATION")
    print("=" * 50)
    print("This will restore the missing GORUKA association")
    print("and fix the accountant's labels")
    
    response = input(f"\nDo you want to proceed? (yes/no): ").lower().strip()
    
    if response != 'yes':
        print(f"❌ Cancelled")
        return
    
    restore_goruka_deal()

if __name__ == "__main__":
    main()