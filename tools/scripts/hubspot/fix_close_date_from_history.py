#!/usr/bin/env python3
"""
Fix Deal Close Date from Property History
==========================================
Gets the earliest close date from deal property history when the deal was won.
This is useful for fixing deals where the close date was updated incorrectly.

Usage:
    # Process a single company
    python fix_close_date_from_history.py --company-id 17655187038
    
    # Process a single deal
    python fix_close_date_from_history.py --deal-id 15583212916
    
    # Process from CSV (with company_id or deal_id columns)
    python fix_close_date_from_history.py --csv input.csv
    
    # Apply updates (default is dry run)
    python fix_close_date_from_history.py --csv input.csv --update
    
    # Save results to CSV
    python fix_close_date_from_history.py --csv input.csv --output results.csv

CSV Format:
    The CSV file should contain either:
    - A 'company_id' column (will fetch all deals for each company)
    - A 'deal_id' column (will process those specific deals)
    - Or both columns (will process all deals from companies + specific deals)
"""

import os
import sys
import argparse
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List

# Load environment variables
load_dotenv()

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY") or os.getenv("ColppyCRMAutomations")
HUBSPOT_BASE_URL = "https://api.hubapi.com"

def get_deal_property_history(deal_id: str, property_name: str = "closedate") -> List[Dict[str, Any]]:
    """
    Get property history for a deal using HubSpot API
    
    Args:
        deal_id: HubSpot deal ID
        property_name: Property name to get history for (default: closedate)
    
    Returns:
        List of property history entries
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/{deal_id}"
    
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    params = {
        "propertiesWithHistory": property_name
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # HubSpot returns property history in "propertiesWithHistory" key at top level
        properties_with_history = data.get("propertiesWithHistory", {})
        property_data = properties_with_history.get(property_name)
        
        # Property history format: can be a list of versions directly, or a dict with "versions" key
        if isinstance(property_data, list):
            # Direct list of versions
            history = property_data
        elif isinstance(property_data, dict) and "versions" in property_data:
            # Dict with versions array
            history = property_data.get("versions", [])
        else:
            # No history available
            history = []
        
        return history
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching property history: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return []

def get_earliest_close_date_from_history(deal_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the earliest close date from deal property history
    This finds when the deal was FIRST closed (won), not the most recent update
    
    Args:
        deal_id: HubSpot deal ID
    
    Returns:
        Dictionary with earliest close date info or None
    """
    history = get_deal_property_history(deal_id, "closedate")
    
    if not history:
        return None
    
    # Collect all valid close dates from history
    valid_dates = []
    for entry in history:
        value = entry.get("value")
        if value and value.strip() and value.strip().lower() != "null":
            try:
                # Parse the date
                date_obj = datetime.fromisoformat(value.replace('Z', '+00:00'))
                valid_dates.append({
                    "date": date_obj,
                    "date_iso": date_obj.isoformat(),
                    "date_only": date_obj.date().isoformat(),
                    "timestamp": entry.get("timestamp"),
                    "sourceType": entry.get("sourceType"),
                    "sourceId": entry.get("sourceId"),
                    "value": value
                })
            except Exception as e:
                print(f"   ⚠️  Could not parse date '{value}': {e}")
                continue
    
    if not valid_dates:
        return None
    
    # Sort by date (earliest first) - this is the FIRST time the deal was closed
    sorted_dates = sorted(valid_dates, key=lambda x: x["date"])
    earliest = sorted_dates[0]
    
    return {
        "date": earliest["date_iso"],
        "date_only": earliest["date_only"],
        "timestamp": earliest["timestamp"],
        "sourceType": earliest["sourceType"],
        "sourceId": earliest["sourceId"],
        "all_dates": [d["date_only"] for d in sorted_dates]
    }

