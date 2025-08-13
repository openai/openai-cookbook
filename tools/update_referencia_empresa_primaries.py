#!/usr/bin/env python3
"""
Update Primary Company Associations for Referencia Empresa Administrada Deals
Processes deals one by one with confirmation for testing
"""

import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Optional

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Deal, Company

def load_recommendations():
    """Load the recommendations from the JSON file"""
    
    # Find the most recent recommendations file
    import glob
    files = glob.glob("referencia_empresa_primary_changes_*.json")
    if not files:
        print("❌ No recommendations file found. Run the analysis first.")
        return None
    
    latest_file = max(files, key=os.path.getctime)
    print(f"📂 Loading recommendations from: {latest_file}")
    
    with open(latest_file, 'r') as f:
        return json.load(f)

def get_deal_associations(deal_id: str) -> Dict:
    """Get current associations for a deal"""
    
    client = get_client()
    
    try:
        # Get deal details
        deal = Deal.find_by_id(deal_id)
        if not deal:
            return {'error': f'Deal {deal_id} not found'}
        
        # Get associations
        associations = client.get_associations(deal_id, 'deals', 'companies')
        
        companies = []
        current_primary = None
        
        for assoc in associations.get('results', []):
            company_id = str(assoc['toObjectId'])
            
            # Get company details
            company = Company.find_by_id(company_id, properties=[
                'name', 'cuit', 'hs_object_id'
            ])
            
            if company:
                company_props = company.get('properties', {})
                
                # Check if this is primary
                is_primary = False
                is_accountant = False
                labels = []
                
                for assoc_type in assoc.get('associationTypes', []):
                    label = assoc_type.get('label', '')
                    if label:
                        labels.append(label)
                    
                    if label == 'Primary':
                        is_primary = True
                    elif 'Estudio Contable' in str(label) or 'Asesor' in str(label):
                        is_accountant = True
                
                company_info = {
                    'id': company_id,
                    'name': company_props.get('name', 'Unknown'),
                    'cuit': company_props.get('cuit', ''),
                    'is_primary': is_primary,
                    'is_accountant': is_accountant,
                    'labels': labels
                }
                
                companies.append(company_info)
                
                if is_primary:
                    current_primary = company_info
        
        return {
            'deal': deal,
            'companies': companies,
            'current_primary': current_primary
        }
        
    except Exception as e:
        return {'error': str(e)}

def update_primary_association(deal_id: str, current_primary_id: Optional[str], new_primary_id: str) -> bool:
    """Update the primary association for a deal"""
    
    client = get_client()
    
    try:
        # HubSpot API endpoint for updating associations
        # First, we need to remove current primary if exists
        if current_primary_id:
            # Remove primary association
            endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{current_primary_id}"
            payload = [
                {
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": 5  # Primary association type
                }
            ]
            
            try:
                client.session.delete(f"{client.config.base_url}/{endpoint}", json=payload)
                print(f"   ✅ Removed primary association from company {current_primary_id}")
            except Exception as e:
                print(f"   ⚠️  Note: Could not remove existing primary (may not exist): {e}")
        
        # Add new primary association
        endpoint = f"crm/v4/objects/deals/{deal_id}/associations/companies/{new_primary_id}"
        payload = [
            {
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 5  # Primary association type
            }
        ]
        
        response = client.session.put(f"{client.config.base_url}/{endpoint}", json=payload)
        response.raise_for_status()
        
        print(f"   ✅ Set company {new_primary_id} as primary")
        return True
        
    except Exception as e:
        print(f"   ❌ Error updating association: {e}")
        return False

