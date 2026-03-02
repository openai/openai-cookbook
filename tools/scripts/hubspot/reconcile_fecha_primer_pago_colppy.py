#!/usr/bin/env python3
"""
Reconcile HubSpot fecha_primer_pago vs Colppy First Payment
===========================================================
Compares deal.fecha_primer_pago (HubSpot) with pago.fechaPago (Colppy DB)
for closed won deals in a given month. Match by id_empresa.

Amount reconciliation: Colppy amounts (pago.importe, plan.precio) are CON IVA (21%).
HubSpot deal amount is SIN IVA. When comparing: Colppy_importe / 1.21 ≈ HubSpot_amount.

Usage:
  python tools/scripts/hubspot/reconcile_fecha_primer_pago_colppy.py --month 2026-02
  python tools/scripts/hubspot/reconcile_fecha_primer_pago_colppy.py --start 2026-02-01 --end 2026-02-29
  python tools/scripts/hubspot/reconcile_fecha_primer_pago_colppy.py --month 2026-02 --local  # use colppy_export.db
"""

import argparse
import os
import sqlite3
import sys
import time
from calendar import monthrange
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

HUBSPOT_PORTAL_ID = "19877595"
API_KEY = (
    os.getenv("HUBSPOT_API_KEY")
    or os.getenv("COLPPY_CRM_AUTOMATIONS")
    or os.getenv("ColppyCRMAutomations")
)
if not API_KEY:
    print("Error: HUBSPOT_API_KEY (or COLPPY_CRM_AUTOMATIONS) not found in .env")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
BASE_URL = "https://api.hubapi.com"
RATE_LIMIT_DELAY = float(os.getenv("HUBSPOT_RATE_LIMIT_DELAY", "0.5"))
DEFAULT_LOCAL_DB = "tools/data/colppy_export.db"

# Colppy amounts are con IVA (21%); HubSpot deal amount is sin IVA.
# Compare: Colppy_importe / IVA_RATE ≈ HubSpot_amount
IVA_RATE = 1.21  # Argentina 21% IVA
AMOUNT_TOLERANCE = 1.0  # Allow 1 peso difference for rounding


def fetch_deals_closed_won(start_date: str, end_date: str) -> list[dict]:
    """Fetch HubSpot deals closed won in period with id_empresa and fecha_primer_pago."""
    url = f"{BASE_URL}/crm/v3/objects/deals/search"
    all_deals = []
    after = None
    props = [
        "dealname",
        "id_empresa",
        "amount",
        "closedate",
        "fecha_primer_pago",
        "hs_object_id",
    ]
    while True:
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"},
                        {"propertyName": "closedate", "operator": "GTE", "value": f"{start_date}T00:00:00.000Z"},
                        {"propertyName": "closedate", "operator": "LTE", "value": f"{end_date}T23:59:59.999Z"},
                    ]
                }
            ],
            "properties": props,
            "limit": 100,
        }
        if after:
            payload["after"] = after
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"Error: {resp.status_code} {resp.text}")
            break
        data = resp.json()
        results = data.get("results", [])
        all_deals.extend(results)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        time.sleep(RATE_LIMIT_DELAY)
    return all_deals


def query_first_payment_medio_by_empresas(
    id_empresas: list[str], db_path: str
) -> dict[str, dict]:
    """First payment (any period) per id_empresa for medioPago lookup. Returns {id_empresa: {medioPago, fechaPago}}."""
    if not id_empresas:
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(id_empresas))
    cur = conn.execute(
        f"""
        SELECT p.idEmpresa, p.medioPago, p.fechaPago
        FROM pago p
        WHERE p.primerPago = 1
          AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
          AND p.idEmpresa IN ({placeholders})
        ORDER BY p.idEmpresa, p.fechaPago, p.idPago
        """,
        id_empresas,
    )
    rows = cur.fetchall()
    conn.close()
    out = {}
    for r in rows:
        ie = str(r["idEmpresa"])
        if ie not in out:
            out[ie] = {"medioPago": r["medioPago"], "fechaPago": r["fechaPago"]}
    return out


