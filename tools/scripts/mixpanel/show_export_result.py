#!/usr/bin/env python3
"""
Show the raw JSON result from export_insight_report before CSV conversion.
"""

import os
import sys
import json
from pathlib import Path

# Add parent directory to path to import mixpanel_api
sys.path.insert(0, str(Path(__file__).parent))

from mixpanel_api import MixpanelAPI
from dotenv import load_dotenv

def show_export_result(bookmark_id: str, workspace_id: str = None):
    """Call export_insight_report and show the raw JSON before CSV conversion."""
    # Load credentials from .env
    env_path = Path(__file__).parent.parent.parent.parent / '.env'
    load_dotenv(env_path)
    
    username = os.getenv("MIXPANEL_USERNAME")
    password = os.getenv("MIXPANEL_PASSWORD")
    project_id = os.getenv("MIXPANEL_PROJECT_ID")
    
    if not username or not password:
        print("❌ Error: MIXPANEL_USERNAME and MIXPANEL_PASSWORD must be set in .env file")
        sys.exit(1)
    
    if not project_id:
        print("⚠️  Warning: MIXPANEL_PROJECT_ID not set")
        sys.exit(1)
    
    mixpanel = MixpanelAPI(username, password, project_id)
    
    print(f"📊 Calling export_insight_report for bookmark: {bookmark_id}")
    print("=" * 80)
    
    # We need to intercept the API call to get the raw JSON
    # Let's modify the approach - call the API directly like export_insight_report does
    import requests
    
    workspace_id = workspace_id or os.getenv("MIXPANEL_WORKSPACE_ID")
    
    url = f"{mixpanel.BASE_URL}/query/insights"
    params = {
        'project_id': mixpanel.project_id,
        'bookmark_id': bookmark_id
    }
    if workspace_id:
        params['workspace_id'] = workspace_id
    
    try:
        print(f"🔗 Making GET request to: {url}")
        print(f"📋 Parameters: {params}")
        print("=" * 80)
        print()
        
        response = requests.get(
            url,
            params=params,
            auth=mixpanel.auth,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"Status Code: {response.status_code}")
        print("=" * 80)
        print()
        
        if response.status_code == 200:
            raw_json = response.json()
            
            # Save raw JSON to file
            raw_json_file = f"insight_report_{bookmark_id}_raw.json"
            with open(raw_json_file, 'w', encoding='utf-8') as f:
                json.dump(raw_json, f, indent=2, ensure_ascii=False)
            print(f"💾 Raw JSON saved to: {raw_json_file}")
            print()
            
            print("✅ Raw JSON Response from export_insight_report query:")
            print("=" * 80)
            print(json.dumps(raw_json, indent=2, ensure_ascii=False))
            print("=" * 80)
            print()
            
            print(f"📊 Response Summary:")
            print(f"  Type: {type(raw_json).__name__}")
            if isinstance(raw_json, dict):
                print(f"  Top-level keys: {list(raw_json.keys())}")
                print()
                for key in raw_json.keys():
                    val = raw_json[key]
                    if isinstance(val, dict):
                        print(f"  {key}:")
                        print(f"    Type: dict with {len(val)} keys")
                        if len(val) > 0:
                            sample_keys = list(val.keys())[:5]
                            print(f"    Sample keys: {sample_keys}")
                            if len(val) > 5:
                                print(f"    ... and {len(val) - 5} more keys")
                    elif isinstance(val, list):
                        print(f"  {key}:")
                        print(f"    Type: list with {len(val)} items")
                        if len(val) > 0:
                            print(f"    First item type: {type(val[0]).__name__}")
                            if isinstance(val[0], dict):
                                print(f"    First item keys: {list(val[0].keys())[:5]}")
                    else:
                        val_str = str(val)
                        if len(val_str) > 100:
                            val_str = val_str[:100] + "..."
                        print(f"  {key}: {type(val).__name__} = {val_str}")
            
            print()
            print("=" * 80)
            print("✅ This is the raw, unprocessed JSON that export_insight_report receives")
            print("   before it gets converted to CSV format.")
            
        else:
            print(f"❌ Error {response.status_code}:")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python show_export_result.py <bookmark_id> [workspace_id]")
        print()
        print("Example:")
        print("  python show_export_result.py 72369475")
        sys.exit(1)
    
    bookmark_id = sys.argv[1]
    workspace_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    show_export_result(bookmark_id, workspace_id)






