#!/usr/bin/env python3
"""
Colppy Accountant Offices: MRR Matrix Analysis

Builds an MRR matrix (layout similar to Nubox). MRR only, not NRR. Focus: ACCOUNTANT PORTFOLIO BEHAVIOR
(not billing). Includes churned deals in portfolio counts.

- Rows (Y): Accountant's Client Portfolio Growth (%, from deal close dates)
- Columns (X): Accountant's Client Portfolio (# of Managed Tax IDs) = TOTAL portfolio
- Cells: MRR (sum of facturacion amount for accountants in that cell)

Accountant definition (ICP only):
- Type 8 (Estudio Contable) + Cuenta Contador types: asesor/advisor on deals
- Type 5 + Cuenta Contador types: billing to accountant (ICP Operador)
- Only companies with type IN (Cuenta Contador, Cuenta Contador y Reseller, Contador Robado)

Portfolio (includes churn):
- Total portfolio = ALL deals (active + churned) the accountant is associated with
- Active = id_empresa in facturacion (still paying)
- Churned = deal_stage Cerrado Churn (31849274) indicates customer left

Growth computed from deal close_date:
- Portfolio at beginning = deals closed in first 90 days (baseline)
- Active portfolio now = id_empresa in facturacion (current paying clients)
- Growth % = (active_now - portfolio_beginning) / portfolio_beginning * 100
- Negative growth = shrinking (churn exceeded new clients)

Requires: facturacion_hubspot.db from build_facturacion_hubspot_mapping.py

Churn: Run populate_accountant_deals.py to fetch deals associated with accountant
companies (including churned). This enriches the deals table with id_empresa not
in facturacion, enabling portfolio behavior analysis with churn.

When to run: To rebuild the dashboard, run this script with --html or --serve. No need
to re-run populate_accountant_deals.py if HubSpot data is unchanged. See
tools/docs/HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md section 6.
"""

import argparse
import os
import subprocess
import sqlite3
import sys
import time
import webbrowser
from typing import Optional
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DEFAULT_DB = "tools/outputs/facturacion_hubspot.db"
HUBSPOT_PORTAL_ID = "19877595"

# Only ICP accountant companies (Cuenta Contador types)
ICP_TYPES = ("Cuenta Contador", "Cuenta Contador y Reseller", "Contador Robado")

# Churn = deal stage Cerrado Churn only (31849274). Not closedlost (lost deal).
CHURN_STAGES = ("31849274",)

# Lost = deal stage Cerrado Perdido (closedlost). Deals that closed but generated no revenue.
LOST_STAGES = ("closedlost",)

# Company-wide ICP (all facturacion by tipo_icp_contador / type). Churn = closedlost + Cerrado Churn.
ICP_ORDER = ("ICP Operador", "ICP Asesor", "ICP Híbrido", "ICP Contador", "ICP PYME")
ICP_CHURN_STAGES = ("closedlost", "31849274")

# CAGR lookback: rolling window options (months). Default 24. User can switch in dashboard.
CAGR_LOOKBACK_MONTHS_OPTIONS = [6, 12, 18, 24, 36, 48]
CAGR_LOOKBACK_DEFAULT_MONTHS = 24

# Same format as Nubox slide
GROWTH_BUCKETS = [
    ("<-14%", lambda g: g < -14),
    ("-14% - 0%", lambda g: -14 <= g < 0),
    ("0% - +14%", lambda g: 0 <= g < 14),
    (">+14%", lambda g: g >= 14),
]

PORTFOLIO_BUCKETS = [
    (1, 1, "1"),
    (2, 2, "2"),
    (3, 5, "3-5"),
    (6, 10, "6-10"),
    (11, 20, "11-20"),
    (21, 40, "20-40"),
    (41, 100, "40-100"),
    (101, 200, "100-200"),
    (201, 99999, "200+"),
]


