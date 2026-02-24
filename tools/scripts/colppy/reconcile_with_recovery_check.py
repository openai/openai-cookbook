#!/usr/bin/env python3
"""
Colppy ↔ HubSpot Reconciliation with Recovery Check
====================================================
Same as reconcile_colppy_hubspot_db_only.py, but for HubSpot-only deals:
1. Fetches deal history from HubSpot API and classifies (fresh_close, old_deal_date_correction, slow_close)
2. Flags old_deal_date_correction as potential_recovered
3. Checks Colppy for recurring payments (primerPago=0) in that month
4. If found: recovered_confirmed

Requires: HUBSPOT_API_KEY, colppy_export.db (with full pago table for recurring payments).

Usage:
  python tools/scripts/colppy/reconcile_with_recovery_check.py --year 2026 --month 2
  python tools/scripts/colppy/reconcile_with_recovery_check.py --year 2026 --month 2 --output report.md
"""
import argparse
import calendar
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

DEFAULT_COLPPY_DB = REPO_ROOT / "tools/data/colppy_export.db"
DEFAULT_HUBSPOT_DB = REPO_ROOT / "tools/data/facturacion_hubspot.db"
ACTIVE_DEAL_STAGES = ("closedwon", "34692158")
CLOSEDWON_STAGES = {"closedwon", "34692158"}
DATE_CORRECTION_DAYS = 180
HUBSPOT_BASE_URL = "https://api.hubapi.com"


