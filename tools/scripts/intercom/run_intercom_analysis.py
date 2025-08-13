#!/usr/bin/env python3
"""
Intercom Analytics Runner Script

This script provides a simplified interface to run the intercom_analytics.py
module with commonly used options.

Usage:
  python run_intercom_analysis.py --last-month
  python run_intercom_analysis.py --date-range 2023-01-01 2023-01-31
  python run_intercom_analysis.py --csv-file recent-conversations.csv
"""

import os
import sys
import argparse
import warnings
from datetime import datetime, timedelta
from intercom_analytics import IntercomAnalytics, INTERCOM_ACCESS_TOKEN

# Suppress the urllib3 OpenSSL warnings
warnings.filterwarnings('ignore', message='.*OpenSSL.*LibreSSL.*')

def parse_date(date_str):
    """Parse date string in YYYY-MM-DD format"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        print(f"Error: Invalid date format '{date_str}'. Expected YYYY-MM-DD.")
        sys.exit(1)

def get_date_range_for_last_month():
    """Get date range for the last month"""
    today = datetime.today()
    first_of_this_month = today.replace(day=1)
    last_of_previous_month = first_of_this_month - timedelta(days=1)
    first_of_previous_month = last_of_previous_month.replace(day=1)
    
    start_date = first_of_previous_month.strftime('%Y-%m-%d')
    end_date = last_of_previous_month.strftime('%Y-%m-%d')
    
    return start_date, end_date

def main():
    """Main function to parse arguments and run the analysis"""
    parser = argparse.ArgumentParser(description='Run Intercom Analytics with common options')
    
    # Date range options
    date_group = parser.add_argument_group('Date Range Options')
    date_group.add_argument('--last-month', action='store_true', 
                           help='Analyze conversations from the last month')
    date_group.add_argument('--date-range', nargs=2, metavar=('START_DATE', 'END_DATE'),
                           help='Specify a date range in YYYY-MM-DD format')
    date_group.add_argument('--days', type=int, 
                           help='Analyze the last N days')
    
    # CSV file option (alternative to API)
    parser.add_argument('--csv-file', type=str,
                       help='Use a local CSV file instead of the Intercom API')
    
    # Output options
    parser.add_argument('--output-dir', type=str, default='intercom_reports',
                       help='Directory to save reports (default: intercom_reports)')
    parser.add_argument('--export-zip', action='store_true',
                       help='Export all results to a zip file')
    
    # Analysis options
    parser.add_argument('--limit', type=int, default=1000,
                       help='Limit the number of conversations to analyze')
    
    args = parser.parse_args()
    
    # Determine start and end dates
    start_date = None
    end_date = None
    
    if args.last_month:
        start_date, end_date = get_date_range_for_last_month()
        print(f"Analyzing conversations from last month: {start_date} to {end_date}")
    
    elif args.date_range:
        start_date = args.date_range[0]
        end_date = args.date_range[1]
        print(f"Analyzing conversations from {start_date} to {end_date}")
    
    elif args.days:
        end_date = datetime.today().strftime('%Y-%m-%d')
        start_date = (datetime.today() - timedelta(days=args.days)).strftime('%Y-%m-%d')
        print(f"Analyzing conversations from the last {args.days} days: {start_date} to {end_date}")
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    try:
        # Create analytics instance
        analytics = IntercomAnalytics(INTERCOM_ACCESS_TOKEN, output_dir=args.output_dir)
        
        # Run the analysis
        print("Starting Intercom Analytics...")
        results = analytics.run_full_analysis(start_date, end_date, limit=args.limit)
        
        # Export to zip if requested
        if args.export_zip:
            zip_path = analytics.export_results_to_zip()
            print(f"Results exported to {zip_path}")
        
        print(f"Analysis completed successfully! Reports saved to {args.output_dir}/")
        
    except Exception as e:
        print(f"Error running analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 