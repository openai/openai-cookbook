"""
SQLite operations for facturacion–HubSpot mapping.
"""
import csv
import sqlite3
from pathlib import Path

from .hubspot_build_fetchers import format_cuit_display, normalize_cuit


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


def restore_facturacion_from_mapping(mapping_path: str, out_path: str) -> int:
    """
    Rebuild facturacion.csv from facturacion_hubspot_mapping.csv.
    Use when facturacion.csv was accidentally overwritten or corrupted.
    Returns number of rows written.
    """
    mapping_p = Path(mapping_path)
    if not mapping_p.exists():
        raise FileNotFoundError(f"Mapping file not found: {mapping_path}")
    records = []
    with open(mapping_p, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        cols = ["email", "customer_cuit", "plan", "id_plan", "amount", "product_cuit", "id_empresa"]
        for r in reader:
            records.append([r.get(c, "") for c in cols])
    header = "Email;Customer Cuit;Plan;Id Plan;Amount;Product CUIT;Id Empresa"
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8", newline="") as f:
        f.write(header + "\n")
        for row in records:
            f.write(";".join(str(x) for x in row) + "\n")
    return len(records)


def _get_deal_id_plan(props: dict) -> str:
    """Get id_plan from deal; HubSpot uses colppy_plan (internal name for id_plan). Can be blank."""
    return (props.get("colppy_plan") or props.get("id_plan") or "").strip()


def _get_deal_fecha_primer_pago(props: dict) -> str:
    """Get fecha_primer_pago from deal. Can be blank."""
    v = (props.get("fecha_primer_pago") or "").strip()
    return v[:10] if v else ""


def _ensure_deals_has_id_plan(conn: sqlite3.Connection) -> None:
    """Add id_plan column to deals if missing (migration)."""
    try:
        conn.execute("ALTER TABLE deals ADD COLUMN id_plan TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _ensure_deals_has_fecha_primer_pago(conn: sqlite3.Connection) -> None:
    """Add fecha_primer_pago column to deals if missing (migration)."""
    try:
        conn.execute("ALTER TABLE deals ADD COLUMN fecha_primer_pago TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _ensure_deals_any_stage_has_id_plan(conn: sqlite3.Connection) -> None:
    """Add id_plan column to deals_any_stage if missing (migration)."""
    try:
        conn.execute("ALTER TABLE deals_any_stage ADD COLUMN id_plan TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _ensure_deals_any_stage_has_fecha_primer_pago(conn: sqlite3.Connection) -> None:
    """Add fecha_primer_pago column to deals_any_stage if missing (migration)."""
    try:
        conn.execute("ALTER TABLE deals_any_stage ADD COLUMN fecha_primer_pago TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def populate_companies(conn: sqlite3.Connection, cuit_to_companies: dict[str, list[dict]]) -> None:
    """Insert/replace companies into SQLite. Stores ALL companies per CUIT (multiple rows per cuit)."""
    conn.execute("DROP TABLE IF EXISTS companies")
    conn.execute("""
        CREATE TABLE companies (
            cuit TEXT, cuit_display TEXT, hubspot_id TEXT, name TEXT, type TEXT,
            tipo_icp_contador TEXT,
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
                props.get("tipo_icp_contador", "") or "",
            ))
    conn.executemany(
        "INSERT OR REPLACE INTO companies (cuit, cuit_display, hubspot_id, name, type, tipo_icp_contador) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def populate_deals(conn: sqlite3.Connection, id_to_deal: dict[str, dict]) -> None:
    """Insert/replace deals into SQLite."""
    _ensure_deals_has_id_plan(conn)
    _ensure_deals_has_fecha_primer_pago(conn)
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
            _get_deal_id_plan(props),
            _get_deal_fecha_primer_pago(props),
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO deals (id_empresa, hubspot_id, deal_name, deal_stage, amount, close_date, id_plan, fecha_primer_pago) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def populate_facturacion(conn: sqlite3.Connection, records: list[dict]) -> None:
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


def print_summary(conn: sqlite3.Connection) -> None:
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

    if total == 0:
        print("\n  Facturacion rows: 0 (no data to summarize)")
        return

    print(f"\n  Facturacion rows:  {total:,}")
    print(f"  Companies (unique): {companies:,}")
    print(f"  Deals (unique):     {deals:,}")
    print(f"\n  Company + Deal found: {both:,} ({both/total*100:.1f}%)")
    print(f"  Company only:         {company_only:,} ({company_only/total*100:.1f}%)")
    print(f"  Deal only:            {deal_only:,} ({deal_only/total*100:.1f}%)")
    print(f"  Neither found:        {neither:,} ({neither/total*100:.1f}%)")
    print(f"\n  Self-billed:          {self_billed:,} ({self_billed/total*100:.1f}%)")
    print(f"  Intermediary:         {intermediary:,} ({intermediary/total*100:.1f}%)")

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


def export_csv(conn: sqlite3.Connection, csv_path: str) -> None:
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
            AND c.hubspot_id = (
                SELECT c2.hubspot_id FROM companies c2
                WHERE c2.cuit = f.customer_cuit AND c2.hubspot_id != ''
                ORDER BY CASE WHEN c2.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado') THEN 0 ELSE 1 END,
                         c2.hubspot_id
                LIMIT 1
            )
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
