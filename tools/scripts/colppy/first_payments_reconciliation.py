#!/usr/bin/env python3
"""
First Payments Reconciliation: Colppy DB ↔ facturacion.csv
==========================================================
Queries first payments (primerPago=1) for a given month from Colppy MySQL
or local SQLite export, joins facturacion (cuit_invoicing), mrr_calculo (MRR),
and matches against facturacion.csv by CUIT.

Usage:
  python tools/scripts/colppy/first_payments_reconciliation.py --month 2026-01
  python tools/scripts/colppy/first_payments_reconciliation.py --start 2026-01-01 --end 2026-01-31
  python tools/scripts/colppy/first_payments_reconciliation.py --month 2026-01 --csv  # output CSV
  python tools/scripts/colppy/first_payments_reconciliation.py --month 2026-01 --local  # use colppy_export.db (no MySQL)
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

tools_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(tools_dir))

from dotenv import load_dotenv

load_dotenv(tools_dir / ".env")

DEFAULT_CSV_PATH = "tools/outputs/facturacion.csv"
DEFAULT_LOCAL_DB = "tools/data/colppy_export.db"


def normalize_cuit(raw: str) -> str | None:
    """Normalize CUIT to 11 digits."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    return digits if len(digits) == 11 and digits.isdigit() else None


def query_first_payments_with_mrr(
    start_date: str, end_date: str
) -> list[dict]:
    """First payments in date range with facturacion.CUIT and mrr_calculo (latest fechamrr in range)."""
    from database import get_db

    db = get_db()
    query = """
    SELECT
        p.idPago,
        p.idEmpresa,
        p.idPlan,
        pl.nombre AS plan_name,
        p.fechaPago,
        COALESCE(pd.accreditation_date, pd.payment_date) AS payment_datetime,
        p.importe,
        p.medioPago,
        p.tipoPago,
        f.CUIT AS cuit_invoicing,
        mc.mrrLocal,
        mc.mrrUsd,
        mc.fechamrr AS mrr_date,
        mc.tipo AS mrr_tipo
    FROM pago p
    LEFT JOIN plan pl ON pl.idPlan = p.idPlan
    LEFT JOIN payment_detail pd ON pd.payment_id = p.idPago AND pd.is_first_payment = 1
    LEFT JOIN facturacion f ON f.IdEmpresa = p.idEmpresa AND f.fechaBaja IS NULL
    LEFT JOIN (
        SELECT mc2.idEmpresa, mc2.mrrLocal, mc2.mrrUsd, mc2.fechamrr, mc2.tipo
        FROM mrr_calculo mc2
        INNER JOIN (
            SELECT idEmpresa, MAX(fechamrr) AS max_fecha
            FROM mrr_calculo
            WHERE fechamrr >= :start_date
              AND fechamrr <= :end_date
              AND fechamrr != '0000-00-00'
            GROUP BY idEmpresa
        ) mx ON mx.idEmpresa = mc2.idEmpresa AND mx.max_fecha = mc2.fechamrr
    ) mc ON mc.idEmpresa = p.idEmpresa
    WHERE p.primerPago = 1
      AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
      AND p.fechaPago >= :start_date
      AND p.fechaPago < DATE_ADD(:end_date, INTERVAL 1 DAY)
    ORDER BY p.fechaPago, payment_datetime, p.idPago
    """
    return db.execute_query(
        query, {"start_date": start_date, "end_date": end_date}
    )


