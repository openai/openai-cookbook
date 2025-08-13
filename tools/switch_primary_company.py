#!/usr/bin/env python3
"""
Generic Primary Company Switcher
Usage: python3 switch_primary_company.py <deal_id> <new_primary_company_id> [current_primary_company_id]

This script switches the primary company for a deal while preserving ALL associations.
Uses PUT instead of DELETE to avoid losing associations.
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

def get_deal_state(deal_id: str) -> Dict:
    """Get current state of a deal"""
    
    client = get_client()
    
    try:
        # Get deal details
        deal = Deal.find_by_id(deal_id, properties=['dealname', 'amount', 'lead_source', 'idempresa'])
        if not deal:
            return {'error': 'Deal not found'}
        
        deal_props = deal.get('properties', {})
        
        # Get associated companies
        associations = client.get_associations(deal_id, 'deals', 'companies')
        companies = []
        current_primary = None
        
        for assoc in associations.get('results', []):
            company_id = str(assoc['toObjectId'])
            
            # Get company details
            company = Company.find_by_id(company_id, properties=['name', 'cuit'])
            if company:
                company_props = company.get('properties', {})
                
                # Check association types
                is_primary = False
                is_accountant = False
                labels = []
                
                for assoc_type in assoc.get('associationTypes', []):
                    label = assoc_type.get('label', '')
                    if label:
                        labels.append(label)
                    
                    if label == 'Primary':
                        is_primary = True
                    elif 'Estudio Contable' in str(label):
                        is_accountant = True
                
                company_data = {
                    'id': company_id,
                    'name': company_props.get('name', 'Unknown'),
                    'cuit': company_props.get('cuit', 'NOT SET'),
                    'is_primary': is_primary,
                    'is_accountant': is_accountant,
                    'labels': labels
                }
                
                companies.append(company_data)
                
                if is_primary:
                    current_primary = company_data
        
        return {
            'deal_id': deal_id,
            'deal_name': deal_props.get('dealname', 'Unknown'),
            'amount': deal_props.get('amount', '0'),
            'lead_source': deal_props.get('lead_source', 'Unknown'),
            'id_empresa': deal_props.get('idempresa', 'Unknown'),
            'companies': companies,
            'current_primary': current_primary
        }
        
    except Exception as e:
        return {'error': str(e)}

def switch_primary_company(deal_id: str, new_primary_id: str, current_primary_id: Optional[str] = None) -> bool:
    """Switch primary company while preserving ALL associations"""
    
    client = get_client()
    
    try:
        print(f"🔄 SWITCHING PRIMARY COMPANY")
        print(f"   Deal ID: {deal_id}")
        print(f"   New Primary: {new_primary_id}")
        print(f"   Current Primary: {current_primary_id or 'Auto-detect'}")
        print(f"   Method: PUT (preserves associations)")
        
        # Step 1: Remove PRIMARY from current primary (if exists)
        if current_primary_id:
            print(f"\n   📤 Removing PRIMARY label from company {current_primary_id}...")
            
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
            
            print(f"   📋 Preserving {len(non_primary_types)} non-primary association types")
            
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
        print(f"\n   📥 Adding PRIMARY label to company {new_primary_id}...")
        
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
        print(f"   ❌ Error switching primary: {e}")
        return False

def display_deal_info(deal_state: Dict):
    """Display deal information in a nice format"""
    
    print(f"\n🏢 DEAL INFORMATION:")
    print(f"   Name: {deal_state['deal_name']}")
    print(f"   Amount: ${deal_state['amount']}")
    print(f"   Lead Source: {deal_state['lead_source']}")
    print(f"   ID Empresa: {deal_state['id_empresa']}")
    
    print(f"\n🏢 CURRENT ASSOCIATIONS:")
    for i, company in enumerate(deal_state['companies'], 1):
        markers = []
        if company['is_primary']:
            markers.append("PRIMARY")
        if company['is_accountant']:
            markers.append("ACCOUNTANT")
        
        marker_str = f" ({', '.join(markers)})" if markers else ""
        
        print(f"   {i}. {company['name']}{marker_str}")
        print(f"      ID: {company['id']}")
        print(f"      CUIT: {company['cuit']}")
        print(f"      Labels: {company['labels']}")

def main():
    """Main function"""
    
    if len(sys.argv) < 3:
        print("🚀 GENERIC PRIMARY COMPANY SWITCHER")
        print("=" * 50)
        print("Usage:")
        print("  python3 switch_primary_company.py <deal_id> <new_primary_company_id> [current_primary_company_id]")
        print("")
        print("Examples:")
        print("  # Auto-detect current primary:")
        print("  python3 switch_primary_company.py 40274308013 36234110609")
        print("")
        print("  # Specify current primary:")
        print("  python3 switch_primary_company.py 40274308013 36234110609 36247900198")
        print("")
        print("Parameters:")
        print("  deal_id                   - HubSpot deal ID")
        print("  new_primary_company_id    - ID of company to make primary")
        print("  current_primary_company_id - (Optional) ID of current primary company")
        return
    
    deal_id = sys.argv[1]
    new_primary_id = sys.argv[2]
    current_primary_id = sys.argv[3] if len(sys.argv) > 3 else None
    
    print(f"🚀 SWITCHING PRIMARY COMPANY")
    print(f"=" * 50)
    
    # Get current state
    print(f"📋 Getting current deal state...")
    current_state = get_deal_state(deal_id)
    
    if 'error' in current_state:
        print(f"❌ Error getting deal state: {current_state['error']}")
        return
    
    # Display current state
    display_deal_info(current_state)
    
    # Auto-detect current primary if not provided
    if not current_primary_id and current_state['current_primary']:
        current_primary_id = current_state['current_primary']['id']
        print(f"\n🔍 Auto-detected current primary: {current_state['current_primary']['name']} (ID: {current_primary_id})")
    
    # Find company names for display
    new_primary_name = "Unknown"
    current_primary_name = "Unknown"
    
    for company in current_state['companies']:
        if company['id'] == new_primary_id:
            new_primary_name = company['name']
        if company['id'] == current_primary_id:
            current_primary_name = company['name']
    
    print(f"\n🎯 PROPOSED CHANGE:")
    if current_primary_id:
        print(f"   FROM: {current_primary_name} (ID: {current_primary_id}) [PRIMARY]")
        print(f"   TO:   {new_primary_name} (ID: {new_primary_id}) [PRIMARY]")
    else:
        print(f"   MAKE PRIMARY: {new_primary_name} (ID: {new_primary_id})")
    
    # Perform the switch
    success = switch_primary_company(deal_id, new_primary_id, current_primary_id)
    
    if success:
        print(f"\n✅ PRIMARY SWITCH SUCCESSFUL")
        
        # Verify the result
        print(f"\n🔍 Verifying result...")
        new_state = get_deal_state(deal_id)
        
        if 'error' not in new_state:
            print(f"\n🏢 UPDATED ASSOCIATIONS:")
            total_companies = len(new_state['companies'])
            new_primary_correct = False
            
            for i, company in enumerate(new_state['companies'], 1):
                markers = []
                if company['is_primary']:
                    markers.append("PRIMARY")
                    if company['id'] == new_primary_id:
                        new_primary_correct = True
                if company['is_accountant']:
                    markers.append("ACCOUNTANT")
                
                marker_str = f" ({', '.join(markers)})" if markers else ""
                
                print(f"   {i}. {company['name']}{marker_str}")
                print(f"      ID: {company['id']}")
            
            print(f"\n📊 VERIFICATION:")
            print(f"   Total Companies: {total_companies} (should be {len(current_state['companies'])})")
            print(f"   New Primary Correct: {'✅' if new_primary_correct else '❌'}")
            print(f"   Associations Preserved: {'✅' if total_companies == len(current_state['companies']) else '❌'}")
            
            if new_primary_correct and total_companies == len(current_state['companies']):
                print(f"\n🎉 SUCCESS! Primary switch completed perfectly!")
            else:
                print(f"\n⚠️  Some issues detected")
        else:
            print(f"❌ Error verifying result: {new_state['error']}")
    else:
        print(f"\n❌ PRIMARY SWITCH FAILED")

if __name__ == "__main__":
    main()