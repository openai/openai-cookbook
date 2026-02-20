#!/usr/bin/env python3
"""
Subscription Billed - First payment EVER per id_empresa (via Mixpanel MCP).

Replicates the JQL logic using Mixpanel MCP Run-Segmentation-Query:
1. Jan 2026 segmentation (on company_id) → companies + first date in Jan
2. Pre-2026 segmentation with where filter per batch → exclude companies that had events before
3. Result: id_empresa whose first-ever Subscription Billed was in January 2026

Usage: Run via Cursor with Mixpanel MCP enabled. This script processes
the MCP output files - the actual MCP calls are made by the agent.

For standalone JQL (no MCP): use run_jql.py with subscription_billed_first_payment.jql
"""

import ast
import json
from pathlib import Path

# Jan 2026: company_id -> first date in Jan (from Run-Segmentation-Query Jan 2026)
JAN_FIRST = {
    "79881": "2026-01-02", "73323": "2026-01-06", "106419": "2026-01-06", "106422": "2026-01-06",
    "105976": "2026-01-07", "97604": "2026-01-07", "69858": "2026-01-26", "108151": "2026-01-27",
    "109180": "2026-01-27", "106819": "2026-01-27", "109121": "2026-01-27", "11675": "2026-01-12",
    "109377": "2026-01-28", "43478": "2026-01-28", "109363": "2026-01-29", "109591": "2026-01-29",
    "109595": "2026-01-29", "5779": "2026-01-29", "91840": "2026-01-29", "18266": "2026-01-30",
    "81322": "2026-01-16", "107030": "2026-01-16", "106552": "2026-01-16", "78753": "2026-01-19",
    "106913": "2026-01-22", "28478": "2026-01-22", "108242": "2026-01-22", "103973": "2026-01-23",
    "39081": "2026-01-23", "57430": "2026-01-08", "33734": "2026-01-09", "97884": "2026-01-09",
    "106594": "2026-01-10", "22359": "2026-01-12", "91155": "2026-01-12", "40619": "2026-01-12",
    "5260": "2026-01-12", "97280": "2026-01-12", "106808": "2026-01-13", "74479": "2026-01-13",
    "106154": "2026-01-15", "106472": "2026-01-15", "106817": "2026-01-15",
}

# Companies that had Subscription Billed BEFORE 2026 (from MCP pre-2026 queries with where filter)
HAD_BEFORE_2026 = {
    "79881", "57430", "73323",  # batch 1
    "5260",                     # batch 2
    "69858", "39081", "78753",  # batch 3
    "11675", "18266", "5779", "43478", "91840",  # batch 4
}


def get_first_ever_jan2026() -> list[dict]:
    """Return id_empresa whose first-ever Subscription Billed was in January 2026."""
    result = []
    for cid, first_date in JAN_FIRST.items():
        if cid not in HAD_BEFORE_2026:
            result.append({"id_empresa": cid, "first_billed_date": first_date})
    return sorted(result, key=lambda x: x["first_billed_date"])


def main():
    result = get_first_ever_jan2026()
    out_path = Path(__file__).parent.parent.parent / "outputs" / "subscription_billed_first_payment_ever_jan2026_MCP.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"First-ever Subscription Billed in Jan 2026 (via MCP): {len(result)}")
    for r in result:
        print(f"  {r['id_empresa']} | {r['first_billed_date']}")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
