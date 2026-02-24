#!/usr/bin/env python3
"""
First payments by product (new product sales) in a date range.

Queries Colppy MySQL pago table for primerPago=1 (first payment per company)
and joins plan for product name. For CBU payments, includes accreditation_date
from payment_detail when available (datetime precision).

Usage:
  python tools/scripts/colppy/first_payments_by_product.py --start 2026-02-01 --end 2026-02-28
  python tools/scripts/colppy/first_payments_by_product.py  # defaults to current month
"""

import argparse
import calendar
import sys
from datetime import date
from pathlib import Path

# Add tools to path for database import
tools_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(tools_dir))

from dotenv import load_dotenv
load_dotenv(tools_dir / ".env")

from database import get_db


def query_first_payments(start_date: str, end_date: str) -> list[dict]:
    """
    First payments (primerPago=1) in date range with product and datetime when available.

    Returns list of dicts: idPago, idEmpresa, idPlan, plan_name, fechaPago, payment_datetime,
    importe, medioPago, tipoPago.
    """
    query = """
    SELECT
        p.idPago,
        p.idEmpresa,
        p.idPlan,
        pl.nombre AS plan_name,
        pl.tipo AS plan_tipo,
        p.fechaPago,
        COALESCE(pd.accreditation_date, pd.payment_date) AS payment_datetime,
        p.importe,
        p.medioPago,
        p.tipoPago,
        p.nroOperacion
    FROM pago p
    LEFT JOIN plan pl ON pl.idPlan = p.idPlan
    LEFT JOIN payment_detail pd ON pd.payment_id = p.idPago AND pd.is_first_payment = 1
    WHERE p.primerPago = 1
      AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
      AND p.fechaPago BETWEEN :start_date AND :end_date
    ORDER BY p.fechaPago, payment_datetime, p.idPago
    """
    db = get_db()
    return db.execute_query(query, {"start_date": start_date, "end_date": end_date})


def main():
    today = date.today()
    start_default = today.replace(day=1).strftime("%Y-%m-%d")
    last_day = calendar.monthrange(today.year, today.month)[1]
    end_default = today.replace(day=last_day).strftime("%Y-%m-%d")

    parser = argparse.ArgumentParser(
        description="First payments by product (new product sales) in date range"
    )
    parser.add_argument(
        "--start",
        default=start_default,
        help=f"Start date (YYYY-MM-DD). Default: first day of current month ({start_default})",
    )
    parser.add_argument(
        "--end",
        default=end_default,
        help=f"End date (YYYY-MM-DD). Default: last day of current month ({end_default})",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output as CSV",
    )
    args = parser.parse_args()

    rows = query_first_payments(args.start, args.end)

    if args.csv:
        if not rows:
            print("idPago,idEmpresa,idPlan,plan_name,plan_tipo,fechaPago,payment_datetime,importe,medioPago,tipoPago,nroOperacion")
            return
        cols = list(rows[0].keys())
        print(",".join(cols))
        for r in rows:
            vals = [str(r.get(c, "")) for c in cols]
            print(",".join(vals))
        return

    # Human-readable output
    print(f"First payments (new product sales) {args.start} to {args.end}")
    print(f"Total: {len(rows)} records\n")

    if not rows:
        print("No first payments in this period.")
        return

    # Group by product (plan)
    by_plan: dict[int, list] = {}
    for r in rows:
        pid = r.get("idPlan") or 0
        if pid not in by_plan:
            by_plan[pid] = []
        by_plan[pid].append(r)

    for id_plan in sorted(by_plan.keys()):
        items = by_plan[id_plan]
        plan_name = items[0].get("plan_name") or "(unknown)"
        plan_tipo = items[0].get("plan_tipo") or ""
        print(f"--- {plan_name} (idPlan={id_plan}, tipo={plan_tipo}) ---")
        for r in items:
            dt = r.get("payment_datetime")
            dt_str = str(dt)[:19] if dt else str(r.get("fechaPago", ""))
            print(
                f"  {dt_str} | idEmpresa={r.get('idEmpresa')} | "
                f"${float(r.get('importe') or 0):,.2f} | {r.get('medioPago') or ''}"
            )
        print()


if __name__ == "__main__":
    main()
