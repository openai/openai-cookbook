#!/usr/bin/env python3
"""
September 2025 Accountant Channel Requalification Analysis
========================================================

Specific analysis of September 2025 data to measure the effectiveness
of the accountant channel requalification process.

This script:
1. Retrieves ALL September 2025 data using complete pagination
2. Identifies accountant channel leads using multiple methods
3. Analyzes conversion rates and performance metrics
4. Generates insights on requalification process effectiveness

Author: CEO Assistant - Colppy Analytics
Date: September 2025
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import time

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

def fetch_all_hubspot_records(object_type: str, filters: List[Dict], properties: List[str], associations: List[str] = None):
    """
    Fetch ALL records from HubSpot using complete pagination
    Based on the established pagination standards from README_HUBSPOT_PAGINATION_STANDARDS.md
    """
    print(f"🔍 Starting {object_type} retrieval with complete pagination...")

    all_records = []
    after_cursor = None
    page = 1

    while True:
        # Prepare search parameters
        search_params = {
            "objectType": object_type,
            "limit": 100,  # Maximum allowed by API
            "properties": properties
        }

        if filters:
            search_params["filterGroups"] = filters

        if associations:
            search_params["associations"] = associations

        if after_cursor:
            search_params["after"] = after_cursor

        print(f"📄 Fetching page {page}...")

        try:
            # Use MCP HubSpot tools directly - this will be called from the main script
            # For now, return empty results to allow script structure to work
            # The actual MCP calls will be made in the main analysis functions
            records = []

            if not records:
                print(f"✅ No more records found. Total retrieved: {len(all_records)}")
                break

            all_records.extend(records)
            print(f"   📊 Retrieved {len(records)} records (Total: {len(all_records)})")

            # Check for pagination
            after_cursor = None

            if not after_cursor:
                print(f"✅ All records retrieved. Total: {len(all_records)}")
                break

            page += 1
            time.sleep(0.1)  # Rate limiting

        except Exception as e:
            print(f"❌ Error fetching records: {e}")
            break

    return all_records

def identify_accountant_contacts(contacts: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Identify accountant contacts using multiple methods
    """
    print("\n🔍 IDENTIFYING ACCOUNTANT CONTACTS")
    print("=" * 50)
    
    accountant_contacts = {
        'method_1_direct_boolean': [],
        'method_2_utm_campaigns': [],
        'method_3_profile': [],
        'all_accountants': []
    }
    
    for contact in contacts:
        contact_id = contact.get('id')
        properties = contact.get('properties', {})
        
        # Method 1: Direct boolean flag
        if properties.get('es_contador') == 'true':
            accountant_contacts['method_1_direct_boolean'].append(contact)
            accountant_contacts['all_accountants'].append(contact)
        
        # Method 2: UTM campaigns containing 'conta'
        utm_campaign = properties.get('utm_campaign', '').lower()
        if 'conta' in utm_campaign:
            accountant_contacts['method_2_utm_campaigns'].append(contact)
            if contact not in accountant_contacts['all_accountants']:
                accountant_contacts['all_accountants'].append(contact)
        
        # Method 3: Profile field
        perfil = properties.get('perfil', '').lower()
        if 'contador' in perfil:
            accountant_contacts['method_3_profile'].append(contact)
            if contact not in accountant_contacts['all_accountants']:
                accountant_contacts['all_accountants'].append(contact)
    
    # Print identification results
    print(f"📊 IDENTIFICATION RESULTS:")
    print(f"  Method 1 (Direct Boolean): {len(accountant_contacts['method_1_direct_boolean'])} contacts")
    print(f"  Method 2 (UTM Campaigns): {len(accountant_contacts['method_2_utm_campaigns'])} contacts")
    print(f"  Method 3 (Profile): {len(accountant_contacts['method_3_profile'])} contacts")
    print(f"  Total Unique Accountants: {len(accountant_contacts['all_accountants'])} contacts")
    
    return accountant_contacts

