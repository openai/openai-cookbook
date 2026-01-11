#!/usr/bin/env python3
"""
Analyze Industry Field Property History
========================================
Analyzes the property history of the 'industria' field at company level to see
how much has been updated recently by the industry enrichment workflow and how
this has improved the ICP field (type field).

Usage:
    # Analyze companies from recent deals (last 30 days)
    python analyze_industria_field_history.py
    
    # Analyze companies from specific date range
    python analyze_industria_field_history.py --start-date 2025-12-01 --end-date 2026-01-01
    
    # Analyze specific companies
    python analyze_industria_field_history.py --company-ids 27804859693 17655187038
    
    # Limit number of companies to analyze
    python analyze_industria_field_history.py --limit 50
"""

import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import argparse
import time
from typing import Optional, Dict, Any, List
from collections import defaultdict

load_dotenv()

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY") or os.getenv("ColppyCRMAutomations")
HUBSPOT_BASE_URL = "https://api.hubapi.com"

def get_company_property_history(company_id: str, property_name: str = "industria") -> List[Dict[str, Any]]:
    """
    Get property history for a company using HubSpot API
    
    Args:
        company_id: HubSpot company ID
        property_name: Property name to get history for (default: industria)
    
    Returns:
        List of property history entries
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/{company_id}"
    
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
        if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
            # Company not found - skip silently
            return []
        return []

def get_companies_updated_recently(days_back: int = 14, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Get companies updated recently (based on hs_lastmodifieddate)
    
    Args:
        days_back: Number of days to look back
        limit: Maximum number of companies to fetch
    
    Returns:
        List of company dictionaries
    """
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/search"
    
    payload = {
        "filterGroups": [
            {
                "filters": [
                    {"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": cutoff_date}
                ]
            }
        ],
        "properties": ["name", "industria", "type", "domain", "cuit", "hs_lastmodifieddate"],
        "limit": limit,
        "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "DESCENDING"}]
    }
    
    companies = []
    after = None
    
    while True:
        if after:
            payload["after"] = after
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            for company in results:
                props = company.get('properties', {})
                companies.append({
                    'company_id': company.get('id'),
                    'name': props.get('name', ''),
                    'industria': props.get('industria', ''),
                    'type': props.get('type', ''),
                    'domain': props.get('domain', ''),
                    'cuit': props.get('cuit', ''),
                    'hs_lastmodifieddate': props.get('hs_lastmodifieddate', '')
                })
            
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after or len(companies) >= limit:
                break
                
            time.sleep(0.2)
        except Exception as e:
            print(f"⚠️  Error fetching companies: {e}")
            break
    
    return companies

