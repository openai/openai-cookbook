#!/usr/bin/env python3
"""
Preview what would be updated for Referencia Empresa Administrada deals
Shows current state vs proposed changes without making any modifications
"""

import sys
import os
import json
from typing import Dict, List, Optional

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client
from hubspot_api.models import Deal, Company

def load_recommendations():
    """Load the recommendations from the JSON file"""
    
    import glob
    files = glob.glob("referencia_empresa_primary_changes_*.json")
    if not files:
        print("❌ No recommendations file found. Run the analysis first.")
        return None
    
    latest_file = max(files, key=os.path.getctime)
    print(f"📂 Loading recommendations from: {latest_file}")
    
    with open(latest_file, 'r') as f:
        return json.load(f)

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
        accountant_company = None
        
        for assoc in associations.get('results', []):
            company_id = str(assoc['toObjectId'])
            
            # Get company details
            company = Company.find_by_id(company_id, properties=['name', 'cuit'])
            
            if company:
                company_props = company.get('properties', {})
                
                # Analyze association types
                is_primary = False
                is_accountant = False
                labels = []
                
                for assoc_type in assoc.get('associationTypes', []):
                    label = assoc_type.get('label', '')
                    if label:
                        labels.append(label)
                    
                    if label == 'Primary':
                        is_primary = True
                    elif 'Estudio Contable' in str(label) or 'Asesor' in str(label) or 'Consultor' in str(label):
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
                if is_accountant:
                    accountant_company = company_info
        
        return {
            'deal_id': deal_id,
            'deal_name': deal_props.get('dealname', 'Unknown'),
            'amount': deal_props.get('amount', '0'),
            'id_empresa': deal_props.get('id_empresa', ''),
            'lead_source': deal_props.get('lead_source', ''),
            'companies': companies,
            'current_primary': current_primary,
            'accountant_company': accountant_company
        }
        
    except Exception as e:
        return {'error': str(e)}

def preview_single_change(recommendation: Dict) -> None:
    """Preview what would change for a single deal"""
    
    deal_id = recommendation['deal_id']
    deal_name = recommendation['deal_name']
    new_primary_name = recommendation['recommended_primary_name']
    new_primary_id = recommendation['recommended_primary_id']
    reason = recommendation['reason']
    
    print(f"\n{'='*80}")
    print(f"🔍 DEAL: {deal_name}")
    print(f"ID: {deal_id}")
    print(f"{'='*80}")
    
    # Get current state
    current_state = get_deal_current_state(deal_id)
    
    if 'error' in current_state:
        print(f"❌ Error: {current_state['error']}")
        return
    
    # Show deal info
    print(f"\n📊 DEAL INFORMATION:")
    print(f"   Name: {current_state['deal_name']}")
    print(f"   Amount: ${current_state['amount']}")
    print(f"   ID Empresa: {current_state['id_empresa']}")
    print(f"   Lead Source: {current_state['lead_source']}")
    
    # Show current associations
    print(f"\n🏢 CURRENT ASSOCIATIONS:")
    if current_state['companies']:
        for i, company in enumerate(current_state['companies'], 1):
            markers = []
            if company['is_primary']:
                markers.append("PRIMARY")
            if company['is_accountant']:
                markers.append("ACCOUNTANT")
            
            marker_str = f" ({', '.join(markers)})" if markers else ""
            
            print(f"   {i}. {company['name']}{marker_str}")
            print(f"      ID: {company['id']}")
            print(f"      CUIT: {company['cuit'] or 'NOT SET'}")
            if company['labels']:
                print(f"      Labels: {', '.join(company['labels'])}")
    else:
        print(f"   No associated companies found")
    
    # Show what would change
    print(f"\n🔄 PROPOSED CHANGE:")
    print(f"   Reason: {reason}")
    
    current_primary_name = current_state['current_primary']['name'] if current_state['current_primary'] else "NONE"
    
    print(f"\n   BEFORE:")
    print(f"   ├─ Primary Company: {current_primary_name}")
    if current_state['accountant_company']:
        print(f"   └─ Accountant: {current_state['accountant_company']['name']} (Associated)")
    
    print(f"\n   AFTER:")
    print(f"   ├─ Primary Company: {new_primary_name} (ACCOUNTANT)")
    
    # Find the customer company (non-accountant)
    customer_companies = [c for c in current_state['companies'] if not c['is_accountant']]
    if customer_companies:
        for customer in customer_companies:
            print(f"   └─ Customer: {customer['name']} (Associated)")
    
    # Show the specific API change that would be made
    print(f"\n🔧 TECHNICAL CHANGE:")
    if current_state['current_primary']:
        print(f"   1. Remove PRIMARY label from: {current_state['current_primary']['name']} (ID: {current_state['current_primary']['id']})")
    print(f"   2. Add PRIMARY label to: {new_primary_name} (ID: {new_primary_id})")
    
    # Show business impact
    print(f"\n💼 BUSINESS IMPACT:")
    print(f"   ✅ Accountant will be primary contact for deal")
    print(f"   ✅ Referral attribution will be correctly tracked")
    print(f"   ✅ Customer company remains associated for reference")
    print(f"   ✅ All existing associations are preserved")

def main():
    """Main preview function"""
    
    print("👁️  REFERENCIA EMPRESA ADMINISTRADA - UPDATE PREVIEW")
    print("=" * 80)
    print("This script shows what WOULD be changed without making any actual updates")
    
    # Load recommendations
    recommendations = load_recommendations()
    if not recommendations:
        return
    
    print(f"\n📊 Found {len(recommendations)} deals that would be updated")
    
    # Show first few deals as examples
    print(f"\n🔍 SHOWING FIRST 3 DEALS AS EXAMPLES:")
    
    for i, recommendation in enumerate(recommendations[:3], 1):
        print(f"\n\n{'🔸' * 40} EXAMPLE {i} {'🔸' * 40}")
        preview_single_change(recommendation)
    
    # Summary of all changes
    print(f"\n\n📋 SUMMARY OF ALL {len(recommendations)} PROPOSED CHANGES:")
    print("=" * 80)
    
    accountant_groups = {}
    
    for rec in recommendations:
        accountant = rec['recommended_primary_name']
        if accountant not in accountant_groups:
            accountant_groups[accountant] = []
        accountant_groups[accountant].append(rec['deal_name'])
    
    for accountant, deals in accountant_groups.items():
        print(f"\n🏢 {accountant} → Would become primary for {len(deals)} deals:")
        for deal in deals[:5]:  # Show first 5
            print(f"   • {deal}")
        if len(deals) > 5:
            print(f"   • ... and {len(deals) - 5} more deals")
    
    print(f"\n\n⚠️  WHAT HAPPENS NEXT:")
    print("=" * 80)
    print("1. Review the examples above to understand the changes")
    print("2. If you approve, I'll create the actual update script")
    print("3. The update script will process deals one by one with confirmation")
    print("4. Each change will be verified before proceeding to the next")
    
    print(f"\n✅ Ready to proceed with creating the update script?")

if __name__ == "__main__":
    main()