def get_deal_info(deal_id: str) -> Optional[Dict[str, Any]]:
    """Get current deal information"""
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/{deal_id}"
    
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    params = {
        "properties": "dealname,dealstage,closedate,fecha_pedido_baja"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching deal: {e}")
        return None

def update_deal_close_date(deal_id: str, new_close_date: str) -> bool:
    """
    Update deal close date
    
    Args:
        deal_id: HubSpot deal ID
        new_close_date: New close date in ISO format
    
    Returns:
        True if successful, False otherwise
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/{deal_id}"
    
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "properties": {
            "closedate": new_close_date
        }
    }
    
    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error updating deal: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return False

def get_company_deals(company_id: str) -> List[str]:
    """Get all deal IDs associated with a company"""
    url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/companies/{company_id}/associations/deals"
    
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    deal_ids = []
    after = None
    
    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            for result in results:
                deal_ids.append(str(result.get("toObjectId")))
            
            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            
            if not after:
                break
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching company deals: {e}")
            break
    
    return deal_ids

def load_deal_ids_from_csv(csv_path: str) -> List[str]:
    """
    Load deal IDs or company IDs from CSV file
    
    Args:
        csv_path: Path to CSV file
    
    Returns:
        List of deal IDs to process
    """
    try:
        df = pd.read_csv(csv_path)
        print(f"📄 Loaded CSV: {csv_path}")
        print(f"   Total rows: {len(df)}")
        print(f"   Columns: {', '.join(df.columns.tolist())}")
        
        deal_ids = []
        
        # Check for deal_id column
        if 'deal_id' in df.columns:
            deal_ids_from_csv = df['deal_id'].dropna().astype(str).tolist()
            deal_ids.extend(deal_ids_from_csv)
            print(f"   Found {len(deal_ids_from_csv)} deal IDs in CSV")
        
        # Check for company_id column - need to fetch deals for each company
        if 'company_id' in df.columns:
            company_ids = df['company_id'].dropna().astype(str).unique().tolist()
            print(f"   Found {len(company_ids)} unique company IDs in CSV")
            
            for company_id in company_ids:
                print(f"   🔍 Getting deals for company {company_id}...")
                company_deal_ids = get_company_deals(company_id)
                deal_ids.extend(company_deal_ids)
                print(f"      Found {len(company_deal_ids)} deals")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_deal_ids = []
        for deal_id in deal_ids:
            if deal_id not in seen:
                seen.add(deal_id)
                unique_deal_ids.append(deal_id)
        
        print(f"   📊 Total unique deal IDs to process: {len(unique_deal_ids)}")
        return unique_deal_ids
        
    except FileNotFoundError:
        print(f"❌ Error: CSV file not found: {csv_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Fix deal close date from property history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single company
  python fix_close_date_from_history.py --company-id 17655187038
  
  # Process a single deal
  python fix_close_date_from_history.py --deal-id 15583212916
  
  # Process from CSV (with company_id or deal_id columns)
  python fix_close_date_from_history.py --csv input.csv
  
  # Apply updates (default is dry run)
  python fix_close_date_from_history.py --csv input.csv --update
  
  # Save results to CSV
  python fix_close_date_from_history.py --csv input.csv --output results.csv
        """
    )
    parser.add_argument("--company-id", type=str, help="Company ID to process")
    parser.add_argument("--deal-id", type=str, help="Deal ID to process")
    parser.add_argument("--csv", type=str, help="CSV file with company_id or deal_id columns")
    parser.add_argument("--output", type=str, help="Output CSV file path for results")
    parser.add_argument("--update", action="store_true", help="Actually update the close date (default: dry run)")
    
    args = parser.parse_args()
    
    if not HUBSPOT_API_KEY:
        print("❌ Error: HUBSPOT_API_KEY or ColppyCRMAutomations not found in environment variables")
        sys.exit(1)
    
    deal_ids = []
    
    if args.csv:
        deal_ids = load_deal_ids_from_csv(args.csv)
    elif args.company_id:
        print(f"🔍 Getting deals for company {args.company_id}...")
        deal_ids = get_company_deals(args.company_id)
        print(f"   Found {len(deal_ids)} deals")
    elif args.deal_id:
        deal_ids = [args.deal_id]
    else:
        print("❌ Error: Must provide either --company-id, --deal-id, or --csv")
        parser.print_help()
        sys.exit(1)
    
    if not deal_ids:
        print("❌ No deals found")
        sys.exit(1)
    
    print(f"\n📊 Processing {len(deal_ids)} deal(s)...\n")
    print("=" * 100)
    
    updates = []
    
    for deal_id in deal_ids:
        print(f"\n🔍 Deal ID: {deal_id}")
        
        # Get current deal info
        deal_info = get_deal_info(deal_id)
        if not deal_info:
            print("   ❌ Could not fetch deal info")
            continue
        
        props = deal_info.get("properties", {})
        deal_name = props.get("dealname", "Unknown")
        current_stage = props.get("dealstage", "Unknown")
        current_close_date = props.get("closedate", "")
        
        print(f"   Deal Name: {deal_name}")
        print(f"   Current Stage: {current_stage}")
        print(f"   Current Close Date: {current_close_date or 'NULL'}")
        
        # Get earliest close date from history
        earliest = get_earliest_close_date_from_history(deal_id)
        
        if not earliest:
            print("   ⚠️  No close date history found")
            updates.append({
                "deal_id": deal_id,
                "deal_name": deal_name,
                "status": "no_history",
                "old_date": current_close_date,
                "new_date": "",
                "old_date_only": current_date_only,
                "new_date_only": "",
                "message": "No close date history found"
            })
            continue
        
        print(f"   📅 Earliest Close Date from History: {earliest['date']}")
        print(f"   📅 Date Only: {earliest['date_only']}")
        print(f"   📊 Source: {earliest.get('source', 'Unknown')}")
        
        # Compare with current
        current_date_only = None
        if current_close_date:
            try:
                current_date_only = datetime.fromisoformat(current_close_date.replace('Z', '+00:00')).date().isoformat()
            except:
                pass
        
        if current_date_only and current_date_only == earliest['date_only']:
            print(f"   ✅ Close date is already correct ({current_date_only})")
            updates.append({
                "deal_id": deal_id,
                "deal_name": deal_name,
                "status": "no_change",
                "old_date": current_close_date,
                "new_date": earliest['date'],
                "old_date_only": current_date_only,
                "new_date_only": earliest['date_only'],
                "message": "Close date already correct"
            })
        else:
            print(f"   ⚠️  MISMATCH: Current ({current_date_only or 'NULL'}) vs Earliest from History ({earliest['date_only']})")
            
            if args.update:
                print(f"   🔄 Updating close date to {earliest['date']}...")
                if update_deal_close_date(deal_id, earliest['date']):
                    print(f"   ✅ Successfully updated!")
                    updates.append({
                        "deal_id": deal_id,
                        "deal_name": deal_name,
                        "status": "updated",
                        "old_date": current_close_date,
                        "new_date": earliest['date'],
                        "old_date_only": current_date_only,
                        "new_date_only": earliest['date_only'],
                        "message": "Successfully updated"
                    })
                else:
                    print(f"   ❌ Failed to update")
                    updates.append({
                        "deal_id": deal_id,
                        "deal_name": deal_name,
                        "status": "error",
                        "old_date": current_close_date,
                        "new_date": earliest['date'],
                        "old_date_only": current_date_only,
                        "new_date_only": earliest['date_only'],
                        "message": "Failed to update"
                    })
            else:
                print(f"   💡 DRY RUN: Would update to {earliest['date']} (use --update to apply)")
                updates.append({
                    "deal_id": deal_id,
                    "deal_name": deal_name,
                    "status": "dry_run",
                    "old_date": current_close_date,
                    "new_date": earliest['date'],
                    "old_date_only": current_date_only,
                    "new_date_only": earliest['date_only'],
                    "message": "Would update (dry run)"
                })
        
        print("-" * 100)
    
    # Summary
    print(f"\n\n📊 SUMMARY")
    print("=" * 100)
    print(f"Total deals processed: {len(deal_ids)}")
    print(f"Deals with mismatches: {len(updates)}")
    
    if updates:
        print(f"\n📋 Updates {'(DRY RUN)' if not args.update else '(APPLIED)'}:")
        for update in updates:
            print(f"   Deal {update['deal_id']}: {update['deal_name']}")
            print(f"      {update['old_date_only'] or 'NULL'} → {update['new_date_only']}")
    
    # Save to CSV if output path provided (save all results, not just updates)
    if args.output:
        try:
            output_df = pd.DataFrame(updates)
            output_df.to_csv(args.output, index=False)
            print(f"\n💾 Results saved to: {args.output}")
            print(f"   Total records: {len(updates)}")
        except Exception as e:
            print(f"\n⚠️  Error saving CSV: {e}")
    
    if not args.update and updates:
        print(f"\n💡 To apply updates, run with --update flag")

if __name__ == "__main__":
    main()

