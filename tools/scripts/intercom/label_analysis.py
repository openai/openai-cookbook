#!/usr/bin/env python3
"""
Label Analysis - Show all labels found and which ones are missing from SLA standards
"""

import json
from collections import defaultdict

# Load the complete analysis results
with open('/Users/virulana/openai-cookbook/tools/outputs/complete_friday_analysis_20250829_232210.json', 'r') as f:
    data = json.load(f)

# SLA Standards from our analysis
SLA_STANDARDS = {
    "Contabilidad": 48,
    "Conecta tu Banco": 48,
    "Inventario": 3,
    "Onboarding": 1,
    "Importaciones": 1,
    "Plan de Cuentas": None,
    "Soporte/ Clientes": 0.67,
    "Proveedores": 0.67,
    "Caida ARCA/ Clientes": 0.67,
    "Sin asignar": 0.67,
    "Tesoreria": 0.67,
    "Cobranzas/Retención": 0.33,
    "MC-Límite de Comprobantes": 48,
    "Soporte Telefónico- Llamado Cumplido": 0.67,
    "Mod Cont-Eliminar cuenta contable": 48,
    "Mod Cont-Nuevo plan de cuentas": 48,
    "Mod Cli-Aceptación Factura Electronica": 24,
    "CS Cambio de plan automático": 24,
    "Caída ARCA": 0.67,
    "Mod Cli-Errores en Factura Electrónica": 24,
    "Mod Cli - Facturas no aparecen en Colppy": 24,
    "Consultas-No responden": 24,
    "CS - eSueldos -Implementador Sueldos": 48,
}

# Analyze all labels found
all_labels = defaultdict(int)
labels_with_sla = defaultdict(int)
labels_without_sla = defaultdict(int)

for conversation in data:
    labels = conversation.get('labels', [])
    for label in labels:
        all_labels[label] += 1
        if label in SLA_STANDARDS:
            labels_with_sla[label] += 1
        else:
            labels_without_sla[label] += 1

print("🔍 LABEL ANALYSIS - ALL 282 TICKETS CLOSED ON FRIDAY")
print("=" * 80)

print(f"\n📊 SUMMARY:")
print(f"   • Total conversations: {len(data)}")
print(f"   • Conversations with ANY labels: {sum(all_labels.values())}")
print(f"   • Conversations with SLA-defined labels: {sum(labels_with_sla.values())}")
print(f"   • Conversations with undefined labels: {sum(labels_without_sla.values())}")

print(f"\n📈 LABELS WITH SLA STANDARDS ({len(labels_with_sla)} types):")
print("-" * 60)
for label, count in sorted(labels_with_sla.items(), key=lambda x: x[1], reverse=True):
    sla_hours = SLA_STANDARDS[label]
    sla_text = f"{sla_hours}h" if sla_hours is not None else "No SLA"
    print(f"   • {label}: {count} tickets (SLA: {sla_text})")

print(f"\n⚠️ LABELS WITHOUT SLA STANDARDS ({len(labels_without_sla)} types):")
print("-" * 60)
for label, count in sorted(labels_without_sla.items(), key=lambda x: x[1], reverse=True):
    print(f"   • {label}: {count} tickets")

print(f"\n📋 MISSING SLA DEFINITIONS:")
print("-" * 60)
if labels_without_sla:
    print("These labels need SLA standards defined:")
    for label, count in sorted(labels_without_sla.items(), key=lambda x: x[1], reverse=True):
        print(f"   • '{label}': None,  # {count} tickets - NEED SLA DEFINITION")
else:
    print("All labels have SLA standards defined!")

print(f"\n✅ VERIFICATION:")
print(f"   • Total in table (with SLA): {sum(labels_with_sla.values())}")
print(f"   • Total conversations: {len(data)}")
print(f"   • Conversations without labels: {len(data) - sum(all_labels.values())}")
print(f"   • Conversations with undefined labels: {sum(labels_without_sla.values())}")


