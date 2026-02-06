#!/usr/bin/env python3
import os
import sys
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import time

load_dotenv()
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
HUBSPOT_BASE_URL = 'https://api.hubapi.com'
HEADERS = {
    'Authorization': f'Bearer {HUBSPOT_API_KEY}',
    'Content-Type': 'application/json'
}

def is_likely_direct_deal(deal_properties):
    """
    Determine if deal was likely created directly (not from contact conversion)
    using ONLY deal-level properties.
    """
    props = deal_properties
    
    # Indicator 1: Deal type suggests existing customer
    dealtype = props.get('dealtype', '')
    if dealtype and dealtype.lower() in ['upsell', 'existing business', 'add-on', 'renewal']:
        return True
    
    # Indicator 2: Pipeline suggests direct creation
    pipeline = props.get('pipeline', '')
    if pipeline and ('upsell' in pipeline.lower() or 'direct' in pipeline.lower() or 'existing' in pipeline.lower()):
        return True
    
    # Indicator 3: Analytics source is empty (no contact attribution)
    analytics_source = props.get('hs_analytics_source', '')
    if not analytics_source or analytics_source.strip() == '':
        # Combined with empty lead_source, more likely direct
        lead_source = props.get('lead_source', '')
        if not lead_source or lead_source.strip() == '':
            return True
    
    return False

