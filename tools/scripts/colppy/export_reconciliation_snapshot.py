#!/usr/bin/env python3
"""
Export Colppy Snapshots for Plugin
==================================
Reads from local colppy_export.db and exports:
1. First payments by month (for HubSpot closed won reconciliation)
2. Colppy facturacion / billing (for facturacion.csv reconciliation)

Use when VPN/MySQL is unavailable. Snapshots are bundled in the plugin.

Usage:
  python tools/scripts/colppy/export_reconciliation_snapshot.py
  python tools/scripts/colppy/export_reconciliation_snapshot.py --months 62
"""

import argparse
import json
import re
import sqlite3
import sys
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = REPO_ROOT / "tools/data/colppy_export.db"
DEFAULT_OUTPUT = REPO_ROOT / "plugins/colppy-ceo-assistant/docs/colppy_first_payments_snapshot.json"
EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}


def normalize_cuit(raw: str) -> str:
    """Normalize CUIT to 11 digits or empty."""
    if not raw or str(raw).strip().upper() in ("#N/A", "N/A", ""):
        return ""
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    if len(digits) != 11 or not digits.isdigit() or digits in EXCLUDE_CUITS:
        return ""
    return digits


def query_first_payments(db_path: Path, start_date: str, end_date: str) -> list[dict]:
    """First payments from SQLite for date range."""
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
            p.medioPago,
            f.CUIT AS cuit_invoicing
        FROM pago p
        LEFT JOIN plan pl ON pl.idPlan = p.idPlan
        LEFT JOIN payment_detail pd ON pd.payment_id = p.idPago AND pd.is_first_payment = 1
        LEFT JOIN facturacion f ON f.IdEmpresa = p.idEmpresa AND (f.fechaBaja IS NULL OR f.fechaBaja = '' OR f.fechaBaja = '0000-00-00')
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


def query_colppy_facturacion(db_path: Path) -> list[dict]:
    """Active Colppy billing (facturacion + empresa + plan, fechaBaja IS NULL)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT
            f.IdEmpresa AS id_empresa,
            f.CUIT AS customer_cuit_raw,
            e.CUIT AS product_cuit_raw,
            f.email,
            f.razonSocial,
            e.idPlan AS id_plan,
            p.nombre AS plan,
            p.precio AS amount
        FROM facturacion f
        LEFT JOIN empresa e ON e.IdEmpresa = f.IdEmpresa
        LEFT JOIN plan p ON p.idPlan = e.idPlan
        WHERE (f.fechaBaja IS NULL OR f.fechaBaja = '' OR f.fechaBaja = '0000-00-00')
          AND f.IdEmpresa IS NOT NULL AND f.IdEmpresa != 0 AND f.IdEmpresa != ''
        ORDER BY f.IdEmpresa
        """
    )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        ie = str(d.get("id_empresa") or "").strip()
        if not ie or ie == "0":
            continue
        cust = normalize_cuit(d.get("customer_cuit_raw") or "")
        prod = normalize_cuit(d.get("product_cuit_raw") or "")
        rows.append({
            "id_empresa": ie,
            "email": (d.get("email") or "").strip(),
            "customer_cuit": cust,
            "product_cuit": prod,
            "plan": (d.get("plan") or "").strip(),
            "id_plan": str(d.get("id_plan") or ""),
            "amount": str(d.get("amount") or ""),
            "razonSocial": (d.get("razonSocial") or "").strip(),
        })
    conn.close()
    return rows


def run_export(db_path: Path, output_path: Path, months: int) -> None:
    """Export first payments for last N months to JSON."""
    if not db_path.exists():
        print(f"Error: SQLite not found at {db_path}")
        print("Run export_colppy_to_sqlite.py first (requires Colppy MySQL/VPN).")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    snapshot = {
        "metadata": {
            "exported_at": now.isoformat() + "Z",
            "source": "colppy_export.db",
            "months_included": months,
        },
        "first_payments_by_month": {},
    }

    for i in range(months):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        last = monthrange(y, m)[1]
        start_date = f"{y:04d}-{m:02d}-01"
        end_date = f"{y:04d}-{m:02d}-{last:02d}"
        month_key = f"{y:04d}-{m:02d}"

        rows = query_first_payments(db_path, start_date, end_date)
        for r in rows:
            v = r.get("fechaPago")
            if v is not None and not isinstance(v, str):
                r["fechaPago"] = str(v)[:10]
        snapshot["first_payments_by_month"][month_key] = rows

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    total_fp = sum(len(v) for v in snapshot["first_payments_by_month"].values())
    print(f"Exported {total_fp} first payments across {months} months")
    print(f"Saved to: {output_path}")

    # 2. Export Colppy facturacion (billing) for facturacion.csv reconciliation
    facturacion_path = output_path.parent / "colppy_facturacion_snapshot.json"
    facturacion_rows = query_colppy_facturacion(db_path)
    facturacion_snapshot = {
        "metadata": {
            "exported_at": snapshot["metadata"]["exported_at"],
            "source": "colppy_export.db",
            "description": "Active billing (fechaBaja IS NULL). For facturacion.csv reconciliation.",
        },
        "facturacion": facturacion_rows,
    }
    with open(facturacion_path, "w", encoding="utf-8") as f:
        json.dump(facturacion_snapshot, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(facturacion_rows)} Colppy facturacion rows")
    print(f"Saved to: {facturacion_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Export Colppy first payments snapshot for plugin"
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"Path to colppy_export.db (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=62,
        help="Number of months to export (default: 62, from 2021-01 onwards)",
    )
    args = parser.parse_args()
    run_export(Path(args.db), Path(args.output), args.months)


if __name__ == "__main__":
    main()
