#!/usr/bin/env python3
"""
Classify Deal Age from Property History
=======================================
Fetches createdate, closedate, and dealstage history from HubSpot to distinguish:
- **fresh_close**: Deal created and closed in the same period (or within ~90 days)
- **old_deal_date_correction**: Deal was first closed long ago; current closedate was updated later
- **slow_close**: Deal created long ago but first closed in the period (genuine slow close)

Usage:
    # Deals from facturacion_hubspot.db for a month
    python classify_deal_age_from_history.py --year 2026 --month 2

    # Specific deal IDs
    python classify_deal_age_from_history.py --deal-ids 13424641957 12345678

    # CSV with deal_id or hubspot_id column
    python classify_deal_age_from_history.py --csv input.csv

    # Export results to CSV
    python classify_deal_age_from_history.py --year 2026 --month 2 --output results.csv
"""
import argparse
import calendar
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

_script_dir = Path(__file__).resolve().parent
_repo_root = _script_dir.parents[3]
sys.path.insert(0, str(_repo_root))
from dotenv import load_dotenv

load_dotenv()

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY") or os.getenv("ColppyCRMAutomations")
HUBSPOT_BASE_URL = "https://api.hubapi.com"
DEFAULT_DB = "tools/data/facturacion_hubspot.db"

# Stage values that mean "closed won"
CLOSEDWON_STAGES = {"closedwon", "34692158"}

# Threshold: if first_closedwon is more than this many days before current closedate, it's a date correction
DATE_CORRECTION_DAYS = 180

# Threshold: if createdate is more than this many days before first_closedwon, it's a slow close
SLOW_CLOSE_DAYS = 180


def _parse_date(value: str) -> Optional[datetime]:
    """Parse HubSpot date string to datetime."""
    if not value or not value.strip() or value.strip().lower() == "null":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _date_only(dt: Optional[datetime]) -> str:
    """Return YYYY-MM-DD or empty string."""
    if dt is None:
        return ""
    return dt.date().isoformat()


def fetch_deal_with_history(deal_id: str) -> Optional[dict[str, Any]]:
    """
    Fetch deal with createdate, closedate, dealstage history from HubSpot API.

    Returns dict with: dealname, createdate, closedate, first_closedwon, dealstage_history, etc.
    """
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/{deal_id}"
    params = {
        "properties": "dealname,createdate,closedate,dealstage,id_empresa",
        "propertiesWithHistory": "createdate,closedate,dealstage",
    }
    headers = {"Authorization": f"Bearer {HUBSPOT_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error fetching deal {deal_id}: {e}", file=sys.stderr)
        return None

    props = data.get("properties", {})
    hist = data.get("propertiesWithHistory", {})

    createdate = _parse_date(props.get("createdate"))
    closedate = _parse_date(props.get("closedate"))

    # First time deal entered closedwon (from dealstage history)
    first_closedwon: Optional[datetime] = None
    stage_hist = hist.get("dealstage")
    if stage_hist:
        versions = stage_hist if isinstance(stage_hist, list) else stage_hist.get("versions", [])
        closedwon_timestamps = []
        for v in versions:
            val = (v.get("value") or "").strip()
            if val in CLOSEDWON_STAGES:
                ts = v.get("timestamp")
                if ts:
                    dt = _parse_date(ts)
                    if dt:
                        closedwon_timestamps.append(dt)
        if closedwon_timestamps:
            first_closedwon = min(closedwon_timestamps)

    # Earliest closedate from history (fallback if no dealstage history)
    earliest_closedate: Optional[datetime] = None
    closedate_hist = hist.get("closedate")
    if closedate_hist:
        versions = closedate_hist if isinstance(closedate_hist, list) else closedate_hist.get("versions", [])
        valid = []
        for v in versions:
            val = v.get("value")
            dt = _parse_date(val) if val else None
            if dt:
                valid.append(dt)
        if valid:
            earliest_closedate = min(valid)

    return {
        "deal_id": deal_id,
        "dealname": props.get("dealname", ""),
        "id_empresa": props.get("id_empresa", ""),
        "createdate": createdate,
        "closedate": closedate,
        "first_closedwon": first_closedwon or earliest_closedate,
        "earliest_closedate": earliest_closedate,
    }


def classify_deal(row: dict[str, Any], period_start: Optional[datetime] = None) -> str:
    """
    Classify deal as fresh_close, old_deal_date_correction, or slow_close.

    Args:
        row: Output from fetch_deal_with_history
        period_start: Start of the period (e.g. first day of month). If None, uses closedate.
    """
    createdate = row.get("createdate")
    closedate = row.get("closedate")
    first_closedwon = row.get("first_closedwon")

    if not closedate:
        return "unknown"

    # Use first_closedwon if available; else fall back to closedate for "true" close
    true_close = first_closedwon or closedate

    # Days between true close and current closedate
    close_diff_days = (closedate - true_close).days if (closedate and true_close) else 0

    # Days between createdate and true close
    create_to_close_days = (
        (true_close - createdate).days if (createdate and true_close) else 0
    )

    # Old deal, date correction: current closedate was set much later than when it was first won
    if close_diff_days > DATE_CORRECTION_DAYS:
        return "old_deal_date_correction"

    # Slow close: deal was created long before it was first closed
    if create_to_close_days > SLOW_CLOSE_DAYS:
        return "slow_close"

    # Fresh close: created and closed within reasonable window
    return "fresh_close"


