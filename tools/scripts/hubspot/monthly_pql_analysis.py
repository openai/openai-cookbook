#!/usr/bin/env python3
"""
Monthly PQL Analysis - Automated Reporting
==========================================

Standardized monthly analysis of PQL conversion rates using:
- Metric: PQL Rate = PQLs / All Contacts Created in Month
- Data Source: HubSpot CRM via API
- PQL Definition: contact property 'activo' = true

Usage:
    # Current month-to-date
    python monthly_pql_analysis.py
    
    # Specific month
    python monthly_pql_analysis.py --month 2025-08
    
    # Date range
    python monthly_pql_analysis.py --start-date 2025-08-01 --end-date 2025-08-31
    
    # Multi-month comparison 
    python monthly_pql_analysis.py --months 2025-05,2025-06,2025-07,2025-08

Author: Data Analytics Team - Colppy
"""

import os
import sys
import json
import pandas as pd
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Import PQL analysis module from same directory
import deal_focused_pql_analysis as pql_module

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Monthly PQL Analysis')
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--month', help='Month in YYYY-MM format (e.g., 2025-08)')
    group.add_argument('--start-date', help='Start date YYYY-MM-DD')
    group.add_argument('--months', help='Comma-separated months for comparison (e.g., 2025-05,2025-06,2025-07)')
    
    parser.add_argument('--end-date', help='End date YYYY-MM-DD (use with --start-date)')
    parser.add_argument('--output-dir', default='tools/outputs', help='Output directory')
    parser.add_argument('--format', choices=['json', 'csv', 'both'], default='both', 
                       help='Output format')
    
    return parser.parse_args()

def get_month_dates(month_str):
    """Convert YYYY-MM to start/end dates"""
    year, month = map(int, month_str.split('-'))
    start_date = datetime(year, month, 1)
    
    # Get last day of month
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def get_current_month_to_date():
    """Get current month start to today"""
    today = datetime.now()
    start_date = datetime(today.year, today.month, 1)
    return start_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')

def analyze_month(month_str):
    """Analyze a single month and return metrics"""
    start_date, end_date = get_month_dates(month_str)
    
    print(f"\n📊 ANALYZING {month_str.upper()}")
    print(f"📅 Period: {start_date} to {end_date}")
    
    # Fetch contacts using existing module
    contacts = pql_module.fetch_contacts_with_pql(start_date, end_date)
    
    if not contacts:
        return {
            'month': month_str,
            'start_date': start_date,
            'end_date': end_date,
            'total_contacts': 0,
            'pql_contacts': 0,
            'pql_rate': 0.0,
            'error': 'No contacts found'
        }
    
    # Calculate metrics
    total_contacts = len(contacts)
    pql_contacts = sum(1 for c in contacts if c.get('is_pql', False))
    pql_rate = (pql_contacts / total_contacts * 100) if total_contacts > 0 else 0.0
    
    # Additional breakdown
    leads_current = sum(1 for c in contacts if c.get('lifecyclestage') == 'lead')
    customers_current = sum(1 for c in contacts if c.get('lifecyclestage') == 'customer')
    
    result = {
        'month': month_str,
        'start_date': start_date,
        'end_date': end_date,
        'total_contacts': total_contacts,
        'pql_contacts': pql_contacts,
        'pql_rate': round(pql_rate, 2),
        'leads_current_stage': leads_current,
        'customers_current_stage': customers_current,
        'analysis_timestamp': datetime.now().isoformat()
    }
    
    print(f"✅ Results: {total_contacts:,} contacts, {pql_contacts} PQLs ({pql_rate:.2f}%)")
    
    return result

def calculate_mom_deltas(results_list):
    """Calculate month-over-month deltas"""
    if len(results_list) < 2:
        return results_list
    
    enhanced_results = []
    
    for i, result in enumerate(results_list):
        enhanced = result.copy()
        
        if i > 0:
            prev = results_list[i-1]
            enhanced['mom_delta_contacts'] = result['total_contacts'] - prev['total_contacts']
            enhanced['mom_delta_pql_rate'] = round(result['pql_rate'] - prev['pql_rate'], 2)
            enhanced['mom_delta_pql_count'] = result['pql_contacts'] - prev['pql_contacts']
        else:
            enhanced['mom_delta_contacts'] = None
            enhanced['mom_delta_pql_rate'] = None
            enhanced['mom_delta_pql_count'] = None
        
        enhanced_results.append(enhanced)
    
    return enhanced_results

