#!/usr/bin/env python3
"""
Analyze Uncontacted Contacts Without Lead Status
================================================
Analyzes how many uncontacted contacts don't have a Lead status field filled in,
and confirms if this means they don't have a Lead object associated.
"""

import sys
import os
import pandas as pd
import argparse
from collections import defaultdict

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dotenv import load_dotenv
load_dotenv()

# Try to use HubSpot API client if available
try:
    from hubspot_api.client import HubSpotClient, HubSpotAPIError
    HUBSPOT_CLIENT_AVAILABLE = True
except ImportError:
    HUBSPOT_CLIENT_AVAILABLE = False

PORTAL_ID = "19877595"
UI_DOMAIN = "app.hubspot.com"

def check_lead_associations(contact_ids):
    """Check if contacts have associated Lead objects"""
    if not HUBSPOT_CLIENT_AVAILABLE:
        return {}
    
    lead_associations = {}
    client = HubSpotClient()
    
    print(f"🔍 Checking Lead object associations for {len(contact_ids)} contacts...")
    
    for i, contact_id in enumerate(contact_ids, 1):
        if i % 10 == 0:
            print(f"   Checking {i}/{len(contact_ids)}...")
        
        try:
            # Check for Lead associations
            result = client.list_associations(
                from_object_type="contacts",
                from_object_id=str(contact_id),
                to_object_type="leads"
            )
            
            has_lead = len(result.get('results', [])) > 0
            lead_associations[contact_id] = has_lead
            
        except Exception as e:
            # If error, assume no lead
            lead_associations[contact_id] = False
    
    return lead_associations

