#!/usr/bin/env python3
"""
Sales Team Ramping Cohort Analysis
==================================
Analyzes sales rep performance from their start date, showing cumulative deals closed
over time as a cohort analysis. Each rep's trajectory is plotted from month 1 (their
first month) onwards.

A closed won deal is counted based on its close date, which determines the month
to attribute it to.
"""

import sys
import os
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from hubspot_api.client import HubSpotClient
from hubspot_api.models import Deal
from hubspot_api.config import get_config

# Import owner_utils with relative import
sys.path.insert(0, os.path.dirname(__file__))
from owner_utils import get_owner_name, _STATIC_OWNER_MAP

# Configuration
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'outputs', 'visualizations', 'hubspot'
)

# Sales team identifiers (from HubSpot teams)
SALES_TEAMS = ['Closers', 'Accountant Channel']  # Teams that contain sales reps

# Month mapping for CSV parsing
MONTH_ABBR_TO_NUM = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

# Reverse mapping for static owner map to find owner IDs by name
_OWNER_NAME_TO_ID = {v: k for k, v in _STATIC_OWNER_MAP.items()}

# Additional owner mappings not in static map (from hubspot_owner_list.txt)
_ADDITIONAL_OWNER_MAP = {
    "Romina Herrera": "612003866"
}

# Merge both maps
for name, owner_id in _ADDITIONAL_OWNER_MAP.items():
    _OWNER_NAME_TO_ID[name] = owner_id


def get_all_sales_reps(client: Optional[HubSpotClient] = None) -> Dict[str, str]:
    """
    Get all sales reps from HubSpot (owners in Closers or Accountant Channel teams).
    
    Args:
        client: HubSpot client instance
        
    Returns:
        Dictionary mapping rep name to owner ID
    """
    if client is None:
        client = HubSpotClient()
    
    print("🔍 Fetching all sales reps from HubSpot...")
    
    # Get all owners
    owners_response = client.get("crm/v3/owners")
    owners = owners_response.get("results", [])
    
    sales_reps = {}
    excluded_names = ['mariano', 'mariano alvarez', 'sofia celentano', 'sofia']  # Exclude Mariano and Sofia who are out
    
    for owner in owners:
        owner_id = str(owner.get("id", ""))
        first_name = owner.get("firstName", "")
        last_name = owner.get("lastName", "")
        full_name = f"{first_name} {last_name}".strip()
        archived = owner.get("archived", True)
        
        # Skip archived owners
        if archived:
            continue
        
        # Skip excluded names
        if any(excluded.lower() in full_name.lower() for excluded in excluded_names):
            print(f"⏭️  Excluding {full_name} (out/archived)")
            continue
        
        # Check if owner is in a sales team
        teams = owner.get("teams", [])
        is_sales_rep = False
        
        for team in teams:
            team_name = team.get("name", "")
            if team_name in SALES_TEAMS:
                is_sales_rep = True
                break
        
        if is_sales_rep and full_name:
            sales_reps[full_name] = owner_id
            print(f"  ✓ {full_name} (Owner ID: {owner_id}) - Teams: {[t.get('name') for t in teams]}")
    
    print(f"✅ Found {len(sales_reps)} active sales reps")
    return sales_reps


