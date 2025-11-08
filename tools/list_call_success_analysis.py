#!/usr/bin/env python3
"""
HubSpot List - Call Success Analysis
Analyzes actual call attempts and outcomes using Engagements API
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

class CallSuccessAnalyzer:
    """Analyze call success using HubSpot Engagements API"""
    
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
        
        print(f"📥 Fetching companies from list...")
        
        while True:
            params = {'limit': 100}
            if after:
                params['after'] = after
            
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code != 200:
                break
            
            data = response.json()
            batch = [m.get('recordId') for m in data.get('results', [])]
            all_ids.extend(batch)
            
            print(f"   Retrieved {len(batch)} companies (Total: {len(all_ids)})")
            
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after:
                break
        
        return all_ids
    
    def get_company_engagements(self, company_id: str) -> dict:
        """Get all engagements for a company"""
        url = f"{self.base_url}/engagements/v1/engagements/associated/company/{company_id}/paged"
        
        all_engagements = []
        offset = 0
        
        while True:
            params = {'limit': 100, 'offset': offset}
            
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                engagements = data.get('results', [])
                
                if not engagements:
                    break
                
                all_engagements.extend(engagements)
                
                if not data.get('hasMore', False):
                    break
                
                offset = data.get('offset', 0)
                
            except Exception as e:
                break
        
        # Categorize engagements
        calls = []
        emails = []
        meetings = []
        notes = []
        tasks = []
        
        for eng in all_engagements:
            eng_type = eng.get('engagement', {}).get('type')
            
            if eng_type == 'CALL':
                calls.append(eng)
            elif eng_type == 'EMAIL':
                emails.append(eng)
            elif eng_type == 'MEETING':
                meetings.append(eng)
            elif eng_type == 'NOTE':
                notes.append(eng)
            elif eng_type == 'TASK':
                tasks.append(eng)
        
        return {
            'total': len(all_engagements),
            'calls': calls,
            'emails': emails,
            'meetings': meetings,
            'notes': notes,
            'tasks': tasks
        }
    
    def analyze_call_outcomes(self, calls: list) -> dict:
        """Analyze call outcomes and success"""
        
        stats = {
            'total_calls': len(calls),
            'by_status': defaultdict(int),
            'by_disposition': defaultdict(int),
            'by_direction': defaultdict(int),
            'by_duration': {
                'under_1_min': 0,
                '1_to_3_min': 0,
                '3_to_5_min': 0,
                'over_5_min': 0
            },
            'successful_connections': 0,
            'voicemails': 0,
            'no_answers': 0,
            'wrong_numbers': 0,
            'calls_by_month': defaultdict(int),
            'recent_calls': {
                'last_7_days': 0,
                'last_30_days': 0,
                'last_60_days': 0,
                'last_90_days': 0
            }
        }
        
        now = datetime.now()
        
        for call in calls:
            engagement = call.get('engagement', {})
            metadata = call.get('metadata', {})
            
            # Status
            status = metadata.get('status', 'UNKNOWN')
            stats['by_status'][status] += 1
            
            # Disposition
            disposition = metadata.get('disposition', 'UNKNOWN')
            stats['by_disposition'][disposition] += 1
            
            # Direction
            direction = metadata.get('direction', 'UNKNOWN')
            stats['by_direction'][direction] += 1
            
            # Duration
            duration_ms = metadata.get('durationMilliseconds', 0)
            duration_sec = duration_ms / 1000 if duration_ms else 0
            
            if duration_sec < 60:
                stats['by_duration']['under_1_min'] += 1
            elif duration_sec < 180:
                stats['by_duration']['1_to_3_min'] += 1
            elif duration_sec < 300:
                stats['by_duration']['3_to_5_min'] += 1
            else:
                stats['by_duration']['over_5_min'] += 1
            
            # Success indicators
            if status == 'COMPLETED' and duration_sec > 30:
                stats['successful_connections'] += 1
            
            # Call timing
            timestamp = engagement.get('timestamp')
            if timestamp:
                call_date = datetime.fromtimestamp(timestamp / 1000)
                month_key = call_date.strftime('%Y-%m')
                stats['calls_by_month'][month_key] += 1
                
                # Recent calls
                days_ago = (now - call_date).days
                if days_ago <= 7:
                    stats['recent_calls']['last_7_days'] += 1
                if days_ago <= 30:
                    stats['recent_calls']['last_30_days'] += 1
                if days_ago <= 60:
                    stats['recent_calls']['last_60_days'] += 1
                if days_ago <= 90:
                    stats['recent_calls']['last_90_days'] += 1
        
        return stats
    
    def analyze_list(self, list_id: str, sample_size: int = 100):
        """Analyze call success for a list"""
        
        print(f"🚀 Call Success Analysis - List {list_id}")
        print("=" * 80)
        
        # Get list details
        response = requests.get(f"{self.base_url}/crm/v3/lists/{list_id}", headers=self.headers)
        list_data = response.json().get('list', {})
        list_name = list_data.get('name', 'Unknown')
        list_size = list_data.get('size', 0)
        
        print(f"📋 List: {list_name}")
        print(f"📊 Size: {list_size:,} companies")
        print()
        
        # Get company IDs
        company_ids = self.get_list_companies(list_id)
        print(f"✅ Found {len(company_ids):,} companies")
        print()
        
        # Sample companies for analysis (or all if small list)
        if len(company_ids) > sample_size:
            print(f"📊 Analyzing sample of {sample_size} companies...")
            sample_ids = company_ids[:sample_size]
        else:
            print(f"📊 Analyzing all {len(company_ids)} companies...")
            sample_ids = company_ids
        
        # Get engagements for each company
        print(f"\n📞 Fetching call data...")
        
        companies_with_calls = 0
        companies_without_calls = 0
        all_calls = []
        all_engagements_by_company = []
        
        for i, comp_id in enumerate(sample_ids, 1):
            if i % 50 == 0:
                print(f"   Processed {i}/{len(sample_ids)} companies...")
            
            engagements = self.get_company_engagements(comp_id)
            
            company_data = {
                'company_id': comp_id,
                'total_engagements': engagements['total'],
                'calls': len(engagements['calls']),
                'emails': len(engagements['emails']),
                'meetings': len(engagements['meetings']),
                'notes': len(engagements['notes']),
                'tasks': len(engagements['tasks'])
            }
            
            all_engagements_by_company.append(company_data)
            
            if len(engagements['calls']) > 0:
                companies_with_calls += 1
                all_calls.extend(engagements['calls'])
            else:
                companies_without_calls += 1
        
        print(f"✅ Completed fetching engagements")
        print()
        
        # Analyze calls
        call_stats = self.analyze_call_outcomes(all_calls)
        
        # Display results
        self.display_results(
            list_name, 
            list_size, 
            len(sample_ids),
            companies_with_calls,
            companies_without_calls,
            call_stats,
            all_engagements_by_company
        )
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"/Users/virulana/openai-cookbook/tools/outputs/list_{list_id}_call_analysis_{timestamp}.json"
        
        results = {
            'list_name': list_name,
            'list_id': list_id,
            'total_companies': list_size,
            'analyzed_companies': len(sample_ids),
            'companies_with_calls': companies_with_calls,
            'companies_without_calls': companies_without_calls,
            'call_stats': call_stats,
            'companies': all_engagements_by_company
        }
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to: {filename}")
        
        return results
    
    def display_results(self, list_name, list_size, analyzed, with_calls, without_calls, call_stats, companies):
        """Display call analysis results"""
        
        print("=" * 80)
        print("📞 CALL SUCCESS ANALYSIS RESULTS")
        print("=" * 80)
        
        print(f"\n📋 List: {list_name}")
        print(f"📊 Total Companies in List: {list_size:,}")
        print(f"🔍 Analyzed: {analyzed:,} companies")
        print()
        
        # Contact attempt rate
        print(f"📞 CALL ATTEMPT RATE")
        print("-" * 80)
        print(f"Companies Called: {with_calls:,}/{analyzed:,} ({with_calls/analyzed*100:.1f}%)")
        print(f"Companies NOT Called: {without_calls:,}/{analyzed:,} ({without_calls/analyzed*100:.1f}%)")
        print()
        
        if call_stats['total_calls'] == 0:
            print("❌ No calls found in analyzed sample")
            return
        
        # Call volume
        print(f"📊 CALL VOLUME")
        print("-" * 80)
        print(f"Total Calls Made: {call_stats['total_calls']:,}")
        print(f"Avg Calls per Company: {call_stats['total_calls']/with_calls:.1f}")
        print()
        
        # Call recency
        print(f"📅 CALL RECENCY")
        print("-" * 80)
        print(f"Last 7 days: {call_stats['recent_calls']['last_7_days']:,}")
        print(f"Last 30 days: {call_stats['recent_calls']['last_30_days']:,}")
        print(f"Last 60 days: {call_stats['recent_calls']['last_60_days']:,}")
        print(f"Last 90 days: {call_stats['recent_calls']['last_90_days']:,}")
        print()
        
        # Call outcomes
        print(f"✅ CALL OUTCOMES")
        print("-" * 80)
        total = call_stats['total_calls']
        print(f"Successful Connections: {call_stats['successful_connections']:,} ({call_stats['successful_connections']/total*100:.1f}%)")
        print()
        
        # Call status
        if call_stats['by_status']:
            print(f"Call Status Breakdown:")
            for status, count in sorted(call_stats['by_status'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {status}: {count:,} ({count/total*100:.1f}%)")
            print()
        
        # Call direction
        if call_stats['by_direction']:
            print(f"Call Direction:")
            for direction, count in sorted(call_stats['by_direction'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {direction}: {count:,} ({count/total*100:.1f}%)")
            print()
        
        # Call duration
        print(f"📏 CALL DURATION")
        print("-" * 80)
        print(f"Under 1 minute: {call_stats['by_duration']['under_1_min']:,} ({call_stats['by_duration']['under_1_min']/total*100:.1f}%)")
        print(f"1-3 minutes: {call_stats['by_duration']['1_to_3_min']:,} ({call_stats['by_duration']['1_to_3_min']/total*100:.1f}%)")
        print(f"3-5 minutes: {call_stats['by_duration']['3_to_5_min']:,} ({call_stats['by_duration']['3_to_5_min']/total*100:.1f}%)")
        print(f"Over 5 minutes: {call_stats['by_duration']['over_5_min']:,} ({call_stats['by_duration']['over_5_min']/total*100:.1f}%)")
        print()
        
        # Disposition
        if call_stats['by_disposition']:
            print(f"📋 CALL DISPOSITIONS (Top 10)")
            print("-" * 80)
            for disp, count in sorted(call_stats['by_disposition'].items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"{disp}: {count:,} ({count/total*100:.1f}%)")
            print()
        
        # Monthly trend
        if call_stats['calls_by_month']:
            print(f"📈 MONTHLY CALL TREND")
            print("-" * 80)
            for month in sorted(call_stats['calls_by_month'].keys(), reverse=True)[:6]:
                count = call_stats['calls_by_month'][month]
                print(f"{month}: {count:,} calls")
            print()
        
        print("=" * 80)


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
    sample_size = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    
    analyzer = CallSuccessAnalyzer(api_key)
    analyzer.analyze_list(list_id, sample_size)


if __name__ == "__main__":
    main()