def _parse_date(value: str) -> Optional[Any]:
    from datetime import datetime

    if not value or not str(value).strip() or str(value).strip().lower() == "null":
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def load_colppy_first_payments(colppy_db: Path, year: str, month: int) -> list[dict]:
    """Load Colppy first payments for given month."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    conn = sqlite3.connect(str(colppy_db))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT p.idPago, p.idEmpresa, p.idPlan, pl.nombre AS plan_name, p.fechaPago,
               COALESCE(pd.accreditation_date, pd.payment_date) AS payment_datetime,
               p.importe, p.medioPago, p.tipoPago, f.CUIT AS cuit_invoicing
        FROM pago p
        LEFT JOIN plan pl ON pl.idPlan = p.idPlan
        LEFT JOIN payment_detail pd ON pd.payment_id = p.idPago AND pd.is_first_payment = 1
        LEFT JOIN facturacion f ON f.IdEmpresa = p.idEmpresa AND (f.fechaBaja IS NULL OR f.fechaBaja = '')
        WHERE p.primerPago = 1
          AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
          AND p.fechaPago >= ? AND p.fechaPago < date(?, '+1 day')
        ORDER BY p.fechaPago
        """,
        (start, end),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def load_colppy_recurring_payments(
    colppy_db: Path, year: str, month: int, id_empresas: list[str]
) -> dict[str, list[dict]]:
    """Load Colppy recurring payments (primerPago=0) for given month and id_empresas."""
    if not id_empresas:
        return {}
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    # Use int for idEmpresa (colppy_export stores as integer)
    params = [int(x) if str(x).isdigit() else x for x in id_empresas]
    conn = sqlite3.connect(str(colppy_db))
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(params))
    cur = conn.execute(
        f"""
        SELECT p.idPago, p.idEmpresa, p.fechaPago, p.importe, p.medioPago, pl.nombre AS plan_name
        FROM pago p
        LEFT JOIN plan pl ON pl.idPlan = p.idPlan
        WHERE p.primerPago = 0
          AND p.idEmpresa IN ({placeholders})
          AND p.fechaPago >= ? AND p.fechaPago <= ?
          AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
        ORDER BY p.idEmpresa, p.fechaPago
        """,
        (*params, start, end),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    by_id: dict[str, list[dict]] = {}
    for r in rows:
        ie = str(r["idEmpresa"])
        by_id.setdefault(ie, []).append(r)
    return by_id


def load_hubspot_closed_won(hubspot_db: Path, year: str, month: int) -> list[dict]:
    """Load HubSpot closed won from DB."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    conn = sqlite3.connect(str(hubspot_db))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date
        FROM deals
        WHERE deal_stage IN (?, ?) AND close_date >= ? AND close_date <= ?
        ORDER BY close_date
        """,
        (*ACTIVE_DEAL_STAGES, start, end),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def fetch_deal_classification(deal_id: str, api_key: str) -> Optional[str]:
    """Fetch deal from HubSpot and return classification: fresh_close, old_deal_date_correction, slow_close."""
    url = f"{HUBSPOT_BASE_URL}/crm/v3/objects/deals/{deal_id}"
    params = {
        "properties": "createdate,closedate",
        "propertiesWithHistory": "closedate,dealstage",
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException:
        return None

    props = data.get("properties", {})
    hist = data.get("propertiesWithHistory", {})
    createdate = _parse_date(props.get("createdate"))
    closedate = _parse_date(props.get("closedate"))
    if not closedate:
        return "unknown"

    first_closedwon: Optional[Any] = None
    stage_hist = hist.get("dealstage")
    if stage_hist:
        versions = stage_hist if isinstance(stage_hist, list) else stage_hist.get("versions", [])
        closedwon_times = []
        for v in versions:
            val = (v.get("value") or "").strip()
            if val in CLOSEDWON_STAGES:
                ts = v.get("timestamp")
                if ts:
                    dt = _parse_date(ts)
                    if dt:
                        closedwon_times.append(dt)
        if closedwon_times:
            first_closedwon = min(closedwon_times)
    if not first_closedwon:
        closedate_hist = hist.get("closedate")
        if closedate_hist:
            versions = closedate_hist if isinstance(closedate_hist, list) else closedate_hist.get("versions", [])
            valid = [_parse_date(v.get("value")) for v in versions if v.get("value")]
            valid = [d for d in valid if d]
            if valid:
                first_closedwon = min(valid)
    if not first_closedwon:
        first_closedwon = closedate

    close_diff_days = (closedate - first_closedwon).days if (closedate and first_closedwon) else 0
    create_to_close_days = (first_closedwon - createdate).days if (createdate and first_closedwon) else 0

    if close_diff_days > DATE_CORRECTION_DAYS:
        return "old_deal_date_correction"
    if create_to_close_days > 180:
        return "slow_close"
    return "fresh_close"


def _fmt_amt(x) -> str:
    try:
        return f"${float(x):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(x)


def run(
    year: str,
    month: int,
    colppy_db: Path,
    hubspot_db: Path,
    output_path: Optional[str] = None,
    delay: float = 0.2,
) -> None:
    """Run reconciliation with recovery check."""
    api_key = os.getenv("HUBSPOT_API_KEY") or os.getenv("ColppyCRMAutomations")
    if not api_key:
        print("❌ HUBSPOT_API_KEY or ColppyCRMAutomations required for recovery check", file=sys.stderr)
        sys.exit(1)

    month_key = f"{year}-{month:02d}"
    print(f"Colppy ↔ HubSpot Reconciliation with Recovery Check — {month_key}")
    print("=" * 70)

    colppy = load_colppy_first_payments(colppy_db, year, month)
    colppy_by_id = {str(r["idEmpresa"]): r for r in colppy}
    colppy_ids = set(colppy_by_id.keys())
    print(f"Colppy first payments: {len(colppy):,} ({len(colppy_ids):,} unique id_empresa)")

    hubspot = load_hubspot_closed_won(hubspot_db, year, month)
    hubspot_by_id = {str(r["id_empresa"]): r for r in hubspot}
    hubspot_ids = set(hubspot_by_id.keys())
    print(f"HubSpot closed won: {len(hubspot):,} ({len(hubspot_ids):,} unique id_empresa)")

    match_ids = colppy_ids & hubspot_ids
    colppy_only = colppy_ids - hubspot_ids
    hubspot_only = sorted(hubspot_ids - colppy_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # For HubSpot-only: classify and check Colppy recurring
    hubspot_only_classified: list[dict] = []
    if hubspot_only:
        print(f"\nClassifying {len(hubspot_only)} HubSpot-only deals (API)...")
        recurring_by_id = load_colppy_recurring_payments(colppy_db, year, month, hubspot_only)
        for i, ie in enumerate(hubspot_only):
            if (i + 1) % 5 == 0 or i == 0:
                print(f"  {i + 1}/{len(hubspot_only)}...", flush=True)
            h = hubspot_by_id[ie]
            hubspot_id = h.get("hubspot_id", "")
            classification = fetch_deal_classification(hubspot_id, api_key) if hubspot_id else "unknown"
            potential_recovered = classification == "old_deal_date_correction"
            recurring = recurring_by_id.get(ie, [])
            recovered_confirmed = potential_recovered and len(recurring) > 0
            hubspot_only_classified.append({
                "id_empresa": ie,
                "deal_name": h.get("deal_name", ""),
                "amount": h.get("amount", ""),
                "close_date": (h.get("close_date") or "")[:10],
                "classification": classification or "unknown",
                "potential_recovered": potential_recovered,
                "recovered_confirmed": recovered_confirmed,
                "colppy_recurring_count": len(recurring),
                "colppy_recurring": recurring,
            })
            time.sleep(delay)

    # Build report
    lines = []
    lines.append(f"# {month_key}: Colppy First Payments ↔ HubSpot Closed Won (with Recovery Check)")
    lines.append("")
    lines.append("**Sources:** colppy_export.db | facturacion_hubspot.db | HubSpot API")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| MATCH (in both) | {len(match_ids)} |")
    lines.append(f"| Colppy only | {len(colppy_only)} |")
    lines.append(f"| HubSpot only | {len(hubspot_only)} |")
    recovered_confirmed_count = sum(1 for r in hubspot_only_classified if r["recovered_confirmed"])
    potential_count = sum(1 for r in hubspot_only_classified if r["potential_recovered"])
    lines.append(f"| → Potential recovered (old deal) | {potential_count} |")
    lines.append(f"| → Recovered confirmed (Colppy payment) | {recovered_confirmed_count} |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## MATCH — Full List")
    lines.append("")
    lines.append("| id_empresa | Colppy plan | Colppy importe | HubSpot deal | HubSpot amount | close_date |")
    lines.append("|------------|-------------|---------------|--------------|----------------|-----------|")
    for ie in sorted(match_ids, key=lambda x: int(x) if x.isdigit() else 0):
        c = colppy_by_id[ie]
        h = hubspot_by_id[ie]
        lines.append(f"| {ie} | {c.get('plan_name','')} | {_fmt_amt(c.get('importe'))} | {(h.get('deal_name') or '')[:40]} | {_fmt_amt(h.get('amount'))} | {(h.get('close_date') or '')[:10]} |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Colppy Only — Full List")
    lines.append("")
    lines.append("| id_empresa | plan_name | fechaPago | importe | medioPago |")
    lines.append("|------------|-----------|-----------|---------|-----------|")
    for ie in sorted(colppy_only, key=lambda x: int(x) if x.isdigit() else 0):
        c = colppy_by_id[ie]
        lines.append(f"| {ie} | {c.get('plan_name','')} | {c.get('fechaPago','')} | {_fmt_amt(c.get('importe'))} | {c.get('medioPago','')} |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## HubSpot Only — With Recovery Check")
    lines.append("")
    lines.append("| id_empresa | deal_name | amount | close_date | classification | potential_recovered | recovered_confirmed | Colppy recurring |")
    lines.append("|------------|-----------|--------|-----------|----------------|---------------------|---------------------|------------------|")
    for r in hubspot_only_classified:
        rec = f"{len(r['colppy_recurring'])} pago(s)" if r["colppy_recurring"] else "—"
        lines.append(
            f"| {r['id_empresa']} | {(r['deal_name'] or '')[:35]} | {_fmt_amt(r['amount'])} | {r['close_date']} | "
            f"{r['classification']} | {'✓' if r['potential_recovered'] else ''} | {'✓' if r['recovered_confirmed'] else ''} | {rec} |"
        )
    lines.append("")

    report = "\n".join(lines)
    print(report)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        print(f"\nReport written to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconciliation with recovery check (HubSpot API + Colppy recurring)")
    parser.add_argument("--year", type=str, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--colppy-db", default=str(DEFAULT_COLPPY_DB))
    parser.add_argument("--hubspot-db", default=str(DEFAULT_HUBSPOT_DB))
    parser.add_argument("--output", "-o", type=str)
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args()

    run(
        args.year,
        args.month,
        Path(args.colppy_db),
        Path(args.hubspot_db),
        output_path=args.output,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
