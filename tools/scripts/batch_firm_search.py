#!/usr/bin/env python3
"""
Batch search script for multiple firms
Can read from a file or accept a list of firms
"""

import sys
import argparse
import csv
import json
from datetime import datetime
from search_firm_cuit import FirmCUITSearcher


def read_firms_from_file(filename):
    """
    Read firm names from a file (one per line or CSV)
    
    Args:
        filename: Path to the file
        
    Returns:
        List of firm names
    """
    firms = []
    
    try:
        # Try to detect file type
        if filename.endswith('.csv'):
            with open(filename, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                # Try common column names
                for row in reader:
                    if 'name' in row:
                        firms.append(row['name'])
                    elif 'firm' in row:
                        firms.append(row['firm'])
                    elif 'company' in row:
                        firms.append(row['company'])
                    else:
                        # Just take the first column
                        firms.append(list(row.values())[0])
        else:
            # Plain text file, one firm per line
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):  # Skip empty lines and comments
                        firms.append(line)
    
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        sys.exit(1)
    
    return firms


def batch_search_firms(firms, method="playwright", max_variations=5):
    """
    Search for multiple firms and compile results
    
    Args:
        firms: List of firm names
        method: Scraping method
        max_variations: Max variations per firm
        
    Returns:
        Dictionary with all results
    """
    searcher = FirmCUITSearcher(method=method, headless=True)
    all_results = {}
    summary = {
        'total_firms': len(firms),
        'firms_with_results': 0,
        'firms_without_results': 0,
        'total_cuits_found': 0,
        'firms_searched': []
    }
    
    print(f"Starting batch search for {len(firms)} firms...")
    print("=" * 70)
    
    for i, firm in enumerate(firms, 1):
        print(f"\n[{i}/{len(firms)}] Searching: {firm}")
        
        # Search for the firm
        results = searcher.search_firm(firm, max_variations=max_variations)
        
        if results:
            all_results[firm] = results
            summary['firms_with_results'] += 1
            summary['total_cuits_found'] += len(results)
        else:
            summary['firms_without_results'] += 1
        
        summary['firms_searched'].append({
            'name': firm,
            'cuits_found': len(results) if results else 0
        })
        
        # Clear for next search
        searcher.all_results = []
        searcher.unique_cuits = set()
    
    return all_results, summary


def export_batch_results(all_results, summary, output_prefix="batch_search"):
    """Export batch search results to files"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create summary report
    summary_file = f"outputs/{output_prefix}_summary_{timestamp}.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("BATCH CUIT SEARCH SUMMARY\n")
        f.write("=" * 70 + "\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total firms searched: {summary['total_firms']}\n")
        f.write(f"Firms with results: {summary['firms_with_results']}\n")
        f.write(f"Firms without results: {summary['firms_without_results']}\n")
        f.write(f"Total CUITs found: {summary['total_cuits_found']}\n")
        f.write("\nDetailed Results:\n")
        f.write("-" * 70 + "\n")
        
        for firm_info in summary['firms_searched']:
            f.write(f"\n{firm_info['name']}: {firm_info['cuits_found']} CUITs found\n")
            
            # Add the actual CUITs if found
            if firm_info['name'] in all_results:
                for result in all_results[firm_info['name']]:
                    f.write(f"  - {result.cuit}: {result.name}\n")
    
    # Create CSV with all results
    csv_file = f"outputs/{output_prefix}_all_results_{timestamp}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Search Query', 'CUIT', 'Name Found', 'Type', 'Status'])
        
        for firm_name, results in all_results.items():
            for result in results:
                cuit_type = "Company" if result.cuit[:2] in ['30', '33'] else "Individual"
                writer.writerow([
                    firm_name,
                    result.cuit,
                    result.name,
                    cuit_type,
                    result.estado
                ])
    
    # Create JSON with complete data
    json_file = f"outputs/{output_prefix}_complete_{timestamp}.json"
    json_data = {
        'metadata': {
            'timestamp': timestamp,
            'summary': summary
        },
        'results': {}
    }
    
    for firm_name, results in all_results.items():
        json_data['results'][firm_name] = [
            {
                'cuit': r.cuit,
                'name': r.name,
                'tipo_persona': r.tipo_persona,
                'estado': r.estado,
                'search_url': r.search_url
            }
            for r in results
        ]
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Batch results exported to:")
    print(f"   - {summary_file}")
    print(f"   - {csv_file}")
    print(f"   - {json_file}")


def main():
    """Main function for batch search"""
    
    parser = argparse.ArgumentParser(
        description='Batch search for CUIT information of multiple firms',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search firms from a file
  python batch_firm_search.py --file firms.txt
  python batch_firm_search.py --file accounting_firms.csv
  
  # Search specific firms
  python batch_firm_search.py --firms "PwC Argentina" "KPMG" "Deloitte"
  
  # Custom settings
  python batch_firm_search.py --file firms.txt --method selenium --variations 3
        """
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--file', '-f',
                            help='File containing firm names (one per line or CSV)')
    input_group.add_argument('--firms', '-l',
                            nargs='+',
                            help='List of firm names to search')
    
    parser.add_argument('--method', '-m',
                       choices=['requests', 'selenium', 'playwright'],
                       default='playwright',
                       help='Scraping method to use (default: playwright)')
    
    parser.add_argument('--variations', '-v',
                       type=int,
                       default=5,
                       help='Maximum variations per firm (default: 5)')
    
    parser.add_argument('--output', '-o',
                       default='batch_search',
                       help='Output filename prefix (default: batch_search)')
    
    args = parser.parse_args()
    
    # Get list of firms
    if args.file:
        firms = read_firms_from_file(args.file)
        if not firms:
            print("No firms found in file")
            sys.exit(1)
    else:
        firms = args.firms
    
    # Remove duplicates while preserving order
    seen = set()
    unique_firms = []
    for firm in firms:
        if firm not in seen:
            seen.add(firm)
            unique_firms.append(firm)
    
    print(f"Found {len(unique_firms)} unique firms to search")
    
    # Perform batch search
    all_results, summary = batch_search_firms(
        unique_firms,
        method=args.method,
        max_variations=args.variations
    )
    
    # Display final summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Total firms searched: {summary['total_firms']}")
    print(f"Firms with results: {summary['firms_with_results']}")
    print(f"Firms without results: {summary['firms_without_results']}")
    print(f"Total CUITs found: {summary['total_cuits_found']}")
    
    # Export results
    if all_results:
        export_batch_results(all_results, summary, args.output)
    else:
        print("\nNo results found for any firm")


if __name__ == "__main__":
    main()