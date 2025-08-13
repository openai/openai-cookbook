#!/usr/bin/env python3
"""
Restore the accountant's Estudio Contable label
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api import get_client

def restore_accountant_label():
    """Restore the Estudio Contable label to the accountant"""
    
    deal_id = "40272444002"
    accountant_id = "36234110609"
    
    print(f"🔧 RESTORING ACCOUNTANT LABEL")
    print(f"=" * 50)
    
    client = get_client()
    
    try:
        # Add the accountant label
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
            print(f"✅ Restored Estudio Contable label")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    success = restore_accountant_label()
    
    if success:
        print(f"\n✅ Label restored!")
        print(f"Contador Alejandro Perez now has both:")
        print(f"• PRIMARY label")
        print(f"• Estudio Contable label")

if __name__ == "__main__":
    main()