#!/usr/bin/env python3
"""
Full Closed Won ↔ Facturación Reconciliation
=============================================
Compares HubSpot closed won deals (snapshot) with facturación DB bidirectionally.

Direction 1 (HubSpot → Facturación): Deals closed won that are NOT in facturación.
  → These should not exist: if we won the deal, we should be billing.

Direction 2 (Facturación → HubSpot): id_empresa in facturación with NO closed won deal.
  → These should not exist: if we bill them, we should have a closed won deal.

Uses: facturacion_hubspot.db, HubSpot API.
"""
import argparse
import calendar
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/data/facturacion_hubspot.db"
ACTIVE_DEAL_STAGES = ("closedwon", "34692158")


def fetch_closed_won_deals(
    client,
    closedate_start: str | None = None,
    closedate_end: str | None = None,
):
    """Fetch closed won deals. Filter by closedate at API when start/end provided (faster)."""
    all_deals = []
    after = None
    props = ["dealname", "id_empresa", "dealstage", "amount", "closedate", "hs_object_id"]
    filters = [{"propertyName": "dealstage", "operator": "IN", "values": list(ACTIVE_DEAL_STAGES)}]
    if closedate_start:
        filters.append({"propertyName": "closedate", "operator": "GTE", "value": closedate_start})
    if closedate_end:
        filters.append({"propertyName": "closedate", "operator": "LTE", "value": closedate_end})
    filter_groups = [{"filters": filters}]
    while True:
        resp = client.search_objects(
            object_type="deals",
            filter_groups=filter_groups,
            properties=props,
            limit=100,
            after=after,
        )
        results = resp.get("results", [])
        all_deals.extend(results)
        after = resp.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return all_deals


def get_facturacion_id_empresas(conn, id_empresas: set[str] | None = None):
    """Get id_empresa from facturacion. If id_empresas given, only query those (faster)."""
    if id_empresas is not None:
        if not id_empresas:
            return set()
        placeholders = ",".join("?" * len(id_empresas))
        rows = conn.execute(
            f"SELECT DISTINCT id_empresa FROM facturacion WHERE id_empresa IN ({placeholders})",
            tuple(id_empresas),
        ).fetchall()
        return {str(r[0]).strip() for r in rows}
    rows = conn.execute(
        "SELECT DISTINCT id_empresa FROM facturacion WHERE id_empresa IS NOT NULL AND TRIM(id_empresa) != ''"
    ).fetchall()
    return {str(r[0]).strip() for r in rows}


