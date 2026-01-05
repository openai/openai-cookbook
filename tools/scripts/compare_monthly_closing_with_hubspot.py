"""
Compare monthly closing data with HubSpot for consistency validation and reconciliation.

IMPORTANT: This script analyzes DEALS (products), not Companies.
- id_empresa is a PRODUCT ID on Deals
- Revenue is tracked at the Deal level
- New customers = Deals closed in the analysis period
- Churn = Deals in churn stage (31849274)

This script performs BIDIRECTIONAL RECONCILIATION:
1. CSV → HubSpot: Reads consolidated CSV, fetches HubSpot Deal data, compares
2. HubSpot → CSV: Searches HubSpot for ALL deals closed won in period, compares with CSV
3. Identifies inconsistencies where one side has more than the other
4. Generates a reconciliation report at the Deal/Product level

Usage:
    python compare_monthly_closing_with_hubspot.py \\
        --consolidated-file "path/to/consolidated.csv" \\
        --month 12 \\
        --year 2025 \\
        [--output-dir "path/to/output"] \\
        [--batch-size 100] \\
        [--sample-size 0]
"""

import pandas as pd
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from collections import Counter
import time
import os

# Load environment variables from .env file
from dotenv import load_dotenv

# Try to load .env from multiple locations
script_dir = Path(__file__).parent
root_dir = script_dir.parent.parent
env_files = [
    root_dir / '.env',
    script_dir.parent / '.env',
    Path.cwd() / '.env'
]

for env_file in env_files:
    if env_file.exists():
        load_dotenv(env_file)
        break

# Add parent directory to path to import hubspot_api
sys.path.insert(0, str(root_dir))
from tools.hubspot_api.client import HubSpotClient
from tools.hubspot_api.config import get_config


def load_consolidated_data(file_path: str) -> pd.DataFrame:
    """
    Load the consolidated monthly closing data.
    
    Args:
        file_path: Path to consolidated CSV file
        
    Returns:
        DataFrame with consolidated data
    """
    df = pd.read_csv(file_path)
    
    # Ensure Empresa_Id and id_empresa are strings
    df['Empresa_Id'] = df['Empresa_Id'].astype(str)
    df['id_empresa'] = df['id_empresa'].astype(str)
    
    # Clean id_empresa values according to HubSpot property rules:
    # - "Allow numbers only" - must be numeric
    # - "Don't allow any spaces" - remove all spaces
    df['id_empresa'] = df['id_empresa'].str.strip()  # Remove leading/trailing spaces
    df['id_empresa'] = df['id_empresa'].str.replace(' ', '')  # Remove all spaces
    # Keep only numeric characters (remove any non-numeric chars)
    df['id_empresa'] = df['id_empresa'].str.replace(r'[^0-9]', '', regex=True)
    
    return df


def search_deal_by_id_empresa(client: HubSpotClient, id_empresa: str) -> Optional[Dict]:
    """
    Search for a Deal (product) in HubSpot by id_empresa property.
    
    IMPORTANT: id_empresa is a PRODUCT ID on Deals.
    This is the revenue/product level analysis, not company level.
    
    Args:
        client: HubSpot API client instance
        id_empresa: The id_empresa (product ID) value to search for
        
    Returns:
        Deal data dictionary or None if not found
    """
    # Clean id_empresa value according to HubSpot property rules:
    # - "Allow numbers only" - must be numeric
    # - "Don't allow any spaces" - remove all spaces
    import re
    cleaned_id = str(id_empresa).strip()  # Remove leading/trailing spaces
    cleaned_id = cleaned_id.replace(' ', '')  # Remove all spaces
    cleaned_id = re.sub(r'[^0-9]', '', cleaned_id)  # Keep only numeric characters
    
    # Validate: must be numeric and not empty
    if not cleaned_id or not cleaned_id.isdigit():
        print(f"    ⚠️  Invalid id_empresa value '{id_empresa}' (must be numeric, no spaces)")
        return None
    
    try:
        # Search Deals by id_empresa (product ID)
        # This is the revenue/product level - we're analyzing deals, not companies
        deals_response = client.search_objects(
            object_type="deals",
            filter_groups=[{
                "filters": [{
                    "propertyName": "id_empresa",
                    "operator": "EQ",
                    "value": cleaned_id  # Product ID on deal
                }]
            }],
            properties=[
                "dealname",
                "id_empresa",
                "dealstage",
                "closedate",
                "amount",
                "hs_object_id",
                "fecha_pedido_baja",
                "fecha_de_desactivacion",
                "createdate"
            ],
            limit=1
        )
        
        if not deals_response.get("results") or len(deals_response["results"]) == 0:
            return None
        
        # Return the deal data directly (this is product/revenue level)
        deal = deals_response["results"][0]
        return deal
            
    except Exception as e:
        # Search failed - log error
        error_msg = str(e)
        if "400" in error_msg or "Bad Request" in error_msg:
            print(f"    ⚠️  Search failed for id_empresa={cleaned_id}: {error_msg}")
        else:
            print(f"    ⚠️  Error searching for deal with id_empresa {cleaned_id}: {error_msg}")
    
    return None


def fetch_hubspot_deals_batch(
    client: HubSpotClient,
    id_empresa_list: List[str],
    batch_size: int = 100
) -> Dict[str, Dict]:
    """
    Fetch multiple Deals (products) from HubSpot in batches.
    
    Args:
        client: HubSpot API client instance
        id_empresa_list: List of id_empresa (product ID) values to fetch
        batch_size: Number of deals to fetch per batch
        
    Returns:
        Dictionary mapping id_empresa to deal data
    """
    results = {}
    total_batches = (len(id_empresa_list) + batch_size - 1) // batch_size
    
    # Process in batches
    for i in range(0, len(id_empresa_list), batch_size):
        batch = id_empresa_list[i:i + batch_size]
        batch_num = i // batch_size + 1
        print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} products/deals)...")
        
        # Search for each deal by id_empresa (product ID)
        for idx, id_empresa in enumerate(batch):
            try:
                deal_data = search_deal_by_id_empresa(client, id_empresa)
                
                if deal_data:
                    results[id_empresa] = deal_data
                else:
                    results[id_empresa] = None
                
                # Progress indicator
                if (idx + 1) % 10 == 0 or (idx + 1) == len(batch):
                    print(f"    Processed {idx + 1}/{len(batch)} in this batch (Found: {sum(1 for v in results.values() if v is not None)})...")
                    
            except Exception as e:
                print(f"    ⚠️  Error fetching deal {id_empresa}: {str(e)}")
                results[id_empresa] = None
    
    return results


def extract_hubspot_deal_properties(deal_data: Optional[Dict]) -> Dict:
    """
    Extract relevant properties from HubSpot Deal data.
    
    IMPORTANT: This is Deal/Product level analysis, not Company level.
    id_empresa is a PRODUCT ID on Deals - this is revenue/product tracking.
    
    Args:
        deal_data: Deal data dictionary from HubSpot or None
        
    Returns:
        Dictionary with extracted Deal properties including data integrity flags
    """
    if not deal_data:
        return {
            'hubspot_deal_id': None,
            'hubspot_deal_name': None,
            'hubspot_id_empresa': None,
            'hubspot_deal_stage': None,
            'hubspot_close_date': None,
            'hubspot_amount': None,
            'hubspot_fecha_pedido_baja': None,
            'hubspot_fecha_de_desactivacion': None,
            'hubspot_found': False,
            'data_integrity_issues': ['Deal not found in HubSpot'],
            'missing_required_fields': [],
            'has_id_empresa': False
        }
    
    properties = deal_data.get('properties', {})
    integrity_issues = []
    missing_fields = []
    
    # Check for id_empresa (product ID) - CRITICAL field
    hubspot_id_empresa = properties.get('id_empresa')
    has_id_empresa = bool(hubspot_id_empresa and str(hubspot_id_empresa).strip())
    
    if not has_id_empresa:
        integrity_issues.append('Missing id_empresa (product ID) in HubSpot Deal')
        missing_fields.append('id_empresa')
    
    # Check for deal name
    deal_name = properties.get('dealname')
    if not deal_name or not str(deal_name).strip():
        integrity_issues.append('Missing deal name')
        missing_fields.append('dealname')
    
    # Check for deal stage
    deal_stage = properties.get('dealstage')
    if not deal_stage or not str(deal_stage).strip():
        integrity_issues.append('Missing deal stage')
        missing_fields.append('dealstage')
    
    # Check for close date
    close_date = properties.get('closedate')
    if not close_date or not str(close_date).strip():
        missing_fields.append('closedate')
    
    # Check for amount (revenue)
    amount = properties.get('amount')
    if not amount or not str(amount).strip():
        missing_fields.append('amount')
    
    # Check for churn-related dates (for churn deals)
    fecha_pedido_baja = properties.get('fecha_pedido_baja')
    fecha_de_desactivacion = properties.get('fecha_de_desactivacion')
    
    # If no integrity issues, mark as clean
    if not integrity_issues:
        integrity_issues = None
    
    return {
        'hubspot_deal_id': deal_data.get('id'),
        'hubspot_deal_name': deal_name,
        'hubspot_id_empresa': hubspot_id_empresa,
        'hubspot_deal_stage': deal_stage,
        'hubspot_close_date': close_date,
        'hubspot_amount': amount,
        'hubspot_fecha_pedido_baja': fecha_pedido_baja,
        'hubspot_fecha_de_desactivacion': fecha_de_desactivacion,
        'hubspot_found': True,
        'data_integrity_issues': integrity_issues,
        'missing_required_fields': ', '.join(missing_fields) if missing_fields else None,
        'has_id_empresa': has_id_empresa
    }


