#!/usr/bin/env python3
"""
Check and Update CUITs for Accountant Companies Found in Both Systems
Verifies if the 3 accountant companies have correct CUITs in HubSpot
"""

import sys
from typing import List, Dict

# Add the current directory to the path
sys.path.append('.')

# Import HubSpot API package
from hubspot_api.models import Company
from hubspot_api import get_client

# Import Colppy database package
from database.models import BaseModel

class Empresa(BaseModel):
    table_name = 'empresa'
    primary_key = 'IdEmpresa'

# The 3 accountant companies found in both systems
ACCOUNTANT_COMPANIES_TO_CHECK = [
    {
        'hubspot_id': '36233955731',
        'hubspot_name': '94778 - ALEJANDRO NICOLAS PEREZ',
        'empresa_id': '94778',
        'colppy_cuit': '20357299277'
    },
    {
        'hubspot_id': '36527860848',
        'hubspot_name': '95165 - COR CONSULTING ASOCIADOS  S R L',
        'empresa_id': '95165',
        'colppy_cuit': '30703967406'
    },
    {
        'hubspot_id': '9019095822',
        'hubspot_name': '31308 - Ombú Consulting Services S.A.',
        'empresa_id': '31308',
        'colppy_cuit': '30-60720870-7'
    }
]

def clean_cuit(cuit: str) -> str:
    """Clean CUIT to numeric format for comparison"""
    if not cuit:
        return ''
    import re
    return re.sub(r'[^0-9]', '', str(cuit))

def check_accountant_cuits():
    """Check current CUIT status in HubSpot for the 3 companies"""
    print('🔍 Checking CUITs for Accountant Companies Found in Both Systems')
    print('='*70)
    
    companies_needing_update = []
    
    for company_info in ACCOUNTANT_COMPANIES_TO_CHECK:
        hubspot_id = company_info['hubspot_id']
        hubspot_name = company_info['hubspot_name']
        empresa_id = company_info['empresa_id']
        colppy_cuit = company_info['colppy_cuit']
        colppy_cuit_clean = clean_cuit(colppy_cuit)
        
        print(f'\n📋 Checking: {hubspot_name}')
        print(f'   HubSpot ID: {hubspot_id}')
        print(f'   Empresa ID: {empresa_id}')
        print(f'   Colppy CUIT: {colppy_cuit} (cleaned: {colppy_cuit_clean})')
        
        try:
            # Get current HubSpot company data
            company = Company.find_by_id(hubspot_id, properties=['name', 'cuit'])
            
            if company:
                properties = company.get('properties', {})
                current_cuit = properties.get('cuit', '')
                current_cuit_clean = clean_cuit(current_cuit)
                
                print(f'   Current HubSpot CUIT: {current_cuit} (cleaned: {current_cuit_clean})')
                
                # Check if CUIT needs update
                if not current_cuit or current_cuit in ['', 'None', 'NOT SET']:
                    print(f'   ❌ CUIT is MISSING in HubSpot')
                    companies_needing_update.append({
                        'hubspot_id': hubspot_id,
                        'name': hubspot_name,
                        'current_cuit': current_cuit,
                        'new_cuit': colppy_cuit_clean,
                        'status': 'MISSING'
                    })
                elif current_cuit_clean != colppy_cuit_clean:
                    print(f'   ⚠️  CUIT MISMATCH: HubSpot has different CUIT')
                    companies_needing_update.append({
                        'hubspot_id': hubspot_id,
                        'name': hubspot_name,
                        'current_cuit': current_cuit,
                        'new_cuit': colppy_cuit_clean,
                        'status': 'MISMATCH'
                    })
                else:
                    print(f'   ✅ CUIT is CORRECT in HubSpot')
            else:
                print(f'   ❌ Company not found in HubSpot')
                
        except Exception as e:
            print(f'   ❌ Error checking company: {e}')
    
    return companies_needing_update

