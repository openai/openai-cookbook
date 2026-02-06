#!/usr/bin/env python3
"""
Analyze SQL PQL conversion from MCP HubSpot data
This script analyzes contacts fetched via MCP HubSpot tools
"""

import json
import pandas as pd
from datetime import datetime, timezone
import sys

def parse_datetime(date_str):
    """Parse HubSpot datetime string to datetime object
    
    Handles multiple formats:
    - ISO format: "2025-11-15T10:30:00.000Z"
    - Timestamp (milliseconds): "1762174592703"
    - Date-only: "2025-11-15"
    """
    if not date_str:
        return None
    try:
        # Try ISO format first (e.g., "2025-11-15T10:30:00.000Z")
        if 'T' in str(date_str) or 'Z' in str(date_str):
            return datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        # Try timestamp (milliseconds since epoch)
        elif str(date_str).isdigit() and len(str(date_str)) > 10:
            # Convert milliseconds to seconds, UTC timezone
            timestamp_ms = int(date_str)
            return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        # Try date-only format (e.g., "2025-11-15")
        else:
            return datetime.fromisoformat(str(date_str) + "T00:00:00+00:00")
    except (ValueError, AttributeError, OSError, OverflowError):
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
    print(f"   → These contacts performed the critical event BEFORE sales engagement")
    if len(pql_before_sql) > 0:
        avg_days = pql_before_sql['days_between_pql_sql'].mean()
        print(f"   → Average days between PQL and SQL: {avg_days:.1f} days")
    
    print(f"\n⏰ PQL AFTER SQL: {len(pql_after_sql):,} ({len(pql_after_sql)/total_sqls*100:.1f}%)")
    print(f"   → These contacts performed the critical event AFTER sales engagement started")
    if len(pql_after_sql) > 0:
        avg_days = pql_after_sql['days_between_pql_sql'].abs().mean()
        print(f"   → Average days between SQL and PQL: {avg_days:.1f} days")
    
    print(f"\n❌ NEVER PQL: {len(never_pql):,} ({len(never_pql)/total_sqls*100:.1f}%)")
    print(f"   → These contacts never performed the critical event")
    
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
    print("📋 SQL PQL Conversion Analysis")
    print("=" * 60)
    print("\nThis script analyzes contacts to determine SQL → PQL timing relationship")
    print("Requires pre-fetched contact data (doesn't fetch data itself)")
    print("\nUsage Workflow:")
    print("1. Fetch contacts using HubSpot API (for the period you want to analyze)")
    print("   - Filter by createdate to get contacts from the period")
    print("   - Required properties: email, firstname, lastname, createdate,")
    print("     hs_lifecyclestage_opportunity_date, fecha_activo, activo,")
    print("     lifecyclestage, num_associated_deals")
    print("2. Save contacts to JSON file")
    print("3. Load JSON and call analyze_sql_pql_timing() function")
    print("\nExample code:")
    print("  from analyze_sql_pql_from_mcp import analyze_sql_pql_timing")
    print("  import json")
    print("  ")
    print("  with open('contacts_nov_2025.json', 'r') as f:")
    print("      contacts_data = json.load(f)")
    print("  ")
    print("  df, summary = analyze_sql_pql_timing(")
    print("      contacts_data, ")
    print("      start_date='2025-11-01',")
    print("      end_date='2025-11-30'")
    print("  )")
    print("\nNote: The script filters for contacts where hs_lifecyclestage_opportunity_date")
    print("      (SQL date) falls within the specified date range.")
    print("      Handles timestamps (milliseconds) and ISO date formats automatically.")




