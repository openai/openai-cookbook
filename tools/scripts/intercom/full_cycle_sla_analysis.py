#!/usr/bin/env python3
"""
Full Cycle SLA Compliance Analysis for Intercom Conversations
Analyzes complete cycle time from ticket creation to closure on Friday
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

# SLA Standards updated based on actual labels found
SLA_STANDARDS = {
    # Original standards from the table
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
    
    # Actual labels found in conversations
    "MC-Límite de Comprobantes": 48,  # Document limit issues
    "Soporte Telefónico- Llamado Cumplido": 0.67,  # Phone call completed
    "Mod Cont-Eliminar cuenta contable": 48,  # Accounting modification
    "Mod Cont-Nuevo plan de cuentas": 48,  # New chart of accounts
    "Mod Cli-Aceptación Factura Electronica": 24,  # Electronic invoice acceptance
    "CS Cambio de plan automático": 24,  # Automatic plan change
    "Caída ARCA": 0.67,  # ARCA fall (phone call)
    "Mod Cli-Errores en Factura Electrónica": 24,  # Electronic invoice errors
    "Mod Cli - Facturas no aparecen en Colppy": 24,  # Invoices not appearing
    "Consultas-No responden": 24,  # Queries not responding
    "CS - eSueldos -Implementador Sueldos": 48,  # Salary implementation
}

class FullCycleSLAAnalyzer:
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
        """Extract labels/tags from conversation with better error handling"""
        labels = []
        
        try:
            # Check for tags in conversation
            if conversation.get('tags') and isinstance(conversation['tags'], dict):
                tags_data = conversation['tags'].get('tags', [])
                if isinstance(tags_data, list):
                    for tag in tags_data:
                        if isinstance(tag, dict) and tag.get('name'):
                            labels.append(tag['name'])
            
            # Check for conversation parts that might have labels
            if conversation.get('conversation_parts') and isinstance(conversation['conversation_parts'], dict):
                parts_data = conversation['conversation_parts'].get('conversation_parts', [])
                if isinstance(parts_data, list):
                    for part in parts_data:
                        if isinstance(part, dict) and part.get('tags'):
                            part_tags = part['tags'].get('tags', [])
                            if isinstance(part_tags, list):
                                for tag in part_tags:
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

    async def analyze_conversations_closed_on_friday(self, target_date: str = "2025-08-29"):
        """Analyze conversations that were CLOSED on Friday (regardless of when created)"""
        print(f"🔍 Analyzing FULL CYCLE TIME for conversations CLOSED on {target_date} (Friday)...")
        print("📊 This includes tickets created on any day but closed on Friday")
        
        # Search for conversations that were UPDATED (closed) on Friday
        from_timestamp = int(datetime.fromisoformat(target_date).timestamp())
        to_timestamp = int(datetime.fromisoformat(target_date + "T23:59:59").timestamp())
        
        search_query = {
            "query": {
                "operator": "AND",
                "value": [
                    {
                        "field": "updated_at",
                        "operator": ">=",
                        "value": from_timestamp
                    },
                    {
                        "field": "updated_at",
                        "operator": "<=",
                        "value": to_timestamp
                    },
                    {
                        "field": "state",
                        "operator": "=",
                        "value": "closed"
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
            # Get conversation IDs that were closed on Friday
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
                    print(f"📈 Found {len(conversations)} conversations closed on Friday. Total: {len(all_conversations)}")
                    
                    if response.get('pages', {}).get('next', {}).get('starting_after'):
                        starting_after = response['pages']['next']['starting_after']
                        await asyncio.sleep(0.5)
                    else:
                        break
                        
                except Exception as e:
                    print(f"❌ Error fetching conversations: {e}")
                    break
            
            # Now get detailed information for analysis (limit to first 40 for analysis)
            conversations_to_analyze = all_conversations[:40]
            print(f"\n🔒 Analyzing {len(conversations_to_analyze)} conversations for FULL CYCLE SLA compliance...")
            
            sla_analysis = []
            
            for i, conv in enumerate(conversations_to_analyze):
                print(f"📊 Processing conversation {i+1}/{len(conversations_to_analyze)}...")
                
                # Get detailed conversation info
                try:
                    details = await self.retryable_request(
                        session, 'GET', f"{self.base_url}/conversations/{conv['id']}"
                    )
                except Exception as e:
                    print(f"❌ Error getting details for {conv['id']}: {e}")
                    continue
                
                # Calculate FULL CYCLE TIME (from creation to closure)
                created_at = datetime.fromtimestamp(conv['created_at'])
                closed_at = datetime.fromtimestamp(conv['updated_at'])  # This is when it was closed
                full_cycle_hours = (closed_at - created_at).total_seconds() / 3600
                
                # Extract labels
                labels = self.extract_conversation_labels(details)
                
                # Calculate SLA compliance using FULL CYCLE TIME
                sla_results = self.calculate_sla_compliance(full_cycle_hours, labels)
                
                sla_analysis.append({
                    'conversation_id': conv['id'],
                    'created_at': created_at,
                    'closed_at': closed_at,
                    'full_cycle_hours': full_cycle_hours,
                    'created_on_friday': created_at.strftime('%Y-%m-%d') == target_date,
                    'days_open': (closed_at - created_at).days,
                    'labels': labels,
                    'sla_compliance': sla_results,
                    'admin_assignee': details.get('admin_assignee_id'),
                    'team_assignee': details.get('team_assignee_id'),
                    'source': details.get('source', {}).get('author', {}).get('type', 'unknown')
                })
                
                await asyncio.sleep(0.2)  # Rate limiting
            
            return sla_analysis

    def print_full_cycle_results(self, sla_analysis: List[Dict]):
        """Print detailed full cycle SLA compliance results"""
        print(f"\n📊 FULL CYCLE SLA COMPLIANCE ANALYSIS RESULTS")
        print("=" * 80)
        
        # Summary by label
        label_summary = defaultdict(lambda: {'total': 0, 'compliant': 0, 'total_cycle_time': 0})
        
        for analysis in sla_analysis:
            for label, compliance in analysis['sla_compliance'].items():
                label_summary[label]['total'] += 1
                label_summary[label]['total_cycle_time'] += analysis['full_cycle_hours']
                if compliance['is_compliant']:
                    label_summary[label]['compliant'] += 1
        
        print(f"\n📈 FULL CYCLE SLA COMPLIANCE BY LABEL:")
        print("-" * 75)
        print(f"{'Label':<35} {'Total':<8} {'Compliant':<10} {'Compliance %':<12} {'Avg Cycle Time':<15}")
        print("-" * 75)
        
        for label, stats in label_summary.items():
            compliance_pct = (stats['compliant'] / stats['total']) * 100 if stats['total'] > 0 else 0
            avg_cycle_time = stats['total_cycle_time'] / stats['total'] if stats['total'] > 0 else 0
            print(f"{label:<35} {stats['total']:<8} {stats['compliant']:<10} {compliance_pct:<12.1f}% {avg_cycle_time:<15.1f}h")
        
        # Show detailed examples with FULL CYCLE calculations
        print(f"\n📝 DETAILED EXAMPLES WITH FULL CYCLE TIME:")
        print("-" * 80)
        
        for i, analysis in enumerate(sla_analysis[:20]):  # Show first 20 examples
            print(f"\n🔍 Example {i+1}: Conversation {analysis['conversation_id']}")
            print(f"   📅 Created: {analysis['created_at'].strftime('%Y-%m-%d %H:%M')}")
            print(f"   ✅ Closed: {analysis['closed_at'].strftime('%Y-%m-%d %H:%M')}")
            print(f"   ⏱️ FULL CYCLE TIME: {analysis['full_cycle_hours']:.1f} hours ({analysis['days_open']} days)")
            print(f"   📊 Created on Friday: {'Yes' if analysis['created_on_friday'] else 'No'}")
            print(f"   🏷️ Labels: {', '.join(analysis['labels']) if analysis['labels'] else 'None'}")
            
            if analysis['sla_compliance']:
                for label, compliance in analysis['sla_compliance'].items():
                    status = "✅ COMPLIANT" if compliance['is_compliant'] else "❌ OVERDUE"
                    print(f"   📊 {label}: {status}")
                    print(f"      - SLA: {compliance['sla_hours']}h | Full Cycle: {compliance['resolution_hours']:.1f}h")
                    if not compliance['is_compliant']:
                        print(f"      - Overdue by: {compliance['overdue_hours']:.1f}h")
                    else:
                        print(f"      - Under SLA by: {compliance['sla_hours'] - compliance['resolution_hours']:.1f}h")
            else:
                print(f"   ⚠️ No matching SLA standards found")
        
        # Overall statistics
        total_conversations = len(sla_analysis)
        total_with_labels = len([a for a in sla_analysis if a['labels']])
        total_with_sla = len([a for a in sla_analysis if a['sla_compliance']])
        created_on_friday = len([a for a in sla_analysis if a['created_on_friday']])
        
        # Calculate overall compliance
        total_compliant = 0
        total_with_sla_standards = 0
        for analysis in sla_analysis:
            for label, compliance in analysis['sla_compliance'].items():
                total_with_sla_standards += 1
                if compliance['is_compliant']:
                    total_compliant += 1
        
        overall_compliance = (total_compliant / total_with_sla_standards * 100) if total_with_sla_standards > 0 else 0
        
        # Calculate average cycle times
        avg_cycle_time = sum(a['full_cycle_hours'] for a in sla_analysis) / total_conversations if total_conversations > 0 else 0
        avg_days_open = sum(a['days_open'] for a in sla_analysis) / total_conversations if total_conversations > 0 else 0
        
        print(f"\n📊 OVERALL STATISTICS:")
        print(f"   • Total conversations analyzed: {total_conversations}")
        print(f"   • Created on Friday: {created_on_friday} ({created_on_friday/total_conversations*100:.1f}%)")
        print(f"   • Created before Friday: {total_conversations - created_on_friday} ({(total_conversations - created_on_friday)/total_conversations*100:.1f}%)")
        print(f"   • Average cycle time: {avg_cycle_time:.1f} hours ({avg_days_open:.1f} days)")
        print(f"   • Conversations with labels: {total_with_labels} ({total_with_labels/total_conversations*100:.1f}%)")
        print(f"   • Conversations with SLA standards: {total_with_sla} ({total_with_sla/total_conversations*100:.1f}%)")
        print(f"   • Overall SLA compliance: {overall_compliance:.1f}% ({total_compliant}/{total_with_sla_standards})")

async def main():
    """Main analysis function"""
    print("🚀 Full Cycle SLA Compliance Analysis for Friday Conversations")
    print("=" * 60)
    
    analyzer = FullCycleSLAAnalyzer(INTERCOM_ACCESS_TOKEN)
    
    # Analyze conversations CLOSED on Friday (2025-08-29) - full cycle time
    sla_analysis = await analyzer.analyze_conversations_closed_on_friday("2025-08-29")
    
    if sla_analysis:
        analyzer.print_full_cycle_results(sla_analysis)
        
        # Save results
        output_file = f"/Users/virulana/openai-cookbook/tools/outputs/full_cycle_sla_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(sla_analysis, f, indent=2, default=str)
        print(f"\n💾 Detailed results saved to: {output_file}")
    else:
        print("❌ No conversations found or analysis failed")

if __name__ == "__main__":
    asyncio.run(main())