def update_accountant_cuits(companies_to_update: List[Dict]):
    """Update CUITs in HubSpot for companies that need it"""
    if not companies_to_update:
        print('\n✅ All accountant companies already have correct CUITs!')
        return True
    
    print(f'\n🔄 Updating {len(companies_to_update)} Companies with CUITs')
    print('='*60)
    
    client = get_client()
    successful_updates = 0
    
    for company in companies_to_update:
        try:
            hubspot_id = company['hubspot_id']
            new_cuit = company['new_cuit']
            name = company['name']
            status = company['status']
            
            print(f'\n📝 Updating: {name}')
            print(f'   Status: {status}')
            print(f'   Current CUIT: {company["current_cuit"] or "NOT SET"}')
            print(f'   New CUIT: {new_cuit}')
            
            # Update company
            response = client.patch(f'crm/v3/objects/companies/{hubspot_id}', {
                'properties': {'cuit': new_cuit}
            })
            
            if response:
                successful_updates += 1
                print(f'   ✅ CUIT successfully updated!')
            else:
                print(f'   ❌ Update failed')
                
        except Exception as e:
            print(f'   ❌ Error updating company: {e}')
    
    print(f'\n📊 Update Results:')
    print(f'   • Companies needing updates: {len(companies_to_update)}')
    print(f'   • Successful updates: {successful_updates}')
    print(f'   • Success rate: {successful_updates/len(companies_to_update)*100:.1f}%')
    
    return successful_updates == len(companies_to_update)

def verify_colppy_data():
    """Verify the CUIT data from Colppy for these companies"""
    print('\n🔍 Verifying Colppy Data for Accountant Companies')
    print('='*60)
    
    empresa_ids = [comp['empresa_id'] for comp in ACCOUNTANT_COMPANIES_TO_CHECK]
    
    try:
        # Query Colppy for these specific empresas
        id_list = ','.join(f"'{emp_id}'" for emp_id in empresa_ids)
        query = f"""
        SELECT IdEmpresa, CUIT, Nombre, razonSocial
        FROM empresa
        WHERE IdEmpresa IN ({id_list})
        """
        
        results = Empresa.execute_custom_query(query)
        
        print('\n📋 Colppy Data Verification:')
        for row in results:
            empresa_id = row.get('IdEmpresa')
            cuit = row.get('CUIT', '')
            nombre = row.get('Nombre', '')
            razon_social = row.get('razonSocial', '')
            
            print(f'\nEmpresa ID: {empresa_id}')
            print(f'   CUIT: {cuit}')
            print(f'   Nombre: {nombre}')
            print(f'   Razón Social: {razon_social}')
            
    except Exception as e:
        print(f'❌ Error verifying Colppy data: {e}')

def main():
    """Main execution function"""
    print('🚀 Accountant Company CUIT Verification & Update')
    print('='*70)
    
    # Step 1: Verify Colppy data
    verify_colppy_data()
    
    # Step 2: Check current CUIT status in HubSpot
    companies_needing_update = check_accountant_cuits()
    
    # Step 3: Update if needed
    if companies_needing_update:
        print(f'\n⚠️  Found {len(companies_needing_update)} companies needing CUIT updates')
        
        # Show summary
        print('\n📋 Companies Needing Updates:')
        for company in companies_needing_update:
            print(f'   - {company["name"]} ({company["status"]})')
        
        # Confirm updates
        print('\n⚠️  CONFIRMATION REQUIRED')
        print('This will update CUITs in your live HubSpot data.')
        confirmation = input('Do you want to proceed? (yes/no): ').strip().lower()
        
        if confirmation in ['yes', 'y']:
            success = update_accountant_cuits(companies_needing_update)
            
            if success:
                print('\n🎉 All CUITs updated successfully!')
            else:
                print('\n⚠️  Some updates failed')
        else:
            print('\n❌ Update cancelled')
    else:
        print('\n🎉 All accountant companies already have correct CUITs!')
    
    return True

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