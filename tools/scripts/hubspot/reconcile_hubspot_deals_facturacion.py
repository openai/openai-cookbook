#!/usr/bin/env python3
"""
HubSpot Deals ↔ Billing Reconciliation (DB)
============================================
Reconciles deals in facturacion_hubspot.db with billing (facturacion table from facturacion.csv):
1. Deals ↔ billing by id_empresa (each deal must have a billing row)
2. Deal's PRIMARY company (association type 5) CUIT must match billing.customer_cuit

Uses: deals, deal_associations (type 5 = PRIMARY), companies, facturacion (billing).
Run populate_deal_associations.py first to ensure deal_associations is current.
See tools/docs/DATA_SOURCES_TERMINOLOGY.md for Billing vs HubSpot vs Colppy.

Usage:
  python tools/scripts/hubspot/reconcile_hubspot_deals_facturacion.py --year 2025 --month 11
  python tools/scripts/hubspot/reconcile_hubspot_deals_facturacion.py --year 2025 --month 11 --output tools/outputs/hubspot_facturacion_reconcile_202511.md
  python tools/scripts/hubspot/reconcile_hubspot_deals_facturacion.py  # all deals
"""
import argparse
import calendar
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

DEFAULT_DB = REPO_ROOT / "tools/data/facturacion_hubspot.db"
PRIMARY_ASSOCIATION_TYPE = 5


def _normalize_cuit(cuit: str | None) -> str:
    """Normalize CUIT to 11 digits for comparison."""
    if not cuit:
        return ""
    return "".join(c for c in str(cuit) if c.isdigit())


def _format_cuit(cuit: str | None) -> str:
    """Format CUIT as 30-12345678-9 for display."""
    if not cuit:
        return ""
    digits = _normalize_cuit(cuit)
    if len(digits) != 11:
        return cuit or ""
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"


def run(
    db_path: Path,
    year: str | None = None,
    month: int | None = None,
    output_path: str | None = None,
) -> None:
    """
    Reconcile HubSpot deals with facturacion.
    For each deal: primary company CUIT (from HubSpot) must match facturacion.customer_cuit.
    """
    if not db_path.exists():
        print(f"Error: DB not found: {db_path}")
        return

    month_key = ""
    if year and month:
        month_key = f"{year}-{month:02d}"
        start = f"{year}-{month:02d}-01"
        last_day = calendar.monthrange(int(year), month)[1]
        end = f"{year}-{month:02d}-{last_day}"
        date_filter = "AND d.close_date >= ? AND d.close_date <= ?"
        date_params = (start, end)
    else:
        date_filter = ""
        date_params = ()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    query = f"""
        SELECT
            d.id_empresa,
            d.hubspot_id,
            d.deal_name,
            d.close_date,
            da.company_hubspot_id AS primary_company_hs_id,
            c.cuit AS hubspot_primary_cuit,
            f.customer_cuit AS facturacion_cuit,
            f.plan AS facturacion_plan
        FROM deals d
        LEFT JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
        LEFT JOIN companies c ON c.hubspot_id = da.company_hubspot_id
        LEFT JOIN facturacion f ON f.id_empresa = d.id_empresa
        WHERE d.deal_stage IN ('closedwon', '34692158')
        {date_filter}
        ORDER BY d.id_empresa
    """
    cur = conn.execute(query, date_params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        print(f"No closed-won deals found{f' for {month_key}' if month_key else ''}.")
        return

    match = []
    mismatch = []
    no_primary = []
    no_facturacion = []
    no_cuit = []

    for r in rows:
        hs_cuit = _normalize_cuit(r.get("hubspot_primary_cuit"))
        fact_cuit = _normalize_cuit(r.get("facturacion_cuit"))

        if not r.get("primary_company_hs_id"):
            no_primary.append(r)
        elif not hs_cuit:
            no_cuit.append(r)
        elif not r.get("facturacion_cuit") or not fact_cuit:
            no_facturacion.append(r)
        elif hs_cuit == fact_cuit:
            match.append(r)
        else:
            mismatch.append(r)

    # Report
    lines = []
    title = f"HubSpot Deals ↔ Facturacion Reconciliation"
    if month_key:
        title += f" — {month_key}"
    lines.append(f"# {title}")
    lines.append("")
    lines.append("**Logic:** For each deal, the PRIMARY company (association type 5) CUIT must match billing.customer_cuit for that id_empresa.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| MATCH (HubSpot primary CUIT = facturacion.customer_cuit) | {len(match)} |")
    lines.append(f"| MISMATCH (CUIT differs) | {len(mismatch)} |")
    lines.append(f"| NO_PRIMARY (no type 5 association) | {len(no_primary)} |")
    lines.append(f"| NO_FACTURACION (id_empresa not in facturacion) | {len(no_facturacion)} |")
    lines.append(f"| NO_CUIT (primary company has no CUIT) | {len(no_cuit)} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    if mismatch:
        lines.append("## MISMATCH — HubSpot primary CUIT ≠ facturacion.customer_cuit")
        lines.append("")
        lines.append("| id_empresa | deal_name | HubSpot primary CUIT | facturacion.customer_cuit |")
        lines.append("|------------|-----------|----------------------|---------------------------|")
        for r in sorted(mismatch, key=lambda x: int(x["id_empresa"]) if str(x["id_empresa"]).isdigit() else 0):
            lines.append(f"| {r['id_empresa']} | {(r.get('deal_name') or '')[:40]} | {_format_cuit(r.get('hubspot_primary_cuit'))} | {_format_cuit(r.get('facturacion_cuit'))} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    if no_primary:
        lines.append("## NO_PRIMARY — Deal has no PRIMARY (type 5) company association")
        lines.append("")
        lines.append("| id_empresa | deal_name | close_date |")
        lines.append("|------------|-----------|------------|")
        for r in sorted(no_primary, key=lambda x: int(x["id_empresa"]) if str(x["id_empresa"]).isdigit() else 0):
            lines.append(f"| {r['id_empresa']} | {(r.get('deal_name') or '')[:40]} | {(r.get('close_date') or '')[:10]} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    if no_facturacion:
        lines.append("## NO_FACTURACION — id_empresa not in facturacion table")
        lines.append("")
        lines.append("| id_empresa | deal_name | HubSpot primary CUIT |")
        lines.append("|------------|-----------|----------------------|")
        for r in sorted(no_facturacion, key=lambda x: int(x["id_empresa"]) if str(x["id_empresa"]).isdigit() else 0):
            lines.append(f"| {r['id_empresa']} | {(r.get('deal_name') or '')[:40]} | {_format_cuit(r.get('hubspot_primary_cuit'))} |")
        lines.append("")

    report = "\n".join(lines)
    print(report)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\nReport written to: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile HubSpot deals with facturacion (id_empresa, primary CUIT)")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to facturacion_hubspot.db")
    parser.add_argument("--year", type=str, help="Year for timeframe filter (e.g. 2025)")
    parser.add_argument("--month", type=int, help="Month 1-12 for timeframe filter")
    parser.add_argument("--output", type=str, help="Output path for report file")
    args = parser.parse_args()

    if (args.year and not args.month) or (args.month and not args.year):
        parser.error("--year and --month must be specified together")
        return 1

    run(
        db_path=Path(args.db),
        year=args.year,
        month=args.month,
        output_path=args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
