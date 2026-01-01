#!/usr/bin/env python3
"""
Find companies with churn date in the CSV file
"""

import csv
from pathlib import Path

csv_file = Path("../outputs/hubspot-crm-exports-companias-con-fecha-de-primer-n-2025-12-31.csv")

print("=" * 80)
print("SEARCHING FOR CHURNED COMPANIES")
print("=" * 80)

churned_companies = []
total_companies = 0

with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';')
    for row in reader:
        total_companies += 1
        churn_date = row.get('Fecha de baja de la compañía', '').strip()
        
        if churn_date:  # If churn date exists
            churned_companies.append({
                'company_id': row.get('Record ID', '').strip(),
                'company_name': row.get('Company name', '').strip(),
                'first_deal_date': row.get('First deal closed won date', '').strip(),
                'churn_date': churn_date,
                'cuit': row.get('CUIT', '').strip()
            })

print(f"\n📊 Statistics:")
print(f"   Total companies in file: {total_companies}")
print(f"   Companies with churn date: {len(churned_companies)}")
print(f"   Active companies: {total_companies - len(churned_companies)}")

if churned_companies:
    print(f"\n✅ Found {len(churned_companies)} churned companies")
    print("\n" + "=" * 80)
    print("FIRST 10 CHURNED COMPANIES:")
    print("=" * 80)
    
    for i, company in enumerate(churned_companies[:10], 1):
        print(f"\n{i}. {company['company_name']} (ID: {company['company_id']})")
        print(f"   - CUIT: {company['cuit']}")
        print(f"   - First deal closed won: {company['first_deal_date']}")
        print(f"   - Churn date: {company['churn_date']}")
else:
    print("\n⚠️  No companies with churn date found in the file")

print("\n" + "=" * 80)



