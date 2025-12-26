#!/usr/bin/env python3
"""
Final comprehensive analysis of ALL unengaged contacts from November 2025
This script will process all fetched pages to provide exact counts
"""
from collections import defaultdict
from datetime import datetime

# Import owner utilities for fetching owner names from API
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from owner_utils import get_owner_name

PORTAL_ID = "19877595"
UI_DOMAIN = "app.hubspot.com"

def generate_contact_link(contact_id):
    """Generate HubSpot contact link"""
    return f"https://{UI_DOMAIN}/contacts/{PORTAL_ID}/contact/{contact_id}"

def format_date(date_str):
    """Format ISO date string to readable format"""
    try:
        if date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
    except:
        pass
    return date_str[:10] if date_str else 'N/A'

def process_contacts(contacts_list, period_name):
    """Process and analyze contacts"""
    # Deduplicate by contact ID
    unique_contacts = {}
    for contact in contacts_list:
        contact_id = contact.get('id')
        if contact_id:
            # Normalize contact data
            normalized = {
                'id': contact_id,
                'email': contact.get('properties', {}).get('email', ''),
                'firstname': contact.get('properties', {}).get('firstname', ''),
                'createdate': contact.get('properties', {}).get('createdate', ''),
                'hubspot_owner_id': contact.get('properties', {}).get('hubspot_owner_id', ''),
            }
            unique_contacts[contact_id] = normalized
    
    total = len(unique_contacts)
    
    # Group by owner
    owner_groups = defaultdict(list)
    for contact in unique_contacts.values():
        owner_id = contact.get('hubspot_owner_id') or 'No Owner'
        owner_groups[owner_id].append(contact)
    
    # Generate report
    print('=' * 110)
    print(f'COMPLETE ANALYSIS: {period_name}')
    print('=' * 110)
    print()
    print(f'📊 TOTAL UNENGAGED CONTACTS: {total}')
    print()
    print('📋 BREAKDOWN BY OWNER:')
    print('-' * 110)
    print(f"{'Owner Name':<35} {'Owner ID':<15} {'Count':>10} {'Percentage':>15}")
    print('-' * 110)
    
    # Sort by count (descending)
    sorted_owners = sorted(owner_groups.items(), key=lambda x: len(x[1]), reverse=True)
    
    for owner_id, owner_contacts in sorted_owners:
        owner_name = get_owner_name(owner_id)
        count = len(owner_contacts)
        percentage = (count / total * 100) if total > 0 else 0
        print(f"{owner_name:<35} {owner_id:<15} {count:>10} {percentage:>14.2f}%")
    
    print('-' * 110)
    print()
    
    # Show sample contacts with clickable links
    print('📎 SAMPLE CONTACTS (First 30 with clickable links):')
    print('-' * 110)
    
    sample_contacts = list(unique_contacts.values())[:30]
    for i, contact in enumerate(sample_contacts, 1):
        owner_id = contact.get('hubspot_owner_id') or 'No Owner'
        owner_name = get_owner_name(owner_id)
        email = contact.get('email', 'No email')
        firstname = contact.get('firstname', '')
        created_date = contact.get('createdate', '')
        date_str = format_date(created_date)
        
        contact_link = generate_contact_link(contact['id'])
        name_display = firstname if firstname else email.split('@')[0] if email else 'Unknown'
        
        print(f"{i:2}. {name_display:<25} | {email:<35} | {date_str} | {owner_name}")
        print(f"    Link: {contact_link}")
        print()
    
    if total > 30:
        print(f"    ... and {total - 30} more contacts")
        print()
    
    print('=' * 110)
    print()
    
    return {
        'total': total,
        'by_owner': {owner_id: len(contacts) for owner_id, contacts in owner_groups.items()},
        'unique_contacts': unique_contacts
    }

if __name__ == "__main__":
    print("This script processes contact data from HubSpot API calls.")
    print("The process_contacts() function generates comprehensive reports.")














