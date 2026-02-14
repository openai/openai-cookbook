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
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --limit 100
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --dry-run
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --csv  # also export CSV
"""
import argparse
import csv
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}
DEFAULT_FACTURACION = "tools/outputs/facturacion.csv"
DEFAULT_DB = "tools/outputs/facturacion_hubspot.db"
DEFAULT_CSV = "tools/outputs/facturacion_hubspot_mapping.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    cuit            TEXT,
    cuit_display    TEXT,
    hubspot_id      TEXT,
    name            TEXT,
    type            TEXT,
    PRIMARY KEY (cuit, hubspot_id)
);

CREATE TABLE IF NOT EXISTS deals (
    id_empresa      TEXT PRIMARY KEY,
    hubspot_id      TEXT,
    deal_name       TEXT,
    deal_stage      TEXT,
    amount          TEXT,
    close_date      TEXT
);

CREATE TABLE IF NOT EXISTS facturacion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT,
    customer_cuit   TEXT,
    plan            TEXT,
    id_plan         TEXT,
    amount          TEXT,
    product_cuit    TEXT,
    id_empresa      TEXT,
    self_billed     INTEGER DEFAULT 0,
    FOREIGN KEY (customer_cuit) REFERENCES companies(cuit),
    FOREIGN KEY (id_empresa)    REFERENCES deals(id_empresa)
);

CREATE TABLE IF NOT EXISTS deal_associations (
    deal_hubspot_id     TEXT,
    company_hubspot_id  TEXT,
    association_type_id INTEGER,
    association_category TEXT,
    PRIMARY KEY (deal_hubspot_id, company_hubspot_id, association_type_id)
);

CREATE INDEX IF NOT EXISTS idx_facturacion_cuit ON facturacion(customer_cuit);
CREATE INDEX IF NOT EXISTS idx_facturacion_id_empresa ON facturacion(id_empresa);
CREATE INDEX IF NOT EXISTS idx_companies_hubspot_id ON companies(hubspot_id);
CREATE INDEX IF NOT EXISTS idx_deals_hubspot_id ON deals(hubspot_id);
CREATE INDEX IF NOT EXISTS idx_deal_assoc_deal ON deal_associations(deal_hubspot_id);
CREATE INDEX IF NOT EXISTS idx_deal_assoc_company ON deal_associations(company_hubspot_id);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_cuit(raw: str) -> str | None:
    """Normalize CUIT to 11 digits."""
    if not raw or str(raw).strip().upper() in ("#N/A", "N/A", ""):
        return None
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    if len(digits) != 11 or not digits.isdigit() or digits in EXCLUDE_CUITS:
        return None
    return digits


def format_cuit_display(digits: str) -> str:
    """Format 11 digits as XX-XXXXXXXX-X."""
    if not digits or len(digits) != 11:
        return str(digits)
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"


# ---------------------------------------------------------------------------
# Load facturacion CSV
# ---------------------------------------------------------------------------

def load_facturacion(path: str) -> list[dict]:
    """Load facturacion CSV including IdEmpresa column (col 7)."""
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
        self_billed = 1 if customer_cuit and product_cuit and customer_cuit == product_cuit else 0
        records.append({
            "email": parts[0].strip(),
            "customer_cuit": customer_cuit,
            "plan": parts[2].strip(),
            "id_plan": parts[3].strip() if len(parts) > 3 else "",
            "amount": parts[4].strip(),
            "product_cuit": product_cuit,
            "id_empresa": id_empresa,
            "self_billed": self_billed,
        })
    return records


# ---------------------------------------------------------------------------
# HubSpot API fetchers
# ---------------------------------------------------------------------------

def fetch_companies_by_cuit(client, cuits: set[str], delay: float = 0.3) -> dict[str, list[dict]]:
    """Batch-search companies by cuit IN (25/request). Returns CUIT -> list of all companies (no dedup)."""
    cuit_list = sorted(cuits)
    cuit_to_companies: dict[str, list[dict]] = {}
    batch_size = 25
    total_batches = (len(cuit_list) + batch_size - 1) // batch_size

    for i in range(0, len(cuit_list), batch_size):
        batch = cuit_list[i : i + batch_size]
        values = [format_cuit_display(c) for c in batch] + list(batch)
        values = list(dict.fromkeys(values))
        try:
            resp = client.search_objects(
                object_type="companies",
                filter_groups=[{"filters": [{"propertyName": "cuit", "operator": "IN", "values": values}]}],
                properties=["name", "cuit", "type", "hs_object_id"],
                limit=100,
            )
            for r in resp.get("results", []):
                n = normalize_cuit(r.get("properties", {}).get("cuit"))
                if n:
                    if n not in cuit_to_companies:
                        cuit_to_companies[n] = []
                    # Avoid duplicate hubspot_id per CUIT
                    ids_seen = {x.get("id") for x in cuit_to_companies[n]}
                    if r.get("id") not in ids_seen:
                        cuit_to_companies[n].append(r)
        except Exception as e:
            bn = i // batch_size + 1
            print(f"  Warning: Company batch {bn}/{total_batches} failed: {e}")
        time.sleep(delay)

    return cuit_to_companies


def fetch_deals_by_id_empresa(client, id_empresas: set[str], delay: float = 0.25) -> dict[str, dict]:
    """Batch-search deals by id_empresa IN (100/request). Returns id_empresa -> deal."""
    valid_ids = sorted({x for x in id_empresas if x and x.isdigit()})
    id_to_deal = {}
    batch_size = 100
    total_batches = (len(valid_ids) + batch_size - 1) // batch_size

    for i in range(0, len(valid_ids), batch_size):
        batch = valid_ids[i : i + batch_size]
        try:
            resp = client.search_objects(
                object_type="deals",
                filter_groups=[{"filters": [{"propertyName": "id_empresa", "operator": "IN", "values": batch}]}],
                properties=["dealname", "id_empresa", "dealstage", "amount", "closedate", "hs_object_id"],
                limit=100,
            )
            for r in resp.get("results", []):
                raw = (r.get("properties", {}).get("id_empresa") or "").strip()
                if raw and raw not in id_to_deal:
                    id_to_deal[raw] = r
        except Exception as e:
            bn = i // batch_size + 1
            print(f"  Warning: Deal batch {bn}/{total_batches} failed: {e}")
        time.sleep(delay)

    return id_to_deal


# ---------------------------------------------------------------------------
# SQLite operations
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    """Create or open database and apply schema."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def populate_companies(conn: sqlite3.Connection, cuit_to_companies: dict[str, list[dict]]):
    """Insert/replace companies into SQLite. Stores ALL companies per CUIT (multiple rows per cuit)."""
    # Recreate table to support (cuit, hubspot_id) as PK (multiple companies per CUIT)
    conn.execute("DROP TABLE IF EXISTS companies")
    conn.execute("""
        CREATE TABLE companies (
            cuit TEXT, cuit_display TEXT, hubspot_id TEXT, name TEXT, type TEXT,
            PRIMARY KEY (cuit, hubspot_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_companies_hubspot_id ON companies(hubspot_id)")
    rows = []
    for cuit, companies in cuit_to_companies.items():
        for c in companies:
            props = c.get("properties", {})
            rows.append((
                cuit,
                format_cuit_display(cuit),
                str(c.get("id", "")),
                props.get("name", ""),
                props.get("type", ""),
            ))
    conn.executemany(
        "INSERT OR REPLACE INTO companies (cuit, cuit_display, hubspot_id, name, type) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def populate_deals(conn: sqlite3.Connection, id_to_deal: dict[str, dict]):
    """Insert/replace deals into SQLite."""
    rows = []
    for id_emp, d in id_to_deal.items():
        if not d:
            continue
        props = d.get("properties", {})
        rows.append((
            id_emp,
            d.get("id", ""),
            props.get("dealname", ""),
            props.get("dealstage", ""),
            props.get("amount", ""),
            props.get("closedate", ""),
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO deals (id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def populate_facturacion(conn: sqlite3.Connection, records: list[dict]):
    """Insert facturacion rows (clears existing first)."""
    conn.execute("DELETE FROM facturacion")
    rows = [
        (r["email"], r["customer_cuit"], r["plan"], r["id_plan"], r["amount"],
         r["product_cuit"], r["id_empresa"], r["self_billed"])
        for r in records
    ]
    conn.executemany(
        "INSERT INTO facturacion (email, customer_cuit, plan, id_plan, amount, product_cuit, id_empresa, self_billed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def print_summary(conn: sqlite3.Connection):
    """Print summary stats from the database."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total = conn.execute("SELECT COUNT(*) FROM facturacion").fetchone()[0]
    companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    deals = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]

    both = conn.execute("""
        SELECT COUNT(DISTINCT f.id) FROM facturacion f
        JOIN companies c ON f.customer_cuit = c.cuit
        JOIN deals d ON f.id_empresa = d.id_empresa
    """).fetchone()[0]

    company_only = conn.execute("""
        SELECT COUNT(DISTINCT f.id) FROM facturacion f
        JOIN companies c ON f.customer_cuit = c.cuit
        LEFT JOIN deals d ON f.id_empresa = d.id_empresa
        WHERE d.id_empresa IS NULL
    """).fetchone()[0]

    deal_only = conn.execute("""
        SELECT COUNT(DISTINCT f.id) FROM facturacion f
        LEFT JOIN companies c ON f.customer_cuit = c.cuit
        JOIN deals d ON f.id_empresa = d.id_empresa
        WHERE c.cuit IS NULL
    """).fetchone()[0]

    neither = conn.execute("""
        SELECT COUNT(DISTINCT f.id) FROM facturacion f
        LEFT JOIN companies c ON f.customer_cuit = c.cuit
        LEFT JOIN deals d ON f.id_empresa = d.id_empresa
        WHERE c.cuit IS NULL AND d.id_empresa IS NULL
    """).fetchone()[0]

    self_billed = conn.execute("SELECT COUNT(*) FROM facturacion WHERE self_billed = 1").fetchone()[0]
    intermediary = conn.execute("SELECT COUNT(*) FROM facturacion WHERE self_billed = 0").fetchone()[0]

    print(f"\n  Facturacion rows:  {total:,}")
    print(f"  Companies (unique): {companies:,}")
    print(f"  Deals (unique):     {deals:,}")
    print(f"\n  Company + Deal found: {both:,} ({both/total*100:.1f}%)")
    print(f"  Company only:         {company_only:,} ({company_only/total*100:.1f}%)")
    print(f"  Deal only:            {deal_only:,} ({deal_only/total*100:.1f}%)")
    print(f"  Neither found:        {neither:,} ({neither/total*100:.1f}%)")
    print(f"\n  Self-billed:          {self_billed:,} ({self_billed/total*100:.1f}%)")
    print(f"  Intermediary:         {intermediary:,} ({intermediary/total*100:.1f}%)")

    # Company type breakdown (one row per cuit)
    print("\n  Company type breakdown:")
    type_rows = conn.execute("""
        SELECT c.type, COUNT(DISTINCT f.customer_cuit) AS cnt
        FROM facturacion f
        JOIN companies c ON f.customer_cuit = c.cuit
        GROUP BY c.type
        ORDER BY cnt DESC
    """).fetchall()
    for t, cnt in type_rows:
        label = t if t else "(empty)"
        print(f"    {label}: {cnt:,}")

    # Deal stage breakdown
    print("\n  Deal stage breakdown:")
    stage_rows = conn.execute("""
        SELECT d.deal_stage, COUNT(*) AS cnt
        FROM facturacion f
        JOIN deals d ON f.id_empresa = d.id_empresa
        GROUP BY d.deal_stage
        ORDER BY cnt DESC
    """).fetchall()
    for s, cnt in stage_rows:
        label = s if s else "(empty)"
        print(f"    {label}: {cnt:,}")

    print()


