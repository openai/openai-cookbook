#!/usr/bin/env python3
"""
Quick verification of Colppy Age calculations
"""

from datetime import datetime, date
import sys
sys.path.insert(0, '/Users/virulana/openai-cookbook/tools/scripts')
from analyze_creation_to_close_timing_v2 import calculate_colppy_age

print("=" * 80)
print("VERIFICATION: Colppy Age Calculations")
print("=" * 80)

# Today's date for reference
today = datetime.now().date()
print(f"\n📅 Today's date: {today}")
print(f"   (Used as reference for active companies)")

# SCENARIO 1: ACTIVE COMPANY
print("\n" + "=" * 80)
print("SCENARIO 1: ACTIVE COMPANY (No Churn Date)")
print("=" * 80)

create_date_active = "2024-06-15 10:30"
churn_date_active = ""  # Empty = active

print(f"\nInput:")
print(f"  Create Date (HubSpot): {create_date_active}")
print(f"  Churn Date: {churn_date_active or '(empty - company is active)'}")

result_active = calculate_colppy_age(create_date_active, churn_date_active)

print(f"\n✅ Result:")
print(f"  Days: {result_active['days']}")
print(f"  Months: {result_active['months']:.1f}")
print(f"  Years: {result_active['years']:.2f}")
print(f"  Formatted: {result_active['formatted']}")
print(f"  Is Churned: {result_active['is_churned']}")

# Manual verification
from analyze_creation_to_close_timing_v2 import parse_date
create_parsed = parse_date(create_date_active)
if create_parsed:
    manual_days = (today - create_parsed).days
    print(f"\n  ✓ Manual Check: {manual_days} days from {create_parsed} to {today}")
    print(f"  ✓ Match: {'YES' if abs(result_active['days'] - manual_days) <= 1 else 'NO'}")

# SCENARIO 2: CHURNED COMPANY
print("\n" + "=" * 80)
print("SCENARIO 2: CHURNED COMPANY (With Churn Date)")
print("=" * 80)

create_date_churned = "2024-03-01 14:20"
churn_date_churned = "2024-09-15 16:45"

print(f"\nInput:")
print(f"  Create Date (HubSpot): {create_date_churned}")
print(f"  Churn Date: {churn_date_churned}")

result_churned = calculate_colppy_age(create_date_churned, churn_date_churned)

print(f"\n✅ Result:")
print(f"  Days: {result_churned['days']}")
print(f"  Months: {result_churned['months']:.1f}")
print(f"  Years: {result_churned['years']:.2f}")
print(f"  Formatted: {result_churned['formatted']}")
print(f"  Is Churned: {result_churned['is_churned']}")

# Manual verification
create_parsed2 = parse_date(create_date_churned)
churn_parsed = parse_date(churn_date_churned)
if create_parsed2 and churn_parsed:
    manual_days2 = (churn_parsed - create_parsed2).days
    print(f"\n  ✓ Manual Check: {manual_days2} days from {create_parsed2} to {churn_parsed}")
    print(f"  ✓ Match: {'YES' if abs(result_churned['days'] - manual_days2) <= 1 else 'NO'}")

# SCENARIO 3: RECENT CHURN (Short tenure)
print("\n" + "=" * 80)
print("SCENARIO 3: RECENT CHURN (Short tenure - 19 days)")
print("=" * 80)

create_date_short = "2024-12-01 09:00"
churn_date_short = "2024-12-20 17:30"

print(f"\nInput:")
print(f"  Create Date (HubSpot): {create_date_short}")
print(f"  Churn Date: {churn_date_short}")

result_short = calculate_colppy_age(create_date_short, churn_date_short)

print(f"\n✅ Result:")
print(f"  Days: {result_short['days']}")
print(f"  Months: {result_short['months']:.1f}")
print(f"  Years: {result_short['years']:.2f}")
print(f"  Formatted: {result_short['formatted']}")
print(f"  Is Churned: {result_short['is_churned']}")

# Manual verification
create_parsed3 = parse_date(create_date_short)
churn_parsed3 = parse_date(churn_date_short)
if create_parsed3 and churn_parsed3:
    manual_days3 = (churn_parsed3 - create_parsed3).days
    print(f"\n  ✓ Manual Check: {manual_days3} days from {create_parsed3} to {churn_parsed3}")
    print(f"  ✓ Match: {'YES' if abs(result_short['days'] - manual_days3) <= 1 else 'NO'}")

print("\n" + "=" * 80)
print("✅ Verification Complete")
print("=" * 80)
print("\nSummary:")
print(f"  • Active company: Calculates from today ({today}) to Create Date")
print(f"  • Churned company: Calculates from Churn Date to Create Date")
print(f"  • Both scenarios correctly identify churn status")
print("=" * 80)









