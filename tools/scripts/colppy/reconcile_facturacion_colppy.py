#!/usr/bin/env python3
"""
Reconcile Facturación Sources: CSV ↔ Colppy MySQL ↔ facturacion_hubspot.db
============================================================================
Compares facturacion.csv (billing export), facturacion_hubspot.db (SQLite), and
Colppy MySQL facturacion to identify discrepancies.

Data sources:
- facturacion.csv: Manual billing export (Email;Customer Cuit;Plan;Id Plan;Amount;Product CUIT;Id Empresa)
- facturacion_hubspot.db: SQLite built from facturacion.csv + HubSpot (facturacion table)
- Colppy MySQL: facturacion + empresa + plan (live billing in Colppy)

Reconciliation directions:
1. In CSV only: id_empresa in CSV but not in Colppy (likely churned or data issue)
2. In Colppy only: id_empresa in Colppy but not in CSV (CSV may be filtered/outdated)
3. In both: compare plan, amount, customer_cuit, product_cuit

Usage:
    python tools/scripts/colppy/reconcile_facturacion_colppy.py
    python tools/scripts/colppy/reconcile_facturacion_colppy.py --csv tools/outputs/facturacion.csv
    python tools/scripts/colppy/reconcile_facturacion_colppy.py --include-db  # also compare facturacion_hubspot.db
    python tools/scripts/colppy/reconcile_facturacion_colppy.py --export-colppy tools/outputs/colppy_facturacion_export.csv
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

tools_dir = Path(__file__).resolve().parents[2]
repo_root = tools_dir.parent
sys.path.insert(0, str(repo_root))
from dotenv import load_dotenv

load_dotenv(tools_dir / ".env")
load_dotenv(repo_root / ".env")

DEFAULT_CSV = "tools/outputs/facturacion.csv"
DEFAULT_DB = "tools/data/facturacion_hubspot.db"
DEFAULT_COLPPY_DB = "tools/data/colppy_export.db"
EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}


def normalize_cuit(raw: str) -> Optional[str]:
    """Normalize CUIT to 11 digits."""
    if not raw or str(raw).strip().upper() in ("#N/A", "N/A", ""):
        return None
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    if len(digits) != 11 or not digits.isdigit() or digits in EXCLUDE_CUITS:
        return None
    return digits


def load_facturacion_csv(path: str) -> list[dict]:
    """Load facturacion CSV. Returns list of dicts with id_empresa, customer_cuit, product_cuit, plan, id_plan, amount, email."""
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
        customer_cuit = normalize_cuit(parts[1].strip())
        product_cuit = normalize_cuit(parts[5].strip())
        id_empresa_raw = parts[6].strip() if len(parts) > 6 else ""
        id_empresa = id_empresa_raw if id_empresa_raw and id_empresa_raw.isdigit() else ""
        if not id_empresa:
            continue
        records.append({
            "id_empresa": id_empresa,
            "email": parts[0].strip(),
            "customer_cuit": customer_cuit or "",
            "plan": parts[2].strip(),
            "id_plan": parts[3].strip() if len(parts) > 3 else "",
            "amount": parts[4].strip(),
            "product_cuit": product_cuit or "",
        })
    return records


def load_colppy_facturacion_local(db_path: str) -> list[dict]:
    """Load active facturacion from local colppy_export.db."""
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
            e.idPlan,
            p.nombre AS plan,
            p.precio AS amount
        FROM facturacion f
        LEFT JOIN empresa e ON e.IdEmpresa = f.IdEmpresa
        LEFT JOIN plan p ON p.idPlan = e.idPlan
        WHERE (f.fechaBaja IS NULL OR f.fechaBaja = '')
          AND f.IdEmpresa IS NOT NULL AND f.IdEmpresa != 0 AND f.IdEmpresa != ''
        """
    )
    out = []
    for r in cur.fetchall():
        d = dict(r)
        ie = str(d.get("id_empresa") or "").strip()
        if not ie:
            continue
        cust = normalize_cuit(d.get("customer_cuit_raw") or "") or ""
        prod = normalize_cuit(d.get("product_cuit_raw") or "") or ""
        out.append({
            "id_empresa": ie,
            "email": (d.get("email") or "").strip(),
            "customer_cuit": cust,
            "product_cuit": prod,
            "plan": (d.get("plan") or "").strip(),
            "id_plan": str(d.get("idPlan") or ""),
            "amount": str(d.get("amount") or ""),
            "razonSocial": (d.get("razonSocial") or "").strip(),
        })
    conn.close()
    return out


