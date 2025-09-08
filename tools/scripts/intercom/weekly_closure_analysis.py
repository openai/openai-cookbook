#!/usr/bin/env python3
"""
Weekly Closure Analysis - Direct Intercom API
Analyzes conversations closed each day using updated_at as closure proxy.
"""

import os
import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
from dotenv import load_dotenv

# Load environment variables from root .env
load_dotenv(dotenv_path='/Users/virulana/openai-cookbook/.env')

class WeeklyClosureAnalyzer:
    def __init__(self):
        self.access_token = os.getenv('INTERCOM_ACCESS_TOKEN')
        if not self.access_token:
            raise ValueError("INTERCOM_ACCESS_TOKEN not found in environment variables")
        
        self.api_url = "https://api.intercom.io"
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Intercom-Version': '2.13'
        }
    
    def search_conversations(self, from_date, to_date, state=None):
        """Search conversations using Intercom API"""
        from_timestamp = int(datetime.fromisoformat(from_date).timestamp())
        to_timestamp = int(datetime.fromisoformat(to_date + "T23:59:59").timestamp())
        
        search_query = {
            "query": {
                "operator": "AND",
                "value": [
                    {
                        "field": "created_at",
                        "operator": ">=",
                        "value": from_timestamp
                    },
                    {
                        "field": "created_at", 
                        "operator": "<=",
                        "value": to_timestamp
                    }
                ]
            },
            "pagination": {
                "per_page": 150
            }
        }
        
        if state:
            search_query["query"]["value"].append({
                "field": "state",
                "operator": "=", 
                "value": state
            })
        
        all_conversations = []
        starting_after = None
        
        while True:
            if starting_after:
                search_query["pagination"]["starting_after"] = starting_after
            else:
                search_query["pagination"].pop("starting_after", None)
            
            try:
                response = requests.post(
                    f"{self.api_url}/conversations/search",
                    headers=self.headers,
                    json=search_query,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                
                conversations = data.get('conversations', [])
                if not conversations:
                    break
                
                all_conversations.extend(conversations)
                
                # Check for next page
                if data.get('pages', {}).get('next', {}).get('starting_after'):
                    starting_after = data['pages']['next']['starting_after']
                else:
                    break
                    
            except Exception as e:
                print(f"Error in API request: {e}")
                break
        
        return all_conversations
    
    def get_conversation_details(self, conversation_id):
        """Get detailed conversation data including full conversation parts"""
        try:
            response = requests.get(
                f"{self.api_url}/conversations/{conversation_id}",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting conversation {conversation_id}: {e}")
            return None
    
    def analyze_closures_by_updated_date(self, from_date, to_date):
        """Analyze conversations closed each day using updated_at as proxy for closure date"""
        print(f"📊 Analyzing conversation closures from {from_date} to {to_date}")
        print("Using updated_at as proxy for closure date...")
        
        # Get all closed conversations in the period
        closed_conversations = self.search_conversations(from_date, to_date, state="closed")
        print(f"Found {len(closed_conversations)} closed conversations")
        
        # Group by updated_at date (proxy for closure date)
        daily_closures = defaultdict(list)
        
        for conv in closed_conversations:
            if conv.get('updated_at'):
                updated_dt = datetime.fromtimestamp(conv['updated_at'])
                updated_date = updated_dt.strftime('%Y-%m-%d')
                daily_closures[updated_date].append({
                    'id': conv['id'],
                    'created_at': datetime.fromtimestamp(conv['created_at']) if conv.get('created_at') else None,
                    'updated_at': updated_dt,
                    'resolution_time_hours': (updated_dt - datetime.fromtimestamp(conv['created_at'])).total_seconds() / 3600 if conv.get('created_at') else 0
                })
        
        return daily_closures
    
    def print_closure_report(self, daily_closures, from_date, to_date):
        """Print formatted closure report"""
        print(f"\n📅 CONVERSATIONS CLOSED BY DAY ({from_date} to {to_date})")
        print("=" * 70)
        print("(Using updated_at as proxy for closure date)")
        print("-" * 70)
        print(f"{'Date':<12} {'Day':<10} {'Closed':<7} {'Avg Resolution (hrs)':<18}")
        print("-" * 70)
        
        total_closed = 0
        total_resolution_time = 0
        total_with_resolution = 0
        
        # Generate all dates in range
        start_date = datetime.fromisoformat(from_date)
        end_date = datetime.fromisoformat(to_date)
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            day_name = current_date.strftime('%A')
            
            if date_str in daily_closures:
                closures = daily_closures[date_str]
                count = len(closures)
                
                # Calculate average resolution time
                resolution_times = [c['resolution_time_hours'] for c in closures if c['resolution_time_hours'] > 0]
                avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0
                
                total_closed += count
                if resolution_times:
                    total_resolution_time += sum(resolution_times)
                    total_with_resolution += len(resolution_times)
                
                print(f"{date_str:<12} {day_name:<10} {count:<7} {avg_resolution:<18.1f}")
            else:
                print(f"{date_str:<12} {day_name:<10} {0:<7} {0:<18.1f}")
            
            current_date += timedelta(days=1)
        
        print("-" * 70)
        print(f"{'TOTAL':<12} {'':<10} {total_closed:<7} {total_resolution_time/total_with_resolution if total_with_resolution > 0 else 0:<18.1f}")
        
        return {
            'total_closed': total_closed,
            'avg_resolution_hours': total_resolution_time/total_with_resolution if total_with_resolution > 0 else 0,
            'daily_closures': daily_closures
        }

def main():
    analyzer = WeeklyClosureAnalyzer()
    
    # Analyze August 25-29, 2025
    from_date = "2025-08-25"
    to_date = "2025-08-29"
    
    try:
        daily_closures = analyzer.analyze_closures_by_updated_date(from_date, to_date)
        results = analyzer.print_closure_report(daily_closures, from_date, to_date)
        
        print(f"\n🎯 SUMMARY:")
        print(f"• Total conversations closed: {results['total_closed']}")
        print(f"• Average resolution time: {results['avg_resolution_hours']:.1f} hours ({results['avg_resolution_hours']/24:.1f} days)")
        
        # Save detailed results
        output_file = f"weekly_closure_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            # Convert datetime objects to strings for JSON serialization
            json_data = {}
            for date, closures in daily_closures.items():
                json_data[date] = []
                for closure in closures:
                    json_data[date].append({
                        'id': closure['id'],
                        'created_at': closure['created_at'].isoformat() if closure['created_at'] else None,
                        'updated_at': closure['updated_at'].isoformat(),
                        'resolution_time_hours': closure['resolution_time_hours']
                    })
            
            json.dump({
                'analysis_period': {'from': from_date, 'to': to_date},
                'summary': results,
                'daily_closures': json_data
            }, f, indent=2)
        
        print(f"\n💾 Detailed analysis saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    main()


