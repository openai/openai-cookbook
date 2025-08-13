#!/usr/bin/env python3
"""
Update a single deal's primary company association
Starting with Example 1: GLAM FILMS SA (Deal ID: 39867108669)
"""

import sys
import os
import json
from typing import Dict, Optional

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Deal, Company

def get_deal_current_state(deal_id: str) -> Dict:
    """Get current state of a deal and its associations"""
    
    client = get_client()
    
    try:
        # Get deal details
        deal = Deal.find_by_id(deal_id, properties=['dealname', 'amount', 'id_empresa', 'lead_source'])
        if not deal:
            return {'error': f'Deal {deal_id} not found'}
        
        deal_props = deal.get('properties', {})
        
        # Get associations
        associations = client.get_associations(deal_id, 'deals', 'companies')
        
        companies = []
        current_primary = None
        
        for assoc in associations.get('results', []):
            company_id = str(assoc['toObjectId'])
            
            # Get company details
            company = Company.find_by_id(company_id, properties=['name', 'cuit'])
            
            if company:
                company_props = company.get('properties', {})
                
                # Analyze association types
                is_primary = False
                labels = []
                
                for assoc_type in assoc.get('associationTypes', []):
                    label = assoc_type.get('label', '')
                    if label:
                        labels.append(label)
                    
                    if label == 'Primary':
                        is_primary = True
                
                company_info = {
                    'id': company_id,
                    'name': company_props.get('name', 'Unknown'),
                    'cuit': company_props.get('cuit', ''),
                    'is_primary': is_primary,
                    'labels': labels
                }
                
                companies.append(company_info)
                
                if is_primary:
                    current_primary = company_info
        
        return {
            'deal_id': deal_id,
            'deal_name': deal_props.get('dealname', 'Unknown'),
            'amount': deal_props.get('amount', '0'),
            'id_empresa': deal_props.get('id_empresa', ''),
            'lead_source': deal_props.get('lead_source', ''),
            'companies': companies,
            'current_primary': current_primary
        }
        
    except Exception as e:
        return {'error': str(e)}