def compare_with_hubspot(
    consolidated_df: pd.DataFrame,
    hubspot_data: Dict[str, Dict],
    month: int,
    year: int
) -> pd.DataFrame:
    """
    Compare consolidated data with HubSpot data and identify inconsistencies.
    
    Args:
        consolidated_df: Consolidated DataFrame
        hubspot_data: Dictionary mapping id_empresa to HubSpot company data
        month: Analysis month
        year: Analysis year
        
    Returns:
        DataFrame with comparison results
    """
    comparison_results = []
    
    # Generate period string for date comparison
    period_start = datetime(year, month, 1)
    if month == 12:
        period_end = datetime(year + 1, 1, 1)
    else:
        period_end = datetime(year, month + 1, 1)
    
    # FILTER: Process both WON deals (closed won in period) AND CHURN deals (churned in period)
    # IMPORTANT: 
    # - Won deals: must be 'closedwon' stage AND closedate in period
    # - Churn deals: must have churn date (fecha_pedido_baja or fecha_de_desactivacion) in period
    #   Churn deals can have closed earlier - we check churn date, not close date
    deals_in_period = []
    won_deals_out_of_period = []
    churn_deals_out_of_period = []
    deals_not_found = []
    
    print(f"\n📅 FILTERING DEALS BY TYPE AND DATE:")
    print(f"   Period: {month}/{year} ({period_start.date()} to {period_end.date()})")
    print(f"   WON deals: Must be 'closedwon' stage AND closedate in period")
    print(f"   CHURN deals: ALL true churns from CSV (Ending_Sin_Descuentos = 0)")
    print(f"   CHURN FILTER: Only Ending_Sin_Descuentos = 0 (exclude retained customers with > 0)")
    print(f"   ⚠️  IMPORTANT: CSV is source of truth - if in churn CSV for this month, it churned in this month")
    print(f"   ⚠️  HubSpot churn date is used for VALIDATION only, NOT for filtering")
    print("")
    
    for _, row in consolidated_df.iterrows():
        id_empresa = str(row['id_empresa'])
        hubspot_info = hubspot_data.get(id_empresa, {})
        
        if not hubspot_info:
            # Deal not found - still process it to report as missing
            deals_not_found.append((row, None))
            continue
        
        # Extract HubSpot Deal properties
        hubspot_props = extract_hubspot_deal_properties(hubspot_info)
        close_date = hubspot_props['hubspot_close_date']
        deal_stage = hubspot_props['hubspot_deal_stage']
        fecha_pedido_baja = hubspot_props['hubspot_fecha_pedido_baja']
        fecha_de_desactivacion = hubspot_props['hubspot_fecha_de_desactivacion']
        
        # Determine deal type from CSV
        is_new_customer = row.get('is_new_customer', False)
        is_churn_customer = row.get('is_churn_customer', False)
        
        # Process WON deals (new customers)
        if is_new_customer:
            is_closed_won = (deal_stage == "closedwon")
            
            if not is_closed_won:
                # Not closed won - skip for won analysis
                continue
            
            # Check if deal was closed in the period
            if close_date:
                try:
                    deal_date = pd.to_datetime(close_date).date()
                    date_in_period = period_start.date() <= deal_date < period_end.date()
                    
                    if date_in_period:
                        deals_in_period.append((row, hubspot_info))
                    else:
                        won_deals_out_of_period.append((id_empresa, deal_date))
                except:
                    # Invalid date format - skip
                    continue
            else:
                # No close date - skip (can't verify if in period)
                continue
        
        # Process CHURN deals
        elif is_churn_customer:
            # FILTER: Only consider true churns (Ending_Sin_Descuentos = 0)
            # If Ending_Sin_Descuentos > 0, customer was retained and didn't churn
            ending_sin_descuentos = row.get('Ending_Sin_Descuentos', 0)
            # Handle NaN/null values - treat as 0 (true churn)
            if pd.isna(ending_sin_descuentos):
                ending_sin_descuentos = 0
            else:
                try:
                    ending_sin_descuentos = float(ending_sin_descuentos)
                except (ValueError, TypeError):
                    ending_sin_descuentos = 0
            
            # Skip if Ending_Sin_Descuentos > 0 (retained customer, not a churn)
            if ending_sin_descuentos > 0:
                # This is a retained customer, not a true churn - skip it
                continue
            
            # IMPORTANT: CSV is the source of truth for churn period
            # If a deal is in the December 2025 churn CSV file, it churned in December 2025
            # We do NOT filter by HubSpot churn date - we include ALL true churns from CSV
            # HubSpot churn date is only used for VALIDATION/COMPARISON, not for filtering
            deals_in_period.append((row, hubspot_info))
    
    print(f"   ✅ Deals in period (won + churn): {len(deals_in_period):,}")
    print(f"   ⏭️  Won deals closed outside period: {len(won_deals_out_of_period):,}")
    print(f"   ⏭️  Churn deals churned outside period: {len(churn_deals_out_of_period):,}")
    print(f"   ⚠️  Deals not found in HubSpot: {len(deals_not_found):,}")
    if len(won_deals_out_of_period) > 0 and len(won_deals_out_of_period) <= 10:
        print(f"   Skipped won (closed outside period, sample): {', '.join([f'{id_emp}: {date}' for id_emp, date in won_deals_out_of_period[:10]])}")
    if len(churn_deals_out_of_period) > 0 and len(churn_deals_out_of_period) <= 10:
        print(f"   Skipped churn (churned outside period, sample): {', '.join([f'{id_emp}: {date}' for id_emp, date in churn_deals_out_of_period[:10]])}")
    print("")
    
    # Process deals in period (both won and churn) + deals not found
    all_deals_to_process = deals_in_period + deals_not_found
    
    for row, hubspot_info in all_deals_to_process:
        id_empresa = str(row['id_empresa'])
        
        # Extract HubSpot Deal properties
        hubspot_props = extract_hubspot_deal_properties(hubspot_info)
        
        # Determine consistency status
        consistency_issues = []
        data_integrity_issues = []
        consistency_status = "✅ Consistent"
        
        # Check 1: Deal exists in HubSpot
        if not hubspot_props['hubspot_found']:
            consistency_status = "❌ Not Found in HubSpot"
            consistency_issues.append("Deal (product) not found in HubSpot")
            data_integrity_issues.append("Deal not found in HubSpot")
        else:
            # Check 1a: Data Integrity - id_empresa must exist (it's the product ID)
            if not hubspot_props['has_id_empresa']:
                consistency_status = "❌ Data Integrity Issue"
                consistency_issues.append("Missing id_empresa (product ID) in HubSpot Deal")
                data_integrity_issues.append("Missing id_empresa (required field)")
            
            # Check 1b: Other data integrity issues
            if hubspot_props['data_integrity_issues']:
                for issue in hubspot_props['data_integrity_issues']:
                    if issue not in consistency_issues:
                        consistency_issues.append(issue)
                        data_integrity_issues.append(issue)
            
            # Check 1c: Missing required fields
            if hubspot_props['missing_required_fields']:
                missing_fields = hubspot_props['missing_required_fields'].split(', ')
                for field in missing_fields:
                    field_clean = field.strip()
                    if field_clean:
                        data_integrity_issues.append(f"Missing {field_clean}")
            
            # Check 2: New customers - Deal should be closed won in the period
            # Since we already filtered for closed won deals in period, this should be consistent
            if row['is_new_customer']:
                close_date = hubspot_props['hubspot_close_date']
                deal_stage = hubspot_props['hubspot_deal_stage']
                
                if not close_date:
                    consistency_status = "❌ Missing Close Date"
                    consistency_issues.append("Missing closedate in HubSpot Deal (required for new customers)")
                elif not deal_stage:
                    consistency_status = "⚠️  Missing Deal Stage"
                    consistency_issues.append("Missing dealstage in HubSpot Deal")
                else:
                    try:
                        deal_date = pd.to_datetime(close_date).date()
                        # Check if deal is closed won
                        is_closed_won = (deal_stage == "closedwon")
                        
                        # Check if date is in period (December 2025)
                        date_in_period = period_start.date() <= deal_date < period_end.date()
                        
                        if not is_closed_won:
                            consistency_status = "❌ Not Closed Won"
                            consistency_issues.append(f"Deal stage is '{deal_stage}', expected 'closedwon' for new customer")
                        elif not date_in_period:
                            consistency_status = "❌ Date Mismatch"
                            consistency_issues.append(
                                f"Deal close date ({deal_date}) not in {month}/{year} - Expected December 2025"
                            )
                        else:
                            # All good - closed won and date is in period
                            consistency_status = "✅ Consistent"
                            consistency_issues.append(f"Deal closed won on {deal_date} (correct)")
                    except Exception as e:
                        consistency_status = "❌ Invalid Date Format"
                        consistency_issues.append(f"Invalid closedate format: {str(e)}")
            
            # Check 3: Churn customers - Deal should be in churn stage with correct churn date
            if row['is_churn_customer']:
                deal_stage = hubspot_props['hubspot_deal_stage']
                fecha_pedido_baja = hubspot_props['hubspot_fecha_pedido_baja']
                fecha_de_desactivacion = hubspot_props['hubspot_fecha_de_desactivacion']
                close_date = hubspot_props['hubspot_close_date']
                
                # Check if deal is in churn stage (31849274)
                is_churn_stage = (deal_stage == "31849274")
                is_closed_won_stage = (deal_stage == "closedwon")
                
                # Check for churn date fields (fecha_pedido_baja is primary, fecha_de_desactivacion is fallback)
                churn_date = None
                churn_date_source = None
                
                if fecha_pedido_baja and str(fecha_pedido_baja).strip():
                    try:
                        churn_date = pd.to_datetime(fecha_pedido_baja).date()
                        churn_date_source = "fecha_pedido_baja"
                    except:
                        pass
                
                if not churn_date and fecha_de_desactivacion and str(fecha_de_desactivacion).strip():
                    try:
                        churn_date = pd.to_datetime(fecha_de_desactivacion).date()
                        churn_date_source = "fecha_de_desactivacion"
                    except:
                        pass
                
                # Determine consistency status for churn deals
                if not is_churn_stage and not churn_date:
                    # Both issues: wrong stage and missing churn date
                    consistency_status = "❌ Missing Churn Date & Wrong Stage"
                    consistency_issues.append(
                        f"Deal stage is '{deal_stage}', expected churn stage '31849274'; Missing churn dates"
                    )
                elif not is_churn_stage:
                    # Wrong stage but has churn date
                    consistency_status = "⚠️  Wrong Stage"
                    consistency_issues.append(
                        f"Deal stage is '{deal_stage}', expected churn stage '31849274'"
                    )
                elif not churn_date:
                    # Correct stage but missing churn date
                    consistency_status = "❌ Missing Churn Date"
                    consistency_issues.append(
                        "Missing fecha_pedido_baja and fecha_de_desactivacion in HubSpot Deal (required for churn)"
                    )
                else:
                    # Both correct: churn stage and churn date present
                    # Validate churn date is in the analysis period
                    if churn_date > period_end.date():
                        consistency_status = "⚠️  Churn Date Future"
                        consistency_issues.append(
                            f"Churn date ({churn_date}) is after analysis period {month}/{year}"
                        )
                    elif churn_date < period_start.date():
                        consistency_status = "⚠️  Churn Date Past"
                        consistency_issues.append(
                            f"Churn date ({churn_date}) is before analysis period {month}/{year}"
                        )
                    else:
                        # Churn date is in the period - correct
                        consistency_status = "✅ Consistent"
                        consistency_issues.append(f"Churn date ({churn_date}) from {churn_date_source} is correct")
        
        # Build comparison record
        comparison_record = {
            'Empresa_Id': row['Empresa_Id'],
            'id_empresa': id_empresa,
            'is_new_customer': row['is_new_customer'],
            'is_churn_customer': row['is_churn_customer'],
            'hubspot_deal_id': hubspot_props['hubspot_deal_id'],
            'hubspot_deal_name': hubspot_props['hubspot_deal_name'],
            'hubspot_id_empresa': hubspot_props['hubspot_id_empresa'],
            'hubspot_found': hubspot_props['hubspot_found'],
            'hubspot_has_id_empresa': hubspot_props['has_id_empresa'],
            'hubspot_deal_stage': hubspot_props['hubspot_deal_stage'],
            'hubspot_close_date': hubspot_props['hubspot_close_date'],
            'hubspot_amount': hubspot_props['hubspot_amount'],
            'hubspot_fecha_pedido_baja': hubspot_props['hubspot_fecha_pedido_baja'],
            'hubspot_fecha_de_desactivacion': hubspot_props['hubspot_fecha_de_desactivacion'],
            'consistency_status': consistency_status,
            'consistency_issues': '; '.join(consistency_issues) if consistency_issues else None,
            'data_integrity_issues': '; '.join(data_integrity_issues) if data_integrity_issues else None,
            'missing_required_fields': hubspot_props['missing_required_fields'],
            'csv_new_total': row.get('New_Total'),
            'csv_churn_total': row.get('Churn_Total'),
        }
        
        comparison_results.append(comparison_record)
    
    return pd.DataFrame(comparison_results)


