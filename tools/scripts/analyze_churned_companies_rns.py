#!/usr/bin/env python3
"""
Analyze churned companies using RNS government dataset
Looks up company creation dates from government registry and calculates aging
"""

import sys
from pathlib import Path
from datetime import datetime, date
sys.path.insert(0, str(Path(__file__).parent))
from rns_dataset_lookup import RNSDatasetLookup
from analyze_creation_to_close_timing_v2 import (
    calculate_company_age,
    calculate_time_difference,
    calculate_colppy_age,
    parse_date
)

print("=" * 80)
print("CHURNED COMPANIES - RNS DATASET ANALYSIS")
print("=" * 80)

# Churned companies we identified
churned_companies = [
    {
        'company_id': '9018923331',
        'company_name': '12514 Ticketing SA',
        'cuit': '30-71463258-9',
        'first_deal_date': '2017-04-26 00:00',
        'churn_date': '2022-12-29 21:00'
    },
    {
        'company_id': '9018856115',
        'company_name': '15026 Concierge Travel srl',
        'cuit': '30-71513243-1',
        'first_deal_date': '2017-09-05 00:00',
        'churn_date': '2021-09-30 21:00'
    },
    {
        'company_id': '9019082038',
        'company_name': '12436 Grupo A1 SRL',
        'cuit': '30-71166004-2',
        'first_deal_date': '2017-04-27 00:00',
        'churn_date': '2023-04-30 21:00'
    },
    {
        'company_id': '9019105626',
        'company_name': '11926 SERVICIOS DE SUSCRIPCION DIGITALES SA',
        'cuit': '30-71472244-8',
        'first_deal_date': '2017-03-19 00:00',
        'churn_date': '2022-10-30 21:00'
    },
    {
        'company_id': '9018923328',
        'company_name': '10877 - .',
        'cuit': '27-14077822-8',
        'first_deal_date': '2017-02-28 00:00',
        'churn_date': '2024-02-04 21:00'
    }
]

# Fix CUIT for company 4 (it was incorrectly extracted)
churned_companies[3]['cuit'] = '30-71472244-8'

print(f"\n📋 Companies to analyze: {len(churned_companies)}")
print(f"📅 Reference Date (Today): {date.today()}\n")

# Initialize RNS lookup
print("🔍 Initializing RNS Dataset Lookup...")
lookup = RNSDatasetLookup()

# Check if dataset exists
dataset_files = list(lookup.dataset_dir.glob('*.csv')) + list(lookup.dataset_dir.glob('*.zip'))
if not dataset_files:
    print(f"\n⚠️  WARNING: No RNS dataset files found in {lookup.dataset_dir}")
    print(f"   Please download the dataset first or place CSV/ZIP files in that directory")
    print(f"   You can use: lookup.download_sample_dataset() for testing")
    sys.exit(1)

print(f"✓ Found {len(dataset_files)} dataset file(s)")

# Process each company
print("\n" + "=" * 80)
print("PROCESSING COMPANIES")
print("=" * 80)

results = []

