#!/usr/bin/env python3
"""
Build Facturacion–HubSpot Mapping (SQLite)
==========================================
Maps facturacion rows to HubSpot companies and deals, stores in SQLite DB.

Tables:
- companies: one row per billing company (by cuit)
- deals: one row per deal (by id_empresa)
- facturacion: billing relationships (customer_cuit → id_empresa)
- deal_associations: current HubSpot deal–company associations (populated separately)

Two-phase API fetching:
1. Batch-search companies by cuit IN (25/request)
2. Batch-search deals by id_empresa IN (100/request)

Usage:
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --csv  # also export mapping (backup)
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --limit 100
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --dry-run
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --restore-from-mapping tools/outputs/facturacion_hubspot_mapping.csv  # recovery
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year 2026 --month 1  # timeframe-only refresh
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year 2026 --month 2 --fetch-wrong-stage  # also populate deals_any_stage

Full build clears deals and repopulates from facturacion; run --refresh-deals-only for each month needed.
Use --fetch-wrong-stage when running reconciliation to detect Colppy-only cases where the deal exists but has wrong stage.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

DEFAULT_FACTURACION = "tools/outputs/facturacion.csv"
DEFAULT_DB = "tools/data/facturacion_hubspot.db"
DEFAULT_CSV = "tools/outputs/facturacion_hubspot_mapping.csv"
MIN_FACTURACION_ROWS = 50


def main():
    parser = argparse.ArgumentParser(
        description="Build facturacion–HubSpot mapping (SQLite + optional CSV export)"
    )
    parser.add_argument("--facturacion", default=DEFAULT_FACTURACION, help="Path to facturacion.csv")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--csv", action="store_true", help="Also export flat CSV")
    parser.add_argument("--csv-path", default=DEFAULT_CSV, help="CSV export path")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between API calls (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Only analyze, do not write")
    parser.add_argument("--limit", type=int, default=0, help="Limit rows (0 = all)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass minimum row validation (use only for small test datasets)",
    )
    parser.add_argument(
        "--restore-from-mapping",
        metavar="MAPPING_CSV",
        help="Rebuild facturacion.csv from facturacion_hubspot_mapping.csv and exit (recovery)",
    )
    parser.add_argument(
        "--reconcile-no-deal",
        action="store_true",
        help="List id_empresa in facturacion with no HubSpot deal (requires existing DB)",
    )
    parser.add_argument(
        "--refresh-deals-only",
        action="store_true",
        help="Only refresh deals table for given month (requires --year and --month)",
    )
    parser.add_argument("--year", type=str, help="Year for timeframe refresh (e.g. 2026)")
    parser.add_argument("--month", type=int, help="Month 1-12 for timeframe refresh")
    parser.add_argument(
        "--fetch-wrong-stage",
        action="store_true",
        help="Also fetch deals (any stage) for Colppy-only id_empresas; populates deals_any_stage",
    )
    parser.add_argument(
        "--colppy-db",
        type=str,
        default="tools/data/colppy_export.db",
        help="Path to colppy_export.db (for --fetch-wrong-stage)",
    )
    args = parser.parse_args()

    if args.refresh_deals_only:
        if not args.year or not args.month:
            parser.error("--refresh-deals-only requires --year and --month")
        return _run_refresh_deals_only(args)

    if args.reconcile_no_deal:
        return _run_reconcile_no_deal(args)

    if args.restore_from_mapping:
        return _run_restore_from_mapping(args)

    return _run_full_build(args)


def _run_refresh_deals_only(args) -> int:
    """Refresh deals table for given month, optionally populate deals_any_stage."""
    from tools.scripts.hubspot.hubspot_build_refresh import run_refresh_deals_only

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"\nERROR: Database not found: {db_path}")
        print("Run full build first (without --refresh-deals-only).")
        return 1

    colppy_db_path = Path(args.colppy_db)
    if not colppy_db_path.is_absolute():
        colppy_db_path = Path(__file__).resolve().parents[3] / colppy_db_path

    return run_refresh_deals_only(
        db_path=db_path,
        year=args.year,
        month=args.month,
        fetch_wrong_stage=args.fetch_wrong_stage,
        colppy_db_path=colppy_db_path,
    )


def _run_reconcile_no_deal(args) -> int:
    """List id_empresa with no HubSpot deal."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"\nERROR: Database not found: {db_path}")
        return 1
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("""
            SELECT f.id_empresa, f.plan, f.amount, f.customer_cuit, f.email
            FROM facturacion f
            LEFT JOIN deals d ON f.id_empresa = d.id_empresa
            WHERE d.id_empresa IS NULL AND f.id_empresa != '' AND f.id_empresa IS NOT NULL
            GROUP BY f.id_empresa
            ORDER BY CAST(f.amount AS REAL) DESC
        """).fetchall()
        total_amount = conn.execute("""
            SELECT SUM(CAST(x.amount AS REAL)) FROM (
                SELECT f.id_empresa, MAX(f.amount) as amount
                FROM facturacion f
                LEFT JOIN deals d ON f.id_empresa = d.id_empresa
                WHERE d.id_empresa IS NULL AND f.id_empresa != '' AND f.id_empresa IS NOT NULL
                GROUP BY f.id_empresa
            ) x
        """).fetchone()[0] or 0
    print(f"\nReconcile: id_empresa with no HubSpot deal: {len(rows):,}")
    print(f"Total amount (one per id_empresa): ${total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    print("\nid_empresa | plan | amount | customer_cuit | email")
    print("-" * 80)
    for r in rows[:50]:
        amt = str(r[2]) if r[2] else ""
        print(f"{r[0]} | {r[1] or ''} | {amt} | {r[3] or ''} | {r[4] or ''}")
    if len(rows) > 50:
        print(f"... and {len(rows) - 50} more")
    print()
    return 0


def _run_restore_from_mapping(args) -> int:
    """Rebuild facturacion.csv from mapping CSV."""
    from tools.scripts.hubspot.hubspot_build_sqlite import restore_facturacion_from_mapping

    try:
        n = restore_facturacion_from_mapping(args.restore_from_mapping, args.facturacion)
        print(f"Restored facturacion.csv: {n:,} rows from {args.restore_from_mapping}")
        return 0
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        return 1


def _run_full_build(args) -> int:
    """Full build: load facturacion, fetch companies/deals, populate SQLite."""
    from tools.hubspot_api.client import get_hubspot_client
    from tools.scripts.hubspot.hubspot_build_fetchers import fetch_companies_by_cuit, fetch_deals_by_id_empresa
    from tools.scripts.hubspot.hubspot_build_schema import init_db
    from tools.scripts.hubspot.hubspot_build_sqlite import (
        export_csv,
        load_facturacion,
        populate_companies,
        populate_deals,
        populate_facturacion,
        print_summary,
    )

    client = get_hubspot_client()

    print("=" * 70)
    print("BUILD FACTURACION–HUBSPOT MAPPING (SQLite)")
    print("=" * 70)

    facturacion_path = Path(args.facturacion)
    if not facturacion_path.exists():
        print(f"\nERROR: File not found: {facturacion_path}")
        return 1

    records = load_facturacion(str(facturacion_path))

    if len(records) < MIN_FACTURACION_ROWS and not args.force:
        mapping_path = Path(args.csv_path)
        print(f"\nERROR: facturacion.csv has only {len(records)} rows (minimum: {MIN_FACTURACION_ROWS})")
        print("This usually means the file was overwritten or corrupted.")
        if mapping_path.exists():
            print(f"\nRecovery: run with --restore-from-mapping to rebuild from backup:")
            print(f"  python {__file__} --restore-from-mapping {mapping_path}")
        print("\nTo bypass (small test dataset): use --force")
        return 1
    if args.limit:
        records = records[: args.limit]
    print(f"\nFacturacion rows: {len(records):,}")

    customer_cuits = {r["customer_cuit"] for r in records if r["customer_cuit"]}
    id_empresas = {r["id_empresa"] for r in records if r["id_empresa"]}
    print(f"Unique billing CUITs: {len(customer_cuits):,}")
    print(f"Unique id_empresa:    {len(id_empresas):,}")

    print(f"\n--- Phase 1: Companies by billing CUIT ({len(customer_cuits):,}) ---")
    cuit_to_company = fetch_companies_by_cuit(client, customer_cuits, delay=args.delay)
    print(f"  Found: {len(cuit_to_company):,} | Missing: {len(customer_cuits) - len(cuit_to_company):,}")

    print(f"\n--- Phase 2: Deals by id_empresa ({len(id_empresas):,}) ---")
    id_to_deal = fetch_deals_by_id_empresa(client, id_empresas, delay=args.delay)
    print(f"  Found: {len(id_to_deal):,} | Missing: {len(id_empresas) - len(id_to_deal):,}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would write to {args.db}")
        return 0

    print(f"\n--- Phase 3: Writing SQLite ({args.db}) ---")
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with init_db(str(db_path)) as conn:
        populate_companies(conn, cuit_to_company)
        total_companies = sum(len(v) for v in cuit_to_company.values())
        print(f"  companies: {total_companies:,} rows ({len(cuit_to_company):,} unique CUITs)")

        conn.execute("DELETE FROM deals")
        conn.commit()
        populate_deals(conn, id_to_deal)
        print(f"  deals:     {len(id_to_deal):,} rows")

        populate_facturacion(conn, records)
        print(f"  facturacion: {len(records):,} rows")

        print_summary(conn)

        if args.csv:
            export_csv(conn, args.csv_path)

        try:
            from tools.scripts.hubspot.edit_log_db import log_edit
            log_edit(
                conn,
                script="build_facturacion_hubspot_mapping",
                action="build",
                outcome="success",
                detail=f"companies: {total_companies:,}, deals: {len(id_to_deal):,}, facturacion: {len(records):,}",
            )
        except Exception as e:
            print(f"  Warning: Could not log to edit_logs: {e}", file=sys.stderr)
    print(f"Database: {db_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