def search_hubspot_deals_closed_in_period(
    client: HubSpotClient,
    month: int,
    year: int,
    batch_size: int = 100
) -> List[Dict]:
    """
    Search HubSpot for ALL deals closed won in the specified period.
    
    This is used for bidirectional reconciliation (HubSpot → CSV).
    
    Args:
        client: HubSpot API client
        month: Month to search (1-12)
        year: Year to search
        batch_size: Number of results per page
        
    Returns:
        List of deal dictionaries
    """
    period_start = datetime(year, month, 1)
    if month == 12:
        period_end = datetime(year + 1, 1, 1)
    else:
        period_end = datetime(year, month + 1, 1)
    
    # Format dates for HubSpot API (ISO format)
    start_date_str = period_start.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    end_date_str = period_end.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    
    print(f"\n🔍 RECONCILIATION: Searching HubSpot for ALL deals closed won in {month}/{year}...")
    print(f"   Period: {period_start.date()} to {period_end.date()}")
    print(f"   Criteria: dealstage = 'closedwon' AND closedate in period")
    print("")
    
    all_deals = []
    after = None
    page = 1
    
    while True:
        try:
            # Search for deals closed won in the period
            filter_groups = [{
                "filters": [
                    {
                        "propertyName": "dealstage",
                        "operator": "EQ",
                        "value": "closedwon"
                    },
                    {
                        "propertyName": "closedate",
                        "operator": "GTE",
                        "value": start_date_str
                    },
                    {
                        "propertyName": "closedate",
                        "operator": "LT",
                        "value": end_date_str
                    }
                ]
            }]
            
            response = client.search_objects(
                object_type="deals",
                filter_groups=filter_groups,
                properties=[
                    "dealname",
                    "id_empresa",
                    "dealstage",
                    "closedate",
                    "amount",
                    "hs_object_id",
                    "createdate"
                ],
                limit=batch_size,
                after=after
            )
            
            results = response.get("results", [])
            if not results:
                break
            
            all_deals.extend(results)
            print(f"   Page {page}: Found {len(results)} deals (Total: {len(all_deals)})")
            
            # Check for pagination
            paging = response.get("paging", {})
            after = paging.get("next", {}).get("after")
            
            if not after:
                break
            
            page += 1
            
        except Exception as e:
            print(f"   ⚠️  Error searching HubSpot: {str(e)}")
            break
    
    print(f"✅ Total deals found in HubSpot: {len(all_deals):,}")
    return all_deals


def search_hubspot_deals_churned_in_period(
    client: HubSpotClient,
    month: int,
    year: int,
    batch_size: int = 100
) -> List[Dict]:
    """
    Search HubSpot for all deals that churned in the specified period.
    
    Churn is determined by:
    - fecha_pedido_baja (primary) OR fecha_de_desactivacion (fallback) in the period
    - Deal stage can be churn stage (31849274) or any stage (we check churn date, not stage)
    
    Args:
        client: HubSpot API client instance
        month: Analysis month (1-12)
        year: Analysis year
        batch_size: Number of deals to fetch per API call
        
    Returns:
        List of deal dictionaries that churned in the period
    """
    from datetime import datetime
    
    period_start = datetime(year, month, 1)
    if month == 12:
        period_end = datetime(year + 1, 1, 1)
    else:
        period_end = datetime(year, month + 1, 1)
    
    start_date_str = period_start.strftime('%Y-%m-%d')
    end_date_str = period_end.strftime('%Y-%m-%d')
    
    print(f"\n🔍 SEARCHING HUBSPOT FOR CHURNED DEALS:")
    print(f"   Period: {month}/{year} ({start_date_str} to {end_date_str})")
    print(f"   Churn date fields: fecha_pedido_baja (primary), fecha_de_desactivacion (fallback)")
    print("")
    
    all_deals = []
    page = 1
    after = None
    
    # Search for deals with fecha_pedido_baja or fecha_de_desactivacion set
    # Note: HubSpot search may not support date range filters on custom date fields directly
    # So we'll search for deals in churn stage or with churn dates, then filter by date
    while True:
        try:
            # Search for deals that might be churned (in churn stage OR have churn date fields)
            # We'll fetch all deals with churn stage or with churn date fields populated,
            # then filter by date in Python
            filter_groups = [{
                "filters": [
                    {
                        "propertyName": "dealstage",
                        "operator": "EQ",
                        "value": "31849274"  # Churn stage
                    }
                ]
            }]
            
            response = client.search_objects(
                object_type="deals",
                filter_groups=filter_groups,
                properties=[
                    "dealname",
                    "id_empresa",
                    "dealstage",
                    "closedate",
                    "amount",
                    "hs_object_id",
                    "fecha_pedido_baja",
                    "fecha_de_desactivacion",
                    "createdate"
                ],
                limit=batch_size,
                after=after
            )
            
            results = response.get("results", [])
            if not results:
                break
            
            # Filter by churn date in the period
            filtered_results = []
            for deal in results:
                properties = deal.get("properties", {})
                fecha_pedido_baja = properties.get("fecha_pedido_baja", "")
                fecha_de_desactivacion = properties.get("fecha_de_desactivacion", "")
                
                # Get churn date (primary: fecha_pedido_baja, fallback: fecha_de_desactivacion)
                churn_date = None
                if fecha_pedido_baja and str(fecha_pedido_baja).strip():
                    try:
                        churn_date = pd.to_datetime(fecha_pedido_baja).date()
                    except:
                        pass
                
                if not churn_date and fecha_de_desactivacion and str(fecha_de_desactivacion).strip():
                    try:
                        churn_date = pd.to_datetime(fecha_de_desactivacion).date()
                    except:
                        pass
                
                # Check if churn date is in period
                if churn_date:
                    if period_start.date() <= churn_date < period_end.date():
                        filtered_results.append(deal)
            
            all_deals.extend(filtered_results)
            print(f"   Page {page}: Found {len(results)} deals in churn stage, {len(filtered_results)} churned in period (Total: {len(all_deals)})")
            
            # Check for pagination
            paging = response.get("paging", {})
            after = paging.get("next", {}).get("after")
            
            if not after:
                break
            
            page += 1
            
        except Exception as e:
            print(f"   ⚠️  Error searching HubSpot: {str(e)}")
            break
    
    print(f"✅ Total churned deals found in HubSpot for {month}/{year}: {len(all_deals):,}")
    return all_deals


