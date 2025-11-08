#!/usr/bin/env python3
"""
Check specific collaborators
Purpose: Check the specific collaborator IDs from the deal
"""

import os
import requests
import json

def check_specific_user(user_id: str, access_token: str) -> dict:
    """Check a specific user by ID"""
    print(f"🔍 CHECKING USER: {user_id}")
    print("-" * 50)
    
    try:
        # Try Users API first
        url = f"https://api.hubspot.com/settings/v3/users/{user_id}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ USERS API SUCCESS: {user_id}")
            print(f"📋 Raw data: {json.dumps(data, indent=2)}")
            
            first_name = data.get('firstName', '')
            last_name = data.get('lastName', '')
            full_name = f"{first_name} {last_name}".strip()
            email = data.get('email', 'No email')
            team_id = data.get('teamId', 'No team')
            
            print(f"👤 Name: '{full_name}'")
            print(f"📧 Email: {email}")
            print(f"🏢 Team ID: {team_id}")
            
            # Check if this could be Karina
            if 'karina' in full_name.lower() or 'karina' in email.lower():
                print(f"🎯 POTENTIAL KARINA: This could be the user we're looking for!")
            
            return data
        else:
            print(f"❌ USERS API FAILED: Status {response.status_code}")
            print(f"📄 Error: {response.text[:200]}")
            
            # Try Owners API as fallback
            print(f"🔄 TRYING OWNERS API FALLBACK...")
            url = f"https://api.hubspot.com/crm/v3/owners/{user_id}"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ OWNERS API SUCCESS: {user_id}")
                print(f"📋 Raw data: {json.dumps(data, indent=2)}")
                
                first_name = data.get('firstName', '')
                last_name = data.get('lastName', '')
                full_name = f"{first_name} {last_name}".strip()
                email = data.get('email', 'No email')
                
                print(f"👤 Name: '{full_name}'")
                print(f"📧 Email: {email}")
                print(f"🏢 Team: Not available in Owners API")
                
                return data
            else:
                print(f"❌ OWNERS API ALSO FAILED: Status {response.status_code}")
                print(f"📄 Error: {response.text[:200]}")
                return None
            
    except Exception as e:
        print(f"💥 EXCEPTION: {str(e)}")
        return None

def main():
    """Main function"""
    print("🔧 HubSpot Collaborator Checker")
    print("=" * 80)
    
    # Get access token
    access_token = "REPLACED_API_KEY"
    
    # Check the specific collaborators from the deal
    collaborator_ids = ["103406387", "79369461"]
    
    for user_id in collaborator_ids:
        print(f"\n📊 CHECKING COLLABORATOR: {user_id}")
        print("=" * 80)
        user_data = check_specific_user(user_id, access_token)
        
        if user_data:
            print(f"✅ Successfully retrieved data for {user_id}")
        else:
            print(f"❌ Failed to retrieve data for {user_id}")
    
    print("\n" + "=" * 80)
    print("📊 COLLABORATOR CHECK SUMMARY")
    print("=" * 80)
    print("These are the collaborator IDs from the deal:")
    print("- 103406387")
    print("- 79369461")
    print("\nIf neither of these is Karina, the issue might be:")
    print("1. Karina is not actually a collaborator on this deal")
    print("2. The collaborator IDs have changed")
    print("3. Karina is assigned to a different deal")

if __name__ == "__main__":
    main()
