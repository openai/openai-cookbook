#!/usr/bin/env python3
"""
Working SLA Compliance Analysis for Intercom Conversations
Based on correct conversation structure discovered
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from typing import Dict, List, Optional

# Load environment variables from root
load_dotenv(dotenv_path='/Users/virulana/openai-cookbook/.env')

INTERCOM_ACCESS_TOKEN = os.getenv('INTERCOM_ACCESS_TOKEN')
if not INTERCOM_ACCESS_TOKEN:
    raise ValueError("INTERCOM_ACCESS_TOKEN not found in environment variables.")

# SLA Standards from the provided table
SLA_STANDARDS = {
    # General Work Teams
    "Contabilidad": 48,  # 48 hours
    "Conecta tu Banco": 48,  # 48 hours
    "Inventario": 3,  # 3 hours
    "Onboarding": 1,  # 60 minutes = 1 hour
    "Importaciones": 1,  # 60 minutes = 1 hour
    "Plan de Cuentas": None,  # No SLA specified
    
    # Phone Calls (Llamados telefonicas)
    "Soporte/ Clientes": 0.67,  # 40 minutes = 0.67 hours
    "Proveedores": 0.67,  # 40 minutes = 0.67 hours
    "Caida ARCA/ Clientes": 0.67,  # 40 minutes = 0.67 hours
    "Sin asignar": 0.67,  # 40 minutes = 0.67 hours
    "Tesoreria": 0.67,  # 40 minutes = 0.67 hours
    "Cobranzas/Retención": 0.33,  # 20 minutes = 0.33 hours
    
    # Additional labels found in conversations
    "MC-Límite de Comprobantes": 48,  # Assuming 48 hours for document limit issues
    "Límite de Comprobantes": 48,  # Document limit issues
}

class WorkingSLAAnalyzer:
    def __init__(self, access_token: str, timeout: int = 45):
        self.access_token = access_token
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
        """Retry mechanism for failed requests"""
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

    def extract_conversation_labels(self, conversation: Dict) -> List[str]:
        """Extract labels/tags from conversation using correct structure"""
        labels = []
        
        try:
            # Check for tags in conversation (correct structure)
            if conversation.get('tags', {}).get('tags'):
                for tag in conversation['tags']['tags']:
                    if isinstance(tag, dict) and tag.get('name'):
                        labels.append(tag['name'])
            
            # Check for conversation parts that might have labels
            if conversation.get('conversation_parts', {}).get('conversation_parts'):
                for part in conversation['conversation_parts']['conversation_parts']:
                    if isinstance(part, dict) and part.get('tags', {}).get('tags'):
                        for tag in part['tags']['tags']:
                            if isinstance(tag, dict) and tag.get('name'):
                                labels.append(tag['name'])
                
        except Exception as e:
            print(f"❌ Error extracting labels: {e}")
            
        return list(set(labels))  # Remove duplicates

    def calculate_sla_compliance(self, resolution_hours: float, labels: List[str]) -> Dict:
        """Calculate SLA compliance for given labels and resolution time"""
        results = {}
        
        for label in labels:
            if label in SLA_STANDARDS:
                sla_hours = SLA_STANDARDS[label]
                if sla_hours is not None:
                    is_compliant = resolution_hours <= sla_hours
                    results[label] = {
                        'sla_hours': sla_hours,
                        'resolution_hours': resolution_hours,
                        'is_compliant': is_compliant,
                        'overdue_hours': max(0, resolution_hours - sla_hours),
                        'compliance_percentage': min(100, (sla_hours / resolution_hours) * 100) if resolution_hours > 0 else 100
                    }
        
        return results

    async def analyze_friday_conversations(self, target_date: str = "2025-08-29"):
        """Analyze Friday conversations for SLA compliance"""
        print(f"🔍 Analyzing SLA compliance for {target_date} (Friday)...")
        
        # First, get all conversations for Friday
        from_timestamp = int(datetime.fromisoformat(target_date).timestamp())
        to_timestamp = int(datetime.fromisoformat(target_date + "T23:59:59").timestamp())
        
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
                "per_page": 50
            }
        }
        
        all_conversations = []
        starting_after = None
        
        async with aiohttp.ClientSession() as session:
            # Get conversation IDs first
            while True:
                if starting_after:
                    search_query["pagination"]["starting_after"] = starting_after
                else:
                    search_query["pagination"].pop("starting_after", None)
                
                try:
                    response = await self.retryable_request(
                        session, 'POST', f"{self.base_url}/conversations/search", 
                        data=search_query
                    )
                    
                    conversations = response.get('conversations', [])
                    if not conversations:
                        break
                    
                    all_conversations.extend(conversations)
                    print(f"📈 Found {len(conversations)} conversations. Total: {len(all_conversations)}")
                    
                    if response.get('pages', {}).get('next', {}).get('starting_after'):
                        starting_after = response['pages']['next']['starting_after']
                        await asyncio.sleep(0.5)
                    else:
                        break
                        
                except Exception as e:
                    print(f"❌ Error fetching conversations: {e}")
                    break
            
            # Now get detailed information for closed conversations (limit to first 20 for analysis)
            closed_conversations = [c for c in all_conversations if c.get('state') == 'closed'][:20]
            print(f"\n🔒 Analyzing {len(closed_conversations)} closed conversations for SLA compliance...")
            
            sla_analysis = []
            
            for i, conv in enumerate(closed_conversations):
                print(f"📊 Processing conversation {i+1}/{len(closed_conversations)}...")
                
                # Get detailed conversation info
                try:
                    details = await self.retryable_request(
                        session, 'GET', f"{self.base_url}/conversations/{conv['id']}"
                    )
                except Exception as e:
                    print(f"❌ Error getting details for {conv['id']}: {e}")
                    continue
                
                # Calculate resolution time
                created_at = datetime.fromtimestamp(conv['created_at'])
                updated_at = datetime.fromtimestamp(conv['updated_at'])
                resolution_hours = (updated_at - created_at).total_seconds() / 3600
                
                # Extract labels
                labels = self.extract_conversation_labels(details)
                
                # Calculate SLA compliance
                sla_results = self.calculate_sla_compliance(resolution_hours, labels)
                
                sla_analysis.append({
                    'conversation_id': conv['id'],
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'resolution_hours': resolution_hours,
                    'labels': labels,
                    'sla_compliance': sla_results,
                    'admin_assignee': details.get('admin_assignee_id'),
                    'team_assignee': details.get('team_assignee_id'),
                    'source': details.get('source', {}).get('author', {}).get('type', 'unknown')
                })
                
                await asyncio.sleep(0.2)  # Rate limiting
            
            return sla_analysis

    def print_sla_results(self, sla_analysis: List[Dict]):
        """Print detailed SLA compliance results"""
        print(f"\n📊 SLA COMPLIANCE ANALYSIS RESULTS")
        print("=" * 80)
        
        # Summary by label
        label_summary = defaultdict(lambda: {'total': 0, 'compliant': 0, 'total_resolution': 0})
        
        for analysis in sla_analysis:
            for label, compliance in analysis['sla_compliance'].items():
                label_summary[label]['total'] += 1
                label_summary[label]['total_resolution'] += analysis['resolution_hours']
                if compliance['is_compliant']:
                    label_summary[label]['compliant'] += 1
        
        print(f"\n📈 SLA COMPLIANCE BY LABEL:")
        print("-" * 60)
        print(f"{'Label':<30} {'Total':<8} {'Compliant':<10} {'Compliance %':<12} {'Avg Resolution':<15}")
        print("-" * 60)
        
        for label, stats in label_summary.items():
            compliance_pct = (stats['compliant'] / stats['total']) * 100 if stats['total'] > 0 else 0
            avg_resolution = stats['total_resolution'] / stats['total'] if stats['total'] > 0 else 0
            print(f"{label:<30} {stats['total']:<8} {stats['compliant']:<10} {compliance_pct:<12.1f}% {avg_resolution:<15.1f}h")
        
        # Show detailed examples
        print(f"\n📝 DETAILED EXAMPLES:")
        print("-" * 80)
        
        for i, analysis in enumerate(sla_analysis[:10]):  # Show first 10 examples
            print(f"\n🔍 Example {i+1}: Conversation {analysis['conversation_id']}")
            print(f"   📅 Created: {analysis['created_at'].strftime('%Y-%m-%d %H:%M')}")
            print(f"   ✅ Closed: {analysis['updated_at'].strftime('%Y-%m-%d %H:%M')}")
            print(f"   ⏱️ Resolution: {analysis['resolution_hours']:.1f} hours")
            print(f"   🏷️ Labels: {', '.join(analysis['labels']) if analysis['labels'] else 'None'}")
            
            if analysis['sla_compliance']:
                for label, compliance in analysis['sla_compliance'].items():
                    status = "✅ COMPLIANT" if compliance['is_compliant'] else "❌ OVERDUE"
                    print(f"   📊 {label}: {status}")
                    print(f"      - SLA: {compliance['sla_hours']}h | Actual: {compliance['resolution_hours']:.1f}h")
                    if not compliance['is_compliant']:
                        print(f"      - Overdue by: {compliance['overdue_hours']:.1f}h")
            else:
                print(f"   ⚠️ No matching SLA standards found")
        
        # Overall statistics
        total_conversations = len(sla_analysis)
        total_with_labels = len([a for a in sla_analysis if a['labels']])
        total_with_sla = len([a for a in sla_analysis if a['sla_compliance']])
        
        print(f"\n📊 OVERALL STATISTICS:")
        print(f"   • Total conversations analyzed: {total_conversations}")
        print(f"   • Conversations with labels: {total_with_labels} ({total_with_labels/total_conversations*100:.1f}%)")
        print(f"   • Conversations with SLA standards: {total_with_sla} ({total_with_sla/total_conversations*100:.1f}%)")

async def main():
    """Main analysis function"""
    print("🚀 Working SLA Compliance Analysis for Friday Conversations")
    print("=" * 60)
    
    analyzer = WorkingSLAAnalyzer(INTERCOM_ACCESS_TOKEN)
    
    # Analyze Friday (2025-08-29) conversations
    sla_analysis = await analyzer.analyze_friday_conversations("2025-08-29")
    
    if sla_analysis:
        analyzer.print_sla_results(sla_analysis)
        
        # Save results
        output_file = f"/Users/virulana/openai-cookbook/tools/outputs/working_sla_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(sla_analysis, f, indent=2, default=str)
        print(f"\n💾 Detailed results saved to: {output_file}")
    else:
        print("❌ No conversations found or analysis failed")

if __name__ == "__main__":
    asyncio.run(main())


