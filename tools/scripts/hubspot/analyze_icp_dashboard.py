#!/usr/bin/env python3
"""
Colppy ICP Dashboard (redirect)

This script now generates a redirect page to the MRR Dashboard, which includes
the company-wide ICP section (revenue by ICP, churn by ICP, churn by month).
Run analyze_accountant_mrr_matrix.py --html to build the full dashboard.

Legacy: Builds a redirect for Ideal Customer Profiles (ICP) so old links
(icp_dashboard.html) still work. The real content lives in mrr_dashboard.html#company-icp.

ICP definitions (from tools/docs/NPS_TO_ICP_DATA_FLOW.md and ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md):
- ICP Operador: tipo_icp_contador == "Operador" (empresa contadora que opera directamente)
- ICP Asesor: tipo_icp_contador == "Asesor" (empresa contadora que asesora)
- ICP Híbrido: tipo_icp_contador == "Híbrido" (empresa contadora híbrida)
- ICP Contador: type in (Cuenta Contador, Cuenta Contador y Reseller, Contador Robado) AND tipo_icp_contador empty
- ICP PYME: type == Cuenta Pyme (facturamos a la PyME)

Requires: facturacion_hubspot.db from build_facturacion_hubspot_mapping.py (with tipo_icp_contador).
Churn: Run populate_accountant_deals.py to include churned deals.
"""

import argparse
import os
import sqlite3
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

DEFAULT_DB = "tools/data/facturacion_hubspot.db"
ACCOUNTANT_TYPES = ("Cuenta Contador", "Cuenta Contador y Reseller", "Contador Robado")
ICP_ORDER = ("ICP Operador", "ICP Asesor", "ICP Híbrido", "ICP Contador", "ICP PYME")
# Churn = deal stage indicates customer left or no revenue (Cerrado Churn, Cerrado Perdido)
CHURN_STAGES = ("closedlost", "31849274")


