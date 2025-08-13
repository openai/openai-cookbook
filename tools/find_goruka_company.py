#!/usr/bin/env python3
"""
Find the GORUKA company to get the correct ID
"""

import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hubspot_api.models import Company

def find_goruka():
    """Find GORUKA company"""
    
    print("🔍 SEARCHING FOR GORUKA COMPANY")
    print("=" * 50)
    
    # Search for companies with GORUKA in the name
    companies = Company.search(
        filters=[{
            'propertyName': 'name',
            'operator': 'CONTAINS_TOKEN',
            'value': 'GORUKA'
        }],
        properties=['name', 'cuit', 'hs_object_id'],
        limit=10
    )
    
    results = companies.get('results', [])
    
    print(f"Found {len(results)} companies with 'GORUKA' in name:")
    
    for company in results:
        props = company.get('properties', {})
        print(f"\n🏢 {props.get('name', 'Unknown')}")
        print(f"   ID: {company['id']}")
        print(f"   CUIT: {props.get('cuit', 'NOT SET')}")
        print(f"   Object ID: {props.get('hs_object_id', 'NOT SET')}")

def main():
    find_goruka()

if __name__ == "__main__":
    main()