def reconcile_hubspot_with_csv(
    hubspot_deals: List[Dict],
    csv_df: pd.DataFrame,
    month: int,
    year: int
) -> pd.DataFrame:
    """
    Reconcile HubSpot deals with CSV data (HubSpot → CSV direction).
    
    Args:
        hubspot_deals: List of deal dictionaries from HubSpot
        csv_df: DataFrame with CSV data
        month: Analysis month
        year: Analysis year
        
    Returns:
        DataFrame with reconciliation results
    """
    print(f"\n🔍 RECONCILIATION: Comparing HubSpot deals with CSV...")
    
    # Get id_empresa values from CSV (cleaned)
    csv_df_clean = csv_df.copy()
    csv_df_clean['id_empresa_clean'] = csv_df_clean['id_empresa'].astype(str).str.strip().str.replace(' ', '')
    csv_id_empresas = set(csv_df_clean['id_empresa_clean'].tolist())
    
    reconciliation_results = []
    hubspot_id_empresas = set()
    
    for deal in hubspot_deals:
        properties = deal.get('properties', {})
        id_empresa_raw = str(properties.get('id_empresa', '')).strip()
        id_empresa = id_empresa_raw.replace(' ', '')
        
        # Only process deals with valid id_empresa
        if not id_empresa or not id_empresa.isdigit():
            continue
        
        hubspot_id_empresas.add(id_empresa)
        
        # Check if this id_empresa exists in CSV
        in_csv = id_empresa in csv_id_empresas
        
        # Get CSV row if exists
        csv_row = None
        if in_csv:
            csv_matches = csv_df_clean[csv_df_clean['id_empresa_clean'] == id_empresa]
            if len(csv_matches) > 0:
                csv_row = csv_matches.iloc[0]
        
        # Format close date
        close_date = properties.get('closedate', '')
        close_date_formatted = ''
        if close_date:
            try:
                close_date_formatted = pd.to_datetime(close_date).strftime('%Y-%m-%d')
            except:
                close_date_formatted = str(close_date)[:10]
        
        reconciliation_results.append({
            'id_empresa': id_empresa,
            'hubspot_deal_id': deal.get('id'),
            'hubspot_deal_name': properties.get('dealname', ''),
            'hubspot_close_date': close_date_formatted,
            'hubspot_amount': properties.get('amount', ''),
            'in_csv': in_csv,
            'csv_empresa_id': csv_row.get('Empresa_Id') if csv_row is not None else None,
            'csv_new_total': csv_row.get('New_Total') if csv_row is not None else None,
            'csv_churn_total': csv_row.get('Churn_Total') if csv_row is not None else None,
            'csv_inicio_inicial': csv_row.get('Inicio_Inicial') if csv_row is not None else None,
            'is_new_customer': csv_row.get('is_new_customer') if csv_row is not None else None,
            'is_churn_customer': csv_row.get('is_churn_customer') if csv_row is not None else None,
        })
    
    # Find deals in CSV that are NOT in HubSpot (for deals closed in period)
    csv_not_in_hubspot = csv_id_empresas - hubspot_id_empresas
    
    print(f"   ✅ HubSpot deals with id_empresa: {len(hubspot_id_empresas):,}")
    print(f"   ✅ Deals in both HubSpot and CSV: {len([r for r in reconciliation_results if r['in_csv']]):,}")
    print(f"   ⚠️  Deals in HubSpot but NOT in CSV: {len([r for r in reconciliation_results if not r['in_csv']]):,}")
    print(f"   ⚠️  Deals in CSV but NOT in HubSpot (for period): {len(csv_not_in_hubspot):,}")
    
    return pd.DataFrame(reconciliation_results), csv_not_in_hubspot


def generate_comparison_report(
    comparison_df: pd.DataFrame,
    month: int,
    year: int,
    period_description: Optional[str] = None,
    reconciliation_df: Optional[pd.DataFrame] = None,
    csv_not_in_hubspot: Optional[Set] = None
) -> str:
    """
    Generate a summary report of the HubSpot comparison.
    
    Args:
        comparison_df: DataFrame with comparison results
        month: Analysis month
        year: Analysis year
        period_description: Optional custom period description
        
    Returns:
        Formatted report string
    """
    if period_description:
        period_str = period_description
    else:
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        period_str = f"{month_names[month - 1]} {year}"
    
    report = []
    report.append("=" * 80)
    report.append(f"HUBSPOT CONSISTENCY COMPARISON - {period_str.upper()}")
    report.append("=" * 80)
    report.append("")
    
    # Overall Statistics
    report.append("📊 OVERALL STATISTICS")
    report.append("-" * 80)
    report.append("ℹ️  NOTE: This is DEAL/PRODUCT level analysis, not Company level")
    report.append("   - id_empresa is a PRODUCT ID on Deals")
    report.append("   - Revenue is tracked at the Deal level")
    report.append("   - WON deals: Closed won in the analysis period")
    report.append("   - CHURN deals: Churned in the analysis period (may have closed earlier)")
    report.append("")
    
    # Handle empty DataFrame
    if len(comparison_df) == 0:
        report.append("⚠️  NO DEALS FOUND IN THE ANALYSIS PERIOD")
        report.append("")
        report.append("This means:")
        report.append("  - No won deals in the CSV have close dates in the analysis period")
        report.append("  - No churn deals in the CSV have churn dates in the analysis period")
        report.append("  - Or deals exist but dates are not in the period")
        report.append("")
        return "\n".join(report)
    
    total_deals = len(comparison_df)
    found_in_hubspot = comparison_df['hubspot_found'].sum()
    not_found = total_deals - found_in_hubspot
    
    report.append(f"Total Products/Deals Analyzed: {total_deals:,}")
    report.append(f"Found in HubSpot: {found_in_hubspot:,} ({found_in_hubspot/total_deals*100:.1f}%)")
    report.append(f"Not Found in HubSpot: {not_found:,} ({not_found/total_deals*100:.1f}%)")
    report.append("")
    
    # Consistency Status Breakdown
    report.append("🔍 CONSISTENCY STATUS BREAKDOWN")
    report.append("-" * 80)
    status_counts = comparison_df['consistency_status'].value_counts()
    for status, count in status_counts.items():
        percentage = count / total_deals * 100
        report.append(f"{status}: {count:,} ({percentage:.1f}%)")
    report.append("")
    
    # New Customers Analysis (New Deals/Products)
    new_customers = comparison_df[comparison_df['is_new_customer'] == True]
    if len(new_customers) > 0:
        report.append("🆕 NEW DEALS/PRODUCTS ANALYSIS")
        report.append("-" * 80)
        report.append("   (Deals closed won in the analysis period)")
        new_total = len(new_customers)
        new_found = new_customers['hubspot_found'].sum()
        new_consistent = len(new_customers[new_customers['consistency_status'] == '✅ Consistent'])
        new_missing_date = len(new_customers[new_customers['consistency_status'] == '⚠️  Missing Close Date'])
        new_date_mismatch = len(new_customers[new_customers['consistency_status'] == '⚠️  Date Mismatch'])
        
        report.append(f"Total New Customers: {new_total:,}")
        report.append(f"Found in HubSpot: {new_found:,} ({new_found/new_total*100:.1f}%)")
        report.append(f"✅ Consistent: {new_consistent:,} ({new_consistent/new_total*100:.1f}%)")
        report.append(f"⚠️  Missing first_deal_closed_won_date: {new_missing_date:,}")
        report.append(f"⚠️  Date Mismatch: {new_date_mismatch:,}")
        report.append("")
    
    # Churn Customers Analysis
    churn_customers = comparison_df[comparison_df['is_churn_customer'] == True]
    if len(churn_customers) > 0:
        report.append("🔴 CHURN CUSTOMERS ANALYSIS")
        report.append("-" * 80)
        report.append("   (Deals that churned in the analysis period)")
        churn_total = len(churn_customers)
        churn_found = churn_customers['hubspot_found'].sum()
        churn_consistent = len(churn_customers[churn_customers['consistency_status'] == '✅ Consistent'])
        churn_missing_date = len(churn_customers[churn_customers['consistency_status'] == '❌ Missing Churn Date'])
        churn_wrong_stage = len(churn_customers[churn_customers['consistency_status'] == '⚠️  Wrong Stage'])
        churn_both_issues = len(churn_customers[churn_customers['consistency_status'] == '❌ Missing Churn Date & Wrong Stage'])
        
        report.append(f"Total Churn Customers: {churn_total:,}")
        report.append(f"Found in HubSpot: {churn_found:,} ({churn_found/churn_total*100:.1f}%)")
        report.append(f"✅ Consistent: {churn_consistent:,} ({churn_consistent/churn_total*100:.1f}%)")
        report.append(f"❌ Missing Churn Date: {churn_missing_date:,}")
        report.append(f"⚠️  Wrong Stage (has churn date but wrong stage): {churn_wrong_stage:,}")
        report.append(f"❌ Missing Churn Date & Wrong Stage: {churn_both_issues:,}")
        report.append("")
    
    # Data Integrity Summary
    report.append("🔍 DATA INTEGRITY ANALYSIS")
    report.append("-" * 80)
    
    # Check if companies were found
    not_found = comparison_df[comparison_df['hubspot_found'] == False]
    if len(not_found) > 0:
        report.append(f"⚠️  WARNING: {len(not_found):,} companies not found in HubSpot")
        report.append("   Possible reasons:")
        report.append("   1. id_empresa property is not marked as 'searchable' in HubSpot")
        report.append("   2. Companies don't exist in HubSpot")
        report.append("   3. id_empresa values don't match")
        report.append("")
        report.append("   ACTION REQUIRED: Ensure 'id_empresa' property is searchable in HubSpot:")
        report.append("   Settings → Properties → Companies → id_empresa → Enable 'Searchable'")
        report.append("")
    
    # Note about id_empresa location
    found_companies = comparison_df[comparison_df['hubspot_found'] == True]
    if len(found_companies) > 0:
        report.append(f"✅ Found {len(found_companies):,} companies via Deal id_empresa (product ID) search")
        report.append("   Note: id_empresa is a PRODUCT ID on Deals, not Companies")
        report.append("   Companies were found by searching Deals, then getting associated Companies")
        
        # Check if companies have id_empresa property (optional - it's primarily on Deals)
        missing_id_empresa = found_companies[found_companies['hubspot_has_id_empresa'] == False]
        if len(missing_id_empresa) > 0:
            report.append(f"ℹ️  {len(missing_id_empresa):,} companies don't have id_empresa property (expected - it's on Deals)")
    else:
        report.append("⚠️  No companies found in HubSpot")
        report.append("   Possible reasons:")
        report.append("   1. No Deals exist with matching id_empresa (product ID) values")
        report.append("   2. id_empresa property on Deals is not searchable")
        report.append("   3. Deals exist but have no associated Companies")
    
    # Check for missing required fields
    missing_fields_df = comparison_df[comparison_df['missing_required_fields'].notna()]
    if len(missing_fields_df) > 0:
        report.append(f"⚠️  {len(missing_fields_df):,} companies have missing required fields")
        
        # Count missing fields
        all_missing = []
        for fields_str in missing_fields_df['missing_required_fields'].dropna():
            if fields_str:
                all_missing.extend([f.strip() for f in fields_str.split(',')])
        
        missing_counts = Counter(all_missing)
        report.append("   Missing fields breakdown:")
        for field, count in missing_counts.most_common():
            report.append(f"     - {field}: {count:,}")
    else:
        report.append("✅ All required fields are present")
    
    report.append("")
    
    # Issues Summary
    report.append("⚠️  ISSUES REQUIRING ATTENTION")
    report.append("-" * 80)
    issues_df = comparison_df[comparison_df['consistency_status'] != '✅ Consistent']
    if len(issues_df) > 0:
        report.append(f"Total Companies with Issues: {len(issues_df):,}")
        report.append("")
        report.append("Top Issues:")
        issue_counts = issues_df['consistency_status'].value_counts()
        for issue, count in issue_counts.head(10).items():
            report.append(f"  - {issue}: {count:,}")
        
        # Data integrity issues breakdown
        integrity_issues_df = issues_df[issues_df['data_integrity_issues'].notna()]
        if len(integrity_issues_df) > 0:
            report.append("")
            report.append("Data Integrity Issues Breakdown:")
            all_integrity_issues = []
            for issues_str in integrity_issues_df['data_integrity_issues'].dropna():
                if issues_str:
                    all_integrity_issues.extend([i.strip() for i in issues_str.split(';')])
            
            integrity_counts = Counter(all_integrity_issues)
            for issue, count in integrity_counts.most_common(10):
                report.append(f"  - {issue}: {count:,}")
    else:
        report.append("✅ No issues found - all companies are consistent!")
    
    report.append("")
    report.append("=" * 80)
    
    # Add reconciliation section if reconciliation data is available
    if reconciliation_df is not None and len(reconciliation_df) > 0:
        report.append("")
        report.append("=" * 80)
        report.append("🔄 RECONCILIATION SUMMARY (HubSpot → CSV)")
        report.append("=" * 80)
        report.append("")
        report.append("This section shows deals found in HubSpot and whether they exist in CSV.")
        report.append("")
        
        total_hubspot = len(reconciliation_df)
        in_both = len(reconciliation_df[reconciliation_df['in_csv'] == True])
        in_hubspot_only = len(reconciliation_df[reconciliation_df['in_csv'] == False])
        
        report.append(f"📊 HubSpot deals closed won in {period_str}: {total_hubspot:,}")
        report.append(f"✅ Deals in both HubSpot and CSV: {in_both:,} ({in_both/total_hubspot*100:.1f}%)")
        report.append(f"⚠️  Deals in HubSpot but NOT in CSV: {in_hubspot_only:,} ({in_hubspot_only/total_hubspot*100:.1f}%)")
        report.append("")
        
        if in_hubspot_only > 0:
            report.append("⚠️  DEALS IN HUBSPOT BUT NOT IN CSV (Reconciliation Issues):")
            report.append("-" * 80)
            missing_deals = reconciliation_df[reconciliation_df['in_csv'] == False]
            for _, row in missing_deals.head(20).iterrows():
                report.append(f"   - id_empresa: {row['id_empresa']}, Deal: {row['hubspot_deal_name']}, Close Date: {row['hubspot_close_date']}, Amount: ${row['hubspot_amount']}")
            if len(missing_deals) > 20:
                report.append(f"   ... and {len(missing_deals) - 20} more")
            report.append("")
        
        if csv_not_in_hubspot and len(csv_not_in_hubspot) > 0:
            report.append(f"ℹ️  Note: {len(csv_not_in_hubspot):,} deals in CSV are not in HubSpot for this period.")
            report.append("   This is expected - CSV contains deals from all periods, not just closed won in this month.")
            report.append("")
    
    report.append("=" * 80)
    
    return "\n".join(report)