def _ensure_tipo_icp_contador(conn: sqlite3.Connection) -> None:
    """Add tipo_icp_contador column to companies if missing (for company-wide ICP)."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()]
    if "tipo_icp_contador" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN tipo_icp_contador TEXT")


def get_company_icp_metrics(conn: sqlite3.Connection) -> dict:
    """
    Company-wide metrics: paying customers, total MRR, churn by ICP type (Operador, Asesor, etc.).
    Used for the consolidated ICP section. Churn = deal_stage in (closedlost, 31849274).
    """
    _ensure_tipo_icp_contador(conn)
    ph = ",".join("?" * len(ICP_CHURN_STAGES))
    paying_customers = conn.execute(
        "SELECT COUNT(DISTINCT customer_cuit) FROM facturacion WHERE customer_cuit != ''"
    ).fetchone()[0]
    total_mrr_raw = conn.execute(
        "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM facturacion"
    ).fetchone()[0]
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
          AND c.hubspot_id = (SELECT MIN(c2.hubspot_id) FROM companies c2 WHERE c2.cuit = f.customer_cuit)
        WHERE f.customer_cuit != ''
        GROUP BY icp
    """).fetchall()
    mrr_by_icp = {r[0]: {"mrr": r[1], "unique_cuits": r[2]} for r in mrr_rows}
    billed_cuit_subq = "SELECT DISTINCT customer_cuit FROM facturacion WHERE customer_cuit != ''"
    churn_base = """
        d.id_empresa != '' AND d.id_empresa NOT IN (SELECT id_empresa FROM facturacion WHERE id_empresa != '')
        AND d.deal_stage IN ({0})
    """.format(ph)
    churn_total = conn.execute(
        f"""
        SELECT COUNT(DISTINCT d.hubspot_id) FROM deals d
        JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
        JOIN companies c ON c.hubspot_id = da.company_hubspot_id
        WHERE c.cuit IN ({billed_cuit_subq}) AND {churn_base}
        """,
        ICP_CHURN_STAGES,
    ).fetchone()[0]
    churn_by_icp_rows = conn.execute(
        f"""
        WITH churn_deals AS (
            SELECT d.hubspot_id
            FROM deals d
            JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
            JOIN companies c ON c.hubspot_id = da.company_hubspot_id
            WHERE c.cuit IN ({billed_cuit_subq}) AND d.id_empresa != ''
            AND d.id_empresa NOT IN (SELECT id_empresa FROM facturacion WHERE id_empresa != '')
            AND d.deal_stage IN ({ph})
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
        ICP_CHURN_STAGES,
    ).fetchall()
    churn_by_icp = {r[0]: r[1] for r in churn_by_icp_rows}
    churn_by_month = conn.execute(
        f"""
        SELECT strftime('%Y-%m', d.close_date) AS month, COUNT(*) AS cnt
        FROM deals d
        JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
        JOIN companies c ON c.hubspot_id = da.company_hubspot_id
        WHERE c.cuit IN ({billed_cuit_subq}) AND d.id_empresa != ''
        AND d.id_empresa NOT IN (SELECT id_empresa FROM facturacion WHERE id_empresa != '')
        AND d.deal_stage IN ({ph})
        AND d.close_date IS NOT NULL AND d.close_date != ''
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
        """,
        ICP_CHURN_STAGES,
    ).fetchall()
    active_deals = conn.execute(
        """SELECT COUNT(*) FROM deals d
        WHERE d.id_empresa IN (SELECT id_empresa FROM facturacion WHERE id_empresa != '')"""
    ).fetchone()[0]
    churn_rate = (churn_total / (active_deals + churn_total) * 100) if (active_deals + churn_total) else 0
    return {
        "paying_customers": paying_customers,
        "total_mrr": total_mrr_raw,
        "mrr_by_icp": mrr_by_icp,
        "churn_total": churn_total,
        "churn_by_icp": churn_by_icp,
        "churn_by_month": churn_by_month,
        "active_deals": active_deals,
        "churn_rate": churn_rate,
    }


def get_accountant_metrics(conn: sqlite3.Connection) -> list[dict]:
    """Compute per-accountant: total_portfolio (active+churned), active, churned, growth_pct, mrr."""
    churn_ph = ",".join("?" * len(CHURN_STAGES))
    rows = conn.execute(f"""
        WITH accountant_deals AS (
            SELECT da.company_hubspot_id AS accountant_id, da.deal_hubspot_id, d.id_empresa, d.close_date, d.deal_stage
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 8
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            UNION
            SELECT da.company_hubspot_id, da.deal_hubspot_id, d.id_empresa, d.close_date, d.deal_stage
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 5
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
        ),
        active_facturacion AS (
            SELECT DISTINCT id_empresa FROM facturacion WHERE id_empresa != ''
        ),
        accountant_first_close AS (
            SELECT accountant_id, MIN(date(close_date)) AS first_close
            FROM accountant_deals
            WHERE close_date IS NOT NULL AND close_date != ''
            GROUP BY accountant_id
        ),
        portfolio_beginning_cte AS (
            SELECT ad.accountant_id, COUNT(DISTINCT ad.id_empresa) AS portfolio_beginning
            FROM accountant_deals ad
            JOIN accountant_first_close afc ON ad.accountant_id = afc.accountant_id
            WHERE ad.close_date IS NOT NULL AND ad.close_date != ''
              AND date(ad.close_date) <= date(afc.first_close, '+90 days')
            GROUP BY ad.accountant_id
            HAVING portfolio_beginning > 0
        ),
        accountant_metrics AS (
            SELECT
                ad.accountant_id,
                COUNT(DISTINCT ad.id_empresa) AS total_portfolio,
                COUNT(DISTINCT CASE WHEN af.id_empresa IS NOT NULL THEN ad.id_empresa END) AS active_portfolio,
                COUNT(DISTINCT CASE WHEN ad.deal_stage IN ({churn_ph}) THEN ad.id_empresa END) AS churned_portfolio,
                pbc.portfolio_beginning
            FROM accountant_deals ad
            LEFT JOIN active_facturacion af ON ad.id_empresa = af.id_empresa
            JOIN portfolio_beginning_cte pbc ON ad.accountant_id = pbc.accountant_id
            WHERE ad.close_date IS NOT NULL AND ad.close_date != ''
            GROUP BY ad.accountant_id, pbc.portfolio_beginning
        ),
        accountant_with_growth AS (
            SELECT accountant_id, total_portfolio, active_portfolio, churned_portfolio,
                ROUND((active_portfolio - portfolio_beginning) * 100.0 / portfolio_beginning, 1) AS growth_pct
            FROM accountant_metrics
        ),
        accountant_mrr AS (
            SELECT ad.accountant_id, SUM(CAST(f.amount AS REAL)) AS mrr
            FROM (
                SELECT DISTINCT da.company_hubspot_id AS accountant_id, d.id_empresa
                FROM deal_associations da
                JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
                JOIN companies c ON da.company_hubspot_id = c.hubspot_id
                WHERE da.association_type_id = 8
                  AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
                UNION
                SELECT da.company_hubspot_id, d.id_empresa
                FROM deal_associations da
                JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
                JOIN companies c ON da.company_hubspot_id = c.hubspot_id
                WHERE da.association_type_id = 5
                  AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            ) ad
            JOIN facturacion f ON ad.id_empresa = f.id_empresa
            GROUP BY ad.accountant_id
        )
        SELECT a.accountant_id, c.name, a.total_portfolio, a.active_portfolio, a.churned_portfolio, a.growth_pct, COALESCE(m.mrr, 0) AS mrr
        FROM accountant_with_growth a
        JOIN companies c ON a.accountant_id = c.hubspot_id
        LEFT JOIN accountant_mrr m ON a.accountant_id = m.accountant_id
    """, CHURN_STAGES).fetchall()
    return [
        {"id": r[0], "name": r[1], "portfolio": r[2], "active": r[3], "churned": r[4], "growth": r[5], "mrr": r[6]}
        for r in rows
    ]


def get_accountant_mrr_timeline(conn: sqlite3.Connection, months: int = CAGR_LOOKBACK_DEFAULT_MONTHS) -> tuple[dict[str, float], dict[str, float], float]:
    """
    Returns (mrr_now_by_id, mrr_start_by_id, years) for matrix CAGR.
    Same logic as get_growth_by_tier but per accountant.
    Uses rolling window: last `months` months.
    """
    cutoff, years = _get_cagr_cutoff(months)
    rows = conn.execute("""
        WITH cutoff AS (SELECT ? AS d),
        accountant_deals AS (
            SELECT da.company_hubspot_id AS accountant_id, d.id_empresa, d.close_date, CAST(d.amount AS REAL) AS deal_amount
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 8
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            UNION
            SELECT da.company_hubspot_id, d.id_empresa, d.close_date, CAST(d.amount AS REAL)
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 5
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
        ),
        id_empresa_mrr AS (
            SELECT id_empresa, SUM(CAST(amount AS REAL)) AS mrr FROM facturacion WHERE id_empresa != '' GROUP BY id_empresa
        ),
        id_mrr_timeline AS (
            SELECT ad.accountant_id, ad.id_empresa,
                COALESCE(im.mrr, 0) AS mrr_now,
                CASE WHEN date(ad.close_date) <= (SELECT d FROM cutoff) THEN COALESCE(ad.deal_amount, 0) ELSE 0 END AS mrr_start
            FROM accountant_deals ad
            LEFT JOIN id_empresa_mrr im ON ad.id_empresa = im.id_empresa
            WHERE ad.close_date IS NOT NULL AND ad.close_date != ''
        )
        SELECT accountant_id, SUM(mrr_now) AS mrr_now, SUM(mrr_start) AS mrr_start
        FROM (SELECT accountant_id, id_empresa, MAX(mrr_now) AS mrr_now, MAX(mrr_start) AS mrr_start FROM id_mrr_timeline GROUP BY accountant_id, id_empresa) x
        GROUP BY accountant_id
    """, (cutoff,)).fetchall()
    mrr_now_by_id = {str(r[0]): r[1] or 0 for r in rows}
    mrr_start_by_id = {str(r[0]): r[2] or 0 for r in rows}
    return mrr_now_by_id, mrr_start_by_id, years


def _get_earliest_close_date(conn: sqlite3.Connection) -> str:
    """Earliest close_date in deals. Used as fallback."""
    row = conn.execute(
        "SELECT MIN(date(close_date)) FROM deals WHERE close_date IS NOT NULL AND close_date != ''"
    ).fetchone()
    if row and row[0]:
        return row[0]
    return (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")


def _get_cagr_cutoff(months: int) -> tuple[str, float]:
    """Cutoff date and years for CAGR. Rolling window: last N months. Returns (cutoff_date, years)."""
    cutoff = (datetime.now() - timedelta(days=365.25 * months / 12)).strftime("%Y-%m-%d")
    years = max(0.1, months / 12)
    return cutoff, years


def get_growth_by_tier(conn: sqlite3.Connection, months: int = CAGR_LOOKBACK_DEFAULT_MONTHS) -> list[dict]:
    """
    MRR growth by portfolio tier. Only ICP accountant companies.
    Reconstructs MRR at cutoff using close_date:
    - Active: in facturacion; if close_date <= cutoff they were paying at cutoff
    - Churned: not in facturacion; if close_date <= cutoff they were paying at cutoff (use deal.amount)
    CAGR = (MRR_now / MRR_start)^(1/years) - 1
    Uses rolling window: last `months` months.
    """
    cutoff, years = _get_cagr_cutoff(months)
    rows = conn.execute("""
        WITH cutoff AS (SELECT ? AS d),
        accountant_deals AS (
            SELECT da.company_hubspot_id AS accountant_id, d.id_empresa, d.close_date, d.deal_stage, CAST(d.amount AS REAL) AS deal_amount
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 8
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            UNION
            SELECT da.company_hubspot_id, d.id_empresa, d.close_date, d.deal_stage, CAST(d.amount AS REAL)
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 5
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
        ),
        id_empresa_mrr AS (
            SELECT id_empresa, SUM(CAST(amount AS REAL)) AS mrr FROM facturacion WHERE id_empresa != '' GROUP BY id_empresa
        ),
        id_mrr_timeline AS (
            SELECT ad.accountant_id, ad.id_empresa,
                COALESCE(im.mrr, 0) AS mrr_now,
                CASE WHEN date(ad.close_date) <= (SELECT d FROM cutoff) THEN COALESCE(ad.deal_amount, 0) ELSE 0 END AS mrr_12m_ago
            FROM accountant_deals ad
            LEFT JOIN id_empresa_mrr im ON ad.id_empresa = im.id_empresa
            WHERE ad.close_date IS NOT NULL AND ad.close_date != ''
        ),
        accountant_mrr AS (
            SELECT accountant_id, SUM(mrr_now) AS mrr_now, SUM(mrr_12m_ago) AS mrr_12m_ago
            FROM (
                SELECT accountant_id, id_empresa, MAX(mrr_now) AS mrr_now, MAX(mrr_12m_ago) AS mrr_12m_ago
                FROM id_mrr_timeline GROUP BY accountant_id, id_empresa
            ) x GROUP BY accountant_id
        ),
        accountant_portfolio AS (
            SELECT accountant_id, COUNT(DISTINCT id_empresa) AS portfolio_size
            FROM accountant_deals WHERE close_date IS NOT NULL AND close_date != ''
            GROUP BY accountant_id
        )
        SELECT
            CASE
                WHEN ap.portfolio_size = 1 THEN '1'
                WHEN ap.portfolio_size = 2 THEN '2'
                WHEN ap.portfolio_size BETWEEN 3 AND 5 THEN '3-5'
                WHEN ap.portfolio_size BETWEEN 6 AND 10 THEN '6-10'
                WHEN ap.portfolio_size BETWEEN 11 AND 20 THEN '11-20'
                WHEN ap.portfolio_size BETWEEN 21 AND 40 THEN '20-40'
                WHEN ap.portfolio_size BETWEEN 41 AND 100 THEN '40-100'
                WHEN ap.portfolio_size BETWEEN 101 AND 200 THEN '100-200'
                ELSE '200+'
            END AS tier,
            SUM(am.mrr_now) AS mrr_now,
            SUM(am.mrr_12m_ago) AS mrr_12m_ago
        FROM accountant_mrr am
        JOIN accountant_portfolio ap ON am.accountant_id = ap.accountant_id
        GROUP BY tier
    """, (cutoff,)).fetchall()
    tier_order = [pb for _, _, pb in PORTFOLIO_BUCKETS]
    result = []
    for r in rows:
        tier, mrr_now, mrr_start = r[0], r[1] or 0, r[2] or 0
        if mrr_start > 0:
            cagr = ((mrr_now / mrr_start) ** (1 / years) - 1) * 100
        else:
            cagr = None  # Cannot compute CAGR from zero; show "New" in UI
        result.append({"tier": tier, "mrr_now": mrr_now, "mrr_start": mrr_start, "cagr_pct": cagr})
    result.sort(key=lambda x: tier_order.index(x["tier"]) if x["tier"] in tier_order else 999)
    if result:
        result[0]["_cutoff_date"] = cutoff  # For dashboard display
    return result


def get_deals_growth_by_tier(conn: sqlite3.Connection, months: int = CAGR_LOOKBACK_DEFAULT_MONTHS) -> list[dict]:
    """
    Deals growth by portfolio tier. Same structure as get_growth_by_tier but counts deals.
    - deals_now: distinct deals associated with accountants in each tier (all association types)
    - deals_start: distinct deals with close_date <= cutoff
    CAGR = (deals_now / deals_start)^(1/years) - 1
    Uses rolling window: last `months` months.
    """
    cutoff, years = _get_cagr_cutoff(months)
    rows = conn.execute("""
        WITH cutoff AS (SELECT ? AS d),
        accountant_portfolio AS (
            SELECT accountant_id, COUNT(DISTINCT id_empresa) AS portfolio_size
            FROM (
                SELECT da.company_hubspot_id AS accountant_id, d.id_empresa
                FROM deal_associations da
                JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
                JOIN companies c ON da.company_hubspot_id = c.hubspot_id
                WHERE da.association_type_id = 8
                  AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
                UNION
                SELECT da.company_hubspot_id, d.id_empresa
                FROM deal_associations da
                JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
                JOIN companies c ON da.company_hubspot_id = c.hubspot_id
                WHERE da.association_type_id = 5
                  AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            ) x
            GROUP BY accountant_id
        ),
        accountant_tier AS (
            SELECT accountant_id,
                CASE
                    WHEN portfolio_size = 1 THEN '1'
                    WHEN portfolio_size = 2 THEN '2'
                    WHEN portfolio_size BETWEEN 3 AND 5 THEN '3-5'
                    WHEN portfolio_size BETWEEN 6 AND 10 THEN '6-10'
                    WHEN portfolio_size BETWEEN 11 AND 20 THEN '11-20'
                    WHEN portfolio_size BETWEEN 21 AND 40 THEN '20-40'
                    WHEN portfolio_size BETWEEN 41 AND 100 THEN '40-100'
                    WHEN portfolio_size BETWEEN 101 AND 200 THEN '100-200'
                    ELSE '200+'
                END AS tier
            FROM accountant_portfolio
        ),
        deal_accountant_tier AS (
            SELECT da.deal_hubspot_id, d.close_date, at.tier
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            JOIN accountant_tier at ON at.accountant_id = da.company_hubspot_id
            WHERE c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
              AND d.close_date IS NOT NULL AND d.close_date != ''
        ),
        tier_companies AS (
            SELECT tier, COUNT(DISTINCT accountant_id) AS companies
            FROM accountant_tier
            GROUP BY tier
        )
        SELECT dat.tier,
               COUNT(DISTINCT dat.deal_hubspot_id) AS deals_now,
               COUNT(DISTINCT CASE WHEN date(dat.close_date) <= (SELECT d FROM cutoff) THEN dat.deal_hubspot_id END) AS deals_start,
               MAX(tc.companies) AS companies
        FROM deal_accountant_tier dat
        LEFT JOIN tier_companies tc ON tc.tier = dat.tier
        GROUP BY dat.tier
    """, (cutoff,)).fetchall()
    tier_order = [pb for _, _, pb in PORTFOLIO_BUCKETS]
    result = []
    for r in rows:
        tier = r[0]
        deals_now = int(r[1] or 0)
        deals_start = int(r[2] or 0)
        companies = int(r[3] or 0)
        if deals_start > 0:
            cagr = ((deals_now / deals_start) ** (1 / years) - 1) * 100
        else:
            cagr = None  # Cannot compute CAGR from zero; show "New" in UI
        result.append({"tier": tier, "deals_now": deals_now, "deals_start": deals_start, "companies": companies, "cagr_pct": cagr})
    result.sort(key=lambda x: tier_order.index(x["tier"]) if x["tier"] in tier_order else 999)
    if result:
        result[0]["_cutoff_date"] = cutoff
    return result


def get_portfolio_churn_metrics(conn: sqlite3.Connection) -> dict:
    """Churn by MRR for accountant portfolio. Churn = deals with deal_stage in CHURN_STAGES (Cerrado Churn)."""
    placeholders = ",".join("?" * len(CHURN_STAGES))
    row = conn.execute(f"""
        WITH accountant_portfolio AS (
            SELECT DISTINCT d.id_empresa
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 8
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            UNION
            SELECT d.id_empresa
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 5
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
        )
        SELECT COALESCE(SUM(CAST(d.amount AS REAL)), 0)
        FROM deals d
        WHERE d.id_empresa IN (SELECT id_empresa FROM accountant_portfolio WHERE id_empresa != '')
          AND d.deal_stage IN ({placeholders})
    """, CHURN_STAGES).fetchone()
    return {"churned_mrr": row[0] or 0}


def get_top_accountants(conn: sqlite3.Connection, limit: int = 20, order_by: str = "mrr", months: int = CAGR_LOOKBACK_DEFAULT_MONTHS) -> list[dict]:
    """Top/worst accountants. order_by: 'mrr' (default) or 'churn_pct' for worst by churn %."""
    cutoff, years = _get_cagr_cutoff(months)
    churn_placeholders = ",".join("?" * len(CHURN_STAGES))
    lost_placeholders = ",".join("?" * len(LOST_STAGES))
    rows = conn.execute(f"""
        WITH cutoff AS (SELECT ? AS d),
        accountant_deals_billed AS (
            SELECT da.company_hubspot_id AS accountant_id, d.id_empresa, d.close_date, d.deal_stage, CAST(d.amount AS REAL) AS deal_amount
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 5
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
        ),
        accountant_deals_consultant AS (
            SELECT da.company_hubspot_id AS accountant_id, d.id_empresa, d.close_date, d.deal_stage, CAST(d.amount AS REAL) AS deal_amount
            FROM deal_associations da
            JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 8
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
        ),
        id_empresa_billed AS (
            SELECT DISTINCT accountant_id, id_empresa FROM accountant_deals_billed
        ),
        id_empresa_consultant_only AS (
            SELECT DISTINCT adc.accountant_id, adc.id_empresa
            FROM accountant_deals_consultant adc
            WHERE NOT EXISTS (SELECT 1 FROM id_empresa_billed b WHERE b.accountant_id = adc.accountant_id AND b.id_empresa = adc.id_empresa)
        ),
        id_empresa_mrr AS (
            SELECT id_empresa, SUM(CAST(amount AS REAL)) AS mrr FROM facturacion WHERE id_empresa != '' GROUP BY id_empresa
        ),
        timeline_billed AS (
            SELECT adb.accountant_id, adb.id_empresa,
                COALESCE(im.mrr, 0) AS mrr_now,
                CASE
                    WHEN im.id_empresa IS NOT NULL THEN
                        CASE WHEN date(adb.close_date) <= (SELECT d FROM cutoff) THEN COALESCE(adb.deal_amount, 0) ELSE 0 END
                    ELSE
                        CASE WHEN date(adb.close_date) <= (SELECT d FROM cutoff) THEN adb.deal_amount ELSE 0 END
                END AS mrr_start
            FROM accountant_deals_billed adb
            LEFT JOIN id_empresa_mrr im ON adb.id_empresa = im.id_empresa
            WHERE adb.close_date IS NOT NULL AND adb.close_date != ''
        ),
        timeline_consultant AS (
            SELECT adc.accountant_id, adc.id_empresa,
                COALESCE(im.mrr, 0) AS mrr_now,
                CASE
                    WHEN im.id_empresa IS NOT NULL THEN
                        CASE WHEN date(adc.close_date) <= (SELECT d FROM cutoff) THEN COALESCE(adc.deal_amount, 0) ELSE 0 END
                    ELSE
                        CASE WHEN date(adc.close_date) <= (SELECT d FROM cutoff) THEN adc.deal_amount ELSE 0 END
                END AS mrr_start
            FROM accountant_deals_consultant adc
            JOIN id_empresa_consultant_only ico ON adc.accountant_id = ico.accountant_id AND adc.id_empresa = ico.id_empresa
            LEFT JOIN id_empresa_mrr im ON adc.id_empresa = im.id_empresa
            WHERE adc.close_date IS NOT NULL AND adc.close_date != ''
        ),
        amt_billed AS (
            SELECT accountant_id, SUM(mrr_now) AS mrr_now, SUM(mrr_start) AS mrr_start
            FROM (SELECT accountant_id, id_empresa, MAX(mrr_now) AS mrr_now, MAX(mrr_start) AS mrr_start FROM timeline_billed GROUP BY accountant_id, id_empresa) x
            GROUP BY accountant_id
        ),
        amt_consultant AS (
            SELECT accountant_id, SUM(mrr_now) AS mrr_now, SUM(mrr_start) AS mrr_start
            FROM (SELECT accountant_id, id_empresa, MAX(mrr_now) AS mrr_now, MAX(mrr_start) AS mrr_start FROM timeline_consultant GROUP BY accountant_id, id_empresa) x
            GROUP BY accountant_id
        ),
        accountant_deals AS (
            SELECT accountant_id, id_empresa, close_date, deal_amount FROM accountant_deals_billed
            UNION
            SELECT accountant_id, id_empresa, close_date, deal_amount FROM accountant_deals_consultant
        ),
        id_mrr_timeline AS (
            SELECT ad.accountant_id, ad.id_empresa,
                COALESCE(im.mrr, 0) AS mrr_now,
                CASE WHEN date(ad.close_date) <= (SELECT d FROM cutoff) THEN COALESCE(ad.deal_amount, 0) ELSE 0 END AS mrr_12m_ago
            FROM accountant_deals ad
            LEFT JOIN id_empresa_mrr im ON ad.id_empresa = im.id_empresa
            WHERE ad.close_date IS NOT NULL AND ad.close_date != ''
        ),
        accountant_mrr_timeline AS (
            SELECT accountant_id, SUM(mrr_now) AS mrr_now, SUM(mrr_12m_ago) AS mrr_12m_ago
            FROM (SELECT accountant_id, id_empresa, MAX(mrr_now) AS mrr_now, MAX(mrr_12m_ago) AS mrr_12m_ago FROM id_mrr_timeline GROUP BY accountant_id, id_empresa) x
            GROUP BY accountant_id
        ),
        accountant_portfolio AS (
            SELECT DISTINCT accountant_id, id_empresa FROM accountant_deals_billed
            UNION
            SELECT DISTINCT accountant_id, id_empresa FROM accountant_deals_consultant
        ),
        accountant_mrr AS (
            SELECT ap.accountant_id, SUM(CAST(f.amount AS REAL)) AS mrr
            FROM accountant_portfolio ap
            JOIN facturacion f ON ap.id_empresa = f.id_empresa
            GROUP BY ap.accountant_id
        ),
        deals_with_type8 AS (
            SELECT company_hubspot_id AS accountant_id, deal_hubspot_id
            FROM deal_associations
            WHERE association_type_id = 8
        ),
        operator_deals AS (
            SELECT da.company_hubspot_id AS accountant_id, COUNT(DISTINCT da.deal_hubspot_id) AS operator_count
            FROM deal_associations da
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 5
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
              AND NOT EXISTS (
                  SELECT 1 FROM deals_with_type8 t8
                  WHERE t8.accountant_id = da.company_hubspot_id AND t8.deal_hubspot_id = da.deal_hubspot_id
              )
            GROUP BY da.company_hubspot_id
        ),
        consultant_deals AS (
            SELECT da.company_hubspot_id AS accountant_id, COUNT(DISTINCT da.deal_hubspot_id) AS consultant_count
            FROM deal_associations da
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.association_type_id = 8
              AND c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            GROUP BY da.company_hubspot_id
        ),
        total_deals AS (
            SELECT da.company_hubspot_id AS accountant_id, COUNT(DISTINCT da.deal_hubspot_id) AS total_deals
            FROM deal_associations da
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
            GROUP BY da.company_hubspot_id
        ),
        churned_mrr_billed AS (
            SELECT adb.accountant_id, SUM(adb.deal_amount) AS churned_mrr
            FROM accountant_deals_billed adb
            WHERE adb.deal_stage IN ({churn_placeholders})
            GROUP BY adb.accountant_id
        ),
        churned_mrr_consultant AS (
            SELECT adc.accountant_id, SUM(adc.deal_amount) AS churned_mrr
            FROM accountant_deals_consultant adc
            JOIN id_empresa_consultant_only ico ON adc.accountant_id = ico.accountant_id AND adc.id_empresa = ico.id_empresa
            WHERE adc.deal_stage IN ({churn_placeholders})
            GROUP BY adc.accountant_id
        ),
        lost_mrr_billed AS (
            SELECT adb.accountant_id, SUM(adb.deal_amount) AS lost_mrr, COUNT(*) AS lost_count
            FROM accountant_deals_billed adb
            WHERE adb.deal_stage IN ({lost_placeholders})
            GROUP BY adb.accountant_id
        ),
        lost_mrr_consultant AS (
            SELECT adc.accountant_id, SUM(adc.deal_amount) AS lost_mrr, COUNT(*) AS lost_count
            FROM accountant_deals_consultant adc
            JOIN id_empresa_consultant_only ico ON adc.accountant_id = ico.accountant_id AND adc.id_empresa = ico.id_empresa
            WHERE adc.deal_stage IN ({lost_placeholders})
            GROUP BY adc.accountant_id
        ),
        ranked AS (
            SELECT m.accountant_id, c.name, m.mrr,
                   COALESCE(od.operator_count, 0) AS operator_deals,
                   COALESCE(cd.consultant_count, 0) AS consultant_deals,
                   COALESCE(td.total_deals, 0) AS total_deals,
                   amt.mrr_12m_ago,
                   ab.mrr_now AS mrr_billed_now, ab.mrr_start AS mrr_billed_start,
                   ac.mrr_now AS mrr_consultant_now, ac.mrr_start AS mrr_consultant_start,
                   COALESCE(cmb.churned_mrr, 0) AS churned_mrr_operador,
                   COALESCE(cmc.churned_mrr, 0) AS churned_mrr_asesor,
                   (COALESCE(cmb.churned_mrr, 0) + COALESCE(cmc.churned_mrr, 0)) AS churned_total,
                   COALESCE(lmb.lost_mrr, 0) AS lost_mrr_operador,
                   COALESCE(lmc.lost_mrr, 0) AS lost_mrr_asesor,
                   COALESCE(lmb.lost_count, 0) AS lost_count_operador,
                   COALESCE(lmc.lost_count, 0) AS lost_count_asesor
            FROM accountant_mrr m
            JOIN companies c ON c.hubspot_id = m.accountant_id
            LEFT JOIN operator_deals od ON od.accountant_id = m.accountant_id
            LEFT JOIN consultant_deals cd ON cd.accountant_id = m.accountant_id
            LEFT JOIN total_deals td ON td.accountant_id = m.accountant_id
            LEFT JOIN accountant_mrr_timeline amt ON amt.accountant_id = m.accountant_id
            LEFT JOIN amt_billed ab ON ab.accountant_id = m.accountant_id
            LEFT JOIN amt_consultant ac ON ac.accountant_id = m.accountant_id
            LEFT JOIN churned_mrr_billed cmb ON cmb.accountant_id = m.accountant_id
            LEFT JOIN churned_mrr_consultant cmc ON cmc.accountant_id = m.accountant_id
            LEFT JOIN lost_mrr_billed lmb ON lmb.accountant_id = m.accountant_id
            LEFT JOIN lost_mrr_consultant lmc ON lmc.accountant_id = m.accountant_id
        )
        SELECT accountant_id, name, mrr, operator_deals, consultant_deals, total_deals, mrr_12m_ago,
               mrr_billed_now, mrr_billed_start, mrr_consultant_now, mrr_consultant_start,
               churned_mrr_operador, churned_mrr_asesor,
               lost_mrr_operador, lost_mrr_asesor, lost_count_operador, lost_count_asesor
        FROM ranked
        WHERE (? = 'mrr') OR (churned_total > 0)
        ORDER BY CASE WHEN ? = 'churn_pct' THEN churned_total * 1.0 / NULLIF(mrr + churned_total, 0) ELSE 0 END DESC,
                 CASE WHEN ? = 'mrr' THEN mrr ELSE 0 END DESC
        LIMIT ?
    """, (cutoff,) + CHURN_STAGES + CHURN_STAGES + LOST_STAGES + LOST_STAGES + (order_by, order_by, order_by, limit)).fetchall()

    def _cagr(mrr_now: float, mrr_start: float) -> Optional[float]:
        if mrr_start > 0:
            return ((mrr_now / mrr_start) ** (1 / years) - 1) * 100
        if mrr_now > 0:
            return None  # "New" - had no MRR at start
        return 0.0

    result = []
    for r in rows:
        hubspot_id = str(r[0])
        mrr_now = r[2]
        mrr_start = r[6] or 0
        mrr_billed_now = r[7] or 0
        mrr_billed_start = r[8] or 0
        mrr_consultant_now = r[9] or 0
        mrr_consultant_start = r[10] or 0
        churned_operador = r[11] or 0
        churned_asesor = r[12] or 0
        lost_mrr_operador = r[13] or 0
        lost_mrr_asesor = r[14] or 0
        lost_count_operador = r[15] or 0
        lost_count_asesor = r[16] or 0
        cagr_total = _cagr(mrr_now, mrr_start)
        cagr_billed = _cagr(mrr_billed_now, mrr_billed_start) if (mrr_billed_now or mrr_billed_start) else None
        cagr_consultant = _cagr(mrr_consultant_now, mrr_consultant_start) if (mrr_consultant_now or mrr_consultant_start) else None
        result.append({
            "hubspot_id": hubspot_id,
            "name": r[1],
            "mrr": mrr_now,
            "mrr_operador": mrr_billed_now or 0,
            "mrr_asesor": mrr_consultant_now or 0,
            "churned_operador": churned_operador,
            "churned_asesor": churned_asesor,
            "lost_mrr_operador": lost_mrr_operador,
            "lost_mrr_asesor": lost_mrr_asesor,
            "lost_count_operador": lost_count_operador,
            "lost_count_asesor": lost_count_asesor,
            "operator_deals": r[3],
            "consultant_deals": r[4],
            "total_deals": r[5],
            "cagr_pct": cagr_total if cagr_total is not None else 0.0,
            "cagr_billed_pct": cagr_billed,
            "cagr_consultant_pct": cagr_consultant,
            "_mrr_billed_now": mrr_billed_now,
            "_mrr_consultant_now": mrr_consultant_now,
        })
    return result


def bucket_growth(growth: float) -> str:
    """Return growth bucket label."""
    for label, pred in GROWTH_BUCKETS:
        if pred(growth):
            return label
    return "N/A"


def bucket_portfolio(n: int) -> str:
    """Return portfolio bucket label."""
    for lo, hi, label in PORTFOLIO_BUCKETS:
        if lo <= n <= hi:
            return label
    return "1" if n <= 5 else "200+"


def build_matrix(metrics: list[dict]) -> dict[tuple[str, str], float]:
    """Aggregate MRR per (growth_bucket, portfolio_bucket)."""
    matrix = {}
    for m in metrics:
        gb = bucket_growth(m["growth"])
        pb = bucket_portfolio(m["portfolio"])
        key = (gb, pb)
        matrix[key] = matrix.get(key, 0) + m["mrr"]
    return matrix


def build_matrix_cagr(
    metrics: list[dict],
    mrr_start_by_id: dict[str, float],
    years: float,
) -> dict[tuple[str, str], Optional[float]]:
    """
    Aggregate CAGR per (growth_bucket, portfolio_bucket).
    CAGR = (sum_mrr_now / sum_mrr_start)^(1/years) - 1 per cell.
    Returns None for cells with mrr_start=0.
    """
    mrr_now_sum: dict[tuple[str, str], float] = {}
    mrr_start_sum: dict[tuple[str, str], float] = {}
    for m in metrics:
        gb = bucket_growth(m["growth"])
        pb = bucket_portfolio(m["portfolio"])
        key = (gb, pb)
        mrr_now = m["mrr"]
        mrr_start = mrr_start_by_id.get(str(m["id"]), 0)
        mrr_now_sum[key] = mrr_now_sum.get(key, 0) + mrr_now
        mrr_start_sum[key] = mrr_start_sum.get(key, 0) + mrr_start
    result: dict[tuple[str, str], Optional[float]] = {}
    for key in mrr_now_sum:
        ms = mrr_start_sum.get(key, 0)
        mn = mrr_now_sum.get(key, 0)
        if ms > 0:
            result[key] = ((mn / ms) ** (1 / years) - 1) * 100
        else:
            result[key] = None
    return result


def format_ars(val: float) -> str:
    """Format as ARS with Argentina conventions (comma decimal, dot thousands)."""
    s = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${s}"


def print_verification_examples(
    db_path: Path,
    metrics: list[dict],
    matrix: dict[tuple[str, str], float],
    growth_by_tier: list[dict],
    deals_growth_by_tier: list[dict],
    matrix_cagr: dict[tuple[str, str], Optional[float]],
    cols: list[str],
    rows_order: list[str],
) -> None:
    """
    Print real examples and formulas so you can validate the dashboard calculations.
    Uses default CAGR period (24 months).
    """
    months = CAGR_LOOKBACK_DEFAULT_MONTHS
    cutoff, years = _get_cagr_cutoff(months)
    conn = sqlite3.connect(str(db_path))
    mrr_start_by_id, _, _ = get_accountant_mrr_timeline(conn, months=months)
    conn.close()

    print("\n" + "=" * 80)
    print("VERIFICATION EXAMPLES (default CAGR period = 24 months)")
    print("=" * 80)

    # --- 1. MRR matrix: one cell = sum of MRR of accountants in (growth_bucket, portfolio_bucket) ---
    print("\n--- 1. MRR MATRIX (Growth x Portfolio) ---")
    print("Each cell = sum of MRR of all ICP accountants whose:")
    print("  - growth_pct falls in the row bucket (e.g. '>+14%' means growth >= 14%)")
    print("  - portfolio (total managed tax IDs) falls in the column bucket (e.g. '3-5')")
    for gb in rows_order:
        for pb in cols:
            cell_mrr = matrix.get((gb, pb), 0)
            if cell_mrr <= 0:
                continue
            in_cell = [
                m for m in metrics
                if bucket_growth(m["growth"]) == gb and bucket_portfolio(m["portfolio"]) == pb
            ]
            manual_sum = sum(m["mrr"] for m in in_cell)
            print(f"\n  Cell ({gb!r}, {pb!r}): dashboard value = {format_ars(cell_mrr)}")
            print(f"  Accountants in this cell: {len(in_cell)}")
            if len(in_cell) <= 5:
                for m in in_cell:
                    print(f"    - {m['name'][:40]}... growth={m['growth']}% portfolio={m['portfolio']} mrr={format_ars(m['mrr'])}")
            else:
                for m in in_cell[:3]:
                    print(f"    - {m['name'][:40]}... growth={m['growth']}% portfolio={m['portfolio']} mrr={format_ars(m['mrr'])}")
                print(f"    ... and {len(in_cell) - 3} more")
            print(f"  Sum of their MRR: {format_ars(manual_sum)}  (match: {abs(manual_sum - cell_mrr) < 0.01})")
            break
        else:
            continue
        break

    # --- 2. MRR Growth by Tier ---
    print("\n--- 2. MRR GROWTH BY PORTFOLIO TIER (CAGR from MRR) ---")
    print("Formula: CAGR = (MRR_now / MRR_start)^(1/years) - 1  (then * 100 for %)")
    print(f"  Cutoff date (start of period): {cutoff}  |  years = {years}")
    if growth_by_tier:
        g = growth_by_tier[0]
        tier = g["tier"]
        mrr_now = g["mrr_now"]
        mrr_start = g["mrr_start"]
        cagr_pct = g.get("cagr_pct")
        print(f"\n  Example tier: {tier!r}")
        print(f"    MRR now (sum):     {format_ars(mrr_now)}")
        print(f"    MRR at start:      {format_ars(mrr_start)}")
        if mrr_start > 0:
            computed = ((mrr_now / mrr_start) ** (1 / years) - 1) * 100
            print(f"    CAGR % (computed): {computed:+.1f}%")
            print(f"    CAGR % (dashboard): {cagr_pct:+.1f}%" if cagr_pct is not None else "    CAGR % (dashboard): N/A")
            print(f"    Match: {abs(computed - (cagr_pct or 0)) < 0.01}")

    # --- 3. Deals Growth by Tier ---
    print("\n--- 3. DEALS GROWTH BY PORTFOLIO TIER (CAGR from deal counts) ---")
    print("Formula: CAGR = (deals_now / deals_start)^(1/years) - 1  (then * 100 for %)")
    print("  Companies = number of ICP accountant companies in that portfolio-size tier.")
    if deals_growth_by_tier:
        d = deals_growth_by_tier[0]
        tier = d["tier"]
        companies = d.get("companies", 0)
        deals_now = d["deals_now"]
        deals_start = d["deals_start"]
        cagr_pct = d.get("cagr_pct")
        print(f"\n  Example tier: {tier!r}")
        print(f"    Companies (in cohort): {companies}")
        print(f"    Deals now:   {deals_now:,}")
        print(f"    Deals at start: {deals_start:,}")
        if deals_start > 0:
            computed = ((deals_now / deals_start) ** (1 / years) - 1) * 100
            print(f"    CAGR % (computed):   {computed:+.1f}%")
            print(f"    CAGR % (dashboard):  {cagr_pct:+.1f}%" if cagr_pct is not None else "    CAGR % (dashboard): N/A")
            print(f"    Match: {abs(computed - (cagr_pct or 0)) < 0.01}")

    # --- 4. CAGR (MRR) matrix cell ---
    print("\n--- 4. CAGR (MRR) BY SEGMENT MATRIX ---")
    print("Each cell = (sum MRR_now / sum MRR_start)^(1/years) - 1 for that (growth, portfolio) bucket.")
    for gb in rows_order:
        for pb in cols:
            cagr_val = matrix_cagr.get((gb, pb))
            if cagr_val is None:
                continue
            in_cell = [
                m for m in metrics
                if bucket_growth(m["growth"]) == gb and bucket_portfolio(m["portfolio"]) == pb
            ]
            sum_now = sum(m["mrr"] for m in in_cell)
            sum_start = sum(mrr_start_by_id.get(str(m["id"]), 0) for m in in_cell)
            if sum_start <= 0:
                continue
            computed = ((sum_now / sum_start) ** (1 / years) - 1) * 100
            print(f"\n  Cell ({gb!r}, {pb!r}):")
            print(f"    Sum MRR now:   {format_ars(sum_now)}")
            print(f"    Sum MRR start: {format_ars(sum_start)}")
            print(f"    CAGR % (computed):   {computed:+.1f}%")
            print(f"    CAGR % (dashboard): {cagr_val:+.1f}%")
            print(f"    Match: {abs(computed - cagr_val) < 0.01}")
            break
        else:
            continue
        break

    print("\n" + "=" * 80 + "\n")


def _serialize_cagr_data_for_js(cagr_data_by_months: dict[int, dict], cols: list[str], rows_order: list[str]) -> str:
    """Serialize CAGR data for client-side period switching. Returns JSON string."""
    import json

    out = {}
    for months, data in cagr_data_by_months.items():
        key = str(months)
        gbt = data.get("growth_by_tier") or []
        dgt = data.get("deals_growth_by_tier") or []
        top = data.get("top_accountants") or []
        worst = data.get("worst_accountants") or []
        mc = data.get("matrix_cagr") or {}
        out[key] = {
            "growth_by_tier": [
                {"tier": g["tier"], "mrr_now": g["mrr_now"], "mrr_start": g["mrr_start"], "cagr_pct": g.get("cagr_pct"), "cutoff": g.get("_cutoff_date")}
                for g in gbt
            ],
            "deals_growth_by_tier": [
                {"tier": g["tier"], "companies": g.get("companies", 0), "deals_now": g["deals_now"], "deals_start": g["deals_start"], "cagr_pct": g.get("cagr_pct"), "cutoff": g.get("_cutoff_date")}
                for g in dgt
            ],
            "top_cagr": [{"cagr_pct": a.get("cagr_pct"), "cagr_billed_pct": a.get("cagr_billed_pct"), "cagr_consultant_pct": a.get("cagr_consultant_pct"), "_mrr_billed_now": a.get("_mrr_billed_now", 0), "_mrr_consultant_now": a.get("_mrr_consultant_now", 0)} for a in top],
            "worst_cagr": [{"cagr_pct": a.get("cagr_pct"), "cagr_billed_pct": a.get("cagr_billed_pct"), "cagr_consultant_pct": a.get("cagr_consultant_pct"), "_mrr_billed_now": a.get("_mrr_billed_now", 0), "_mrr_consultant_now": a.get("_mrr_consultant_now", 0)} for a in worst],
            "matrix_cagr": {f"{gb}|{pb}": mc.get((gb, pb)) for gb in rows_order for pb in cols},
        }
    return json.dumps(out)


def build_dashboard_from_db(db_path: Path) -> str:
    """
    Build dashboard HTML from DB. Returns HTML string. Used for live serving so each page load
    shows fresh data from the DB (no pre-refresh needed).
    """
    conn = sqlite3.connect(str(db_path))
    metrics = get_accountant_metrics(conn)
    churn_metrics = get_portfolio_churn_metrics(conn)
    icp_metrics = get_company_icp_metrics(conn)
    conn.close()

    if not metrics:
        return "<!DOCTYPE html><html><body><h1>No accountant data</h1><p>Need portfolio_12m_ago > 0.</p></body></html>"

    matrix = build_matrix(metrics)
    cagr_data_by_months: dict[int, dict] = {}
    for months in CAGR_LOOKBACK_MONTHS_OPTIONS:
        conn = sqlite3.connect(str(db_path))
        growth_by_tier = get_growth_by_tier(conn, months=months)
        deals_growth_by_tier = get_deals_growth_by_tier(conn, months=months)
        top_accountants = get_top_accountants(conn, limit=20, order_by="mrr", months=months)
        worst_accountants = get_top_accountants(conn, limit=20, order_by="churn_pct", months=months)
        mrr_now_by_id, mrr_start_by_id, years = get_accountant_mrr_timeline(conn, months=months)
        conn.close()
        matrix_cagr = build_matrix_cagr(metrics, mrr_start_by_id, years)
        cagr_data_by_months[months] = {
            "growth_by_tier": growth_by_tier,
            "deals_growth_by_tier": deals_growth_by_tier,
            "top_accountants": top_accountants,
            "worst_accountants": worst_accountants,
            "matrix_cagr": matrix_cagr,
        }

    default_data = cagr_data_by_months[CAGR_LOOKBACK_DEFAULT_MONTHS]
    top_accountants = default_data["top_accountants"]
    worst_accountants = default_data["worst_accountants"]
    growth_by_tier = default_data["growth_by_tier"]
    deals_growth_by_tier = default_data["deals_growth_by_tier"]
    matrix_cagr = default_data["matrix_cagr"]
    cols = [pb for _, _, pb in PORTFOLIO_BUCKETS]
    rows_order = [gb for gb, _ in GROWTH_BUCKETS]

    return generate_dashboard_html(
        matrix, matrix_cagr, metrics, cols, rows_order,
        top_accountants, worst_accountants, churn_metrics,
        growth_by_tier, deals_growth_by_tier, cagr_data_by_months, icp_metrics,
    )


def generate_dashboard_html(
    matrix: dict[tuple[str, str], float],
    matrix_cagr: Optional[dict[tuple[str, str], Optional[float]]],
    metrics: list[dict],
    cols: list[str],
    rows_order: list[str],
    top_accountants: list[dict],
    worst_accountants: list[dict],
    churn_metrics: dict,
    growth_by_tier: Optional[list[dict]] = None,
    deals_growth_by_tier: Optional[list[dict]] = None,
    cagr_data_by_months: Optional[dict[int, dict]] = None,
    icp_metrics: Optional[dict] = None,
) -> str:
    """Generate HTML dashboard (Nubox-style layout). Includes company-wide ICP section when icp_metrics provided."""
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_mrr = sum(m["mrr"] for m in metrics)
    total_accountants = len(metrics)
    avg_ticket = total_mrr / total_accountants if total_accountants else 0
    total_portfolio = sum(m["portfolio"] for m in metrics)
    total_active = sum(m.get("active", m["portfolio"]) for m in metrics)
    total_churned = sum(m.get("churned", 0) for m in metrics)
    churned_mrr = churn_metrics.get("churned_mrr", 0)
    churn_rate_smbs = (total_churned / total_portfolio * 100) if total_portfolio else 0
    churn_rate_mrr = (churned_mrr / (total_mrr + churned_mrr) * 100) if (total_mrr + churned_mrr) else 0
    # Company-wide ICP section (consolidated from ICP dashboard)
    icp_section_html = ""
    if icp_metrics:
        im = icp_metrics
        icp_cards = ""
        for icp in ICP_ORDER:
            data = im.get("mrr_by_icp", {}).get(icp, {})
            churn = im.get("churn_by_icp", {}).get(icp, 0)
            mrr = data.get("mrr", 0)
            cuits = data.get("unique_cuits", 0)
            if mrr > 0 or cuits > 0 or churn > 0:
                icp_cards += f'<div class="card" style="min-width:160px"><h2 style="font-size:0.9rem;margin:0 0 8px 0;color:var(--text-muted)">{icp}</h2><div class="value" style="font-size:1.2rem">{format_ars(mrr)}</div><div class="detail" style="font-size:0.8rem;margin-top:6px">{cuits:,} CUITs · {churn} churn</div></div>'
        churn_rows = "".join(
            f'<tr><td>{icp}</td><td class="num">{im.get("churn_by_icp", {}).get(icp, 0)}</td></tr>'
            for icp in ICP_ORDER if im.get("churn_by_icp", {}).get(icp, 0) > 0
        )
        churn_rows += f'<tr><td><strong>Total</strong></td><td class="num"><strong>{im["churn_total"]}</strong></td></tr>'
        churn_month_rows = "".join(
            f'<tr><td>{r[0]}</td><td class="num">{r[1]}</td></tr>' for r in im.get("churn_by_month", [])
        )
        if not churn_month_rows:
            churn_month_rows = '<tr><td colspan="2">No churn with close_date in last 12 months</td></tr>'
        icp_section_html = f'''
        <div class="matrix-card" id="company-icp" style="margin-top: 24px;">
            <h2 style="margin:0 0 16px 0;font-size:1.1rem">Company-wide: revenue by ICP</h2>
            <p class="detail" style="margin-bottom:16px;font-size:0.85rem;color:var(--text-muted)">All paying customers (facturacion). ICP = tipo_icp_contador (Operador/Asesor/Híbrido) or type (Contador/PYME). Churn = deal_stage closedlost or 31849274.</p>
            <div class="grid" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));gap:12px;margin-bottom:20px">
                <div class="card" style="min-width:140px"><h2 style="font-size:0.9rem;margin:0 0 8px 0;color:var(--text-muted)">Paying Customers</h2><div class="value" style="font-size:1.2rem">{im["paying_customers"]:,}</div><div class="detail" style="font-size:0.8rem">Unique CUITs billed</div></div>
                <div class="card" style="min-width:140px"><h2 style="font-size:0.9rem;margin:0 0 8px 0;color:var(--text-muted)">Total MRR</h2><div class="value" style="font-size:1.2rem">{format_ars(im["total_mrr"])}</div><div class="detail" style="font-size:0.8rem">From facturacion</div></div>
                <div class="card churn-card" style="min-width:140px;border-left:4px solid var(--warning)"><h2 style="font-size:0.9rem;margin:0 0 8px 0;color:var(--text-muted)">Churn Deals</h2><div class="value" style="font-size:1.2rem">{im["churn_total"]}</div><div class="detail" style="font-size:0.8rem">{im["churn_rate"]:.1f}% churn rate</div></div>
            </div>
            <div class="grid" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));gap:12px;margin-bottom:20px">{icp_cards}</div>
            <table class="sortable" style="width:100%;border-collapse:collapse;font-size:0.9rem;margin-bottom:16px">
                <thead><tr><th>ICP</th><th class="num">Churn Deals</th></tr></thead>
                <tbody>{churn_rows}</tbody>
            </table>
            <p class="detail" style="font-size:0.8rem;margin-bottom:8px">Churn by month (close_date). Last 12 months.</p>
            <table class="sortable" style="width:100%;border-collapse:collapse;font-size:0.9rem">
                <thead><tr><th>Month</th><th class="num">Churn Deals</th></tr></thead>
                <tbody>{churn_month_rows}</tbody>
            </table>
        </div>'''
    max_related_deals = max(
        (a.get("operator_deals", 0) + a.get("consultant_deals", 0)) for a in top_accountants
    ) if top_accountants else 0
    # Sidebar "Grow their Client Portfolio": median CAGR (annualized) of top 20 by MRR
    cagr_values = [a.get("cagr_pct") for a in top_accountants if a.get("cagr_pct") is not None]
    if cagr_values:
        s = sorted(cagr_values)
        n = len(s)
        median_cagr_top = (s[(n - 1) // 2] + s[n // 2]) / 2
        sidebar_goal_growth = f"{median_cagr_top:+.0f}% YoY"
    else:
        sidebar_goal_growth = "—"
    # Sidebar "Manage": minimum portfolio (total_deals) among top 20
    min_portfolio_top = min((a.get("total_deals", 0) for a in top_accountants), default=0)
    sidebar_goal_smbs = f"{min_portfolio_top}+ SMBs" if top_accountants else "—"

    def cell_val(gb: str, pb: str) -> str:
        v = matrix.get((gb, pb), 0)
        return format_ars(v) if v else "N/A"

    def _cagr_section(cols: list[str], cagr_rows: str) -> str:
        if not cagr_rows:
            return ""
        th_cols = "".join(f'<th data-col-id="pb-{pb}">Managed Tax IDs: {pb}</th>' for pb in cols)
        return f'<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin:20px 0 8px 0"><h3 style="font-size:0.95rem;margin:0;color:var(--text)">CAGR (MRR) by Segment (rolling)</h3><div class="col-toggle" data-table-id="cagr-matrix"><button type="button" class="col-toggle-btn">Columns</button><div class="col-toggle-dropdown"></div></div></div><table class="sortable" data-table-id="cagr-matrix"><thead><tr><th data-col-id="growth">Accountant\'s Client Portfolio Growth</th>{th_cols}</tr></thead><tbody id="cagr-matrix-tbody">{cagr_rows}</tbody></table><p class="detail" style="margin:12px 0 0 0;font-size:0.8rem;color:var(--text-muted)">CAGR = (MRR_now / MRR_at_start)^(1/years) - 1. Same dimensions as MRR matrix.</p>'

    def cell_cagr_val(gb: str, pb: str) -> str:
        c = matrix_cagr.get((gb, pb)) if matrix_cagr else None
        if c is not None:
            return f"{c:+.1f}%"
        return "N/A"

    matrix_rows = "".join(
        f"""
        <tr>
            <td class="growth-label" data-col-id="growth">{gb}</td>
            {"".join(f'<td class="cell" data-col-id="pb-{pb}">{cell_val(gb, pb)}</td>' for pb in cols)}
        </tr>"""
        for gb in rows_order
    )

    cagr_matrix_rows = ""
    if matrix_cagr:
        for gb in rows_order:
            cells = "".join(
                f'<td class="cell {("positive" if matrix_cagr.get((gb, pb)) >= 0 else "negative") if matrix_cagr.get((gb, pb)) is not None else ""}" data-gb="{gb}" data-pb="{pb}" data-col-id="pb-{pb}">{cell_cagr_val(gb, pb)}</td>'
                for pb in cols
            )
            cagr_matrix_rows += f'<tr data-gb="{gb}"><td class="growth-label" data-col-id="growth">{gb}</td>{cells}</tr>'

    # Growth by tier table rows
    growth_tier_rows_html = ""
    if growth_by_tier:
        for idx, g in enumerate(growth_by_tier):
            cagr_val = g["cagr_pct"]
            if cagr_val is not None:
                cagr_class = "positive" if cagr_val >= 0 else "negative"
                cagr_str = f"{cagr_val:+.1f}%"
            else:
                cagr_class = ""
                cagr_str = "New" if g["mrr_now"] > 0 else "—"
            growth_tier_rows_html += f"""
                        <tr data-row-index="{idx}">
                            <td class="growth-label" data-col-id="tier">{g["tier"]}</td>
                            <td class="num" data-col-id="mrr_now">{format_ars(g["mrr_now"])}</td>
                            <td class="num" data-col="mrr_start" data-col-id="mrr_start">{format_ars(g["mrr_start"])}</td>
                            <td class="num {cagr_class}" data-col="cagr_pct" data-col-id="cagr_pct">{cagr_str}</td>
                        </tr>"""

    # Deals growth by tier table rows
    deals_growth_tier_rows_html = ""
    cutoff_deals = "?"
    if deals_growth_by_tier:
        cutoff_deals = deals_growth_by_tier[0].get("_cutoff_date", "?")
        for idx, g in enumerate(deals_growth_by_tier):
            cagr_val = g["cagr_pct"]
            if cagr_val is not None:
                cagr_class = "positive" if cagr_val >= 0 else "negative"
                cagr_str = f"{cagr_val:+.1f}%"
            else:
                cagr_class = ""
                cagr_str = "New" if g["deals_now"] > 0 else "—"
            deals_growth_tier_rows_html += f"""
                        <tr data-row-index="{idx}">
                            <td class="growth-label" data-col-id="tier">{g["tier"]}</td>
                            <td class="num" data-col-id="companies">{g.get("companies", 0):,}</td>
                            <td class="num" data-col-id="deals_now">{g["deals_now"]:,}</td>
                            <td class="num" data-col="deals_start" data-col-id="deals_start">{g["deals_start"]:,}</td>
                            <td class="num {cagr_class}" data-col="cagr_pct" data-col-id="cagr_pct">{cagr_str}</td>
                        </tr>"""

    # Top 20 accountants table rows
    top_rows_html = ""
    for i, a in enumerate(top_accountants, 1):
        name_display = (a["name"][:50] + "…") if len(a["name"]) > 50 else a["name"]
        hubspot_url = f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL_ID}/company/{a.get('hubspot_id', '')}" if a.get("hubspot_id") else ""
        name_cell = f'<a href="{hubspot_url}" target="_blank" rel="noopener" class="growth-label">{name_display}</a>' if hubspot_url else f'<span class="growth-label">{name_display}</span>'
        cagr_total = a.get("cagr_pct", 0)
        cagr_class = "positive" if cagr_total >= 0 else "negative"
        cagr_str = f"{cagr_total:+.1f}%" if cagr_total is not None else "N/A"
        cagr_billed = a.get("cagr_billed_pct")
        cagr_consultant = a.get("cagr_consultant_pct")
        cagr_billed_str = f"{cagr_billed:+.1f}%" if cagr_billed is not None else ("New" if a.get("_mrr_billed_now", 0) > 0 else "—")
        cagr_consultant_str = f"{cagr_consultant:+.1f}%" if cagr_consultant is not None else ("New" if a.get("_mrr_consultant_now", 0) > 0 else "—")
        cb_class = "positive" if (cagr_billed or 0) >= 0 else "negative"
        cc_class = "positive" if (cagr_consultant or 0) >= 0 else "negative"
        churned_total = (a.get("churned_operador", 0) or 0) + (a.get("churned_asesor", 0) or 0)
        mrr_total = a["mrr"] or 0
        mrr_op = a.get("mrr_operador", 0) or 0
        mrr_as = a.get("mrr_asesor", 0) or 0
        ch_op = a.get("churned_operador", 0) or 0
        ch_as = a.get("churned_asesor", 0) or 0
        churn_pct = (churned_total / (mrr_total + churned_total) * 100) if (mrr_total + churned_total) > 0 else 0
        churn_op_pct = (ch_op / (mrr_op + ch_op) * 100) if (mrr_op + ch_op) > 0 else 0
        churn_as_pct = (ch_as / (mrr_as + ch_as) * 100) if (mrr_as + ch_as) > 0 else 0
        churn_pct_str = f"{churn_pct:.1f}%" if (mrr_total + churned_total) > 0 else "—"
        churn_op_str = f"{churn_op_pct:.1f}%" if (mrr_op + ch_op) > 0 else "—"
        churn_as_str = f"{churn_as_pct:.1f}%" if (mrr_as + ch_as) > 0 else "—"
        lost_op = a.get("lost_mrr_operador", 0) or 0
        lost_as = a.get("lost_mrr_asesor", 0) or 0
        lost_total = lost_op + lost_as
        lost_count = (a.get("lost_count_operador", 0) or 0) + (a.get("lost_count_asesor", 0) or 0)
        top_rows_html += f"""
                        <tr data-row-index="{i-1}">
                            <td class="num" data-col-id="num">{i}</td>
                            <td data-col-id="accountant">{name_cell}</td>
                            <td class="num" data-col-id="mrr">{format_ars(a["mrr"])}</td>
                            <td class="num" data-col-id="mrr_operador">{format_ars(a.get("mrr_operador", 0))}</td>
                            <td class="num" data-col-id="mrr_asesor">{format_ars(a.get("mrr_asesor", 0))}</td>
                            <td class="num" data-col-id="churn">{format_ars(churned_total)}</td>
                            <td class="num" data-col-id="churn_operador">{format_ars(a.get("churned_operador", 0))}</td>
                            <td class="num" data-col-id="churn_asesor">{format_ars(a.get("churned_asesor", 0))}</td>
                            <td class="num" data-col-id="churn_pct">{churn_pct_str}</td>
                            <td class="num" data-col-id="churn_op_pct">{churn_op_str}</td>
                            <td class="num" data-col-id="churn_as_pct">{churn_as_str}</td>
                            <td class="num" data-col-id="lost">{format_ars(lost_total)}</td>
                            <td class="num" data-col-id="lost_operador">{format_ars(lost_op)}</td>
                            <td class="num" data-col-id="lost_asesor">{format_ars(lost_as)}</td>
                            <td class="num" data-col-id="lost_count">{lost_count}</td>
                            <td class="num" data-col-id="operador">{a.get("operator_deals", 0)}</td>
                            <td class="num" data-col-id="asesor">{a.get("consultant_deals", 0)}</td>
                            <td class="num" data-col-id="total_deals">{a.get("total_deals", 0)}</td>
                            <td class="num {cagr_class}" data-col="cagr_pct" data-col-id="cagr_pct">{cagr_str}</td>
                            <td class="num {cb_class}" data-col="cagr_billed_pct" data-col-id="cagr_billed_pct">{cagr_billed_str}</td>
                            <td class="num {cc_class}" data-col="cagr_consultant_pct" data-col-id="cagr_consultant_pct">{cagr_consultant_str}</td>
                        </tr>"""

    # Worst 20 accountants table rows (same structure)
    worst_rows_html = ""
    for i, a in enumerate(worst_accountants, 1):
        name_display = (a["name"][:50] + "…") if len(a["name"]) > 50 else a["name"]
        hubspot_url = f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL_ID}/company/{a.get('hubspot_id', '')}" if a.get("hubspot_id") else ""
        name_cell = f'<a href="{hubspot_url}" target="_blank" rel="noopener" class="growth-label">{name_display}</a>' if hubspot_url else f'<span class="growth-label">{name_display}</span>'
        cagr_total = a.get("cagr_pct", 0)
        cagr_class = "positive" if cagr_total >= 0 else "negative"
        cagr_str = f"{cagr_total:+.1f}%" if cagr_total is not None else "N/A"
        cagr_billed = a.get("cagr_billed_pct")
        cagr_consultant = a.get("cagr_consultant_pct")
        cagr_billed_str = f"{cagr_billed:+.1f}%" if cagr_billed is not None else ("New" if a.get("_mrr_billed_now", 0) > 0 else "—")
        cagr_consultant_str = f"{cagr_consultant:+.1f}%" if cagr_consultant is not None else ("New" if a.get("_mrr_consultant_now", 0) > 0 else "—")
        cb_class = "positive" if (cagr_billed or 0) >= 0 else "negative"
        cc_class = "positive" if (cagr_consultant or 0) >= 0 else "negative"
        churned_total = (a.get("churned_operador", 0) or 0) + (a.get("churned_asesor", 0) or 0)
        mrr_total = a["mrr"] or 0
        mrr_op = a.get("mrr_operador", 0) or 0
        mrr_as = a.get("mrr_asesor", 0) or 0
        ch_op = a.get("churned_operador", 0) or 0
        ch_as = a.get("churned_asesor", 0) or 0
        churn_pct = (churned_total / (mrr_total + churned_total) * 100) if (mrr_total + churned_total) > 0 else 0
        churn_op_pct = (ch_op / (mrr_op + ch_op) * 100) if (mrr_op + ch_op) > 0 else 0
        churn_as_pct = (ch_as / (mrr_as + ch_as) * 100) if (mrr_as + ch_as) > 0 else 0
        churn_pct_str = f"{churn_pct:.1f}%" if (mrr_total + churned_total) > 0 else "—"
        churn_op_str = f"{churn_op_pct:.1f}%" if (mrr_op + ch_op) > 0 else "—"
        churn_as_str = f"{churn_as_pct:.1f}%" if (mrr_as + ch_as) > 0 else "—"
        lost_op = a.get("lost_mrr_operador", 0) or 0
        lost_as = a.get("lost_mrr_asesor", 0) or 0
        lost_total = lost_op + lost_as
        lost_count = (a.get("lost_count_operador", 0) or 0) + (a.get("lost_count_asesor", 0) or 0)
        worst_rows_html += f"""
                        <tr data-row-index="{i-1}">
                            <td class="num" data-col-id="num">{i}</td>
                            <td data-col-id="accountant">{name_cell}</td>
                            <td class="num" data-col-id="mrr">{format_ars(a["mrr"])}</td>
                            <td class="num" data-col-id="mrr_operador">{format_ars(a.get("mrr_operador", 0))}</td>
                            <td class="num" data-col-id="mrr_asesor">{format_ars(a.get("mrr_asesor", 0))}</td>
                            <td class="num" data-col-id="churn">{format_ars(churned_total)}</td>
                            <td class="num" data-col-id="churn_operador">{format_ars(a.get("churned_operador", 0))}</td>
                            <td class="num" data-col-id="churn_asesor">{format_ars(a.get("churned_asesor", 0))}</td>
                            <td class="num" data-col-id="churn_pct">{churn_pct_str}</td>
                            <td class="num" data-col-id="churn_op_pct">{churn_op_str}</td>
                            <td class="num" data-col-id="churn_as_pct">{churn_as_str}</td>
                            <td class="num" data-col-id="lost">{format_ars(lost_total)}</td>
                            <td class="num" data-col-id="lost_operador">{format_ars(lost_op)}</td>
                            <td class="num" data-col-id="lost_asesor">{format_ars(lost_as)}</td>
                            <td class="num" data-col-id="lost_count">{lost_count}</td>
                            <td class="num" data-col-id="operador">{a.get("operator_deals", 0)}</td>
                            <td class="num" data-col-id="asesor">{a.get("consultant_deals", 0)}</td>
                            <td class="num" data-col-id="total_deals">{a.get("total_deals", 0)}</td>
                            <td class="num {cagr_class}" data-col="cagr_pct" data-col-id="cagr_pct">{cagr_str}</td>
                            <td class="num {cb_class}" data-col="cagr_billed_pct" data-col-id="cagr_billed_pct">{cagr_billed_str}</td>
                            <td class="num {cc_class}" data-col="cagr_consultant_pct" data-col-id="cagr_consultant_pct">{cagr_consultant_str}</td>
                        </tr>"""

    # CAGR period options and default for dropdown
    cagr_options = sorted((cagr_data_by_months or {}).keys())
    default_months = CAGR_LOOKBACK_DEFAULT_MONTHS
    default_cutoff = (growth_by_tier or [{}])[0].get("_cutoff_date", "?") if growth_by_tier else "?"
    cagr_dropdown_html = ""
    cagr_data_json = "{}"
    if cagr_data_by_months and cagr_options:
        opts = "".join(
            f'<option value="{m}" {"selected" if m == default_months else ""}>Last {m} months</option>'
            for m in cagr_options
        )
        cagr_dropdown_html = f'''
        <div class="cagr-period-control" style="margin:20px 0 12px 0;display:flex;align-items:center;gap:12px;">
            <label for="cagr-period-select" style="font-size:0.9rem;color:var(--text-muted)">CAGR period (rolling):</label>
            <select id="cagr-period-select" style="padding:6px 12px;border-radius:8px;background:var(--card);border:1px solid var(--border);color:var(--text);font-size:0.9rem;">
                {opts}
            </select>
            <span id="cagr-cutoff-span" class="detail" style="font-size:0.85rem;">Start: {default_cutoff}</span>
        </div>'''
        cagr_data_json = _serialize_cagr_data_for_js(cagr_data_by_months, cols, rows_order)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Colppy - MRR Accountant Offices</title>
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
        .container {{
            max-width: 100%;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text);
        }}
        .subtitle {{
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-bottom: 24px;
        }}
        .top-tier {{
            background: var(--card);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 24px;
            border: 1px solid var(--border);
        }}
        .top-tier h2 {{
            font-size: 1rem;
            font-weight: 600;
            margin: 0 0 12px 0;
            color: var(--text);
        }}
        .top-tier ul {{
            list-style: none;
            padding: 0;
            margin: 0;
            display: flex;
            flex-wrap: wrap;
            gap: 16px 24px;
        }}
        .top-tier li {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9rem;
            color: var(--text-muted);
        }}
        .top-tier li::before {{
            content: "✓";
            color: var(--success);
            font-weight: bold;
        }}
        .main-grid {{
            display: grid;
            grid-template-columns: 1fr 260px;
            gap: 24px;
            align-items: start;
        }}
        @media (max-width: 900px) {{
            .main-grid {{ grid-template-columns: 1fr; }}
        }}
        .matrix-card {{
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
            overflow-x: auto;
            border: 1px solid var(--border);
        }}
        #company-icp .card {{
            background: var(--card);
            border-radius: 8px;
            padding: 12px;
            border: 1px solid var(--border);
        }}
        #company-icp .value {{ font-weight: 700; color: var(--accent); }}
        .matrix-card h2 {{
            font-size: 1rem;
            font-weight: 600;
            margin: 0 0 16px 0;
            color: var(--text);
        }}
        table {{
            width: max-content;
            min-width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: right;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            font-weight: 600;
            color: var(--text-muted);
            text-align: center;
        }}
        .growth-label {{
            text-align: left;
            font-weight: 500;
            color: var(--text);
        }}
        .cell {{
            min-width: 100px;
        }}
        .cell:not(:empty) {{
            color: var(--accent);
        }}
        .sidebar {{
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid var(--accent);
        }}
        .sidebar h2 {{
            font-size: 1rem;
            font-weight: 600;
            margin: 0 0 12px 0;
            color: var(--accent);
        }}
        .sidebar p {{
            font-size: 0.85rem;
            color: var(--text-muted);
            margin: 0 0 16px 0;
            line-height: 1.4;
        }}
        .sidebar .goal {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 12px;
            background: var(--accent-dim);
            border-radius: 8px;
            margin-bottom: 8px;
            font-size: 0.9rem;
        }}
        .sidebar .goal-btn {{
            background: var(--accent);
            color: white;
            border: none;
            padding: 4px 12px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.8rem;
        }}
        .metrics {{
            display: flex;
            flex-wrap: wrap;
            gap: 24px;
            margin-top: 24px;
            padding: 16px 0;
            border-top: 1px solid var(--border);
        }}
        .metric {{
            font-size: 0.9rem;
        }}
        .metric strong {{
            color: var(--accent);
        }}
        .detail {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}
        .positive {{ color: var(--success); }}
        .negative {{ color: #ef4444; }}
        a {{ color: var(--accent); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        table.sortable th {{ cursor: pointer; -webkit-user-select: none; user-select: none; }}
        table.sortable th:hover {{ color: var(--accent); }}
        table.sortable th::after {{ content: " ⇅"; opacity: 0.5; font-size: 0.8em; }}
        .col-hidden {{ display: none !important; }}
        .col-toggle {{ position: relative; display: inline-block; margin-left: 12px; }}
        .col-toggle-btn {{
            padding: 10px 14px; min-height: 44px; font-size: 0.9rem; background: var(--accent-dim); border: 1px solid var(--border);
            border-radius: 8px; color: var(--text); cursor: pointer; display: inline-flex; align-items: center;
        }}
        .col-toggle-btn:hover {{ background: var(--accent); }}
        .col-toggle-dropdown {{
            display: none; position: fixed; z-index: 9999;
            background: var(--card); border: 1px solid var(--border); border-radius: 10px;
            padding: 14px; min-width: 220px; max-width: min(320px, 90vw); max-height: min(360px, 70vh); overflow-y: auto;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }}
        .col-toggle-dropdown.open {{ display: block; }}
        .col-toggle-dropdown label {{ display: flex; align-items: center; gap: 10px; padding: 10px 6px; min-height: 44px; cursor: pointer; font-size: 0.9rem; color: var(--text); border-radius: 6px; }}
        .col-toggle-dropdown label:hover {{ background: var(--accent-dim); color: var(--accent); }}
        .col-toggle-dropdown input {{ margin: 0; width: 18px; height: 18px; flex-shrink: 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Colppy Accountant Offices: Where We Win</h1>
        <p class="subtitle">MRR by Client Portfolio Growth and Managed Tax IDs (ICP accountants only · MRR only, not NRR · includes churned)</p>
        <p class="detail" style="font-size:0.8rem;color:var(--text-muted);margin:-8px 0 16px 0">Generated: {generated_at} — hard refresh (Ctrl+Shift+R / Cmd+Shift+R) if you don’t see this time.</p>

        <div class="top-tier">
            <h2>Top Tier Accountant Offices</h2>
            <ul>
                <li>Growth Oriented</li>
                <li>Offer bookkeeping, payroll and at least one advisory service (tax, legal, HR, etc)</li>
                <li>Value productivity in core workflows (free up time for advisory service)</li>
                <li>Digital Adopters (High quality webpage, e-signature, others)</li>
            </ul>
        </div>

        <div class="main-grid">
            <div class="matrix-card">
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:8px">
                    <h2 style="margin:0">MRR - Accountant Customers (not NRR)</h2>
                    <div class="col-toggle" data-table-id="mrr-matrix"><button type="button" class="col-toggle-btn">Columns</button><div class="col-toggle-dropdown"></div></div>
                </div>
                <table class="sortable" data-table-id="mrr-matrix">
                    <thead>
                        <tr>
                            <th data-col-id="growth">Accountant's Client Portfolio Growth</th>
                            {"".join(f'<th data-col-id="pb-{pb}">Managed Tax IDs: {pb}</th>' for pb in cols)}
                        </tr>
                    </thead>
                    <tbody>
                        {matrix_rows}
                    </tbody>
                </table>
                <p class="detail" style="margin:12px 0 8px 0;font-size:0.8rem;color:var(--text-muted)">Cells = sum of MRR (facturacion amount) for accountants in that segment. Not NRR. Churned MRR = sum of deal.amount for deals with deal_stage Cerrado Churn.</p>
                {_cagr_section(cols, cagr_matrix_rows)}
                <div class="metrics">
                    <span class="metric">Total accountants: <strong>{total_accountants:,}</strong></span>
                    <span class="metric">Total MRR: <strong>{format_ars(total_mrr)}</strong></span>
                    <span class="metric">Avg ticket (MRR/accountant): <strong>{format_ars(avg_ticket)}</strong></span>
                    <span class="metric">Total portfolio (active+churned): <strong>{total_portfolio:,}</strong></span>
                    <span class="metric">Active SMBs: <strong>{total_active:,}</strong></span>
                    <span class="metric">Churned SMBs: <strong>{total_churned:,}</strong></span>
                    <span class="metric">Churned MRR: <strong>{format_ars(churned_mrr)}</strong></span>
                    <span class="metric">Churn rate (SMBs): <strong>{churn_rate_smbs:.1f}%</strong></span>
                    <span class="metric">Churn rate (MRR): <strong>{churn_rate_mrr:.1f}%</strong></span>
                </div>
            </div>
            <div class="sidebar">
                <h2>Colppy Top Accountants</h2>
                <p>Most attractive Accounting Offices to accelerate Accountant Partner Channel Growth</p>
                <div class="goal">
                    <span>Top accountant</span>
                    <span class="goal-btn">{max_related_deals} related deals</span>
                </div>
                <div class="goal">
                    <span>Grow their Client Portfolio</span>
                    <span class="goal-btn">{sidebar_goal_growth}</span>
                </div>
                <div class="goal">
                    <span>Manage</span>
                    <span class="goal-btn">{sidebar_goal_smbs}</span>
                </div>
            </div>
        </div>

        {cagr_dropdown_html}
        {f'<div class="matrix-card" style="margin-top: 24px;"><div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:8px"><h2 style="margin:0">MRR Growth by Portfolio Tier (CAGR rolling)</h2><div class="col-toggle" data-table-id="mrr-growth"><button type="button" class="col-toggle-btn">Columns</button><div class="col-toggle-dropdown"></div></div></div><p class="detail" style="margin-bottom:12px;font-size:0.85rem;color:var(--text-muted)">ICP accountants only. MRR now vs MRR at start of rolling period. Use dropdown above to change period. CAGR = (MRR_now / MRR_start)^(1/years) - 1. Reconstructed from deal close_date.</p><table class="sortable" data-table-id="mrr-growth"><thead><tr><th data-col-id="tier">Managed Tax IDs</th><th class="num" data-col-id="mrr_now">MRR Now</th><th class="num" data-col-id="mrr_start">MRR at Start</th><th class="num" data-col-id="cagr_pct">CAGR % (MRR)</th></tr></thead><tbody id="mrr-growth-tbody">{growth_tier_rows_html}</tbody></table><p class="detail" id="mrr-growth-cutoff" style="margin-top:8px;font-size:0.8rem;">Start: {default_cutoff}</p></div>' if growth_by_tier else ''}
        {f'<div class="matrix-card" style="margin-top: 24px;"><div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:8px"><h2 style="margin:0">Deals Growth by Portfolio Tier (CAGR rolling)</h2><div class="col-toggle" data-table-id="deals-growth"><button type="button" class="col-toggle-btn">Columns</button><div class="col-toggle-dropdown"></div></div></div><p class="detail" style="margin-bottom:12px;font-size:0.85rem;color:var(--text-muted)">ICP accountants only. Deals now vs deals at start of rolling period. Same tier buckets as MRR. CAGR = (deals_now / deals_start)^(1/years) - 1. New = cannot compute CAGR from zero (no deals at start).</p><table class="sortable" data-table-id="deals-growth"><thead><tr><th data-col-id="tier">Managed Tax IDs</th><th class="num" data-col-id="companies">Companies</th><th class="num" data-col-id="deals_now">Deals Now</th><th class="num" data-col-id="deals_start">Deals at Start</th><th class="num" data-col-id="cagr_pct">CAGR % (deals)</th></tr></thead><tbody id="deals-growth-tbody">{deals_growth_tier_rows_html}</tbody></table><p class="detail" id="deals-growth-cutoff" style="margin-top:8px;font-size:0.8rem;">Start: {cutoff_deals}</p></div>' if deals_growth_by_tier else ''}

        <div class="matrix-card" style="margin-top: 24px;">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:8px">
                <h2 style="margin:0">Top 20 Accountants by MRR</h2>
                <div class="col-toggle" data-table-id="top-20"><button type="button" class="col-toggle-btn">Columns</button><div class="col-toggle-dropdown"></div></div>
            </div>
            <p class="detail" style="margin-bottom:12px;font-size:0.85rem;color:var(--text-muted)">ICP accountants only. Operador = type 5 only (bill, excludes hybrids). Asesor = type 8 (includes hybrids). Binary: each deal in one bucket. Total Deals = all associations (matches HubSpot company record). Churn = deal_stage Cerrado Churn (31849274) only. Lost = deal_stage Cerrado Perdido (closedlost). Top accountant has <strong>{max_related_deals}</strong> related deals.</p>
            <table class="sortable" data-table-id="top-20">
                <thead>
                    <tr>
                        <th class="num" data-col-id="num">#</th>
                        <th data-col-id="accountant">Accountant</th>
                        <th class="num" data-col-id="mrr">MRR</th>
                        <th class="num" data-col-id="mrr_operador">MRR Operador</th>
                        <th class="num" data-col-id="mrr_asesor">MRR Asesor</th>
                        <th class="num" data-col-id="churn">Churn</th>
                        <th class="num" data-col-id="churn_operador">Churn Operador</th>
                        <th class="num" data-col-id="churn_asesor">Churn Asesor</th>
                        <th class="num" data-col-id="churn_pct">Churn %</th>
                        <th class="num" data-col-id="churn_op_pct">Churn Operador %</th>
                        <th class="num" data-col-id="churn_as_pct">Churn Asesor %</th>
                        <th class="num" data-col-id="lost">Lost</th>
                        <th class="num" data-col-id="lost_operador">Lost Operador</th>
                        <th class="num" data-col-id="lost_asesor">Lost Asesor</th>
                        <th class="num" data-col-id="lost_count">Lost #</th>
                        <th class="num" data-col-id="operador">Operador</th>
                        <th class="num" data-col-id="asesor">Asesor</th>
                        <th class="num" data-col-id="total_deals">Total Deals</th>
                        <th class="num" data-col-id="cagr_pct">CAGR from start (MRR)</th>
                        <th class="num" data-col-id="cagr_billed_pct">CAGR Operador (MRR)</th>
                        <th class="num" data-col-id="cagr_consultant_pct">CAGR Asesor (MRR)</th>
                    </tr>
                </thead>
                <tbody id="top-20-tbody">
                    {top_rows_html}
                </tbody>
            </table>
        </div>

        <div class="matrix-card" style="margin-top: 24px;">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:8px">
                <h2 style="margin:0">Worst 20 Accountants by Churn %</h2>
                <div class="col-toggle" data-table-id="worst-20"><button type="button" class="col-toggle-btn">Columns</button><div class="col-toggle-dropdown"></div></div>
            </div>
            <p class="detail" style="margin-bottom:12px;font-size:0.85rem;color:var(--text-muted)">ICP accountants with churn deals only. Sorted by Churn % (MRR-based). Same columns as Top 20. Lost = deals closed but no revenue (Cerrado Perdido).</p>
            <table class="sortable" data-table-id="worst-20">
                <thead>
                    <tr>
                        <th class="num" data-col-id="num">#</th>
                        <th data-col-id="accountant">Accountant</th>
                        <th class="num" data-col-id="mrr">MRR</th>
                        <th class="num" data-col-id="mrr_operador">MRR Operador</th>
                        <th class="num" data-col-id="mrr_asesor">MRR Asesor</th>
                        <th class="num" data-col-id="churn">Churn</th>
                        <th class="num" data-col-id="churn_operador">Churn Operador</th>
                        <th class="num" data-col-id="churn_asesor">Churn Asesor</th>
                        <th class="num" data-col-id="churn_pct">Churn %</th>
                        <th class="num" data-col-id="churn_op_pct">Churn Operador %</th>
                        <th class="num" data-col-id="churn_as_pct">Churn Asesor %</th>
                        <th class="num" data-col-id="lost">Lost</th>
                        <th class="num" data-col-id="lost_operador">Lost Operador</th>
                        <th class="num" data-col-id="lost_asesor">Lost Asesor</th>
                        <th class="num" data-col-id="lost_count">Lost #</th>
                        <th class="num" data-col-id="operador">Operador</th>
                        <th class="num" data-col-id="asesor">Asesor</th>
                        <th class="num" data-col-id="total_deals">Total Deals</th>
                        <th class="num" data-col-id="cagr_pct">CAGR from start (MRR)</th>
                        <th class="num" data-col-id="cagr_billed_pct">CAGR Operador (MRR)</th>
                        <th class="num" data-col-id="cagr_consultant_pct">CAGR Asesor (MRR)</th>
                    </tr>
                </thead>
                <tbody id="worst-20-tbody">
                    {worst_rows_html}
                </tbody>
            </table>
        </div>
        {icp_section_html}
    </div>
    <script type="application/json" id="cagr-data-json">{cagr_data_json}</script>
    <script>
    (function() {{
        var cagrDataEl = document.getElementById('cagr-data-json');
        var selectEl = document.getElementById('cagr-period-select');
        if (!cagrDataEl || !selectEl) return;
        var cagrData = JSON.parse(cagrDataEl.textContent || '{{}}'  );
        if (Object.keys(cagrData).length === 0) return;

        function formatArs(v) {{
            if (v == null || v === undefined) return 'N/A';
            var parts = v.toFixed(2).split('.');
            var intPart = parts[0].replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, '.');
            return '$' + intPart + ',' + parts[1];
        }}
        function formatCagr(v, hasNow) {{
            if (v != null && v !== undefined) return (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
            return hasNow ? 'New' : '\u2014';
        }}
        function qsRow(tbodyId, idx) {{
            return document.querySelector('#' + tbodyId + ' tr[data-row-index="' + idx + '"]');
        }}
        function qsCol(row, col) {{
            return row.querySelector('td[data-col="' + col + '"]');
        }}

        function applyCagrPeriod(months) {{
            var key = String(months);
            var d = cagrData[key];
            if (!d) return;

            var cutoff = (d.growth_by_tier && d.growth_by_tier[0]) ? d.growth_by_tier[0].cutoff : '?';
            var cutoffDeals = (d.deals_growth_by_tier && d.deals_growth_by_tier[0]) ? d.deals_growth_by_tier[0].cutoff : '?';
            var cutoffSpan = document.getElementById('cagr-cutoff-span');
            if (cutoffSpan) cutoffSpan.textContent = 'Start: ' + cutoff;

            var mrrCutoff = document.getElementById('mrr-growth-cutoff');
            if (mrrCutoff) mrrCutoff.textContent = 'Start: ' + cutoff;
            var dealsCutoff = document.getElementById('deals-growth-cutoff');
            if (dealsCutoff) dealsCutoff.textContent = 'Start: ' + cutoffDeals;

            if (d.growth_by_tier) {{
                d.growth_by_tier.forEach(function(g, idx) {{
                    var row = qsRow('mrr-growth-tbody', idx);
                    if (!row) return;
                    var mrrStart = qsCol(row, 'mrr_start');
                    var cagrPct = qsCol(row, 'cagr_pct');
                    if (mrrStart) {{ mrrStart.textContent = formatArs(g.mrr_start); }}
                    if (cagrPct) {{
                        var c = g.cagr_pct;
                        cagrPct.textContent = formatCagr(c, g.mrr_now > 0);
                        cagrPct.className = 'num ' + (c != null ? (c >= 0 ? 'positive' : 'negative') : '');
                    }}
                }});
            }}

            if (d.deals_growth_by_tier) {{
                d.deals_growth_by_tier.forEach(function(g, idx) {{
                    var row = qsRow('deals-growth-tbody', idx);
                    if (!row) return;
                    var dealsStart = qsCol(row, 'deals_start');
                    var cagrPct = qsCol(row, 'cagr_pct');
                    if (dealsStart) {{ dealsStart.textContent = (g.deals_start || 0).toLocaleString('es-AR'); }}
                    if (cagrPct) {{
                        var c = g.cagr_pct;
                        cagrPct.textContent = formatCagr(c, g.deals_now > 0);
                        cagrPct.className = 'num ' + (c != null ? (c >= 0 ? 'positive' : 'negative') : '');
                    }}
                }});
            }}

            if (d.top_cagr) {{
                d.top_cagr.forEach(function(a, idx) {{
                    var row = qsRow('top-20-tbody', idx);
                    if (!row) return;
                    var cells = row.querySelectorAll('td[data-col]');
                    cells.forEach(function(cell) {{
                        var col = cell.getAttribute('data-col');
                        var v, hasNow = false;
                        if (col === 'cagr_pct') {{ v = a.cagr_pct; }}
                        else if (col === 'cagr_billed_pct') {{ v = a.cagr_billed_pct; hasNow = (a._mrr_billed_now || 0) > 0; }}
                        else if (col === 'cagr_consultant_pct') {{ v = a.cagr_consultant_pct; hasNow = (a._mrr_consultant_now || 0) > 0; }}
                        if (v !== undefined) {{
                            cell.textContent = formatCagr(v, hasNow);
                            cell.className = 'num ' + (v != null ? (v >= 0 ? 'positive' : 'negative') : '');
                        }}
                    }});
                }});
            }}

            if (d.worst_cagr) {{
                d.worst_cagr.forEach(function(a, idx) {{
                    var row = qsRow('worst-20-tbody', idx);
                    if (!row) return;
                    var cells = row.querySelectorAll('td[data-col]');
                    cells.forEach(function(cell) {{
                        var col = cell.getAttribute('data-col');
                        var v, hasNow = false;
                        if (col === 'cagr_pct') {{ v = a.cagr_pct; }}
                        else if (col === 'cagr_billed_pct') {{ v = a.cagr_billed_pct; hasNow = (a._mrr_billed_now || 0) > 0; }}
                        else if (col === 'cagr_consultant_pct') {{ v = a.cagr_consultant_pct; hasNow = (a._mrr_consultant_now || 0) > 0; }}
                        if (v !== undefined) {{
                            cell.textContent = formatCagr(v, hasNow);
                            cell.className = 'num ' + (v != null ? (v >= 0 ? 'positive' : 'negative') : '');
                        }}
                    }});
                }});
            }}

            if (d.matrix_cagr) {{
                var tbody = document.getElementById('cagr-matrix-tbody');
                if (tbody) {{
                    tbody.querySelectorAll('td[data-gb][data-pb]').forEach(function(td) {{
                        var gb = td.getAttribute('data-gb');
                        var pb = td.getAttribute('data-pb');
                        var k = gb + '|' + pb;
                        var v = d.matrix_cagr[k];
                        td.textContent = (v != null && v !== undefined) ? (v >= 0 ? '+' : '') + v.toFixed(1) + '%' : 'N/A';
                        td.className = 'cell ' + (v != null && v !== undefined ? (v >= 0 ? 'positive' : 'negative') : '');
                    }});
                }}
            }}
            if (window.reapplyAllColVisibility) window.reapplyAllColVisibility();
        }}

        selectEl.addEventListener('change', function() {{ applyCagrPeriod(parseInt(selectEl.value, 10)); }});
    }})();
    (function() {{
        var STORAGE_KEY = 'mrr-dashboard-cols';
        function loadColVisibility(tableId) {{
            try {{
                var s = localStorage.getItem(STORAGE_KEY);
                if (!s) return null;
                var all = JSON.parse(s);
                return all[tableId] || null;
            }} catch (e) {{ return null; }}
        }}
        function saveColVisibility(tableId, vis) {{
            try {{
                var all = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
                all[tableId] = vis;
                localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
            }} catch (e) {{}}
        }}
        function applyColVisibility(table, vis) {{
            if (!vis) return;
            table.querySelectorAll('[data-col-id]').forEach(function(el) {{
                var id = el.getAttribute('data-col-id');
                if (vis[id] === false) el.classList.add('col-hidden');
                else el.classList.remove('col-hidden');
            }});
        }}
        document.querySelectorAll('.col-toggle').forEach(function(toggle) {{
            var tableId = toggle.getAttribute('data-table-id');
            var table = document.querySelector('table[data-table-id="' + tableId + '"]');
            if (!table) return;
            var btn = toggle.querySelector('.col-toggle-btn');
            var dropdown = toggle.querySelector('.col-toggle-dropdown');
            var headers = table.querySelectorAll('thead th[data-col-id]');
            var vis = loadColVisibility(tableId) || {{}};
            var checkboxes = [];
            var toggleAllLink = document.createElement('div');
            toggleAllLink.style.cssText = 'display:flex;gap:12px;margin-bottom:10px;padding:8px 0 10px 0;border-bottom:1px solid var(--border);font-size:0.9rem;';
            var selAll = document.createElement('a');
            selAll.textContent = 'Select all';
            selAll.href = '#';
            selAll.style.color = 'var(--accent)';
            var deselAll = document.createElement('a');
            deselAll.textContent = 'Deselect all';
            deselAll.href = '#';
            deselAll.style.color = 'var(--accent)';
            toggleAllLink.appendChild(selAll);
            toggleAllLink.appendChild(deselAll);
            dropdown.appendChild(toggleAllLink);
            function setAll(state) {{
                checkboxes.forEach(function(cb) {{
                    cb.checked = state;
                    var id = cb.dataset.colId;
                    vis[id] = state;
                    table.querySelectorAll('[data-col-id="' + id + '"]').forEach(function(el) {{
                        if (state) el.classList.remove('col-hidden');
                        else el.classList.add('col-hidden');
                    }});
                }});
                saveColVisibility(tableId, vis);
            }}
            selAll.addEventListener('click', function(e) {{ e.preventDefault(); setAll(true); }});
            deselAll.addEventListener('click', function(e) {{ e.preventDefault(); setAll(false); }});
            headers.forEach(function(th) {{
                var id = th.getAttribute('data-col-id');
                if (vis[id] === undefined) vis[id] = true;
                var label = document.createElement('label');
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = vis[id];
                cb.dataset.colId = id;
                checkboxes.push(cb);
                cb.addEventListener('change', function() {{
                    vis[id] = cb.checked;
                    table.querySelectorAll('[data-col-id="' + id + '"]').forEach(function(el) {{
                        if (cb.checked) el.classList.remove('col-hidden');
                        else el.classList.add('col-hidden');
                    }});
                    saveColVisibility(tableId, vis);
                }});
                label.appendChild(cb);
                label.appendChild(document.createTextNode(th.textContent.trim()));
                dropdown.appendChild(label);
            }});
            applyColVisibility(table, vis);
            function positionDropdown() {{
                var rect = btn.getBoundingClientRect();
                var dropW = dropdown.offsetWidth || 220;
                var dropH = dropdown.offsetHeight || Math.min(360, window.innerHeight * 0.7);
                var pad = 8;
                var left = rect.left;
                var top = rect.bottom + pad;
                if (left + dropW > window.innerWidth - pad) left = window.innerWidth - dropW - pad;
                if (left < pad) left = pad;
                if (top + dropH > window.innerHeight - pad) {{ top = rect.top - dropH - pad; }}
                if (top < pad) top = pad;
                dropdown.style.left = left + 'px';
                dropdown.style.top = top + 'px';
            }}
            btn.addEventListener('click', function(e) {{
                e.stopPropagation();
                var isOpening = !dropdown.classList.contains('open');
                dropdown.classList.toggle('open');
                if (isOpening) {{ dropdown.style.left = ''; dropdown.style.top = ''; requestAnimationFrame(positionDropdown); }}
            }});
            document.addEventListener('click', function() {{ dropdown.classList.remove('open'); }});
            dropdown.addEventListener('click', function(e) {{ e.stopPropagation(); }});
            window.addEventListener('resize', function() {{ if (dropdown.classList.contains('open')) positionDropdown(); }});
        }});
        window.reapplyAllColVisibility = function() {{
            document.querySelectorAll('table[data-table-id]').forEach(function(table) {{
                var tableId = table.getAttribute('data-table-id');
                var vis = loadColVisibility(tableId);
                if (vis) applyColVisibility(table, vis);
            }});
        }};
    }})();
    document.querySelectorAll("table.sortable").forEach(function(table) {{
        var headers = table.querySelectorAll("th");
        headers.forEach(function(th, idx) {{
            th.addEventListener("click", function() {{
                var tbody = table.querySelector("tbody");
                var rows = Array.from(tbody.querySelectorAll("tr"));
                var asc = th.getAttribute("data-sort") !== "asc";
                th.setAttribute("data-sort", asc ? "asc" : "desc");
                rows.sort(function(a, b) {{
                    var va = a.cells[idx] ? a.cells[idx].textContent.trim() : "";
                    var vb = b.cells[idx] ? b.cells[idx].textContent.trim() : "";
                    var cell = a.cells[idx];
                    var isNum = cell && (cell.classList.contains("num") || /^[$€]?[\d.,\s]+%?$|^[+-]?[\d.]+\s*%?$|^[+-]?[\d,]+%?$/.test(va));
                    if (isNum) {{
                        var parseVal = function(s) {{
                            if (!s || s === "N/A" || s === "—" || s === "New") return NaN;
                            var neg = s.includes("-") && s.indexOf("-") < 3;
                            var n = parseFloat(s.replace(/[.$€\s]/g, "").replace(",", ".").replace(/[^0-9.-]/g, "")) || 0;
                            return neg ? -Math.abs(n) : n;
                        }};
                        var na = parseVal(va), nb = parseVal(vb);
                        if (isNaN(na) && isNaN(nb)) return 0;
                        if (isNaN(na)) return asc ? 1 : -1;
                        if (isNaN(nb)) return asc ? -1 : 1;
                        return asc ? na - nb : nb - na;
                    }}
                    return asc ? (va < vb ? -1 : va > vb ? 1 : 0) : (vb < va ? -1 : vb > va ? 1 : 0);
                }});
                rows.forEach(function(r) {{ tbody.appendChild(r); }});
            }});
        }});
    }});
    </script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Colppy Accountant MRR Matrix (Nubox-style)")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to facturacion_hubspot.db")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("--html", metavar="PATH", help="Generate HTML dashboard (e.g. tools/outputs/mrr_dashboard.html)")
    parser.add_argument("--serve", action="store_true", help="Serve dashboard and open in browser (implies --html)")
    parser.add_argument("--verify", action="store_true", help="Print verification examples (formulas and one cell per section) to validate calculations")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        print("Run build_facturacion_hubspot_mapping.py first.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    metrics = get_accountant_metrics(conn)
    churn_metrics = get_portfolio_churn_metrics(conn)
    icp_metrics = get_company_icp_metrics(conn)
    conn.close()

    if not metrics:
        print("No accountant data (need portfolio_12m_ago > 0).")
        return 0

    matrix = build_matrix(metrics)

    # Pre-compute CAGR data for all period options (for dashboard dropdown)
    cagr_data_by_months: dict[int, dict] = {}
    for months in CAGR_LOOKBACK_MONTHS_OPTIONS:
        conn = sqlite3.connect(str(db_path))
        growth_by_tier = get_growth_by_tier(conn, months=months)
        deals_growth_by_tier = get_deals_growth_by_tier(conn, months=months)
        top_accountants = get_top_accountants(conn, limit=20, order_by="mrr", months=months)
        worst_accountants = get_top_accountants(conn, limit=20, order_by="churn_pct", months=months)
        mrr_now_by_id, mrr_start_by_id, years = get_accountant_mrr_timeline(conn, months=months)
        conn.close()
        matrix_cagr = build_matrix_cagr(metrics, mrr_start_by_id, years)
        cagr_data_by_months[months] = {
            "growth_by_tier": growth_by_tier,
            "deals_growth_by_tier": deals_growth_by_tier,
            "top_accountants": top_accountants,
            "worst_accountants": worst_accountants,
            "matrix_cagr": matrix_cagr,
        }

    # Use default for initial display
    default_data = cagr_data_by_months[CAGR_LOOKBACK_DEFAULT_MONTHS]
    top_accountants = default_data["top_accountants"]
    worst_accountants = default_data["worst_accountants"]
    growth_by_tier = default_data["growth_by_tier"]
    deals_growth_by_tier = default_data["deals_growth_by_tier"]
    matrix_cagr = default_data["matrix_cagr"]

    # Column headers (portfolio buckets)
    cols = [pb for _, _, pb in PORTFOLIO_BUCKETS]
    rows_order = [gb for gb, _ in GROWTH_BUCKETS]

    if args.verify:
        print_verification_examples(
            db_path, metrics, matrix,
            growth_by_tier, deals_growth_by_tier, matrix_cagr,
            cols, rows_order,
        )

    if args.csv:
        print("growth_bucket," + ",".join(cols))
        for gb in rows_order:
            cells = [format_ars(matrix.get((gb, pb), 0)) for pb in cols]
            print(f"{gb}," + ",".join(cells))
        return 0

    html_path = args.html or (Path("tools/outputs/mrr_dashboard.html") if args.serve else None)
    if html_path:
        html_path = Path(html_path)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html = generate_dashboard_html(matrix, matrix_cagr, metrics, cols, rows_order, top_accountants, worst_accountants, churn_metrics, growth_by_tier, deals_growth_by_tier, cagr_data_by_months, icp_metrics)
        html_path.write_text(html, encoding="utf-8")
        print(f"Dashboard written to: {html_path.absolute()}")
        if args.serve:
            port = 8765
            try:
                out = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if out.returncode == 0 and out.stdout.strip():
                    pids = out.stdout.strip().split()
                    subprocess.run(["kill", "-9"] + pids, capture_output=True, timeout=5)
                    time.sleep(0.5)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            def make_handler(db):
                class DashboardHandler(BaseHTTPRequestHandler):
                    """Serves dashboard regenerated from DB on each request (no refresh needed)."""

                    def do_GET(self):
                        if self.path in ("/", "/mrr_dashboard.html"):
                            try:
                                html = build_dashboard_from_db(db)
                                self.send_response(200)
                                self.send_header("Content-Type", "text/html; charset=utf-8")
                                self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                                self.end_headers()
                                self.wfile.write(html.encode("utf-8"))
                            except Exception as e:
                                self.send_response(500)
                                self.send_header("Content-Type", "text/plain; charset=utf-8")
                                self.end_headers()
                                self.wfile.write(f"Error: {e}".encode("utf-8"))
                        else:
                            self.send_response(404)
                            self.end_headers()

                    def log_message(self, format, *args):
                        pass

                return DashboardHandler

            server = HTTPServer(("", port), make_handler(db_path))
            url = f"http://localhost:{port}/"
            print(f"Serving at {url} (dashboard regenerated from DB on each request)")
            webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            return 0
        return 0

    # Table output (slide format)
    cell_width = 18
    print("\n" + "=" * 100)
    print("MRR - Accountant Customers (Colppy)")
    print("=" * 100)
    header = "Growth / Portfolio"
    print(f"\n{header:<22}" + "".join(f"{c:^{cell_width}}" for c in cols))
    print("-" * 100)
    for gb in rows_order:
        cells = []
        for pb in cols:
            val = matrix.get((gb, pb), 0)
            cells.append(format_ars(val) if val else "N/A")
        print(f"{gb:<22}" + "".join(f"{c:^{cell_width}}" for c in cells))
    print("-" * 100)

    total_mrr = sum(m["mrr"] for m in metrics)
    total_accountants = len(metrics)
    avg_ticket = total_mrr / total_accountants if total_accountants else 0
    total_portfolio = sum(m["portfolio"] for m in metrics)
    total_active = sum(m.get("active", m["portfolio"]) for m in metrics)
    total_churned = sum(m.get("churned", 0) for m in metrics)
    churned_mrr = churn_metrics.get("churned_mrr", 0)
    churn_rate_smbs = (total_churned / total_portfolio * 100) if total_portfolio else 0
    churn_rate_mrr = (churned_mrr / (total_mrr + churned_mrr) * 100) if (total_mrr + churned_mrr) else 0

    print(f"\nTotal accountants: {total_accountants} | Total MRR: {format_ars(total_mrr)}")
    print(f"Avg ticket (MRR/accountant): {format_ars(avg_ticket)}")
    print(f"Portfolio (active+churned): {total_portfolio:,} | Active: {total_active:,} | Churned: {total_churned:,}")
    print(f"Churned MRR: {format_ars(churned_mrr)} | Churn rate (SMBs): {churn_rate_smbs:.1f}% | Churn rate (MRR): {churn_rate_mrr:.1f}%")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