def process_single_deal(recommendation: Dict, test_mode: bool = True) -> bool:
    """Process a single deal update with confirmation"""
    
    deal_id = recommendation['deal_id']
    deal_name = recommendation['deal_name']
    current_primary_name = recommendation.get('current_primary_name', 'NONE')
    new_primary_name = recommendation['recommended_primary_name']
    new_primary_id = recommendation['recommended_primary_id']
    reason = recommendation['reason']
    
    print(f"\n🔄 PROCESSING DEAL:")
    print(f"=" * 60)
    print(f"Deal: {deal_name}")
    print(f"Deal ID: {deal_id}")
    print(f"Current Primary: {current_primary_name}")
    print(f"→ Change to: {new_primary_name}")
    print(f"Reason: {reason}")
    
    # Get current state
    print(f"\n📋 Getting current associations...")
    current_state = get_deal_associations(deal_id)
    
    if 'error' in current_state:
        print(f"❌ Error: {current_state['error']}")
        return False
    
    # Display current associations
    print(f"\n🏢 Current Associations:")
    for i, company in enumerate(current_state['companies'], 1):
        primary_marker = " (PRIMARY)" if company['is_primary'] else ""
        accountant_marker = " (ACCOUNTANT)" if company['is_accountant'] else ""
        print(f"   {i}. {company['name']}{primary_marker}{accountant_marker}")
        print(f"      ID: {company['id']}")
        print(f"      CUIT: {company['cuit'] or 'NOT SET'}")
        if company['labels']:
            print(f"      Labels: {', '.join(company['labels'])}")
    
    # Confirm the change
    if test_mode:
        print(f"\n⚠️  TEST MODE - No actual changes will be made")
        response = input(f"\nDo you want to SIMULATE this change? (y/n): ").lower().strip()
    else:
        response = input(f"\nDo you want to make this change? (y/n): ").lower().strip()
    
    if response != 'y':
        print(f"❌ Skipped")
        return False
    
    if test_mode:
        print(f"✅ SIMULATED: Would change primary to {new_primary_name}")
        return True
    
    # Get current primary ID
    current_primary_id = None
    if current_state['current_primary']:
        current_primary_id = current_state['current_primary']['id']
    
    # Make the update
    print(f"\n🔄 Updating primary association...")
    success = update_primary_association(deal_id, current_primary_id, new_primary_id)
    
    if success:
        print(f"✅ SUCCESS: Primary company updated")
        
        # Verify the change
        print(f"\n🔍 Verifying change...")
        new_state = get_deal_associations(deal_id)
        
        if 'error' not in new_state and new_state['current_primary']:
            if new_state['current_primary']['id'] == new_primary_id:
                print(f"✅ VERIFIED: {new_state['current_primary']['name']} is now primary")
            else:
                print(f"⚠️  WARNING: Primary is {new_state['current_primary']['name']}, expected {new_primary_name}")
        else:
            print(f"⚠️  Could not verify change")
    
    return success

def main():
    """Main function to process deal updates"""
    
    print("🔄 REFERENCIA EMPRESA ADMINISTRADA - PRIMARY COMPANY UPDATER")
    print("=" * 70)
    
    # Load recommendations
    recommendations = load_recommendations()
    if not recommendations:
        return
    
    print(f"📊 Found {len(recommendations)} deals to update")
    
    # Ask for mode
    mode = input(f"\nSelect mode:\n1. Test mode (simulate changes)\n2. Live mode (make actual changes)\nEnter choice (1 or 2): ").strip()
    
    test_mode = mode != '2'
    
    if test_mode:
        print(f"\n🧪 TEST MODE: No actual changes will be made")
    else:
        print(f"\n🚨 LIVE MODE: Real changes will be made to HubSpot")
        confirm = input(f"Are you sure? (yes/no): ").lower().strip()
        if confirm != 'yes':
            print(f"❌ Cancelled")
            return
    
    # Process deals one by one
    successful = 0
    skipped = 0
    failed = 0
    
    for i, recommendation in enumerate(recommendations, 1):
        print(f"\n\n{'='*70}")
        print(f"DEAL {i} of {len(recommendations)}")
        
        try:
            result = process_single_deal(recommendation, test_mode)
            if result:
                successful += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"❌ Error processing deal: {e}")
            failed += 1
        
        # Ask to continue after first deal
        if i == 1:
            continue_response = input(f"\nContinue with remaining deals? (y/n): ").lower().strip()
            if continue_response != 'y':
                print(f"🛑 Stopped by user")
                break
    
    # Summary
    print(f"\n\n📊 SUMMARY:")
    print(f"=" * 70)
    print(f"Successful: {successful}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    print(f"Total processed: {successful + skipped + failed}")

if __name__ == "__main__":
    main()