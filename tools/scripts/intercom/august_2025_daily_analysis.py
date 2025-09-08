#!/usr/bin/env python3
"""
August 2025 Daily Conversation Analysis
Analyzes conversations created each day in August 2025 and calculates open duration.
"""

import json
import subprocess
import datetime
from typing import Dict, List, Tuple
import pandas as pd

class August2025ConversationAnalyzer:
    def __init__(self):
        self.mcp_server_path = "/Users/virulana/openai-cookbook/tools/scripts/intercom/mcp-intercom-server.js"
        self.today = datetime.date.today()
        
    def call_mcp_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool and return parsed response"""
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        proc = subprocess.run(
            ["node", "mcp-intercom-server.js"],
            input=json.dumps(req).encode(),
            capture_output=True,
            cwd="/Users/virulana/openai-cookbook/tools/scripts/intercom"
        )
        
        if proc.returncode != 0:
            raise Exception(f"MCP call failed: {proc.stderr.decode()}")
            
        raw = proc.stdout.decode()
        obj = json.loads(raw)
        text = obj.get('result', {}).get('content', [{}])[0].get('text', '{}')
        return json.loads(text)
    
    def get_conversations_for_date(self, date: datetime.date) -> List[dict]:
        """Get all conversations created on a specific date"""
        date_str = date.isoformat()
        
        result = self.call_mcp_tool(
            "export_intercom_conversations",
            {
                "from_date": date_str,
                "to_date": date_str,
                "output_format": "json",
                "include_message_content": False
            }
        )
        
        return result.get('conversations_summary', [])
    
    def calculate_open_duration(self, created_at_timestamp: int) -> Tuple[int, str]:
        """Calculate how long a conversation has been open in hours and human readable format"""
        if not created_at_timestamp:
            return 0, "0 hours"
            
        created_dt = datetime.datetime.fromtimestamp(created_at_timestamp)
        now = datetime.datetime.now()
        duration = now - created_dt
        
        hours = int(duration.total_seconds() / 3600)
        days = hours // 24
        remaining_hours = hours % 24
        
        if days > 0:
            return hours, f"{days} days, {remaining_hours} hours"
        else:
            return hours, f"{hours} hours"
    
    def analyze_august_2025(self) -> Dict:
        """Analyze all days in August 2025"""
        results = {}
        august_start = datetime.date(2025, 8, 1)
        august_end = datetime.date(2025, 8, 31)
        
        # Limit to current date if we're still in August
        if self.today.month == 8 and self.today.year == 2025:
            august_end = min(august_end, self.today)
        
        print(f"📊 Analyzing August 2025 conversations from {august_start} to {august_end}")
        print("=" * 60)
        
        daily_data = []
        
        current_date = august_start
        while current_date <= august_end:
            print(f"📅 Processing {current_date.strftime('%Y-%m-%d')}...")
            
            try:
                conversations = self.get_conversations_for_date(current_date)
                
                # Filter for conversations that are still open
                open_conversations = [c for c in conversations if c.get('state') == 'open']
                
                # Calculate durations for open conversations
                open_durations = []
                for conv in open_conversations:
                    created_at = conv.get('created_at')
                    if created_at:
                        # Convert ISO string to timestamp
                        created_dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        created_timestamp = created_dt.timestamp()
                        hours, human_readable = self.calculate_open_duration(created_timestamp)
                        open_durations.append(hours)
                
                avg_open_hours = sum(open_durations) / len(open_durations) if open_durations else 0
                max_open_hours = max(open_durations) if open_durations else 0
                
                day_data = {
                    'date': current_date.isoformat(),
                    'day_name': current_date.strftime('%A'),
                    'total_created': len(conversations),
                    'still_open': len(open_conversations),
                    'closed_same_day': len(conversations) - len(open_conversations),
                    'avg_open_hours': round(avg_open_hours, 1),
                    'max_open_hours': max_open_hours,
                    'avg_open_days': round(avg_open_hours / 24, 1) if avg_open_hours > 0 else 0
                }
                
                daily_data.append(day_data)
                results[current_date.isoformat()] = day_data
                
                print(f"   ✅ Created: {day_data['total_created']}, Still Open: {day_data['still_open']}, Avg Open: {day_data['avg_open_days']} days")
                
            except Exception as e:
                print(f"   ❌ Error processing {current_date}: {e}")
                day_data = {
                    'date': current_date.isoformat(),
                    'day_name': current_date.strftime('%A'),
                    'total_created': 0,
                    'still_open': 0,
                    'closed_same_day': 0,
                    'avg_open_hours': 0,
                    'max_open_hours': 0,
                    'avg_open_days': 0,
                    'error': str(e)
                }
                daily_data.append(day_data)
                results[current_date.isoformat()] = day_data
            
            current_date += datetime.timedelta(days=1)
        
        # Generate summary
        df = pd.DataFrame(daily_data)
        
        summary = {
            'analysis_date': self.today.isoformat(),
            'period': f"{august_start} to {august_end}",
            'total_days_analyzed': len(daily_data),
            'total_conversations_created': df['total_created'].sum(),
            'total_still_open': df['still_open'].sum(),
            'avg_conversations_per_day': round(df['total_created'].mean(), 1),
            'avg_open_duration_days': round(df['avg_open_days'].mean(), 1),
            'daily_breakdown': daily_data
        }
        
        return summary
    
    def print_summary_report(self, analysis: Dict):
        """Print a formatted summary report"""
        print("\n" + "=" * 80)
        print("📊 AUGUST 2025 INTERCOM CONVERSATION ANALYSIS")
        print("=" * 80)
        
        print(f"📅 Analysis Period: {analysis['period']}")
        print(f"📈 Total Conversations Created: {analysis['total_conversations_created']}")
        print(f"🔓 Still Open: {analysis['total_still_open']}")
        print(f"📊 Average per Day: {analysis['avg_conversations_per_day']}")
        print(f"⏱️  Average Open Duration: {analysis['avg_open_duration_days']} days")
        
        print("\n📅 DAILY BREAKDOWN:")
        print("-" * 80)
        print(f"{'Date':<12} {'Day':<10} {'Created':<8} {'Open':<6} {'Closed':<8} {'Avg Open Days':<12}")
        print("-" * 80)
        
        for day in analysis['daily_breakdown']:
            if 'error' not in day:
                print(f"{day['date']:<12} {day['day_name']:<10} {day['total_created']:<8} "
                      f"{day['still_open']:<6} {day['closed_same_day']:<8} {day['avg_open_days']:<12}")
            else:
                print(f"{day['date']:<12} {day['day_name']:<10} {'ERROR':<8} {'N/A':<6} {'N/A':<8} {'N/A':<12}")
        
        print("-" * 80)
        
        # Insights
        df = pd.DataFrame([d for d in analysis['daily_breakdown'] if 'error' not in d])
        if not df.empty:
            busiest_day = df.loc[df['total_created'].idxmax()]
            longest_open = df.loc[df['avg_open_days'].idxmax()] if df['avg_open_days'].max() > 0 else None
            
            print("\n🎯 KEY INSIGHTS:")
            print(f"• Busiest day: {busiest_day['date']} ({busiest_day['day_name']}) with {busiest_day['total_created']} conversations")
            if longest_open is not None:
                print(f"• Longest average open time: {longest_open['date']} ({longest_open['avg_open_days']} days)")
            print(f"• Weekend vs Weekday pattern: {'Analyzing...' if len(df) > 7 else 'Insufficient data'}")

def main():
    analyzer = August2025ConversationAnalyzer()
    
    print("🚀 Starting August 2025 Intercom Analysis...")
    analysis = analyzer.analyze_august_2025()
    
    # Print results
    analyzer.print_summary_report(analysis)
    
    # Save to JSON for further analysis
    output_file = f"august_2025_conversation_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    print(f"\n💾 Detailed analysis saved to: {output_file}")
    
    return analysis

if __name__ == "__main__":
    main()



