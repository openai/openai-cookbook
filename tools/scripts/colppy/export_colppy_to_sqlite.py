#!/usr/bin/env python3
"""
Export Colppy MySQL to Local SQLite
===================================
Exports key tables for offline reconciliation with facturacion.csv and HubSpot.

Tables: facturacion, empresa, plan, pago, payment_detail
~135k rows total, ~50 MB, ~1-2 min

Usage:
  python tools/scripts/colppy/export_colppy_to_sqlite.py
  python tools/scripts/colppy/export_colppy_to_sqlite.py --output tools/data/colppy_export.db
  python tools/scripts/colppy/export_colppy_to_sqlite.py --year 2026 --month 1  # timeframe-only refresh
  python tools/scripts/colppy/export_colppy_to_sqlite.py --dry-run
"""

import argparse
import calendar
import sqlite3
import sys
from pathlib import Path

tools_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(tools_dir))

from dotenv import load_dotenv

load_dotenv(tools_dir / ".env")

DEFAULT_OUTPUT = "tools/data/colppy_export.db"
BATCH_SIZE = 5000

TABLES = ["plan", "facturacion", "pago", "payment_detail", "empresa"]


def _py_to_sqlite(val):
    """Convert Python value for SQLite (handle datetime, None)."""
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def export_table(
    mysql_db, sqlite_conn: sqlite3.Connection, table: str, dry_run: bool
) -> int:
    """Export one table from MySQL to SQLite. Returns row count."""
    rows = mysql_db.execute_query(f"SELECT * FROM {table}")
    count = len(rows)
    if count == 0:
        return 0
    if dry_run:
        return count
    cols = list(rows[0].keys())
    placeholders = ",".join("?" * len(cols))
    col_list = ",".join(f'"{c}"' for c in cols)
    sqlite_conn.execute(f"DROP TABLE IF EXISTS {table}")
    sqlite_conn.execute(
        f"CREATE TABLE {table} ({col_list})"
    )
    for i in range(0, count, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        vals = [
            tuple(_py_to_sqlite(r.get(c)) for c in cols)
            for r in batch
        ]
        sqlite_conn.executemany(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
            vals,
        )
    sqlite_conn.commit()
    return count


def run_export_timeframe(
    output_path: str, year: str, month: int, dry_run: bool
) -> None:
    """Export only first payments for given month and merge into existing DB."""
    from database import get_db

    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(int(year), month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    month_key = f"{year}-{month:02d}"

    print("=" * 60)
    print(f"Colppy MySQL → SQLite Export (timeframe: {month_key})")
    print("=" * 60)
    print(f"Output: {output_path}")
    if dry_run:
        print("(dry-run: count only, no write)")
    print()

    mysql_db = get_db()

    # 1. Fetch first payments for month
    end_next = f"{year}-{month + 1:02d}-01" if month < 12 else f"{int(year) + 1}-01-01"
    pago_query = """
        SELECT * FROM pago
        WHERE primerPago = 1
          AND (estado = 1 OR (estado = 0 AND fechaTransferencia IS NOT NULL))
          AND fechaPago >= :start AND fechaPago < :end_next
    """
    pago_rows = mysql_db.execute_query(
        pago_query, {"start": start, "end_next": end_next}
    )
    if not pago_rows:
        print(f"No first payments for {month_key}. Nothing to export.")
        return

    id_empresas = sorted({str(r.get("idEmpresa") or "") for r in pago_rows if r.get("idEmpresa")})
    id_plans = sorted({r.get("idPlan") for r in pago_rows if r.get("idPlan")})
    id_pagos = sorted({r.get("idPago") for r in pago_rows if r.get("idPago")})

    print(f"  First payments: {len(pago_rows):,} ({len(id_empresas):,} unique id_empresa)")

    if dry_run:
        print(f"  Would merge into {output_path}")
        return

    # 2. Fetch related tables (use :p0, :p1, ... for IN clauses)
    facturacion_rows = []
    if id_empresas:
        ph = ",".join([f":e{i}" for i in range(len(id_empresas))])
        params = {f"e{i}": id_empresas[i] for i in range(len(id_empresas))}
        facturacion_rows = mysql_db.execute_query(
            f"SELECT * FROM facturacion WHERE IdEmpresa IN ({ph})", params
        )
    empresa_rows = []
    if id_empresas:
        ph = ",".join([f":e{i}" for i in range(len(id_empresas))])
        params = {f"e{i}": id_empresas[i] for i in range(len(id_empresas))}
        empresa_rows = mysql_db.execute_query(
            f"SELECT * FROM empresa WHERE IdEmpresa IN ({ph})", params
        )
    plan_rows = []
    if id_plans:
        ph = ",".join([f":p{i}" for i in range(len(id_plans))])
        params = {f"p{i}": id_plans[i] for i in range(len(id_plans))}
        plan_rows = mysql_db.execute_query(
            f"SELECT * FROM plan WHERE idPlan IN ({ph})", params
        )
    payment_detail_rows = []
    if id_pagos:
        ph = ",".join([f":pd{i}" for i in range(len(id_pagos))])
        params = {f"pd{i}": id_pagos[i] for i in range(len(id_pagos))}
        payment_detail_rows = mysql_db.execute_query(
            f"SELECT * FROM payment_detail WHERE payment_id IN ({ph})", params
        )

    print(f"  facturacion: {len(facturacion_rows):,} | empresa: {len(empresa_rows):,} | plan: {len(plan_rows):,} | payment_detail: {len(payment_detail_rows):,}")

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(out_p))

    # 3. Ensure schema exists (create if new DB)
    if not _table_exists(conn, "pago"):
        # Create tables from our data (partial DB for this timeframe)
        for table, rows in [
            ("pago", pago_rows),
            ("facturacion", facturacion_rows),
            ("empresa", empresa_rows),
            ("plan", plan_rows),
            ("payment_detail", payment_detail_rows),
        ]:
            if rows:
                cols = list(rows[0].keys())
                col_list = ",".join(f'"{c}"' for c in cols)
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({col_list})")
        conn.commit()

    # 4. Merge: delete existing for this month, then insert
    conn.execute(
        "DELETE FROM pago WHERE primerPago = 1 AND fechaPago >= ? AND fechaPago <= ?",
        (start, end),
    )
    if id_empresas:
        conn.execute(
            "DELETE FROM facturacion WHERE IdEmpresa IN (" + ",".join("?" * len(id_empresas)) + ")",
            id_empresas,
        )
        conn.execute(
            "DELETE FROM empresa WHERE IdEmpresa IN (" + ",".join("?" * len(id_empresas)) + ")",
            id_empresas,
        )
    if id_plans:
        conn.execute(
            "DELETE FROM plan WHERE idPlan IN (" + ",".join("?" * len(id_plans)) + ")",
            id_plans,
        )
    if id_pagos:
        conn.execute(
            "DELETE FROM payment_detail WHERE payment_id IN (" + ",".join("?" * len(id_pagos)) + ")",
            id_pagos,
        )
    conn.commit()

    # 5. Insert new rows
    def _insert_rows(table: str, rows: list[dict]) -> None:
        if not rows:
            return
        cols = list(rows[0].keys())
        placeholders = ",".join("?" * len(cols))
        col_list = ",".join(f'"{c}"' for c in cols)
        vals = [tuple(_py_to_sqlite(r.get(c)) for c in cols) for r in rows]
        conn.executemany(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
            vals,
        )

    _insert_rows("pago", pago_rows)
    _insert_rows("facturacion", facturacion_rows)
    _insert_rows("empresa", empresa_rows)
    _insert_rows("plan", plan_rows)
    _insert_rows("payment_detail", payment_detail_rows)
    conn.commit()
    conn.close()

    print(f"\nMerged {month_key} data into {out_p.absolute()}")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def run_export(output_path: str, dry_run: bool) -> None:
    """Run full export."""
    from database import get_db

    print("=" * 60)
    print("Colppy MySQL → SQLite Export")
    print("=" * 60)
    print(f"Output: {output_path}")
    print(f"Tables: {', '.join(TABLES)}")
    if dry_run:
        print("(dry-run: count only, no write)")
    print()

    mysql_db = get_db()
    total = 0

    if dry_run:
        for table in TABLES:
            row = mysql_db.execute_query(f"SELECT COUNT(*) as cnt FROM {table}")[0]
            cnt = list(row.values())[0]
            total += cnt
            print(f"  {table}: {cnt:,} rows")
        print(f"\nTotal: {total:,} rows")
        return

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(out_p))

    for table in TABLES:
        print(f"Exporting {table}...", end=" ", flush=True)
        cnt = export_table(mysql_db, conn, table, dry_run=False)
        total += cnt
        print(f"{cnt:,} rows")

    conn.close()
    size_mb = out_p.stat().st_size / (1024 * 1024)
    print()
    print(f"Total: {total:,} rows")
    print(f"File size: {size_mb:.1f} MB")
    print(f"Saved to: {out_p.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description="Export Colppy MySQL to SQLite for offline reconciliation"
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output SQLite path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--year",
        type=str,
        help="Year for timeframe-only refresh (e.g. 2026). Use with --month.",
    )
    parser.add_argument(
        "--month",
        type=int,
        help="Month 1-12 for timeframe-only refresh. Use with --year.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows only, do not write",
    )
    args = parser.parse_args()
    if args.year and args.month:
        run_export_timeframe(args.output, args.year, args.month, args.dry_run)
    elif args.year or args.month:
        parser.error("--year and --month must be used together")
    else:
        run_export(args.output, args.dry_run)


if __name__ == "__main__":
    main()