def analyze_uncontacted_lead_status(csv_file):
    """Analyze uncontacted contacts and their lead status"""
    print(f"📥 Reading contacts from: {csv_file}")
    df = pd.read_csv(csv_file)
    
    print(f"   Total contacts: {len(df)}")
    
    # Filter for uncontacted contacts
    uncontacted = df[df['is_contacted'] == False].copy()
    print(f"   Uncontacted contacts: {len(uncontacted)}")
    
    # Check if hs_lead_status column exists
    # If not, we need to fetch it from API
    if 'hs_lead_status' not in df.columns:
        print("\n⚠️  'hs_lead_status' column not found in CSV. Fetching from API...")
        
        if not HUBSPOT_CLIENT_AVAILABLE:
            print("❌ HubSpot API client not available. Cannot fetch lead status.")
            return
        
        client = HubSpotClient()
        lead_statuses = {}
        
        print(f"   Fetching lead status for {len(uncontacted)} uncontacted contacts...")
        for i, (_, contact) in enumerate(uncontacted.iterrows(), 1):
            if i % 20 == 0:
                print(f"   Fetching {i}/{len(uncontacted)}...")
            
            try:
                contact_id = contact['contact_id']
                result = client.get(f"crm/v3/objects/contacts/{contact_id}", {
                    'properties': 'hs_lead_status'
                })
                lead_status = result.get('properties', {}).get('hs_lead_status', '')
                lead_statuses[contact_id] = lead_status if lead_status else None
            except Exception as e:
                lead_statuses[contact_id] = None
        
        uncontacted['hs_lead_status'] = uncontacted['contact_id'].map(lead_statuses)
    else:
        # Use existing column
        print("\n✅ 'hs_lead_status' column found in CSV")
    
    # Analyze lead status
    no_lead_status = uncontacted[uncontacted['hs_lead_status'].isna() | (uncontacted['hs_lead_status'] == '')]
    has_lead_status = uncontacted[uncontacted['hs_lead_status'].notna() & (uncontacted['hs_lead_status'] != '')]
    
    print(f"\n{'='*100}")
    print("ANALYSIS: UNCONTACTED CONTACTS - LEAD STATUS")
    print(f"{'='*100}")
    
    print(f"\n📊 Summary:")
    print(f"   Total uncontacted contacts: {len(uncontacted)}")
    print(f"   Without Lead Status: {len(no_lead_status)} ({len(no_lead_status)/len(uncontacted)*100:.1f}%)")
    print(f"   With Lead Status: {len(has_lead_status)} ({len(has_lead_status)/len(uncontacted)*100:.1f}%)")
    
    # Check Lead object associations for contacts without lead status
    if len(no_lead_status) > 0:
        print(f"\n🔍 Checking if contacts WITHOUT Lead Status have Lead objects associated...")
        sample_ids = no_lead_status['contact_id'].head(50).tolist()  # Sample first 50
        lead_associations = check_lead_associations(sample_ids)
        
        has_lead_object = sum(1 for v in lead_associations.values() if v)
        no_lead_object = len(lead_associations) - has_lead_object
        
        print(f"\n   Sample Analysis (first 50 contacts without Lead Status):")
        print(f"   Contacts with Lead object: {has_lead_object} ({has_lead_object/len(lead_associations)*100:.1f}%)")
        print(f"   Contacts without Lead object: {no_lead_object} ({no_lead_object/len(lead_associations)*100:.1f}%)")
        
        if has_lead_object > 0:
            print(f"\n   ⚠️  WARNING: {has_lead_object} contacts have Lead objects but NO Lead Status field!")
            print(f"      This suggests a data quality issue.")
        
        if no_lead_object > 0:
            print(f"\n   ✅ CONFIRMED: {no_lead_object} contacts have NO Lead Status AND NO Lead object")
            print(f"      This confirms: No Lead Status = No Lead object associated")
    
    # Breakdown by owner
    print(f"\n{'='*100}")
    print("BREAKDOWN BY OWNER")
    print(f"{'='*100}")
    
    owner_breakdown = []
    for owner_id in uncontacted['owner_id'].unique():
        owner_df = uncontacted[uncontacted['owner_id'] == owner_id]
        owner_name = owner_df['owner_name'].iloc[0] if len(owner_df) > 0 else f"Unknown ({owner_id})"
        
        total = len(owner_df)
        without_status = len(owner_df[owner_df['hs_lead_status'].isna() | (owner_df['hs_lead_status'] == '')])
        with_status = total - without_status
        
        owner_breakdown.append({
            'owner_name': owner_name,
            'total_uncontacted': total,
            'without_lead_status': without_status,
            'with_lead_status': with_status,
            'pct_without_status': (without_status / total * 100) if total > 0 else 0
        })
    
    owner_breakdown_df = pd.DataFrame(owner_breakdown).sort_values('total_uncontacted', ascending=False)
    
    print(f"\n{'Owner Name':<35} │ {'Total Uncontacted':<18} │ {'Without Lead Status':<20} │ {'With Lead Status':<18} │ {'% Without Status':<18}")
    print("─" * 35 + "┼" + "─" * 18 + "┼" + "─" * 20 + "┼" + "─" * 18 + "┼" + "─" * 18)
    for _, row in owner_breakdown_df.iterrows():
        print(f"{row['owner_name']:<35} │ {row['total_uncontacted']:<18} │ {row['without_lead_status']:<20} │ {row['with_lead_status']:<18} │ {row['pct_without_status']:<17.1f}%")
    
    # Lead status values breakdown
    if len(has_lead_status) > 0:
        print(f"\n{'='*100}")
        print("LEAD STATUS VALUES (for contacts WITH Lead Status)")
        print(f"{'='*100}")
        
        status_counts = has_lead_status['hs_lead_status'].value_counts()
        print(f"\n{'Lead Status':<40} │ {'Count':<10} │ {'Percentage':<12}")
        print("─" * 40 + "┼" + "─" * 10 + "┼" + "─" * 12)
        for status, count in status_counts.items():
            pct = (count / len(has_lead_status) * 100) if len(has_lead_status) > 0 else 0
            print(f"{str(status):<40} │ {count:<10} │ {pct:<11.1f}%")
    
    return {
        'total_uncontacted': len(uncontacted),
        'without_lead_status': len(no_lead_status),
        'with_lead_status': len(has_lead_status),
        'owner_breakdown': owner_breakdown_df
    }

