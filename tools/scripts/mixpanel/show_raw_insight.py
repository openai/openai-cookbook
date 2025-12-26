#!/usr/bin/env python3
"""
Show the raw, unprocessed JSON output from a Mixpanel Insight report API call.
"""

import os
import sys
import json
from pathlib import Path

# Add parent directory to path to import mixpanel_api
sys.path.insert(0, str(Path(__file__).parent))

from mixpanel_api import MixpanelAPI

def show_raw_insight(bookmark_id: str, workspace_id: str = None):
    """Fetch and display raw insight report data."""
    # Load credentials from .env
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent.parent / '.env'
    load_dotenv(env_path)
    
    username = os.getenv("MIXPANEL_USERNAME")
    password = os.getenv("MIXPANEL_PASSWORD")
    project_id = os.getenv("MIXPANEL_PROJECT_ID")
    
    if not username or not password:
        print("❌ Error: MIXPANEL_USERNAME and MIXPANEL_PASSWORD must be set in .env file")
        sys.exit(1)
    
    if not project_id:
        print("⚠️  Warning: MIXPANEL_PROJECT_ID not set, using default")
    
    mixpanel = MixpanelAPI(username, password, project_id)
    
    print(f"📊 Fetching raw Insight report data (bookmark: {bookmark_id})...")
    print("=" * 80)
    
    # Make the API call directly to get raw response
    import requests
    from requests.auth import HTTPBasicAuth
    
    url = f"{mixpanel.BASE_URL}/query/insights"
    params = {
        'project_id': mixpanel.project_id,
        'bookmark_id': bookmark_id
    }
    if workspace_id:
        params['workspace_id'] = workspace_id
    
    try:
        response = requests.get(
            url,
            params=params,
            auth=HTTPBasicAuth(username, password),
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print("=" * 80)
        print()
        
        if response.status_code == 200:
            data = response.json()
            
            # Save raw JSON to file
            raw_json_file = f"insight_report_{bookmark_id}_raw.json"
            with open(raw_json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 Raw JSON saved to: {raw_json_file}")
            print()
            
            print("✅ Raw JSON Response:")
            print("=" * 80)
            print(json.dumps(data, indent=2, ensure_ascii=False))
            print("=" * 80)
            print()
            print(f"📊 Response Summary:")
            print(f"  Type: {type(data).__name__}")
            if isinstance(data, dict):
                print(f"  Top-level keys: {list(data.keys())}")
                for key in data.keys():
                    if isinstance(data[key], (dict, list)):
                        if isinstance(data[key], list):
                            print(f"    {key}: list with {len(data[key])} items")
                            if len(data[key]) > 0:
                                print(f"      First item type: {type(data[key][0]).__name__}")
                        else:
                            print(f"    {key}: dict with {len(data[key])} keys: {list(data[key].keys())[:5]}")
                    else:
                        val = data[key]
                        val_str = str(val)
                        if len(val_str) > 100:
                            val_str = val_str[:100] + "..."
                        print(f"    {key}: {type(data[key]).__name__} = {val_str}")
        else:
            print(f"❌ Error {response.status_code}:")
            print(response.text)
            print()
            print("💡 Note: If you're hitting rate limits, wait a bit and try again.")
            print("   The raw JSON structure will be saved when the API call succeeds.")
            
    except Exception as e:
        print(f"❌ Error fetching insight report: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python show_raw_insight.py <bookmark_id> [workspace_id]")
        print()
        print("Example:")
        print("  python show_raw_insight.py 72369475")
        sys.exit(1)
    
    bookmark_id = sys.argv[1]
    workspace_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    show_raw_insight(bookmark_id, workspace_id)