def find_rep_start_from_deals(
    rep_name: str,
    owner_id: str,
    client: Optional[HubSpotClient] = None
) -> Optional[Tuple[int, int]]:
    """
    Find when a rep started by finding their first closed won deal in recent period.
    Uses a more recent start date (2024+) to avoid old reassigned deals.
    For reps with deals in 2024-2025, uses the earliest deal in that period.
    For older reps, uses their actual first deal.
    
    Args:
        rep_name: Rep name
        owner_id: HubSpot owner ID
        client: HubSpot client instance
        
    Returns:
        Tuple of (month, year) or None if not found
    """
    if client is None:
        client = HubSpotClient()
    
    print(f"🔍 Finding start date for {rep_name} (Owner ID: {owner_id})...")
    
    # First, try to find deals from 2024-2025 (recent period for ramping analysis)
    # Use createdate (when deal was created/assigned) instead of closedate for start date
    # This gives us when they actually started working, not when they closed their first deal
    filter_groups_recent = [
        {
            "filters": [
                {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
                {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"},
                {"propertyName": "createdate", "operator": "GTE", "value": "2024-01-01T00:00:00Z"}
            ]
        },
        {
            "filters": [
                {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
                {"propertyName": "dealstage", "operator": "EQ", "value": "34692158"},  # Recovery
                {"propertyName": "createdate", "operator": "GTE", "value": "2024-01-01T00:00:00Z"}
            ]
        }
    ]
    
    properties = ["createdate", "closedate", "dealstage"]
    sorts = [{"propertyName": "createdate", "direction": "ASCENDING"}]
    
    # Try recent period first (2024+)
    response = client.search_objects(
        object_type="deals",
        filter_groups=filter_groups_recent[:1],
        properties=properties,
        sorts=sorts,
        limit=1
    )
    
    results = response.get("results", [])
    if not results:
        # Try recovery stage in recent period
        response = client.search_objects(
            object_type="deals",
            filter_groups=filter_groups_recent[1:],
            properties=properties,
            sorts=sorts,
            limit=1
        )
        results = response.get("results", [])
    
    # If found in recent period, use createdate (when they started working on the deal)
    if results:
        first_deal = results[0]
        create_date = first_deal.get("properties", {}).get("createdate")
        if create_date:
            month_year = parse_closedate(create_date)  # parse_closedate works for any ISO date
            if month_year:
                month, year = month_year
                print(f"  ✓ Found start date for {rep_name} (from deal creation date): {month}/{year}")
                return (month, year)
    
    # If no recent deals, try all-time (for older reps like Karina, Rocio)
    filter_groups_all = [
        {
            "filters": [
                {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
                {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"},
                {"propertyName": "closedate", "operator": "GTE", "value": "2020-01-01T00:00:00Z"}
            ]
        }
    ]
    
    response = client.search_objects(
        object_type="deals",
        filter_groups=filter_groups_all,
        properties=properties,
        sorts=sorts,
        limit=1
    )
    
    results = response.get("results", [])
    if results:
        first_deal = results[0]
        close_date = first_deal.get("properties", {}).get("closedate")
        if close_date:
            month_year = parse_closedate(close_date)
            if month_year:
                month, year = month_year
                print(f"  ✓ Found start date for {rep_name} (all-time): {month}/{year}")
                return (month, year)
    
    print(f"  ⚠️  No deals found for {rep_name}")
    return None


def normalize_name(name: str) -> str:
    """
    Normalize name for comparison (remove accents, lowercase, strip).
    
    Args:
        name: Name string
        
    Returns:
        Normalized name
    """
    name = name.strip().lower()
    # Remove common accents and special characters
    replacements = {
        'í': 'i', 'á': 'a', 'é': 'e', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u'
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name


def get_owner_id_from_name(rep_name: str) -> Optional[str]:
    """
    Get HubSpot owner ID from rep name.
    
    Args:
        rep_name: Sales rep name
        
    Returns:
        Owner ID as string, or None if not found
    """
    # Normalize names for comparison
    rep_name_normalized = normalize_name(rep_name)
    
    # Try direct match first
    for name, owner_id in _OWNER_NAME_TO_ID.items():
        if normalize_name(name) == rep_name_normalized:
            return owner_id
    
    # Try matching first and last name separately
    # Handle cases like "Jair Calás" vs "Jair Josue Calas"
    rep_parts = rep_name_normalized.split()
    if len(rep_parts) >= 2:
        rep_first = rep_parts[0]
        rep_last = rep_parts[-1]
        
        for name, owner_id in _OWNER_NAME_TO_ID.items():
            name_normalized = normalize_name(name)
            name_parts = name_normalized.split()
            if len(name_parts) >= 2:
                name_first = name_parts[0]
                name_last = name_parts[-1]
                # Match if first and last names match
                if rep_first == name_first and rep_last == name_last:
                    return owner_id
    
    print(f"⚠️ Warning: Owner ID not found for rep: {rep_name}")
    return None


def fetch_closed_won_deals(
    start_date: str,
    end_date: str,
    client: Optional[HubSpotClient] = None
) -> List[Dict]:
    """
    Fetch all closed won deals from HubSpot in the date range.
    
    Args:
        start_date: Start date in format 'YYYY-MM-DD'
        end_date: End date in format 'YYYY-MM-DD'
        client: HubSpot client instance (optional)
        
    Returns:
        List of deal dictionaries with properties
    """
    print(f"📊 Fetching closed won deals from {start_date} to {end_date}...")
    
    if client is None:
        client = HubSpotClient()
    
    # Fetch deals with both closedwon and recovery stage
    filter_groups = [
        {
            "filters": [
                {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"},
                {"propertyName": "closedate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                {"propertyName": "closedate", "operator": "LT", "value": f"{end_date}T23:59:59Z"}
            ]
        },
        {
            "filters": [
                {"propertyName": "dealstage", "operator": "EQ", "value": "34692158"},  # Recovery stage
                {"propertyName": "closedate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                {"propertyName": "closedate", "operator": "LT", "value": f"{end_date}T23:59:59Z"}
            ]
        }
    ]
    
    properties = [
        "dealname",
        "amount",
        "dealstage",
        "closedate",
        "createdate",
        "hubspot_owner_id",
        "hs_all_collaborator_owner_ids"  # Include collaborators for Accountant Channel tracking
    ]
    
    all_deals = []
    for filter_group in filter_groups:
        deals = client.get_all_objects(
            object_type="deals",
            filter_groups=[filter_group],
            properties=properties
        )
        all_deals.extend(deals)
        stage = filter_group['filters'][0]['value']
        stage_name = "Recovery" if stage == "34692158" else "Closed Won"
        print(f"  ✓ Fetched {len(deals)} deals from {stage_name} stage")
    
    print(f"✅ Total closed won deals fetched: {len(all_deals)}")
    return all_deals


def parse_closedate(date_str: Optional[str]) -> Optional[Tuple[int, int]]:
    """
    Parse HubSpot close date to (month, year).
    
    Args:
        date_str: Date string from HubSpot (ISO format)
        
    Returns:
        Tuple of (month, year) or None if invalid
    """
    if not date_str:
        return None
    
    try:
        # HubSpot dates are in ISO format: "2025-03-15T10:30:00Z"
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return (dt.month, dt.year)
    except (ValueError, AttributeError):
        return None


def get_rep_team(rep_name: str, owner_id: str, client: Optional[HubSpotClient] = None) -> Optional[str]:
    """
    Get the primary team for a sales rep.
    
    Uses the correct Owners API endpoint: /crm/v3/owners/{ownerId}
    (NOT /crm/v3/objects/owners/{ownerId} which doesn't work)
    
    Args:
        rep_name: Rep name
        owner_id: Owner ID
        client: HubSpot client instance
        
    Returns:
        Team name ('Accountant Channel' or 'Closers') or None
    """
    if client is None:
        client = HubSpotClient()
    
    try:
        # Use the correct Owners API endpoint (not objects/owners)
        # See: tools/docs/README_HUBSPOT_CONFIGURATION.md line 82-87
        # The Owners API endpoint is /crm/v3/owners/{ownerId}, not /crm/v3/objects/owners/{ownerId}
        owner = client.get(f"crm/v3/owners/{owner_id}")
        if not owner:
            return None
        
        teams = owner.get("teams", [])
        for team in teams:
            team_name = team.get("name", "")
            if team_name == "Accountant Channel":
                return "Accountant Channel"
            if team_name == "Closers":
                return "Closers"
    except:
        pass
    return None


def get_deals_for_rep_month(
    deals: List[Dict],
    rep_starts: Dict[str, Tuple[int, int]],
    owner_name_to_id: Dict[str, str],
    rep_name: str,
    target_month: int,
    target_year: int,
    client: Optional[HubSpotClient] = None
) -> List[Dict]:
    """
    Get all deals for a specific rep in a specific month/year.
    Includes deals where rep is owner or collaborator (if Accountant Channel).
    
    Args:
        deals: List of all deal dictionaries
        rep_starts: Dictionary mapping rep name to (month, year) start date
        owner_name_to_id: Dictionary mapping rep name to owner ID
        rep_name: Name of the rep to filter for
        target_month: Target month (1-12)
        target_year: Target year
        client: HubSpot client instance
        
    Returns:
        List of deal info dictionaries
    """
    if rep_name not in rep_starts:
        return []
    
    if client is None:
        client = HubSpotClient()
    
    # Get rep's owner ID
    rep_owner_id = owner_name_to_id.get(rep_name)
    if not rep_owner_id:
        return []
    
    # Get rep's team
    rep_team = get_rep_team(rep_name, rep_owner_id, client)
    
    # Map owner IDs to rep names
    owner_id_to_name = {v: k for k, v in owner_name_to_id.items()}
    
    matching_deals = []
    
    for deal in deals:
        props = deal.get('properties', {})
        owner_id = props.get('hubspot_owner_id', '')
        close_date = props.get('closedate', '')
        collaborator_ids_str = props.get('hs_all_collaborator_owner_ids', '')
        
        if not close_date:
            continue
        
        # Parse close date
        close_month_year = parse_closedate(close_date)
        if not close_month_year:
            continue
        
        close_month, close_year = close_month_year
        
        # Check if this deal is in the target month/year
        if close_month != target_month or close_year != target_year:
            continue
        
        # Check if rep is involved (owner or collaborator)
        is_owner = (owner_id == rep_owner_id)
        is_collaborator = False
        collaborator_names = []
        
        if collaborator_ids_str:
            collaborator_ids = [cid.strip() for cid in str(collaborator_ids_str).split(';') if cid.strip()]
            # Note: Owner ID may appear in collaborator list when there are other collaborators
            # Only count as collaborator if NOT the owner
            is_collaborator = (rep_owner_id in collaborator_ids) and not is_owner
            collaborator_names = [get_owner_name(cid) for cid in collaborator_ids if get_owner_name(cid)]
        
        # For Accountant Channel reps, count if owner OR collaborator
        # For Closers, only count as owner (never as collaborator)
        if is_owner or (is_collaborator and rep_team == "Accountant Channel"):
            deal_info = {
                'deal_id': deal.get('id'),
                'deal_name': props.get('dealname', 'N/A'),
                'amount': props.get('amount', '0'),
                'close_date': close_date,
                'owner_id': owner_id,
                'owner_name': get_owner_name(owner_id) if owner_id else 'N/A',
                'collaborator_names': collaborator_names,
                'is_owner': is_owner,
                'is_collaborator': is_collaborator,
                'dealstage': props.get('dealstage', 'N/A')
            }
            matching_deals.append(deal_info)
    
    return matching_deals


def calculate_cohort_data(
    deals: List[Dict],
    rep_starts: Dict[str, Tuple[int, int]],
    owner_name_to_id: Dict[str, str],
    client: Optional[HubSpotClient] = None
) -> pd.DataFrame:
    """
    Calculate cohort data: deals grouped by rep and cohort month.
    
    Args:
        deals: List of deal dictionaries from HubSpot
        rep_starts: Dictionary mapping rep name to (month, year) start date
        owner_name_to_id: Dictionary mapping rep name to owner ID
        
    Returns:
        DataFrame with columns: rep_name, cohort_month, deals_count, cumulative_deals
    """
    print("📈 Calculating cohort data (including collaborators for Accountant Channel)...")
    
    if client is None:
        client = HubSpotClient()
    
    # Map owner IDs to rep names (inverse of owner_name_to_id)
    owner_id_to_name = {v: k for k, v in owner_name_to_id.items()}
    
    # Build team mapping for each rep
    rep_teams = {}
    for rep_name, owner_id in owner_name_to_id.items():
        if rep_name in rep_starts:
            team = get_rep_team(rep_name, owner_id, client)
            rep_teams[rep_name] = team
    
    # Group deals by rep and month
    rep_month_deals = defaultdict(lambda: defaultdict(int))
    
    for deal in deals:
        props = deal.get('properties', {})
        owner_id = props.get('hubspot_owner_id')
        close_date = props.get('closedate')
        collaborator_ids_str = props.get('hs_all_collaborator_owner_ids', '')
        
        if not close_date:
            continue
        
        # Parse close date
        close_month_year = parse_closedate(close_date)
        if not close_month_year:
            continue
        
        close_month, close_year = close_month_year
        
        # Get all reps involved in this deal (owner + collaborators)
        reps_involved = set()
        
        # Add deal owner if they're in our rep list
        if owner_id:
            rep_name = owner_id_to_name.get(str(owner_id))
            if rep_name and rep_name in rep_starts:
                reps_involved.add(rep_name)
        
        # Parse collaborators (semicolon-separated)
        if collaborator_ids_str:
            collaborator_ids = [cid.strip() for cid in str(collaborator_ids_str).split(';') if cid.strip()]
            for collab_id in collaborator_ids:
                # Skip if this collaborator is also the owner (owner may appear in collaborator list)
                if str(collab_id) == str(owner_id):
                    continue
                    
                rep_name = owner_id_to_name.get(str(collab_id))
                if rep_name and rep_name in rep_starts:
                    # For Accountant Channel reps, count them as collaborators
                    # For Closers, they don't count as collaborators (only as owners)
                    rep_team = rep_teams.get(rep_name)
                    if rep_team == "Accountant Channel":
                        reps_involved.add(rep_name)
        
        # Count this deal for each rep involved
        for rep_name in reps_involved:
            start_month, start_year = rep_starts[rep_name]
            
            # Calculate cohort month
            # Month 0 = first month (start month), Month 1 = second month, etc.
            if close_year == start_year:
                cohort_month = close_month - start_month  # Month 0 for first month
            elif close_year > start_year:
                months_diff = (close_year - start_year) * 12
                cohort_month = close_month - start_month + months_diff  # Month 0 for first month
            else:
                continue
            
            if cohort_month < 0:
                continue
            
            rep_month_deals[rep_name][cohort_month] += 1
    
    # Build DataFrame - fill ALL months from Month 0 to max month for each rep
    # This ensures we can compare Month 1, Month 2, etc. across all reps
    data_rows = []
    
    # Find the maximum month across all reps
    all_months = set()
    for rep_name in rep_starts.keys():
        if rep_name in rep_month_deals:
            all_months.update(rep_month_deals[rep_name].keys())
    max_month = max(all_months) if all_months else 0
    
    for rep_name in rep_starts.keys():
        cumulative = 0
        
        # Fill ALL months from Month 0 to max_month for this rep
        # This allows proper comparison across reps at the same cohort month
        for month in range(0, max_month + 1):
            deals_count = rep_month_deals[rep_name].get(month, 0)  # 0 if no deals in this month
            cumulative += deals_count
            data_rows.append({
                'rep_name': rep_name,
                'cohort_month': month,
                'deals_count': deals_count,
                'cumulative_deals': cumulative
            })
    
    df = pd.DataFrame(data_rows)
    print(f"✅ Processed {len(df)} rep-month combinations (filled all months from 0 to {max_month})")
    return df


def create_deals_per_month_table(
    deals: List[Dict], 
    rep_starts: Dict[str, Tuple[int, int]], 
    owner_name_to_id: Dict[str, str],
    client: Optional[HubSpotClient] = None,
    start_year: int = 2024,
    end_year: int = 2025
) -> pd.DataFrame:
    """
    Create a table showing deals closed per rep per month.
    Shows data from start_year through end_year.
    
    Args:
        deals: List of deal dictionaries from HubSpot
        rep_starts: Dictionary mapping rep name to (month, year) start date
        owner_name_to_id: Dictionary mapping rep name to owner ID
        start_year: First year to include
        end_year: Last year to include
        
    Returns:
        DataFrame with deals per rep per month
    """
    print(f"📊 Creating deals per month table ({start_year}-{end_year}, including collaborators)...")
    
    if client is None:
        client = HubSpotClient()
    
    # Map owner IDs to rep names
    owner_id_to_name = {v: k for k, v in owner_name_to_id.items()}
    
    # Build team mapping
    rep_teams = {}
    for rep_name, owner_id in owner_name_to_id.items():
        if rep_name in rep_starts:
            team = get_rep_team(rep_name, owner_id, client)
            rep_teams[rep_name] = team
    
    # Group deals by rep, year, and month
    rep_month_deals = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    
    for deal in deals:
        props = deal.get('properties', {})
        owner_id = props.get('hubspot_owner_id')
        close_date = props.get('closedate')
        collaborator_ids_str = props.get('hs_all_collaborator_owner_ids', '')
        
        if not close_date:
            continue
        
        # Parse close date
        close_month_year = parse_closedate(close_date)
        if not close_month_year:
            continue
        
        close_month, close_year = close_month_year
        
        # Only count deals in the year range
        if close_year < start_year or close_year > end_year:
            continue
        
        # Get all reps involved in this deal
        reps_involved = set()
        
        # Add deal owner
        if owner_id:
            rep_name = owner_id_to_name.get(str(owner_id))
            if rep_name and rep_name in rep_starts:
                reps_involved.add(rep_name)
        
        # Parse collaborators
        if collaborator_ids_str:
            collaborator_ids = [cid.strip() for cid in str(collaborator_ids_str).split(';') if cid.strip()]
            for collab_id in collaborator_ids:
                rep_name = owner_id_to_name.get(str(collab_id))
                if rep_name and rep_name in rep_starts:
                    rep_team = rep_teams.get(rep_name)
                    if rep_team == "Accountant Channel":
                        reps_involved.add(rep_name)
        
        # Count for each rep involved
        for rep_name in reps_involved:
            rep_month_deals[rep_name][close_year][close_month] += 1
    
    # Build DataFrame with all months from start_year to end_year
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    # Create column names with year prefix for months
    columns = ['Rep Name']
    for year in range(start_year, end_year + 1):
        for month_name in month_names:
            columns.append(f"{month_name} {year}")
    columns.append('Total')
    
    data_rows = []
    # Sort reps by start date
    sorted_reps = sorted(rep_starts.items(), key=lambda x: (x[1][1], x[1][0]))
    
    for rep_name, start_date in sorted_reps:
        row = {'Rep Name': rep_name}
        total = 0
        
        for year in range(start_year, end_year + 1):
            for month_num in range(1, 13):
                month_name = month_names[month_num - 1]
                col_name = f"{month_name} {year}"
                count = rep_month_deals[rep_name][year].get(month_num, 0)
                row[col_name] = count
                total += count
        
        row['Total'] = total
        data_rows.append(row)
    
    df = pd.DataFrame(data_rows, columns=columns)
    return df


def print_markdown_table(df: pd.DataFrame, start_year: int = 2024, end_year: int = 2025):
    """
    Print DataFrame as markdown table.
    
    Args:
        df: DataFrame to print
        start_year: First year in the data
        end_year: Last year in the data
    """
    print("\n" + "=" * 100)
    print(f"DEALS CLOSED PER REP PER MONTH ({start_year}-{end_year})")
    print("=" * 100 + "\n")
    
    # Print markdown table
    columns = list(df.columns)
    
    # Header
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join([" --- " for _ in columns]) + "|"
    print(header)
    print(separator)
    
    # Rows
    for _, row in df.iterrows():
        values = []
        for col in columns:
            val = row.get(col, 0)
            if isinstance(val, (int, float)):
                values.append(str(int(val)))
            else:
                values.append(str(val))
        print("| " + " | ".join(values) + " |")
    
    print("\n" + "=" * 100)


def create_cohort_grid_table(
    deals: List[Dict],
    rep_starts: Dict[str, Tuple[int, int]],
    owner_name_to_id: Dict[str, str],
    client: Optional[HubSpotClient] = None,
    max_months: Optional[int] = None
) -> pd.DataFrame:
    """
    Create a cohort grid table showing deals per rep per cohort month.
    Month 1 = first month from start date, Month 2 = second month, etc.
    
    Args:
        deals: List of deal dictionaries from HubSpot
        rep_starts: Dictionary mapping rep name to (month, year) start date
        owner_name_to_id: Dictionary mapping rep name to owner ID
        max_months: Maximum number of cohort months to show (default 12)
        
    Returns:
        DataFrame with cohort months as rows, reps as columns
    """
    print("📊 Creating cohort grid table (including collaborators for Accountant Channel)...")
    
    if client is None:
        client = HubSpotClient()
    
    # Map owner IDs to rep names
    owner_id_to_name = {v: k for k, v in owner_name_to_id.items()}
    
    # Build team mapping
    rep_teams = {}
    for rep_name, owner_id in owner_name_to_id.items():
        if rep_name in rep_starts:
            team = get_rep_team(rep_name, owner_id, client)
            rep_teams[rep_name] = team
    
    # Group deals by rep and cohort month
    rep_cohort_deals = defaultdict(lambda: defaultdict(int))
    
    for deal in deals:
        props = deal.get('properties', {})
        owner_id = props.get('hubspot_owner_id')
        close_date = props.get('closedate')
        collaborator_ids_str = props.get('hs_all_collaborator_owner_ids', '')
        
        if not close_date:
            continue
        
        # Parse close date
        close_month_year = parse_closedate(close_date)
        if not close_month_year:
            continue
        
        close_month, close_year = close_month_year
        
        # Get all reps involved in this deal (owner + collaborators)
        reps_involved = set()
        
        # Add deal owner
        if owner_id:
            rep_name = owner_id_to_name.get(str(owner_id))
            if rep_name and rep_name in rep_starts:
                reps_involved.add(rep_name)
        
        # Parse collaborators
        if collaborator_ids_str:
            collaborator_ids = [cid.strip() for cid in str(collaborator_ids_str).split(';') if cid.strip()]
            for collab_id in collaborator_ids:
                rep_name = owner_id_to_name.get(str(collab_id))
                if rep_name and rep_name in rep_starts:
                    rep_team = rep_teams.get(rep_name)
                    if rep_team == "Accountant Channel":
                        reps_involved.add(rep_name)
        
        # Count for each rep involved
        for rep_name in reps_involved:
            start_month, start_year = rep_starts[rep_name]
            
            # Calculate cohort month
            # Month 0 = first month (start month), Month 1 = second month, etc.
            if close_year == start_year:
                cohort_month = close_month - start_month  # Month 0 for first month
            elif close_year > start_year:
                months_diff = (close_year - start_year) * 12
                cohort_month = close_month - start_month + months_diff  # Month 0 for first month
            else:
                continue
            
            if cohort_month < 0:
                continue
            
            rep_cohort_deals[rep_name][cohort_month] += 1
    
    # Determine max_months dynamically from actual data if not provided
    if max_months is None:
        all_months = set()
        for rep_name in rep_cohort_deals.keys():
            all_months.update(rep_cohort_deals[rep_name].keys())
        max_months = max(all_months) + 1 if all_months else 12  # +1 because months are 0-indexed
        print(f"  📊 Detected {max_months} months of data (Month 0 to Month {max_months-1})")
    
    # Build DataFrame - rows are cohort months, columns are reps
    # Sort reps by start date
    sorted_reps = sorted(rep_starts.items(), key=lambda x: (x[1][1], x[1][0]))
    rep_names = [rep[0] for rep in sorted_reps]
    
    # Create data rows - Month 0 to max_months-1
    # Fill all months so we can compare Month 1, Month 2, etc. across all reps
    data_rows = []
    for cohort_month in range(0, max_months):
        row = {'MES': cohort_month}
        for rep_name in rep_names:
            count = rep_cohort_deals[rep_name].get(cohort_month, 0)
            # Show 0 as "—" (gray) for months with no deals, actual count otherwise
            row[rep_name] = count if count > 0 else None  # None for gray cells
        data_rows.append(row)
    
    df = pd.DataFrame(data_rows)
    return df


def format_rep_name_with_date(rep_name: str, rep_starts: Dict[str, Tuple[int, int]]) -> str:
    """
    Format rep name with start date for visualization labels.
    
    Args:
        rep_name: Sales rep name
        rep_starts: Dictionary mapping rep name to (month, year) start date
        
    Returns:
        Formatted string like "Rocio Luque (Apr 2024)"
    """
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    if rep_name in rep_starts:
        start_month, start_year = rep_starts[rep_name]
        month_name = month_names[start_month - 1]
        return f"{rep_name} ({month_name} {start_year})"
    return rep_name


def create_cohort_grid_visualization(
    df: pd.DataFrame,
    output_path: str,
    rep_starts: Dict[str, Tuple[int, int]]
):
    """
    Create a heatmap/grid visualization of cohort data.
    
    Args:
        df: DataFrame with cohort months as rows, reps as columns
        output_path: Path to save visualization
        rep_starts: Dictionary mapping rep name to start date
    """
    print("📊 Creating cohort grid visualization...")
    
    # Prepare data for visualization
    df_viz = df.set_index('MES')
    
    # Create figure
    fig, ax = plt.subplots(figsize=(16, 10))
    
    # Create color map: None/0 = gray, positive values = color scale
    # Replace None with -1 for visualization purposes (will show as gray)
    df_plot = df_viz.copy()
    df_plot = df_plot.fillna(-1)
    
    # Create custom colormap: gray for -1, color scale for positive values
    import matplotlib.colors as mcolors
    from matplotlib.colors import LinearSegmentedColormap
    
    # Colors: gray for missing, light blue to dark blue for values
    colors = ['#D3D3D3'] + plt.cm.Blues(np.linspace(0.3, 1, 100)).tolist()
    cmap = LinearSegmentedColormap.from_list('custom', colors, N=101)
    
    # Create heatmap
    im = ax.imshow(df_plot.T, aspect='auto', cmap=cmap, vmin=-1, vmax=df_plot.max().max() if df_plot.max().max() > 0 else 10)
    
    # Set ticks and labels
    ax.set_xticks(range(len(df_plot.index)))
    ax.set_xticklabels([f'M{int(m)}' for m in df_plot.index])
    ax.set_xlabel('Cohort Month (MES)', fontsize=12, fontweight='bold')
    
    # Format rep names with start dates
    ax.set_yticks(range(len(df_plot.columns)))
    formatted_labels = [format_rep_name_with_date(col, rep_starts) for col in df_plot.columns]
    ax.set_yticklabels(formatted_labels)
    ax.set_ylabel('Sales Rep', fontsize=12, fontweight='bold')
    
    # Add text annotations
    for i in range(len(df_plot.columns)):
        for j in range(len(df_plot.index)):
            value = df_viz.iloc[j, i]
            if pd.notna(value) and value > 0:
                text = ax.text(j, i, int(value),
                             ha="center", va="center", color="black", fontweight='bold', fontsize=9)
            elif pd.isna(value):
                # Mark start position with an X or indicator
                rep_name = df_plot.columns[i]
                start_month, start_year = rep_starts.get(rep_name, (0, 0))
                # Mark start position (Month 0) - already handled by value display
                pass
    
    ax.set_title('Sales Team Cohort Analysis\nDeals Closed by Cohort Month (Month 0 = First Month)', 
                 fontsize=14, fontweight='bold', pad=20)
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Number of Deals Closed', rotation=270, labelpad=20)
    
    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ Cohort grid visualization saved to: {output_path}")
    plt.close()


def create_cohort_visualization(df: pd.DataFrame, output_path: str, rep_starts: Dict[str, Tuple[int, int]]):
    """
    Create cohort analysis line chart showing deals closed per cohort month.
    Each line represents a sales rep, showing deals closed in that month (not cumulative).
    
    Args:
        df: DataFrame with cohort data
        output_path: Path to save the visualization
        rep_starts: Dictionary mapping rep name to start date
    """
    print("📊 Creating cohort line chart visualization...")
    
    # Set style
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Plot each rep's trajectory (deals per month, not cumulative)
    reps = df['rep_name'].unique()
    colors = sns.color_palette("husl", len(reps))
    
    # Sort reps by name for consistent colors
    reps_sorted = sorted(reps)
    
    for idx, rep_name in enumerate(reps_sorted):
        rep_data = df[df['rep_name'] == rep_name].sort_values('cohort_month')
        
        if len(rep_data) == 0:
            continue
        
        # Format rep name with start date for label
        formatted_label = format_rep_name_with_date(rep_name, rep_starts)
        
        # Plot line showing deals per month (not cumulative)
        ax.plot(
            rep_data['cohort_month'],
            rep_data['deals_count'],
            marker='o',
            markersize=6,
            linewidth=2.5,
            label=formatted_label,
            color=colors[idx],
            alpha=0.8
        )
        
        # Mark the start (month 0) with an X
        start_data = rep_data[rep_data['cohort_month'] == 0]
        if len(start_data) > 0:
            ax.scatter(
                [0],
                [start_data.iloc[0]['deals_count']],
                s=150,
                marker='x',
                color=colors[idx],
                linewidths=3,
                zorder=5
            )
    
    # Customize chart
    ax.set_xlabel('Cohort Month (Month 0 = First Month)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Deals Closed in Month', fontsize=12, fontweight='bold')
    ax.set_title('Sales Team Ramping Cohort Analysis\nDeals Closed per Month from Start', 
                 fontsize=14, fontweight='bold', pad=20)
    
    # Grid
    ax.grid(True, alpha=0.3, linestyle='--', which='both')
    ax.set_axisbelow(True)
    
    # Legend
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10, framealpha=0.9)
    
    # Format axes
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.set_xlim(-0.5, None)  # Start slightly before 0
    
    # Set x-axis to show all months (no limit)
    max_month = df['cohort_month'].max() if len(df) > 0 else 12
    ax.set_xlim(-0.5, max_month + 1)
    
    # Tight layout
    plt.tight_layout()
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ Visualization saved to: {output_path}")
    plt.close()


def main():
    """Main execution function."""
    print("=" * 60)
    print("Sales Team Ramping Cohort Analysis")
    print("=" * 60)
    
    client = HubSpotClient()
    
    # 1. Get all sales reps from HubSpot
    print("\n1️⃣ Fetching all sales reps from HubSpot...")
    owner_name_to_id = get_all_sales_reps(client)
    
    if not owner_name_to_id:
        print("❌ Error: No sales reps found. Exiting.")
        return
    
    # 2. Get each rep's start date from hardcoded array
    # This array is manually maintained - update it when new employees join
    # Source: INGRESOS 2024 and 2025 tables from the image provided
    # Format: 'Full Name': (month_number, year)
    print("\n2️⃣ Getting each rep's start date from hardcoded data...")
    
    # HARDCODED START DATES - Manually update this when new employees join
    # These are the actual first day in Colppy (from INGRESOS tables), NOT first deal date
    # All deal data comes from HubSpot API (fetched below)
    SALES_REP_START_DATES = {
        # INGRESOS 2024
        'Karina Lorena Russo': (9, 2024),   # September 2024
        'Rocio Luque': (4, 2024),           # April 2024
        
        # INGRESOS 2025
        'Estefania Sol Arregui': (3, 2025),  # March 2025
        'Estefanía Sol Arregui': (3, 2025),  # Alternate spelling (with accent)
        'Tatiana Amaya': (7, 2025),          # July 2025
        'Jair Josue Calas': (9, 2025),       # September 2025
        'Jair Calás': (9, 2025),             # Alternate spelling (with accent)
    }
    
    rep_starts = {}
    for rep_name, owner_id in owner_name_to_id.items():
        # Check if rep has a start date in the hardcoded array
        if rep_name in SALES_REP_START_DATES:
            rep_starts[rep_name] = SALES_REP_START_DATES[rep_name]
            month, year = SALES_REP_START_DATES[rep_name]
            print(f"  ✓ Found start date for {rep_name}: {month}/{year}")
        else:
            # Try name normalization for matching (handles accents/variations)
            rep_name_normalized = normalize_name(rep_name)
            found = False
            for stored_name, start_date in SALES_REP_START_DATES.items():
                if normalize_name(stored_name) == rep_name_normalized:
                    rep_starts[rep_name] = start_date
                    month, year = start_date
                    print(f"  ✓ Found start date for {rep_name} (matched {stored_name}): {month}/{year}")
                    found = True
                    break
            
            if not found:
                # Skip reps not in hardcoded list (they haven't started yet or need to be added manually)
                print(f"  ⚠️  No start date found for {rep_name}. Add to SALES_REP_START_DATES array. Skipping.")
                continue
    
    # Filter out reps with no deals (they haven't started yet)
    rep_starts = {k: v for k, v in rep_starts.items() if v is not None}
    
    if not rep_starts:
        print("❌ Error: No reps with deals found. Exiting.")
        return
    
    # Find the earliest start date to determine date range
    earliest_date = min(rep_starts.values(), key=lambda x: (x[1], x[0]))
    latest_year = 2025  # Current year
    
    print(f"\n📅 Date range: Reps started from {earliest_date[0]}/{earliest_date[1]} to present")
    
    # Fetch deals from the earliest rep start date (but at minimum from June 2024 as requested)
    # We'll fetch from earliest rep start or June 2024, whichever is earlier for complete cohort view
    fetch_start_month = min(earliest_date[0], 6)  # June is month 6
    fetch_start_year = min(earliest_date[1], 2024)
    
    if earliest_date[1] < 2024 or (earliest_date[1] == 2024 and earliest_date[0] < 6):
        # Reps started before June 2024, fetch from their actual start
        start_date = f"{earliest_date[1]}-{earliest_date[0]:02d}-01"
        print(f"📅 Analysis period: {start_date} to December {latest_year} (from earliest rep start)")
    else:
        # All reps started June 2024 or later
        start_date = "2024-06-01"
        print(f"📅 Analysis period: June 2024 to December {latest_year}")
    
    end_date = f"{latest_year}-12-31"
    
    # 3. Fetch closed won deals from earliest start through end of 2025
    print("\n3️⃣ Fetching closed won deals from HubSpot...")
    deals = fetch_closed_won_deals(start_date, end_date, client)
    
    if not deals:
        print("❌ Error: No deals fetched. Exiting.")
        return
    
    # 4. Calculate cohort data
    print("\n4️⃣ Calculating cohort data (including collaborators)...")
    df = calculate_cohort_data(deals, rep_starts, owner_name_to_id, client)
    
    if df.empty:
        print("❌ Error: No cohort data calculated. Exiting.")
        return
    
    # Save raw data to CSV
    csv_output_path = os.path.join(OUTPUT_DIR, 'sales_ramp_cohort_data.csv')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df.to_csv(csv_output_path, index=False)
    print(f"✅ Cohort data saved to: {csv_output_path}")
    
    # Create and print deals per month table
    print("\n6️⃣ Creating deals per month table...")
    deals_table = create_deals_per_month_table(
        deals, rep_starts, owner_name_to_id, client,
        start_year=2024, end_year=latest_year
    )
    print_markdown_table(deals_table, start_year=2024, end_year=latest_year)
    
    # Save table to CSV
    table_csv_path = os.path.join(OUTPUT_DIR, 'deals_per_rep_per_month.csv')
    deals_table.to_csv(table_csv_path, index=False)
    print(f"✅ Deals per month table saved to: {table_csv_path}")
    
    # 7. Show Karina's December 2025 deals as example
    print("\n7️⃣ Analyzing Karina's December 2025 deals (Cohort Month 15)...")
    karina_deals_dec_2025 = get_deals_for_rep_month(
        deals, rep_starts, owner_name_to_id, 
        "Karina Lorena Russo", 12, 2025, client
    )
    if karina_deals_dec_2025:
        print(f"\n✅ Found {len(karina_deals_dec_2025)} deal(s) for Karina in December 2025:")
        owner_count = sum(1 for d in karina_deals_dec_2025 if d['is_owner'])
        collab_count = sum(1 for d in karina_deals_dec_2025 if d['is_collaborator'])
        print(f"   - As Owner: {owner_count}")
        print(f"   - As Collaborator: {collab_count}")
        for i, deal_info in enumerate(karina_deals_dec_2025[:5], 1):  # Show first 5
            print(f"\n{i}. Deal: {deal_info['deal_name']} (${deal_info['amount']})")
            print(f"   Owner: {deal_info['owner_name']}")
            print(f"   Karina is Owner: {'✅ YES' if deal_info['is_owner'] else '❌ NO'}")
            print(f"   Karina is Collaborator: {'✅ YES' if deal_info['is_collaborator'] else '❌ NO'}")
            if deal_info['collaborator_names']:
                print(f"   All Collaborators: {', '.join(deal_info['collaborator_names'])}")
        if len(karina_deals_dec_2025) > 5:
            print(f"\n   ... and {len(karina_deals_dec_2025) - 5} more deals")
    else:
        print("❌ No deals found for Karina in December 2025")
    
    # 8. Show Rocio's December 2025 deals as example (Month 20 for Rocio)
    print("\n8️⃣ Analyzing Rocio's December 2025 deals (Cohort Month 20)...")
    rocio_deals_dec_2025 = get_deals_for_rep_month(
        deals, rep_starts, owner_name_to_id, 
        "Rocio Luque", 12, 2025, client
    )
    if rocio_deals_dec_2025:
        print(f"\n✅ Found {len(rocio_deals_dec_2025)} deal(s) for Rocio in December 2025:")
        owner_count = sum(1 for d in rocio_deals_dec_2025 if d['is_owner'])
        collab_count = sum(1 for d in rocio_deals_dec_2025 if d['is_collaborator'])
        print(f"   - As Owner: {owner_count} (should match total - Closers only count as owner)")
        print(f"   - As Collaborator: {collab_count} (should be 0 for Closers)")
        for i, deal_info in enumerate(rocio_deals_dec_2025[:5], 1):  # Show first 5
            print(f"\n{i}. Deal: {deal_info['deal_name']} (${deal_info['amount']})")
            print(f"   Owner: {deal_info['owner_name']}")
            print(f"   Rocio is Owner: {'✅ YES' if deal_info['is_owner'] else '❌ NO'}")
            print(f"   Rocio is Collaborator: {'✅ YES' if deal_info['is_collaborator'] else '❌ NO'}")
            if deal_info['collaborator_names']:
                print(f"   All Collaborators: {', '.join(deal_info['collaborator_names'])}")
        if len(rocio_deals_dec_2025) > 5:
            print(f"\n   ... and {len(rocio_deals_dec_2025) - 5} more deals")
    else:
        print("❌ No deals found for Rocio in December 2025")
    
    # 5. Create cohort grid table and visualization (auto-detect max months)
    print("\n5️⃣ Creating cohort grid table...")
    cohort_grid = create_cohort_grid_table(deals, rep_starts, owner_name_to_id, client, max_months=None)
    
    # Print cohort grid as markdown table
    print("\n" + "=" * 100)
    print("COHORT ANALYSIS - DEALS CLOSED BY MONTH FROM START")
    print("Month 0 = First month (start month), Month 1 = Second month, etc.")
    print("=" * 100 + "\n")
    
    # Create markdown table - show first 25 months for display, full data in CSV
    columns = ['MES'] + [col for col in cohort_grid.columns if col != 'MES']
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join([" --- " for _ in columns]) + "|"
    print(header)
    print(separator)
    
    # Display first 25 months for readability, but save all to CSV
    display_rows = cohort_grid.head(25)
    for _, row in display_rows.iterrows():
        values = [str(int(row['MES']))]
        for col in columns[1:]:
            val = row.get(col)
            if pd.isna(val) or val == 0:
                values.append("—")  # Use em dash for empty/gray cells
            else:
                values.append(str(int(val)))
        print("| " + " | ".join(values) + " |")
    
    total_rows = len(cohort_grid)
    if total_rows > 25:
        print(f"\n... (showing first 25 of {total_rows} months - see CSV for full data)")
    
    print("\n" + "=" * 100)
    
    # Save cohort grid to CSV
    grid_csv_path = os.path.join(OUTPUT_DIR, 'cohort_grid_table.csv')
    cohort_grid.to_csv(grid_csv_path, index=False)
    print(f"✅ Cohort grid table saved to: {grid_csv_path}")
    
    # Create cohort grid visualization (heatmap)
    print("\n6️⃣ Creating cohort grid visualization...")
    grid_viz_path = os.path.join(OUTPUT_DIR, 'cohort_grid_visualization.png')
    create_cohort_grid_visualization(cohort_grid, grid_viz_path, rep_starts)
    
    # Also create the line chart visualization
    print("\n7️⃣ Creating cohort line chart visualization...")
    viz_output_path = os.path.join(OUTPUT_DIR, 'sales_ramp_cohort_analysis.png')
    create_cohort_visualization(df, viz_output_path, rep_starts)
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ Analysis Complete!")
    print("=" * 60)
    print(f"📊 Processed {len(deals)} closed won deals")
    print(f"👥 Analyzed {len(rep_starts)} sales reps")
    print(f"📈 Generated cohort data for {len(df)} rep-month combinations")
    print(f"💾 Output files:")
    print(f"   - CSV: {csv_output_path}")
    print(f"   - Visualization: {viz_output_path}")


if __name__ == "__main__":
    main()

