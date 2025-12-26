#!/usr/bin/env python3
"""Quick test to get MQL count with the fix"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from analyze_smb_mql_funnel import fetch_smb_mqls

start_date = '2025-12-01'
end_date = '2026-01-01'

print("="*80)
print("TESTING MQL COUNT WITH FIX")
print("="*80)
print()

print("Fetching MQL PYME contacts...")
mqls = fetch_smb_mqls(start_date, end_date)

print()
print("="*80)
print("RESULTS")
print("="*80)
print(f"MQL PYME count (after fix): {len(mqls)}")
print(f"HubSpot count: 959")
print(f"Difference: {len(mqls) - 959} ({((len(mqls) - 959) / 959 * 100) if 959 > 0 else 0:+.1f}%)")
print("="*80)