def _ensure_tipo_icp_contador(conn: sqlite3.Connection) -> None:
    """Add tipo_icp_contador column if missing (for older DBs)."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()]
    if "tipo_icp_contador" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN tipo_icp_contador TEXT")


def get_icp_metrics(conn: sqlite3.Connection) -> dict:
    """Compute ICP-level metrics: paying customers, MRR, churn by ICP."""
    _ensure_tipo_icp_contador(conn)

    # Paying customers (unique CUITs billed)
    paying_customers = conn.execute(
        "SELECT COUNT(DISTINCT customer_cuit) FROM facturacion WHERE customer_cuit != ''"
    ).fetchone()[0]

    # Total MRR from facturacion directly (source of truth, no join - avoids double-counting)
    total_mrr_raw = conn.execute(
        "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM facturacion"
    ).fetchone()[0]

    # ICP classification per NPS_TO_ICP_DATA_FLOW.md: tipo_icp_contador (Operador/Asesor/Híbrido)
    # or type when tipo_icp_contador empty. Uses one company per CUIT to avoid double-counting.
    _icp_case = """
        CASE
            WHEN c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado') THEN
                CASE
                    WHEN COALESCE(c.tipo_icp_contador, '') = 'Operador' THEN 'ICP Operador'
                    WHEN COALESCE(c.tipo_icp_contador, '') = 'Asesor' THEN 'ICP Asesor'
                    WHEN COALESCE(c.tipo_icp_contador, '') = 'Híbrido' THEN 'ICP Híbrido'
                    ELSE 'ICP Contador'
                END
            ELSE 'ICP PYME'
        END
    """
    mrr_rows = conn.execute(f"""
        SELECT {_icp_case} AS icp,
            SUM(CAST(f.amount AS REAL)) AS mrr,
            COUNT(DISTINCT f.customer_cuit) AS unique_cuits
        FROM facturacion f
        JOIN companies c ON f.customer_cuit = c.cuit
          AND c.hubspot_id = (
            SELECT c2.hubspot_id FROM companies c2
            WHERE c2.cuit = f.customer_cuit AND c2.hubspot_id != ''
            ORDER BY CASE WHEN c2.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado') THEN 0 ELSE 1 END,
                     c2.hubspot_id
            LIMIT 1
          )
        WHERE f.customer_cuit != ''
        GROUP BY icp
    """).fetchall()

    mrr_by_icp = {r[0]: {"mrr": r[1], "unique_cuits": r[2]} for r in mrr_rows}

    # Churn: id_empresa NOT in facturacion + deal_stage in churn stages + primary company in billing set
    # close_date = when product stopped being paid
    churn_stage_placeholders = ",".join("?" * len(CHURN_STAGES))
    billed_cuit_subq = "SELECT DISTINCT customer_cuit FROM facturacion WHERE customer_cuit != ''"
    churn_base = """
        d.id_empresa != '' AND d.id_empresa NOT IN (SELECT id_empresa FROM facturacion WHERE id_empresa != '')
        AND d.deal_stage IN ({0})
    """.format(churn_stage_placeholders)

    churn_total = conn.execute(
        f"""
        SELECT COUNT(DISTINCT d.hubspot_id) FROM deals d
        JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
        JOIN companies c ON c.hubspot_id = da.company_hubspot_id
        WHERE c.cuit IN ({billed_cuit_subq}) AND {churn_base}
        """,
        CHURN_STAGES,
    ).fetchone()[0]

    # Churn by ICP (primary company type 5, same classification as MRR)
    churn_by_icp = conn.execute(
        f"""
        WITH churn_deals AS (
            SELECT d.hubspot_id
            FROM deals d
            JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
            JOIN companies c ON c.hubspot_id = da.company_hubspot_id
            WHERE c.cuit IN ({billed_cuit_subq}) AND d.id_empresa != ''
            AND d.id_empresa NOT IN (SELECT id_empresa FROM facturacion WHERE id_empresa != '')
            AND d.deal_stage IN ({churn_stage_placeholders})
        ),
        deal_primary AS (
            SELECT da.deal_hubspot_id, da.company_hubspot_id
            FROM deal_associations da
            WHERE da.association_type_id = 5
        )
        SELECT {_icp_case} AS icp, COUNT(*) AS churn_count
        FROM churn_deals cd
        JOIN deal_primary dp ON dp.deal_hubspot_id = cd.hubspot_id
        JOIN companies c ON c.hubspot_id = dp.company_hubspot_id
        GROUP BY icp
        """,
        CHURN_STAGES,
    ).fetchall()

    churn_icp = {r[0]: r[1] for r in churn_by_icp}

    # Churn by month (close_date = when product stopped being paid)
    churn_by_month = conn.execute(
        f"""
        SELECT strftime('%Y-%m', d.close_date) AS month, COUNT(*) AS cnt
        FROM deals d
        JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
        JOIN companies c ON c.hubspot_id = da.company_hubspot_id
        WHERE c.cuit IN ({billed_cuit_subq}) AND d.id_empresa != ''
        AND d.id_empresa NOT IN (SELECT id_empresa FROM facturacion WHERE id_empresa != '')
        AND d.deal_stage IN ({churn_stage_placeholders})
        AND d.close_date IS NOT NULL AND d.close_date != ''
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
        """,
        CHURN_STAGES,
    ).fetchall()

    # Active deals (id_empresa in facturacion)
    active_deals = conn.execute(
        """SELECT COUNT(*) FROM deals d
        WHERE d.id_empresa IN (SELECT id_empresa FROM facturacion WHERE id_empresa != '')"""
    ).fetchone()[0]

    # Churn rate: churn / (active + churn) for deals we track
    churn_rate = (churn_total / (active_deals + churn_total) * 100) if (active_deals + churn_total) else 0

    return {
        "paying_customers": paying_customers,
        "total_mrr": total_mrr_raw,
        "mrr_by_icp": mrr_by_icp,
        "churn_total": churn_total,
        "churn_by_icp": churn_icp,
        "churn_by_month": churn_by_month,
        "active_deals": active_deals,
        "churn_rate": churn_rate,
    }


def format_ars(val: float) -> str:
    """Format as ARS with Argentina conventions."""
    s = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${s}"


def generate_dashboard_html(metrics: dict) -> str:
    """Generate HTML dashboard for ICP metrics."""
    total_mrr = metrics["total_mrr"]
    mrr_by_icp = metrics["mrr_by_icp"]
    churn_by_icp = metrics["churn_by_icp"]

    # Build ICP cards in defined order (only those with data)
    icp_cards_html = ""
    for icp in ICP_ORDER:
        data = mrr_by_icp.get(icp, {})
        churn = churn_by_icp.get(icp, 0)
        mrr = data.get("mrr", 0)
        cuits = data.get("unique_cuits", 0)
        if mrr > 0 or cuits > 0 or churn > 0:
            icp_cards_html += f"""
            <div class="card">
                <h2>{icp}</h2>
                <div class="value">{format_ars(mrr)}</div>
                <div class="detail">{cuits:,} unique CUITs · {churn} churn deals</div>
            </div>"""

    # Churn table rows
    churn_rows_html = ""
    for icp in ICP_ORDER:
        cnt = churn_by_icp.get(icp, 0)
        if cnt > 0:
            churn_rows_html += f"""
                    <tr>
                        <td>{icp}</td>
                        <td class="num">{cnt}</td>
                    </tr>"""
    churn_rows_html += f"""
                    <tr>
                        <td><strong>Total</strong></td>
                        <td class="num"><strong>{metrics["churn_total"]}</strong></td>
                    </tr>"""

    # Churn by month
    churn_by_month_html = ""
    for row in metrics.get("churn_by_month", []):
        churn_by_month_html += f"""
                    <tr>
                        <td>{row[0]}</td>
                        <td class="num">{row[1]}</td>
                    </tr>"""
    if not churn_by_month_html:
        churn_by_month_html = """
                    <tr>
                        <td colspan="2">No churn with close_date in last 12 months</td>
                    </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Colppy - ICP Dashboard</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card: #1e293b;
            --accent: #3b82f6;
            --accent-dim: #1e40af;
            --text: #f1f5f9;
            --text-muted: #94a3b8;
            --success: #22c55e;
            --warning: #f59e0b;
            --border: #334155;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 8px; color: var(--text); }}
        .subtitle {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 24px; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid var(--border);
        }}
        .card h2 {{ font-size: 0.95rem; font-weight: 600; margin: 0 0 12px 0; color: var(--text-muted); }}
        .card .value {{ font-size: 1.5rem; font-weight: 700; color: var(--accent); }}
        .card .detail {{ font-size: 0.85rem; color: var(--text-muted); margin-top: 8px; }}
        .churn-card {{ border-left: 4px solid var(--warning); }}
        .table-card {{ grid-column: 1 / -1; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ font-weight: 600; color: var(--text-muted); }}
        .num {{ text-align: right; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Colppy ICP Dashboard</h1>
        <p class="subtitle">Paying customers, MRR, and churn by Ideal Customer Profile</p>

        <div class="grid">
            <div class="card">
                <h2>Paying Customers</h2>
                <div class="value">{metrics["paying_customers"]:,}</div>
                <div class="detail">Unique CUITs billed (no duplication)</div>
            </div>
            <div class="card">
                <h2>Total MRR</h2>
                <div class="value">{format_ars(total_mrr)}</div>
                <div class="detail">From facturacion (billing source of truth)</div>
            </div>
            <div class="card churn-card">
                <h2>Churn Deals</h2>
                <div class="value">{metrics["churn_total"]}</div>
                <div class="detail">Deal stage closedlost/31849274 · primary company in billing · {metrics["churn_rate"]:.1f}% churn rate</div>
            </div>
        </div>

        <div class="grid">
            {icp_cards_html}
        </div>
        <p class="detail" style="margin-bottom:16px;font-size:0.85rem">Total MRR comes from facturacion directly (no join). ICP uses tipo_icp_contador (Operador/Asesor/Híbrido) when set; else type (Cuenta Contador → ICP Contador, Cuenta Pyme → ICP PYME). See tools/docs/NPS_TO_ICP_DATA_FLOW.md.</p>

        <div class="card table-card">
            <h2>Churn by ICP</h2>
            <p class="detail" style="margin-bottom:12px">Churn = deals with deal_stage in (closedlost, 31849274), id_empresa NOT in facturacion, primary company in billing. close_date = when product stopped being paid.</p>
            <table>
                <thead>
                    <tr>
                        <th>ICP</th>
                        <th class="num">Churn Deals</th>
                    </tr>
                </thead>
                <tbody>
                    {churn_rows_html}
                </tbody>
            </table>
        </div>

        <div class="card table-card">
            <h2>Churn by Month (close_date)</h2>
            <p class="detail" style="margin-bottom:12px">When the product stopped being paid. Last 12 months.</p>
            <table>
                <thead>
                    <tr>
                        <th>Month</th>
                        <th class="num">Churn Deals</th>
                    </tr>
                </thead>
                <tbody>
                    {churn_by_month_html}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Colppy ICP Dashboard")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to facturacion_hubspot.db")
    parser.add_argument("--html", metavar="PATH", help="Generate HTML dashboard")
    parser.add_argument("--serve", action="store_true", help="Serve and open in browser")
    args = parser.parse_args()

    html_path = args.html or (Path("tools/outputs/icp_dashboard.html") if args.serve else None)
    if html_path:
        html_path = Path(html_path)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        # Redirect to MRR Dashboard (company-wide ICP section consolidated there)
        mrr_anchor = "mrr_dashboard.html#company-icp"
        redirect_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="0;url={mrr_anchor}">
  <title>Colppy ICP - Redirect</title>
  <style>body {{ font-family: system-ui; background: #0f172a; color: #f1f5f9; padding: 40px; }}</style>
</head>
<body>
  <p>ICP view is consolidated into the <a href="{mrr_anchor}">MRR Dashboard</a> (company-wide revenue by ICP).</p>
  <p>Redirecting to <a href="{mrr_anchor}">MRR Dashboard &rarr;</a></p>
</body>
</html>"""
        html_path.write_text(redirect_html, encoding="utf-8")
        print(f"Redirect page written to: {html_path.absolute()} (target: {mrr_anchor})")
        if args.serve:
            port = 8766
            os.chdir(html_path.parent)
            server = HTTPServer(("", port), SimpleHTTPRequestHandler)
            url = f"http://localhost:{port}/{html_path.name}"
            print(f"Opening {url}")
            webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0

    # Console output (still need DB)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(db_path))
    metrics = get_icp_metrics(conn)
    conn.close()
    print("\nICP Dashboard Metrics (company-wide; also in MRR Dashboard)")
    print("=" * 50)
    print(f"Paying customers (unique CUITs): {metrics['paying_customers']:,}")
    print(f"Churn deals: {metrics['churn_total']} (stage closedlost/31849274, billing companies only)")
    print(f"Churn rate: {metrics['churn_rate']:.1f}%")
    for icp, data in metrics["mrr_by_icp"].items():
        print(f"  {icp}: {format_ars(data['mrr'])} ({data['unique_cuits']} CUITs)")
    for icp, cnt in metrics["churn_by_icp"].items():
        print(f"  Churn {icp}: {cnt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