for i, company in enumerate(churned_companies, 1):
    print(f"\n{'='*80}")
    print(f"{i}. {company['company_name']} (ID: {company['company_id']})")
    print(f"{'='*80}")
    
    cuit = company['cuit']
    print(f"\n📋 Company Data:")
    print(f"   - CUIT: {cuit}")
    print(f"   - First deal closed won: {company['first_deal_date']}")
    print(f"   - Churn date: {company['churn_date']}")
    
    # Lookup in RNS dataset
    print(f"\n🔍 Looking up CUIT {cuit} in RNS dataset...")
    try:
        result = lookup.lookup_cuit(cuit)
        
        if result.found:
            print(f"   ✅ Found in RNS dataset!")
            print(f"   - Creation date: {result.creation_date}")
            print(f"   - Razón social: {result.razon_social}")
            print(f"   - Tipo societario: {result.tipo_societario}")
            print(f"   - Provincia: {result.provincia}")
            
            rns_creation_date = result.creation_date
            
            # Calculate Company Age (from RNS creation to churn date)
            print(f"\n📊 1️⃣ COMPANY AGE (RNS Creation → Churn Date)")
            print(f"   - From: {rns_creation_date} (RNS creation)")
            print(f"   - To: {company['churn_date']} (churn date)")
            
            churn_date_parsed = parse_date(company['churn_date'])
            if rns_creation_date and churn_date_parsed:
                company_age = calculate_company_age(rns_creation_date, reference_date=churn_date_parsed)
                if company_age['days'] is not None:
                    print(f"   ✅ Result: {company_age['formatted']}")
                    print(f"      - Days: {company_age['days']:,}")
                    print(f"      - Months: {company_age['months']:.1f}")
                    print(f"      - Years: {company_age['years']:.2f}")
                else:
                    print(f"   ⚠️  {company_age['formatted']}")
            
            # Calculate Time to Close (from RNS creation to first deal)
            print(f"\n📊 2️⃣ TIME TO CLOSE (RNS Creation → First Deal)")
            print(f"   - From: {rns_creation_date} (RNS creation)")
            print(f"   - To: {company['first_deal_date']} (first deal closed won)")
            
            if rns_creation_date and company['first_deal_date']:
                time_to_close = calculate_time_difference(rns_creation_date, company['first_deal_date'])
                if time_to_close['days'] is not None:
                    print(f"   ✅ Result: {time_to_close['formatted']}")
                    print(f"      - Days: {time_to_close['days']:,}")
                    print(f"      - Months: {time_to_close['months']:.1f}")
                    print(f"      - Years: {time_to_close['years']:.2f}")
                else:
                    print(f"   ⚠️  {time_to_close['formatted']}")
            
            # Calculate Colppy Age (from first deal to churn)
            print(f"\n📊 3️⃣ COLPPY AGE (First Deal → Churn Date)")
            print(f"   - From: {company['first_deal_date']} (first deal closed won)")
            print(f"   - To: {company['churn_date']} (churn date)")
            
            colppy_age = calculate_colppy_age(
                creation_date=company['first_deal_date'],
                churn_date=company['churn_date'],
                reference_date=churn_date_parsed
            )
            if colppy_age['days'] is not None:
                print(f"   ✅ Result: {colppy_age['formatted']}")
                print(f"      - Days: {colppy_age['days']:,}")
                print(f"      - Months: {colppy_age['months']:.1f}")
                print(f"      - Years: {colppy_age['years']:.2f}")
                print(f"      - Status: {'Churned' if colppy_age['is_churned'] else 'Active'}")
            else:
                print(f"   ⚠️  {colppy_age['formatted']}")
            
            # Store result
            results.append({
                'company_name': company['company_name'],
                'cuit': cuit,
                'rns_found': True,
                'rns_creation_date': rns_creation_date,
                'rns_razon_social': result.razon_social,
                'rns_tipo_societario': result.tipo_societario,
                'first_deal_date': company['first_deal_date'],
                'churn_date': company['churn_date'],
                'company_age_days': company_age.get('days'),
                'company_age_formatted': company_age.get('formatted'),
                'time_to_close_days': time_to_close.get('days'),
                'time_to_close_formatted': time_to_close.get('formatted'),
                'colppy_age_days': colppy_age.get('days'),
                'colppy_age_formatted': colppy_age.get('formatted')
            })
            
        else:
            print(f"   ❌ NOT FOUND in RNS dataset")
            print(f"   - This CUIT may not be in the dataset, or it's an individual (not a company)")
            
            results.append({
                'company_name': company['company_name'],
                'cuit': cuit,
                'rns_found': False,
                'rns_creation_date': None,
                'first_deal_date': company['first_deal_date'],
                'churn_date': company['churn_date']
            })
            
    except Exception as e:
        print(f"   ❌ Error looking up CUIT: {e}")
        results.append({
            'company_name': company['company_name'],
            'cuit': cuit,
            'rns_found': False,
            'error': str(e)
        })

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

found_count = sum(1 for r in results if r.get('rns_found'))
print(f"\n📊 Results:")
print(f"   - Total companies analyzed: {len(churned_companies)}")
print(f"   - Found in RNS dataset: {found_count}")
print(f"   - Not found: {len(churned_companies) - found_count}")

if found_count > 0:
    print(f"\n✅ Successfully calculated aging for {found_count} companies")
    print(f"\n📋 Detailed Results:")
    for r in results:
        if r.get('rns_found'):
            print(f"\n   {r['company_name']} ({r['cuit']}):")
            print(f"      - Company Age: {r.get('company_age_formatted', 'N/A')}")
            print(f"      - Time to Close: {r.get('time_to_close_formatted', 'N/A')}")
            print(f"      - Colppy Age: {r.get('colppy_age_formatted', 'N/A')}")

print("\n" + "=" * 80)

