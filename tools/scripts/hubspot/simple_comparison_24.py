#!/usr/bin/env python3
"""
Simple HubSpot April 1-24 vs May 1-24, 2025 Comparison
"""

import pandas as pd

def main():
    print("HubSpot April 1-24 vs May 1-24, 2025 Conversion Comparison Analysis")
    print("="*70)
    
    # Load data
    april_df = pd.read_csv("outputs/csv_data/hubspot/hubspot_conversion_metrics_2025_04_01_2025_04_25.csv")
    may_df = pd.read_csv("outputs/csv_data/hubspot/hubspot_conversion_metrics_2025_05_01_2025_05_25.csv")
    
    april = april_df.iloc[0]
    may = may_df.iloc[0]
    
    print("LOADING DATA:")
    print(f"✅ April 1-24 data loaded")
    print(f"✅ May 1-24 data loaded")
    
    print("\nKEY METRICS COMPARISON:")
    print("="*50)
    
    # Contacts
    contact_change = may['total_contacts'] - april['total_contacts']
    contact_pct = (contact_change / april['total_contacts']) * 100
    print(f"📊 Total Contacts: {april['total_contacts']:,.0f} → {may['total_contacts']:,.0f} ({contact_change:+,.0f}, {contact_pct:+.1f}%)")
    
    # Deals
    deal_change = may['total_deals'] - april['total_deals']
    deal_pct = (deal_change / april['total_deals']) * 100
    print(f"🎯 Total Deals: {april['total_deals']:,.0f} → {may['total_deals']:,.0f} ({deal_change:+,.0f}, {deal_pct:+.1f}%)")
    
    # Closed Won
    won_change = may['total_closed_won_deals'] - april['total_closed_won_deals']
    won_pct = (won_change / april['total_closed_won_deals']) * 100
    print(f"💰 Closed Won: {april['total_closed_won_deals']:,.0f} → {may['total_closed_won_deals']:,.0f} ({won_change:+,.0f}, {won_pct:+.1f}%)")
    
    print("\nCONVERSION RATES:")
    print("="*50)
    
    # Contact to Deal
    contact_deal_change = may['contact_to_deal_conversion'] - april['contact_to_deal_conversion']
    print(f"🔄 Contact→Deal: {april['contact_to_deal_conversion']:.2f}% → {may['contact_to_deal_conversion']:.2f}% ({contact_deal_change:+.2f}pp)")
    
    # Contact to Won
    contact_won_change = may['contact_to_closed_won_conversion'] - april['contact_to_closed_won_conversion']
    print(f"💎 Contact→Won: {april['contact_to_closed_won_conversion']:.2f}% → {may['contact_to_closed_won_conversion']:.2f}% ({contact_won_change:+.2f}pp)")
    
    # Win Rate
    win_rate_change = may['deal_win_rate'] - april['deal_win_rate']
    print(f"🏆 Deal Win Rate: {april['deal_win_rate']:.2f}% → {may['deal_win_rate']:.2f}% ({win_rate_change:+.2f}pp)")
    
    print("\nCALCULATION EXAMPLES FOR VERIFICATION:")
    print("="*60)
    
    print(f"\nEXAMPLE 1: Contact to Deal Conversion Rate (May 1-24)")
    print(f"Formula: Total Deals ÷ Total Contacts × 100")
    print(f"Values: {may['total_deals']:.0f} deals ÷ {may['total_contacts']:.0f} contacts × 100")
    print(f"Step 1: {may['total_deals']:.0f} ÷ {may['total_contacts']:.0f} = {may['total_deals']/may['total_contacts']:.6f}")
    print(f"Step 2: {may['total_deals']/may['total_contacts']:.6f} × 100 = {may['contact_to_deal_conversion']:.2f}%")
    print(f"RESULT: {may['contact_to_deal_conversion']:.2f}%")
    
    print(f"\nEXAMPLE 2: Deal Win Rate (April 1-24)")
    total_decided_april = april['total_closed_won_deals'] + april['total_closed_lost_deals']
    print(f"Formula: Closed Won ÷ (Closed Won + Closed Lost) × 100")
    print(f"Values: {april['total_closed_won_deals']:.0f} won ÷ ({april['total_closed_won_deals']:.0f} won + {april['total_closed_lost_deals']:.0f} lost) × 100")
    print(f"Step 1: {april['total_closed_won_deals']:.0f} ÷ {total_decided_april:.0f} = {april['total_closed_won_deals']/total_decided_april:.6f}")
    print(f"Step 2: {april['total_closed_won_deals']/total_decided_april:.6f} × 100 = {april['deal_win_rate']:.2f}%")
    print(f"RESULT: {april['deal_win_rate']:.2f}%")
    
    print(f"\nEXAMPLE 3: Contact Growth Rate (April to May)")
    print(f"Formula: (May Contacts - April Contacts) ÷ April Contacts × 100")
    print(f"Values: ({may['total_contacts']:.0f} - {april['total_contacts']:.0f}) ÷ {april['total_contacts']:.0f} × 100")
    print(f"Step 1: {contact_change:.0f} ÷ {april['total_contacts']:.0f} = {contact_change/april['total_contacts']:.6f}")
    print(f"Step 2: {contact_change/april['total_contacts']:.6f} × 100 = {contact_pct:.2f}%")
    print(f"RESULT: {contact_pct:.2f}%")
    
    print(f"\nEXAMPLE 4: Contact to Closed Won (May 1-24)")
    print(f"Formula: Closed Won Deals ÷ Total Contacts × 100")
    print(f"Values: {may['total_closed_won_deals']:.0f} closed won ÷ {may['total_contacts']:.0f} contacts × 100")
    print(f"Step 1: {may['total_closed_won_deals']:.0f} ÷ {may['total_contacts']:.0f} = {may['total_closed_won_deals']/may['total_contacts']:.6f}")
    print(f"Step 2: {may['total_closed_won_deals']/may['total_contacts']:.6f} × 100 = {may['contact_to_closed_won_conversion']:.2f}%")
    print(f"RESULT: {may['contact_to_closed_won_conversion']:.2f}%")
    
    print(f"\nEXAMPLE 5: Deal Volume Change (April to May)")
    print(f"Formula: (May Deals - April Deals) ÷ April Deals × 100")
    print(f"Values: ({may['total_deals']:.0f} - {april['total_deals']:.0f}) ÷ {april['total_deals']:.0f} × 100")
    print(f"Step 1: {deal_change:.0f} ÷ {april['total_deals']:.0f} = {deal_change/april['total_deals']:.6f}")
    print(f"Step 2: {deal_change/april['total_deals']:.6f} × 100 = {deal_pct:.2f}%")
    print(f"RESULT: {deal_pct:.2f}%")
    
    print("\n" + "="*70)
    print("KEY INSIGHTS SUMMARY:")
    print("="*70)
    print(f"📈 Contact Growth: {contact_change:+,.0f} contacts ({contact_pct:+.1f}% increase)")
    print(f"🎯 Deal Generation: {deal_change:+,.0f} deals ({deal_pct:+.1f}% change)")
    print(f"💰 Revenue Impact: {won_change:+,.0f} closed won deals ({won_pct:+.1f}% change)")
    print(f"🏆 Win Rate: {may['deal_win_rate']:.1f}% ({'↗️' if win_rate_change > 0 else '↘️'} {abs(win_rate_change):.1f}pp)")
    print(f"⚡ Contact to Deal: {may['contact_to_deal_conversion']:.1f}% conversion rate")
    print(f"🎯 Contact to Closed Won: {may['contact_to_closed_won_conversion']:.1f}% end-to-end conversion")
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETED SUCCESSFULLY!")
    print("="*70)

if __name__ == "__main__":
    main() 