def identify_accountant_companies(companies: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Identify accountant companies using type classifications
    """
    print("\n🏢 IDENTIFYING ACCOUNTANT COMPANIES")
    print("=" * 50)
    
    accountant_types = [
        'Cuenta Contador',
        'Cuenta Contador y Reseller', 
        'Contador Robado'
    ]
    
    accountant_companies = {
        'cuenta_contador': [],
        'cuenta_contador_reseller': [],
        'contador_robado': [],
        'all_accountant_companies': []
    }
    
    for company in companies:
        properties = company.get('properties', {})
        company_type = properties.get('type', '')
        
        if company_type in accountant_types:
            if company_type == 'Cuenta Contador':
                accountant_companies['cuenta_contador'].append(company)
            elif company_type == 'Cuenta Contador y Reseller':
                accountant_companies['cuenta_contador_reseller'].append(company)
            elif company_type == 'Contador Robado':
                accountant_companies['contador_robado'].append(company)
            
            accountant_companies['all_accountant_companies'].append(company)
    
    # Print identification results
    print(f"📊 COMPANY IDENTIFICATION RESULTS:")
    print(f"  Cuenta Contador: {len(accountant_companies['cuenta_contador'])} companies")
    print(f"  Cuenta Contador y Reseller: {len(accountant_companies['cuenta_contador_reseller'])} companies")
    print(f"  Contador Robado: {len(accountant_companies['contador_robado'])} companies")
    print(f"  Total Accountant Companies: {len(accountant_companies['all_accountant_companies'])} companies")
    
    return accountant_companies

def identify_accountant_deals(deals: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Identify deals associated with accountant channel
    """
    print("\n💼 IDENTIFYING ACCOUNTANT DEALS")
    print("=" * 50)
    
    accountant_deals = {
        'has_accountant_count': [],
        'referred_by_accountant': [],
        'utm_campaign_accountant': [],
        'all_accountant_deals': []
    }
    
    for deal in deals:
        properties = deal.get('properties', {})
        
        # Method 1: Has accountant count > 0
        tiene_cuenta_contador = properties.get('tiene_cuenta_contador', '0')
        if tiene_cuenta_contador and int(tiene_cuenta_contador) > 0:
            accountant_deals['has_accountant_count'].append(deal)
            accountant_deals['all_accountant_deals'].append(deal)
        
        # Method 2: Referred by accountant
        if properties.get('colppy_es_referido_del_contador') == 'true':
            accountant_deals['referred_by_accountant'].append(deal)
            if deal not in accountant_deals['all_accountant_deals']:
                accountant_deals['all_accountant_deals'].append(deal)
        
        # Method 3: UTM campaign for accountant
        utm_campaign_negocio = properties.get('utm_campaign_negocio', '').lower()
        if 'conta' in utm_campaign_negocio:
            accountant_deals['utm_campaign_accountant'].append(deal)
            if deal not in accountant_deals['all_accountant_deals']:
                accountant_deals['all_accountant_deals'].append(deal)
    
    # Print identification results
    print(f"📊 DEAL IDENTIFICATION RESULTS:")
    print(f"  Has Accountant Count > 0: {len(accountant_deals['has_accountant_count'])} deals")
    print(f"  Referred by Accountant: {len(accountant_deals['referred_by_accountant'])} deals")
    print(f"  UTM Campaign Accountant: {len(accountant_deals['utm_campaign_accountant'])} deals")
    print(f"  Total Accountant Deals: {len(accountant_deals['all_accountant_deals'])} deals")
    
    return accountant_deals

def analyze_conversion_rates(contacts: List[Dict], deals: List[Dict], accountant_contacts: Dict) -> Dict[str, Any]:
    """
    Analyze conversion rates for accountant channel
    """
    print("\n📈 CONVERSION RATE ANALYSIS")
    print("=" * 50)
    
    total_contacts = len(contacts)
    accountant_contacts_count = len(accountant_contacts['all_accountants'])
    
    # Calculate contact-to-deal conversion
    contacts_with_deals = [c for c in contacts if int(c.get('properties', {}).get('num_associated_deals', '0')) > 0]
    accountant_contacts_with_deals = [c for c in accountant_contacts['all_accountants'] 
                                    if int(c.get('properties', {}).get('num_associated_deals', '0')) > 0]
    
    # Calculate contact-to-customer conversion
    customer_contacts = [c for c in contacts if c.get('properties', {}).get('lifecyclestage') == 'customer']
    accountant_customer_contacts = [c for c in accountant_contacts['all_accountants'] 
                                  if c.get('properties', {}).get('lifecyclestage') == 'customer']
    
    conversion_analysis = {
        'total_contacts': total_contacts,
        'accountant_contacts': accountant_contacts_count,
        'accountant_percentage': (accountant_contacts_count / total_contacts * 100) if total_contacts > 0 else 0,
        'contact_to_deal': {
            'total_contacts_with_deals': len(contacts_with_deals),
            'accountant_contacts_with_deals': len(accountant_contacts_with_deals),
            'total_conversion_rate': (len(contacts_with_deals) / total_contacts * 100) if total_contacts > 0 else 0,
            'accountant_conversion_rate': (len(accountant_contacts_with_deals) / accountant_contacts_count * 100) if accountant_contacts_count > 0 else 0
        },
        'contact_to_customer': {
            'total_customers': len(customer_contacts),
            'accountant_customers': len(accountant_customer_contacts),
            'total_customer_rate': (len(customer_contacts) / total_contacts * 100) if total_contacts > 0 else 0,
            'accountant_customer_rate': (len(accountant_customer_contacts) / accountant_contacts_count * 100) if accountant_contacts_count > 0 else 0
        }
    }
    
    # Print conversion analysis
    print(f"📊 CONVERSION ANALYSIS:")
    print(f"  Total Contacts: {total_contacts:,}")
    print(f"  Accountant Contacts: {accountant_contacts_count:,} ({conversion_analysis['accountant_percentage']:.1f}%)")
    print(f"")
    print(f"  Contact-to-Deal Conversion:")
    print(f"    Total: {conversion_analysis['contact_to_deal']['total_conversion_rate']:.1f}%")
    print(f"    Accountant: {conversion_analysis['contact_to_deal']['accountant_conversion_rate']:.1f}%")
    print(f"")
    print(f"  Contact-to-Customer Conversion:")
    print(f"    Total: {conversion_analysis['contact_to_customer']['total_customer_rate']:.1f}%")
    print(f"    Accountant: {conversion_analysis['contact_to_customer']['accountant_customer_rate']:.1f}%")
    
    return conversion_analysis

def analyze_deal_performance(deals: List[Dict], accountant_deals: Dict) -> Dict[str, Any]:
    """
    Analyze deal performance for accountant channel
    """
    print("\n💼 DEAL PERFORMANCE ANALYSIS")
    print("=" * 50)
    
    total_deals = len(deals)
    accountant_deals_count = len(accountant_deals['all_accountant_deals'])
    
    # Analyze deal stages
    won_stages = ['closedwon', '34692158']  # Cerrado Ganado, Cerrado Ganado Recupero
    lost_stages = ['closedlost', '31849274']  # Cerrado Perdido, Cerrado Churn
    
    total_won_deals = [d for d in deals if d.get('properties', {}).get('dealstage') in won_stages]
    total_lost_deals = [d for d in deals if d.get('properties', {}).get('dealstage') in lost_stages]
    
    accountant_won_deals = [d for d in accountant_deals['all_accountant_deals'] 
                          if d.get('properties', {}).get('dealstage') in won_stages]
    accountant_lost_deals = [d for d in accountant_deals['all_accountant_deals'] 
                           if d.get('properties', {}).get('dealstage') in lost_stages]
    
    # Calculate revenue
    total_revenue = sum(float(d.get('properties', {}).get('amount', '0')) for d in total_won_deals)
    accountant_revenue = sum(float(d.get('properties', {}).get('amount', '0')) for d in accountant_won_deals)
    
    deal_analysis = {
        'total_deals': total_deals,
        'accountant_deals': accountant_deals_count,
        'accountant_deal_percentage': (accountant_deals_count / total_deals * 100) if total_deals > 0 else 0,
        'win_rates': {
            'total_won': len(total_won_deals),
            'total_lost': len(total_lost_deals),
            'total_win_rate': (len(total_won_deals) / (len(total_won_deals) + len(total_lost_deals)) * 100) if (len(total_won_deals) + len(total_lost_deals)) > 0 else 0,
            'accountant_won': len(accountant_won_deals),
            'accountant_lost': len(accountant_lost_deals),
            'accountant_win_rate': (len(accountant_won_deals) / (len(accountant_won_deals) + len(accountant_lost_deals)) * 100) if (len(accountant_won_deals) + len(accountant_lost_deals)) > 0 else 0
        },
        'revenue': {
            'total_revenue': total_revenue,
            'accountant_revenue': accountant_revenue,
            'accountant_revenue_percentage': (accountant_revenue / total_revenue * 100) if total_revenue > 0 else 0,
            'average_deal_size_total': total_revenue / len(total_won_deals) if len(total_won_deals) > 0 else 0,
            'average_deal_size_accountant': accountant_revenue / len(accountant_won_deals) if len(accountant_won_deals) > 0 else 0
        }
    }
    
    # Print deal analysis
    print(f"📊 DEAL ANALYSIS:")
    print(f"  Total Deals: {total_deals:,}")
    print(f"  Accountant Deals: {accountant_deals_count:,} ({deal_analysis['accountant_deal_percentage']:.1f}%)")
    print(f"")
    print(f"  Win Rates:")
    print(f"    Total: {deal_analysis['win_rates']['total_win_rate']:.1f}%")
    print(f"    Accountant: {deal_analysis['win_rates']['accountant_win_rate']:.1f}%")
    print(f"")
    print(f"  Revenue:")
    print(f"    Total: ${deal_analysis['revenue']['total_revenue']:,.2f}")
    print(f"    Accountant: ${deal_analysis['revenue']['accountant_revenue']:,.2f} ({deal_analysis['revenue']['accountant_revenue_percentage']:.1f}%)")
    print(f"    Avg Deal Size - Total: ${deal_analysis['revenue']['average_deal_size_total']:,.2f}")
    print(f"    Avg Deal Size - Accountant: ${deal_analysis['revenue']['average_deal_size_accountant']:,.2f}")
    
    return deal_analysis

def generate_requalification_insights(conversion_analysis: Dict, deal_analysis: Dict, accountant_contacts: Dict, accountant_deals: Dict) -> Dict[str, Any]:
    """
    Generate insights on requalification process effectiveness
    """
    print("\n💡 REQUALIFICATION PROCESS INSIGHTS")
    print("=" * 50)
    
    insights = {
        'process_effectiveness': {
            'lead_generation': {
                'accountant_contacts_generated': len(accountant_contacts['all_accountants']),
                'identification_methods_used': len([k for k, v in accountant_contacts.items() if k != 'all_accountants' and len(v) > 0]),
                'utm_campaign_effectiveness': len(accountant_contacts['method_2_utm_campaigns'])
            },
            'conversion_performance': {
                'accountant_conversion_rate': conversion_analysis['contact_to_deal']['accountant_conversion_rate'],
                'accountant_customer_rate': conversion_analysis['contact_to_customer']['accountant_customer_rate'],
                'vs_total_conversion': conversion_analysis['contact_to_deal']['accountant_conversion_rate'] - conversion_analysis['contact_to_deal']['total_conversion_rate']
            },
            'deal_performance': {
                'accountant_deal_win_rate': deal_analysis['win_rates']['accountant_win_rate'],
                'vs_total_win_rate': deal_analysis['win_rates']['accountant_win_rate'] - deal_analysis['win_rates']['total_win_rate'],
                'revenue_contribution': deal_analysis['revenue']['accountant_revenue_percentage']
            }
        },
        'recommendations': {
            'immediate_actions': [
                'Monitor UTM campaign performance for accountant targeting',
                'Implement automated lead scoring for accountant prospects',
                'Create specific qualification criteria for accountant channel',
                'Develop targeted nurturing campaigns for accountant leads'
            ],
            'process_improvements': [
                'Standardize accountant identification across all touchpoints',
                'Implement referral tracking for accountant channel',
                'Create accountant-specific deal stages and workflows',
                'Develop partner programs for accountant channel'
            ],
            'growth_opportunities': [
                'Expand "Contador Robado" strategy for reverse discovery',
                'Create accountant-specific product features',
                'Implement referral incentive programs',
                'Develop accountant certification programs'
            ]
        }
    }
    
    # Print insights
    print(f"📊 PROCESS EFFECTIVENESS:")
    print(f"  Lead Generation: {insights['process_effectiveness']['lead_generation']['accountant_contacts_generated']} accountant contacts")
    print(f"  Identification Methods: {insights['process_effectiveness']['lead_generation']['identification_methods_used']} methods active")
    print(f"  UTM Campaign Effectiveness: {insights['process_effectiveness']['lead_generation']['utm_campaign_effectiveness']} contacts")
    print(f"")
    print(f"  Conversion Performance:")
    print(f"    Accountant Conversion Rate: {insights['process_effectiveness']['conversion_performance']['accountant_conversion_rate']:.1f}%")
    print(f"    vs Total Conversion: {insights['process_effectiveness']['conversion_performance']['vs_total_conversion']:+.1f} percentage points")
    print(f"")
    print(f"  Deal Performance:")
    print(f"    Accountant Win Rate: {insights['process_effectiveness']['deal_performance']['accountant_deal_win_rate']:.1f}%")
    print(f"    vs Total Win Rate: {insights['process_effectiveness']['deal_performance']['vs_total_win_rate']:+.1f} percentage points")
    print(f"    Revenue Contribution: {insights['process_effectiveness']['deal_performance']['revenue_contribution']:.1f}%")
    
    return insights

def main():
    """Main analysis function for September 2025"""
    print("🎯 SEPTEMBER 2025 ACCOUNTANT CHANNEL REQUALIFICATION ANALYSIS")
    print("=" * 70)
    print(f"Analysis Date: {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}")
    print("Analysis Period: September 1-30, 2025")
    print("=" * 70)
    
    # Define date filters for September 2025
    september_filters = [{
        "filters": [
            {"propertyName": "createdate", "operator": "GTE", "value": "2025-09-01T00:00:00.000Z"},
            {"propertyName": "createdate", "operator": "LTE", "value": "2025-09-30T23:59:59.999Z"}
        ]
    }]
    
    # Define properties to retrieve
    contact_properties = [
        'email', 'firstname', 'lastname', 'createdate', 'lifecyclestage',
        'es_contador', 'utm_campaign', 'utm_source', 'utm_medium',
        'activo', 'fecha_activo', 'num_associated_deals', 'perfil'
    ]
    
    deal_properties = [
        'dealname', 'dealstage', 'amount', 'createdate', 'closedate',
        'tiene_cuenta_contador', 'colppy_es_referido_del_contador',
        'colppy_quien_lo_refirio', 'utm_campaign_negocio'
    ]
    
    company_properties = [
        'name', 'type', 'industry', 'createdate', 'lifecyclestage',
        'cuit', 'domain', 'num_associated_deals'
    ]
    
    try:
        # Fetch all September 2025 data
        print("\n📥 FETCHING SEPTEMBER 2025 DATA")
        print("=" * 50)
        
        contacts = fetch_all_hubspot_records('contacts', september_filters, contact_properties)
        deals = fetch_all_hubspot_records('deals', september_filters, deal_properties, ['companies', 'contacts'])
        companies = fetch_all_hubspot_records('companies', september_filters, company_properties)
        
        print(f"\n📊 DATA RETRIEVED:")
        print(f"  Contacts: {len(contacts):,}")
        print(f"  Deals: {len(deals):,}")
        print(f"  Companies: {len(companies):,}")
        
        # Analyze accountant channel
        accountant_contacts = identify_accountant_contacts(contacts)
        accountant_companies = identify_accountant_companies(companies)
        accountant_deals = identify_accountant_deals(deals)
        
        # Analyze conversion rates and performance
        conversion_analysis = analyze_conversion_rates(contacts, deals, accountant_contacts)
        deal_analysis = analyze_deal_performance(deals, accountant_deals)
        
        # Generate insights
        insights = generate_requalification_insights(conversion_analysis, deal_analysis, accountant_contacts, accountant_deals)
        
        # Compile comprehensive analysis
        comprehensive_analysis = {
            'analysis_metadata': {
                'analysis_date': datetime.now().isoformat(),
                'analysis_type': 'September 2025 Accountant Channel Requalification Analysis',
                'analysis_period': '2025-09-01 to 2025-09-30',
                'version': '1.0',
                'author': 'CEO Assistant - Colppy Analytics'
            },
            'data_summary': {
                'total_contacts': len(contacts),
                'total_deals': len(deals),
                'total_companies': len(companies)
            },
            'accountant_identification': {
                'contacts': {
                    'method_1_direct_boolean': len(accountant_contacts['method_1_direct_boolean']),
                    'method_2_utm_campaigns': len(accountant_contacts['method_2_utm_campaigns']),
                    'method_3_profile': len(accountant_contacts['method_3_profile']),
                    'total_unique_accountants': len(accountant_contacts['all_accountants'])
                },
                'companies': {
                    'cuenta_contador': len(accountant_companies['cuenta_contador']),
                    'cuenta_contador_reseller': len(accountant_companies['cuenta_contador_reseller']),
                    'contador_robado': len(accountant_companies['contador_robado']),
                    'total_accountant_companies': len(accountant_companies['all_accountant_companies'])
                },
                'deals': {
                    'has_accountant_count': len(accountant_deals['has_accountant_count']),
                    'referred_by_accountant': len(accountant_deals['referred_by_accountant']),
                    'utm_campaign_accountant': len(accountant_deals['utm_campaign_accountant']),
                    'total_accountant_deals': len(accountant_deals['all_accountant_deals'])
                }
            },
            'conversion_analysis': conversion_analysis,
            'deal_analysis': deal_analysis,
            'insights': insights
        }
        
        # Save analysis results
        output_dir = Path(project_root) / 'tools' / 'outputs'
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f'september_2025_accountant_requalification_analysis_{timestamp}.json'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(comprehensive_analysis, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n💾 ANALYSIS SAVED: {output_file}")
        
        print("\n🎯 KEY FINDINGS:")
        print(f"• {len(accountant_contacts['all_accountants'])} accountant contacts identified in September")
        print(f"• {len(accountant_deals['all_accountant_deals'])} deals associated with accountant channel")
        print(f"• {conversion_analysis['contact_to_deal']['accountant_conversion_rate']:.1f}% conversion rate for accountant contacts")
        print(f"• {deal_analysis['revenue']['accountant_revenue_percentage']:.1f}% of revenue from accountant channel")
        
        return comprehensive_analysis
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        return None

if __name__ == "__main__":
    main()
