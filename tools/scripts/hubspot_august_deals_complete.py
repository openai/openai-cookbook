#!/usr/bin/env python3
"""
Complete HubSpot August 2025 Deals Retrieval with Pagination
Retrieves ALL deals created in August 2025 using proper pagination
"""

import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Any
import time

def get_hubspot_token() -> str:
    """Get HubSpot token from environment"""
    token = os.environ.get('HUBSPOT_API_KEY')
    if not token:
        raise ValueError("HUBSPOT_API_KEY environment variable not set")
    return token

def fetch_all_deals_august_2025(token: str) -> List[Dict]:
    """Fetch ALL deals created in August 2025 with proper pagination"""
    
    url = "https://api.hubapi.com/crm/v3/objects/deals/search"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Search payload for August 2025
    search_payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "createdate",
                        "operator": "GTE",
                        "value": "2025-08-01T00:00:00.000Z"
                    },
                    {
                        "propertyName": "createdate", 
                        "operator": "LTE",
                        "value": "2025-08-31T23:59:59.999Z"
                    }
                ]
            }
        ],
        "properties": [
            "dealname",
            "dealstage",
            "amount",
            "closedate",
            "createdate",
            "pipeline",
            "dealtype",
            "hs_analytics_source",
            "hs_analytics_source_data_1",
            "hs_analytics_source_data_2",
            "description",
            "hubspot_owner_id",
            "hs_deal_stage_probability",
            "hs_forecast_probability",
            "hs_forecast_category",
            "hs_deal_amount_calculation_preference",
            "hs_next_step",
            "hs_notes_last_contacted",
            "hs_notes_last_activity_date",
            "hs_notes_next_activity_date",
            "hs_sales_email_last_replied",
            "hs_analytics_source",
            "hs_analytics_source_data_1",
            "hs_analytics_source_data_2",
            "hs_analytics_source_data_3",
            "hs_analytics_source_data_4",
            "hs_analytics_source_data_5",
            "hs_analytics_source_data_6",
            "hs_analytics_source_data_7",
            "hs_analytics_source_data_8",
            "hs_analytics_source_data_9",
            "hs_analytics_source_data_10"
        ],
        "limit": 100
    }
    
    all_deals = []
    after = None
    page = 1
    
    print(f"🔍 Starting deals retrieval for August 2025...")
    
    while True:
        if after:
            search_payload["after"] = after
            
        print(f"📄 Fetching page {page}...")
        
        try:
            response = requests.post(url, headers=headers, json=search_payload)
            response.raise_for_status()
            
            data = response.json()
            deals = data.get("results", [])
            
            if not deals:
                print(f"✅ No more deals found. Total retrieved: {len(all_deals)}")
                break
                
            all_deals.extend(deals)
            print(f"   📊 Retrieved {len(deals)} deals (Total: {len(all_deals)})")
            
            # Check for pagination
            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            
            if not after:
                print(f"✅ All deals retrieved. Total: {len(all_deals)}")
                break
                
            page += 1
            time.sleep(0.1)  # Rate limiting
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching deals: {e}")
            break
    
    return all_deals

def analyze_deals(deals: List[Dict]) -> Dict[str, Any]:
    """Analyze the deals data"""
    
    analysis = {
        "total_deals": len(deals),
        "with_amount": 0,
        "with_close_date": 0,
        "with_description": 0,
        "with_owner": 0,
        "total_amount": 0,
        "average_amount": 0,
        "deal_stages": {},
        "pipelines": {},
        "deal_types": {},
        "sources": {},
        "forecast_categories": {},
        "amount_ranges": {},
        "closed_won_amount": 0,
        "closed_lost_amount": 0,
        "open_deals_amount": 0
    }
    
    amounts = []
    
    for deal in deals:
        props = deal.get("properties", {})
        
        # Basic stats
        if props.get("amount"):
            analysis["with_amount"] += 1
            try:
                amount = float(props["amount"])
                amounts.append(amount)
                analysis["total_amount"] += amount
            except:
                pass
                
        if props.get("closedate"):
            analysis["with_close_date"] += 1
            
        if props.get("description"):
            analysis["with_description"] += 1
            
        if props.get("hubspot_owner_id"):
            analysis["with_owner"] += 1
            
        # Deal stages
        stage = props.get("dealstage", "Unknown")
        analysis["deal_stages"][stage] = analysis["deal_stages"].get(stage, 0) + 1
        
        # Pipelines
        pipeline = props.get("pipeline", "Unknown")
        analysis["pipelines"][pipeline] = analysis["pipelines"].get(pipeline, 0) + 1
        
        # Deal types
        deal_type = props.get("dealtype", "Unknown")
        analysis["deal_types"][deal_type] = analysis["deal_types"].get(deal_type, 0) + 1
        
        # Sources
        source = props.get("hs_analytics_source", "Unknown")
        analysis["sources"][source] = analysis["sources"].get(source, 0) + 1
        
        # Forecast categories
        forecast = props.get("hs_forecast_category", "Unknown")
        analysis["forecast_categories"][forecast] = analysis["forecast_categories"].get(forecast, 0) + 1
        
        # Amount ranges
        if props.get("amount"):
            try:
                amount = float(props["amount"])
                if amount < 10000:
                    range_key = "< $10K"
                elif amount < 50000:
                    range_key = "$10K - $50K"
                elif amount < 100000:
                    range_key = "$50K - $100K"
                elif amount < 500000:
                    range_key = "$100K - $500K"
                else:
                    range_key = "> $500K"
                analysis["amount_ranges"][range_key] = analysis["amount_ranges"].get(range_key, 0) + 1
                
                # Categorize by stage for revenue analysis
                stage = props.get("dealstage", "").lower()
                if "closed won" in stage or "won" in stage:
                    analysis["closed_won_amount"] += amount
                elif "closed lost" in stage or "lost" in stage:
                    analysis["closed_lost_amount"] += amount
                else:
                    analysis["open_deals_amount"] += amount
                    
            except:
                pass
    
    # Calculate average
    if amounts:
        analysis["average_amount"] = sum(amounts) / len(amounts)
    
    return analysis