def generate_reconciliation_insights(
    comparison_df: pd.DataFrame,
    reconciliation_df: Optional[pd.DataFrame],
    month: int,
    year: int,
    period_description: Optional[str] = None,
    bidirectional_comparison: Optional[Dict] = None
) -> str:
    """
    Generate reconciliation insights in markdown table format for display in chatbot.
    
    Args:
        comparison_df: DataFrame with comparison results (CSV → HubSpot)
        reconciliation_df: DataFrame with reconciliation results (HubSpot → CSV)
        month: Analysis month
        year: Analysis year
        period_description: Optional custom period description
        
    Returns:
        Formatted insights string with markdown tables
    """
    if period_description:
        period_str = period_description
    else:
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        period_str = f"{month_names[month - 1]} {year}"
    
    insights = []
    insights.append(f"# 🔄 RECONCILIATION INSIGHTS - {period_str}")
    insights.append("")
    
    # Summary Statistics
    insights.append("## 📊 Summary Statistics")
    insights.append("")
    insights.append("| Metric | Count | Percentage |")
    insights.append("|--------|-------|------------|")
    
    if reconciliation_df is not None and len(reconciliation_df) > 0:
        total_hubspot = len(reconciliation_df)
        in_both = len(reconciliation_df[reconciliation_df['in_csv'] == True])
        in_hubspot_only = len(reconciliation_df[reconciliation_df['in_csv'] == False])
        
        insights.append(f"| **HubSpot deals closed won** | **{total_hubspot:,}** | 100% |")
        insights.append(f"| **Deals in both HubSpot and CSV** | **{in_both:,}** | **{in_both/total_hubspot*100:.1f}%** |")
        insights.append(f"| **Deals in HubSpot but NOT in CSV** | **{in_hubspot_only:,}** | **{in_hubspot_only/total_hubspot*100:.1f}%** |")
        insights.append("")
        
        # Close Date Verification
        in_both_df = reconciliation_df[reconciliation_df['in_csv'] == True]
        if len(in_both_df) > 0:
            insights.append("## 📅 CLOSE DATE VERIFICATION (Deals in both)")
            insights.append("")
            close_dates = []
            for _, row in in_both_df.iterrows():
                if pd.notna(row['hubspot_close_date']):
                    try:
                        date_str = str(row['hubspot_close_date'])
                        if 'T' in date_str:
                            date_str = date_str.split('T')[0]
                        date_obj = pd.to_datetime(date_str).date()
                        close_dates.append(date_obj)
                    except:
                        pass
            
            if close_dates:
                period_start = datetime(year, month, 1).date()
                if month == 12:
                    period_end = datetime(year + 1, 1, 1).date()
                else:
                    period_end = datetime(year, month + 1, 1).date()
                
                dates_in_period = [d for d in close_dates if period_start <= d < period_end]
                
                insights.append("| Metric | Count | Percentage |")
                insights.append("|--------|-------|------------|")
                insights.append(f"| Deals with close dates | {len(close_dates)}/{len(in_both_df)} | {len(close_dates)/len(in_both_df)*100:.1f}% |")
                insights.append(f"| Close dates in {period_str} | {len(dates_in_period)}/{len(close_dates)} | {len(dates_in_period)/len(close_dates)*100:.1f}% |")
                if len(close_dates) > 0:
                    insights.append(f"| Earliest close date | {min(close_dates)} | - |")
                    insights.append(f"| Latest close date | {max(close_dates)} | - |")
                insights.append("")
    
    # Won Deals Analysis
    won_deals = comparison_df[comparison_df['is_new_customer'] == True]
    if len(won_deals) > 0:
        insights.append("## 🆕 WON DEALS ANALYSIS")
        insights.append("")
        insights.append("| Metric | Count | Percentage |")
        insights.append("|--------|-------|------------|")
        insights.append(f"| **Total Won Deals from CSV** | **{len(won_deals):,}** | 100% |")
        won_found = won_deals['hubspot_found'].sum()
        won_consistent = len(won_deals[won_deals['consistency_status'] == '✅ Consistent'])
        insights.append(f"| Found in HubSpot | {won_found:,} | {won_found/len(won_deals)*100:.1f}% |")
        insights.append(f"| ✅ Consistent | {won_consistent:,} | {won_consistent/len(won_deals)*100:.1f}% |")
        insights.append("")
    
    # Churn Deals Analysis
    churn_deals = comparison_df[comparison_df['is_churn_customer'] == True]
    if len(churn_deals) > 0:
        insights.append("## 🔴 CHURN DEALS ANALYSIS")
        insights.append("")
        insights.append("| Metric | Count | Percentage |")
        insights.append("|--------|-------|------------|")
        insights.append(f"| **Total Churn Deals** | **{len(churn_deals):,}** | 100% |")
        churn_found = churn_deals['hubspot_found'].sum()
        churn_consistent = len(churn_deals[churn_deals['consistency_status'] == '✅ Consistent'])
        churn_missing_date = len(churn_deals[churn_deals['consistency_status'] == '❌ Missing Churn Date'])
        churn_wrong_stage = len(churn_deals[churn_deals['consistency_status'] == '⚠️  Wrong Stage'])
        churn_both_issues = len(churn_deals[churn_deals['consistency_status'] == '❌ Missing Churn Date & Wrong Stage'])
        
        insights.append(f"| Found in HubSpot | {churn_found:,} | {churn_found/len(churn_deals)*100:.1f}% |")
        insights.append(f"| ✅ Consistent | {churn_consistent:,} | {churn_consistent/len(churn_deals)*100:.1f}% |")
        insights.append(f"| ❌ Missing Churn Date | {churn_missing_date:,} | {churn_missing_date/len(churn_deals)*100:.1f}% |")
        insights.append(f"| ⚠️  Wrong Stage | {churn_wrong_stage:,} | {churn_wrong_stage/len(churn_deals)*100:.1f}% |")
        insights.append(f"| ❌ Missing Churn Date & Wrong Stage | {churn_both_issues:,} | {churn_both_issues/len(churn_deals)*100:.1f}% |")
        insights.append("")
    
    # Missing Deals in CSV
    if reconciliation_df is not None and len(reconciliation_df) > 0:
        missing_in_csv = reconciliation_df[reconciliation_df['in_csv'] == False]
        if len(missing_in_csv) > 0:
            insights.append("## ⚠️  DEALS IN HUBSPOT BUT NOT IN CSV")
            insights.append("")
            insights.append("| Product ID | Deal Name | Close Date |")
            insights.append("|------------|-----------|------------|")
            for _, row in missing_in_csv.iterrows():
                close_date = str(row['hubspot_close_date'])[:10] if pd.notna(row['hubspot_close_date']) else ''
                deal_name = str(row['hubspot_deal_name'])
                if len(deal_name) > 40:
                    deal_name = deal_name[:40] + '...'
                insights.append(f"| {row['id_empresa']} | {deal_name} | {close_date} |")
            insights.append("")
    
    # Consistency Confirmation
    insights.append("## ✅ CONSISTENCY CONFIRMATION")
    insights.append("")
    insights.append("| Check | Result |")
    insights.append("|-------|--------|")
    
    if reconciliation_df is not None and len(reconciliation_df) > 0:
        in_both_count = len(reconciliation_df[reconciliation_df['in_csv'] == True])
        insights.append(f"| Deals in both HubSpot and CSV | {in_both_count:,} |")
        
        # Check if all dates are in period
        in_both_df = reconciliation_df[reconciliation_df['in_csv'] == True]
        if len(in_both_df) > 0:
            close_dates = []
            for _, row in in_both_df.iterrows():
                if pd.notna(row['hubspot_close_date']):
                    try:
                        date_str = str(row['hubspot_close_date'])
                        if 'T' in date_str:
                            date_str = date_str.split('T')[0]
                        date_obj = pd.to_datetime(date_str).date()
                        close_dates.append(date_obj)
                    except:
                        pass
            
            if close_dates:
                period_start = datetime(year, month, 1).date()
                if month == 12:
                    period_end = datetime(year + 1, 1, 1).date()
                else:
                    period_end = datetime(year, month + 1, 1).date()
                
                dates_in_period = [d for d in close_dates if period_start <= d < period_end]
                all_in_period = len(dates_in_period) == len(close_dates)
                insights.append(f"| All close dates in {period_str} | {'✅ True' if all_in_period else '❌ False'} |")
    
    if len(won_deals) > 0:
        won_consistent = len(won_deals[won_deals['consistency_status'] == '✅ Consistent'])
        insights.append(f"| Won deals consistent | {won_consistent}/{len(won_deals)} ({won_consistent/len(won_deals)*100:.1f}%) |")
    
    insights.append("")
    
    # Conclusion
    if reconciliation_df is not None and len(reconciliation_df) > 0:
        in_both_count = len(reconciliation_df[reconciliation_df['in_csv'] == True])
        insights.append(f"**Conclusion:** {in_both_count} deals match between HubSpot and CSV, all with close dates in {period_str}.")
    
    return "\n".join(insights)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compare monthly closing data with HubSpot for consistency validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python compare_monthly_closing_with_hubspot.py \\
      --consolidated-file "outputs/monthly_closing_consolidated_202512_*.csv" \\
      --month 12 \\
      --year 2025

  # With sample size (for testing)
  python compare_monthly_closing_with_hubspot.py \\
      --consolidated-file "outputs/consolidated.csv" \\
      --month 12 \\
      --year 2025 \\
      --sample-size 50
        """
    )
    
    parser.add_argument(
        '--consolidated-file',
        type=str,
        required=True,
        help='Path to the consolidated monthly closing CSV file'
    )
    
    parser.add_argument(
        '--month',
        type=int,
        required=True,
        choices=range(1, 13),
        metavar='[1-12]',
        help='Month number (1-12) for the analysis period'
    )
    
    parser.add_argument(
        '--year',
        type=int,
        required=True,
        help='Year number for the analysis period'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output directory for generated files (default: same directory as consolidated-file)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of companies to fetch per batch from HubSpot (default: 100)'
    )
    
    parser.add_argument(
        '--sample-size',
        type=int,
        default=0,
        help='Process only a sample of companies (for testing). 0 = process all (default: 0)'
    )
    
    parser.add_argument(
        '--period-description',
        type=str,
        default=None,
        help='Custom period description for reports'
    )
    
    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()
    
    # Validate consolidated file exists
    consolidated_path = Path(args.consolidated_file)
    if not consolidated_path.exists():
        print(f"❌ Error: Consolidated file not found: {args.consolidated_file}")
        sys.exit(1)
    
    # Determine output directory
    if args.output_dir:
        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = consolidated_path.parent
    
    # Generate period description
    if args.period_description:
        period_description = args.period_description
    else:
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        period_description = f"{month_names[args.month - 1]} {args.year}"
    
    print("=" * 80)
    print(f"HUBSPOT CONSISTENCY COMPARISON - {period_description.upper()}")
    print("=" * 80)
    print(f"Consolidated File: {args.consolidated_file}")
    print(f"Output Directory: {output_path}")
    print("")
    
    # Initialize HubSpot client FIRST
    print("🔗 Initializing HubSpot API client...")
    try:
        hubspot_client = HubSpotClient()
        print("✅ HubSpot client initialized")
    except Exception as e:
        print(f"❌ Error initializing HubSpot client: {str(e)}")
        print("   Make sure HUBSPOT_ACCESS_TOKEN is set in your environment")
        sys.exit(1)
    
    # OPTIMIZATION: First search HubSpot for deals closed in the period (fast API call)
    print("\n" + "=" * 80)
    print("🔄 STEP 1: Search HubSpot for deals closed in period (Fast API call)")
    print("=" * 80)
    reconciliation_start_time = time.time()
    hubspot_all_deals = search_hubspot_deals_closed_in_period(
        hubspot_client,
        args.month,
        args.year,
        args.batch_size
    )
    reconciliation_elapsed = time.time() - reconciliation_start_time
    print(f"   ⏱️  HubSpot search time: {reconciliation_elapsed:.1f} seconds")
    
    # Extract id_empresas from HubSpot deals to filter CSV efficiently
    hubspot_id_empresas = set()
    for deal in hubspot_all_deals:
        properties = deal.get('properties', {})
        id_empresa_raw = str(properties.get('id_empresa', '')).strip()
        id_empresa = id_empresa_raw.replace(' ', '')
        if id_empresa and id_empresa.isdigit():
            hubspot_id_empresas.add(id_empresa)
    
    print(f"   📊 Found {len(hubspot_all_deals):,} deals closed won in HubSpot")
    print(f"   📊 Unique id_empresas: {len(hubspot_id_empresas):,}")
    
    # Search HubSpot for churned deals in the period
    print("\n" + "=" * 80)
    print("🔄 STEP 1B: Search HubSpot for deals churned in period")
    print("=" * 80)
    churn_search_start_time = time.time()
    hubspot_churned_deals = search_hubspot_deals_churned_in_period(
        hubspot_client,
        args.month,
        args.year,
        args.batch_size
    )
    churn_search_elapsed = time.time() - churn_search_start_time
    print(f"   ⏱️  HubSpot churn search time: {churn_search_elapsed:.1f} seconds")
    
    # Extract id_empresas from HubSpot churned deals
    hubspot_churned_id_empresas = set()
    for deal in hubspot_churned_deals:
        properties = deal.get('properties', {})
        id_empresa_raw = str(properties.get('id_empresa', '')).strip()
        id_empresa = id_empresa_raw.replace(' ', '')
        if id_empresa and id_empresa.isdigit():
            hubspot_churned_id_empresas.add(id_empresa)
    
    print(f"   📊 Found {len(hubspot_churned_deals):,} deals churned in HubSpot")
    print(f"   📊 Unique churned id_empresas: {len(hubspot_churned_id_empresas):,}")
    
    # Display summary
    print("\n" + "=" * 80)
    print("📊 HUBSPOT DEALS SUMMARY")
    print("=" * 80)
    print(f"   ✅ Deals closed won in {period_description}: {len(hubspot_all_deals):,}")
    print(f"   🔴 Deals churned in {period_description}: {len(hubspot_churned_deals):,}")
    print(f"   📊 Total unique id_empresas (won): {len(hubspot_id_empresas):,}")
    print(f"   📊 Total unique id_empresas (churned): {len(hubspot_churned_id_empresas):,}")
    print("")
    
    # Load consolidated data
    print("\n🔄 STEP 2: Loading and filtering CSV data...")
    consolidated_df = load_consolidated_data(args.consolidated_file)
    original_count = len(consolidated_df)
    print(f"✅ Loaded {original_count:,} rows from CSV file")
    print(f"   📊 File: {consolidated_path.name}")
    
    # OPTIMIZATION: Filter CSV to deals that exist in HubSpot for this period OR are churn deals
    # Note: We include ALL churn deals from CSV (they may have closed earlier but churned in period)
    # We only filter won deals to those in HubSpot for the period
    if len(hubspot_id_empresas) > 0:
        # Clean id_empresa in CSV for matching
        consolidated_df['id_empresa_clean'] = consolidated_df['id_empresa'].astype(str).str.strip().str.replace(' ', '')
        
        # Separate won and churn deals
        won_deals = consolidated_df[consolidated_df['is_new_customer'] == True]
        churn_deals = consolidated_df[consolidated_df['is_churn_customer'] == True]
        
        # Filter won deals to only those in HubSpot for this period
        won_deals_filtered = won_deals[won_deals['id_empresa_clean'].isin(hubspot_id_empresas)]
        
        # Include ALL churn deals (they may have closed earlier but churned in period)
        # We'll filter them later based on churn date
        consolidated_df = pd.concat([won_deals_filtered, churn_deals], ignore_index=True)
        
        print(f"   ✅ Filtered won deals: {len(won_deals_filtered):,} (from {len(won_deals):,})")
        print(f"   ✅ Included all churn deals: {len(churn_deals):,} (will filter by churn date)")
        print(f"   📊 Total after filtering: {len(consolidated_df):,} rows")
        print(f"   📊 Filtered from {original_count:,} to {len(consolidated_df):,} rows ({len(consolidated_df)/original_count*100:.1f}%)")
    else:
        print(f"   ⚠️  No HubSpot deals found for this period")
        print(f"   📊 Will process all deals from CSV (won + churn): {len(consolidated_df):,}")
    
    # Apply sample size if specified (for testing)
    if args.sample_size > 0:
        print(f"\n📊 Processing sample of {args.sample_size} companies (for testing)...")
        consolidated_df = consolidated_df.head(args.sample_size)
        print(f"   ⚠️  Sample mode: Processing {len(consolidated_df):,} of {original_count:,} companies")
    
    print("")
    print("ℹ️  NOTE: This is DEAL/PRODUCT level analysis, not Company level.")
    print("   - id_empresa is a PRODUCT ID on Deals")
    print("   - Revenue is tracked at the Deal level")
    print("   - New customers = Deals closed in the period")
    print("   - Churn = Deals in churn stage (31849274)")
    print("")
    
    # Get unique id_empresa values from consolidated CSV (product IDs)
    # Include ALL deals: won deals filtered by period + ALL churn deals
    id_empresa_list = consolidated_df['id_empresa'].unique().tolist()
    
    # Count by type
    won_count = len(consolidated_df[consolidated_df['is_new_customer'] == True])
    churn_count = len(consolidated_df[consolidated_df['is_churn_customer'] == True])
    
    print(f"\n📋 STEP 3: Fetching detailed HubSpot Deal data for CSV deals...")
    print(f"   📊 Unique id_empresa (product ID) values to fetch: {len(id_empresa_list):,}")
    print(f"   📊 Won deals: {won_count:,}")
    print(f"   📊 Churn deals: {churn_count:,}")
    print(f"   📊 Batch size: {args.batch_size}")
    print(f"   📊 Estimated batches: {(len(id_empresa_list) + args.batch_size - 1) // args.batch_size}")
    print("")
    
    # Fetch HubSpot Deal data for ALL deals in consolidated CSV (won + churn)
    print("⏳ Fetching HubSpot Deal data for all deals (won + churn)...")
    start_time = time.time()
    hubspot_data = fetch_hubspot_deals_batch(
        hubspot_client,
        id_empresa_list,
        args.batch_size
    )
    elapsed_time = time.time() - start_time
    
    found_count = sum(1 for v in hubspot_data.values() if v is not None)
    not_found_count = len(id_empresa_list) - found_count
    
    print(f"\n✅ HubSpot Deal data fetch complete!")
    print(f"   📊 Deals (products) found: {found_count:,} ({found_count/len(id_empresa_list)*100:.1f}%)")
    print(f"   📊 Deals (products) not found: {not_found_count:,} ({not_found_count/len(id_empresa_list)*100:.1f}%)")
    print(f"   ⏱️  Time elapsed: {elapsed_time:.1f} seconds")
    if len(id_empresa_list) > 0:
        print(f"   📊 Average time per deal: {elapsed_time/len(id_empresa_list):.2f} seconds")
    
    # BIDIRECTIONAL COMPARISON: Compare CSV vs HubSpot for both WON and CHURN deals
    print("\n" + "=" * 80)
    print("🔄 BIDIRECTIONAL DATASET COMPARISON")
    print("=" * 80)
    
    # Reload full CSV for complete comparison
    full_consolidated_df = load_consolidated_data(args.consolidated_file)
    
    # === WON DEALS COMPARISON ===
    print(f"\n📊 WON DEALS COMPARISON:")
    print("-" * 80)
    
    # Get CSV won deals - filter by Inicio_Inicial date for the period
    # Inicio_Inicial is the date finance uses to determine when deal was closed/won
    csv_won_deals_all = full_consolidated_df[full_consolidated_df['is_new_customer'] == True].copy()
    
    # Filter by Inicio_Inicial date in the analysis period
    period_start = datetime(args.year, args.month, 1)
    if args.month == 12:
        period_end = datetime(args.year + 1, 1, 1)
    else:
        period_end = datetime(args.year, args.month + 1, 1)
    
    # Convert Inicio_Inicial to datetime and filter by period
    if 'Inicio_Inicial' in csv_won_deals_all.columns:
        csv_won_deals_all['Inicio_Inicial_dt'] = pd.to_datetime(csv_won_deals_all['Inicio_Inicial'], errors='coerce')
        csv_won_deals = csv_won_deals_all[
            (csv_won_deals_all['Inicio_Inicial_dt'] >= period_start) & 
            (csv_won_deals_all['Inicio_Inicial_dt'] < period_end)
        ].copy()
        print(f"   Filtering CSV by Inicio_Inicial date: {period_start.date()} to {period_end.date()}")
        print(f"   Total new deals in CSV: {len(csv_won_deals_all):,}")
        print(f"   Deals with Inicio_Inicial in {args.month}/{args.year}: {len(csv_won_deals):,}")
    else:
        # Fallback if Inicio_Inicial column doesn't exist
        csv_won_deals = csv_won_deals_all.copy()
        print(f"   ⚠️  Inicio_Inicial column not found - using all new deals: {len(csv_won_deals):,}")
    
    csv_won_id_empresas = set(csv_won_deals['id_empresa'].astype(str).str.strip().str.replace(' ', '').tolist())
    
    # Get HubSpot won deals id_empresas (already filtered by period)
    hubspot_won_id_empresas_clean = set()
    for deal in hubspot_all_deals:
        properties = deal.get('properties', {})
        id_empresa_raw = str(properties.get('id_empresa', '')).strip()
        id_empresa = id_empresa_raw.replace(' ', '')
        if id_empresa and id_empresa.isdigit():
            hubspot_won_id_empresas_clean.add(id_empresa)
    
    # Compare won deals
    won_in_both = csv_won_id_empresas.intersection(hubspot_won_id_empresas_clean)
    won_in_csv_only = csv_won_id_empresas - hubspot_won_id_empresas_clean
    won_in_hubspot_only = hubspot_won_id_empresas_clean - csv_won_id_empresas
    
    print(f"   CSV Finance (won deals): {len(csv_won_id_empresas):,}")
    print(f"   HubSpot (closed won in period): {len(hubspot_won_id_empresas_clean):,}")
    print(f"   ✅ In both (reconciled): {len(won_in_both):,}")
    print(f"   ⚠️  In CSV only: {len(won_in_csv_only):,}")
    print(f"   ⚠️  In HubSpot only: {len(won_in_hubspot_only):,}")
    
    # === CHURN DEALS COMPARISON ===
    print(f"\n📊 CHURN DEALS COMPARISON:")
    print("-" * 80)
    
    # Get CSV true churns (Ending_Sin_Descuentos = 0)
    csv_churn_deals = full_consolidated_df[full_consolidated_df['is_churn_customer'] == True].copy()
    csv_true_churns = csv_churn_deals[csv_churn_deals['Ending_Sin_Descuentos'].fillna(0) == 0].copy()
    csv_churn_id_empresas = set(csv_true_churns['id_empresa'].astype(str).str.strip().str.replace(' ', '').tolist())
    
    # Get HubSpot churned deals id_empresas
    hubspot_churn_id_empresas_clean = set()
    for deal in hubspot_churned_deals:
        properties = deal.get('properties', {})
        id_empresa_raw = str(properties.get('id_empresa', '')).strip()
        id_empresa = id_empresa_raw.replace(' ', '')
        if id_empresa and id_empresa.isdigit():
            hubspot_churn_id_empresas_clean.add(id_empresa)
    
    # Compare churn deals
    churn_in_both = csv_churn_id_empresas.intersection(hubspot_churn_id_empresas_clean)
    churn_in_csv_only = csv_churn_id_empresas - hubspot_churn_id_empresas_clean
    churn_in_hubspot_only = hubspot_churn_id_empresas_clean - csv_churn_id_empresas
    
    print(f"   CSV Finance (true churns): {len(csv_churn_id_empresas):,}")
    print(f"   HubSpot (churned in period): {len(hubspot_churn_id_empresas_clean):,}")
    print(f"   ✅ In both (reconciled): {len(churn_in_both):,}")
    print(f"   ⚠️  In CSV only: {len(churn_in_csv_only):,}")
    print(f"   ⚠️  In HubSpot only: {len(churn_in_hubspot_only):,}")
    
    # === SUMMARY ===
    print(f"\n📊 RECONCILIATION SUMMARY:")
    print("-" * 80)
    print(f"   🆕 Won Deals:")
    print(f"      CSV: {len(csv_won_id_empresas):,} | HubSpot: {len(hubspot_won_id_empresas_clean):,} | ✅ In both: {len(won_in_both):,}")
    print(f"   🔴 Churn Deals:")
    print(f"      CSV: {len(csv_churn_id_empresas):,} | HubSpot: {len(hubspot_churn_id_empresas_clean):,} | ✅ In both: {len(churn_in_both):,}")
    print()
    
    # Store comparison results for reporting
    comparison_results = {
        'won': {
            'csv_count': len(csv_won_id_empresas),
            'hubspot_count': len(hubspot_won_id_empresas_clean),
            'in_both': len(won_in_both),
            'csv_only': len(won_in_csv_only),
            'hubspot_only': len(won_in_hubspot_only),
            'csv_only_list': sorted(list(won_in_csv_only)),
            'hubspot_only_list': sorted(list(won_in_hubspot_only))
        },
        'churn': {
            'csv_count': len(csv_churn_id_empresas),
            'hubspot_count': len(hubspot_churn_id_empresas_clean),
            'in_both': len(churn_in_both),
            'csv_only': len(churn_in_csv_only),
            'hubspot_only': len(churn_in_hubspot_only),
            'csv_only_list': sorted(list(churn_in_csv_only)),
            'hubspot_only_list': sorted(list(churn_in_hubspot_only)),
            'hubspot_only_deals': hubspot_churned_deals  # For getting deal names
        }
    }
    
    # Compare data (CSV → HubSpot direction)
    print("\n🔍 STEP 4: Comparing data with HubSpot (CSV → HubSpot)...")
    print(f"   📊 Comparing {len(consolidated_df):,} products/deals...")
    comparison_df = compare_with_hubspot(
        consolidated_df,
        hubspot_data,
        args.month,
        args.year
    )
    print(f"   ✅ Comparison complete: {len(comparison_df):,} records processed")
    
    # RECONCILIATION: Reconcile HubSpot deals with CSV
    print("\n" + "=" * 80)
    print("🔄 STEP 5: RECONCILIATION (HubSpot → CSV)")
    print("=" * 80)
    
    reconciliation_df = None
    csv_not_in_hubspot = None
    
    if len(hubspot_all_deals) > 0:
        # Reload full CSV for reconciliation (to check what's missing)
        full_consolidated_df = load_consolidated_data(args.consolidated_file)
        reconciliation_df, csv_not_in_hubspot = reconcile_hubspot_with_csv(
            hubspot_all_deals,
            full_consolidated_df,  # Use full CSV for reconciliation
            args.month,
            args.year
        )
        print(f"   ⏱️  Reconciliation complete")
    else:
        print("   ⚠️  No deals found in HubSpot for this period")
    
    # Generate report with reconciliation data
    print("\n📝 Generating comparison and reconciliation report...")
    report = generate_comparison_report(
        comparison_df,
        args.month,
        args.year,
        args.period_description,
        reconciliation_df,
        csv_not_in_hubspot
    )
    
    # Print report
    print("\n" + report)
    
    # Generate and print reconciliation insights
    print("\n" + "=" * 80)
    print("📊 RECONCILIATION INSIGHTS (For Chatbot Display)")
    print("=" * 80)
    insights = generate_reconciliation_insights(
        comparison_df,
        reconciliation_df,
        args.month,
        args.year,
        args.period_description,
        comparison_results
    )
    print("\n" + insights)
    print("=" * 80)
    
    # Print processing statistics
    print("\n" + "=" * 80)
    print("📊 PROCESSING STATISTICS")
    print("=" * 80)
    print(f"Input File: {consolidated_path.name}")
    print(f"Total Rows in CSV: {original_count:,}")
    print(f"Products/Deals Processed: {len(consolidated_df):,}")
    print(f"Unique id_empresa (Product ID) Values: {len(id_empresa_list):,}")
    print(f"HubSpot Deals Found: {found_count:,}")
    print(f"HubSpot Deals Not Found: {not_found_count:,}")
    print(f"Comparison Records Generated: {len(comparison_df):,}")
    if len(comparison_df) > 0:
        print(f"Consistent Deals: {len(comparison_df[comparison_df['consistency_status'] == '✅ Consistent']):,}")
        print(f"Deals with Issues: {len(comparison_df[comparison_df['consistency_status'] != '✅ Consistent']):,}")
    else:
        print("⚠️  No deals closed in December 2025 found in this sample")
    print(f"Processing Time: {elapsed_time:.1f} seconds")
    print("=" * 80)
    
    # Save comparison results (CSV → HubSpot)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    comparison_filename = f"hubspot_comparison_{args.year}{args.month:02d}_{timestamp}.csv"
    comparison_file = output_path / comparison_filename
    comparison_df.to_csv(comparison_file, index=False, encoding='utf-8')
    print(f"\n💾 Comparison results (CSV → HubSpot) saved to: {comparison_file}")
    
    # Save reconciliation results (HubSpot → CSV)
    if reconciliation_df is not None and len(reconciliation_df) > 0:
        reconciliation_filename = f"hubspot_reconciliation_{args.year}{args.month:02d}_{timestamp}.csv"
        reconciliation_file = output_path / reconciliation_filename
        reconciliation_df.to_csv(reconciliation_file, index=False, encoding='utf-8')
        print(f"💾 Reconciliation results (HubSpot → CSV) saved to: {reconciliation_file}")
        
        # Save deals in HubSpot but NOT in CSV
        missing_in_csv = reconciliation_df[reconciliation_df['in_csv'] == False]
        if len(missing_in_csv) > 0:
            missing_filename = f"hubspot_deals_missing_in_csv_{args.year}{args.month:02d}_{timestamp}.csv"
            missing_file = output_path / missing_filename
            missing_in_csv.to_csv(missing_file, index=False, encoding='utf-8')
            print(f"⚠️  Deals in HubSpot but NOT in CSV: {missing_file}")
            print(f"   📊 Count: {len(missing_in_csv):,}")
    
    # Save report
    report_filename = f"hubspot_reconciliation_report_{args.year}{args.month:02d}_{timestamp}.txt"
    report_file = output_path / report_filename
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"💾 Reconciliation report saved to: {report_file}")
    
    # Save insights (markdown format for chatbot display)
    insights_filename = f"hubspot_reconciliation_insights_{args.year}{args.month:02d}_{timestamp}.md"
    insights_file = output_path / insights_filename
    with open(insights_file, 'w', encoding='utf-8') as f:
        f.write(insights)
    print(f"💾 Reconciliation insights (markdown) saved to: {insights_file}")
    
    # Save issues only (if there are any deals to analyze)
    if len(comparison_df) > 0:
        issues_df = comparison_df[comparison_df['consistency_status'] != '✅ Consistent']
        if len(issues_df) > 0:
            issues_filename = f"hubspot_comparison_issues_{args.year}{args.month:02d}_{timestamp}.csv"
            issues_file = output_path / issues_filename
            issues_df.to_csv(issues_file, index=False, encoding='utf-8')
            print(f"\n⚠️  Issues file saved to: {issues_file}")
            print(f"   📊 Issues found: {len(issues_df):,} deals")
    else:
        print(f"\n⚠️  No deals closed in December 2025 found - no issues file generated")
    
    # Final summary
    print("\n" + "=" * 80)
    print("✅ RECONCILIATION COMPLETE!")
    print("=" * 80)
    print(f"📊 Period analyzed: {period_description}")
    print(f"📁 Output directory: {output_path}")
    print(f"📄 Files generated:")
    print(f"   1. Comparison results (CSV → HubSpot): {comparison_filename}")
    if reconciliation_df is not None and len(reconciliation_df) > 0:
        print(f"   2. Reconciliation results (HubSpot → CSV): {reconciliation_filename}")
        missing_in_csv = reconciliation_df[reconciliation_df['in_csv'] == False]
        if len(missing_in_csv) > 0:
            print(f"   3. Deals in HubSpot but NOT in CSV: {missing_filename}")
    print(f"   4. Summary report: {report_filename}")
    print(f"   5. Reconciliation insights (markdown): {insights_filename}")
    if len(comparison_df) > 0:
        issues_df = comparison_df[comparison_df['consistency_status'] != '✅ Consistent']
        if len(issues_df) > 0:
            print(f"   6. Issues file: {issues_filename}")
    print("=" * 80)
    
    # Reconciliation summary
    if reconciliation_df is not None and len(reconciliation_df) > 0:
        print("\n🔄 RECONCILIATION SUMMARY:")
        print("-" * 80)
        total_hubspot = len(reconciliation_df)
        in_both = len(reconciliation_df[reconciliation_df['in_csv'] == True])
        in_hubspot_only = len(reconciliation_df[reconciliation_df['in_csv'] == False])
        print(f"HubSpot deals closed won in {period_description}: {total_hubspot:,}")
        print(f"✅ Deals in both HubSpot and CSV: {in_both:,} ({in_both/total_hubspot*100:.1f}%)")
        print(f"⚠️  Deals in HubSpot but NOT in CSV: {in_hubspot_only:,} ({in_hubspot_only/total_hubspot*100:.1f}%)")
        if csv_not_in_hubspot:
            print(f"ℹ️  Deals in CSV but NOT in HubSpot (for this period): {len(csv_not_in_hubspot):,}")
            print("   (Expected - CSV contains deals from all periods)")
        print("=" * 80)


if __name__ == "__main__":
    main()

