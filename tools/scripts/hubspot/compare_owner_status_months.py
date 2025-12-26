#!/usr/bin/env python3
"""
Compare Owner Status Across Months
==================================
Compares which owners are active/inactive across October, November, and December MTD.
"""

import sys
import os
import pandas as pd
import argparse
from collections import defaultdict
from datetime import datetime

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from owner_utils import get_owner_name_and_status

def get_contacts_file_for_month(month_str):
    """Get the contacts CSV file path for a given month"""
    # Expected format: high_score_contacts_YYYY_MM_DD_YYYY_MM_DD.csv
    base_dir = "tools/outputs"
    
    if month_str == "october" or month_str == "10":
        # October 1-31, 2025
        return f"{base_dir}/high_score_contacts_2025_10_01_2025_10_31.csv"
    elif month_str == "november" or month_str == "11":
        # November 1-30, 2025
        return f"{base_dir}/high_score_contacts_2025_11_01_2025_11_30.csv"
    elif month_str == "december" or month_str == "12":
        # December 1-20, 2025 (MTD)
        return f"{base_dir}/high_score_contacts_2025_12_01_2025_12_20.csv"
    else:
        return None

def check_owners_from_csv(csv_file, month_name):
    """Check owner status from contacts CSV file"""
    if not os.path.exists(csv_file):
        print(f"⚠️  File not found: {csv_file}")
        return {}
    
    print(f"📥 Reading {month_name} contacts from: {csv_file}")
    df = pd.read_csv(csv_file)
    
    # Get unique owner IDs - convert to int to avoid float issues
    owner_ids = df['owner_id'].dropna().unique()
    owner_ids = [int(float(str(oid))) for oid in owner_ids if pd.notna(oid)]
    
    print(f"   Found {len(owner_ids)} unique owners")
    
    owner_status = {}
    for owner_id in owner_ids:
        owner_id_str = str(owner_id)
        name, status = get_owner_name_and_status(owner_id_str)
        owner_status[owner_id_str] = {
            'name': name,
            'is_active': status,
            'status': '✅ ACTIVE' if status else '❌ INACTIVE' if status is False else '⚠️ UNKNOWN'
        }
    
    # Count contacts per owner
    owner_counts_raw = df.groupby('owner_id').size().to_dict()
    owner_counts = {}
    for k, v in owner_counts_raw.items():
        if pd.notna(k):
            key = str(int(float(str(k))))
            owner_counts[key] = v
    
    # Add contact counts to status
    for owner_id_str in owner_status:
        owner_status[owner_id_str]['contact_count'] = owner_counts.get(owner_id_str, 0)
    
    return owner_status

