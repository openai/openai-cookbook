#!/usr/bin/env python3
"""
High Score (40+) Sales Team Handling Analysis
=============================================
Analyzes how the sales team handles contacts with score 40+:
- Owner assignment distribution
- Time to first contact
- Engagement rates by owner
- Conversion rates by owner
- Unengaged high-score contacts

IMPORTANT EXCLUSIONS:
- Contacts with lead_source = "Usuario Invitado" are EXCLUDED from analysis
  (These are internal users invited to Colppy and should not be counted)

Usage:
    python high_score_sales_handling_analysis.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
    python high_score_sales_handling_analysis.py --month YYYY-MM
    python high_score_sales_handling_analysis.py --current-mtd
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os
import argparse
from collections import defaultdict
from dotenv import load_dotenv
import pytz

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Load environment variables
load_dotenv()

# Try to use HubSpot API client if available
try:
    from hubspot_api.client import HubSpotClient, HubSpotAPIError
    HUBSPOT_CLIENT_AVAILABLE = True
except ImportError:
    HUBSPOT_CLIENT_AVAILABLE = False

# Import owner utilities for fetching owner names and status from API
from owner_utils import get_owner_name, get_owner_status

PORTAL_ID = "19877595"
UI_DOMAIN = "app.hubspot.com"

# Argentina timezone (UTC-3)
AR_TIMEZONE = pytz.timezone('America/Argentina/Buenos_Aires')

# Argentina holidays 2025
ARGENTINA_HOLIDAYS_2025 = [
    datetime(2025, 1, 1),   # New Year's Day
    datetime(2025, 3, 3),   # Carnival
    datetime(2025, 4, 3),   # Carnival
    datetime(2025, 3, 24),  # Truth and Justice Day
    datetime(2025, 4, 2),   # Malvinas Day
    datetime(2025, 4, 17),  # Maundy Thursday
    datetime(2025, 4, 18),  # Good Friday
    datetime(2025, 5, 1),   # Labour Day
    datetime(2025, 5, 2),   # Labour Day Holiday
    datetime(2025, 5, 25),  # Revolution Day
    datetime(2025, 6, 16),  # Martín Miguel de Güemes' Day
    datetime(2025, 6, 20),  # Flag Day
    datetime(2025, 7, 9),   # Independence Day
    datetime(2025, 8, 15),  # Death of San Martin Holiday
    datetime(2025, 8, 17),  # Death of San Martin
    datetime(2025, 10, 12), # Day of Respect for Cultural Diversity
    datetime(2025, 11, 21), # National Sovereignty Day Holiday
    datetime(2025, 11, 24), # National Sovereignty Day
    datetime(2025, 12, 8),  # Immaculate Conception
    datetime(2025, 12, 25), # Christmas Day
]

def generate_contact_link(contact_id):
    """Generate HubSpot contact link"""
    return f"https://{UI_DOMAIN}/contacts/{PORTAL_ID}/contact/{contact_id}"

def parse_datetime(date_str):
    """Parse HubSpot datetime string to datetime object"""
    if not date_str:
        return None
    try:
        if 'T' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(date_str + "T00:00:00+00:00")
        # Ensure timezone-aware
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt
    except (ValueError, AttributeError):
        return None

def is_holiday(dt):
    """Check if date is a holiday"""
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    dt_ar = dt.astimezone(AR_TIMEZONE)
    date_only = dt_ar.date()
    holiday_dates = [h.date() for h in ARGENTINA_HOLIDAYS_2025]
    return date_only in holiday_dates

def is_business_hour(dt):
    """Check if datetime is within business hours (9 AM - 6 PM, weekdays, non-holidays)"""
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    dt_ar = dt.astimezone(AR_TIMEZONE)
    
    if is_holiday(dt):
        return False
    
    if dt_ar.weekday() >= 5:  # Saturday or Sunday
        return False
    
    hour = dt_ar.hour
    return 9 <= hour < 18

def calculate_business_hours(start_dt, end_dt):
    """Calculate business hours between two datetimes"""
    if not start_dt or not end_dt:
        return 0.0
    if end_dt <= start_dt:
        return 0.0
    
    # Ensure timezone-aware
    if start_dt.tzinfo is None:
        start_dt = pytz.UTC.localize(start_dt)
    if end_dt.tzinfo is None:
        end_dt = pytz.UTC.localize(end_dt)
    
    business_hours = 0.0
    current = start_dt
    
    while current < end_dt:
        if is_business_hour(current):
            hour_start = current.replace(minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)
            segment_start = max(current, hour_start)
            segment_end = min(end_dt, hour_end)
            hours_in_segment = (segment_end - segment_start).total_seconds() / 3600
            business_hours += hours_in_segment
        current = (current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    
    return business_hours

def get_score(contact):
    """Extract scoring value using fit_score_contador"""
    props = contact.get('properties', {})
    score = props.get('fit_score_contador')
    
    if score and score != '':
        try:
            return float(score)
        except:
            pass
    
    return None

def calculate_time_to_contact(createdate_str, first_outreach, first_engagement, lead_status, last_status_date):
    """
    Calculate time to contact using both business hours and total calendar time
    Returns: (business_hours, total_hours, contact_method, contact_date)
    """
    createdate = parse_datetime(createdate_str)
    if not createdate:
        return None, None, "No creation date", None
    
    # Priority 1: hs_first_outreach_date
    if first_outreach:
        outreach_date = parse_datetime(first_outreach)
        if outreach_date and outreach_date >= createdate:
            business_hours = calculate_business_hours(createdate, outreach_date)
            total_hours = (outreach_date - createdate).total_seconds() / 3600
            return business_hours, total_hours, "First Outreach", first_outreach
    
    # Priority 2: hs_sa_first_engagement_date
    if first_engagement:
        engagement_date = parse_datetime(first_engagement)
        if engagement_date and engagement_date >= createdate:
            business_hours = calculate_business_hours(createdate, engagement_date)
            total_hours = (engagement_date - createdate).total_seconds() / 3600
            return business_hours, total_hours, "First Engagement", first_engagement
    
    # Priority 3: last_lead_status_date (if status changed from Nuevo Lead)
    if lead_status and lead_status not in ['938333957', 'new-stage-id', None, '']:
        if last_status_date:
            status_date = parse_datetime(last_status_date)
            if status_date and status_date >= createdate:
                business_hours = calculate_business_hours(createdate, status_date)
                total_hours = (status_date - createdate).total_seconds() / 3600
                return business_hours, total_hours, "Lead Status Change", last_status_date
    
    return None, None, "Not Contacted", None

def fetch_high_score_contacts(start_date, end_date):
    """
    Fetch contacts with score 40+ from HubSpot API
    
    EXCLUDES: Contacts with lead_source = "Usuario Invitado" (internal invited users)
    """
    print(f"📥 Fetching high-score (40+) contacts from HubSpot API ({start_date} to {end_date})...")
    print("   ⚠️  Excluding 'Usuario Invitado' contacts (internal invited users)")
    
    start_datetime = f"{start_date}T00:00:00.000Z"
    end_datetime = f"{end_date}T23:59:59.999Z"
    
    # Properties needed for analysis
    properties = [
        'email', 'firstname', 'lastname', 'createdate',
        'fit_score_contador',
        'hubspot_owner_id',
        'hs_first_outreach_date',
        'hs_sa_first_engagement_date',
        'hs_lead_status',
        'last_lead_status_date',
        'hs_v2_date_entered_opportunity',  # SQL conversion
        'activo',  # PQL flag
        'fecha_activo',  # PQL date
        'lifecyclestage',
        'lead_source'  # Used to exclude "Usuario Invitado" contacts
    ]
    
    all_contacts = []
    
    # Try using HubSpot API client first
    if HUBSPOT_CLIENT_AVAILABLE:
        try:
            client = HubSpotClient()
            after = None
            page = 0
            
            while True:
                page += 1
                try:
                    result = client.search_objects(
                        object_type="contacts",
                        filter_groups=[{
                            "filters": [{
                                "propertyName": "createdate",
                                "operator": "GTE",
                                "value": start_datetime
                            }, {
                                "propertyName": "createdate",
                                "operator": "LTE",
                                "value": end_datetime
                            }, {
                                "propertyName": "fit_score_contador",
                                "operator": "GTE",
                                "value": "40"
                            }, {
                                "propertyName": "lead_source",
                                "operator": "NEQ",
                                "value": "Usuario Invitado"
                            }]
                        }],
                        properties=properties,
                        limit=100,
                        after=after
                    )
                    
                    contacts = result.get("results", [])
                    all_contacts.extend(contacts)
                    
                    if page % 5 == 0:
                        print(f"   📊 Fetched {len(all_contacts)} contacts so far...")
                    
                    if 'paging' not in result or 'next' not in result['paging']:
                        break
                    after = result['paging']['next']['after']
                    
                except HubSpotAPIError as e:
                    print(f"   ⚠️  HubSpot API error: {e}")
                    break
                    
            print(f"✅ Fetched {len(all_contacts)} high-score (40+) contacts from HubSpot API (excluding 'Usuario Invitado')")
            return all_contacts
            
        except Exception as e:
            print(f"   ⚠️  Error with HubSpot client: {e}")
            print("   Falling back to direct API requests...")
    
    # Fallback to direct requests
    import requests
    api_key = os.getenv("HUBSPOT_API_KEY")
    if not api_key:
        print("⚠️  HUBSPOT_API_KEY not found. Cannot fetch data from API.")
        return []
    
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    after = None
    page = 0
    
    while True:
        page += 1
        payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "createdate",
                    "operator": "GTE",
                    "value": start_datetime
                }, {
                    "propertyName": "createdate",
                    "operator": "LTE",
                    "value": end_datetime
                }, {
                    "propertyName": "fit_score_contador",
                    "operator": "GTE",
                    "value": "40"
                }, {
                    "propertyName": "lead_source",
                    "operator": "NEQ",
                    "value": "Usuario Invitado"
                }]
            }],
            "properties": properties,
            "limit": 100
        }
        
        if after:
            payload["after"] = after
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            contacts = data.get("results", [])
            all_contacts.extend(contacts)
            
            if page % 5 == 0:
                print(f"   📊 Fetched {len(all_contacts)} contacts so far...")
            
            if 'paging' not in data or 'next' not in data['paging']:
                break
            after = data['paging']['next']['after']
            
        except Exception as e:
            print(f"   ⚠️  Error fetching contacts: {e}")
            break
    
    print(f"✅ Fetched {len(all_contacts)} high-score (40+) contacts from HubSpot API (excluding 'Usuario Invitado')")
    return all_contacts

def analyze_sales_handling(contacts, period_name):
    """
    Analyze how sales team handles high-score contacts
    
    NOTE: Contacts with lead_source = "Usuario Invitado" have already been excluded
    """
    print(f"\n{'='*100}")
    print(f"SALES TEAM HANDLING ANALYSIS - {period_name}")
    print(f"{'='*100}")
    print("   ℹ️  Analysis excludes 'Usuario Invitado' contacts (internal invited users)")
    print("   ℹ️  Analysis excludes contacts assigned to inactive owners")
    
    if len(contacts) == 0:
        print("\n⚠️  No high-score contacts found for this period")
        return None
    
    # Process contacts
    processed = []
    for contact in contacts:
        props = contact.get('properties', {})
        
        score = get_score(contact)
        if score is None or score < 40:
            continue  # Skip if no score or below 40
        
        createdate = parse_datetime(props.get('createdate'))
        owner_id = props.get('hubspot_owner_id', 'No Owner')
        owner_name = get_owner_name(owner_id)
        
        # Calculate time to contact
        first_outreach = props.get('hs_first_outreach_date')
        first_engagement = props.get('hs_sa_first_engagement_date')
        lead_status = props.get('hs_lead_status')
        last_status_date = props.get('last_lead_status_date')
        
        business_hours_to_contact, total_hours_to_contact, contact_method, contact_date = calculate_time_to_contact(
            props.get('createdate'),
            first_outreach,
            first_engagement,
            lead_status,
            last_status_date
        )
        
        # Check conversions
        sql_date = parse_datetime(props.get('hs_v2_date_entered_opportunity'))
        is_sql = sql_date is not None
        
        pql_date = parse_datetime(props.get('fecha_activo'))
        is_pql = props.get('activo') == 'true' and pql_date is not None
        
        processed.append({
            'contact_id': contact.get('id'),
            'email': props.get('email'),
            'firstname': props.get('firstname'),
            'lastname': props.get('lastname'),
            'createdate': createdate,
            'score': score,
            'owner_id': owner_id,
            'owner_name': owner_name,
            'business_hours_to_contact': business_hours_to_contact,
            'total_hours_to_contact': total_hours_to_contact,
            'contact_method': contact_method,
            'contact_date': contact_date,
            'is_contacted': business_hours_to_contact is not None,
            'is_sql': is_sql,
            'is_pql': is_pql,
            'sql_date': sql_date,
            'pql_date': pql_date,
            'lifecyclestage': props.get('lifecyclestage'),
            'hs_lead_status': lead_status
        })
    
    df = pd.DataFrame(processed)
    
    if len(df) == 0:
        print("\n⚠️  No contacts with score 40+ found after processing")
        return None
    
    # Filter out contacts with inactive owners
    print(f"\n🔍 Filtering contacts by owner status...")
    active_owner_mask = df['owner_id'].apply(lambda x: get_owner_status(x) is True if pd.notna(x) else False)
    contacts_before = len(df)
    df = df[active_owner_mask].copy()
    contacts_after = len(df)
    inactive_count = contacts_before - contacts_after
    
    if inactive_count > 0:
        print(f"   ⚠️  Excluded {inactive_count} contacts assigned to inactive owners")
    
    if len(df) == 0:
        print("\n⚠️  No contacts with score 40+ found after filtering for active owners")
        return None
    
    print(f"\n📊 Total high-score (40+) contacts (active owners only): {len(df)}")
    print(f"📊 Scoring Field: fit_score_contador (0-100 scale)")
    print(f"   Note: Despite the name 'contador', this field is used for both SMBs (PyMEs) and accountants")
    print(f"📊 Average score: {df['score'].mean():.2f}")
    print(f"📊 Score range: {df['score'].min():.0f} - {df['score'].max():.0f}")
    
    # Overall metrics
    contacted_count = df['is_contacted'].sum()
    contact_rate = (contacted_count / len(df) * 100) if len(df) > 0 else 0
    sql_count = df['is_sql'].sum()
    sql_rate = (sql_count / len(df) * 100) if len(df) > 0 else 0
    pql_count = df['is_pql'].sum()
    pql_rate = (pql_count / len(df) * 100) if len(df) > 0 else 0
    
    avg_business_hours = df[df['is_contacted']]['business_hours_to_contact'].mean() if contacted_count > 0 else None
    avg_total_hours = df[df['is_contacted']]['total_hours_to_contact'].mean() if contacted_count > 0 else None
    
    print(f"\n📊 Engagement Metrics:")
    print(f"   Contacts Contacted: {contacted_count} ({contact_rate:.1f}%)")
    print(f"   Contacts Not Contacted: {len(df) - contacted_count} ({100 - contact_rate:.1f}%)")
    if avg_business_hours is not None and avg_total_hours is not None:
        print(f"\n   Time to Contact Comparison:")
        print(f"   • Average Business Hours: {avg_business_hours:.2f} hours")
        print(f"   • Average Total Hours: {avg_total_hours:.2f} hours")
        print(f"   • Difference: {avg_total_hours - avg_business_hours:.2f} hours (non-business hours)")
        print(f"   (Business hours: 9 AM - 6 PM, Monday-Friday, excluding holidays, Argentina timezone)")
    
    print(f"\n📊 Conversion Metrics:")
    print(f"   SQL Conversions: {sql_count} ({sql_rate:.1f}%)")
    print(f"   PQL Conversions: {pql_count} ({pql_rate:.1f}%)")
    
    # Analysis by owner
    print(f"\n{'='*100}")
    print("OWNER PERFORMANCE ANALYSIS")
    print(f"{'='*100}")
    
    owner_stats = []
    for owner_id in df['owner_id'].unique():
        owner_df = df[df['owner_id'] == owner_id]
        owner_name = get_owner_name(owner_id)
        owner_status = get_owner_status(owner_id)
        
        # Skip inactive owners (should already be filtered, but double-check)
        if owner_status is not True:
            continue
        
        owner_contacted = owner_df['is_contacted'].sum()
        owner_contact_rate = (owner_contacted / len(owner_df) * 100) if len(owner_df) > 0 else 0
        owner_avg_business_hours = owner_df[owner_df['is_contacted']]['business_hours_to_contact'].mean() if owner_contacted > 0 else None
        owner_avg_total_hours = owner_df[owner_df['is_contacted']]['total_hours_to_contact'].mean() if owner_contacted > 0 else None
        owner_sql = owner_df['is_sql'].sum()
        owner_sql_rate = (owner_sql / len(owner_df) * 100) if len(owner_df) > 0 else 0
        owner_pql = owner_df['is_pql'].sum()
        owner_pql_rate = (owner_pql / len(owner_df) * 100) if len(owner_df) > 0 else 0
        
        owner_stats.append({
            'owner_id': owner_id,
            'owner_name': owner_name,
            'is_active': owner_status,
            'total_contacts': len(owner_df),
            'contacted': owner_contacted,
            'contact_rate': owner_contact_rate,
            'avg_business_hours': owner_avg_business_hours,
            'avg_total_hours': owner_avg_total_hours,
            'sql_count': owner_sql,
            'sql_rate': owner_sql_rate,
            'pql_count': owner_pql,
            'pql_rate': owner_pql_rate
        })
    
    owner_stats_df = pd.DataFrame(owner_stats).sort_values('total_contacts', ascending=False)
    
    print(f"\n{'Owner Name':<30} │ {'Total':<8} │ {'Contacted':<10} │ {'Contact %':<12} │ {'Avg Biz Hrs':<12} │ {'Avg Total Hrs':<14} │ {'Difference':<12} │ {'SQL':<6} │ {'SQL %':<8} │ {'PQL':<6} │ {'PQL %':<8}")
    print(f"{'─'*30}┼{'─'*8}┼{'─'*10}┼{'─'*12}┼{'─'*12}┼{'─'*14}┼{'─'*12}┼{'─'*6}┼{'─'*8}┼{'─'*6}┼{'─'*8}")
    for _, row in owner_stats_df.iterrows():
        avg_biz = f"{row['avg_business_hours']:.1f}" if pd.notna(row['avg_business_hours']) else "N/A"
        avg_tot = f"{row['avg_total_hours']:.1f}" if pd.notna(row['avg_total_hours']) else "N/A"
        diff = f"{row['avg_total_hours'] - row['avg_business_hours']:.1f}" if pd.notna(row['avg_total_hours']) and pd.notna(row['avg_business_hours']) else "N/A"
        print(f"{row['owner_name']:<30} │ {int(row['total_contacts']):<8} │ {int(row['contacted']):<10} │ {row['contact_rate']:<11.1f}% │ {avg_biz:<12} │ {avg_tot:<14} │ {diff:<12} │ {int(row['sql_count']):<6} │ {row['sql_rate']:<7.1f}% │ {int(row['pql_count']):<6} │ {row['pql_rate']:<7.1f}%")
    
    # Time to contact distribution comparison (business hours vs total hours)
    contacted_df = df[df['is_contacted']].copy()
    if len(contacted_df) > 0:
        print(f"\n{'='*100}")
        print("TIME TO CONTACT DISTRIBUTION - COMPARISON")
        print(f"{'='*100}")
        print("Business hours = 9 AM - 6 PM, Monday-Friday, excluding holidays, Argentina timezone")
        print("Total hours = All calendar hours (24/7)")
        
        # Business hours ranges
        biz_ranges = {
            "0-9 hours (0-1 day)": len(contacted_df[contacted_df['business_hours_to_contact'] <= 9]),
            "9-27 hours (1-3 days)": len(contacted_df[(contacted_df['business_hours_to_contact'] > 9) & (contacted_df['business_hours_to_contact'] <= 27)]),
            "27-63 hours (3-7 days)": len(contacted_df[(contacted_df['business_hours_to_contact'] > 27) & (contacted_df['business_hours_to_contact'] <= 63)]),
            "63+ hours (7+ days)": len(contacted_df[contacted_df['business_hours_to_contact'] > 63])
        }
        
        # Total hours ranges (converting to hours: 1 day = 24 hours, 3 days = 72 hours, 7 days = 168 hours)
        tot_ranges = {
            "0-24 hours (0-1 day)": len(contacted_df[contacted_df['total_hours_to_contact'] <= 24]),
            "24-72 hours (1-3 days)": len(contacted_df[(contacted_df['total_hours_to_contact'] > 24) & (contacted_df['total_hours_to_contact'] <= 72)]),
            "72-168 hours (3-7 days)": len(contacted_df[(contacted_df['total_hours_to_contact'] > 72) & (contacted_df['total_hours_to_contact'] <= 168)]),
            "168+ hours (7+ days)": len(contacted_df[contacted_df['total_hours_to_contact'] > 168])
        }
        
        print(f"\n{'Time Range':<35} │ {'Business Hours':<18} │ {'Total Hours':<18} │ {'Difference':<12}")
        print(f"{'─'*35}┼{'─'*18}┼{'─'*18}┼{'─'*12}")
        print(f"{'0-1 day':<35} │ {biz_ranges['0-9 hours (0-1 day)']:<18} │ {tot_ranges['0-24 hours (0-1 day)']:<18} │ {tot_ranges['0-24 hours (0-1 day)'] - biz_ranges['0-9 hours (0-1 day)']:<12}")
        print(f"{'1-3 days':<35} │ {biz_ranges['9-27 hours (1-3 days)']:<18} │ {tot_ranges['24-72 hours (1-3 days)']:<18} │ {tot_ranges['24-72 hours (1-3 days)'] - biz_ranges['9-27 hours (1-3 days)']:<12}")
        print(f"{'3-7 days':<35} │ {biz_ranges['27-63 hours (3-7 days)']:<18} │ {tot_ranges['72-168 hours (3-7 days)']:<18} │ {tot_ranges['72-168 hours (3-7 days)'] - biz_ranges['27-63 hours (3-7 days)']:<12}")
        print(f"{'7+ days':<35} │ {biz_ranges['63+ hours (7+ days)']:<18} │ {tot_ranges['168+ hours (7+ days)']:<18} │ {tot_ranges['168+ hours (7+ days)'] - biz_ranges['63+ hours (7+ days)']:<12}")
        
        # Calculate percentages
        print(f"\n{'Time Range':<35} │ {'Business Hours %':<18} │ {'Total Hours %':<18} │ {'Difference %':<12}")
        print(f"{'─'*35}┼{'─'*18}┼{'─'*18}┼{'─'*12}")
        for i, range_key in enumerate(["0-9 hours (0-1 day)", "9-27 hours (1-3 days)", "27-63 hours (3-7 days)", "63+ hours (7+ days)"]):
            tot_key = ["0-24 hours (0-1 day)", "24-72 hours (1-3 days)", "72-168 hours (3-7 days)", "168+ hours (7+ days)"][i]
            biz_pct = (biz_ranges[range_key] / len(contacted_df) * 100) if len(contacted_df) > 0 else 0
            tot_pct = (tot_ranges[tot_key] / len(contacted_df) * 100) if len(contacted_df) > 0 else 0
            range_label = ["0-1 day", "1-3 days", "3-7 days", "7+ days"][i]
            print(f"{range_label:<35} │ {biz_pct:<17.1f}% │ {tot_pct:<17.1f}% │ {tot_pct - biz_pct:<11.1f}%")
    
    # Score-based contactability analysis
    print(f"\n{'='*100}")
    print("SCORING × CONTACTABILITY ANALYSIS")
    print(f"{'='*100}")
    print("📊 Scoring Field: fit_score_contador (0-100 scale)")
    print("   Note: Despite the name 'contador', this field is used for both SMBs (PyMEs) and accountants")
    print("   Analysis includes only contacts with score ≥ 40 (High-Quality leads)")
    print("   Score Ranges: 40-49, 50-59, 60-69, 70-79, 80-89, 90-100")
    
    def categorize_score(score):
        """Categorize score into ranges (for contacts with score ≥ 40)"""
        if pd.isna(score):
            return 'No Score'
        elif score >= 90:
            return '90-100'
        elif score >= 80:
            return '80-89'
        elif score >= 70:
            return '70-79'
        elif score >= 60:
            return '60-69'
        elif score >= 50:
            return '50-59'
        elif score >= 40:
            return '40-49'
        else:
            return '<40'
    
    df['score_range'] = df['score'].apply(categorize_score)
    
    # Analyze by score range
    score_analysis = []
    for range_name in ['90-100', '80-89', '70-79', '60-69', '50-59', '40-49']:
        range_df = df[df['score_range'] == range_name]
        
        if len(range_df) == 0:
            continue
        
        total = len(range_df)
        contacted = range_df['is_contacted'].sum()
        contact_rate = (contacted / total * 100) if total > 0 else 0
        
        # Average times for contacted contacts
        contacted_range_df = range_df[range_df['is_contacted']]
        avg_biz_hours = contacted_range_df['business_hours_to_contact'].mean() if len(contacted_range_df) > 0 else None
        avg_total_hours = contacted_range_df['total_hours_to_contact'].mean() if len(contacted_range_df) > 0 else None
        difference = (avg_total_hours - avg_biz_hours) if (avg_total_hours is not None and avg_biz_hours is not None) else None
        
        # SQL and PQL conversion rates
        sql_count = range_df['is_sql'].sum()
        sql_rate = (sql_count / total * 100) if total > 0 else 0
        pql_count = range_df['is_pql'].sum()
        pql_rate = (pql_count / total * 100) if total > 0 else 0
        
        score_analysis.append({
            'score_range': range_name,
            'total_contacts': total,
            'contacted': contacted,
            'contact_rate': contact_rate,
            'avg_biz_hours': avg_biz_hours,
            'avg_total_hours': avg_total_hours,
            'difference': difference,
            'sql_count': sql_count,
            'sql_rate': sql_rate,
            'pql_count': pql_count,
            'pql_rate': pql_rate
        })
    
    score_analysis_df = pd.DataFrame(score_analysis).sort_values('score_range', ascending=False)
    
    if len(score_analysis_df) > 0:
        print(f"\n{'Score Range':<12} │ {'Total':<8} │ {'Contacted':<10} │ {'Contact %':<12} │ {'Avg Biz Hrs':<14} │ {'Avg Total Hrs':<16} │ {'Difference':<12} │ {'SQL':<6} │ {'SQL %':<8} │ {'PQL':<6} │ {'PQL %':<8}")
        print(f"{'─'*12}┼{'─'*8}┼{'─'*10}┼{'─'*12}┼{'─'*14}┼{'─'*16}┼{'─'*12}┼{'─'*6}┼{'─'*8}┼{'─'*6}┼{'─'*8}")
        print(f"{'':<12} │ {'Contacts':<8} │ {'Contacts':<10} │ {'Rate':<12} │ {'(9AM-6PM)':<14} │ {'(24/7)':<16} │ {'(non-biz)':<12} │ {'Count':<6} │ {'Rate':<8} │ {'Count':<6} │ {'Rate':<8}")
        print(f"{'─'*12}┼{'─'*8}┼{'─'*10}┼{'─'*12}┼{'─'*14}┼{'─'*16}┼{'─'*12}┼{'─'*6}┼{'─'*8}┼{'─'*6}┼{'─'*8}")
        for _, row in score_analysis_df.iterrows():
            avg_biz = f"{row['avg_biz_hours']:.1f}" if pd.notna(row['avg_biz_hours']) else "N/A"
            avg_tot = f"{row['avg_total_hours']:.1f}" if pd.notna(row['avg_total_hours']) else "N/A"
            diff = f"{row['difference']:.1f}" if pd.notna(row['difference']) else "N/A"
            print(f"{row['score_range']:<12} │ {int(row['total_contacts']):<8} │ {int(row['contacted']):<10} │ {row['contact_rate']:<11.1f}% │ {avg_biz:<14} │ {avg_tot:<16} │ {diff:<12} │ {int(row['sql_count']):<6} │ {row['sql_rate']:<7.1f}% │ {int(row['pql_count']):<6} │ {row['pql_rate']:<7.1f}%")
    
    # Unengaged contacts
    unengaged = df[~df['is_contacted']].copy()
    if len(unengaged) > 0:
        print(f"\n{'='*100}")
        print(f"UNENGAGED HIGH-SCORE CONTACTS ({len(unengaged)} contacts)")
        print(f"{'='*100}")
        
        unengaged_by_owner = unengaged.groupby('owner_id').size().sort_values(ascending=False)
        
        print(f"\n{'Owner Name':<30} │ {'Unengaged Count':<18} │ {'Percentage':<12}")
        print(f"{'─'*30}┼{'─'*18}┼{'─'*12}")
        for owner_id, count in unengaged_by_owner.items():
            owner_name = get_owner_name(owner_id)
            pct = (count / len(unengaged) * 100) if len(unengaged) > 0 else 0
            print(f"{owner_name:<30} │ {count:<18} │ {pct:<11.1f}%")
        
        # Show sample unengaged contacts
        print(f"\n📋 Sample Unengaged Contacts (First 20):")
        for i, (_, contact) in enumerate(unengaged.head(20).iterrows(), 1):
            name = f"{contact['firstname']} {contact['lastname']}".strip() if contact['firstname'] or contact['lastname'] else contact['email']
            contact_link = generate_contact_link(contact['contact_id'])
            print(f"{i:2}. {name:<30} | Score: {contact['score']:.0f} | {contact['owner_name']:<25} | 🔗 {contact_link}")
    
    return df, owner_stats_df

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='High Score (40+) Sales Team Handling Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Specific date range
  python high_score_sales_handling_analysis.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
  
  # Specific month
  python high_score_sales_handling_analysis.py --month YYYY-MM
  
  # Current month-to-date
  python high_score_sales_handling_analysis.py --current-mtd
        """
    )
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    group.add_argument('--month', help='Month in YYYY-MM format')
    group.add_argument('--current-mtd', action='store_true', help='Current month-to-date')
    
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD) - use with --start-date')
    
    return parser.parse_args()

