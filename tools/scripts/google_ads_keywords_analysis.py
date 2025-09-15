#!/usr/bin/env python3
"""
Google Ads Keywords Analysis from HubSpot UTM Data
Analyzes HubSpot contacts to identify which Google Ads keywords are generating leads and conversions
"""

import json
import pandas as pd
from collections import Counter, defaultdict
from datetime import datetime
import re

def load_hubspot_data(filename):
    """Load HubSpot contacts data"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_utm_campaigns(contacts):
    """Analyze UTM campaigns and identify Google Ads campaigns"""
    
    print("🔍 ANALYZING UTM CAMPAIGNS")
    print("=" * 50)
    
    # Extract UTM data
    utm_data = []
    google_ads_campaigns = []
    
    for contact in contacts:
        props = contact.get('properties', {})
        
        utm_campaign = props.get('utm_campaign', '') or ''
        utm_source = props.get('utm_source', '') or ''
        utm_medium = props.get('utm_medium', '') or ''
        utm_term = props.get('utm_term', '') or ''
        utm_content = props.get('utm_content', '') or ''
        
        # Check if it's Google Ads traffic
        is_google_ads = (
            utm_source.lower() in ['google', 'googleads', 'google_ads'] or
            utm_medium.lower() in ['cpc', 'paid_search', 'google_ads'] or
            'google' in utm_source.lower() or
            'ads' in utm_source.lower()
        )
        
        if utm_campaign or utm_source or utm_medium:
            utm_data.append({
                'email': props.get('email', ''),
                'utm_campaign': utm_campaign,
                'utm_source': utm_source,
                'utm_medium': utm_medium,
                'utm_term': utm_term,
                'utm_content': utm_content,
                'is_google_ads': is_google_ads,
                'lifecyclestage': props.get('lifecyclestage', ''),
                'activo': props.get('activo', ''),
                'num_associated_deals': props.get('num_associated_deals') or '0',
                'createdate': props.get('createdate', '')
            })
            
            if is_google_ads:
                google_ads_campaigns.append({
                    'campaign': utm_campaign,
                    'source': utm_source,
                    'medium': utm_medium,
                    'term': utm_term,
                    'content': utm_content,
                    'lifecyclestage': props.get('lifecyclestage', ''),
                    'has_deals': int(props.get('num_associated_deals') or '0') > 0,
                    'is_active': props.get('activo', '') == 'true'
                })
    
    return utm_data, google_ads_campaigns

def analyze_google_ads_keywords(google_ads_campaigns):
    """Analyze Google Ads keywords performance"""
    
    print("\n📊 GOOGLE ADS KEYWORDS ANALYSIS")
    print("=" * 50)
    
    if not google_ads_campaigns:
        print("❌ No Google Ads campaigns found in UTM data")
        return
    
    # Group by campaign and keyword
    campaign_keyword_stats = defaultdict(lambda: {
        'total_leads': 0,
        'customers': 0,
        'deals': 0,
        'active_users': 0,
        'keywords': set()
    })
    
    keyword_stats = defaultdict(lambda: {
        'total_leads': 0,
        'customers': 0,
        'deals': 0,
        'active_users': 0,
        'campaigns': set()
    })
    
    for campaign_data in google_ads_campaigns:
        campaign = campaign_data['campaign']
        keyword = campaign_data['term']
        
        # Update campaign stats
        campaign_keyword_stats[campaign]['total_leads'] += 1
        campaign_keyword_stats[campaign]['keywords'].add(keyword)
        
        if campaign_data['lifecyclestage'] == 'customer':
            campaign_keyword_stats[campaign]['customers'] += 1
            
        if campaign_data['has_deals']:
            campaign_keyword_stats[campaign]['deals'] += 1
            
        if campaign_data['is_active']:
            campaign_keyword_stats[campaign]['active_users'] += 1
        
        # Update keyword stats
        if keyword:
            keyword_stats[keyword]['total_leads'] += 1
            keyword_stats[keyword]['campaigns'].add(campaign)
            
            if campaign_data['lifecyclestage'] == 'customer':
                keyword_stats[keyword]['customers'] += 1
                
            if campaign_data['has_deals']:
                keyword_stats[keyword]['deals'] += 1
                
            if campaign_data['is_active']:
                keyword_stats[keyword]['active_users'] += 1
    
    # Print campaign analysis
    print(f"\n🎯 GOOGLE ADS CAMPAIGNS PERFORMANCE")
    print("-" * 50)
    
    campaign_summary = []
    for campaign, stats in campaign_keyword_stats.items():
        if stats['total_leads'] > 0:
            conversion_rate = (stats['customers'] / stats['total_leads']) * 100
            deal_rate = (stats['deals'] / stats['total_leads']) * 100
            activation_rate = (stats['active_users'] / stats['total_leads']) * 100
            
            campaign_summary.append({
                'campaign': campaign,
                'leads': stats['total_leads'],
                'customers': stats['customers'],
                'deals': stats['deals'],
                'active_users': stats['active_users'],
                'conversion_rate': conversion_rate,
                'deal_rate': deal_rate,
                'activation_rate': activation_rate,
                'unique_keywords': len(stats['keywords'])
            })
    
    # Sort by leads
    campaign_summary.sort(key=lambda x: x['leads'], reverse=True)
    
    for camp in campaign_summary:
        print(f"\n📈 Campaign: {camp['campaign']}")
        print(f"   Leads: {camp['leads']}")
        print(f"   Customers: {camp['customers']} ({camp['conversion_rate']:.1f}%)")
        print(f"   Deals: {camp['deals']} ({camp['deal_rate']:.1f}%)")
        print(f"   Active Users: {camp['active_users']} ({camp['activation_rate']:.1f}%)")
        print(f"   Unique Keywords: {camp['unique_keywords']}")
    
    # Print keyword analysis
    print(f"\n🔑 TOP PERFORMING KEYWORDS")
    print("-" * 50)
    
    keyword_summary = []
    for keyword, stats in keyword_stats.items():
        if stats['total_leads'] > 0:
            conversion_rate = (stats['customers'] / stats['total_leads']) * 100
            deal_rate = (stats['deals'] / stats['total_leads']) * 100
            activation_rate = (stats['active_users'] / stats['total_leads']) * 100
            
            keyword_summary.append({
                'keyword': keyword,
                'leads': stats['total_leads'],
                'customers': stats['customers'],
                'deals': stats['deals'],
                'active_users': stats['active_users'],
                'conversion_rate': conversion_rate,
                'deal_rate': deal_rate,
                'activation_rate': activation_rate,
                'campaigns': list(stats['campaigns'])
            })
    
    # Sort by leads
    keyword_summary.sort(key=lambda x: x['leads'], reverse=True)
    
    print(f"\nTop 10 Keywords by Lead Volume:")
    for i, kw in enumerate(keyword_summary[:10], 1):
        print(f"{i:2d}. {kw['keyword']}")
        print(f"    Leads: {kw['leads']} | Customers: {kw['customers']} ({kw['conversion_rate']:.1f}%) | Deals: {kw['deals']} ({kw['deal_rate']:.1f}%)")
        print(f"    Campaigns: {', '.join(kw['campaigns'])}")
    
    return campaign_summary, keyword_summary

def analyze_utm_sources(utm_data):
    """Analyze all UTM sources to identify traffic patterns"""
    
    print(f"\n📡 UTM SOURCES ANALYSIS")
    print("=" * 50)
    
    # Count by source
    source_counts = Counter()
    source_campaigns = defaultdict(set)
    
    for data in utm_data:
        source = data['utm_source'] or 'Unknown'
        campaign = data['utm_campaign'] or 'Unknown'
        
        source_counts[source] += 1
        source_campaigns[source].add(campaign)
    
    print(f"\nTop UTM Sources:")
    for source, count in source_counts.most_common(10):
        campaigns = list(source_campaigns[source])
        print(f"  {source}: {count} leads")
        if len(campaigns) <= 5:
            print(f"    Campaigns: {', '.join(campaigns)}")
        else:
            print(f"    Campaigns: {', '.join(campaigns[:5])}... (+{len(campaigns)-5} more)")
    
    return source_counts, source_campaigns

def identify_google_ads_patterns(utm_data):
    """Identify potential Google Ads campaigns from UTM patterns"""
    
    print(f"\n🔍 POTENTIAL GOOGLE ADS CAMPAIGNS")
    print("=" * 50)
    
    potential_google_ads = []
    
    for data in utm_data:
        campaign = data['utm_campaign']
        source = data['utm_source']
        medium = data['utm_medium']
        
        # Look for Google Ads patterns
        is_potential_google_ads = (
            # Direct Google Ads indicators
            (source and 'google' in source.lower()) or
            (source and 'ads' in source.lower()) or
            (medium and medium.lower() in ['cpc', 'paid_search', 'google_ads']) or
            
            # Campaign naming patterns
            (campaign and 'pymes' in campaign.lower()) or
            (campaign and 'contador' in campaign.lower()) or
            (campaign and 'conta' in campaign.lower()) or
            (campaign and 'search' in campaign.lower()) or
            (campaign and 'brand' in campaign.lower()) or
            (campaign and 'mercadopago' in campaign.lower()) or
            
            # Source patterns
            (source and source.lower() in ['google', 'googleads', 'google_ads', 'google ads'])
        )
        
        if is_potential_google_ads and campaign:
            potential_google_ads.append({
                'campaign': campaign,
                'source': source,
                'medium': medium,
                'term': data['utm_term'],
                'lifecyclestage': data['lifecyclestage'],
                'has_deals': int(data['num_associated_deals'] or '0') > 0,
                'is_active': data['activo'] == 'true'
            })
    
    # Group and analyze
    campaign_groups = defaultdict(list)
    for ad in potential_google_ads:
        campaign_groups[ad['campaign']].append(ad)
    
    print(f"\nIdentified {len(potential_google_ads)} potential Google Ads leads")
    print(f"Across {len(campaign_groups)} unique campaigns")
    
    print(f"\nCampaign Performance:")
    for campaign, leads in campaign_groups.items():
        customers = sum(1 for lead in leads if lead['lifecyclestage'] == 'customer')
        deals = sum(1 for lead in leads if lead['has_deals'])
        active = sum(1 for lead in leads if lead['is_active'])
        
        conversion_rate = (customers / len(leads)) * 100 if leads else 0
        deal_rate = (deals / len(leads)) * 100 if leads else 0
        activation_rate = (active / len(leads)) * 100 if leads else 0
        
        print(f"\n📈 {campaign}")
        print(f"   Leads: {len(leads)}")
        print(f"   Customers: {customers} ({conversion_rate:.1f}%)")
        print(f"   Deals: {deals} ({deal_rate:.1f}%)")
        print(f"   Active Users: {active} ({activation_rate:.1f}%)")
        
        # Show top keywords for this campaign
        keywords = [lead['term'] for lead in leads if lead['term']]
        if keywords:
            keyword_counts = Counter(keywords)
            print(f"   Top Keywords:")
            for kw, count in keyword_counts.most_common(3):
                print(f"     - {kw}: {count} leads")
    
    return potential_google_ads

def main():
    """Main analysis function"""
    
    # Load the most recent HubSpot data
    import glob
    contact_files = glob.glob("hubspot_contacts_*_20250908_*.json")
    # Filter out analysis files
    contact_files = [f for f in contact_files if not f.endswith('_analysis.json')]
    if not contact_files:
        print("❌ No HubSpot contacts data found")
        return
    
    # Use the raw data file (not analysis file)
    latest_file = contact_files[0]  # Should be the raw data file
    print(f"📁 Available files: {contact_files}")
    print(f"📁 Selected file: {latest_file}")
    print(f"📁 Loading data from: {latest_file}")
    
    contacts = load_hubspot_data(latest_file)
    print(f"📊 Loaded {len(contacts)} contacts")
    
    # Analyze UTM data
    utm_data, google_ads_campaigns = analyze_utm_campaigns(contacts)
    
    print(f"\n📈 UTM DATA SUMMARY")
    print(f"Total contacts with UTM data: {len(utm_data)}")
    print(f"Google Ads campaigns identified: {len(google_ads_campaigns)}")
    
    # Analyze Google Ads keywords
    if google_ads_campaigns:
        campaign_summary, keyword_summary = analyze_google_ads_keywords(google_ads_campaigns)
    
    # Analyze all UTM sources
    source_counts, source_campaigns = analyze_utm_sources(utm_data)
    
    # Identify potential Google Ads patterns
    potential_google_ads = identify_google_ads_patterns(utm_data)
    
    # Save results
    results = {
        'analysis_date': datetime.now().isoformat(),
        'total_contacts': len(contacts),
        'utm_contacts': len(utm_data),
        'google_ads_campaigns': len(google_ads_campaigns),
        'potential_google_ads': len(potential_google_ads),
        'campaign_summary': campaign_summary if google_ads_campaigns else [],
        'keyword_summary': keyword_summary if google_ads_campaigns else [],
        'source_counts': dict(source_counts),
        'potential_google_ads_campaigns': potential_google_ads
    }
    
    output_file = f"google_ads_keywords_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Analysis saved to: {output_file}")
    print(f"\n✅ Google Ads keywords analysis completed!")

if __name__ == "__main__":
    main()