def load_colppy_facturacion() -> list[dict]:
    """Load active facturacion from Colppy MySQL (facturacion + empresa + plan)."""
    from database import get_db

    db = get_db()
    q = """
    SELECT
        f.IdEmpresa AS id_empresa,
        f.CUIT AS customer_cuit_raw,
        e.CUIT AS product_cuit_raw,
        f.email,
        f.razonSocial,
        f.fechaAlta,
        f.fechaBaja,
        e.idPlan,
        p.nombre AS plan,
        p.precio AS amount
    FROM facturacion f
    LEFT JOIN empresa e ON e.IdEmpresa = f.IdEmpresa
    LEFT JOIN plan p ON p.idPlan = e.idPlan
    WHERE f.fechaBaja IS NULL
    """
    rows = db.execute_query(q)
    out = []
    for r in rows:
        cust = normalize_cuit(r.get("customer_cuit_raw") or "")
        prod = normalize_cuit(r.get("product_cuit_raw") or "")
        out.append({
            "id_empresa": str(r["id_empresa"]),
            "email": (r.get("email") or "").strip(),
            "customer_cuit": cust or "",
            "product_cuit": prod or "",
            "plan": (r.get("plan") or "").strip(),
            "id_plan": str(r.get("idPlan") or ""),
            "amount": str(r.get("amount") or ""),
            "razonSocial": (r.get("razonSocial") or "").strip(),
        })
    return out


def load_db_facturacion(db_path: str) -> list[dict]:
    """Load facturacion from facturacion_hubspot.db."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id_empresa, email, customer_cuit, product_cuit, plan, id_plan, amount
        FROM facturacion
        WHERE id_empresa IS NOT NULL AND TRIM(id_empresa) != ''
        """
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        ie = str(r["id_empresa"]).strip()
        cust = normalize_cuit(r["customer_cuit"] or "") or (r["customer_cuit"] or "")
        prod = normalize_cuit(r["product_cuit"] or "") or (r["product_cuit"] or "")
        out.append({
            "id_empresa": ie,
            "email": (r["email"] or "").strip(),
            "customer_cuit": cust if isinstance(cust, str) and len(cust) == 11 else cust,
            "product_cuit": prod if isinstance(prod, str) and len(prod) == 11 else prod,
            "plan": (r["plan"] or "").strip(),
            "id_plan": str(r["id_plan"] or ""),
            "amount": str(r["amount"] or ""),
        })
    return out


