#!/usr/bin/env python3
"""
Correctly switch primary from accountant back to GORUKA customer
while preserving all associations and labels
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Deal, Company

def correct_goruka_primary():
    """Switch primary from accountant to GORUKA while preserving all associations"""
    
    deal_id = "40272444002"
    goruka_company_id = "36280577679"  # Should be primary
    accountant_id = "36234110609"      # Should be associated with labels
    
    print(f"🔧 CORRECTING GORUKA DEAL PRIMARY")
    print(f"=" * 60)
    print(f"Deal ID: {deal_id}")
    print(f"Making GORUKA (ID: {goruka_company_id}) PRIMARY")
    print(f"Keeping Accountant (ID: {accountant_id}) as ASSOCIATED")
    
    client = get_client()
    
    # Step 1: Check current state
    print(f"\n📋 Current state:")
    current_assocs = client.get_associations(deal_id, 'deals', 'companies')
    
    for assoc in current_assocs.get('results', []):
        company_id = str(assoc['toObjectId'])
        company = Company.find_by_id(company_id, properties=['name'])
        if company:
            company_name = company.get('properties', {}).get('name', 'Unknown')
            labels = [a.get('label', '') for a in assoc.get('associationTypes', []) if a.get('label')]
            print(f"  - {company_name} (ID: {company_id}) - Labels: {labels}")
    
    # Step 2: Remove PRIMARY from accountant (keep other labels)
    print(f"\n🔄 Removing PRIMARY label from accountant (keeping Estudio Contable label)...")
    
    try:
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{accountant_id}"
        payload = [
            {
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 5  # Primary association type
            }
        ]
        
        response = client.session.delete(
            f"{client.config.base_url}/{endpoint}", 
            json=payload
        )
        
        if response.status_code in [200, 204]:
            print(f"   ✅ Removed PRIMARY from accountant")
        else:
            print(f"   ⚠️  Warning: Could not remove primary: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Step 3: Add PRIMARY to GORUKA
    print(f"\n🔄 Adding PRIMARY label to GORUKA...")
    
    try:
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{goruka_company_id}"
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
            print(f"   ✅ Added PRIMARY to GORUKA")
        else:
            print(f"   ❌ Error adding primary: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Step 4: Verify final state
    print(f"\n🔍 Final state verification:")
    final_assocs = client.get_associations(deal_id, 'deals', 'companies')
    
    goruka_primary = False
    accountant_present = False
    accountant_has_label = False
    
    for assoc in final_assocs.get('results', []):
        company_id = str(assoc['toObjectId'])
        company = Company.find_by_id(company_id, properties=['name'])
        if company:
            company_name = company.get('properties', {}).get('name', 'Unknown')
            labels = [a.get('label', '') for a in assoc.get('associationTypes', []) if a.get('label')]
            
            if company_id == goruka_company_id:
                if 'Primary' in labels:
                    goruka_primary = True
                    print(f"  ✅ {company_name} is PRIMARY")
                else:
                    print(f"  ❌ {company_name} is NOT primary")
                    
            elif company_id == accountant_id:
                accountant_present = True
                if 'Estudio Contable / Asesor / Consultor Externo del negocio' in labels:
                    accountant_has_label = True
                    print(f"  ✅ {company_name} has Estudio Contable label")
                else:
                    print(f"  ⚠️  {company_name} missing Estudio Contable label")
                    
            print(f"     - {company_name} (ID: {company_id}) - Labels: {labels}")
    
    print(f"\n📊 VERIFICATION SUMMARY:")
    print(f"  GORUKA is primary: {'✅' if goruka_primary else '❌'}")
    print(f"  Accountant present: {'✅' if accountant_present else '❌'}")
    print(f"  Accountant has label: {'✅' if accountant_has_label else '❌'}")
    
    if goruka_primary and accountant_present and accountant_has_label:
        print(f"\n🎉 SUCCESS! Deal is now correctly configured:")
        print(f"  • GORUKA is primary (customer company)")
        print(f"  • Accountant is associated with proper labels")
        print(f"  • All associations preserved")
    else:
        print(f"\n⚠️  Some issues remain - may need manual review")

def main():
    """Main function"""
    
    print("🚀 GORUKA PRIMARY CORRECTION")
    print("=" * 50)
    print("This will make GORUKA the primary company")
    print("and keep the accountant as associated with labels")
    
    response = input(f"\nDo you want to proceed? (yes/no): ").lower().strip()
    
    if response != 'yes':
        print(f"❌ Cancelled")
        return
    
    correct_goruka_primary()

if __name__ == "__main__":
    main()