def print_analysis(analysis: Dict[str, Any]):
    """Print the analysis results"""
    
    print(f"\n📊 DEALS ANALYSIS RESULTS")
    print("=" * 50)
    
    print(f"\n📈 SUMMARY STATISTICS")
    print("-" * 30)
    print(f"Total Deals: {analysis['total_deals']:,}")
    print(f"With Amount: {analysis['with_amount']:,} ({analysis['with_amount']/analysis['total_deals']*100:.1f}%)")
    print(f"With Close Date: {analysis['with_close_date']:,} ({analysis['with_close_date']/analysis['total_deals']*100:.1f}%)")
    print(f"With Description: {analysis['with_description']:,} ({analysis['with_description']/analysis['total_deals']*100:.1f}%)")
    print(f"With Owner: {analysis['with_owner']:,} ({analysis['with_owner']/analysis['total_deals']*100:.1f}%)")
    
    print(f"\n💰 REVENUE ANALYSIS")
    print("-" * 30)
    print(f"Total Deal Value: ${analysis['total_amount']:,.2f}")
    print(f"Average Deal Size: ${analysis['average_amount']:,.2f}")
    print(f"Closed Won Amount: ${analysis['closed_won_amount']:,.2f}")
    print(f"Closed Lost Amount: ${analysis['closed_lost_amount']:,.2f}")
    print(f"Open Deals Amount: ${analysis['open_deals_amount']:,.2f}")
    
    if analysis['deal_stages']:
        print(f"\n🎯 DEAL STAGES")
        print("-" * 30)
        for stage, count in sorted(analysis['deal_stages'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {stage}: {count:,}")
    
    if analysis['pipelines']:
        print(f"\n🔄 PIPELINES")
        print("-" * 30)
        for pipeline, count in sorted(analysis['pipelines'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {pipeline}: {count:,}")
    
    if analysis['deal_types']:
        print(f"\n📋 DEAL TYPES")
        print("-" * 30)
        for deal_type, count in sorted(analysis['deal_types'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {deal_type}: {count:,}")
    
    if analysis['sources']:
        print(f"\n📡 TRAFFIC SOURCES")
        print("-" * 30)
        for source, count in sorted(analysis['sources'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {source}: {count:,}")
    
    if analysis['forecast_categories']:
        print(f"\n📊 FORECAST CATEGORIES")
        print("-" * 30)
        for forecast, count in sorted(analysis['forecast_categories'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {forecast}: {count:,}")
    
    if analysis['amount_ranges']:
        print(f"\n💰 DEAL SIZE RANGES")
        print("-" * 30)
        for range_key, count in sorted(analysis['amount_ranges'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {range_key}: {count:,}")

def main():
    """Main function"""
    try:
        # Get token
        token = get_hubspot_token()
        
        # Fetch all deals
        deals = fetch_all_deals_august_2025(token)
        
        if not deals:
            print("❌ No deals found for August 2025")
            return
            
        # Analyze data
        analysis = analyze_deals(deals)
        
        # Print analysis
        print_analysis(analysis)
        
        # Save raw data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"hubspot_august_2025_deals_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(deals, f, indent=2, ensure_ascii=False)
            
        print(f"\n💾 Raw data saved to: {filename}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
