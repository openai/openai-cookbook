#!/usr/bin/env python3
"""
August 2025 Intercom Conversation Analysis
Adapted from fast-export-intercom.js with retry logic and small batch processing
"""

import os
import requests
import json
import time
import asyncio
import aiohttp
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import pandas as pd
from typing import List, Dict, Optional

# Load environment variables from root
load_dotenv(dotenv_path='/Users/virulana/openai-cookbook/.env')

INTERCOM_ACCESS_TOKEN = os.getenv('INTERCOM_ACCESS_TOKEN')
if not INTERCOM_ACCESS_TOKEN:
    raise ValueError("INTERCOM_ACCESS_TOKEN not found in environment variables.")

class IntercomBatchAnalyzer:
    def __init__(self, access_token: str, max_concurrent: int = 5, timeout: int = 30):
        self.access_token = access_token
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Intercom-Version': '2.13'
        }
        self.base_url = 'https://api.intercom.io'
        
    async def retryable_request(self, session: aiohttp.ClientSession, method: str, url: str, 
                               data: Optional[Dict] = None, max_retries: int = 3, delay: float = 1.0):
        """Retry mechanism adapted from fast-export-intercom.js"""
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                if method.upper() == 'POST':
                    async with session.post(url, json=data, headers=self.headers, timeout=self.timeout) as response:
                        if response.status == 429:  # Rate limited
                            retry_after = int(response.headers.get('retry-after', 5))
                            wait_time = retry_after * 1000 if retry_after > 0 else delay * 1000 * (2 ** attempt)
                            print(f"Rate limited. Retrying after {wait_time/1000:.1f}s (attempt {attempt}/{max_retries})...")
                            await asyncio.sleep(wait_time / 1000)
                            continue
                        response.raise_for_status()
                        return await response.json()
                else:
                    async with session.get(url, headers=self.headers, timeout=self.timeout) as response:
                        response.raise_for_status()
                        return await response.json()
                        
            except Exception as error:
                last_error = error
                if attempt < max_retries:
                    wait_time = delay * (1.5 ** (attempt - 1))
                    print(f"Request failed. Retrying after {wait_time:.1f}s (attempt {attempt}/{max_retries})...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Failed after {max_retries} attempts: {error}")
                    
        raise last_error

    async def fetch_conversations_batch(self, session: aiohttp.ClientSession, 
                                      from_date: str, to_date: str, 
                                      starting_after: Optional[str] = None) -> Dict:
        """Fetch a batch of conversations with pagination"""
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
                "per_page": 50  # Smaller batch size
            }
        }
        
        if starting_after:
            search_query["pagination"]["starting_after"] = starting_after
            
        return await self.retryable_request(
            session, 'POST', f"{self.base_url}/conversations/search", 
            data=search_query
        )

    async def fetch_all_conversations(self, from_date: str, to_date: str) -> List[Dict]:
        """Fetch all conversations with pagination and retry logic"""
        print(f"📅 Fetching conversations from {from_date} to {to_date}...")
        
        all_conversations = []
        starting_after = None
        page_count = 0
        
        async with aiohttp.ClientSession() as session:
            while True:
                page_count += 1
                print(f"📄 Fetching page {page_count}...")
                
                try:
                    response = await self.fetch_conversations_batch(session, from_date, to_date, starting_after)
                    conversations = response.get('conversations', [])
                    
                    if not conversations:
                        print("No more conversations found.")
                        break
                        
                    all_conversations.extend(conversations)
                    print(f"📈 Found {len(conversations)} conversations. Total: {len(all_conversations)}")
                    
                    # Check for next page
                    if response.get('pages', {}).get('next', {}).get('starting_after'):
                        starting_after = response['pages']['next']['starting_after']
                        print(f"Next page will start after: {starting_after[:8]}...")
                        await asyncio.sleep(0.5)  # Rate limiting
                    else:
                        print("No more pages.")
                        break
                        
                except Exception as e:
                    print(f"❌ Error fetching page {page_count}: {e}")
                    await asyncio.sleep(2)  # Wait before retry
                    
        return all_conversations

    def analyze_daily_closures(self, conversations: List[Dict]) -> Dict:
        """Analyze conversations closed by day using updated_at"""
        print(f"\n📊 Analyzing {len(conversations)} conversations for daily closures...")
        
        # Filter for closed conversations
        closed_conversations = [c for c in conversations if c.get('state') == 'closed']
        print(f"🔒 Found {len(closed_conversations)} closed conversations")
        
        # Group by updated_at date (closure date)
        daily_closures = defaultdict(list)
        
        for conv in closed_conversations:
            if conv.get('updated_at'):
                updated_dt = datetime.fromtimestamp(conv['updated_at'])
                updated_date = updated_dt.strftime('%Y-%m-%d')
                
                created_dt = datetime.fromtimestamp(conv['created_at']) if conv.get('created_at') else None
                resolution_hours = (updated_dt - created_dt).total_seconds() / 3600 if created_dt else 0
                
                daily_closures[updated_date].append({
                    'id': conv['id'],
                    'created_at': created_dt,
                    'updated_at': updated_dt,
                    'resolution_hours': resolution_hours
                })
        
        return daily_closures

    def print_daily_results(self, daily_closures: Dict, date_range: List[str]):
        """Print formatted daily closure results"""
        print(f"\n📅 CONVERSATIONS CLOSED BY DAY:")
        print("-" * 60)
        print(f"{'Date':<12} {'Day':<10} {'Closed':<7} {'Avg Resolution (hrs)':<18}")
        print("-" * 60)
        
        total_closed = 0
        
        for date_str in date_range:
            day_name = datetime.fromisoformat(date_str).strftime('%A')
            
            if date_str in daily_closures:
                closures = daily_closures[date_str]
                count = len(closures)
                avg_resolution = sum(c['resolution_hours'] for c in closures) / count if count > 0 else 0
                total_closed += count
                
                print(f"{date_str:<12} {day_name:<10} {count:<7} {avg_resolution:<18.1f}")
                
                # Show sample details for days with closures
                if count > 0:
                    print(f"   📝 Sample closures on {date_str}:")
                    for i, closure in enumerate(closures[:3]):  # Show first 3
                        print(f"      {i+1}. ID: {closure['id']}, Created: {closure['created_at'].strftime('%Y-%m-%d %H:%M')}, Resolution: {closure['resolution_hours']:.1f}h")
                    if len(closures) > 3:
                        print(f"      ... and {len(closures) - 3} more")
            else:
                print(f"{date_str:<12} {day_name:<10} {0:<7} {0:<18.1f}")
        
        print("-" * 60)
        print(f"TOTAL: {total_closed} conversations closed")