def load_deals_from_db(db_path: Path, year: int, month: int) -> list[tuple[str, str, str]]:
    """Load (hubspot_id, id_empresa, deal_name) from facturacion_hubspot.db for given month."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year}-{month:02d}-{last_day}"

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """SELECT hubspot_id, id_empresa, deal_name FROM deals
           WHERE close_date >= ? AND close_date <= ?
           ORDER BY id_empresa""",
        (start, end),
    ).fetchall()
    conn.close()
    return [(str(r[0]), str(r[1]), r[2] or "") for r in rows if r[0]]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify deals as fresh_close, old_deal_date_correction, or slow_close",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--year", type=int, help="Year (with --month) to load deals from DB")
    parser.add_argument("--month", type=int, help="Month 1-12 (with --year) to load deals from DB")
    parser.add_argument("--deal-ids", nargs="+", help="HubSpot deal IDs to analyze")
    parser.add_argument("--csv", type=str, help="CSV with deal_id or hubspot_id column")
    parser.add_argument("--db", type=str, default=DEFAULT_DB, help="Path to facturacion_hubspot.db")
    parser.add_argument("--output", type=str, help="Output CSV path")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    if not HUBSPOT_API_KEY:
        print("❌ HUBSPOT_API_KEY or ColppyCRMAutomations not found in environment", file=sys.stderr)
        return 1

    deal_inputs: list[tuple[str, str, str]] = []  # (hubspot_id, id_empresa, deal_name)

    if args.year and args.month:
        db_path = Path(args.db)
        if not db_path.exists():
            print(f"❌ Database not found: {db_path}", file=sys.stderr)
            return 1
        deal_inputs = load_deals_from_db(db_path, args.year, args.month)
        print(f"Loaded {len(deal_inputs)} deals from DB for {args.year}-{args.month:02d}\n")
    elif args.deal_ids:
        for did in args.deal_ids:
            deal_inputs.append((did, "", ""))
    elif args.csv:
        import csv as csv_module

        with open(args.csv, newline="", encoding="utf-8") as f:
            reader = csv_module.DictReader(f)
            fields = reader.fieldnames or []
            col = "deal_id" if "deal_id" in fields else ("hubspot_id" if "hubspot_id" in fields else None)
            if not col:
                print("❌ CSV must have deal_id or hubspot_id column", file=sys.stderr)
                return 1
            for r in reader:
                did = (r.get(col) or "").strip()
                if did:
                    deal_inputs.append((did, r.get("id_empresa", ""), r.get("deal_name", "")))
        print(f"Loaded {len(deal_inputs)} deals from CSV\n")
    else:
        parser.error("Provide --year/--month, --deal-ids, or --csv")

    if not deal_inputs:
        print("No deals to process.")
        return 0

    period_start = None
    if args.year and args.month:
        period_start = datetime(args.year, args.month, 1)

    results: list[dict[str, Any]] = []
    for i, (hubspot_id, id_empresa, deal_name_db) in enumerate(deal_inputs):
        if (i + 1) % 5 == 0 or i == 0:
            print(f"Fetching {i + 1}/{len(deal_inputs)}...", flush=True)
        row = fetch_deal_with_history(hubspot_id)
        if not row:
            continue
        if not row.get("id_empresa") and id_empresa:
            row["id_empresa"] = id_empresa
        if not row.get("dealname") and deal_name_db:
            row["dealname"] = deal_name_db
        row["classification"] = classify_deal(row, period_start)
        results.append(row)
        time.sleep(args.delay)

    # Summary by classification
    by_class: dict[str, list[dict]] = {}
    for r in results:
        c = r["classification"]
        by_class.setdefault(c, []).append(r)

    print("\n" + "=" * 100)
    print("Deal Age Classification")
    print("=" * 100)
    print("\n## Summary\n")
    print("| Classification | Count | Description |")
    print("|-----------------|-------|-------------|")
    print("| fresh_close |", len(by_class.get("fresh_close", [])), "| Created and closed in same/similar period |")
    print("| old_deal_date_correction |", len(by_class.get("old_deal_date_correction", [])), "| First closed long ago; closedate updated later |")
    print("| slow_close |", len(by_class.get("slow_close", [])), "| Created long ago, first closed in period |")
    print("| unknown |", len(by_class.get("unknown", [])), "| Missing data |")

    print("\n## Full List\n")
    print("| id_empresa | deal_name | createdate | closedate | first_closedwon | classification |")
    print("|------------|-----------|------------|----------|-----------------|----------------|")
    for r in sorted(results, key=lambda x: (x["classification"], x.get("id_empresa", ""))):
        print(
            "|",
            r.get("id_empresa", ""),
            "|",
            (r.get("dealname", "") or "")[:40] + ("..." if len(r.get("dealname", "")) > 40 else ""),
            "|",
            _date_only(r.get("createdate")),
            "|",
            _date_only(r.get("closedate")),
            "|",
            _date_only(r.get("first_closedwon")),
            "|",
            r["classification"],
            "|",
        )

    if args.output:
        import csv as csv_module

        out_cols = [
            "id_empresa", "deal_id", "dealname", "createdate", "closedate",
            "first_closedwon", "classification",
        ]
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            w = csv_module.DictWriter(f, fieldnames=out_cols, extrasaction="ignore")
            w.writeheader()
            for r in results:
                row = {**r, "createdate": _date_only(r.get("createdate")), "closedate": _date_only(r.get("closedate")), "first_closedwon": _date_only(r.get("first_closedwon"))}
                w.writerow(row)
        print(f"\n💾 Results saved to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
