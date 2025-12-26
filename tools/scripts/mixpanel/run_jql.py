#!/usr/bin/env python3
"""
Simple script to run Mixpanel JQL queries from command line.

Usage:
    # Run JQL query directly
    python run_jql.py --query "function main() { return Events({from_date: '2025-01-01', to_date: '2025-12-08'}).groupBy(['name'], mixpanel.reducer.count()); }"
    
    # Run JQL query from file
    python run_jql.py --file query.jql
    
    # Run with pretty JSON output
    python run_jql.py --query "..." --pretty
    
    # Save results to file
    python run_jql.py --query "..." --output results.json
"""

import sys
import os
import json
import csv
import argparse
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Any

# Load environment variables from .env file in project root
# Find project root (openai-cookbook directory)
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent.parent  # Go up from tools/scripts/mixpanel to openai-cookbook
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    # Fallback: try current directory and parent directories
    load_dotenv()

# Add parent directory to path to import mixpanel_api
sys.path.insert(0, str(script_dir))

from mixpanel_api import MixpanelAPI


def flatten_dict(d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
    """Flatten nested dictionary for CSV export."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Convert lists to comma-separated strings
            items.append((new_key, ', '.join(str(item) for item in v)))
        else:
            items.append((new_key, v))
    return dict(items)


def convert_to_csv(data: List[Dict], flatten: bool = True) -> str:
    """Convert query results to CSV format."""
    if not data:
        return ""
    
    # Flatten nested dictionaries if needed
    if flatten:
        flattened_data = [flatten_dict(item) for item in data]
    else:
        flattened_data = data
    
    # Get all unique keys from all records
    all_keys = set()
    for record in flattened_data:
        all_keys.update(record.keys())
    
    # Sort keys for consistent column order
    fieldnames = sorted(all_keys)
    
    # Create CSV in memory
    import io
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for record in flattened_data:
        # Convert all values to strings, handle None
        clean_record = {
            k: str(v) if v is not None else '' 
            for k, v in record.items()
        }
        writer.writerow(clean_record)
    
    return output.getvalue()


def format_output(data, pretty=False, format_type='json'):
    """Format output data."""
    if format_type == 'csv':
        # Ensure data is a list
        if isinstance(data, list):
            data_list = data
        elif isinstance(data, dict):
            if 'data' in data:
                data_list = data['data'] if isinstance(data['data'], list) else [data['data']]
            else:
                data_list = [data]
        else:
            data_list = [{'result': str(data)}]
        return convert_to_csv(data_list, flatten=True)
    else:  # JSON format
        if pretty:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return json.dumps(data, ensure_ascii=False)


def read_jql_file(file_path):
    """Read JQL query from file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Run Mixpanel JQL queries from command line',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run query directly
  python run_jql.py --query "function main() { return Events({from_date: '2025-01-01', to_date: '2025-12-08'}).groupBy(['name'], mixpanel.reducer.count()); }"
  
  # Run query from file
  python run_jql.py --file my_query.jql
  
  # Export to CSV (comma-separated, spreadsheet-ready)
  python run_jql.py --file my_query.jql --format csv --output results.csv
  
  # Pretty print JSON results
  python run_jql.py --query "..." --pretty
  
  # Save JSON to file
  python run_jql.py --query "..." --output results.json
        """
    )
    
    # Query input options (mutually exclusive)
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument(
        '--query',
        type=str,
        help='JQL query as a string'
    )
    query_group.add_argument(
        '--file', '-f',
        type=str,
        help='Path to file containing JQL query'
    )
    
    # Output options
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Save results to file (format depends on --format option)'
    )
    parser.add_argument(
        '--pretty', '-p',
        action='store_true',
        help='Pretty print JSON output'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['json', 'csv'],
        default='json',
        help='Output format: json or csv (default: json). CSV uses comma separator for spreadsheet compatibility.'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress debug output (only show results)'
    )
    
    # API credentials (optional, defaults to env vars)
    parser.add_argument(
        '--username',
        type=str,
        help='Mixpanel service account username (defaults to MIXPANEL_USERNAME env var)'
    )
    parser.add_argument(
        '--password',
        type=str,
        help='Mixpanel service account password (defaults to MIXPANEL_PASSWORD env var)'
    )
    parser.add_argument(
        '--project-id',
        type=str,
        help='Mixpanel project ID (defaults to MIXPANEL_PROJECT_ID env var)'
    )
    
    args = parser.parse_args()
    
    # Get JQL query
    if args.query:
        jql_script = args.query
    elif args.file:
        jql_script = read_jql_file(args.file)
    else:
        parser.error("Either --query or --file must be provided")
    
    # Initialize Mixpanel API
    try:
        mixpanel = MixpanelAPI(
            service_account_username=args.username,
            service_account_password=args.password,
            project_id=args.project_id
        )
        
        # Check if credentials are actually set
        if not mixpanel.auth[0] or not mixpanel.auth[1]:
            print("❌ Error: Mixpanel credentials not found!", file=sys.stderr)
            print("\nPlease provide credentials using one of these methods:", file=sys.stderr)
            print("1. Add to .env file in project root:", file=sys.stderr)
            print("   MIXPANEL_USERNAME=your_username", file=sys.stderr)
            print("   MIXPANEL_PASSWORD=your_password", file=sys.stderr)
            print("   MIXPANEL_PROJECT_ID=2201475", file=sys.stderr)
            print("\n2. Pass as command-line arguments:", file=sys.stderr)
            print("   --username YOUR_USERNAME --password YOUR_PASSWORD --project-id 2201475", file=sys.stderr)
            sys.exit(1)
            
        if not mixpanel.project_id:
            print("⚠️  Warning: MIXPANEL_PROJECT_ID not set. Using default: 2201475", file=sys.stderr)
            mixpanel.project_id = "2201475"
            
    except Exception as e:
        print(f"Error initializing Mixpanel API: {e}", file=sys.stderr)
        print("\nMake sure MIXPANEL_USERNAME, MIXPANEL_PASSWORD, and MIXPANEL_PROJECT_ID are set", file=sys.stderr)
        sys.exit(1)
    
    # Suppress debug output if quiet mode
    original_stdout = sys.stdout
    if args.quiet:
        import logging
        logging.getLogger().setLevel(logging.ERROR)
        # Temporarily redirect stdout to suppress MixpanelAPI debug prints
        import io
        sys.stdout = io.StringIO()
    
    # Run JQL query
    try:
        if not args.quiet:
            print("Running JQL query...", file=sys.stderr)
            print("-" * 50, file=sys.stderr)
        
        result = mixpanel.run_jql(jql_script)
        
        if args.quiet:
            # Restore stdout
            sys.stdout = original_stdout
        
        # Format output
        output = format_output(result, pretty=args.pretty, format_type=args.format)
        
        # Save to file or print to stdout
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            if not args.quiet:
                file_type = args.format.upper()
                print(f"\n✅ Results saved to: {args.output} ({file_type} format)", file=sys.stderr)
        else:
            print(output)
            
    except Exception as e:
        if args.quiet:
            sys.stdout = original_stdout
        print(f"\nError running JQL query: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

