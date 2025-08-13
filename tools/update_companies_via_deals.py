#!/usr/bin/env python3
"""
Update Companies with CUITs via Deal Associations
Gets July 2025 closed won deals, finds associated companies, and updates missing CUITs
"""

import sys
import json
from typing import List, Dict, Optional

# Add the current directory to the path
sys.path.append('.')

# Import HubSpot API package
from hubspot_api.models import Deal, Company
from hubspot_api.query_builder import closed_won_deals_in_july_2025
from hubspot_api import get_client

# Import Colppy database package
from database.models import BaseModel

class Empresa(BaseModel):
    table_name = 'empresa'
    primary_key = 'IdEmpresa'

def get_july_2025_deals_sample(limit: int = 5):
    """Get a sample of July 2025 closed won deals"""
    print(f'🎯 Getting {limit} July 2025 Closed Won Deals')
    print('='*50)
    
    try:
        # Get deals using our pre-built query
        deals = closed_won_deals_in_july_2025().limit(limit).execute()
        
        deal_results = deals.get('results', [])
        print(f'✅ Retrieved {len(deal_results)} closed won deals')
        
        # Process deals and extract info
        deal_info = []
        for deal in deal_results:
            properties = deal.get('properties', {})
            deal_data = {
                'deal_id': deal.get('id'),
                'deal_name': properties.get('dealname', ''),
                'amount': properties.get('amount', '0'),
                'id_empresa': properties.get('id_empresa', ''),
                'createdate': properties.get('createdate', '')
            }
            
            if deal_data['id_empresa']:  # Only include deals with id_empresa
                deal_info.append(deal_data)
        
        print('\n📋 Sample deals with ID Empresa:')
        print('Deal ID      | ID Empresa | Amount    | Deal Name')
        print('-'*70)
        
        for deal in deal_info[:limit]:
            amount = f"${int(deal['amount']):,}" if deal['amount'].isdigit() else deal['amount']
            print(f'{deal["deal_id"]:12} | {deal["id_empresa"]:10} | {amount:>9} | {deal["deal_name"][:30]}')
        
        return deal_info[:limit]
        
    except Exception as e:
        print(f'❌ Error fetching deals: {e}')
        return []

def get_deal_associations(deal_ids: List[str]):
    """Get company associations for deals"""
    print(f'\n🔗 Getting Company Associations for {len(deal_ids)} Deals')
    print('='*60)
    
    client = get_client()
    deal_company_map = {}
    
    for i, deal_id in enumerate(deal_ids, 1):
        try:
            print(f'   {i:2d}/{len(deal_ids)} Getting associations for deal {deal_id}...', end=' ')
            
            # Get deal-company associations
            response = client.get(f'crm/v4/objects/deals/{deal_id}/associations/companies')
            
            if response and 'results' in response:
                associations = response['results']
                
                if associations:
                    # Take the first company association
                    company_id = associations[0]['toObjectId']
                    deal_company_map[deal_id] = company_id
                    print(f'✅ Company ID: {company_id}')
                else:
                    print('⚠️  No company associations')
            else:
                print('❌ No associations found')
                
        except Exception as e:
            print(f'❌ Error: {str(e)[:30]}...')
    
    print(f'\n📊 Found {len(deal_company_map)} deal-company associations')
    return deal_company_map

def get_company_details(company_ids: List[str]):
    """Get company details from HubSpot"""
    print(f'\n📋 Getting Company Details for {len(company_ids)} Companies')
    print('='*60)
    
    companies_data = {}
    
    for i, company_id in enumerate(company_ids, 1):
        try:
            print(f'   {i:2d}/{len(company_ids)} Getting company {company_id}...', end=' ')
            
            # Get company details
            company = Company.find_by_id(company_id, properties=[
                'name', 'cuit', 'domain', 'createdate', 'id_empresa', 'colppy_id'
            ])
            
            if company:
                properties = company.get('properties', {})
                companies_data[company_id] = {
                    'hubspot_id': company_id,
                    'name': properties.get('name', 'Unknown'),
                    'current_cuit': properties.get('cuit', 'NOT SET'),
                    'domain': properties.get('domain', ''),
                    'id_empresa': properties.get('id_empresa', ''),
                    'colppy_id': properties.get('colppy_id', '')
                }
                
                current_cuit = properties.get('cuit', 'NOT SET')
                name = properties.get('name', 'Unknown')[:25]
                print(f'✅ {name} - CUIT: {current_cuit}')
            else:
                print('❌ Company not found')
                
        except Exception as e:
            print(f'❌ Error: {str(e)[:30]}...')
    
    print(f'\n📊 Retrieved {len(companies_data)} company records')
    return companies_data