def query_first_payments_local(start_date: str, end_date: str, db_path: str) -> list[dict]:
    """First payments from colppy_export.db for date range."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT
            p.idPago,
            p.idEmpresa,
            p.idPlan,
            pl.nombre AS plan_name,
            p.fechaPago,
            p.importe,
            p.medioPago
        FROM pago p
        LEFT JOIN plan pl ON pl.idPlan = p.idPlan
        WHERE p.primerPago = 1
          AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
          AND p.fechaPago >= ?
          AND p.fechaPago < date(?, '+1 day')
        ORDER BY p.fechaPago, p.idPago
        """,
        (start_date, end_date),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def run_reconciliation(
    start_date: str,
    end_date: str,
    use_local: bool = True,
    local_db_path: str = DEFAULT_LOCAL_DB,
) -> None:
    """Run reconciliation and print report."""
    db_path = Path(local_db_path)
    if not db_path.exists():
        print(f"Error: colppy_export.db not found at {db_path}")
        print("Run: cd plugins/colppy-revops && ./publish.sh --refresh")
        sys.exit(1)

    print("Fetching HubSpot closed won deals...")
    deals = fetch_deals_closed_won(start_date, end_date)
    print(f"HubSpot: {len(deals)} closed won deals in {start_date} to {end_date}")

    print("Querying Colppy first payments...")
    colppy_payments = query_first_payments_local(start_date, end_date, str(db_path))
    colppy_by_ie = {str(p["idEmpresa"]): p for p in colppy_payments}
    print(f"Colppy:  {len(colppy_payments)} first payments in period")

    # Build deal list with id_empresa (dedupe by id_empresa, keep first)
    deals_by_ie = {}
    for d in deals:
        props = d.get("properties", {})
        ie = (props.get("id_empresa") or "").strip()
        if ie and ie not in deals_by_ie:
            deals_by_ie[ie] = d

    # Match and compare
    match_date_ok = []
    match_date_diff = []
    hubspot_only = []
    colppy_only = []

    for ie, deal in deals_by_ie.items():
        props = deal.get("properties", {})
        fecha_hs = (props.get("fecha_primer_pago") or "").strip()[:10] or None
        colppy = colppy_by_ie.get(ie)

        if colppy:
            fecha_colppy = (colppy.get("fechaPago") or "")[:10] if colppy.get("fechaPago") else None
            if fecha_hs and fecha_colppy:
                if fecha_hs == fecha_colppy:
                    match_date_ok.append((deal, colppy))
                else:
                    match_date_diff.append((deal, colppy))
            else:
                match_date_diff.append((deal, colppy))  # one or both missing date
            del colppy_by_ie[ie]
        else:
            hubspot_only.append(deal)

    colppy_only = list(colppy_by_ie.values())

    # Report
    print()
    print("=" * 100)
    print(f"Reconciliation: fecha_primer_pago (HubSpot) vs fechaPago (Colppy) | {start_date} to {end_date}")
    print("=" * 100)
    print()
    print(f"  MATCH (same id_empresa, same date):     {len(match_date_ok)}")
    print(f"  MATCH (same id_empresa, date diff):     {len(match_date_diff)}")
    print(f"  HubSpot only (no Colppy first payment): {len(hubspot_only)}")
    print(f"  Colppy only (no HubSpot deal):          {len(colppy_only)}")
    print()

    def _amt(p):
        try:
            return float(p.get("amount") or 0)
        except (TypeError, ValueError):
            return 0

    def _link(deal_id: str) -> str:
        return f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL_ID}/deal/{deal_id}"

    if match_date_ok:
        print("--- MATCH (same date) ---")
        for deal, colppy in match_date_ok[:15]:
            props = deal.get("properties", {})
            name = (props.get("dealname") or "")[:40]
            ie = props.get("id_empresa", "")
            fecha = (props.get("fecha_primer_pago") or "")[:10]
            link = _link(deal["id"])
            print(f"  [{ie}] {name} | fecha_primer_pago={fecha} | [{name}]({link})")
        if len(match_date_ok) > 15:
            print(f"  ... and {len(match_date_ok) - 15} more")

    if match_date_diff:
        print()
        print("--- MATCH (date diff) ---")
        for deal, colppy in match_date_diff[:15]:
            props = deal.get("properties", {})
            name = (props.get("dealname") or "")[:35]
            ie = props.get("id_empresa", "")
            fecha_hs = (props.get("fecha_primer_pago") or "").strip()[:10] or "(empty)"
            fecha_colppy = (colppy.get("fechaPago") or "")[:10] if colppy.get("fechaPago") else "(empty)"
            medio = (colppy.get("medioPago") or "").strip() or "(n/a)"
            link = _link(deal["id"])
            print(f"  [{ie}] {name} | HS:{fecha_hs} vs Colppy:{fecha_colppy} | medioPago={medio} | [{name}]({link})")
        if len(match_date_diff) > 15:
            print(f"  ... and {len(match_date_diff) - 15} more")

    if hubspot_only:
        print()
        print("--- HubSpot only (no Colppy first payment in period) ---")
        ie_list = list(
            dict.fromkeys(
                (d.get("properties", {}).get("id_empresa") or "").strip()
                for d in hubspot_only
            )
        )
        ie_list = [x for x in ie_list if x]
        medio_lookup = query_first_payment_medio_by_empresas(ie_list, str(db_path))
        for deal in sorted(hubspot_only, key=lambda d: -_amt(d.get("properties", {})))[:15]:
            props = deal.get("properties", {})
            name = (props.get("dealname") or "")[:40]
            ie = (props.get("id_empresa") or "").strip()
            fecha = (props.get("fecha_primer_pago") or "").strip()[:10] or "(empty)"
            amt = _amt(props)
            link = _link(deal["id"])
            fp = medio_lookup.get(ie, {})
            medio = (fp.get("medioPago") or "").strip() or "(n/a)"
            print(f"  [{ie}] {name} | fecha_primer_pago={fecha} | medioPago={medio} | ${amt:,.0f} | [{name}]({link})")
        if len(hubspot_only) > 15:
            print(f"  ... and {len(hubspot_only) - 15} more")

    if colppy_only:
        print()
        print("--- Colppy only (no HubSpot deal closed won in period) ---")
        for p in colppy_only[:15]:
            ie = str(p.get("idEmpresa", ""))
            plan = (p.get("plan_name") or "")[:30]
            fecha = (p.get("fechaPago") or "")[:10]
            importe = p.get("importe", 0)
            medio = (p.get("medioPago") or "").strip() or "(n/a)"
            print(f"  [{ie}] plan={plan} | fechaPago={fecha} | medioPago={medio} | importe={importe}")
        if len(colppy_only) > 15:
            print(f"  ... and {len(colppy_only) - 15} more")

    # Amount reconciliation (IVA-adjusted): Colppy con IVA / 1.21 ≈ HubSpot sin IVA
    all_matched = match_date_ok + match_date_diff
    amount_ok = []
    amount_diff = []
    amount_skip = []  # one or both amounts missing/zero
    for deal, colppy in all_matched:
        props = deal.get("properties", {})
        hs_amt = _amt(props)
        try:
            colppy_importe = float(colppy.get("importe") or 0)
        except (TypeError, ValueError):
            colppy_importe = 0.0
        if hs_amt <= 0 and colppy_importe <= 0:
            amount_skip.append((deal, colppy, "both zero/empty"))
        elif hs_amt <= 0:
            amount_skip.append((deal, colppy, "HubSpot amount empty"))
        elif colppy_importe <= 0:
            amount_skip.append((deal, colppy, "Colppy importe empty"))
        else:
            colppy_sin_iva = colppy_importe / IVA_RATE
            diff = abs(colppy_sin_iva - hs_amt)
            if diff <= AMOUNT_TOLERANCE:
                amount_ok.append((deal, colppy, hs_amt, colppy_importe, colppy_sin_iva))
            else:
                amount_diff.append((deal, colppy, hs_amt, colppy_importe, colppy_sin_iva, diff))

    print()
    print("--- Amount reconciliation (IVA-adjusted) ---")
    print(f"  Colppy amounts are con IVA (21%); HubSpot deal amount is sin IVA.")
    print(f"  Compare: Colppy_importe / {IVA_RATE} ≈ HubSpot_amount (tolerance: ±${AMOUNT_TOLERANCE:,.0f})")
    print()
    print(f"  Amount MATCH (within tolerance):  {len(amount_ok)}")
    print(f"  Amount DIFF (beyond tolerance):  {len(amount_diff)}")
    print(f"  Skipped (missing/zero amount):   {len(amount_skip)}")
    print()

    if amount_ok:
        print("  Amount OK (sample):")
        for deal, colppy, hs_amt, imp, sin_iva in amount_ok[:10]:
            ie = (deal.get("properties", {}).get("id_empresa") or "")[:10]
            name = (deal.get("properties", {}).get("dealname") or "")[:35]
            print(f"    [{ie}] {name} | Colppy con IVA=${imp:,.0f} → sin IVA=${sin_iva:,.0f} | HubSpot=${hs_amt:,.0f}")
        if len(amount_ok) > 10:
            print(f"    ... and {len(amount_ok) - 10} more")

    if amount_diff:
        print()
        print("  Amount DIFF (investigate):")
        for deal, colppy, hs_amt, imp, sin_iva, diff in sorted(amount_diff, key=lambda x: -x[5])[:15]:
            ie = (deal.get("properties", {}).get("id_empresa") or "")[:10]
            name = (deal.get("properties", {}).get("dealname") or "")[:35]
            link = _link(deal["id"])
            print(f"    [{ie}] {name} | Colppy con IVA=${imp:,.0f} → sin IVA=${sin_iva:,.0f} | HubSpot=${hs_amt:,.0f} | diff=${diff:,.0f} | [{name}]({link})")
        if len(amount_diff) > 15:
            print(f"    ... and {len(amount_diff) - 15} more")


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile HubSpot fecha_primer_pago vs Colppy first payment date"
    )
    parser.add_argument("--month", metavar="YYYY-MM", help="Month (e.g. 2026-02)")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--local",
        action="store_true",
        default=True,
        help="Use colppy_export.db (default: True)",
    )
    parser.add_argument(
        "--local-db",
        default=DEFAULT_LOCAL_DB,
        help=f"Path to colppy_export.db (default: {DEFAULT_LOCAL_DB})",
    )
    args = parser.parse_args()

    if args.month:
        parts = args.month.split("-")
        if len(parts) != 2:
            parser.error("--month must be YYYY-MM")
        y, m = int(parts[0]), int(parts[1])
        last = monthrange(y, m)[1]
        start_date = f"{y:04d}-{m:02d}-01"
        end_date = f"{y:04d}-{m:02d}-{last:02d}"
    elif args.start and args.end:
        start_date = args.start
        end_date = args.end
    else:
        parser.error("Provide --month YYYY-MM or both --start and --end")

    run_reconciliation(
        start_date=start_date,
        end_date=end_date,
        use_local=args.local,
        local_db_path=args.local_db,
    )


if __name__ == "__main__":
    main()
