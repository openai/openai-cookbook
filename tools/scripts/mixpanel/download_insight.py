#!/usr/bin/env python3
"""
Simple script to download Mixpanel Insight Report to CSV

Usage:
    python download_insight.py --bookmark-id 123456 --output report.csv
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()

sys.path.insert(0, str(script_dir))
from mixpanel_api import MixpanelAPI

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Download Mixpanel Insight Report to CSV')
    parser.add_argument('--bookmark-id', '-b', required=True, help='Bookmark ID from report URL')
    parser.add_argument('--workspace-id', '-w', help='Workspace ID (optional)')
    parser.add_argument('--output', '-o', help='Output CSV file (default: auto-generated)')
    
    args = parser.parse_args()
    
    # Initialize API
    mixpanel = MixpanelAPI()
    
    if not mixpanel.auth[0] or not mixpanel.auth[1]:
        print("❌ Error: Mixpanel credentials not found!")
        sys.exit(1)
    
    try:
        print(f"📊 Downloading insight report (bookmark: {args.bookmark_id})...")
        output_file = mixpanel.export_insight_report(
            bookmark_id=args.bookmark_id,
            workspace_id=args.workspace_id,
            output_file=args.output
        )
        print(f"✅ Report downloaded to: {output_file}")
        print(f"📁 Full path: {Path(output_file).absolute()}")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n💡 To get the bookmark_id:")
        print("   1. Open the report in Mixpanel")
        print("   2. Look at the URL for 'report-BOOKMARK_ID'")
        print("   3. Use that number as --bookmark-id")
        sys.exit(1)

if __name__ == "__main__":
    main()






