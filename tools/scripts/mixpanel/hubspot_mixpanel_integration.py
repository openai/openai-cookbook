#!/usr/bin/env python3
import os
import sys
import json
import csv
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Output directory
OUTPUT_DIR = 'hubspot_mixpanel_integration'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Date range for deals
START_DATE = '2025-05-01'
END_DATE = '2025-05-31'

# Function to get closed won deals from HubSpot using direct API
def get_closed_won_deals_id_empresa_only():
    print("Using HubSpot API to fetch closed won deals with 'id_empresa'...")
    
    hubspot_api_key = os.getenv("HUBSPOT_API_KEY")
    if not hubspot_api_key:
        print("Error: HUBSPOT_API_KEY not found in environment variables")
        sys.exit(1)
        
    url = "https://api.hubapi.com/crm/v3/objects/deals/search"
    headers = {
        "Authorization": f"Bearer {hubspot_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "dealstage",
                        "operator": "EQ", 
                        "value": "closedwon"
                    },
                    {
                        "propertyName": "closedate",
                        "operator": "BETWEEN",
                        "value": START_DATE,
                        "highValue": END_DATE
                    }
                ]
            }
        ],
        "properties": [
            "id_empresa"
        ],
        "limit": 100
    }
    
    deals = []
    has_more = True
    after = None
    
    while has_more:
        if after:
            payload["after"] = after
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"Error fetching deals: {response.status_code}")
            print(response.text)
            sys.exit(1)
            
        data = response.json()
        deals.extend(data["results"])
        
        if "paging" in data and "next" in data["paging"]:
            after = data["paging"]["next"]["after"]
        else:
            has_more = False
    
    return deals

# Main function
def main():
    print(f"Starting HubSpot integration to fetch 'id_empresa' for deals closed between {START_DATE} and {END_DATE}")
    
    # Get closed won deals from HubSpot
    print("Fetching closed won deals from HubSpot...")
    deals = get_closed_won_deals_id_empresa_only()
    print(f"Found {len(deals)} closed won deals with 'id_empresa'")
    
    # Output the 'id_empresa' values
    for deal in deals:
        properties = deal['properties']
        id_empresa = properties.get('id_empresa', 'N/A')
        print(f"Deal ID: {deal['id']}, ID Empresa: {id_empresa}")
    
if __name__ == "__main__":
    main() 