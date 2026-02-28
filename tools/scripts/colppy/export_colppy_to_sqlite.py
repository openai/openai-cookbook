#!/usr/bin/env python3
"""
Export Colppy MySQL to Local SQLite
===================================
Exports key tables for offline reconciliation with facturacion.csv and HubSpot.

Tables: facturacion, empresa, plan, pago, payment_detail
~135k rows total, ~50 MB, ~1-2 min

Refresh strategy: See tools/docs/COLPPY_EXPORT_REFRESH_STRATEGY.md
- Transactional (incremental): pago, payment_detail (by fechaPago)
- Snapshot: empresa, facturacion, plan

Usage:
  python tools/scripts/colppy/export_colppy_to_sqlite.py
  python tools/scripts/colppy/export_colppy_to_sqlite.py --output tools/data/colppy_export.db
  python tools/scripts/colppy/export_colppy_to_sqlite.py --full              # full snapshot (bootstrap)
  python tools/scripts/colppy/export_colppy_to_sqlite.py --incremental       # pago since last_sync
  python tools/scripts/colppy/export_colppy_to_sqlite.py --incremental --incremental-since 2026-02-01
  python tools/scripts/colppy/export_colppy_to_sqlite.py --year 2026 --month 1  # timeframe merge
  python tools/scripts/colppy/export_colppy_to_sqlite.py --dry-run
"""

import argparse
import calendar
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

tools_dir = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(tools_dir))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(tools_dir / ".env")

ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
DEFAULT_OUTPUT = str(REPO_ROOT / "tools" / "data" / "colppy_export.db")
BATCH_SIZE = 5000

TABLES = ["plan", "facturacion", "pago", "payment_detail", "empresa"]

COLPPY_REFRESH_LOGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS colppy_export_refresh_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    mode            TEXT NOT NULL,
    total_rows      INTEGER NOT NULL,
    table_counts    TEXT
);
CREATE INDEX IF NOT EXISTS idx_colppy_refresh_ts ON colppy_export_refresh_logs(timestamp);
"""

COLPPY_SYNC_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS colppy_sync_state (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    last_pago_sync      TEXT,
    updated_at          TEXT
);
INSERT OR IGNORE INTO colppy_sync_state (id, last_pago_sync, updated_at) VALUES (1, NULL, NULL);
"""


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

    conn.executescript(COLPPY_SYNC_STATE_SCHEMA)
    max_fecha = max((r.get("fechaPago") or "") for r in pago_rows if r.get("fechaPago"))
    if max_fecha:
        if hasattr(max_fecha, "strftime"):
            max_fecha_str = max_fecha.strftime("%Y-%m-%d")
        else:
            max_fecha_str = str(max_fecha)[:10]
        _set_last_pago_sync(conn, max_fecha_str)
        conn.commit()
        print(f"  last_pago_sync = {max_fecha_str} (for incremental)")

    conn.close()

    total_rows = len(pago_rows) + len(facturacion_rows) + len(empresa_rows) + len(plan_rows) + len(payment_detail_rows)
    _log_colppy_refresh(
        str(out_p),
        mode=f"timeframe_{month_key}",
        total_rows=total_rows,
        table_counts={
            "pago": len(pago_rows),
            "facturacion": len(facturacion_rows),
            "empresa": len(empresa_rows),
            "plan": len(plan_rows),
            "payment_detail": len(payment_detail_rows),
        },
    )
    print(f"\nMerged {month_key} data into {out_p.absolute()}")
    print(f"  Refresh logged to colppy_export_refresh_logs")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def _log_colppy_refresh(
    db_path: str,
    mode: str,
    total_rows: int,
    table_counts: dict[str, int] | None = None,
) -> None:
    """Log refresh to colppy_export_refresh_logs so you can see when DB was last synced."""
    conn = sqlite3.connect(db_path)
    conn.executescript(COLPPY_REFRESH_LOGS_SCHEMA)
    ts = datetime.now(ARGENTINA_TZ).isoformat()
    counts_json = json.dumps(table_counts) if table_counts else None
    conn.execute(
        """
        INSERT INTO colppy_export_refresh_logs (timestamp, mode, total_rows, table_counts)
        VALUES (?, ?, ?, ?)
        """,
        (ts, mode, total_rows, counts_json),
    )
    conn.commit()
    conn.close()


