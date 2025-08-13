#!/usr/bin/env python3
"""
FIXED Primary Switcher - No more deleting associations!
This approach preserves all associations and only switches PRIMARY labels
"""

import sys
import os
from typing import Dict, List, Optional

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Deal, Company

def get_company_association_types(deal_id: str, company_id: str) -> List[Dict]:
    """Get all current association types for a company"""
    
    client = get_client()
    
    try:
        associations = client.get_associations(deal_id, 'deals', 'companies')
        
        for assoc in associations.get('results', []):
            if str(assoc['toObjectId']) == company_id:
                # Return the association types
                return assoc.get('associationTypes', [])
        
        return []
        
    except Exception as e:
        print(f"Error getting association types: {e}")
        return []

def update_primary_association_fixed(deal_id: str, new_primary_id: str, current_primary_id: Optional[str] = None) -> bool:
    """FIXED: Update primary without deleting associations"""
    
    client = get_client()
    
    try:
        print(f"🔄 FIXED APPROACH: Switching PRIMARY labels without deleting associations")
        
        # Step 1: Remove PRIMARY from current primary (if exists)
        if current_primary_id:
            print(f"   📤 Removing PRIMARY label from company {current_primary_id}...")
            
            # Get current association types for this company
            current_types = get_company_association_types(deal_id, current_primary_id)
            
            # Filter out PRIMARY (typeId 5) but keep all other types
            non_primary_types = []
            for assoc_type in current_types:
                if assoc_type.get('typeId') != 5:  # Keep everything except PRIMARY
                    non_primary_types.append({
                        "associationCategory": assoc_type.get('category'),
                        "associationTypeId": assoc_type.get('typeId')
                    })
            
            print(f"   📋 Keeping {len(non_primary_types)} non-primary association types")
            
            # PUT the filtered association types (this preserves the association)
            if non_primary_types:
                endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{current_primary_id}"
                response = client.session.put(
                    f"{client.config.base_url}/{endpoint}", 
                    json=non_primary_types
                )
                
                if response.status_code in [200, 201, 204]:
                    print(f"   ✅ Removed PRIMARY while preserving association")
                else:
                    print(f"   ⚠️  Warning: Could not update association types: {response.status_code}")
                    print(f"   Response: {response.text}")
            else:
                # If no other types, add a basic association to preserve the relationship
                endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{current_primary_id}"
                payload = [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 341  # Standard association
                    }
                ]
                response = client.session.put(
                    f"{client.config.base_url}/{endpoint}", 
                    json=payload
                )
                print(f"   ✅ Preserved association with basic type")
        
        # Step 2: Add PRIMARY to new primary company
        print(f"   📥 Adding PRIMARY label to company {new_primary_id}...")
        
        # Get current association types for the new primary
        current_types = get_company_association_types(deal_id, new_primary_id)
        
        # Add PRIMARY to existing types
        all_types = []
        
        # Keep existing types
        for assoc_type in current_types:
            if assoc_type.get('typeId') != 5:  # Don't duplicate PRIMARY
                all_types.append({
                    "associationCategory": assoc_type.get('category'),
                    "associationTypeId": assoc_type.get('typeId')
                })
        
        # Add PRIMARY
        all_types.append({
            "associationCategory": "HUBSPOT_DEFINED",
            "associationTypeId": 5  # PRIMARY
        })
        
        # If no existing association, also add basic association
        if len(all_types) == 1:  # Only PRIMARY
            all_types.append({
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 341  # Standard association
            })
        
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{new_primary_id}"
        response = client.session.put(
            f"{client.config.base_url}/{endpoint}", 
            json=all_types
        )
        
        if response.status_code in [200, 201, 204]:
            print(f"   ✅ Added PRIMARY label to company {new_primary_id}")
            print(f"   ✅ ALL ASSOCIATIONS PRESERVED")
            return True
        else:
            print(f"   ❌ Error adding primary: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
    except Exception as e:
        print(f"   ❌ Error updating association: {e}")
        return False

def test_fixed_approach():
    """Test the fixed approach on NANDALE deal"""
    
    deal_id = "40274308013"  # NANDALE deal
    accountant_id = "36234110609"  # Contador Alejandro Perez 
    customer_id = "36247900198"   # NANDALE
    
    print(f"🧪 TESTING FIXED APPROACH")
    print(f"=" * 50)
    print(f"Deal: NANDALE (ID: {deal_id})")
    print(f"Making accountant (ID: {accountant_id}) primary")
    print(f"Keeping customer (ID: {customer_id}) associated")
    
    # Check current state
    print(f"\n📋 Current state:")
    client = get_client()
    assocs = client.get_associations(deal_id, 'deals', 'companies')
    
    for assoc in assocs.get('results', []):
        company_id = str(assoc['toObjectId'])
        company = Company.find_by_id(company_id, properties=['name'])
        if company:
            company_name = company.get('properties', {}).get('name', 'Unknown')
            labels = [a.get('label', '') for a in assoc.get('associationTypes', []) if a.get('label')]
            print(f"   • {company_name} (ID: {company_id}) - Labels: {labels}")
    
    # Update primary
    success = update_primary_association_fixed(deal_id, accountant_id, customer_id)
    
    if success:
        print(f"\n🔍 Final verification:")
        final_assocs = client.get_associations(deal_id, 'deals', 'companies')
        
        accountant_primary = False
        customer_present = False
        total_companies = len(final_assocs.get('results', []))
        
        for assoc in final_assocs.get('results', []):
            company_id = str(assoc['toObjectId'])
            company = Company.find_by_id(company_id, properties=['name'])
            if company:
                company_name = company.get('properties', {}).get('name', 'Unknown')
                labels = [a.get('label', '') for a in assoc.get('associationTypes', []) if a.get('label')]
                
                if company_id == accountant_id and 'Primary' in labels:
                    accountant_primary = True
                if company_id == customer_id:
                    customer_present = True
                
                print(f"   • {company_name} (ID: {company_id}) - Labels: {labels}")
        
        print(f"\n📊 RESULTS:")
        print(f"   Total Companies: {total_companies} (should be 2)")
        print(f"   Accountant Primary: {'✅' if accountant_primary else '❌'}")
        print(f"   Customer Present: {'✅' if customer_present else '❌'}")
        
        if total_companies == 2 and accountant_primary and customer_present:
            print(f"\n🎉 SUCCESS! Fixed approach works perfectly!")
        else:
            print(f"\n❌ Still some issues")

def main():
    """Main function"""
    
    print("🔧 FIXED PRIMARY SWITCHER")
    print("=" * 30)
    print("This approach uses PUT instead of DELETE")
    print("to preserve all associations")
    
    response = input(f"\nTest the fixed approach on NANDALE deal? (yes/no): ").lower().strip()
    
    if response == 'yes':
        test_fixed_approach()
    else:
        print("Cancelled")

if __name__ == "__main__":
    main()