def get_month_dates(month_str):
    """Convert YYYY-MM to start/end dates for full month"""
    year, month = map(int, month_str.split('-'))
    start_date = datetime(year, month, 1)
    
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def get_current_month_to_date():
    """Get current month start to today"""
    today = datetime.now()
    start_date = datetime(today.year, today.month, 1)
    return start_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')

if __name__ == "__main__":
    args = parse_arguments()
    
    # Determine date range
    if args.current_mtd:
        start_date, end_date = get_current_month_to_date()
        period_label = f"{datetime.strptime(start_date, '%Y-%m-%d').strftime('%B').upper()} {start_date.split('-')[2]}-{end_date.split('-')[2]}, {start_date.split('-')[0]} (Month-to-Date)"
    elif args.month:
        start_date, end_date = get_month_dates(args.month)
        period_label = f"{datetime.strptime(start_date, '%Y-%m-%d').strftime('%B').upper()} {start_date.split('-')[0]}"
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
        period_label = f"{start_date} to {end_date}"
    else:
        # Default: current month-to-date
        start_date, end_date = get_current_month_to_date()
        period_label = f"{datetime.strptime(start_date, '%Y-%m-%d').strftime('%B').upper()} {start_date.split('-')[2]}-{end_date.split('-')[2]}, {start_date.split('-')[0]} (Month-to-Date)"
    
    print("="*100)
    print("HIGH SCORE (40+) SALES TEAM HANDLING ANALYSIS")
    print(f"{period_label}")
    print("="*100)
    
    # Fetch contacts
    contacts = fetch_high_score_contacts(start_date, end_date)
    
    if len(contacts) == 0:
        print("\n⚠️  No high-score contacts found. Exiting.")
        sys.exit(0)
    
    # Analyze
    result = analyze_sales_handling(contacts, period_label)
    
    if result:
        df, owner_stats_df = result
        
        # Save results
        output_dir = "tools/outputs"
        os.makedirs(output_dir, exist_ok=True)
        
        period_suffix = start_date.replace('-', '_') + '_' + end_date.replace('-', '_')
        df.to_csv(os.path.join(output_dir, f'high_score_contacts_{period_suffix}.csv'), index=False)
        owner_stats_df.to_csv(os.path.join(output_dir, f'high_score_owner_performance_{period_suffix}.csv'), index=False)
        
        print(f"\n✅ Results saved to tools/outputs/")
        print(f"   - high_score_contacts_{period_suffix}.csv")
        print(f"   - high_score_owner_performance_{period_suffix}.csv")

