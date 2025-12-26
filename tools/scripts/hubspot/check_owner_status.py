#!/usr/bin/env python3
"""
Check HubSpot Owner Status
==========================
Checks which owners in the analysis are active or inactive.
"""

import sys
import os
import pandas as pd
import argparse
from collections import defaultdict

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from owner_utils import get_owner_name_and_status

def check_owners_from_csv(csv_file):
    """Check owner status from contacts CSV file"""
    print(f"📥 Reading contacts from: {csv_file}")
    df = pd.read_csv(csv_file)
    
    # Get unique owner IDs - convert to int to avoid float issues
    owner_ids = df['owner_id'].dropna().unique()
    owner_ids = [int(float(str(oid))) for oid in owner_ids if pd.notna(oid)]
    
    print(f"\n🔍 Checking status for {len(owner_ids)} unique owners...\n")
    
    owner_status = {}
    for owner_id in owner_ids:
        owner_id_str = str(owner_id)
        name, status = get_owner_name_and_status(owner_id_str)
        owner_status[owner_id_str] = {
            'name': name,
            'is_active': status,
            'status': '✅ ACTIVE' if status else '❌ INACTIVE' if status is False else '⚠️ UNKNOWN'
        }
    
    # Count contacts per owner - convert keys to int for matching
    owner_counts_raw = df.groupby('owner_id').size().to_dict()
    owner_counts = {}
    for k, v in owner_counts_raw.items():
        if pd.notna(k):
            key = str(int(float(str(k))))
            owner_counts[key] = v
    
    # Create summary
    active_owners = []
    inactive_owners = []
    unknown_owners = []
    
    for owner_id_str, info in owner_status.items():
        count = owner_counts.get(owner_id_str, 0)
        entry = {
            'owner_id': owner_id_str,
            'name': info['name'],
            'contact_count': count,
            'status': info['status']
        }
        
        if info['is_active'] is True:
            active_owners.append(entry)
        elif info['is_active'] is False:
            inactive_owners.append(entry)
        else:
            unknown_owners.append(entry)
    
    # Sort by contact count
    active_owners.sort(key=lambda x: x['contact_count'], reverse=True)
    inactive_owners.sort(key=lambda x: x['contact_count'], reverse=True)
    unknown_owners.sort(key=lambda x: x['contact_count'], reverse=True)
    
    # Print results
    print("=" * 80)
    print("OWNER STATUS SUMMARY")
    print("=" * 80)
    print(f"\n✅ Active Owners: {len(active_owners)}")
    print(f"❌ Inactive Owners: {len(inactive_owners)}")
    print(f"⚠️  Unknown Status: {len(unknown_owners)}")
    
    if active_owners:
        print("\n" + "=" * 80)
        print("✅ ACTIVE OWNERS")
        print("=" * 80)
        print(f"{'Owner ID':<15} | {'Name':<35} | {'Contact Count':<15} | {'Status'}")
        print("-" * 80)
        for owner in active_owners:
            print(f"{owner['owner_id']:<15} | {owner['name']:<35} | {owner['contact_count']:<15} | {owner['status']}")
    
    if inactive_owners:
        print("\n" + "=" * 80)
        print("❌ INACTIVE OWNERS")
        print("=" * 80)
        print(f"{'Owner ID':<15} | {'Name':<35} | {'Contact Count':<15} | {'Status'}")
        print("-" * 80)
        for owner in inactive_owners:
            print(f"{owner['owner_id']:<15} | {owner['name']:<35} | {owner['contact_count']:<15} | {owner['status']}")
    
    if unknown_owners:
        print("\n" + "=" * 80)
        print("⚠️  UNKNOWN STATUS OWNERS")
        print("=" * 80)
        print(f"{'Owner ID':<15} | {'Name':<35} | {'Contact Count':<15} | {'Status'}")
        print("-" * 80)
        for owner in unknown_owners:
            print(f"{owner['owner_id']:<15} | {owner['name']:<35} | {owner['contact_count']:<15} | {owner['status']}")
    
    # Summary statistics
    total_contacts_active = sum(o['contact_count'] for o in active_owners)
    total_contacts_inactive = sum(o['contact_count'] for o in inactive_owners)
    total_contacts_unknown = sum(o['contact_count'] for o in unknown_owners)
    
    print("\n" + "=" * 80)
    print("CONTACT DISTRIBUTION BY OWNER STATUS")
    print("=" * 80)
    print(f"✅ Active Owners: {total_contacts_active:,} contacts ({total_contacts_active/len(df)*100:.1f}%)")
    print(f"❌ Inactive Owners: {total_contacts_inactive:,} contacts ({total_contacts_inactive/len(df)*100:.1f}%)")
    if total_contacts_unknown > 0:
        print(f"⚠️  Unknown Status: {total_contacts_unknown:,} contacts ({total_contacts_unknown/len(df)*100:.1f}%)")
    
    return {
        'active': active_owners,
        'inactive': inactive_owners,
        'unknown': unknown_owners
    }

def main():
    parser = argparse.ArgumentParser(description='Check HubSpot owner status from CSV file')
    parser.add_argument('--contacts-file',
                       default='tools/outputs/high_score_contacts_2025_12_01_2025_12_20.csv',
                       help='Path to contacts CSV file')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.contacts_file):
        print(f"❌ Error: File not found: {args.contacts_file}")
        sys.exit(1)
    
    check_owners_from_csv(args.contacts_file)

if __name__ == '__main__':
    main()