def get_cuits_from_colppy(empresa_ids: List[str]):
    """Get CUITs from Colppy database for given empresa IDs"""
    print(f'\n🔍 Getting CUITs from Colppy for {len(empresa_ids)} Companies')
    print('='*60)
    
    colppy_cuits = {}
    
    for i, empresa_id in enumerate(empresa_ids, 1):
        try:
            print(f'   {i:2d}/{len(empresa_ids)} Querying empresa {empresa_id}...', end=' ')
            
            company = Empresa.find_by_id(empresa_id)
            
            if company:
                data = company.to_dict()
                cuit = data.get('CUIT', '').strip()
                
                if cuit and cuit != '':
                    # Clean CUIT
                    import re
                    clean_cuit = re.sub(r'[^0-9]', '', cuit)
                    
                    if len(clean_cuit) >= 10:
                        colppy_cuits[empresa_id] = {
                            'cuit': clean_cuit,
                            'original_cuit': cuit,
                            'nombre': data.get('Nombre', ''),
                            'localidad': data.get('localidad', '')
                        }
                        print(f'✅ CUIT: {clean_cuit} - {data.get("Nombre", "")[:25]}')
                    else:
                        print(f'⚠️  Invalid CUIT format: {cuit}')
                else:
                    print('❌ No CUIT found')
            else:
                print('❌ Company not found in Colppy')
                
        except Exception as e:
            print(f'❌ Error: {str(e)[:30]}...')
    
    print(f'\n📊 Found {len(colppy_cuits)} valid CUITs in Colppy')
    return colppy_cuits

def plan_cuit_updates(deals_data: List[Dict], deal_company_map: Dict, companies_data: Dict, colppy_cuits: Dict):
    """Plan which companies need CUIT updates"""
    print(f'\n📋 Planning CUIT Updates')
    print('='*40)
    
    updates_needed = []
    
    for deal in deals_data:
        deal_id = deal['deal_id']
        empresa_id = deal['id_empresa']
        
        if deal_id in deal_company_map:
            company_id = deal_company_map[deal_id]
            
            if company_id in companies_data:
                company = companies_data[company_id]
                current_cuit = company['current_cuit']
                
                # Check if company needs CUIT update
                needs_update = current_cuit in ['NOT SET', '', None]
                
                if needs_update and empresa_id in colppy_cuits:
                    colppy_data = colppy_cuits[empresa_id]
                    
                    update_plan = {
                        'deal_id': deal_id,
                        'deal_name': deal['deal_name'],
                        'deal_amount': deal['amount'],
                        'empresa_id': empresa_id,
                        'company_id': company_id,
                        'company_name': company['name'],
                        'current_cuit': current_cuit,
                        'new_cuit': colppy_data['cuit'],
                        'colppy_name': colppy_data['nombre']
                    }
                    
                    updates_needed.append(update_plan)
                    print(f'   ✅ {empresa_id}: {company["name"][:30]} needs CUIT {colppy_data["cuit"]}')
                elif not needs_update:
                    print(f'   ⚪ {empresa_id}: {company["name"][:30]} already has CUIT {current_cuit}')
                else:
                    print(f'   ⚠️  {empresa_id}: Company found but no CUIT in Colppy')
            else:
                print(f'   ❌ {empresa_id}: Company {company_id} details not found')
        else:
            print(f'   ❌ {empresa_id}: No company association for deal {deal_id}')
    
    print(f'\n📊 Update Summary:')
    print(f'   • Total deals analyzed: {len(deals_data)}')
    print(f'   • Companies needing CUIT updates: {len(updates_needed)}')
    
    return updates_needed

