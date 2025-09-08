#!/usr/bin/env python3
"""
Corrected SLA Analysis - Using Official SLA Table Standards Only
Maps conversation labels to official categories and excludes non-standard labels
"""

import json
from collections import defaultdict

# Load the complete analysis results
with open('/Users/virulana/openai-cookbook/tools/outputs/complete_friday_analysis_20250829_232210.json', 'r') as f:
    data = json.load(f)

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

def map_labels_to_official_categories(labels):
    """Map conversation labels to official SLA categories"""
    mapped_labels = []
    for label in labels:
        if label in LABEL_MAPPING:
            official_label = LABEL_MAPPING[label]
            if official_label in OFFICIAL_SLA_STANDARDS:
                mapped_labels.append(official_label)
    return list(set(mapped_labels))  # Remove duplicates

# Analyze with corrected mapping
official_label_counts = defaultdict(int)
official_label_compliance = defaultdict(lambda: {'total': 0, 'compliant': 0, 'total_cycle_time': 0})
total_conversations = len(data)
conversations_with_official_labels = 0
conversations_without_official_labels = 0

for conversation in data:
    labels = conversation.get('labels', [])
    mapped_labels = map_labels_to_official_categories(labels)
    
    if mapped_labels:
        conversations_with_official_labels += 1
        for official_label in mapped_labels:
            official_label_counts[official_label] += 1
            
            # Calculate SLA compliance
            sla_hours = OFFICIAL_SLA_STANDARDS[official_label]
            if sla_hours is not None:
                cycle_hours = conversation['full_cycle_hours']
                is_compliant = cycle_hours <= sla_hours
                
                official_label_compliance[official_label]['total'] += 1
                official_label_compliance[official_label]['total_cycle_time'] += cycle_hours
                if is_compliant:
                    official_label_compliance[official_label]['compliant'] += 1
    else:
        conversations_without_official_labels += 1

print("🔍 CORRECTED SLA ANALYSIS - OFFICIAL STANDARDS ONLY")
print("=" * 80)

print(f"\n📊 SUMMARY:")
print(f"   • Total conversations: {total_conversations}")
print(f"   • Conversations with official labels: {conversations_with_official_labels}")
print(f"   • Conversations without official labels: {conversations_without_official_labels}")
print(f"   • Conversations excluded from SLA analysis: {conversations_without_official_labels}")

print(f"\n📈 OFFICIAL SLA COMPLIANCE BY CATEGORY:")
print("-" * 75)
print(f"{'Official Category':<25} {'Total':<8} {'Compliant':<10} {'Compliance %':<12} {'Avg Cycle Time':<15}")
print("-" * 75)

for official_label in sorted(OFFICIAL_SLA_STANDARDS.keys()):
    if official_label in official_label_compliance:
        stats = official_label_compliance[official_label]
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

print(f"\n📋 LABEL MAPPING SUMMARY:")
print("-" * 60)
for official_label in sorted(OFFICIAL_SLA_STANDARDS.keys()):
    if official_label in official_label_counts:
        count = official_label_counts[official_label]
        print(f"   • {official_label}: {count} tickets")

print(f"\n⚠️ EXCLUDED LABELS (not in official standards):")
print("-" * 60)
excluded_labels = defaultdict(int)
for conversation in data:
    labels = conversation.get('labels', [])
    for label in labels:
        if label not in LABEL_MAPPING:
            excluded_labels[label] += 1

for label, count in sorted(excluded_labels.items(), key=lambda x: x[1], reverse=True):
    print(f"   • {label}: {count} tickets (EXCLUDED)")

print(f"\n✅ VERIFICATION:")
print(f"   • Total conversations: {total_conversations}")
print(f"   • With official labels: {conversations_with_official_labels}")
print(f"   • Without official labels: {conversations_without_official_labels}")
print(f"   • Total official label instances: {sum(official_label_counts.values())}")

# Calculate overall compliance
total_official_instances = 0
total_compliant_instances = 0
for official_label, stats in official_label_compliance.items():
    sla_hours = OFFICIAL_SLA_STANDARDS[official_label]
    if sla_hours is not None:
        total_official_instances += stats['total']
        total_compliant_instances += stats['compliant']

overall_compliance = (total_compliant_instances / total_official_instances * 100) if total_official_instances > 0 else 0

print(f"\n🎯 OVERALL OFFICIAL SLA COMPLIANCE:")
print(f"   • Total official SLA instances: {total_official_instances}")
print(f"   • Compliant instances: {total_compliant_instances}")
print(f"   • Overall compliance: {overall_compliance:.1f}%")