def compare_months(months=['october', 'november', 'december']):
    """Compare owner status across multiple months"""
    print("=" * 100)
    print("OWNER STATUS COMPARISON ACROSS MONTHS")
    print("=" * 100)
    print()
    
    all_owners = set()
    month_data = {}
    
    # Collect data for each month
    for month in months:
        csv_file = get_contacts_file_for_month(month)
        if csv_file:
            month_data[month] = check_owners_from_csv(csv_file, month.capitalize())
            all_owners.update(month_data[month].keys())
        else:
            print(f"⚠️  Could not determine file for month: {month}")
            month_data[month] = {}
    
    print("\n" + "=" * 100)
    print("COMPARISON RESULTS")
    print("=" * 100)
    
    # Create comparison table
    comparison_data = []
    for owner_id in sorted(all_owners):
        row = {'owner_id': owner_id}
        
        # Get owner name from any month (should be same)
        owner_name = None
        for month in months:
            if owner_id in month_data[month]:
                owner_name = month_data[month][owner_id]['name']
                break
        
        if not owner_name:
            owner_name = f"Unknown ({owner_id})"
        
        row['owner_name'] = owner_name
        
        # Get status and contact count for each month
        for month in months:
            if owner_id in month_data[month]:
                owner_info = month_data[month][owner_id]
                row[f'{month}_status'] = owner_info['status']
                row[f'{month}_active'] = owner_info['is_active']
                row[f'{month}_contacts'] = owner_info['contact_count']
            else:
                row[f'{month}_status'] = 'N/A'
                row[f'{month}_active'] = None
                row[f'{month}_contacts'] = 0
        
        comparison_data.append(row)
    
    # Print comparison table
    print(f"\n{'Owner Name':<35} │ {'Oct Status':<12} │ {'Oct Contacts':<12} │ {'Nov Status':<12} │ {'Nov Contacts':<12} │ {'Dec Status':<12} │ {'Dec Contacts':<12}")
    print("─" * 35 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12)
    
    for row in comparison_data:
        print(f"{row['owner_name']:<35} │ {row.get('october_status', 'N/A'):<12} │ {row.get('october_contacts', 0):<12} │ "
              f"{row.get('november_status', 'N/A'):<12} │ {row.get('november_contacts', 0):<12} │ "
              f"{row.get('december_status', 'N/A'):<12} │ {row.get('december_contacts', 0):<12}")
    
    # Summary statistics
    print("\n" + "=" * 100)
    print("SUMMARY STATISTICS")
    print("=" * 100)
    
    for month in months:
        month_owners = month_data.get(month, {})
        if not month_owners:
            continue
        
        active_count = sum(1 for o in month_owners.values() if o['is_active'] is True)
        inactive_count = sum(1 for o in month_owners.values() if o['is_active'] is False)
        unknown_count = sum(1 for o in month_owners.values() if o['is_active'] is None)
        total_contacts = sum(o['contact_count'] for o in month_owners.values())
        active_contacts = sum(o['contact_count'] for o in month_owners.values() if o['is_active'] is True)
        inactive_contacts = sum(o['contact_count'] for o in month_owners.values() if o['is_active'] is False)
        
        print(f"\n{month.upper()}:")
        print(f"  Total Owners: {len(month_owners)}")
        print(f"    ✅ Active: {active_count}")
        print(f"    ❌ Inactive: {inactive_count}")
        print(f"    ⚠️  Unknown: {unknown_count}")
        print(f"  Total Contacts: {total_contacts:,}")
        print(f"    ✅ Active Owners: {active_contacts:,} contacts ({active_contacts/total_contacts*100:.1f}%)" if total_contacts > 0 else "    ✅ Active Owners: 0 contacts")
        print(f"    ❌ Inactive Owners: {inactive_contacts:,} contacts ({inactive_contacts/total_contacts*100:.1f}%)" if total_contacts > 0 else "    ❌ Inactive Owners: 0 contacts")
    
    # Find status changes
    print("\n" + "=" * 100)
    print("STATUS CHANGES")
    print("=" * 100)
    
    status_changes = []
    for owner_id in all_owners:
        oct_status = month_data.get('october', {}).get(owner_id, {}).get('is_active')
        nov_status = month_data.get('november', {}).get(owner_id, {}).get('is_active')
        dec_status = month_data.get('december', {}).get(owner_id, {}).get('is_active')
        
        owner_name = None
        for month in months:
            if owner_id in month_data[month]:
                owner_name = month_data[month][owner_id]['name']
                break
        
        # Check for changes
        if oct_status != nov_status or nov_status != dec_status:
            status_changes.append({
                'owner_id': owner_id,
                'owner_name': owner_name or f"Unknown ({owner_id})",
                'october': '✅' if oct_status else '❌' if oct_status is False else '⚠️',
                'november': '✅' if nov_status else '❌' if nov_status is False else '⚠️',
                'december': '✅' if dec_status else '❌' if dec_status is False else '⚠️'
            })
    
    if status_changes:
        print(f"\n{'Owner Name':<35} │ {'October':<10} │ {'November':<10} │ {'December':<10}")
        print("─" * 35 + "┼" + "─" * 10 + "┼" + "─" * 10 + "┼" + "─" * 10)
        for change in status_changes:
            print(f"{change['owner_name']:<35} │ {change['october']:<10} │ {change['november']:<10} │ {change['december']:<10}")
    else:
        print("\n✅ No status changes detected across months")
    
    return comparison_data

def main():
    parser = argparse.ArgumentParser(description='Compare owner status across months')
    parser.add_argument('--months', nargs='+', 
                       default=['october', 'november', 'december'],
                       help='Months to compare (default: october november december)')
    
    args = parser.parse_args()
    
    compare_months(args.months)

if __name__ == '__main__':
    main()