def query_first_payments_local(
    start_date: str, end_date: str, db_path: str
) -> list[dict]:
    """First payments from local SQLite (colppy_export.db). No mrr_calculo in export → mrrLocal/mrrUsd NULL."""
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
            COALESCE(pd.accreditation_date, pd.payment_date) AS payment_datetime,
            p.importe,
            p.medioPago,
            p.tipoPago,
            f.CUIT AS cuit_invoicing,
            NULL AS mrrLocal,
            NULL AS mrrUsd,
            NULL AS mrr_date,
            NULL AS mrr_tipo
        FROM pago p
        LEFT JOIN plan pl ON pl.idPlan = p.idPlan
        LEFT JOIN payment_detail pd ON pd.payment_id = p.idPago AND pd.is_first_payment = 1
        LEFT JOIN facturacion f ON f.IdEmpresa = p.idEmpresa AND (f.fechaBaja IS NULL OR f.fechaBaja = '')
        WHERE p.primerPago = 1
          AND (p.estado = 1 OR (p.estado = 0 AND p.fechaTransferencia IS NOT NULL))
          AND p.fechaPago >= ?
          AND p.fechaPago < date(?, '+1 day')
        ORDER BY p.fechaPago, payment_datetime, p.idPago
        """,
        (start_date, end_date),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def load_facturacion_csv(path: str) -> list[dict]:
    """Load facturacion.csv. Returns list with id_empresa, customer_cuit_norm, product_cuit_norm, etc."""
    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()
    header_idx = None
    for i, line in enumerate(lines):
        if "Email" in line and "Customer Cuit" in line:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Header not found in facturacion file")
    for line in lines[header_idx + 1 :]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) < 7:
            continue
        ie = parts[6].strip() if len(parts) > 6 else ""
        if ie and ie.isdigit():
            records.append(
                {
                    "id_empresa": ie,
                    "email": parts[0].strip()[:50],
                    "customer_cuit": parts[1].strip(),
                    "customer_cuit_norm": normalize_cuit(parts[1].strip()),
                    "plan": parts[2].strip(),
                    "product_cuit": parts[5].strip(),
                    "product_cuit_norm": normalize_cuit(parts[5].strip()),
                }
            )
    return records


def build_cuit_to_csv(records: list[dict]) -> dict[str, list[dict]]:
    """Map normalized CUIT -> list of CSV rows."""
    cuit_to_csv = {}
    for r in records:
        for k in ["customer_cuit_norm", "product_cuit_norm"]:
            c = r.get(k)
            if c:
                if c not in cuit_to_csv:
                    cuit_to_csv[c] = []
                if r not in cuit_to_csv[c]:
                    cuit_to_csv[c].append(r)
    return cuit_to_csv


def run_reconciliation(
    start_date: str,
    end_date: str,
    csv_path: str,
    output_csv: bool = False,
    use_local: bool = False,
    local_db_path: str = DEFAULT_LOCAL_DB,
) -> None:
    """Run full reconciliation and print report."""
    if use_local:
        db_path = Path(local_db_path)
        if not db_path.exists():
            raise FileNotFoundError(
                f"Local DB not found: {db_path}. Run export_colppy_to_sqlite.py first."
            )
        payments = query_first_payments_local(start_date, end_date, str(db_path))
    else:
        payments = query_first_payments_with_mrr(start_date, end_date)
    csv_path_p = Path(csv_path)
    if not csv_path_p.exists():
        print(f"Warning: facturacion.csv not found at {csv_path}. Skipping CSV match.")
        csv_records = []
        cuit_to_csv = {}
    else:
        csv_records = load_facturacion_csv(str(csv_path_p))
        cuit_to_csv = build_cuit_to_csv(csv_records)

    print("=" * 130)
    print(f"First Payments Reconciliation: {start_date} to {end_date}")
    if use_local:
        print(f"(Source: local SQLite {local_db_path})")
    print("=" * 130)
    print(f"\nFirst payments: {len(payments)} records")
    if csv_records:
        print(f"facturacion.csv: {len(csv_records)} rows (for CUIT matching)")
    print()

    # Match each payment
    match_same_id = 0
    match_cuit_diff_id = 0
    no_match = 0

    rows_out = []
    for r in payments:
        cuit = normalize_cuit(r.get("cuit_invoicing"))
        ie = str(r.get("idEmpresa", ""))
        csv_rows = cuit_to_csv.get(cuit, []) if cuit else []
        csv_same_id = [x for x in csv_rows if x["id_empresa"] == ie]
        csv_diff_id = [x for x in csv_rows if x["id_empresa"] != ie]

        if csv_same_id:
            match_type = "MATCH_same_id_empresa"
            match_same_id += 1
            row = csv_same_id[0]
        elif csv_diff_id:
            match_type = "CUIT_match_diff_id_empresa"
            match_cuit_diff_id += 1
            row = csv_diff_id[0]
        else:
            match_type = "no_match_in_csv"
            no_match += 1
            row = {}

        out = {
            "idPago": r.get("idPago"),
            "idEmpresa": ie,
            "plan_name": r.get("plan_name", ""),
            "fechaPago": r.get("fechaPago"),
            "importe": r.get("importe"),
            "medioPago": r.get("medioPago", ""),
            "cuit_invoicing": r.get("cuit_invoicing", ""),
            "mrrLocal": r.get("mrrLocal"),
            "mrrUsd": r.get("mrrUsd"),
            "mrr_date": r.get("mrr_date"),
            "match_type": match_type,
            "csv_id_empresa": row.get("id_empresa", ""),
            "csv_email": row.get("email", ""),
            "csv_plan": row.get("plan", ""),
        }
        rows_out.append(out)

    # Print table
    print(
        "idPago|idEmpresa|plan_name|fechaPago|importe|medioPago|cuit_invoicing|mrrLocal|mrrUsd|match_type|csv_id_empresa|csv_email|csv_plan"
    )
    print("-" * 130)
    for o in rows_out:
        print(
            f"{o['idPago']}|{o['idEmpresa']}|{o['plan_name']}|{o['fechaPago']}|{o['importe']}|{o['medioPago']}|"
            f"{o['cuit_invoicing']}|{o['mrrLocal']}|{o['mrrUsd']}|{o['match_type']}|"
            f"{o['csv_id_empresa']}|{o['csv_email']}|{o['csv_plan']}"
        )

    print()
    print("=" * 130)
    print("Summary")
    print("=" * 130)
    print(f"  MATCH (same id_empresa + CUIT in CSV):     {match_same_id}")
    print(f"  CUIT match but different id_empresa:       {match_cuit_diff_id}")
    print(f"  No CUIT match in facturacion.csv:          {no_match}")

    if output_csv:
        out_path = Path("tools/outputs") / f"first_payments_reconciliation_{start_date.replace('-','')}_{end_date.replace('-','')}.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            cols = list(rows_out[0].keys()) if rows_out else []
            f.write(";".join(cols) + "\n")
            for o in rows_out:
                f.write(";".join(str(o.get(c, "")) for c in cols) + "\n")
        print(f"\nExported to: {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="First payments reconciliation: Colppy DB vs facturacion.csv"
    )
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        help="Month (e.g. 2026-01). Sets start/end to first/last day.",
    )
    parser.add_argument(
        "--start",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--csv-path",
        default=DEFAULT_CSV_PATH,
        help=f"Path to facturacion.csv (default: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Export results to CSV",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local colppy_export.db (no MySQL). Run export_colppy_to_sqlite.py first.",
    )
    parser.add_argument(
        "--local-db",
        default=DEFAULT_LOCAL_DB,
        help=f"Path to local SQLite export (default: {DEFAULT_LOCAL_DB})",
    )
    args = parser.parse_args()

    if args.month:
        parts = args.month.split("-")
        if len(parts) != 2:
            parser.error("--month must be YYYY-MM")
        y, m = int(parts[0]), int(parts[1])
        from calendar import monthrange

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
        csv_path=args.csv_path,
        output_csv=args.csv,
        use_local=args.local,
        local_db_path=args.local_db,
    )


if __name__ == "__main__":
    main()
