#!/usr/bin/env python3
"""
Test export_insight_report and show the raw JSON result.
"""

import os
import sys
import json
from pathlib import Path

# Add parent directory to path to import mixpanel_api
sys.path.insert(0, str(Path(__file__).parent))

from mixpanel_api import MixpanelAPI
from dotenv import load_dotenv

def test_export_raw(bookmark_id: str):
    """Test export_insight_report with return_raw_json=True to see the raw result."""
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
    
    print(f"📊 Testing export_insight_report with return_raw_json=True")
    print(f"   Bookmark ID: {bookmark_id}")
    print("=" * 80)
    print()
    
    try:
        # Call export_insight_report with return_raw_json=True
        raw_result = mixpanel.export_insight_report(
            bookmark_id=bookmark_id,
            return_raw_json=True
        )
        
        print()
        print("=" * 80)
        print("✅ Raw JSON Result from export_insight_report:")
        print("=" * 80)
        print(json.dumps(raw_result, indent=2, ensure_ascii=False))
        print("=" * 80)
        print()
        
        print(f"📊 Result Summary:")
        print(f"  Type: {type(raw_result).__name__}")
        if isinstance(raw_result, dict):
            print(f"  Top-level keys: {list(raw_result.keys())}")
            print()
            for key in raw_result.keys():
                val = raw_result[key]
                if isinstance(val, dict):
                    print(f"  {key}:")
                    print(f"    Type: dict with {len(val)} keys")
                    if len(val) > 0:
                        sample_keys = list(val.keys())[:5]
                        print(f"    Sample keys: {sample_keys}")
                        if len(val) > 5:
                            print(f"    ... and {len(val) - 5} more keys")
                        # If it's the series object, show more detail
                        if key == 'series' and len(val) > 0:
                            first_metric = list(val.keys())[0]
                            first_metric_data = val[first_metric]
                            if isinstance(first_metric_data, dict):
                                print(f"    First metric '{first_metric}' has {len(first_metric_data)} date keys")
                                if '$overall' in first_metric_data:
                                    print(f"    Overall value: {first_metric_data['$overall']}")
                elif isinstance(val, list):
                    print(f"  {key}:")
                    print(f"    Type: list with {len(val)} items")
                else:
                    val_str = str(val)
                    if len(val_str) > 100:
                        val_str = val_str[:100] + "..."
                    print(f"  {key}: {type(val).__name__} = {val_str}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_export_raw.py <bookmark_id>")
        print()
        print("Example:")
        print("  python test_export_raw.py 72369475")
        sys.exit(1)
    
    bookmark_id = sys.argv[1]
    test_export_raw(bookmark_id)

