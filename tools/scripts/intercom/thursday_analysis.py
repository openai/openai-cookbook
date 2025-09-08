#!/usr/bin/env python3
"""
Thursday Analysis - ALL Tickets Closed on Thursday (August 28th, 2025)
Analyzes the complete dataset using official SLA standards
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

# OFFICIAL SLA STANDARDS from the table
OFFICIAL_SLA_STANDARDS = {
    "Contabilidad": 48,  # 48 hours
    "Conecta tu Banco": 48,  # 48 hours
    "Inventario": 3,  # 3 hours
    "Onboarding": 1,  # 60 minutes = 1 hour
    "Importaciones": 1,  # 60 minutes = 1 hour
    "Plan de Cuentas": None,  # No SLA specified
    "Soporte/ Clientes": 0.67,  # 40 minutes = 0.67 hours
    "Proveedores": 0.67,  # 40 minutes = 0.67 hours
    "Caida ARCA/ Clientes": 0.67,  # 40 minutes = 0.67 hours
    "Sin asignar": 0.67,  # 40 minutes = 0.67 hours
    "Tesoreria": 0.67,  # 40 minutes = 0.67 hours
    "Cobranzas/Retención": 0.33,  # 20 minutes = 0.33 hours
}

# MAPPING from conversation labels to official categories
LABEL_MAPPING = {
    # Direct matches
    "Contabilidad": "Contabilidad",
    "Conecta tu Banco": "Conecta tu Banco",
    "Inventario": "Inventario",
    "Onboarding": "Onboarding",
    "Importaciones": "Importaciones",
    "Plan de Cuentas": "Plan de Cuentas",
    "Soporte/ Clientes": "Soporte/ Clientes",
    "Proveedores": "Proveedores",
    "Caida ARCA/ Clientes": "Caida ARCA/ Clientes",
    "Sin asignar": "Sin asignar",
    "Tesoreria": "Tesoreria",
    "Cobranzas/Retención": "Cobranzas/Retención",
    
    # Mapped variations
    "Caída ARCA": "Caida ARCA/ Clientes",
    "Soporte Telefónico- Llamado Cumplido": "Soporte/ Clientes",
    "Soporte Telefónico- Llamado No Cumplido": "Soporte/ Clientes",
    "Mod Cont-Eliminar cuenta contable": "Contabilidad",
    "Mod Cont-Nuevo plan de cuentas": "Contabilidad",
    "Mod Cli-Aceptación Factura Electronica": "Contabilidad",
    "Mod Cli-Errores en Factura Electrónica": "Contabilidad",
    "Mod Cli - Facturas no aparecen en Colppy": "Contabilidad",
    "Consultas-No responden": "Soporte/ Clientes",
    "CS Cambio de plan automático": "Soporte/ Clientes",
    "CS - eSueldos -Implementador Sueldos": "Contabilidad",
    "MC-Límite de Comprobantes": "Contabilidad",
}

class ThursdayAnalyzer:
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
            # Silently handle errors to avoid spam
            pass
            
        return list(set(labels))  # Remove duplicates

    def map_labels_to_official_categories(self, labels: List[str]) -> List[str]:
        """Map conversation labels to official SLA categories"""
        mapped_labels = []
        for label in labels:
            if label in LABEL_MAPPING:
                official_label = LABEL_MAPPING[label]
                if official_label in OFFICIAL_SLA_STANDARDS:
                    mapped_labels.append(official_label)
        return list(set(mapped_labels))  # Remove duplicates

    def calculate_sla_compliance(self, resolution_hours: float, official_labels: List[str]) -> Dict:
        """Calculate SLA compliance for given official labels and resolution time"""
        results = {}
        
        for official_label in official_labels:
            sla_hours = OFFICIAL_SLA_STANDARDS[official_label]
            if sla_hours is not None:
                is_compliant = resolution_hours <= sla_hours
                results[official_label] = {
                    'sla_hours': sla_hours,
                    'resolution_hours': resolution_hours,
                    'is_compliant': is_compliant,
                    'overdue_hours': max(0, resolution_hours - sla_hours),
                    'compliance_percentage': min(100, (sla_hours / resolution_hours) * 100) if resolution_hours > 0 else 100
                }
        
        return results

    async def get_all_conversations_closed_on_thursday(self, target_date: str = "2025-08-28"):
        """Get ALL conversations that were CLOSED on Thursday"""
        print(f"🔍 Fetching ALL conversations CLOSED on {target_date} (Thursday)...")
        
        # Search for conversations that were UPDATED (closed) on Thursday
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
            # Get ALL conversation IDs that were closed on Thursday
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
            
            print(f"\n✅ Total conversations closed on Thursday: {len(all_conversations)}")
            return all_conversations

    async def analyze_complete_dataset(self, conversations: List[Dict], target_date: str = "2025-08-28"):
        """Analyze the complete dataset of conversations"""
        print(f"\n🔒 Analyzing ALL {len(conversations)} conversations for complete SLA compliance...")
        
        sla_analysis = []
        created_on_thursday = 0
        created_before_thursday = 0
        
        async with aiohttp.ClientSession() as session:
            for i, conv in enumerate(conversations):
                if i % 50 == 0:
                    print(f"📊 Processing conversation {i+1}/{len(conversations)}...")
                
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
                closed_at = datetime.fromtimestamp(conv['updated_at'])
                full_cycle_hours = (closed_at - created_at).total_seconds() / 3600
                
                # Track creation dates
                if created_at.strftime('%Y-%m-%d') == target_date:
                    created_on_thursday += 1
                else:
                    created_before_thursday += 1
                
                # Extract and map labels
                raw_labels = self.extract_conversation_labels(details)
                official_labels = self.map_labels_to_official_categories(raw_labels)
                
                # Calculate SLA compliance using FULL CYCLE TIME
                sla_results = self.calculate_sla_compliance(full_cycle_hours, official_labels)
                
                sla_analysis.append({
                    'conversation_id': conv['id'],
                    'created_at': created_at,
                    'closed_at': closed_at,
                    'full_cycle_hours': full_cycle_hours,
                    'created_on_thursday': created_at.strftime('%Y-%m-%d') == target_date,
                    'days_open': (closed_at - created_at).days,
                    'raw_labels': raw_labels,
                    'official_labels': official_labels,
                    'sla_compliance': sla_results,
                    'admin_assignee': details.get('admin_assignee_id'),
                    'team_assignee': details.get('team_assignee_id'),
                    'source': details.get('source', {}).get('author', {}).get('type', 'unknown')
                })
                
                await asyncio.sleep(0.1)  # Rate limiting
            
            return sla_analysis, created_on_thursday, created_before_thursday

    def print_complete_results(self, sla_analysis: List[Dict], created_on_thursday: int, created_before_thursday: int):
        """Print complete analysis results"""
        print(f"\n📊 COMPLETE THURSDAY ANALYSIS RESULTS")
        print("=" * 80)
        
        # Summary by official label
        official_label_summary = defaultdict(lambda: {'total': 0, 'compliant': 0, 'total_cycle_time': 0})
        
        for analysis in sla_analysis:
            for official_label, compliance in analysis['sla_compliance'].items():
                official_label_summary[official_label]['total'] += 1
                official_label_summary[official_label]['total_cycle_time'] += analysis['full_cycle_hours']
                if compliance['is_compliant']:
                    official_label_summary[official_label]['compliant'] += 1
        
        print(f"\n📈 OFFICIAL SLA COMPLIANCE BY CATEGORY:")
        print("-" * 75)
        print(f"{'Official Category':<25} {'Total':<8} {'Compliant':<10} {'Compliance %':<12} {'Avg Cycle Time':<15}")
        print("-" * 75)
        
        for official_label in sorted(OFFICIAL_SLA_STANDARDS.keys()):
            if official_label in official_label_summary:
                stats = official_label_summary[official_label]
                total = stats['total']
                compliant = stats['compliant']
                avg_cycle_time = stats['total_cycle_time'] / total if total > 0 else 0
                compliance_pct = (compliant / total * 100) if total > 0 else 0
                sla_hours = OFFICIAL_SLA_STANDARDS[official_label]
                sla_text = f"{sla_hours}h" if sla_hours is not None else "No SLA"
                
                print(f"{official_label:<25} {total:<8} {compliant:<10} {compliance_pct:<12.1f}% {avg_cycle_time:<15.1f}h (SLA: {sla_text})")
            else:
                sla_hours = OFFICIAL_SLA_STANDARDS[official_label]
                sla_text = f"{sla_hours}h" if sla_hours is not None else "No SLA"
                print(f"{official_label:<25} {0:<8} {0:<10} {0:<12.1f}% {0:<15.1f}h (SLA: {sla_text})")
        
        # Overall statistics
        total_conversations = len(sla_analysis)
        total_with_official_labels = len([a for a in sla_analysis if a['official_labels']])
        total_with_sla = len([a for a in sla_analysis if a['sla_compliance']])
        
        # Calculate overall compliance
        total_compliant = 0
        total_with_sla_standards = 0
        for analysis in sla_analysis:
            for official_label, compliance in analysis['sla_compliance'].items():
                total_with_sla_standards += 1
                if compliance['is_compliant']:
                    total_compliant += 1
        
        overall_compliance = (total_compliant / total_with_sla_standards * 100) if total_with_sla_standards > 0 else 0
        
        # Calculate average cycle times
        avg_cycle_time = sum(a['full_cycle_hours'] for a in sla_analysis) / total_conversations if total_conversations > 0 else 0
        avg_days_open = sum(a['days_open'] for a in sla_analysis) / total_conversations if total_conversations > 0 else 0
        
        print(f"\n📊 COMPLETE OVERALL STATISTICS:")
        print(f"   • TOTAL conversations closed on Thursday: {total_conversations}")
        print(f"   • Created on Thursday: {created_on_thursday} ({created_on_thursday/total_conversations*100:.1f}%)")
        print(f"   • Created before Thursday: {created_before_thursday} ({created_before_thursday/total_conversations*100:.1f}%)")
        print(f"   • Average cycle time: {avg_cycle_time:.1f} hours ({avg_days_open:.1f} days)")
        print(f"   • Conversations with official labels: {total_with_official_labels} ({total_with_official_labels/total_conversations*100:.1f}%)")
        print(f"   • Conversations with SLA standards: {total_with_sla} ({total_with_sla/total_conversations*100:.1f}%)")
        print(f"   • Overall SLA compliance: {overall_compliance:.1f}% ({total_compliant}/{total_with_sla_standards})")

async def main():
    """Main analysis function"""
    print("🚀 Complete Thursday Analysis - ALL Tickets Closed on Thursday")
    print("=" * 60)
    
    analyzer = ThursdayAnalyzer(INTERCOM_ACCESS_TOKEN)
    
    # Get ALL conversations closed on Thursday
    conversations = await analyzer.get_all_conversations_closed_on_thursday("2025-08-28")
    
    if conversations:
        # Analyze the complete dataset
        sla_analysis, created_on_thursday, created_before_thursday = await analyzer.analyze_complete_dataset(conversations, "2025-08-28")
        
        if sla_analysis:
            analyzer.print_complete_results(sla_analysis, created_on_thursday, created_before_thursday)
            
            # Save results
            output_file = f"/Users/virulana/openai-cookbook/tools/outputs/thursday_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(sla_analysis, f, indent=2, default=str)
            print(f"\n💾 Complete results saved to: {output_file}")
        else:
            print("❌ Analysis failed")
    else:
        print("❌ No conversations found")

if __name__ == "__main__":
    asyncio.run(main())

