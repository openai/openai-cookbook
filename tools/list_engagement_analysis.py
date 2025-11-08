#!/usr/bin/env python3
"""
HubSpot List Engagement Analysis
Analyzes ACTUAL contact attempts and outcomes (calls, emails, meetings, etc.)
"""

import requests
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Load environment
try:
    from dotenv import load_dotenv
    env_path = Path('/Users/virulana/openai-cookbook/.env')
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

class EngagementAnalyzer:
    """Analyze actual contact attempts and outcomes"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def get_list_companies(self, list_id: str) -> list:
        """Get all company IDs from list"""
        url = f"{self.base_url}/crm/v3/lists/{list_id}/memberships"
        all_ids = []
        after = None
        
        while True:
            params = {'limit': 100}
            if after:
                params['after'] = after
            
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code != 200:
                break
            
            data = response.json()
            all_ids.extend([m.get('recordId') for m in data.get('results', [])])
            
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after:
                break
        
        return all_ids
    
    def get_companies_with_engagement(self, company_ids: list) -> list:
        """Get companies with all engagement properties"""
        
        engagement_props = [
            # Basic
            'name', 'type', 'hubspot_owner_id', 'createdate',
            
            # Last Contact
            'notes_last_contacted', 'notes_last_updated', 'notes_next_activity_date',
            
            # Activity Counts
            'num_contacted_notes', 'num_notes', 'num_associated_deals',
            
            # Sales Activity
            'hs_last_sales_activity_timestamp', 'hs_last_sales_activity_type',
            'hs_last_sales_activity_date',
            
            # Email
            'hs_sales_email_last_replied', 'hs_email_last_send_date',
            'hs_email_last_open_date', 'hs_email_last_click_date',
            
            # Calls
            'hs_last_call_disposition', 'hs_last_call_outcome',
            
            # Meetings
            'engagements_last_meeting_booked', 'hs_latest_meeting_activity',
            'num_conversion_events',
            
            # Lifecycle
            'lifecyclestage', 'hs_lifecyclestage_customer_date',
            'hs_analytics_last_timestamp'
        ]
        
        all_companies = []
        
        # Process in batches of 100
        for i in range(0, len(company_ids), 100):
            batch = company_ids[i:i+100]
            
            payload = {
                'properties': engagement_props,
                'inputs': [{'id': cid} for cid in batch]
            }
            
            response = requests.post(
                f"{self.base_url}/crm/v3/objects/companies/batch/read",
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                all_companies.extend(response.json().get('results', []))
        
        return all_companies
    
    def analyze_engagement(self, companies: list) -> dict:
        """Analyze engagement patterns"""
        
        total = len(companies)
        
        stats = {
            'total_companies': total,
            'contacted': {
                'ever_contacted': 0,
                'contacted_last_30_days': 0,
                'contacted_last_60_days': 0,
                'contacted_last_90_days': 0,
                'never_contacted': 0
            },
            'engagement_types': {
                'has_notes': 0,
                'has_calls': 0,
                'has_emails': 0,
                'has_meetings': 0,
                'has_deals': 0
            },
            'email_engagement': {
                'sent': 0,
                'opened': 0,
                'clicked': 0,
                'replied': 0
            },
            'call_outcomes': defaultdict(int),
            'sales_activity_types': defaultdict(int),
            'companies_by_engagement': {
                'high': [],  # Multiple touchpoints
                'medium': [],  # Some touchpoints
                'low': [],  # Minimal touchpoints
                'none': []  # No touchpoints
            }
        }
        
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)
        ninety_days_ago = now - timedelta(days=90)
        
        for company in companies:
            props = company.get('properties', {})
            comp_id = company.get('id')
            name = props.get('name', 'Unknown')
            
            # Contact dates
            last_contacted = props.get('notes_last_contacted')
            
            if last_contacted:
                stats['contacted']['ever_contacted'] += 1
                
                try:
                    contact_date = datetime.fromisoformat(last_contacted.replace('Z', '+00:00'))
                    
                    if contact_date >= thirty_days_ago:
                        stats['contacted']['contacted_last_30_days'] += 1
                    if contact_date >= sixty_days_ago:
                        stats['contacted']['contacted_last_60_days'] += 1
                    if contact_date >= ninety_days_ago:
                        stats['contacted']['contacted_last_90_days'] += 1
                except:
                    pass
            else:
                stats['contacted']['never_contacted'] += 1
            
            # Engagement counts
            num_notes = int(props.get('num_notes') or 0)
            num_deals = int(props.get('num_associated_deals') or 0)
            
            if num_notes > 0:
                stats['engagement_types']['has_notes'] += 1
            
            if num_deals > 0:
                stats['engagement_types']['has_deals'] += 1
            
            # Email engagement
            if props.get('hs_email_last_send_date'):
                stats['email_engagement']['sent'] += 1
            
            if props.get('hs_email_last_open_date'):
                stats['email_engagement']['opened'] += 1
            
            if props.get('hs_email_last_click_date'):
                stats['email_engagement']['clicked'] += 1
            
            if props.get('hs_sales_email_last_replied'):
                stats['email_engagement']['replied'] += 1
            
            # Call outcomes
            call_outcome = props.get('hs_last_call_outcome')
            if call_outcome:
                stats['call_outcomes'][call_outcome] += 1
                stats['engagement_types']['has_calls'] += 1
            
            # Sales activity types
            activity_type = props.get('hs_last_sales_activity_type')
            if activity_type:
                stats['sales_activity_types'][activity_type] += 1
            
            # Meetings
            if props.get('engagements_last_meeting_booked'):
                stats['engagement_types']['has_meetings'] += 1
            
            # Categorize by engagement level
            engagement_score = 0
            engagement_score += min(num_notes, 5)  # Up to 5 points for notes
            engagement_score += 2 if num_deals > 0 else 0
            engagement_score += 1 if props.get('hs_email_last_send_date') else 0
            engagement_score += 1 if props.get('hs_sales_email_last_replied') else 0
            engagement_score += 1 if call_outcome else 0
            engagement_score += 2 if props.get('engagements_last_meeting_booked') else 0
            
            company_data = {
                'id': comp_id,
                'name': name,
                'engagement_score': engagement_score,
                'last_contacted': last_contacted,
                'num_notes': num_notes,
                'num_deals': num_deals
            }
            
            if engagement_score >= 7:
                stats['companies_by_engagement']['high'].append(company_data)
            elif engagement_score >= 4:
                stats['companies_by_engagement']['medium'].append(company_data)
            elif engagement_score >= 1:
                stats['companies_by_engagement']['low'].append(company_data)
            else:
                stats['companies_by_engagement']['none'].append(company_data)
        
        return stats
    
    def display_results(self, list_name: str, stats: dict):
        """Display engagement analysis results"""
        
        total = stats['total_companies']
        
        print(f"\n{'=' * 80}")
        print(f"📞 ENGAGEMENT & CONTACTABILITY ANALYSIS")
        print(f"{'=' * 80}\n")
        
        print(f"📋 List: {list_name}")
        print(f"📊 Total Companies: {total:,}")
        print()
        
        # Contact recency
        print(f"📅 CONTACT RECENCY")
        print(f"-" * 80)
        print(f"Ever Contacted: {stats['contacted']['ever_contacted']:,} ({stats['contacted']['ever_contacted']/total*100:.1f}%)")
        print(f"Never Contacted: {stats['contacted']['never_contacted']:,} ({stats['contacted']['never_contacted']/total*100:.1f}%)")
        print(f"  Last 30 days: {stats['contacted']['contacted_last_30_days']:,} ({stats['contacted']['contacted_last_30_days']/total*100:.1f}%)")
        print(f"  Last 60 days: {stats['contacted']['contacted_last_60_days']:,} ({stats['contacted']['contacted_last_60_days']/total*100:.1f}%)")
        print(f"  Last 90 days: {stats['contacted']['contacted_last_90_days']:,} ({stats['contacted']['contacted_last_90_days']/total*100:.1f}%)")
        
        # Engagement types
        print(f"\n📊 ENGAGEMENT TYPES")
        print(f"-" * 80)
        print(f"Companies with Notes: {stats['engagement_types']['has_notes']:,} ({stats['engagement_types']['has_notes']/total*100:.1f}%)")
        print(f"Companies with Calls: {stats['engagement_types']['has_calls']:,} ({stats['engagement_types']['has_calls']/total*100:.1f}%)")
        print(f"Companies with Emails: {stats['email_engagement']['sent']:,} ({stats['email_engagement']['sent']/total*100:.1f}%)")
        print(f"Companies with Meetings: {stats['engagement_types']['has_meetings']:,} ({stats['engagement_types']['has_meetings']/total*100:.1f}%)")
        print(f"Companies with Deals: {stats['engagement_types']['has_deals']:,} ({stats['engagement_types']['has_deals']/total*100:.1f}%)")
        
        # Email outcomes
        if stats['email_engagement']['sent'] > 0:
            print(f"\n📧 EMAIL OUTCOMES")
            print(f"-" * 80)
            sent = stats['email_engagement']['sent']
            print(f"Emails Sent: {sent:,}")
            print(f"  Opened: {stats['email_engagement']['opened']:,} ({stats['email_engagement']['opened']/sent*100:.1f}%)")
            print(f"  Clicked: {stats['email_engagement']['clicked']:,} ({stats['email_engagement']['clicked']/sent*100:.1f}%)")
            print(f"  Replied: {stats['email_engagement']['replied']:,} ({stats['email_engagement']['replied']/sent*100:.1f}%)")
        
        # Call outcomes
        if stats['call_outcomes']:
            print(f"\n📞 CALL OUTCOMES")
            print(f"-" * 80)
            for outcome, count in sorted(stats['call_outcomes'].items(), key=lambda x: x[1], reverse=True):
                print(f"{outcome}: {count:,}")
        
        # Activity types
        if stats['sales_activity_types']:
            print(f"\n🎯 SALES ACTIVITY TYPES")
            print(f"-" * 80)
            for activity, count in sorted(stats['sales_activity_types'].items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"{activity}: {count:,}")
        
        # Engagement levels
        print(f"\n🔥 ENGAGEMENT LEVELS")
        print(f"-" * 80)
        print(f"High Engagement (7+ score): {len(stats['companies_by_engagement']['high']):,} ({len(stats['companies_by_engagement']['high'])/total*100:.1f}%)")
        print(f"Medium Engagement (4-6): {len(stats['companies_by_engagement']['medium']):,} ({len(stats['companies_by_engagement']['medium'])/total*100:.1f}%)")
        print(f"Low Engagement (1-3): {len(stats['companies_by_engagement']['low']):,} ({len(stats['companies_by_engagement']['low'])/total*100:.1f}%)")
        print(f"No Engagement (0): {len(stats['companies_by_engagement']['none']):,} ({len(stats['companies_by_engagement']['none'])/total*100:.1f}%)")
        
        print(f"\n{'=' * 80}\n")
    
    def analyze_list(self, list_id: str):
        """Complete engagement analysis"""
        
        print(f"🔍 Getting list details...")
        response = requests.get(f"{self.base_url}/crm/v3/lists/{list_id}", headers=self.headers)
        list_data = response.json().get('list', {})
        list_name = list_data.get('name', 'Unknown')
        
        print(f"📋 List: {list_name}")
        print(f"📊 Size: {list_data.get('size', 0):,} companies")
        print()
        
        print(f"🔍 Getting company IDs...")
        company_ids = self.get_list_companies(list_id)
        print(f"✅ Found {len(company_ids):,} companies")
        print()
        
        print(f"📥 Fetching engagement data...")
        companies = self.get_companies_with_engagement(company_ids)
        print(f"✅ Retrieved {len(companies):,} company records")
        print()
        
        print(f"📊 Analyzing engagement patterns...")
        stats = self.analyze_engagement(companies)
        
        self.display_results(list_name, stats)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"/Users/virulana/openai-cookbook/tools/outputs/list_{list_id}_engagement_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(stats, f, indent=2, default=str)
        
        print(f"💾 Results saved to: {filename}\n")
        
        return stats


def main():
    import sys
    
    api_key = (
        os.environ.get('HUBSPOT_API_KEY') or 
        os.environ.get('COLPPY_CRM_AUTOMATIONS')
    )
    
    if not api_key:
        print("❌ API key not found")
        return
    
    list_id = sys.argv[1] if len(sys.argv) > 1 else "2314"
    
    analyzer = EngagementAnalyzer(api_key)
    analyzer.analyze_list(list_id)


if __name__ == "__main__":
    main()