def compare_months(months=['october', 'november', 'december']):
    """Compare uncontacted contacts without Lead Status across multiple months"""
    month_files = {
        'october': 'tools/outputs/high_score_contacts_2025_10_01_2025_10_31.csv',
        'november': 'tools/outputs/high_score_contacts_2025_11_01_2025_11_30.csv',
        'december': 'tools/outputs/high_score_contacts_2025_12_01_2025_12_20.csv'
    }
    
    print("=" * 100)
    print("COMPARISON: UNCONTACTED CONTACTS WITHOUT LEAD STATUS - MONTH TO MONTH")
    print("=" * 100)
    print()
    
    all_results = {}
    
    for month in months:
        csv_file = month_files.get(month)
        if csv_file and os.path.exists(csv_file):
            print(f"\n{'='*100}")
            print(f"ANALYZING {month.upper()}")
            print(f"{'='*100}")
            result = analyze_uncontacted_lead_status(csv_file)
            all_results[month] = result
        else:
            print(f"\n⚠️  File not found for {month}: {csv_file}")
            all_results[month] = None
    
    # Comparison summary
    print("\n" + "=" * 100)
    print("MONTH-TO-MONTH COMPARISON SUMMARY")
    print("=" * 100)
    
    print(f"\n{'Month':<15} │ {'Total Uncontacted':<18} │ {'Without Lead Status':<20} │ {'With Lead Status':<18} │ {'% Without Status':<18}")
    print("─" * 15 + "┼" + "─" * 18 + "┼" + "─" * 20 + "┼" + "─" * 18 + "┼" + "─" * 18)
    
    for month in months:
        result = all_results.get(month)
        if result:
            pct = (result['without_lead_status'] / result['total_uncontacted'] * 100) if result['total_uncontacted'] > 0 else 0
            print(f"{month.capitalize():<15} │ {result['total_uncontacted']:<18} │ {result['without_lead_status']:<20} │ {result['with_lead_status']:<18} │ {pct:<17.1f}%")
        else:
            print(f"{month.capitalize():<15} │ {'N/A':<18} │ {'N/A':<20} │ {'N/A':<18} │ {'N/A':<18}")
    
    # Owner comparison
    print("\n" + "=" * 100)
    print("OWNER COMPARISON - CONTACTS WITHOUT LEAD STATUS")
    print("=" * 100)
    
    # Collect all owners across months
    all_owners = set()
    owner_data = {}
    
    for month in months:
        result = all_results.get(month)
        if result and 'owner_breakdown' in result:
            for _, row in result['owner_breakdown'].iterrows():
                owner_name = row['owner_name']
                all_owners.add(owner_name)
                if owner_name not in owner_data:
                    owner_data[owner_name] = {}
                owner_data[owner_name][month] = {
                    'total_uncontacted': row['total_uncontacted'],
                    'without_lead_status': row['without_lead_status'],
                    'pct_without_status': row['pct_without_status']
                }
    
    # Print owner comparison table
    print(f"\n{'Owner Name':<35} │ {'Oct Without':<15} │ {'Nov Without':<15} │ {'Dec Without':<15} │ {'Oct %':<10} │ {'Nov %':<10} │ {'Dec %':<10}")
    print("─" * 35 + "┼" + "─" * 15 + "┼" + "─" * 15 + "┼" + "─" * 15 + "┼" + "─" * 10 + "┼" + "─" * 10 + "┼" + "─" * 10)
    
    for owner_name in sorted(all_owners):
        oct_data = owner_data.get(owner_name, {}).get('october', {})
        nov_data = owner_data.get(owner_name, {}).get('november', {})
        dec_data = owner_data.get(owner_name, {}).get('december', {})
        
        oct_count = oct_data.get('without_lead_status', 0) if oct_data else 0
        nov_count = nov_data.get('without_lead_status', 0) if nov_data else 0
        dec_count = dec_data.get('without_lead_status', 0) if dec_data else 0
        
        oct_pct = oct_data.get('pct_without_status', 0) if oct_data else 0
        nov_pct = nov_data.get('pct_without_status', 0) if nov_data else 0
        dec_pct = dec_data.get('pct_without_status', 0) if dec_data else 0
        
        print(f"{owner_name:<35} │ {oct_count:<15} │ {nov_count:<15} │ {dec_count:<15} │ {oct_pct:<9.1f}% │ {nov_pct:<9.1f}% │ {dec_pct:<9.1f}%")
    
    return all_results

def main():
    parser = argparse.ArgumentParser(description='Analyze uncontacted contacts without Lead Status')
    parser.add_argument('--contacts-file',
                       default=None,
                       help='Path to contacts CSV file (if provided, analyzes single file)')
    parser.add_argument('--compare-months',
                       action='store_true',
                       help='Compare across October, November, and December')
    
    args = parser.parse_args()
    
    if args.compare_months:
        compare_months()
    elif args.contacts_file:
        if not os.path.exists(args.contacts_file):
            print(f"❌ Error: File not found: {args.contacts_file}")
            sys.exit(1)
        analyze_uncontacted_lead_status(args.contacts_file)
    else:
        # Default: compare months
        compare_months()

if __name__ == '__main__':
    main()

