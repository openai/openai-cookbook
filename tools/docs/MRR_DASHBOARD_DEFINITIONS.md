# Colppy MRR Dashboard – Definitions and How It Works

**Purpose:** Team-shareable document explaining the MRR dashboard metrics, formulas, and data flow. Use this when onboarding or when questions arise about how the dashboard is built.

**Last Updated:** 2026-02-16

---

## 1. Overview

The **MRR Dashboard** shows accountant portfolio behavior: growth, churn, MRR by portfolio size, and CAGR. It uses:

- **Billing data** (facturacion) as the source of truth for MRR
- **HubSpot** for deal–company associations (who is the accountant vs the customer)
- **Association type 8** (Estudio Contable) to identify accountant companies

---

## 2. Data Sources

| Source | What it provides |
|--------|------------------|
| **facturacion.csv** | Billing: `id_empresa`, `customer_cuit`, `amount`, etc. Canonical source for MRR. |
| **HubSpot** | Companies, deals, deal–company associations. Used to link deals to accountants. |
| **facturacion_hubspot.db** | Local SQLite DB built from facturacion + HubSpot. Tables: `facturacion`, `deals`, `companies`, `deal_associations`. |

---

## 3. Association Types (Deal–Company)

| Type ID | Label | Meaning |
|---------|-------|---------|
| **5** | Primary | Billing company – who we invoice. Exactly one per deal. |
| **8** | Estudio Contable | Accountant firm associated with the deal. A deal can have multiple. |
| **11** | Compañía con Múltiples Negocios | Multi-entity, referrer, etc. |
| **341** | Default | Standard association. |

**Important:** The dashboard uses **type 8** to identify accountant companies and build their portfolios. If a company is Cuenta Contador but only has type 341, it will not appear as an accountant in the dashboard until type 8 is added.

---

## 4. Buckets (Matrix Axes)

### Growth Buckets (rows)

| Bucket | Condition | Example |
|--------|-----------|---------|
| &lt;-14% | growth &lt; -14 | -20% |
| -14% to 0% | -14 ≤ growth &lt; 0 | -5% |
| 0% to +14% | 0 ≤ growth &lt; 14 | +8% |
| &gt;+14% | growth ≥ 14 | +25% |

### Portfolio Buckets (columns)

| Bucket | Managed SMBs | Example |
|--------|--------------|---------|
| 1 | 1 | 1 SMB |
| 2 | 2 | 2 SMBs |
| 3–5 | 3 to 5 | 4 SMBs |
| 6–10 | 6 to 10 | 8 SMBs |
| 11–20 | 11 to 20 | 15 SMBs |
| 20–40 | 21 to 40 | 30 SMBs |
| 40–100 | 41 to 100 | 50 SMBs |
| 100–200 | 101 to 200 | 150 SMBs |
| 200+ | 201 or more | 250 SMBs |

---

## 5. Core Formulas

| Metric | Formula |
|--------|---------|
| **Portfolio beginning** | Count of distinct `id_empresa` with `close_date` ≤ first_close + 90 days |
| **Active portfolio** | Count of `id_empresa` in facturacion (currently paying) |
| **Churned portfolio** | Count of `id_empresa` with `deal_stage` = Cerrado Churn (31849274) |
| **Total portfolio** | Active + Churned |
| **Growth %** | (active_portfolio − portfolio_beginning) / portfolio_beginning × 100 |
| **MRR (per accountant)** | SUM(amount) from facturacion for `id_empresa` in accountant's portfolio |
| **MRR matrix cell** | SUM(MRR) of all accountants in that (growth_bucket, portfolio_bucket) |
| **CAGR %** | ((MRR_now / MRR_start)^(1/years) − 1) × 100 |
| **Churn SMBs %** | total_churned / total_portfolio × 100 |
| **Churn MRR %** | churned_mrr / (total_mrr + churned_mrr) × 100 |

---

## 6. Sidebar (Colppy Top Accountants)

| Metric | Procedure |
|--------|-----------|
| **Related deals** | MAX(operator_deals + consultant_deals) across top 20 |
| **Grow portfolio (YoY)** | MEDIAN(CAGR %) of top 20 |
| **Manage SMBs** | MIN(total_deals of top 20) + " SMBs" |

---

## 7. Refresh Pipeline

To keep the dashboard up to date:

1. **Full refresh** (billing + HubSpot changed):
   ```bash
   ./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs
   ```
   Runs: build → populate_deal_associations → populate_accountant_deals → regenerate dashboards.

2. **Dashboard only** (no new billing/HubSpot data):
   ```bash
   ./tools/scripts/hubspot/refresh_dashboard.sh --dashboard-only --output-dir docs
   ```

3. **After fixing deal associations** (e.g. redundant type 8 removal, Group 4):
   ```bash
   python tools/scripts/hubspot/populate_deal_associations.py --db tools/outputs/facturacion_hubspot.db
   python tools/scripts/hubspot/populate_accountant_deals.py --db tools/outputs/facturacion_hubspot.db
   ./tools/scripts/hubspot/refresh_dashboard.sh --dashboard-only --output-dir docs
   ```

---

## 8. Related Documentation

- [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md) – Association rules, fix workflow, redundant type 8
- [dashboard_math_procedure.csv](../outputs/dashboard_math_procedure.csv) – Detailed formulas and examples
- [ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md](./ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md) – ICP and company type definitions
