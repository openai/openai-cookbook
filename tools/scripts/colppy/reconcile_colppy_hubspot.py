#!/usr/bin/env python3
"""
Colppy First Payments ↔ HubSpot Closed Won Reconciliation
==========================================================
Reconciles Colppy first payments with HubSpot closed won for a given month.
HubSpot is filtered at API by closedate (no full fetch).

Usage:
  python tools/scripts/colppy/reconcile_colppy_hubspot.py --year 2026 --month 2
  python tools/scripts/colppy/reconcile_colppy_hubspot.py --year 2026 --month 2 --output tools/outputs/reconcile_202602.md
"""
import argparse
import calendar
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

SNAPSHOT_PATH = REPO_ROOT / "plugins/colppy-ceo-assistant/docs/colppy_first_payments_snapshot.json"
ACTIVE_DEAL_STAGES = ("closedwon", "34692158")


def load_colppy_by_month(snapshot_path: Path, year: str, month: int) -> list[dict]:
    """Load Colppy first payments for given year-month from snapshot."""
    month_key = f"{year}-{month:02d}"
    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("first_payments_by_month", {}).get(month_key, [])


def fetch_hubspot_closed_won_for_period(
    client, year: str, month: int
) -> list[dict]:
    """Fetch HubSpot closed won deals filtered by closedate at API level (no full fetch)."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    all_deals = []
    after = None
    props = ["dealname", "id_empresa", "dealstage", "amount", "closedate", "hs_object_id"]
    filter_groups = [{
        "filters": [
            {"propertyName": "dealstage", "operator": "IN", "values": list(ACTIVE_DEAL_STAGES)},
            {"propertyName": "closedate", "operator": "GTE", "value": start},
            {"propertyName": "closedate", "operator": "LTE", "value": end},
        ]
    }]
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


def run(year: str, month: int, output_path: str | None = None, db_path: str | None = None) -> None:
    from tools.hubspot_api.client import get_hubspot_client
    from tools.utils.reconciliation_logger import log_reconciliation

    month_key = f"{year}-{month:02d}"
    colppy = load_colppy_by_month(SNAPSHOT_PATH, year, month)
    colppy_by_id = {str(r["idEmpresa"]): r for r in colppy}
    colppy_ids = set(colppy_by_id.keys())

    client = get_hubspot_client()
    print(f"Fetching HubSpot closed won deals ({month_key}, filtered at API)...")
    deals = fetch_hubspot_closed_won_for_period(client, year, month)
    print(f"HubSpot: {len(deals):,} deals")

    hubspot_by_id = {}
    for d in deals:
        ie = (d.get("properties", {}).get("id_empresa") or "").strip()
        if ie and ie not in hubspot_by_id:
            hubspot_by_id[ie] = d
    hubspot_ids = set(hubspot_by_id.keys())

    match_ids = colppy_ids & hubspot_ids
    colppy_only = colppy_ids - hubspot_ids
    hubspot_only = hubspot_ids - colppy_ids

    def _fmt_amt(x):
        try:
            return f"${float(x):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (ValueError, TypeError):
            return str(x)

    lines = []
    lines.append(f"# {month_key}: Colppy First Payments ↔ HubSpot Closed Won — Full Reconciliation")
    lines.append("")
    last_day = calendar.monthrange(int(year), month)[1]
    lines.append(f"**Sources:** Colppy `colppy_first_payments_snapshot.json` | HubSpot API (closedate {month_key}-01 to {month_key}-{last_day:02d})")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Category | Count |")
    lines.append(f"|----------|-------|")
    lines.append(f"| MATCH (in both) | {len(match_ids)} |")
    lines.append(f"| Colppy only | {len(colppy_only)} |")
    lines.append(f"| HubSpot only | {len(hubspot_only)} |")
    lines.append(f"| **Colppy total** | {len(colppy_ids)} |")
    lines.append(f"| **HubSpot total** | {len(hubspot_ids)} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## MATCH — Full List")
    lines.append("")
    lines.append("| id_empresa | Colppy plan | Colppy importe | medioPago | cuit_invoicing | HubSpot deal | HubSpot amount | closedate |")
    lines.append("|------------|-------------|----------------|-----------|----------------|--------------|----------------|-----------|")
    for ie in sorted(match_ids, key=lambda x: int(x) if x.isdigit() else 0):
        c = colppy_by_id[ie]
        h = hubspot_by_id[ie]
        props = h.get("properties", {})
        closedate = (props.get("closedate") or "")[:10]
        lines.append(f"| {ie} | {c.get('plan_name','')} | {_fmt_amt(c.get('importe'))} | {c.get('medioPago','')} | {c.get('cuit_invoicing','')} | {(props.get('dealname') or '')[:50]} | {_fmt_amt(props.get('amount'))} | {closedate} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Colppy Only — Full List")
    lines.append("")
    lines.append("| id_empresa | plan_name | fechaPago | importe | medioPago | cuit_invoicing |")
    lines.append("|------------|-----------|-----------|---------|-----------|----------------|")
    for ie in sorted(colppy_only, key=lambda x: int(x) if x.isdigit() else 0):
        c = colppy_by_id[ie]
        lines.append(f"| {ie} | {c.get('plan_name','')} | {c.get('fechaPago','')} | {_fmt_amt(c.get('importe'))} | {c.get('medioPago','')} | {c.get('cuit_invoicing','')} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## HubSpot Only — Full List")
    lines.append("")
    lines.append("| id_empresa | dealname | amount | closedate |")
    lines.append("|------------|----------|--------|-----------|")
    for ie in sorted(hubspot_only, key=lambda x: int(x) if x.isdigit() else 0):
        h = hubspot_by_id[ie]
        props = h.get("properties", {})
        closedate = (props.get("closedate") or "")[:10]
        lines.append(f"| {ie} | {(props.get('dealname') or '')[:60]} | {_fmt_amt(props.get('amount'))} | {closedate} |")
    lines.append("")

    report = "\n".join(lines)
    print(report)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\nFull report written to: {out}")

    # Log to SQLite for progress tracking
    if db_path:
        snapshot_meta = {}
        try:
            with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                snap = json.load(f)
            if snap.get("metadata"):
                snapshot_meta = {"colppy_exported_at": snap["metadata"].get("exported_at")}
        except Exception:
            pass
        log_reconciliation(
            db_path=db_path,
            script="reconcile_colppy_hubspot",
            reconciliation_type="colppy_first_payments_hubspot_closedwon",
            period=month_key,
            match_count=len(match_ids),
            source_a_total=len(colppy_ids),
            source_b_total=len(hubspot_ids),
            source_a_only_count=len(colppy_only),
            source_b_only_count=len(hubspot_only),
            match_ids=sorted(match_ids, key=lambda x: int(x) if x.isdigit() else 0),
            source_a_only_ids=sorted(colppy_only, key=lambda x: int(x) if x.isdigit() else 0),
            source_b_only_ids=sorted(hubspot_only, key=lambda x: int(x) if x.isdigit() else 0),
            source_metadata=snapshot_meta,
        )
        print(f"\nReconciliation logged to {db_path}")


def main():
    parser = argparse.ArgumentParser(description="Colppy First Payments ↔ HubSpot Closed Won reconciliation")
    parser.add_argument("--year", type=str, required=True, help="Year (e.g. 2026)")
    parser.add_argument("--month", type=int, required=True, help="Month 1-12")
    parser.add_argument("--output", "-o", type=str, help="Write full report to file")
    parser.add_argument(
        "--db",
        type=str,
        default=str(REPO_ROOT / "tools/data/facturacion_hubspot.db"),
        help="SQLite DB path for reconciliation logs (default: tools/data/facturacion_hubspot.db)",
    )
    parser.add_argument("--no-log", action="store_true", help="Skip logging to SQLite")
    args = parser.parse_args()
    run(args.year, args.month, output_path=args.output, db_path=None if args.no_log else args.db)


if __name__ == "__main__":
    main()