def analyze_direct_deals_lead_source(start_date, end_date):
    """
    Analyze deals created in period to identify likely direct deals
    and their lead_source distribution.
    """
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T00:00:00+00:00")
    
    print("="*80)
    print("DIRECT DEALS LEAD SOURCE ANALYSIS")
    print("="*80)
    print(f"Period: {start_date} to {end_date}")
    print()
    print("IDENTIFICATION METHOD:")
    print("Using deal-level properties to identify likely direct deals:")
    print("1. dealtype indicates existing customer (Upsell, Existing Business, Add-on, Renewal)")
    print("2. pipeline contains 'upsell', 'direct', or 'existing'")
    print("3. Both hs_analytics_source AND lead_source are empty")
    print()
    
    # Fetch all deals created in period
    url_deals = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/search"
    
    all_deals = []
    after = None
    
    print("📊 Fetching all deals created in period...")
    while True:
        filters = [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
            {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"}
        ]
        
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": [
                "dealname", "createdate", "dealstage", "pipeline", "dealtype",
                "lead_source", "hs_analytics_source", "amount", "closedate"
            ],
            "limit": 100
        }
        if after:
            payload["after"] = after
        
        try:
            response = requests.post(url_deals, headers=HEADERS, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            all_deals.extend(results)
            
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after:
                break
            time.sleep(0.2)
        except Exception as e:
            print(f"   ⚠️  Error fetching deals: {str(e)}")
            break
    
    print(f"   Found {len(all_deals)} total deals created in period")
    print()
    
    # First, let's see what dealtype and pipeline values exist
    print("📊 Analyzing dealtype and pipeline values...")
    dealtype_dist = {}
    pipeline_dist = {}
    empty_analytics = 0
    empty_lead_source = 0
    both_empty = 0
    
    for deal in all_deals:
        props = deal.get('properties', {})
        
        dealtype = props.get('dealtype', 'NULL/EMPTY')
        if dealtype not in dealtype_dist:
            dealtype_dist[dealtype] = 0
        dealtype_dist[dealtype] += 1
        
        pipeline = props.get('pipeline', 'NULL/EMPTY')
        if pipeline not in pipeline_dist:
            pipeline_dist[pipeline] = 0
        pipeline_dist[pipeline] += 1
        
        analytics_source = props.get('hs_analytics_source', '')
        lead_source = props.get('lead_source', '')
        
        if not analytics_source or analytics_source.strip() == '':
            empty_analytics += 1
        if not lead_source or lead_source.strip() == '':
            empty_lead_source += 1
        if (not analytics_source or analytics_source.strip() == '') and (not lead_source or lead_source.strip() == ''):
            both_empty += 1
    
    print(f"   Deals with empty hs_analytics_source: {empty_analytics} ({empty_analytics/len(all_deals)*100:.1f}%)")
    print(f"   Deals with empty lead_source: {empty_lead_source} ({empty_lead_source/len(all_deals)*100:.1f}%)")
    print(f"   Deals with BOTH empty: {both_empty} ({both_empty/len(all_deals)*100:.1f}%)")
    print()
    
    print("Dealtype Distribution:")
    sorted_dealtypes = sorted(dealtype_dist.items(), key=lambda x: x[1], reverse=True)
    for dealtype, count in sorted_dealtypes[:10]:
        print(f"   {dealtype}: {count}")
    print()
    
    print("Pipeline Distribution:")
    sorted_pipelines = sorted(pipeline_dist.items(), key=lambda x: x[1], reverse=True)
    for pipeline, count in sorted_pipelines[:10]:
        print(f"   {pipeline}: {count}")
    print()
    
    # Identify likely direct deals
    # Based on findings: "Cross Selling" dealtype likely indicates direct deals
    direct_deals = []
    other_deals = []
    
    for deal in all_deals:
        props = deal.get('properties', {})
        dealtype = props.get('dealtype', '')
        
        # Cross Selling is likely a direct deal (upsell/add-on)
        if dealtype == 'Cross Selling':
            direct_deals.append(deal)
        elif is_likely_direct_deal(props):
            direct_deals.append(deal)
        else:
            other_deals.append(deal)
    
    # Also check deals with both empty analytics_source and lead_source
    print("="*80)
    print("DEALS WITH BOTH EMPTY ANALYTICS_SOURCE AND LEAD_SOURCE")
    print("="*80)
    print("(These might be direct deals)")
    print()
    
    both_empty_deals = []
    for deal in all_deals:
        props = deal.get('properties', {})
        analytics_source = props.get('hs_analytics_source', '')
        lead_source = props.get('lead_source', '')
        if (not analytics_source or analytics_source.strip() == '') and (not lead_source or lead_source.strip() == ''):
            both_empty_deals.append(deal)
    
    print(f"Found {len(both_empty_deals)} deals with both empty analytics_source and lead_source")
    print()
    
    # Analyze lead_source for these deals (should all be empty, but let's check)
    both_empty_lead_source_dist = {}
    for deal in both_empty_deals:
        props = deal.get('properties', {})
        lead_source = props.get('lead_source', '')
        if not lead_source or lead_source.strip() == '':
            lead_source = 'NULL/EMPTY'
        else:
            lead_source = lead_source.strip()
        
        if lead_source not in both_empty_lead_source_dist:
            both_empty_lead_source_dist[lead_source] = 0
        both_empty_lead_source_dist[lead_source] += 1
    
    print("Lead Source for deals with both empty:")
    for lead_source, count in sorted(both_empty_lead_source_dist.items(), key=lambda x: x[1], reverse=True):
        print(f"   {lead_source}: {count}")
    print()
    
    print(f"📊 Analysis Results:")
    print(f"   Likely Direct Deals: {len(direct_deals)}")
    print(f"   Other Deals: {len(other_deals)}")
    print()
    
    # Analyze lead_source distribution for direct deals
    print("="*80)
    print("LEAD SOURCE DISTRIBUTION - DIRECT DEALS")
    print("="*80)
    print()
    
    lead_source_dist = {}
    empty_lead_source = 0
    
    for deal in direct_deals:
        props = deal.get('properties', {})
        lead_source = props.get('lead_source', '')
        
        if not lead_source or lead_source.strip() == '':
            empty_lead_source += 1
            lead_source = 'NULL/EMPTY'
        else:
            lead_source = lead_source.strip()
        
        if lead_source not in lead_source_dist:
            lead_source_dist[lead_source] = 0
        lead_source_dist[lead_source] += 1
    
    # Sort by count
    sorted_sources = sorted(lead_source_dist.items(), key=lambda x: x[1], reverse=True)
    
    print("| Lead Source | Count | Percentage |")
    print("|-------------|-------|------------|")
    for lead_source, count in sorted_sources:
        percentage = (count / len(direct_deals) * 100) if direct_deals else 0
        print(f"| {lead_source} | {count} | {percentage:.1f}% |")
    print()
    
    # Show some examples
    print("="*80)
    print("SAMPLE DIRECT DEALS (First 10)")
    print("="*80)
    print()
    
    for i, deal in enumerate(direct_deals[:10], 1):
        props = deal.get('properties', {})
        deal_id = deal.get('id')
        deal_name = props.get('dealname', 'N/A')
        dealtype = props.get('dealtype', 'N/A')
        pipeline = props.get('pipeline', 'N/A')
        lead_source = props.get('lead_source', 'NULL/EMPTY')
        analytics_source = props.get('hs_analytics_source', 'NULL/EMPTY')
        
        print(f"{i}. Deal ID: {deal_id}")
        print(f"   Name: {deal_name}")
        print(f"   Deal Type: {dealtype}")
        print(f"   Pipeline: {pipeline}")
        print(f"   Lead Source: {lead_source}")
        print(f"   Analytics Source: {analytics_source}")
        print()
    
    # Compare with other deals
    print("="*80)
    print("LEAD SOURCE DISTRIBUTION - OTHER DEALS (For Comparison)")
    print("="*80)
    print()
    
    other_lead_source_dist = {}
    other_empty = 0
    
    for deal in other_deals:
        props = deal.get('properties', {})
        lead_source = props.get('lead_source', '')
        
        if not lead_source or lead_source.strip() == '':
            other_empty += 1
            lead_source = 'NULL/EMPTY'
        else:
            lead_source = lead_source.strip()
        
        if lead_source not in other_lead_source_dist:
            other_lead_source_dist[lead_source] = 0
        other_lead_source_dist[lead_source] += 1
    
    sorted_other = sorted(other_lead_source_dist.items(), key=lambda x: x[1], reverse=True)
    
    print("| Lead Source | Count | Percentage |")
    print("|-------------|-------|------------|")
    for lead_source, count in sorted_other[:15]:  # Top 15
        percentage = (count / len(other_deals) * 100) if other_deals else 0
        print(f"| {lead_source} | {count} | {percentage:.1f}% |")
    print()
    
    return {
        'direct_deals': direct_deals,
        'other_deals': other_deals,
        'direct_lead_source_dist': lead_source_dist,
        'other_lead_source_dist': other_lead_source_dist
    }

if __name__ == '__main__':
    # December 2025
    start_date = '2025-12-01'
    end_date = '2026-01-01'
    
    results = analyze_direct_deals_lead_source(start_date, end_date)
