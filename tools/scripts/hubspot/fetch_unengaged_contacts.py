#!/usr/bin/env python3
"""
Complete analysis of unengaged contacts from HubSpot
Fetches ALL pages and provides exact counts grouped by owner
"""
import json
from collections import defaultdict
from datetime import datetime

# Import owner utilities for fetching owner names from API
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from owner_utils import get_owner_name

PORTAL_ID = "19877595"
UI_DOMAIN = "app.hubspot.com"

def generate_contact_link(contact_id):
    """Generate HubSpot contact link"""
    return f"https://{UI_DOMAIN}/contacts/{PORTAL_ID}/contact/{contact_id}"

def analyze_unengaged_contacts(contacts_data, period_name):
    """Analyze unengaged contacts and generate report"""
    # Count by owner
    owner_counts = defaultdict(list)
    total_contacts = len(contacts_data)
    
    for contact in contacts_data:
        owner_id = contact.get('hubspot_owner_id') or 'No Owner'
        owner_counts[owner_id].append(contact)
    
    # Generate report
    print('=' * 110)
    print(f'COMPLETE ANALYSIS: {period_name}')
    print('=' * 110)
    print()
    print(f'📊 TOTAL UNENGAGED CONTACTS: {total_contacts}')
    print()
    print('📋 BREAKDOWN BY OWNER:')
    print('-' * 110)
    print(f"{'Owner Name':<35} {'Owner ID':<15} {'Count':>10} {'Percentage':>15} {'Sample Links':>30}")
    print('-' * 110)
    
    # Sort by count (descending)
    sorted_owners = sorted(owner_counts.items(), key=lambda x: len(x[1]), reverse=True)
    
    for owner_id, contacts in sorted_owners:
        owner_name = get_owner_name(owner_id)
        count = len(contacts)
        percentage = (count / total_contacts * 100) if total_contacts > 0 else 0
        
        # Show first 3 contact links as samples
        sample_links = []
        for i, contact in enumerate(contacts[:3]):
            link = generate_contact_link(contact['id'])
            sample_links.append(f"Link {i+1}")
        
        links_display = f"{len(sample_links)} links" if sample_links else "No links"
        
        print(f"{owner_name:<35} {owner_id:<15} {count:>10} {percentage:>14.2f}% {links_display:>30}")
    
    print('-' * 110)
    print()
    
    # Show sample contacts with clickable links
    print('📎 SAMPLE CONTACTS (First 20 with clickable links):')
    print('-' * 110)
    for i, contact in enumerate(contacts_data[:20], 1):
        owner_id = contact.get('hubspot_owner_id') or 'No Owner'
        owner_name = get_owner_name(owner_id)
        email = contact.get('email', 'No email')
        firstname = contact.get('firstname', '')
        created_date = contact.get('createdate', '')
        
        # Parse and format date
        try:
            if created_date:
                dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                date_str = dt.strftime('%Y-%m-%d')
            else:
                date_str = 'N/A'
        except:
            date_str = created_date[:10] if created_date else 'N/A'
        
        contact_link = generate_contact_link(contact['id'])
        name_display = firstname if firstname else email.split('@')[0] if email else 'Unknown'
        
        print(f"{i:2}. {name_display:<25} | {email:<35} | {date_str} | {owner_name}")
        print(f"    Link: {contact_link}")
        print()
    
    if len(contacts_data) > 20:
        print(f"    ... and {len(contacts_data) - 20} more contacts")
        print()
    
    print('=' * 110)
    print()
    
    return {
        'total': total_contacts,
        'by_owner': {owner_id: len(contacts) for owner_id, contacts in owner_counts.items()},
        'contacts': contacts_data
    }

# Note: This script structure is ready for integration with HubSpot API calls
# The actual API calls would be made using the hubspot-search-objects tool
# and the results would be passed to analyze_unengaged_contacts()

if __name__ == "__main__":
    print("This script is designed to be used with HubSpot API integration.")
    print("The analyze_unengaged_contacts() function processes contact data")
    print("and generates comprehensive reports with clickable links.")