def save_results(results, output_dir, format_type):
    """Save results to file(s)"""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Determine filename based on analysis type
    if len(results) == 1:
        month = results[0]['month'].replace('-', '')
        base_name = f"monthly_pql_analysis_{month}_{timestamp}"
    else:
        first_month = results[0]['month'].replace('-', '')
        last_month = results[-1]['month'].replace('-', '')
        base_name = f"monthly_pql_comparison_{first_month}_{last_month}_{timestamp}"
    
    files_created = []
    
    # Save JSON
    if format_type in ['json', 'both']:
        json_file = os.path.join(output_dir, f"{base_name}.json")
        
        output_data = {
            'analysis_type': 'Monthly PQL Analysis',
            'metric_definition': 'PQL Rate = PQLs / All Contacts Created in Month',
            'generated_at': datetime.now().isoformat(),
            'results': results
        }
        
        with open(json_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        files_created.append(json_file)
        print(f"💾 Saved JSON: {json_file}")
    
    # Save CSV
    if format_type in ['csv', 'both']:
        csv_file = os.path.join(output_dir, f"{base_name}.csv")
        
        df = pd.DataFrame(results)
        df.to_csv(csv_file, index=False)
        files_created.append(csv_file)
        print(f"💾 Saved CSV: {csv_file}")
    
    return files_created

def print_summary_table(results):
    """Print formatted summary table"""
    print(f"\n{'='*80}")
    print("MONTHLY PQL ANALYSIS SUMMARY")
    print(f"{'='*80}")
    print("Metric: PQL Rate = PQLs / All Contacts Created in Month")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")
    
    # Header
    headers = ['Month', 'Total Contacts', 'PQLs', 'PQL Rate', 'MoM Δ Contacts', 'MoM Δ Rate (pp)']
    print(f"{'Month':<10} {'Contacts':<12} {'PQLs':<6} {'Rate':<8} {'Δ Contacts':<12} {'Δ Rate (pp)':<12}")
    print("-" * 80)
    
    # Data rows
    for result in results:
        month = result['month']
        contacts = f"{result['total_contacts']:,}"
        pqls = str(result['pql_contacts'])
        rate = f"{result['pql_rate']:.2f}%"
        
        delta_contacts = result.get('mom_delta_contacts')
        delta_rate = result.get('mom_delta_pql_rate')
        
        delta_contacts_str = f"{delta_contacts:+,}" if delta_contacts is not None else "-"
        delta_rate_str = f"{delta_rate:+.2f}" if delta_rate is not None else "-"
        
        print(f"{month:<10} {contacts:<12} {pqls:<6} {rate:<8} {delta_contacts_str:<12} {delta_rate_str:<12}")
    
    print("-" * 80)
    
    # Key insights
    if len(results) > 1:
        latest = results[-1]
        prev = results[-2]
        
        print(f"\n🔍 KEY INSIGHTS:")
        
        # Volume trend
        contact_trend = "📈 increasing" if latest['total_contacts'] > prev['total_contacts'] else "📉 decreasing"
        print(f"   Contact volume: {contact_trend}")
        
        # PQL rate trend  
        rate_trend = "📈 improving" if latest['pql_rate'] > prev['pql_rate'] else "📉 declining"
        print(f"   PQL conversion: {rate_trend}")
        
        # Performance vs best month
        best_month = max(results, key=lambda x: x['pql_rate'])
        if best_month['month'] != latest['month']:
            gap = latest['pql_rate'] - best_month['pql_rate']
            print(f"   vs Best month ({best_month['month']}): {gap:+.2f}pp gap")

def main():
    """Main execution function"""
    args = parse_arguments()
    
    print("🎯 MONTHLY PQL ANALYSIS")
    print("=" * 60)
    print("Standardized metric: PQL Rate = PQLs / All Contacts Created in Month")
    print("=" * 60)
    
    # Determine what to analyze
    if args.months:
        # Multi-month comparison
        months = [m.strip() for m in args.months.split(',')]
        results = []
        
        for month in months:
            try:
                result = analyze_month(month)
                results.append(result)
            except Exception as e:
                print(f"❌ Error analyzing {month}: {e}")
                continue
        
        # Calculate MoM deltas
        results = calculate_mom_deltas(results)
        
    elif args.month:
        # Single month
        results = [analyze_month(args.month)]
        
    elif args.start_date and args.end_date:
        # Custom date range
        print(f"\n📊 CUSTOM DATE RANGE ANALYSIS")
        print(f"📅 Period: {args.start_date} to {args.end_date}")
        
        contacts = pql_module.fetch_contacts_with_pql(args.start_date, args.end_date)
        
        if contacts:
            total_contacts = len(contacts)
            pql_contacts = sum(1 for c in contacts if c.get('is_pql', False))
            pql_rate = (pql_contacts / total_contacts * 100) if total_contacts > 0 else 0.0
            
            results = [{
                'month': f"{args.start_date}_to_{args.end_date}",
                'start_date': args.start_date,
                'end_date': args.end_date,
                'total_contacts': total_contacts,
                'pql_contacts': pql_contacts,
                'pql_rate': round(pql_rate, 2),
                'analysis_timestamp': datetime.now().isoformat()
            }]
        else:
            results = []
            
    else:
        # Default: current month to date
        start_date, end_date = get_current_month_to_date()
        current_month = datetime.now().strftime('%Y-%m')
        
        print(f"\n📊 CURRENT MONTH-TO-DATE ANALYSIS")
        print(f"📅 Period: {start_date} to {end_date}")
        
        contacts = pql_module.fetch_contacts_with_pql(start_date, end_date)
        
        if contacts:
            total_contacts = len(contacts)
            pql_contacts = sum(1 for c in contacts if c.get('is_pql', False))
            pql_rate = (pql_contacts / total_contacts * 100) if total_contacts > 0 else 0.0
            
            results = [{
                'month': f"{current_month} (MTD)",
                'start_date': start_date,
                'end_date': end_date,
                'total_contacts': total_contacts,
                'pql_contacts': pql_contacts,
                'pql_rate': round(pql_rate, 2),
                'analysis_timestamp': datetime.now().isoformat()
            }]
        else:
            results = []
    
    if not results:
        print("❌ No data found for analysis")
        return
    
    # Display results
    print_summary_table(results)
    
    # Save results
    files_created = save_results(results, args.output_dir, args.format)
    
    print(f"\n✅ ANALYSIS COMPLETED")
    print(f"📁 Files saved: {len(files_created)}")
    for file_path in files_created:
        print(f"   - {file_path}")

if __name__ == "__main__":
    main()