def get_companies_from_recent_deals(start_date: str, end_date: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Get companies from recent closed won deals
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        limit: Maximum number of deals to process
    
    Returns:
        List of company dictionaries with deal info
    """
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Fetch closed won deals in date range
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    
    payload = {
        "filterGroups": [
            {
                "filters": [
                    {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"},
                    {"propertyName": "closedate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                    {"propertyName": "closedate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
                ]
            }
        ],
        "properties": ["dealname", "closedate", "primary_company_type"],
        "limit": limit
    }
    
    companies_by_id = {}
    deals = []
    after = None
    
    while True:
        if after:
            payload["after"] = after
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            deals.extend(results)
            
            # Get primary company IDs from deals
            for deal in results:
                deal_id = deal.get('id')
                
                # Get primary company association (Type ID 5)
                assoc_url = f"{HUBSPOT_BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/companies"
                try:
                    assoc_response = requests.get(assoc_url, headers=headers, timeout=30)
                    if assoc_response.status_code == 200:
                        associations = assoc_response.json().get('results', [])
                        for assoc in associations:
                            for assoc_type in assoc.get('associationTypes', []):
                                if assoc_type.get('typeId') == 5:  # Primary company
                                    company_id = assoc.get('toObjectId')
                                    if company_id and company_id not in companies_by_id:
                                        companies_by_id[company_id] = {
                                            'company_id': company_id,
                                            'deal_id': deal_id,
                                            'deal_name': deal.get('properties', {}).get('dealname', ''),
                                            'closedate': deal.get('properties', {}).get('closedate', '')
                                        }
                except:
                    pass
                
                time.sleep(0.1)  # Rate limiting
            
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after or len(companies_by_id) >= limit:
                break
                
            time.sleep(0.2)
        except Exception as e:
            print(f"⚠️  Error fetching deals: {e}")
            break
    
    # Fetch company properties
    company_ids = list(companies_by_id.keys())[:limit]
    if company_ids:
        batch_url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/batch/read"
        for i in range(0, len(company_ids), 100):
            batch = company_ids[i:i+100]
            batch_payload = {
                "inputs": [{"id": cid} for cid in batch],
                "properties": ["name", "industria", "type", "domain", "cuit"]
            }
            
            try:
                batch_response = requests.post(batch_url, headers=headers, json=batch_payload, timeout=30)
                if batch_response.status_code == 200:
                    batch_data = batch_response.json().get('results', [])
                    for company in batch_data:
                        company_id = company.get('id')
                        if company_id in companies_by_id:
                            companies_by_id[company_id].update({
                                'name': company.get('properties', {}).get('name', ''),
                                'industria': company.get('properties', {}).get('industria', ''),
                                'type': company.get('properties', {}).get('type', ''),
                                'domain': company.get('properties', {}).get('domain', ''),
                                'cuit': company.get('properties', {}).get('cuit', '')
                            })
                time.sleep(0.2)
            except:
                pass
    
    return list(companies_by_id.values())

def analyze_industria_history(company_id: str, company_name: str, days_back: int = 14) -> Optional[Dict[str, Any]]:
    """
    Analyze industria field history for a company
    
    Args:
        company_id: HubSpot company ID
        company_name: Company name
        days_back: Number of days to look back for recent updates
    
    Returns:
        Dictionary with analysis results or None
    """
    history = get_company_property_history(company_id, "industria")
    
    if not history:
        return None
    
    # Filter for recent updates (last N days)
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    recent_updates = []
    all_updates = []
    
    for entry in history:
        value = entry.get('value', '')
        timestamp_ms = entry.get('timestamp', 0)
        
        # Convert timestamp to int if it's a string
        try:
            timestamp_ms = int(timestamp_ms) if timestamp_ms else 0
        except (ValueError, TypeError):
            timestamp_ms = 0
        
        if timestamp_ms:
            timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000)
            all_updates.append({
                'value': value,
                'timestamp': timestamp_dt,
                'timestamp_ms': timestamp_ms
            })
            
            if timestamp_dt >= cutoff_date:
                recent_updates.append({
                    'value': value,
                    'timestamp': timestamp_dt,
                    'timestamp_ms': timestamp_ms
                })
    
    if not all_updates:
        return None
    
    # Sort by timestamp (newest first)
    all_updates.sort(key=lambda x: x['timestamp'], reverse=True)
    recent_updates.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Get latest value
    latest_update = all_updates[0]
    first_update = all_updates[-1] if len(all_updates) > 1 else latest_update
    
    # Check if there were recent updates
    has_recent_update = len(recent_updates) > 0
    latest_recent_update = recent_updates[0] if recent_updates else None
    
    return {
        'company_id': company_id,
        'company_name': company_name,
        'current_value': latest_update['value'],
        'first_value': first_update['value'],
        'total_updates': len(all_updates),
        'recent_updates': len(recent_updates),
        'has_recent_update': has_recent_update,
        'latest_update_date': latest_update['timestamp'],
        'first_update_date': first_update['timestamp'],
        'latest_recent_update_date': latest_recent_update['timestamp'] if latest_recent_update else None,
        'history': all_updates
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze industria field property history')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD) - defaults to 30 days ago')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD) - defaults to today')
    parser.add_argument('--company-ids', nargs='+', help='Specific company IDs to analyze')
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of companies to analyze')
    parser.add_argument('--days-back', type=int, default=14, help='Number of days to look back for recent updates (default: 14)')
    parser.add_argument('--use-recent-updates', action='store_true', help='Use companies updated recently instead of from deals')
    
    args = parser.parse_args()
    
    if not HUBSPOT_API_KEY:
        print("❌ HUBSPOT_API_KEY or ColppyCRMAutomations environment variable required")
        return
    
    # Determine date range
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    if args.start_date:
        start_date = args.start_date
    else:
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    print("="*80)
    print("INDUSTRIA FIELD HISTORY ANALYSIS")
    print("="*80)
    if args.use_recent_updates:
        print(f"Using companies updated in last {args.days_back} days")
    else:
        print(f"Date Range (for deals): {start_date} to {end_date}")
    print(f"Recent Updates Window: Last {args.days_back} days")
    print(f"Max Companies to Analyze: {args.limit}")
    print("="*80)
    print()
    
    # Get companies to analyze
    if args.company_ids:
        print(f"📋 Analyzing {len(args.company_ids)} specific companies...")
        companies = []
        headers = {
            "Authorization": f"Bearer {HUBSPOT_API_KEY}",
            "Content-Type": "application/json"
        }
        batch_url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/companies/batch/read"
        batch_payload = {
            "inputs": [{"id": cid} for cid in args.company_ids],
            "properties": ["name", "industria", "type"]
        }
        try:
            response = requests.post(batch_url, headers=headers, json=batch_payload, timeout=30)
            if response.status_code == 200:
                batch_data = response.json().get('results', [])
                for company in batch_data:
                    companies.append({
                        'company_id': company.get('id'),
                        'name': company.get('properties', {}).get('name', ''),
                        'industria': company.get('properties', {}).get('industria', ''),
                        'type': company.get('properties', {}).get('type', '')
                    })
        except Exception as e:
            print(f"⚠️  Error fetching companies: {e}")
    elif args.use_recent_updates:
        print(f"📋 Fetching companies updated in last {args.days_back} days...")
        companies = get_companies_updated_recently(args.days_back, args.limit)
        print(f"✅ Found {len(companies)} companies updated recently\n")
    else:
        print(f"📋 Fetching companies from recent closed deals ({start_date} to {end_date})...")
        companies = get_companies_from_recent_deals(start_date, end_date, args.limit)
        print(f"✅ Found {len(companies)} companies from recent deals\n")
    
    if not companies:
        print("❌ No companies found to analyze")
        return
    
    # Analyze property history for each company
    print(f"📊 Analyzing industria field history for {len(companies)} companies...")
    print(f"   Looking for updates in the last {args.days_back} days...")
    print()
    
    results = []
    companies_with_history = 0
    companies_with_recent_updates = 0
    companies_without_history = 0
    
    for i, company in enumerate(companies, 1):
        if i % 10 == 0:
            print(f"   Processing {i}/{len(companies)}...", end='\r')
        
        company_id = str(company.get('company_id', ''))
        company_name = company.get('name', 'Unknown')
        
        analysis = analyze_industria_history(company_id, company_name, args.days_back)
        
        if analysis:
            companies_with_history += 1
            if analysis['has_recent_update']:
                companies_with_recent_updates += 1
            
            # Add current company data
            analysis.update({
                'current_industria': company.get('industria', ''),
                'current_type': company.get('type', ''),
                'has_type': bool(company.get('type', '').strip()),
                'deal_id': company.get('deal_id', ''),
                'deal_name': company.get('deal_name', '')
            })
            
            results.append(analysis)
        else:
            companies_without_history += 1
        
        time.sleep(0.1)  # Rate limiting
    
    print(f"\n✅ Analysis complete!\n")
    
    # Summary statistics
    print("="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    print()
    print(f"Total Companies Analyzed: {len(companies)}")
    print(f"Companies WITH Property History: {companies_with_history}")
    print(f"Companies WITHOUT Property History: {companies_without_history}")
    print(f"Companies WITH Recent Updates (last {args.days_back} days): {companies_with_recent_updates}")
    print()
    
    if results:
        # Recent updates statistics
        recent_results = [r for r in results if r['has_recent_update']]
        type_coverage_recent = sum(1 for r in recent_results if r['has_type'])
        type_coverage_all = sum(1 for r in results if r['has_type'])
        
        print("="*80)
        print("RECENT UPDATES ANALYSIS (Last {} days)".format(args.days_back))
        print("="*80)
        print()
        print(f"Companies Updated in Last {args.days_back} Days: {len(recent_results)}")
        print(f"Companies with Type Field Populated (from recent updates): {type_coverage_recent} ({type_coverage_recent/len(recent_results)*100:.1f}%)" if recent_results else "N/A")
        print()
        
        # Updates by day
        updates_by_day = defaultdict(int)
        for result in recent_results:
            if result['latest_recent_update_date']:
                day = result['latest_recent_update_date'].strftime('%Y-%m-%d')
                updates_by_day[day] += 1
        
        if updates_by_day:
            print("Updates by Day (Last {} days):".format(args.days_back))
            print()
            print("| Date | Companies Updated |")
            print("|------|-------------------|")
            for day in sorted(updates_by_day.keys(), reverse=True)[:14]:
                print(f"| {day} | {updates_by_day[day]} |")
            print()
        
        # Type field coverage
        print("="*80)
        print("ICP FIELD (TYPE) COVERAGE")
        print("="*80)
        print()
        print(f"Total Companies with History: {len(results)}")
        print(f"Companies WITH Type Field Populated: {type_coverage_all} ({type_coverage_all/len(results)*100:.1f}%)")
        print(f"Companies WITHOUT Type Field: {len(results) - type_coverage_all} ({(len(results) - type_coverage_all)/len(results)*100:.1f}%)")
        print()
        
        # Correlation: Recent updates vs Type field
        if recent_results:
            print("Correlation: Recent Updates → Type Field Population")
            print(f"  Companies updated recently AND have type field: {type_coverage_recent}/{len(recent_results)} ({type_coverage_recent/len(recent_results)*100:.1f}%)")
            print()
        
        # Sample companies with recent updates
        if recent_results:
            print("="*80)
            print(f"SAMPLE COMPANIES WITH RECENT UPDATES (Last {args.days_back} days)")
            print("="*80)
            print()
            print("| Company Name | Latest Update | Current Industria | Type Field |")
            print("|--------------|---------------|-------------------|------------|")
            for result in sorted(recent_results, key=lambda x: x['latest_recent_update_date'] if x['latest_recent_update_date'] else datetime.min, reverse=True)[:20]:
                update_date = result['latest_recent_update_date'].strftime('%Y-%m-%d %H:%M') if result['latest_recent_update_date'] else 'N/A'
                industria = result['current_industria'] or 'NULL'
                type_field = result['current_type'] or 'NULL'
                name = result['company_name'][:40]
                print(f"| {name} | {update_date} | {industria[:30]} | {type_field} |")
            print()
        
        # Save results to CSV
        output_dir = "tools/outputs"
        os.makedirs(output_dir, exist_ok=True)
        
        df_data = []
        for result in results:
            df_data.append({
                'company_id': result['company_id'],
                'company_name': result['company_name'],
                'current_industria': result['current_industria'],
                'current_type': result['current_type'],
                'has_type': result['has_type'],
                'total_updates': result['total_updates'],
                'recent_updates': result['recent_updates'],
                'has_recent_update': result['has_recent_update'],
                'latest_update_date': result['latest_update_date'].isoformat() if result['latest_update_date'] else '',
                'latest_recent_update_date': result['latest_recent_update_date'].isoformat() if result['latest_recent_update_date'] else '',
                'first_update_date': result['first_update_date'].isoformat() if result['first_update_date'] else '',
            })
        
        df = pd.DataFrame(df_data)
        output_file = f"{output_dir}/industria_field_history_analysis_{start_date.replace('-', '')}_{end_date.replace('-', '')}.csv"
        df.to_csv(output_file, index=False)
        print(f"📄 Results saved to CSV: {output_file}")
        print()

if __name__ == "__main__":
    main()