def get_last_colppy_refresh(db_path: str) -> dict | None:
    """Return the most recent colppy_export refresh record, or None."""
    path = Path(db_path)
    if not path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.executescript(COLPPY_REFRESH_LOGS_SCHEMA)
    row = conn.execute(
        """
        SELECT timestamp, mode, total_rows, table_counts
        FROM colppy_export_refresh_logs
        ORDER BY timestamp DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    if not row:
        return None
    counts = None
    if row[3]:
        try:
            counts = json.loads(row[3])
        except (json.JSONDecodeError, TypeError):
            pass
    return {"timestamp": row[0], "mode": row[1], "total_rows": row[2], "table_counts": counts}


def _get_last_pago_sync(conn: sqlite3.Connection) -> str | None:
    """Get last_pago_sync from colppy_sync_state. Returns None if not set."""
    conn.executescript(COLPPY_SYNC_STATE_SCHEMA)
    row = conn.execute(
        "SELECT last_pago_sync FROM colppy_sync_state WHERE id = 1"
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0]


def _set_last_pago_sync(conn: sqlite3.Connection, sync_date: str) -> None:
    """Update last_pago_sync in colppy_sync_state."""
    conn.executescript(COLPPY_SYNC_STATE_SCHEMA)
    ts = datetime.now(ARGENTINA_TZ).isoformat()
    conn.execute(
        "UPDATE colppy_sync_state SET last_pago_sync = ?, updated_at = ? WHERE id = 1",
        (sync_date, ts),
    )


def _upsert_rows(
    conn: sqlite3.Connection,
    table: str,
    rows: list[dict],
    id_column: str,
    id_values: list,
) -> None:
    """Delete existing rows by id_column IN (...) and insert new rows. Runs DELETE even when rows empty (removes stale data)."""
    if id_values:
        placeholders_in = ",".join("?" * len(id_values))
        conn.execute(
            f'DELETE FROM {table} WHERE "{id_column}" IN ({placeholders_in})',
            id_values,
        )
    if not rows:
        return
    cols = list(rows[0].keys())
    col_list = ",".join(f'"{c}"' for c in cols)
    placeholders = ",".join("?" * len(cols))
    vals = [tuple(_py_to_sqlite(r.get(c)) for c in cols) for r in rows]
    conn.executemany(
        f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})',
        vals,
    )


def _upsert_payment_detail(
    conn: sqlite3.Connection, rows: list[dict], payment_ids: list
) -> None:
    """Delete payment_detail by payment_id and insert. Multiple rows per payment_id. Runs DELETE even when rows empty."""
    if payment_ids:
        ph = ",".join("?" * len(payment_ids))
        conn.execute(f"DELETE FROM payment_detail WHERE payment_id IN ({ph})", payment_ids)
    if not rows:
        return
    cols = list(rows[0].keys())
    col_list = ",".join(f'"{c}"' for c in cols)
    placeholders = ",".join("?" * len(cols))
    vals = [tuple(_py_to_sqlite(r.get(c)) for c in cols) for r in rows]
    conn.executemany(
        f"INSERT INTO payment_detail ({col_list}) VALUES ({placeholders})",
        vals,
    )


def run_export_incremental(
    output_path: str,
    dry_run: bool,
    since_date: str | None = None,
) -> None:
    """
    Incremental export: pago + payment_detail by fechaPago >= last_sync.
    Fetches empresa, facturacion, plan only for id_empresa in new pago (targeted merge).
    Requires existing DB from --full or --year --month. Use --full for bootstrap.
    """
    from database import get_db

    out_p = Path(output_path)
    if not out_p.exists():
        print(f"Error: {output_path} does not exist. Run --full first to bootstrap.")
        return

    conn = sqlite3.connect(str(out_p))
    try:
        conn.executescript(COLPPY_SYNC_STATE_SCHEMA)
        last_sync = since_date or _get_last_pago_sync(conn)
        if not last_sync:
            last_sync = "2020-01-01"
            print(f"  No last_sync; using bootstrap date: {last_sync}")

        print("=" * 60)
        print("Colppy MySQL → SQLite Export (incremental)")
        print("=" * 60)
        print(f"Output: {output_path}")
        print(f"Since: {last_sync}")
        if dry_run:
            print("(dry-run: count only, no write)")
        print()

        mysql_db = get_db()
        pago_query = """
            SELECT * FROM pago
            WHERE fechaPago >= :since
            ORDER BY fechaPago
        """
        pago_rows = mysql_db.execute_query(pago_query, {"since": last_sync})

        if not pago_rows:
            print(f"No new pago since {last_sync}.")
            if not dry_run:
                today = datetime.now(ARGENTINA_TZ).strftime("%Y-%m-%d")
                _set_last_pago_sync(conn, today)
                conn.commit()
                _log_colppy_refresh(
                    str(out_p),
                    mode="incremental",
                    total_rows=0,
                    table_counts={"pago": 0, "payment_detail": 0},
                )
            return

        max_fecha = max(
            (r.get("fechaPago") or "") for r in pago_rows
            if r.get("fechaPago")
        )
        if isinstance(max_fecha, datetime):
            max_fecha = max_fecha.strftime("%Y-%m-%d") if max_fecha else last_sync
        else:
            max_fecha = str(max_fecha)[:10] if max_fecha else last_sync

        id_pagos = sorted({r.get("idPago") for r in pago_rows if r.get("idPago")})
        id_empresas = sorted({str(r.get("idEmpresa") or "") for r in pago_rows if r.get("idEmpresa")})
        id_plans = sorted({r.get("idPlan") for r in pago_rows if r.get("idPlan")})

        payment_detail_rows = []
        if id_pagos:
            ph = ",".join([f":pd{i}" for i in range(len(id_pagos))])
            params = {f"pd{i}": id_pagos[i] for i in range(len(id_pagos))}
            payment_detail_rows = mysql_db.execute_query(
                f"SELECT * FROM payment_detail WHERE payment_id IN ({ph})", params
            )

        facturacion_rows = []
        empresa_rows = []
        if id_empresas:
            ph = ",".join([f":e{i}" for i in range(len(id_empresas))])
            params = {f"e{i}": id_empresas[i] for i in range(len(id_empresas))}
            facturacion_rows = mysql_db.execute_query(
                f"SELECT * FROM facturacion WHERE IdEmpresa IN ({ph})", params
            )
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

        print(f"  pago: {len(pago_rows):,} | payment_detail: {len(payment_detail_rows):,}")
        print(f"  empresa: {len(empresa_rows):,} | facturacion: {len(facturacion_rows):,} | plan: {len(plan_rows):,}")

        if dry_run:
            print(f"  Would merge into {output_path}; next last_sync = {max_fecha}")
            return

        if not _table_exists(conn, "pago"):
            for table, rows in [
                ("pago", pago_rows),
                ("payment_detail", payment_detail_rows),
                ("facturacion", facturacion_rows),
                ("empresa", empresa_rows),
                ("plan", plan_rows),
            ]:
                if rows:
                    cols = list(rows[0].keys())
                    col_list = ",".join(f'"{c}"' for c in cols)
                    conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({col_list})")
            conn.commit()

        id_pago_list = list(id_pagos)
        _upsert_rows(conn, "pago", pago_rows, "idPago", id_pago_list)
        _upsert_payment_detail(conn, payment_detail_rows, id_pago_list)
        if id_empresas:
            _upsert_rows(conn, "facturacion", facturacion_rows, "IdEmpresa", id_empresas)
            _upsert_rows(conn, "empresa", empresa_rows, "IdEmpresa", id_empresas)
        if id_plans:
            _upsert_rows(conn, "plan", plan_rows, "idPlan", list(id_plans))

        _set_last_pago_sync(conn, max_fecha)
        conn.commit()
        total = len(pago_rows) + len(payment_detail_rows) + len(facturacion_rows) + len(empresa_rows) + len(plan_rows)
        _log_colppy_refresh(
            str(out_p),
            mode="incremental",
            total_rows=total,
            table_counts={
                "pago": len(pago_rows),
                "payment_detail": len(payment_detail_rows),
                "facturacion": len(facturacion_rows),
                "empresa": len(empresa_rows),
                "plan": len(plan_rows),
            },
        )
        print(f"\nMerged incremental data into {out_p.absolute()}")
        print(f"  last_pago_sync = {max_fecha}")
        print(f"  Refresh logged to colppy_export_refresh_logs")
    finally:
        conn.close()


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

    table_counts = {}
    for table in TABLES:
        print(f"Exporting {table}...", end=" ", flush=True)
        cnt = export_table(mysql_db, conn, table, dry_run=False)
        total += cnt
        table_counts[table] = cnt
        print(f"{cnt:,} rows")

    conn.executescript(COLPPY_SYNC_STATE_SCHEMA)
    row = conn.execute(
        "SELECT MAX(date(fechaPago)) FROM pago WHERE fechaPago IS NOT NULL"
    ).fetchone()
    if row and row[0]:
        _set_last_pago_sync(conn, row[0])
        conn.commit()
        print(f"  last_pago_sync = {row[0]} (for incremental)")

    conn.close()
    _log_colppy_refresh(str(out_p), mode="full", total_rows=total, table_counts=table_counts)
    print(f"  Refresh logged to colppy_export_refresh_logs")

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
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full snapshot (default when no other mode). Bootstrap for --incremental.",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Incremental: pago + payment_detail since last_sync. Requires existing DB.",
    )
    parser.add_argument(
        "--incremental-since",
        type=str,
        metavar="YYYY-MM-DD",
        help="Override last_sync date for --incremental (e.g. 2026-02-01)",
    )
    args = parser.parse_args()
    if args.year and args.month:
        run_export_timeframe(args.output, args.year, args.month, args.dry_run)
    elif args.incremental:
        run_export_incremental(
            args.output, args.dry_run, since_date=args.incremental_since
        )
    elif args.year or args.month:
        parser.error("--year and --month must be used together")
    else:
        run_export(args.output, args.dry_run)


if __name__ == "__main__":
    main()
