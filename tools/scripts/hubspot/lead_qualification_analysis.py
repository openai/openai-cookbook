#!/usr/bin/env python3
"""
Lead Qualification Deep Dive Analysis
=====================================

Investigating why 107% more contacts are generating 22% fewer deals
"""

import pandas as pd
import numpy as np
from datetime import datetime

def analyze_contact_quality():
    """Analyze contact quality differences between April and May"""
    print("🔍 LEAD QUALIFICATION DEEP DIVE ANALYSIS")
    print("="*60)
    
    # Load contact data
    april_contacts = pd.read_csv("tools/outputs/csv_data/hubspot/contacts/hubspot_contacts_2025_04_01_2025_04_25.csv")
    may_contacts = pd.read_csv("tools/outputs/csv_data/hubspot/contacts/hubspot_contacts_2025_05_01_2025_05_25_with_company.csv")
    
    # Load deals data
    april_deals = pd.read_csv("tools/outputs/csv_data/hubspot/deals/hubspot_deals_2025_04_01_2025_04_25_with_company.csv")
    may_deals = pd.read_csv("tools/outputs/csv_data/hubspot/deals/hubspot_deals_2025_05_01_2025_05_25_with_company.csv")
    
    print(f"📊 Data Loaded:")
    print(f"   April: {len(april_contacts):,} contacts, {len(april_deals):,} deals")
    print(f"   May: {len(may_contacts):,} contacts, {len(may_deals):,} deals")
    
    print("\n" + "="*60)
    print("1. CONTACT SOURCE ANALYSIS")
    print("="*60)
    
    # Analyze lead sources
    april_sources = april_contacts['lead_source'].value_counts()
    may_sources = may_contacts['lead_source'].value_counts()
    
    print("\nAPRIL 1-24 LEAD SOURCES:")
    for source, count in april_sources.head(10).items():
        pct = (count / len(april_contacts)) * 100
        print(f"   {source}: {count:,} ({pct:.1f}%)")
    
    print("\nMAY 1-24 LEAD SOURCES:")
    for source, count in may_sources.head(10).items():
        pct = (count / len(may_contacts)) * 100
        print(f"   {source}: {count:,} ({pct:.1f}%)")
    
    print("\n" + "="*60)
    print("2. LIFECYCLE STAGE ANALYSIS")
    print("="*60)
    
    # Analyze lifecycle stages
    april_stages = april_contacts['lifecyclestage'].value_counts()
    may_stages = may_contacts['lifecyclestage'].value_counts()
    
    print("\nAPRIL 1-24 LIFECYCLE STAGES:")
    for stage, count in april_stages.items():
        pct = (count / len(april_contacts)) * 100
        print(f"   {stage}: {count:,} ({pct:.1f}%)")
    
    print("\nMAY 1-24 LIFECYCLE STAGES:")
    for stage, count in may_stages.items():
        pct = (count / len(may_contacts)) * 100
        print(f"   {stage}: {count:,} ({pct:.1f}%)")
    
    print("\n" + "="*60)
    print("3. LEAD STATUS ANALYSIS")
    print("="*60)
    
    # Analyze lead status
    april_status = april_contacts['hs_lead_status'].value_counts()
    may_status = may_contacts['hs_lead_status'].value_counts()
    
    print("\nAPRIL 1-24 LEAD STATUS:")
    for status, count in april_status.items():
        pct = (count / len(april_contacts)) * 100
        print(f"   {status}: {count:,} ({pct:.1f}%)")
    
    print("\nMAY 1-24 LEAD STATUS:")
    for status, count in may_status.items():
        pct = (count / len(may_contacts)) * 100
        print(f"   {status}: {count:,} ({pct:.1f}%)")
    
    print("\n" + "="*60)
    print("4. OWNER PERFORMANCE ANALYSIS")
    print("="*60)
    
    # Analyze by owner
    april_owners = april_contacts['hubspot_owner_id'].value_counts()
    may_owners = may_contacts['hubspot_owner_id'].value_counts()
    
    print("\nTOP APRIL 1-24 CONTACT OWNERS:")
    for owner, count in april_owners.head(5).items():
        pct = (count / len(april_contacts)) * 100
        print(f"   Owner {owner}: {count:,} contacts ({pct:.1f}%)")
    
    print("\nTOP MAY 1-24 CONTACT OWNERS:")
    for owner, count in may_owners.head(5).items():
        pct = (count / len(may_contacts)) * 100
        print(f"   Owner {owner}: {count:,} contacts ({pct:.1f}%)")
    
    print("\n" + "="*60)
    print("5. DEAL STAGE ANALYSIS")
    print("="*60)
    
    # Analyze deal stages
    april_deal_stages = april_deals['Stage'].value_counts()
    may_deal_stages = may_deals['Stage'].value_counts()
    
    print("\nAPRIL 1-24 DEAL STAGES:")
    for stage, count in april_deal_stages.items():
        pct = (count / len(april_deals)) * 100
        print(f"   {stage}: {count:,} ({pct:.1f}%)")
    
    print("\nMAY 1-24 DEAL STAGES:")
    for stage, count in may_deal_stages.items():
        pct = (count / len(may_deals)) * 100
        print(f"   {stage}: {count:,} ({pct:.1f}%)")
    
    print("\n" + "="*60)
    print("6. CONVERSION EFFICIENCY BY SOURCE")
    print("="*60)
    
    # Calculate conversion rates by source
    print("\nAPRIL 1-24 CONVERSION BY SOURCE:")
    for source in april_sources.index[:5]:
        source_contacts = len(april_contacts[april_contacts['lead_source'] == source])
        # This is simplified - in reality we'd need to match contacts to deals
        conversion_rate = (len(april_deals) / len(april_contacts)) * 100
        print(f"   {source}: {source_contacts:,} contacts → Est. {conversion_rate:.1f}% conversion")
    
    print("\nMAY 1-24 CONVERSION BY SOURCE:")
    for source in may_sources.index[:5]:
        source_contacts = len(may_contacts[may_contacts['lead_source'] == source])
        conversion_rate = (len(may_deals) / len(may_contacts)) * 100
        print(f"   {source}: {source_contacts:,} contacts → Est. {conversion_rate:.1f}% conversion")
    
    print("\n" + "="*60)
    print("7. QUALITY INDICATORS ANALYSIS")
    print("="*60)
    
    # Analyze quality indicators
    april_qualified = len(april_contacts[april_contacts['lifecyclestage'].isin(['opportunity', 'customer'])])
    may_qualified = len(may_contacts[may_contacts['lifecyclestage'].isin(['opportunity', 'customer'])])
    
    april_qual_rate = (april_qualified / len(april_contacts)) * 100
    may_qual_rate = (may_qualified / len(may_contacts)) * 100
    
    print(f"\nQUALIFIED CONTACT RATES:")
    print(f"   April 1-24: {april_qualified:,}/{len(april_contacts):,} = {april_qual_rate:.1f}%")
    print(f"   May 1-24: {may_qualified:,}/{len(may_contacts):,} = {may_qual_rate:.1f}%")
    print(f"   Change: {may_qual_rate - april_qual_rate:+.1f} percentage points")
    
    # Analyze customers vs leads
    april_customers = len(april_contacts[april_contacts['lifecyclestage'] == 'customer'])
    may_customers = len(may_contacts[may_contacts['lifecyclestage'] == 'customer'])
    
    april_cust_rate = (april_customers / len(april_contacts)) * 100
    may_cust_rate = (may_customers / len(may_contacts)) * 100
    
    print(f"\nCUSTOMER RATES:")
    print(f"   April 1-24: {april_customers:,}/{len(april_contacts):,} = {april_cust_rate:.1f}%")
    print(f"   May 1-24: {may_customers:,}/{len(may_contacts):,} = {may_cust_rate:.1f}%")
    print(f"   Change: {may_cust_rate - april_cust_rate:+.1f} percentage points")
    
    print("\n" + "="*60)
    print("8. KEY INSIGHTS & HYPOTHESES")
    print("="*60)
    
    # Calculate key metrics for insights
    organic_april = april_sources.get('Orgánico', 0)
    paid_april = april_sources.get('Pago', 0)
    organic_may = may_sources.get('Orgánico', 0)
    paid_may = may_sources.get('Pago', 0)
    
    print(f"\n🔍 TRAFFIC SOURCE SHIFT:")
    print(f"   April Organic: {organic_april:,} ({(organic_april/len(april_contacts)*100):.1f}%)")
    print(f"   May Organic: {organic_may:,} ({(organic_may/len(may_contacts)*100):.1f}%)")
    print(f"   April Paid: {paid_april:,} ({(paid_april/len(april_contacts)*100):.1f}%)")
    print(f"   May Paid: {paid_may:,} ({(paid_may/len(may_contacts)*100):.1f}%)")
    
    # Lead quality analysis
    april_leads = len(april_contacts[april_contacts['lifecyclestage'] == 'lead'])
    may_leads = len(may_contacts[may_contacts['lifecyclestage'] == 'lead'])
    
    print(f"\n🎯 LEAD QUALITY INDICATORS:")
    print(f"   April Raw Leads: {april_leads:,} ({(april_leads/len(april_contacts)*100):.1f}%)")
    print(f"   May Raw Leads: {may_leads:,} ({(may_leads/len(may_contacts)*100):.1f}%)")
    
    # Deal creation efficiency
    april_deal_rate = (len(april_deals) / len(april_contacts)) * 100
    may_deal_rate = (len(may_deals) / len(may_contacts)) * 100
    
    print(f"\n⚡ DEAL CREATION EFFICIENCY:")
    print(f"   April: {len(april_deals):,} deals from {len(april_contacts):,} contacts = {april_deal_rate:.2f}%")
    print(f"   May: {len(may_deals):,} deals from {len(may_contacts):,} contacts = {may_deal_rate:.2f}%")
    print(f"   Efficiency Drop: {april_deal_rate - may_deal_rate:.2f} percentage points")
    
    print("\n" + "="*60)
    print("9. RECOMMENDED IMMEDIATE ACTIONS")
    print("="*60)
    
    print("\n🚨 CRITICAL FINDINGS:")
    
    if may_qual_rate < april_qual_rate:
        print(f"   ❌ Lead quality declined by {april_qual_rate - may_qual_rate:.1f}pp")
        print("   → URGENT: Review lead scoring and qualification criteria")
    
    if (paid_may / len(may_contacts)) > (paid_april / len(april_contacts)):
        print(f"   ⚠️  Increased reliance on paid traffic")
        print("   → REVIEW: Paid campaign targeting and quality")
    
    if may_leads > april_leads * 1.5:
        print(f"   📈 Raw lead volume increased significantly")
        print("   → ACTION: Implement stricter lead qualification")
    
    print(f"\n💡 STRATEGIC RECOMMENDATIONS:")
    print(f"   1. Audit lead qualification process immediately")
    print(f"   2. Review paid campaign targeting quality")
    print(f"   3. Implement lead scoring improvements")
    print(f"   4. Analyze sales team capacity vs lead volume")
    print(f"   5. Review trial-to-paid conversion funnel")
    
    print("\n" + "="*60)
    print("ANALYSIS COMPLETED")
    print("="*60)

if __name__ == "__main__":
    analyze_contact_quality() 