def update_primary_association(deal_id: str, new_primary_id: str, current_primary_id: Optional[str] = None) -> bool:
    """Update the primary association for a deal"""
    
    client = get_client()
    
    try:
        print(f"🔄 Making API calls to update associations...")
        
        # Step 1: Remove current primary if exists
        if current_primary_id:
            print(f"   📤 Removing PRIMARY from company {current_primary_id}...")
            
            # Use HubSpot associations API to remove primary label
            endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{current_primary_id}"
            
            # Get current associations to see what to remove
            current_assocs = client.get_associations(deal_id, 'deals', 'companies')
            
            # Find the specific association to modify
            for assoc in current_assocs.get('results', []):
                if str(assoc['toObjectId']) == current_primary_id:
                    # Remove only the primary association type
                    types_to_remove = []
                    for assoc_type in assoc.get('associationTypes', []):
                        if assoc_type.get('label') == 'Primary':
                            types_to_remove.append({
                                "associationCategory": assoc_type.get('category'),
                                "associationTypeId": assoc_type.get('typeId')
                            })
                    
                    if types_to_remove:
                        response = client.session.delete(
                            f"{client.config.base_url}/{endpoint}", 
                            json=types_to_remove
                        )
                        if response.status_code in [200, 204]:
                            print(f"   ✅ Removed PRIMARY label from company {current_primary_id}")
                        else:
                            print(f"   ⚠️  Warning: Could not remove primary (status: {response.status_code})")
                    break
        
        # Step 2: Add new primary association
        print(f"   📥 Adding PRIMARY to company {new_primary_id}...")
        
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{new_primary_id}"
        payload = [
            {
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 5  # Primary association type ID
            }
        ]
        
        response = client.session.put(
            f"{client.config.base_url}/{endpoint}", 
            json=payload
        )
        
        if response.status_code in [200, 201, 204]:
            print(f"   ✅ Added PRIMARY label to company {new_primary_id}")
            return True
        else:
            print(f"   ❌ Error adding primary: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
    except Exception as e:
        print(f"   ❌ Error updating association: {e}")
        return False

def update_glam_films_deal():
    """Update the GLAM FILMS SA deal specifically"""
    
    # Deal details from Example 1
    deal_id = "39867108669"
    deal_name = "87624 - GLAM FILMS SA"
    new_primary_id = "22621974713"  # GLAM FILMS SA company ID
    
    print(f"🎯 UPDATING SINGLE DEAL - EXAMPLE 1")
    print(f"=" * 60)
    print(f"Deal: {deal_name}")
    print(f"Deal ID: {deal_id}")
    print(f"Target Primary Company ID: {new_primary_id}")
    
    # Get current state
    print(f"\n📋 Getting current state...")
    current_state = get_deal_current_state(deal_id)
    
    if 'error' in current_state:
        print(f"❌ Error: {current_state['error']}")
        return False
    
    # Display current state
    print(f"\n🏢 CURRENT ASSOCIATIONS:")
    for i, company in enumerate(current_state['companies'], 1):
        primary_marker = " (PRIMARY)" if company['is_primary'] else ""
        print(f"   {i}. {company['name']}{primary_marker}")
        print(f"      ID: {company['id']}")
        print(f"      CUIT: {company['cuit'] or 'NOT SET'}")
        if company['labels']:
            print(f"      Labels: {', '.join(company['labels'])}")
    
    # Show what will change
    current_primary_name = current_state['current_primary']['name'] if current_state['current_primary'] else "NONE"
    target_company = next((c for c in current_state['companies'] if c['id'] == new_primary_id), None)
    
    if not target_company:
        print(f"❌ Error: Target company {new_primary_id} not found in associations")
        return False
    
    print(f"\n🔄 PLANNED CHANGE:")
    print(f"   Current Primary: {current_primary_name}")
    print(f"   → New Primary: {target_company['name']}")
    
    # Confirm the change
    print(f"\n⚠️  CONFIRMATION REQUIRED:")
    response = input(f"Do you want to make this change? (yes/no): ").lower().strip()
    
    if response != 'yes':
        print(f"❌ Update cancelled")
        return False
    
    # Make the update
    print(f"\n🔄 Updating primary association...")
    current_primary_id = current_state['current_primary']['id'] if current_state['current_primary'] else None
    
    success = update_primary_association(deal_id, new_primary_id, current_primary_id)
    
    if success:
        print(f"\n✅ SUCCESS: Primary company updated!")
        
        # Verify the change
        print(f"\n🔍 Verifying change...")
        new_state = get_deal_current_state(deal_id)
        
        if 'error' not in new_state:
            if new_state['current_primary'] and new_state['current_primary']['id'] == new_primary_id:
                print(f"✅ VERIFIED: {new_state['current_primary']['name']} is now primary")
                
                print(f"\n🏢 UPDATED ASSOCIATIONS:")
                for i, company in enumerate(new_state['companies'], 1):
                    primary_marker = " (PRIMARY)" if company['is_primary'] else ""
                    print(f"   {i}. {company['name']}{primary_marker}")
                    print(f"      ID: {company['id']}")
                
                return True
            else:
                print(f"⚠️  WARNING: Verification failed")
                if new_state['current_primary']:
                    print(f"   Current primary: {new_state['current_primary']['name']}")
                else:
                    print(f"   No primary company found")
        else:
            print(f"⚠️  Could not verify change: {new_state['error']}")
    
    return success

def main():
    """Main function"""
    
    print("🚀 SINGLE DEAL UPDATE - GLAM FILMS SA")
    print("=" * 60)
    print("This will update ONLY the GLAM FILMS SA deal (Example 1)")
    print("Making GLAM FILMS SA the primary company for this deal")
    
    success = update_glam_films_deal()
    
    if success:
        print(f"\n🎉 UPDATE COMPLETED SUCCESSFULLY!")
        print(f"The GLAM FILMS SA deal now has the correct primary company.")
    else:
        print(f"\n❌ UPDATE FAILED")
        print(f"Please check the errors above and try again.")

if __name__ == "__main__":
    main()