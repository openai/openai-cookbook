#!/usr/bin/env python3
"""
Analyze SQL PQL conversion from MCP HubSpot data
This script analyzes contacts fetched via MCP HubSpot tools
"""

import json
import pandas as pd
from datetime import datetime
import sys

def parse_datetime(date_str):
    """Parse HubSpot datetime string to datetime object"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None

def analyze_sql_pql_timing(contacts_data, start_date, end_date):
    """
    Analyze SQL contacts to determine if they were PQL before or after SQL conversion.
    """
    print(f"\n🎯 ANALYZING SQL → PQL TIMING RELATIONSHIP")
    print(f"📅 SQL Conversion Date Range: {start_date} to {end_date}")
    print("=" * 60)
    
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T23:59:59+00:00")
    
    analysis_data = []
    sql_contacts = []
    
    # Filter for SQL contacts (contacts that became opportunities in the date range)
    for contact in contacts_data:
        sql_date_str = contact.get('properties', {}).get('hs_lifecyclestage_opportunity_date')
        if not sql_date_str:
            continue
            
        sql_date = parse_datetime(sql_date_str)
        if not sql_date:
            continue
            
        # Check if SQL conversion is in the target date range
        if start_dt <= sql_date <= end_dt:
            sql_contacts.append(contact)
    
    print(f"✅ Found {len(sql_contacts)} SQL contacts in date range")
    
    if len(sql_contacts) == 0:
        print("⚠️  No SQL contacts found for this period")
        return None, None
    
    # Analyze each SQL contact
    for contact in sql_contacts:
        props = contact.get('properties', {})
        
        sql_date = parse_datetime(props.get('hs_lifecyclestage_opportunity_date'))
        pql_date = parse_datetime(props.get('fecha_activo'))
        is_pql = props.get('activo') == 'true'
        
        # Determine PQL timing relative to SQL conversion
        if not is_pql or not pql_date:
            if is_pql and not pql_date:
                pql_timing = 'pql_no_date'
            else:
                pql_timing = 'never_pql'
        elif sql_date and pql_date:
            if pql_date < sql_date:
                pql_timing = 'pql_before_sql'
            elif pql_date >= sql_date:
                pql_timing = 'pql_after_sql'
            else:
                pql_timing = 'unknown'
        else:
            pql_timing = 'unknown'
        
        # Calculate time difference if both dates exist
        days_diff = None
        if sql_date and pql_date:
            days_diff = (sql_date - pql_date).days
        
        row = {
            'contact_id': contact.get('id'),
            'email': props.get('email'),
            'firstname': props.get('firstname'),
            'lastname': props.get('lastname'),
            'createdate': props.get('createdate'),
            'sql_date': props.get('hs_lifecyclestage_opportunity_date'),
            'pql_date': props.get('fecha_activo'),
            'is_pql': is_pql,
            'pql_timing': pql_timing,
            'days_between_pql_sql': days_diff,
            'lifecyclestage': props.get('lifecyclestage'),
            'num_associated_deals': int(props.get('num_associated_deals', 0)) if props.get('num_associated_deals') else 0
        }
        
        analysis_data.append(row)
    
    df = pd.DataFrame(analysis_data)
    
    # Summary statistics
    total_sqls = len(df)
    
    pql_before_sql = df[df['pql_timing'] == 'pql_before_sql']
    pql_after_sql = df[df['pql_timing'] == 'pql_after_sql']
    never_pql = df[df['pql_timing'] == 'never_pql']
    pql_no_date = df[df['pql_timing'] == 'pql_no_date']
    
    print(f"\n📊 SQL → PQL TIMING ANALYSIS RESULTS:")
    print("=" * 50)
    print(f"Total SQLs Analyzed: {total_sqls:,}")
    print(f"\n🎯 PQL BEFORE SQL: {len(pql_before_sql):,} ({len(pql_before_sql)/total_sqls*100:.1f}%)")
    print(f"   → These contacts activated in product BEFORE sales engagement")
    if len(pql_before_sql) > 0:
        avg_days = pql_before_sql['days_between_pql_sql'].mean()
        print(f"   → Average days between PQL and SQL: {avg_days:.1f} days")
    
    print(f"\n⏰ PQL AFTER SQL: {len(pql_after_sql):,} ({len(pql_after_sql)/total_sqls*100:.1f}%)")
    print(f"   → These contacts activated AFTER sales engagement started")
    if len(pql_after_sql) > 0:
        avg_days = pql_after_sql['days_between_pql_sql'].abs().mean()
        print(f"   → Average days between SQL and PQL: {avg_days:.1f} days")
    
    print(f"\n❌ NEVER PQL: {len(never_pql):,} ({len(never_pql)/total_sqls*100:.1f}%)")
    print(f"   → These contacts never activated in product")
    
    if len(pql_no_date) > 0:
        print(f"\n⚠️  PQL NO DATE: {len(pql_no_date):,} ({len(pql_no_date)/total_sqls*100:.1f}%)")
        print(f"   → Data quality issue: marked as PQL but fecha_activo is missing")
    
    # Additional insights
    print(f"\n💡 KEY INSIGHTS:")
    print("=" * 50)
    pql_before_rate = len(pql_before_sql) / total_sqls * 100 if total_sqls > 0 else 0
    print(f"• {pql_before_rate:.1f}% of SQLs were PQL BEFORE sales engagement")
    print(f"• This indicates product-led growth effectiveness")
    
    if len(pql_before_sql) > 0 and len(pql_after_sql) > 0:
        ratio = len(pql_before_sql) / len(pql_after_sql)
        print(f"• PQL-before-SQL vs PQL-after-SQL ratio: {ratio:.2f}:1")
    
    summary = {
        'total_sqls': total_sqls,
        'pql_before_sql': len(pql_before_sql),
        'pql_after_sql': len(pql_after_sql),
        'never_pql': len(never_pql),
        'pql_no_date': len(pql_no_date),
        'pql_before_rate': pql_before_rate
    }
    
    return df, summary

if __name__ == "__main__":
    print("📋 SQL PQL Conversion Analysis from MCP Data")
    print("=" * 60)
    print("\nThis script analyzes contacts fetched via MCP HubSpot tools")
    print("To use: Fetch contacts using MCP tools, save to JSON, then analyze")
    print("\nExample:")
    print("1. Use MCP hubspot-list-objects to fetch contacts")
    print("2. Save results to a JSON file")
    print("3. Run this script with the JSON file")
    print("\nFor November 2025 analysis, use:")
    print("  python analyze_sql_pql_from_mcp.py --input contacts.json --start-date 2025-11-01 --end-date 2025-11-30")




