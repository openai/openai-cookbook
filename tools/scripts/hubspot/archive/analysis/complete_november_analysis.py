#!/usr/bin/env python3
"""
Complete November 2025 Analysis:
1. Time to First Contact (Cycle Time) for Engaged Contacts
2. Unengaged Contacts Analysis
Both grouped by owner with clickable HubSpot links
"""
import json
from collections import defaultdict
from datetime import datetime, timedelta
import pytz

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

# Import owner utilities for fetching owner names from API
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from owner_utils import get_owner_name

PORTAL_ID = "19877595"
UI_DOMAIN = "app.hubspot.com"

def generate_contact_link(contact_id):
    return f"https://{UI_DOMAIN}/contacts/{PORTAL_ID}/contact/{contact_id}"

def is_holiday(dt):
    """Check if date is a holiday"""
    dt_ar = dt.astimezone(AR_TIMEZONE) if dt.tzinfo else AR_TIMEZONE.localize(dt)
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
    if end_dt <= start_dt:
        return 0.0
    
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

def parse_datetime(dt_str):
    """Parse HubSpot datetime string to datetime object"""
    if not dt_str:
        return None
    try:
        # Handle both with and without Z
        if dt_str.endswith('Z'):
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt
    except:
        return None

def process_engaged_contacts(contacts_data, title):
    """Process engaged contacts and calculate cycle time"""
    engaged_contacts = []
    
    for contact in contacts_data:
        created_str = contact.get('properties', {}).get('createdate')
        engagement_str = contact.get('properties', {}).get('hs_sa_first_engagement_date')
        
        if not created_str or not engagement_str:
            continue
        
        created_dt = parse_datetime(created_str)
        engagement_dt = parse_datetime(engagement_str)
        
        if not created_dt or not engagement_dt:
            continue
        
        cycle_time_hours = calculate_business_hours(created_dt, engagement_dt)
        
        contact_info = {
            'id': contact.get('id'),
            'createdate': created_str,
            'engagement_date': engagement_str,
            'cycle_time_hours': cycle_time_hours,
            'owner_id': contact.get('properties', {}).get('hubspot_owner_id', 'No Owner'),
            'firstname': contact.get('properties', {}).get('firstname', ''),
            'lastname': contact.get('properties', {}).get('lastname', ''),
            'email': contact.get('properties', {}).get('email', ''),
        }
        engaged_contacts.append(contact_info)
    
    # Group by owner
    by_owner = defaultdict(list)
    for contact in engaged_contacts:
        owner_id = contact['owner_id']
        by_owner[owner_id].append(contact)
    
    print(f"\n{'=' * 110}")
    print(f"TIME TO FIRST CONTACT ANALYSIS - {title}")
    print(f"{'=' * 110}")
    print()
    
    if not engaged_contacts:
        print("No engaged contacts found for this period.")
        return
    
    total_contacts = len(engaged_contacts)
    total_hours = sum(c['cycle_time_hours'] for c in engaged_contacts)
    avg_hours = total_hours / total_contacts if total_contacts > 0 else 0
    
    print(f"Total Engaged Contacts: {total_contacts}")
    print(f"Average Cycle Time: {avg_hours:.2f} business hours")
    print()
    print(f"{'Owner Name':<30} {'Owner ID':<15} {'Contacts':>10} {'Avg Hours':>12} {'Total Hours':>15}")
    print("-" * 82)
    
    for owner_id, contact_list in sorted(by_owner.items(), key=lambda item: len(item[1]), reverse=True):
        owner_name = get_owner_name(owner_id)
        owner_total_hours = sum(c['cycle_time_hours'] for c in contact_list)
        owner_avg_hours = owner_total_hours / len(contact_list) if contact_list else 0
        print(f"{owner_name:<30} {owner_id:<15} {len(contact_list):>10} {owner_avg_hours:>12.2f} {owner_total_hours:>15.2f}")
    
    print("-" * 82)
    print(f"{'TOTAL':<45} {total_contacts:>10} {avg_hours:>12.2f} {total_hours:>15.2f}")
    print(f"{'=' * 110}")
    
    # Show examples with clickable links
    print("\n📋 Examples (First 20 contacts with clickable links):")
    print()
    for i, contact in enumerate(engaged_contacts[:20], 1):
        owner_name = get_owner_name(contact['owner_id'])
        contact_link = generate_contact_link(contact['id'])
        created_date = datetime.fromisoformat(contact['createdate'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
        name = f"{contact['firstname']} {contact['lastname']}".strip() if contact['firstname'] or contact['lastname'] else contact['email']
        
        print(f"{i:2}. {name:<30} | Created: {created_date} | Cycle Time: {contact['cycle_time_hours']:.2f} hrs | {owner_name}")
        print(f"    🔗 {contact_link}")
        print()

def process_unengaged_contacts(contacts_data, title):
    """Process unengaged contacts"""
    # Deduplicate by contact ID
    unique_contacts = {}
    for contact in contacts_data:
        contact_id = contact.get('id')
        if contact_id:
            unique_contacts[contact_id] = contact
    
    # Group by owner
    unengaged_by_owner = defaultdict(list)
    for contact in unique_contacts.values():
        owner_id = contact.get('properties', {}).get('hubspot_owner_id', 'No Owner')
        unengaged_by_owner[owner_id].append(contact)
    
    total_unengaged = len(unique_contacts)
    
    print(f"\n{'=' * 110}")
    print(f"UNENGAGED CONTACTS ANALYSIS - {title}")
    print(f"{'=' * 110}")
    print()
    
    if total_unengaged == 0:
        print("No unengaged contacts found for this period.")
        return
    
    print(f"{'Owner Name':<30} {'Owner ID':<15} {'Unengaged Contacts':>20} {'Percentage':>15}")
    print("-" * 80)
    
    for owner_id, contact_list in sorted(unengaged_by_owner.items(), key=lambda item: len(item[1]), reverse=True):
        owner_name = get_owner_name(owner_id)
        percentage = (len(contact_list) / total_unengaged) * 100
        print(f"{owner_name:<30} {owner_id:<15} {len(contact_list):>20} {percentage:>14.2f}%")
    
    print("-" * 80)
    print(f"{'TOTAL':<45} {total_unengaged:>20} {100.00:>14.2f}%")
    print(f"{'=' * 110}")
    
    # Show examples with clickable links
    print("\n📋 Examples (First 20 contacts with clickable links):")
    print()
    for i, contact in enumerate(list(unique_contacts.values())[:20], 1):
        owner_id = contact.get('properties', {}).get('hubspot_owner_id', 'No Owner')
        owner_name = get_owner_name(owner_id)
        contact_link = generate_contact_link(contact['id'])
        created_date = datetime.fromisoformat(contact['properties']['createdate'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
        first_name = contact['properties'].get('firstname', '')
        last_name = contact['properties'].get('lastname', '')
        email = contact['properties'].get('email', '')
        
        name = f"{first_name} {last_name}".strip() if first_name or last_name else email
        
        print(f"{i:2}. {name:<30} | {created_date} | {owner_name}")
        print(f"    🔗 {contact_link}")
        print()

if __name__ == "__main__":
    print('=' * 110)
    print('COMPLETE NOVEMBER 2025 ANALYSIS')
    print('=' * 110)
    print()
    print('This script will process:')
    print('  1. Engaged contacts - Time to First Contact (Cycle Time)')
    print('  2. Unengaged contacts - Never touched by sales')
    print()
    print('Note: Contact data needs to be collected from API responses.')
    print()