def preview_updates(updates: List[Dict]):
    """Preview the planned updates"""
    if not updates:
        print('\n✅ No CUIT updates needed!')
        return
    
    print(f'\n📋 PREVIEW: {len(updates)} CUIT Updates')
    print('='*100)
    print('Company ID | Empresa ID | Company Name              | Current CUIT | New CUIT    | Deal Amount')
    print('-'*100)
    
    for update in updates:
        amount = f"${int(update['deal_amount']):,}" if update['deal_amount'].isdigit() else update['deal_amount']
        current_cuit = update["current_cuit"] if update["current_cuit"] else "NOT SET"
        print(f'{update["company_id"]:10} | {update["empresa_id"]:10} | {update["company_name"][:25]:<25} | {current_cuit:<12} | {update["new_cuit"]:<11} | {amount:>11}')

def perform_cuit_updates(updates: List[Dict]):
    """Perform the CUIT updates in HubSpot"""
    if not updates:
        return True
    
    print(f'\n🔄 Performing {len(updates)} CUIT Updates')
    print('='*50)
    
    client = get_client()
    successful_updates = 0
    
    for i, update in enumerate(updates, 1):
        try:
            company_id = update['company_id']
            new_cuit = update['new_cuit']
            company_name = update['company_name']
            
            print(f'   {i:2d}/{len(updates)} Updating {company_name[:25]}...', end=' ')
            
            # Update company with CUIT
            response = client.patch(f'crm/v3/objects/companies/{company_id}', {
                'properties': {'cuit': new_cuit}
            })
            
            if response:
                successful_updates += 1
                print(f'✅ CUIT updated to {new_cuit}')
            else:
                print('❌ Update failed')
                
        except Exception as e:
            print(f'❌ Error: {str(e)[:40]}...')
    
    print(f'\n📊 Update Results:')
    print(f'   • Successful: {successful_updates}/{len(updates)}')
    print(f'   • Success rate: {successful_updates/len(updates)*100:.1f}%')
    
    return successful_updates == len(updates)

def main():
    """Main execution function"""
    print('🚀 Update Companies with CUITs via Deal Associations')
    print('='*70)
    print('📊 Focus: July 2025 closed won deals (5 deals sample)')
    print()
    
    # Step 1: Get July 2025 deals
    deals_data = get_july_2025_deals_sample(5)
    if not deals_data:
        print('❌ No deals found')
        return False
    
    # Step 2: Get deal-company associations
    deal_ids = [deal['deal_id'] for deal in deals_data]
    deal_company_map = get_deal_associations(deal_ids)
    
    if not deal_company_map:
        print('❌ No company associations found')
        return False
    
    # Step 3: Get company details from HubSpot
    company_ids = list(deal_company_map.values())
    companies_data = get_company_details(company_ids)
    
    # Step 4: Get CUITs from Colppy
    empresa_ids = [deal['id_empresa'] for deal in deals_data if deal['id_empresa']]
    colppy_cuits = get_cuits_from_colppy(empresa_ids)
    
    # Step 5: Plan updates
    updates_needed = plan_cuit_updates(deals_data, deal_company_map, companies_data, colppy_cuits)
    
    # Step 6: Preview updates
    preview_updates(updates_needed)
    
    if not updates_needed:
        print('\n🎉 All companies already have CUITs!')
        return True
    
    # Step 7: Confirm updates
    print(f'\n⚠️  CONFIRMATION REQUIRED')
    print('='*30)
    print(f'About to update {len(updates_needed)} companies in HubSpot with CUITs')
    print('This will modify your live HubSpot data.')
    print()
    
    confirmation = input('Do you want to proceed? (yes/no): ').strip().lower()
    
    if confirmation not in ['yes', 'y']:
        print('❌ Update cancelled')
        return False
    
    # Step 8: Perform updates
    success = perform_cuit_updates(updates_needed)
    
    if success:
        print('\n🎉 CUIT updates completed successfully!')
    else:
        print('\n⚠️  Some updates failed')
    
    return success

if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print('\n⚠️  Cancelled by user')
        sys.exit(1)
    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)