async def main():
    """Main analysis function"""
    print("🚀 August 2025 Intercom Conversation Analysis")
    print("=" * 60)
    
    analyzer = IntercomBatchAnalyzer(INTERCOM_ACCESS_TOKEN, max_concurrent=3, timeout=45)
    
    # Define date ranges for August 2025
    august_dates = [
        ("2025-08-25", "2025-08-25"),  # Monday
        ("2025-08-26", "2025-08-26"),  # Tuesday  
        ("2025-08-27", "2025-08-27"),  # Wednesday
        ("2025-08-28", "2025-08-28"),  # Thursday
        ("2025-08-29", "2025-08-29"),  # Friday
    ]
    
    all_conversations = []
    
    # Fetch conversations day by day to avoid timeouts
    for from_date, to_date in august_dates:
        print(f"\n🔍 Processing {from_date} ({datetime.fromisoformat(from_date).strftime('%A')})...")
        try:
            day_conversations = await analyzer.fetch_all_conversations(from_date, to_date)
            all_conversations.extend(day_conversations)
            print(f"✅ {from_date}: {len(day_conversations)} conversations found")
            
            # Small delay between days
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"❌ Error processing {from_date}: {e}")
            continue
    
    if all_conversations:
        print(f"\n📊 Total conversations found: {len(all_conversations)}")
        
        # Analyze daily closures
        daily_closures = analyzer.analyze_daily_closures(all_conversations)
        
        # Print results
        date_range = ["2025-08-25", "2025-08-26", "2025-08-27", "2025-08-28", "2025-08-29"]
        analyzer.print_daily_results(daily_closures, date_range)
        
        # Save results to file
        output_file = f"/Users/virulana/openai-cookbook/tools/outputs/august_2025_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                'total_conversations': len(all_conversations),
                'daily_closures': {k: len(v) for k, v in daily_closures.items()},
                'detailed_closures': {k: [{'id': c['id'], 'resolution_hours': c['resolution_hours']} for c in v] for k, v in daily_closures.items()}
            }, f, indent=2)
        print(f"\n💾 Results saved to: {output_file}")
        
    else:
        print("❌ No conversations found or all requests failed")

if __name__ == "__main__":
    asyncio.run(main())