def run_reconciliation(
    csv_path: str,
    db_path: Optional[str],
    include_db: bool,
    export_colppy_path: Optional[str],
    use_local: bool = False,
    local_colppy_db: str = DEFAULT_COLPPY_DB,
    log_to_db: bool = True,
) -> None:
    """Run full reconciliation and print report."""
    print("=" * 60)
    print("Facturación Reconciliation: CSV ↔ Colppy ↔ facturacion_hubspot.db")
    if use_local:
        print(f"(Colppy source: local SQLite {local_colppy_db})")
    print("=" * 60)

    # 1. Load CSV
    csv_p = Path(csv_path)
    if not csv_p.exists():
        print(f"Error: CSV not found: {csv_path}")
        sys.exit(1)
    csv_records = load_facturacion_csv(str(csv_p))
    csv_by_id = {r["id_empresa"]: r for r in csv_records}
    csv_ids = set(csv_by_id.keys())
    print(f"\n1. facturacion.csv: {len(csv_records):,} rows, {len(csv_ids):,} unique id_empresa")

    # 2. Load Colppy
    if use_local:
        colppy_p = Path(local_colppy_db)
        if not colppy_p.exists():
            print(f"Error: Local DB not found: {local_colppy_db}")
            print("Run export_colppy_to_sqlite.py first.")
            sys.exit(1)
        print("   Loading Colppy from local SQLite...")
        colppy_records = load_colppy_facturacion_local(str(colppy_p))
    else:
        print("   Loading Colppy MySQL facturacion...")
        colppy_records = load_colppy_facturacion()
    colppy_by_id = {r["id_empresa"]: r for r in colppy_records}
    colppy_ids = set(colppy_by_id.keys())
    print(f"   Colppy: {len(colppy_records):,} active rows (fechaBaja IS NULL)")

    # Export Colppy if requested
    if export_colppy_path:
        out_p = Path(export_colppy_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        header = "Email;Customer Cuit;Plan;Id Plan;Amount;Product CUIT;Id Empresa"
        with open(out_p, "w", encoding="utf-8", newline="") as f:
            f.write(header + "\n")
            for r in colppy_records:
                cust = r["customer_cuit"]
                prod = r["product_cuit"]
                cust_display = f"{cust[:2]}-{cust[2:10]}-{cust[10]}" if len(cust) == 11 else cust
                prod_display = f"{prod[:2]}-{prod[2:10]}-{prod[10]}" if len(prod) == 11 else prod
                row = [
                    r["email"],
                    cust_display,
                    r["plan"],
                    r["id_plan"],
                    r["amount"],
                    prod_display,
                    r["id_empresa"],
                ]
                f.write(";".join(str(x) for x in row) + "\n")
        print(f"\n   Exported Colppy facturacion to: {export_colppy_path}")

    # 3. Load DB if requested
    db_by_id = {}
    log_db_path = str(Path(db_path or DEFAULT_DB).resolve()) if db_path else None
    if include_db and db_path:
        db_p = Path(db_path)
        if db_p.exists():
            db_records = load_db_facturacion(str(db_p))
            db_by_id = {r["id_empresa"]: r for r in db_records}
            print(f"\n2. facturacion_hubspot.db: {len(db_records):,} rows")
        else:
            print(f"\n   Warning: DB not found: {db_path}")

    # 4. Reconciliation
    in_csv_only = csv_ids - colppy_ids
    in_colppy_only = colppy_ids - csv_ids
    in_both = csv_ids & colppy_ids

    print("\n" + "-" * 60)
    print("RECONCILIATION SUMMARY (CSV vs Colppy)")
    print("-" * 60)
    print(f"   In both:              {len(in_both):,}")
    print(f"   In CSV only:          {len(in_csv_only):,} (in CSV but not in Colppy)")
    print(f"   In Colppy only:       {len(in_colppy_only):,} (in Colppy but not in CSV)")

    # 5. In CSV only - likely churned
    if in_csv_only:
        print("\n--- In CSV only (id_empresa in CSV but not in Colppy) ---")
        print("   These may be churned or have fechaBaja set in Colppy.")
        sample = sorted(in_csv_only, key=lambda x: int(x) if x.isdigit() else 0)[:10]
        for ie in sample:
            r = csv_by_id[ie]
            print(f"   {ie}: {r.get('plan','')} | {r.get('amount','')} | {r.get('email','')[:40]}")

    # 6. In Colppy only - CSV may be filtered
    if in_colppy_only:
        print("\n--- In Colppy only (id_empresa in Colppy but not in CSV) ---")
        print("   CSV may be a filtered export (e.g. excluding Pendiente de Pago).")
        # Sample by plan
        pendiente = [ie for ie in in_colppy_only if colppy_by_id.get(ie, {}).get("plan") == "Pendiente de Pago"]
        other = [ie for ie in in_colppy_only if ie not in pendiente]
        print(f"   Of these: {len(pendiente):,} with plan 'Pendiente de Pago', {len(other):,} other")
        sample = sorted(
            (ie for ie in other if ie and ie.isdigit() and int(ie) > 0),
            key=lambda x: int(x),
        )[:5]
        for ie in sample:
            r = colppy_by_id[ie]
            print(f"   {ie}: {r.get('plan','')} | {r.get('amount','')} | {r.get('razonSocial','')[:35]}")

    # 7. In both - compare
    diffs = []
    for ie in in_both:
        c = csv_by_id[ie]
        p = colppy_by_id[ie]
        diff = []
        if (c.get("plan") or "").strip() != (p.get("plan") or "").strip():
            diff.append(f"plan:{c.get('plan','')} vs {p.get('plan','')}")
        if (c.get("id_plan") or "").strip() != (p.get("id_plan") or "").strip():
            diff.append(f"id_plan:{c.get('id_plan','')} vs {p.get('id_plan','')}")
        if (c.get("amount") or "").strip() != (p.get("amount") or "").strip():
            diff.append(f"amount:{c.get('amount','')} vs {p.get('amount','')}")
        cust_c = normalize_cuit(c.get("customer_cuit") or "") or c.get("customer_cuit", "")
        cust_p = normalize_cuit(p.get("customer_cuit") or "") or p.get("customer_cuit", "")
        if cust_c != cust_p:
            diff.append(f"customer_cuit differs")
        prod_c = normalize_cuit(c.get("product_cuit") or "") or c.get("product_cuit", "")
        prod_p = normalize_cuit(p.get("product_cuit") or "") or p.get("product_cuit", "")
        if prod_c != prod_p:
            diff.append(f"product_cuit differs")
        if diff:
            diffs.append((ie, c, p, diff))

    if diffs:
        print("\n--- In both but with differences ---")
        print(f"   {len(diffs):,} rows with plan/amount/cuit mismatches")
        for ie, c, p, diff in diffs[:10]:
            print(f"   {ie}: {diff}")
    else:
        print("\n--- In both: no plan/amount/cuit differences ---")

    # Log to SQLite for progress tracking
    if log_to_db and log_db_path:
        try:
            from tools.utils.reconciliation_logger import log_reconciliation
            log_reconciliation(
                db_path=log_db_path,
                script="reconcile_facturacion_colppy",
                reconciliation_type="facturacion_csv_colppy",
                period=None,
                match_count=len(in_both),
                source_a_total=len(csv_ids),
                source_b_total=len(colppy_ids),
                source_a_only_count=len(in_csv_only),
                source_b_only_count=len(in_colppy_only),
                match_ids=sorted(in_both, key=lambda x: int(x) if x.isdigit() else 0),
                source_a_only_ids=sorted(in_csv_only, key=lambda x: int(x) if x.isdigit() else 0),
                source_b_only_ids=sorted(in_colppy_only, key=lambda x: int(x) if x.isdigit() else 0),
                source_metadata={
                    "csv_path": str(csv_path),
                    "use_local_colppy": use_local,
                    "include_db": include_db,
                },
                extra={"diffs_count": len(diffs)} if diffs else None,
            )
            print(f"\nReconciliation logged to {log_db_path}")
        except Exception as e:
            print(f"\nWarning: Could not log reconciliation: {e}")

    # 8. DB vs CSV (if included)
    if include_db and db_by_id:
        db_ids = set(db_by_id.keys())
        db_only = db_ids - csv_ids
        csv_only_db = csv_ids - db_ids
        print("\n" + "-" * 60)
        print("DB vs CSV (facturacion_hubspot.db vs facturacion.csv)")
        print("-" * 60)
        print(f"   In DB only:           {len(db_only):,}")
        print(f"   In CSV only (vs DB):  {len(csv_only_db):,}")
        if len(db_only) != len(csv_only_db) or db_ids != csv_ids:
            print("   Note: Run build_facturacion_hubspot_mapping.py to sync DB from CSV.")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile facturacion.csv, facturacion_hubspot.db, and Colppy MySQL"
    )
    parser.add_argument(
        "--csv",
        default=DEFAULT_CSV,
        help=f"Path to facturacion.csv (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"Path to facturacion_hubspot.db (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--include-db",
        action="store_true",
        help="Also compare facturacion_hubspot.db with CSV",
    )
    parser.add_argument(
        "--export-colppy",
        metavar="PATH",
        help="Export Colppy facturacion to CSV at given path",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local colppy_export.db instead of MySQL",
    )
    parser.add_argument(
        "--local-db",
        default=DEFAULT_COLPPY_DB,
        help=f"Path to colppy_export.db (default: {DEFAULT_COLPPY_DB})",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Skip logging to facturacion_hubspot.db",
    )
    args = parser.parse_args()

    run_reconciliation(
        csv_path=args.csv,
        db_path=args.db,
        include_db=args.include_db,
        export_colppy_path=args.export_colppy,
        use_local=args.local,
        local_colppy_db=args.local_db,
        log_to_db=not args.no_log,
    )


if __name__ == "__main__":
    main()
