#!/usr/bin/env python3
"""
Export Mixpanel Insight Report to CSV via API

Usage:
    # Export by bookmark ID
    python export_insight_report.py --bookmark-id 1XEB5C
    
    # Export with custom output file
    python export_insight_report.py --bookmark-id 1XEB5C --output report.csv
    
    # Export from shared link
    python export_insight_report.py --share-link https://mixpanel.com/s/1XEB5C
"""

import sys
import os
import argparse
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

# Add parent directory to path to import mixpanel_api
sys.path.insert(0, str(script_dir))
from mixpanel_api import MixpanelAPI


def extract_bookmark_from_share_link(share_link: str) -> str:
    """
    Extract bookmark ID from Mixpanel share link.
    
    Note: Share tokens (like /s/1XEB5C) are NOT the same as bookmark_id.
    You need to open the report in Mixpanel and get the bookmark_id from the URL:
    https://mixpanel.com/project/PROJECT_ID/view/WORKSPACE_ID/app/boards#id=12345&editor-card-id="report-BOOKMARK_ID"
    
    The bookmark_id is the number after "report-" in the URL.
    """
    # Format: https://mixpanel.com/s/1XEB5C
    # Share tokens need to be resolved - they're not bookmark_ids
    if '/s/' in share_link:
        share_token = share_link.split('/s/')[-1].split('?')[0].split('#')[0].strip()
        print(f"⚠️  Warning: Share token '{share_token}' is not a bookmark_id.")
        print(f"   To get the bookmark_id:")
        print(f"   1. Open the report in Mixpanel: {share_link}")
        print(f"   2. Look at the URL - it will contain 'report-BOOKMARK_ID'")
        print(f"   3. Use that BOOKMARK_ID number instead")
        print(f"   Example URL: .../app/boards#id=12345&editor-card-id=\"report-123456\"")
        print(f"   The bookmark_id would be: 123456")
        raise ValueError(
            f"Share token '{share_token}' cannot be used directly. "
            f"Please open the report in Mixpanel and extract the bookmark_id from the URL."
        )
    
    # If it's a full report URL, try to extract bookmark_id
    if 'report-' in share_link:
        parts = share_link.split('report-')
        if len(parts) > 1:
            bookmark_id = parts[-1].split('"')[0].split('&')[0].split('#')[0].strip()
            return bookmark_id
    
    raise ValueError(f"Could not extract bookmark ID from: {share_link}")


def main():
    parser = argparse.ArgumentParser(
        description='Export Mixpanel Insight Report to CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export by bookmark ID
  python export_insight_report.py --bookmark-id 1XEB5C
  
  # Export from shared link
  python export_insight_report.py --share-link https://mixpanel.com/s/1XEB5C
  
  # Export with custom output file
  python export_insight_report.py --bookmark-id 1XEB5C --output my_report.csv
        """
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--bookmark-id', '-b',
        type=str,
        help='Bookmark ID of the Insight report (extract from report URL: ...report-BOOKMARK_ID)'
    )
    input_group.add_argument(
        '--share-link', '-s',
        type=str,
        help='Full report URL (not share link) containing bookmark_id (e.g., .../app/boards#id=12345&editor-card-id="report-123456")'
    )
    
    # Output options
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output CSV file path (default: auto-generated)'
    )
    parser.add_argument(
        '--workspace-id', '-w',
        type=str,
        help='Workspace ID (defaults to MIXPANEL_WORKSPACE_ID env var)'
    )
    
    args = parser.parse_args()
    
    # Get bookmark ID
    if args.share_link:
        bookmark_id = extract_bookmark_from_share_link(args.share_link)
        print(f"📋 Extracted bookmark ID: {bookmark_id}")
    else:
        bookmark_id = args.bookmark_id
    
    # Initialize Mixpanel API
    try:
        mixpanel = MixpanelAPI()
        
        if not mixpanel.auth[0] or not mixpanel.auth[1]:
            print("❌ Error: Mixpanel credentials not found!", file=sys.stderr)
            print("Make sure MIXPANEL_USERNAME and MIXPANEL_PASSWORD are set in .env", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error initializing Mixpanel API: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Export report
    try:
        print(f"📊 Exporting Insight report (bookmark: {bookmark_id})...")
        output_file = mixpanel.export_insight_report(
            bookmark_id=bookmark_id,
            workspace_id=args.workspace_id,
            output_file=args.output
        )
        print(f"✅ Report exported successfully to: {output_file}")
        return output_file
    except Exception as e:
        print(f"❌ Error exporting report: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

