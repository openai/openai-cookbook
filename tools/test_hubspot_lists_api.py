#!/usr/bin/env python3
"""
Test HubSpot Lists API beyond MCP tools
Using direct REST API calls to access list memberships
"""

import os
import requests
import json
from typing import Dict, List, Optional

class HubSpotListsAPI:
    """Direct HubSpot Lists API client"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from environment or parameter"""
        self.api_key = api_key or os.getenv('HUBSPOT_API_KEY')
        if not self.api_key:
            raise ValueError("HubSpot API key required")
        
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def get_lists(self, limit: int = 100, after: str = None) -> Dict:
        """Get all lists"""
        url = f"{self.base_url}/crm/v3/lists"
        params = {"limit": limit}
        if after:
            params["after"] = after
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_list_details(self, list_id: str) -> Dict:
        """Get details of a specific list"""
        url = f"{self.base_url}/crm/v3/lists/{list_id}"
        
        response = requests.get(url, headers=self.headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    
    def get_list_members(self, list_id: str, limit: int = 100, after: str = None) -> Dict:
        """Get members of a specific list"""
        url = f"{self.base_url}/crm/v3/lists/{list_id}/contacts"
        params = {"limit": limit}
        if after:
            params["after"] = after
        
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 404:
            return {"results": [], "total": 0}
        response.raise_for_status()
        return response.json()
    
    def get_all_list_members(self, list_id: str, max_results: int = None) -> List[Dict]:
        """Get all members of a list with pagination"""
        all_members = []
        after = None
        total_fetched = 0
        
        while True:
            response = self.get_list_members(list_id, after=after)
            members = response.get("results", [])
            all_members.extend(members)
            total_fetched += len(members)
            
            print(f"Fetched {len(members)} members, total: {total_fetched}")
            
            # Check pagination
            paging = response.get("paging", {})
            next_page = paging.get("next", {})
            after = next_page.get("after")
            
            # Stop if no more pages or max results reached
            if not after or (max_results and total_fetched >= max_results):
                break
        
        return all_members
    
    def get_list_by_name(self, name: str) -> Optional[Dict]:
        """Find a list by name"""
        lists_response = self.get_lists()
        lists = lists_response.get("results", [])
        
        for list_item in lists:
            if list_item.get("name") == name:
                return list_item
        
        return None

def test_lists_api():
    """Test the Lists API functionality"""
    try:
        client = HubSpotListsAPI()
        
        print("🔍 Testing HubSpot Lists API...")
        print("=" * 50)
        
        # Test 1: Get all lists
        print("\n1. Getting all lists...")
        lists_response = client.get_lists()
        lists = lists_response.get("results", [])
        print(f"Found {len(lists)} lists")
        
        if lists:
            print(f"First list: {lists[0].get('name', 'Unknown')} (ID: {lists[0].get('listId', 'Unknown')})")
        
        # Test 2: Find specific list 2216
        print("\n2. Looking for list 2216...")
        list_details = client.get_list_details("2216")
        if list_details:
            print(f"Found list 2216: {list_details.get('name', 'Unknown')}")
            print(f"Description: {list_details.get('description', 'No description')}")
            print(f"Created: {list_details.get('createdAt', 'Unknown')}")
            print(f"Updated: {list_details.get('updatedAt', 'Unknown')}")
        else:
            print("List 2216 not found")
        
        # Test 3: Get list members (if list exists)
        if list_details:
            print("\n3. Getting list members...")
            members_response = client.get_list_members("2216", limit=10)
            members = members_response.get("results", [])
            print(f"Found {len(members)} members (showing first 10)")
            
            if members:
                print("Sample members:")
                for i, member in enumerate(members[:5]):
                    props = member.get("properties", {})
                    print(f"  {i+1}. {props.get('firstname', '')} {props.get('lastname', '')} ({props.get('email', 'No email')})")
        
        print("\n✅ Lists API test completed!")
        
    except Exception as e:
        print(f"❌ Error testing Lists API: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_lists_api()