def export_csv(conn: sqlite3.Connection, csv_path: str):
    """Export the full mapping as a flat CSV for easy viewing. Picks one company per CUIT."""
    query = """
        SELECT
            f.email,
            COALESCE(c.cuit_display, f.customer_cuit) AS customer_cuit,
            f.plan,
            f.id_plan,
            f.amount,
            f.product_cuit,
            f.id_empresa,
            CASE WHEN f.self_billed = 1 THEN 'yes' ELSE 'no' END AS self_billed,
            COALESCE(c.hubspot_id, '') AS billing_company_id,
            COALESCE(c.name, '') AS billing_company_name,
            COALESCE(c.type, '') AS billing_company_type,
            COALESCE(d.hubspot_id, '') AS deal_id,
            COALESCE(d.deal_name, '') AS deal_name,
            COALESCE(d.deal_stage, '') AS deal_stage,
            COALESCE(d.amount, '') AS deal_amount,
            CASE WHEN c.cuit IS NOT NULL THEN 'yes' ELSE 'no' END AS company_found,
            CASE WHEN d.id_empresa IS NOT NULL THEN 'yes' ELSE 'no' END AS deal_found
        FROM facturacion f
        LEFT JOIN companies c ON f.customer_cuit = c.cuit
            AND c.hubspot_id = (SELECT MIN(c2.hubspot_id) FROM companies c2 WHERE c2.cuit = f.customer_cuit)
        LEFT JOIN deals d ON f.id_empresa = d.id_empresa
        ORDER BY f.id
    """
    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(columns)
        writer.writerows(rows)

    print(f"  Exported CSV: {csv_path} ({len(rows):,} rows)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
    args = parser.parse_args()

    from tools.hubspot_api.client import get_hubspot_client
    client = get_hubspot_client()

    print("=" * 70)
    print("BUILD FACTURACION–HUBSPOT MAPPING (SQLite)")
    print("=" * 70)

    facturacion_path = Path(args.facturacion)
    if not facturacion_path.exists():
        print(f"\nERROR: File not found: {facturacion_path}")
        return 1

    records = load_facturacion(str(facturacion_path))
    if args.limit:
        records = records[: args.limit]
    print(f"\nFacturacion rows: {len(records):,}")

    customer_cuits = {r["customer_cuit"] for r in records if r["customer_cuit"]}
    id_empresas = {r["id_empresa"] for r in records if r["id_empresa"]}
    print(f"Unique billing CUITs: {len(customer_cuits):,}")
    print(f"Unique id_empresa:    {len(id_empresas):,}")

    # Phase 1: Companies
    print(f"\n--- Phase 1: Companies by billing CUIT ({len(customer_cuits):,}) ---")
    cuit_to_company = fetch_companies_by_cuit(client, customer_cuits, delay=args.delay)
    print(f"  Found: {len(cuit_to_company):,} | Missing: {len(customer_cuits) - len(cuit_to_company):,}")

    # Phase 2: Deals
    print(f"\n--- Phase 2: Deals by id_empresa ({len(id_empresas):,}) ---")
    id_to_deal = fetch_deals_by_id_empresa(client, id_empresas, delay=args.delay)
    print(f"  Found: {len(id_to_deal):,} | Missing: {len(id_empresas) - len(id_to_deal):,}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would write to {args.db}")
        return 0

    # Phase 3: Populate SQLite
    print(f"\n--- Phase 3: Writing SQLite ({args.db}) ---")
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(str(db_path))

    populate_companies(conn, cuit_to_company)
    total_companies = sum(len(v) for v in cuit_to_company.values())
    print(f"  companies: {total_companies:,} rows ({len(cuit_to_company):,} unique CUITs)")

    populate_deals(conn, id_to_deal)
    print(f"  deals:     {len(id_to_deal):,} rows")

    populate_facturacion(conn, records)
    print(f"  facturacion: {len(records):,} rows")

    # Summary
    print_summary(conn)

    # Optional CSV export
    if args.csv:
        export_csv(conn, args.csv_path)

    conn.close()
    print(f"Database: {db_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
