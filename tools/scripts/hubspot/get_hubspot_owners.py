#!/usr/bin/env python3
import os
import json
import requests
import argparse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Use HubSpot API to get owner information
def get_hubspot_owners(api_key=None):
    # Use API key from args if provided, otherwise from .env
    api_key = api_key or os.getenv('HUBSPOT_API_KEY')
    
    if not api_key:
        print("Error: No HubSpot API key provided. Please either:")
        print("1. Set HUBSPOT_API_KEY in your .env file")
        print("2. Provide the API key via command line argument: python get_hubspot_owners.py --api-key YOUR_API_KEY")
        return {}
    
    print("Fetching all HubSpot owners...")
    
    # Get all owners directly using the owners endpoint
    url = "https://api.hubapi.com/crm/v3/owners"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    owner_info = {}
    
    try:
        # Get active owners
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        owners = response.json().get("results", [])
        
        print(f"Found {len(owners)} active owners")
        
        # Process active owners
        for owner in owners:
            owner_id = owner.get("id")
            if owner_id:
                first_name = owner.get("firstName", "")
                last_name = owner.get("lastName", "")
                email = owner.get("email", "")
                user_id = owner.get("userId")
                teams = owner.get("teams", [])
                
                team_name = "Unknown"
                if teams and len(teams) > 0:
                    primary_teams = [team for team in teams if team.get("primary", False)]
                    if primary_teams:
                        team_name = primary_teams[0].get("name", "Unknown")
                    else:
                        team_name = teams[0].get("name", "Unknown")
                
                owner_info[owner_id] = {
                    "id": owner_id,
                    "firstName": first_name,
                    "lastName": last_name,
                    "fullName": f"{first_name} {last_name}".strip(),
                    "email": email,
                    "userId": user_id,
                    "team": team_name,
                    "archived": False
                }
                print(f"Owner ID: {owner_id}, Name: {first_name} {last_name}, Email: {email}, Team: {team_name}")
        
        # Get archived owners
        print("\nFetching archived owners...")
        archived_url = f"{url}?archived=true"
        archived_response = requests.get(archived_url, headers=headers)
        archived_response.raise_for_status()
        archived_owners = archived_response.json().get("results", [])
        
        print(f"Found {len(archived_owners)} archived owners")
        
        # Process archived owners
        for owner in archived_owners:
            owner_id = owner.get("id")
            if owner_id:
                first_name = owner.get("firstName", "")
                last_name = owner.get("lastName", "")
                email = owner.get("email", "")
                user_id_including_inactive = owner.get("userIdIncludingInactive")
                
                owner_info[owner_id] = {
                    "id": owner_id,
                    "firstName": first_name,
                    "lastName": last_name,
                    "fullName": f"{first_name} {last_name}".strip(),
                    "email": email,
                    "userId": None,
                    "userIdIncludingInactive": user_id_including_inactive,
                    "team": "Archived",
                    "archived": True
                }
                print(f"Owner ID: {owner_id}, Name: {first_name} {last_name}, Email: {email} (Archived)")
        
        # Save owner information to a file
        output_dir = "tools/outputs"
        os.makedirs(output_dir, exist_ok=True)
        
        with open(os.path.join(output_dir, "hubspot_owners.json"), "w") as f:
            json.dump(owner_info, f, indent=2)
            
        print(f"\nOwner information saved to tools/outputs/hubspot_owners.json")
        
        # Create text file with the table format
        with open(os.path.join(output_dir, "hubspot_owner_list_updated.txt"), "w") as f:
            f.write("# HubSpot Owner IDs and Names\n")
            f.write("# Retrieved using direct API method\n\n")
            f.write("| Owner ID | Full Name | Email | Team |\n")
            f.write("|----------|-----------|-------|------|\n")
            
            for owner_id, info in sorted(owner_info.items(), key=lambda x: x[0]):
                full_name = info.get('fullName', 'Unknown')
                email = info.get('email', 'Unknown')
                team = info.get('team', 'Unknown')
                
                f.write(f"| {owner_id} | {full_name} | {email} | {team} |\n")
        
        print(f"Updated owner list saved to tools/outputs/hubspot_owner_list_updated.txt")
        return owner_info
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {}

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Fetch HubSpot owner information')
    parser.add_argument('--api-key', help='HubSpot API key or access token')
    args = parser.parse_args()
    
    # Get owners with the API key from args or .env
    owners = get_hubspot_owners(args.api_key)
    
    if owners:
        # Print a summary table
        print("\nSummary of Owner IDs with Full Names:")
        print("-" * 80)
        print(f"{'Owner ID':<15} | {'Full Name':<30} | {'Email':<30} | {'Team':<15}")
        print("-" * 80)
        
        for owner_id, info in sorted(owners.items(), key=lambda x: x[0]):
            print(f"{owner_id:<15} | {info.get('fullName', 'Unknown'):<30} | {info.get('email', 'Unknown'):<30} | {info.get('team', 'Unknown'):<15}") 