def run_reconciliation(db_path: str, dry_run: bool = False, year_filter: str = None, month_filter: int = None, export_path: str = None, skip_log: bool = False):
    from tools.hubspot_api.client import get_hubspot_client

    conn = sqlite3.connect(db_path)

    # 1. Closedate filter at API when year/month provided (faster: fetch only that period)
    closedate_start = closedate_end = None
    if year_filter:
        closedate_start = f"{year_filter}-01-01"
        closedate_end = f"{year_filter}-12-31"
        if month_filter is not None:
            last_day = calendar.monthrange(int(year_filter), month_filter)[1]
            closedate_start = f"{year_filter}-{month_filter:02d}-01"
            closedate_end = f"{year_filter}-{month_filter:02d}-{last_day}"

    # 2. HubSpot closed won deals (filtered at API when timeframe set)
    client = get_hubspot_client()
    if closedate_start:
        print(f"Fetching HubSpot closed won deals ({closedate_start} to {closedate_end}, filtered at API)...")
    else:
        print("Fetching all HubSpot closed won deals...")
    deals = fetch_closed_won_deals(client, closedate_start, closedate_end)
    print(f"HubSpot: {len(deals):,} closed won deals")

    # Build id_empresa -> deal (keep first if duplicates)
    hubspot_by_id = {}
    for d in deals:
        ie = (d.get("properties", {}).get("id_empresa") or "").strip()
        if ie and ie not in hubspot_by_id:
            hubspot_by_id[ie] = d
    hubspot_ids = set(hubspot_by_id.keys())

    # 3. Facturación: when timeframe filter, only query DB for those HubSpot ids (faster)
    if closedate_start:
        fact_ids = get_facturacion_id_empresas(conn, hubspot_ids)
        print(f"Facturación (queried for {len(hubspot_ids):,} ids): {len(fact_ids):,} found")
    else:
        fact_ids = get_facturacion_id_empresas(conn)
        print(f"Facturación: {len(fact_ids):,} unique id_empresa")

    # 4. Direction 1: HubSpot closed won NOT in facturación
    hubspot_not_fact = hubspot_ids - fact_ids
    def _amt(d):
        try:
            return float(d.get("properties", {}).get("amount") or 0)
        except (ValueError, TypeError):
            return 0.0

    deals_not_billed = [
        (ie, hubspot_by_id[ie].get("properties", {}).get("dealname", ""), _amt(hubspot_by_id[ie]))
        for ie in sorted(hubspot_not_fact, key=lambda x: -_amt(hubspot_by_id[x]))
    ]

    # 5. Direction 2: Facturación id_empresa with NO closed won deal (only when full snapshot)
    if closedate_start:
        billed_no_deal = []
    else:
        fact_not_hubspot = fact_ids - hubspot_ids
        billed_no_deal = []
        for ie in sorted(fact_not_hubspot):
            row = conn.execute(
                "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM facturacion WHERE id_empresa = ?",
                (ie,),
            ).fetchone()
            amt = row[0] if row else 0
            billed_no_deal.append((ie, amt))

    # 6. Report
    print("\n" + "=" * 70)
    title = "CLOSED WON ↔ FACTURACIÓN RECONCILIATION"
    if closedate_start:
        title += f" ({closedate_start} to {closedate_end})"
    else:
        title += " (Full Snapshot)"
    print(title)
    print("=" * 70)
    print(f"\nHubSpot closed won:     {len(hubspot_ids):,} unique id_empresa")
    print(f"Facturación:           {len(fact_ids):,} unique id_empresa")
    print(f"In both:               {len(hubspot_ids & fact_ids):,}")

    print("\n--- DIRECTION 1: HubSpot closed won NOT in facturación ---")
    print(f"   (Deals we won but are NOT being billed: {len(deals_not_billed):,})")
    if deals_not_billed:
        total = sum(d[2] for d in deals_not_billed)
        print(f"   Total amount: ${total:,.0f}")
        # Close date distribution
        from collections import defaultdict
        by_year = defaultdict(lambda: {"count": 0, "amount": 0.0})
        by_year_month = defaultdict(lambda: {"count": 0, "amount": 0.0})
        for ie in hubspot_not_fact:
            d = hubspot_by_id[ie]
            closedate = (d.get("properties", {}).get("closedate") or "").strip()
            amt = _amt(d)
            if closedate and len(closedate) >= 4:
                yr = closedate[:4]
                by_year[yr]["count"] += 1
                by_year[yr]["amount"] += amt
                if len(closedate) >= 7:
                    ym = closedate[:7]
                    by_year_month[ym]["count"] += 1
                    by_year_month[ym]["amount"] += amt
        print("\n   By close date (year):")
        for yr in sorted(by_year.keys()):
            v = by_year[yr]
            print(f"     {yr}: {v['count']:>4} deals, ${v['amount']:>,.0f}")
        print("\n   By close date (year-month, last 12 months):")
        recent_ym = sorted(by_year_month.keys(), reverse=True)[:12]
        for ym in recent_ym:
            v = by_year_month[ym]
            print(f"     {ym}: {v['count']:>4} deals, ${v['amount']:>,.0f}")
        print("\n   Top 20 by amount:")
        for ie, name, amt in deals_not_billed[:20]:
            closedate = (hubspot_by_id[ie].get("properties", {}).get("closedate") or "")[:10]
            print(f"     {ie:<10} | {closedate} | {name[:45]:<45} | ${amt:>12,.0f}")
        if len(deals_not_billed) > 20:
            print(f"     ... and {len(deals_not_billed) - 20} more")
        if export_path:
            import csv
            Path(export_path).parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["id_empresa", "deal_name", "amount", "closedate"])
                for ie, name, amt in deals_not_billed:
                    closedate = (hubspot_by_id[ie].get("properties", {}).get("closedate") or "")[:10]
                    w.writerow([ie, name, amt, closedate])
            print(f"\n   Exported: {export_path}")
    else:
        print("   None (all closed won deals are in facturación)")

    print("\n--- DIRECTION 2: Facturación id_empresa with NO closed won deal ---")
    if closedate_start:
        print("   (Skipped when filtering by timeframe; run without --year/--month for full snapshot)")
    else:
        print(f"   (We bill them but no closed won deal in HubSpot: {len(billed_no_deal):,})")
    if not closedate_start and billed_no_deal:
        total = sum(d[1] for d in billed_no_deal)
        print(f"   Total amount billed: ${total:,.0f}")
        print("\n   Top 20 by amount:")
        billed_no_deal_sorted = sorted(billed_no_deal, key=lambda x: -x[1])[:20]
        for ie, amt in billed_no_deal_sorted:
            print(f"     {ie:<10} | ${amt:>12,.0f}")
        if len(billed_no_deal) > 20:
            print(f"     ... and {len(billed_no_deal) - 20} more")
    else:
        print("   None (all facturación id_empresa have closed won deals)")

    # Log to SQLite for progress tracking
    if skip_log:
        conn.close()
        return len(deals_not_billed), len(billed_no_deal)
    match_count = len(hubspot_ids & fact_ids)
    period = None
    if year_filter:
        period = f"{year_filter}"
        if month_filter is not None:
            period = f"{year_filter}-{month_filter:02d}"
    try:
        from tools.utils.reconciliation_logger import log_reconciliation
        hubspot_ids_list = sorted(hubspot_ids, key=lambda x: int(x) if x.isdigit() else 0)
        fact_ids_list = sorted(fact_ids, key=lambda x: int(x) if x.isdigit() else 0)
        match_ids_list = sorted(hubspot_ids & fact_ids, key=lambda x: int(x) if x.isdigit() else 0)
        a_only_list = [t[0] for t in deals_not_billed]
        b_only_list = [t[0] for t in billed_no_deal]
        log_reconciliation(
            db_path=db_path,
            script="reconcile_closedwon_facturacion",
            reconciliation_type="hubspot_closedwon_facturacion",
            period=period,
            match_count=match_count,
            source_a_total=len(hubspot_ids),
            source_b_total=len(fact_ids),
            source_a_only_count=len(deals_not_billed),
            source_b_only_count=len(billed_no_deal),
            match_ids=match_ids_list,
            source_a_only_ids=a_only_list,
            source_b_only_ids=b_only_list,
            source_metadata={"year_filter": year_filter, "month_filter": month_filter} if year_filter else None,
        )
        print(f"\nReconciliation logged to {db_path}")
    except Exception as e:
        print(f"\nWarning: Could not log reconciliation: {e}")

    conn.close()
    return len(deals_not_billed), len(billed_no_deal)


def main():
    parser = argparse.ArgumentParser(description="Full closed won ↔ facturación reconciliation")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to facturacion_hubspot.db")
    parser.add_argument("--dry-run", action="store_true", help="No-op (same output)")
    parser.add_argument("--no-log", action="store_true", help="Skip logging to SQLite")
    parser.add_argument("--year", type=str, help="Filter Direction 1 to close date year (e.g. 2026)")
    parser.add_argument("--month", type=int, help="Filter Direction 1 to close date month 1-12 (use with --year)")
    parser.add_argument("--export", type=str, help="Export filtered list to CSV path")
    args = parser.parse_args()
    run_reconciliation(
        args.db,
        args.dry_run,
        year_filter=args.year,
        month_filter=args.month,
        export_path=args.export,
        skip_log=args.no_log,
    )


if __name__ == "__main__":
    main()
