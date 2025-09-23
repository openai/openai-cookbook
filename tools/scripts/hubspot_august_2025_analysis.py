#!/usr/bin/env python3
"""
HubSpot August 2025 Comprehensive Analysis
Analyzes contacts, deals, and companies created in August 2025
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict, Counter
import argparse

def load_hubspot_data():
    """Load HubSpot data from the API responses"""
    
    # Sample data structure - in real implementation, this would come from API calls
    contacts_data = {
        "results": [
            # This would be populated with actual API response data
        ]
    }
    
    deals_data = {
        "results": [
            # This would be populated with actual API response data  
        ]
    }
    
    companies_data = {
        "results": [
            # This would be populated with actual API response data
        ]
    }
    
    return contacts_data, deals_data, companies_data

def analyze_contacts(contacts: List[Dict]) -> Dict[str, Any]:
    """Analyze contacts created in August 2025"""
    
    analysis = {
        "total_contacts": len(contacts),
        "by_lifecycle_stage": Counter(),
        "by_source": Counter(),
        "utm_campaigns": Counter(),
        "utm_sources": Counter(),
        "utm_mediums": Counter(),
        "utm_terms": Counter(),
        "active_users": 0,
        "with_deals": 0,
        "by_day": defaultdict(int),
        "top_companies": Counter()
    }
    
    for contact in contacts:
        props = contact.get("properties", {})
        
        # Lifecycle stage
        lifecycle = props.get("lifecyclestage", "unknown")
        analysis["by_lifecycle_stage"][lifecycle] += 1
        
        # Source analysis
        source = props.get("hs_analytics_source", "unknown")
        analysis["by_source"][source] += 1
        
        # UTM analysis
        utm_campaign = props.get("utm_campaign", "")
        if utm_campaign:
            analysis["utm_campaigns"][utm_campaign] += 1
            
        utm_source = props.get("utm_source", "")
        if utm_source:
            analysis["utm_sources"][utm_source] += 1
            
        utm_medium = props.get("utm_medium", "")
        if utm_medium:
            analysis["utm_mediums"][utm_medium] += 1
            
        utm_term = props.get("utm_term", "")
        if utm_term:
            analysis["utm_terms"][utm_term] += 1
        
        # Active users
        if props.get("activo") == "true":
            analysis["active_users"] += 1
            
        # Users with deals
        num_deals = props.get("num_associated_deals", "0")
        if int(num_deals) > 0:
            analysis["with_deals"] += 1
            
        # Company analysis
        company = props.get("company", "")
        if company:
            analysis["top_companies"][company] += 1
            
        # Daily breakdown
        created_date = contact.get("createdAt", "")
        if created_date:
            day = created_date[:10]  # Extract YYYY-MM-DD
            analysis["by_day"][day] += 1
    
    return analysis

def analyze_deals(deals: List[Dict]) -> Dict[str, Any]:
    """Analyze deals created in August 2025"""
    
    analysis = {
        "total_deals": len(deals),
        "by_stage": Counter(),
        "by_type": Counter(),
        "by_source": Counter(),
        "total_amount": 0,
        "won_amount": 0,
        "lost_amount": 0,
        "by_day": defaultdict(int),
        "average_deal_size": 0,
        "won_deals": 0,
        "lost_deals": 0,
        "open_deals": 0
    }
    
    amounts = []
    
    for deal in deals:
        props = deal.get("properties", {})
        
        # Deal stage
        stage = props.get("dealstage", "unknown")
        analysis["by_stage"][stage] += 1
        
        # Deal type
        deal_type = props.get("dealtype", "unknown")
        analysis["by_type"][deal_type] += 1
        
        # Source analysis
        source = props.get("hs_analytics_source", "unknown")
        analysis["by_source"][source] += 1
        
        # Amount analysis
        amount_str = props.get("amount", "0")
        try:
            amount = float(amount_str)
            analysis["total_amount"] += amount
            amounts.append(amount)
            
            if stage == "closedwon":
                analysis["won_amount"] += amount
                analysis["won_deals"] += 1
            elif stage == "closedlost":
                analysis["lost_amount"] += amount
                analysis["lost_deals"] += 1
            else:
                analysis["open_deals"] += 1
                
        except (ValueError, TypeError):
            pass
            
        # Daily breakdown
        created_date = deal.get("createdAt", "")
        if created_date:
            day = created_date[:10]
            analysis["by_day"][day] += 1
    
    if amounts:
        analysis["average_deal_size"] = sum(amounts) / len(amounts)
    
    return analysis

def analyze_companies(companies: List[Dict]) -> Dict[str, Any]:
    """Analyze companies created in August 2025"""
    
    analysis = {
        "total_companies": len(companies),
        "by_lifecycle_stage": Counter(),
        "by_source": Counter(),
        "by_industry": Counter(),
        "with_deals": 0,
        "by_day": defaultdict(int),
        "domains": []
    }
    
    for company in companies:
        props = company.get("properties", {})
        
        # Lifecycle stage
        lifecycle = props.get("lifecyclestage", "unknown")
        analysis["by_lifecycle_stage"][lifecycle] += 1
        
        # Source analysis
        source = props.get("hs_analytics_source", "unknown")
        analysis["by_source"][source] += 1
        
        # Industry analysis
        industry = props.get("industry", "unknown")
        analysis["by_industry"][industry] += 1
        
        # Companies with deals
        num_deals = props.get("num_associated_deals", "0")
        if int(num_deals) > 0:
            analysis["with_deals"] += 1
            
        # Domain analysis
        domain = props.get("domain", "")
        if domain:
            analysis["domains"].append(domain)
            
        # Daily breakdown
        created_date = company.get("createdAt", "")
        if created_date:
            day = created_date[:10]
            analysis["by_day"][day] += 1
    
    return analysis

def format_currency(amount: float) -> str:
    """Format currency in Argentine pesos"""
    return f"${amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def format_number(num: float) -> str:
    """Format number with Argentine formatting"""
    return f"{num:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def print_analysis(contacts_analysis: Dict, deals_analysis: Dict, companies_analysis: Dict):
    """Print comprehensive analysis in readable format"""
    
    print("=" * 80)
    print("HUBSPOT AUGUST 2025 COMPREHENSIVE ANALYSIS")
    print("=" * 80)
    print()
    
    # CONTACTS ANALYSIS
    print("📊 CONTACTS ANALYSIS")
    print("-" * 40)
    print(f"Total Contacts Created: {contacts_analysis['total_contacts']:,}")
    print(f"Active Users: {contacts_analysis['active_users']:,}")
    print(f"Contacts with Deals: {contacts_analysis['with_deals']:,}")
    print()
    
    print("Lifecycle Stage Distribution:")
    for stage, count in contacts_analysis['by_lifecycle_stage'].most_common():
        percentage = (count / contacts_analysis['total_contacts']) * 100
        print(f"  {stage}: {count:,} ({percentage:.1f}%)")
    print()
    
    print("Top Traffic Sources:")
    for source, count in contacts_analysis['by_source'].most_common(10):
        percentage = (count / contacts_analysis['total_contacts']) * 100
        print(f"  {source}: {count:,} ({percentage:.1f}%)")
    print()
    
    print("Top UTM Campaigns:")
    for campaign, count in contacts_analysis['utm_campaigns'].most_common(10):
        print(f"  {campaign}: {count:,}")
    print()
    
    print("Top UTM Sources:")
    for source, count in contacts_analysis['utm_sources'].most_common(10):
        print(f"  {source}: {count:,}")
    print()
    
    print("Top UTM Terms:")
    for term, count in contacts_analysis['utm_terms'].most_common(10):
        print(f"  {term}: {count:,}")
    print()
    
    # DEALS ANALYSIS
    print("💰 DEALS ANALYSIS")
    print("-" * 40)
    print(f"Total Deals Created: {deals_analysis['total_deals']:,}")
    print(f"Total Deal Value: {format_currency(deals_analysis['total_amount'])}")
    print(f"Average Deal Size: {format_currency(deals_analysis['average_deal_size'])}")
    print()
    
    print("Deal Stage Distribution:")
    for stage, count in deals_analysis['by_stage'].most_common():
        percentage = (count / deals_analysis['total_deals']) * 100
        print(f"  {stage}: {count:,} ({percentage:.1f}%)")
    print()
    
    print("Deal Type Distribution:")
    for deal_type, count in deals_analysis['by_type'].most_common():
        percentage = (count / deals_analysis['total_deals']) * 100
        print(f"  {deal_type}: {count:,} ({percentage:.1f}%)")
    print()
    
    print("Deal Source Distribution:")
    for source, count in deals_analysis['by_source'].most_common(10):
        percentage = (count / deals_analysis['total_deals']) * 100
        print(f"  {source}: {count:,} ({percentage:.1f}%)")
    print()
    
    print("Deal Performance:")
    print(f"  Won Deals: {deals_analysis['won_deals']:,} ({format_currency(deals_analysis['won_amount'])})")
    print(f"  Lost Deals: {deals_analysis['lost_deals']:,} ({format_currency(deals_analysis['lost_amount'])})")
    print(f"  Open Deals: {deals_analysis['open_deals']:,}")
    
    if deals_analysis['won_deals'] + deals_analysis['lost_deals'] > 0:
        win_rate = (deals_analysis['won_deals'] / (deals_analysis['won_deals'] + deals_analysis['lost_deals'])) * 100
        print(f"  Win Rate: {win_rate:.1f}%")
    print()
    
    # COMPANIES ANALYSIS
    print("🏢 COMPANIES ANALYSIS")
    print("-" * 40)
    print(f"Total Companies Created: {companies_analysis['total_companies']:,}")
    print(f"Companies with Deals: {companies_analysis['with_deals']:,}")
    print()
    
    print("Company Lifecycle Stage Distribution:")
    for stage, count in companies_analysis['by_lifecycle_stage'].most_common():
        percentage = (count / companies_analysis['total_companies']) * 100
        print(f"  {stage}: {count:,} ({percentage:.1f}%)")
    print()
    
    print("Company Source Distribution:")
    for source, count in companies_analysis['by_source'].most_common(10):
        percentage = (count / companies_analysis['total_companies']) * 100
        print(f"  {source}: {count:,} ({percentage:.1f}%)")
    print()
    
    print("Top Industries:")
    for industry, count in companies_analysis['by_industry'].most_common(10):
        percentage = (count / companies_analysis['total_companies']) * 100
        print(f"  {industry}: {count:,} ({percentage:.1f}%)")
    print()
    
    # DAILY BREAKDOWN
    print("📅 DAILY BREAKDOWN (Top 10 Days)")
    print("-" * 40)
    
    # Combine daily data from all sources
    daily_totals = defaultdict(int)
    for day, count in contacts_analysis['by_day'].items():
        daily_totals[day] += count
    for day, count in deals_analysis['by_day'].items():
        daily_totals[day] += count
    for day, count in companies_analysis['by_day'].items():
        daily_totals[day] += count
    
    for day, total in sorted(daily_totals.items(), key=lambda x: x[1], reverse=True)[:10]:
        contacts_day = contacts_analysis['by_day'].get(day, 0)
        deals_day = deals_analysis['by_day'].get(day, 0)
        companies_day = companies_analysis['by_day'].get(day, 0)
        print(f"  {day}: {total:,} total ({contacts_day:,} contacts, {deals_day:,} deals, {companies_day:,} companies)")
    print()
    
    # KEY INSIGHTS
    print("🔍 KEY INSIGHTS")
    print("-" * 40)
    
    # Calculate conversion rates
    contact_to_deal_rate = (contacts_analysis['with_deals'] / contacts_analysis['total_contacts']) * 100 if contacts_analysis['total_contacts'] > 0 else 0
    company_to_deal_rate = (companies_analysis['with_deals'] / companies_analysis['total_companies']) * 100 if companies_analysis['total_companies'] > 0 else 0
    
    print(f"Contact-to-Deal Conversion Rate: {contact_to_deal_rate:.1f}%")
    print(f"Company-to-Deal Conversion Rate: {company_to_deal_rate:.1f}%")
    
    # Top performing sources
    top_contact_source = contacts_analysis['by_source'].most_common(1)[0] if contacts_analysis['by_source'] else ("None", 0)
    top_deal_source = deals_analysis['by_source'].most_common(1)[0] if deals_analysis['by_source'] else ("None", 0)
    
    print(f"Top Contact Source: {top_contact_source[0]} ({top_contact_source[1]:,} contacts)")
    print(f"Top Deal Source: {top_deal_source[0]} ({top_deal_source[1]:,} deals)")
    
    # UTM performance
    if contacts_analysis['utm_campaigns']:
        top_utm_campaign = contacts_analysis['utm_campaigns'].most_common(1)[0]
        print(f"Top UTM Campaign: {top_utm_campaign[0]} ({top_utm_campaign[1]:,} contacts)")
    
    print()
    print("=" * 80)

def main():
    """Main analysis function"""
    parser = argparse.ArgumentParser(description="Analyze HubSpot August 2025 data")
    parser.add_argument("--output", "-o", help="Output file path (optional)")
    args = parser.parse_args()
    
    # Load data (in real implementation, this would call HubSpot API)
    contacts_data, deals_data, companies_data = load_hubspot_data()
    
    # Analyze data
    contacts_analysis = analyze_contacts(contacts_data["results"])
    deals_analysis = analyze_deals(deals_data["results"])
    companies_analysis = analyze_companies(companies_data["results"])
    
    # Print analysis
    print_analysis(contacts_analysis, deals_analysis, companies_analysis)
    
    # Save to file if requested
    if args.output:
        analysis_data = {
            "contacts": contacts_analysis,
            "deals": deals_analysis,
            "companies": companies_analysis,
            "generated_at": datetime.now().isoformat()
        }
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"Analysis saved to: {args.output}")

if __name__ == "__main__":
    main()
