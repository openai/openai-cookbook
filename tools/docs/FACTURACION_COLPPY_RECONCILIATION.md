# Reconciliation: Billing ↔ Colppy ↔ facturacion_hubspot.db

**Purpose:** Design and process for reconciling data across three sources. See [DATA_SOURCES_TERMINOLOGY.md](./DATA_SOURCES_TERMINOLOGY.md) for standard terms.

| Source | Artifact | Meaning |
|--------|----------|---------|
| **Billing** | facturacion.csv | Manual export from billing process; CRM mapping source |
| **Colppy** | Colppy MySQL (facturacion, pago, empresa, plan) | Colppy product DB; where payments happen |
| **facturacion_hubspot.db** | SQLite | Built from billing CSV + HubSpot; facturacion table = billing |

**Last Updated:** 2026-02-24

---

## Reconciliation Logging

All reconciliation scripts log each run to `reconciliation_logs` in `facturacion_hubspot.db`. Use this to track progress and compare variations between data refreshes.

**View history:**
```bash
python tools/scripts/colppy/show_reconciliation_history.py
python tools/scripts/colppy/show_reconciliation_history.py --script reconcile_colppy_hubspot --limit 10
```

**Run Colppy ↔ HubSpot reconciliation (parametrized by year/month):**
```bash
# API-based (Colppy snapshot + HubSpot API)
python tools/scripts/colppy/reconcile_colppy_hubspot.py --year 2026 --month 2

# DB-only (colppy_export.db + facturacion_hubspot.db, no API)
python tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py --year 2026 --month 1
```

**Record-level diff (fixed, new, unchanged, regression):**
```bash
python tools/scripts/colppy/show_reconciliation_history.py --diff
python tools/scripts/colppy/show_reconciliation_history.py --diff --filter fixed,new
```

**Skip logging:** Add `--no-log` to any reconciliation script.

---

## HubSpot Refresh Evolution Tracking

When refreshing HubSpot deals (`--refresh-deals-only`), the system logs what changed (added/updated/removed) so you can track evolution even when Colppy staging is unavailable.

**Table:** `hubspot_refresh_logs` in `facturacion_hubspot.db` (timestamps in Argentina timezone).

**View history:**
```bash
python tools/scripts/hubspot/show_hubspot_refresh_history.py
python tools/scripts/hubspot/show_hubspot_refresh_history.py --limit 10
python tools/scripts/hubspot/show_hubspot_refresh_history.py --period 2026-02
```

**Logger:** `tools/utils/hubspot_refresh_logger.py` — used by `build_facturacion_hubspot_mapping.py` when `--refresh-deals-only` runs.

**Stale data cleanup:** All refresh operations remove outdated data to avoid discrepancies:
- **Full build:** `DELETE FROM deals` before populate; then run `--refresh-deals-only` for each month needed.
- **refresh-deals-only:** Deletes deals that were in the DB for that month but HubSpot no longer returns (closedate changed or deal removed).
- **export_colppy_to_sqlite** (timeframe): Deletes existing rows for that month before insert.
- **facturacion table:** Full replace (`DELETE FROM facturacion` then INSERT) on every build.
- **companies table:** Full replace (DROP + CREATE) on every build.

---

## Deal Age Classification (Fresh vs Old Deal)

When a deal shows `close_date` in a given month, it may be a **fresh close** (newly won) or an **old deal** whose close date was updated later. Use `classify_deal_age_from_history.py` to distinguish:

| Classification | Meaning |
|----------------|---------|
| **fresh_close** | Deal created and closed in same/similar period |
| **old_deal_date_correction** | Deal was first closed long ago; closedate was updated later (e.g. by integration) |
| **slow_close** | Deal created long ago, first closed in the period (genuine slow close) |

**Usage:**
```bash
# Deals from facturacion_hubspot.db for a month
python tools/scripts/hubspot/classify_deal_age_from_history.py --year 2026 --month 2

# Specific deal IDs
python tools/scripts/hubspot/classify_deal_age_from_history.py --deal-ids 13424641957

# Export to CSV
python tools/scripts/hubspot/classify_deal_age_from_history.py --year 2026 --month 2 --output results.csv
```

**Logic:** Fetches `createdate`, `closedate`, and `dealstage` history from HubSpot. Uses the **first time** the deal entered closedwon (from dealstage history) as the true close date. If current closedate is >180 days after that, it's `old_deal_date_correction`. If createdate is >180 days before first closedwon, it's `slow_close`.

### Recovery Check (potential_recovered + recovered_confirmed)

For HubSpot-only deals, use `reconcile_with_recovery_check.py` to:
1. **Flag** `old_deal_date_correction` as **potential_recovered** (deal was first closed long ago; close date updated to reflect payment in this period)
2. **Check Colppy** for recurring payments (`primerPago=0`) in that month
3. **Confirm** as **recovered_confirmed** when Colppy has a payment

```bash
python tools/scripts/colppy/reconcile_with_recovery_check.py --year 2026 --month 2
python tools/scripts/colppy/reconcile_with_recovery_check.py --year 2026 --month 2 --output report.md
```

Requires: `HUBSPOT_API_KEY`, `colppy_export.db` with full pago table (recurring payments). The close date then correctly reflects when the product was paid (first time or again).

---

## 1. Data Sources

| Source | Purpose | Key columns | Update frequency |
|--------|---------|-------------|------------------|
| **Billing** (facturacion.csv) | Manual export from billing process; CRM/HubSpot mapping | email, customer_cuit, plan, id_plan, amount, product_cuit, id_empresa | Manual (periodic export) |
| **facturacion_hubspot.db** | SQLite built from billing CSV + HubSpot API | facturacion (from billing), companies, deals, deal_associations | Built by `build_facturacion_hubspot_mapping.py` |
| **Colppy MySQL** | Colppy product DB; payments, Colppy facturacion | facturacion (IdEmpresa, CUIT), pago, empresa, plan | Real-time |

### Column Mapping

| Billing (facturacion.csv) | Colppy MySQL |
|-----------------|--------------|
| id_empresa | facturacion.IdEmpresa = empresa.IdEmpresa |
| customer_cuit | facturacion.CUIT (invoice recipient CUIT) |
| product_cuit | empresa.CUIT (service holder CUIT) |
| email | facturacion.email |
| plan | plan.nombre (via empresa.idPlan) |
| id_plan | empresa.idPlan |
| amount | plan.precio (standard) or custom in CSV |

**CUIT types:** See [DATA_SOURCES_TERMINOLOGY.md](./DATA_SOURCES_TERMINOLOGY.md) §3.5 — **Service holder CUIT** (company that uses the product) vs **Invoice recipient CUIT** (entity we send the invoice to). In channel billing, Colppy facturacion.CUIT = invoice recipient; billing product_cuit = service holder.

**Note:** Colppy `plan.precio` is the standard plan price. The billing CSV may have custom amounts (discounts, promotions). Amount differences are expected for custom pricing.

**IVA:** Colppy amounts (plan.precio, pago.importe) are **con IVA** (21%). HubSpot deal amount is **sin IVA**. When reconciling amounts between Colppy and HubSpot (e.g. in `reconcile_fecha_primer_pago_colppy.py`), use: `Colppy_importe / 1.21 ≈ HubSpot_amount`.

---

## 2. Reconciliation Script

**Script:** `tools/scripts/colppy/reconcile_facturacion_colppy.py`

**Usage:**
```bash
# Basic: CSV vs Colppy MySQL
python tools/scripts/colppy/reconcile_facturacion_colppy.py

# Custom CSV path
python tools/scripts/colppy/reconcile_facturacion_colppy.py --csv tools/outputs/facturacion.csv

# Also compare facturacion_hubspot.db
python tools/scripts/colppy/reconcile_facturacion_colppy.py --include-db

# Export Colppy facturacion to CSV (for backup or comparison)
python tools/scripts/colppy/reconcile_facturacion_colppy.py --export-colppy tools/outputs/colppy_facturacion_export.csv
```

---

## 3. Reconciliation Directions

| Direction | Meaning | Action |
|-----------|---------|--------|
| **In Billing only** | id_empresa in billing CSV but not in Colppy (fechaBaja IS NULL) | Likely churned or has fechaBaja set in Colppy. Verify in Colppy; if churned, remove from CSV or update export. |
| **In Colppy only** | id_empresa in Colppy but not in billing CSV | Billing CSV may be filtered (e.g. excluding "Pendiente de Pago"). Run `--export-colppy` to get full Colppy snapshot. |
| **In both** | id_empresa in both | Compare plan, amount, customer_cuit, product_cuit. Differences may indicate: (a) custom pricing in billing CSV, (b) plan change in Colppy, (c) data sync issue. |

---

## 4. Typical Results

| Metric | Typical range |
|--------|----------------|
| **In both** | Most of CSV rows (CSV is subset of Colppy) |
| **In CSV only** | Small (churned since last export) |
| **In Colppy only** | Large (many in "Pendiente de Pago" or not in export) |
| **Differences** | Amount differences common (custom pricing); plan/cuit differences need investigation |

---

## 5. Workflow (Similar to HubSpot + Facturacion)

1. **Run reconciliation** periodically: `reconcile_facturacion_colppy.py`
2. **Review "In CSV only"** — verify churned in Colppy; update CSV export if needed
3. **Review "In Colppy only"** — decide if CSV should include more (e.g. Pendiente de Pago)
4. **Review differences** — amount vs plan/cuit: amount often custom; plan/cuit changes require data fix
5. **Refresh facturacion.csv** — when Colppy is source of truth, run `--export-colppy` and use as new CSV (after validation)
6. **Rebuild facturacion_hubspot.db** — after CSV update: `build_facturacion_hubspot_mapping.py`
7. **Timeframe-only refresh** — for a given month: `export_colppy_to_sqlite.py --year 2026 --month 1` and `build_facturacion_hubspot_mapping.py --refresh-deals-only --year 2026 --month 1`

---

## 6. Master Source Decision

| Use case | Master source |
|----------|---------------|
| **CRM/HubSpot mapping** | Billing (facturacion.csv — manual export, curated) |
| **Live billing state** | Colppy MySQL |
| **Reconciliation** | Compare both; fix billing CSV when Colppy is correct; fix Colppy when billing CSV reflects correct business state |

**Do not overwrite facturacion.csv** (billing export) without explicit confirmation. Use `--export-colppy` to generate a Colppy snapshot; compare manually before replacing.

---

## 6.1 Colppy ↔ HubSpot: Colppy is Master, Mismatch Reasons

**Script:** `reconcile_colppy_hubspot_db_only.py`

**Colppy is master** for id_empresa, close date, and id_plan. Mismatch reasons:

| Reason | Meaning | Action |
|--------|---------|--------|
| **close_date** | Colppy fechaPago ≠ HubSpot close_date | Update HubSpot close_date to match Colppy (compliance) |
| **id_plan** | Colppy idPlan ≠ HubSpot colppy_plan (both non-blank) | Update HubSpot colppy_plan to match Colppy (defines amount) |
| **id_empresa** | HubSpot has CRM id instead of Colppy id, or deal missing | Use `fix_colppy_id_empresa_on_deals.py` or create deal |
| **NO_HUBSPOT_DEAL** | Colppy has first payment, no HubSpot deal | Create deal (with confirmation) |
| **WRONG_STAGE** | Deal exists in HubSpot but not closed-won (e.g. Cerrado Churn) | Move to closed-won, set close_date = Colppy fechaPago |
| **NO_COLPPY_PAYMENT** | HubSpot has deal, no Colppy first payment in that month | Verify; may be wrong close_date or not yet paid |
| **WRONG_CLOSE_DATE** | Deal/payment exists but in different month | Update HubSpot close_date or investigate |
| **PLAN_MISMATCH** | Both have id_plan but values differ | Update HubSpot colppy_plan to match Colppy idPlan |

**id_plan:** HubSpot deal property `colppy_plan` = Colppy `pago.idPlan`. Either side can be blank; only flag mismatch when both are non-blank and differ.

**WRONG_STAGE detection:** Requires `deals_any_stage` populated. Run HubSpot refresh with `--fetch-wrong-stage` to fetch deals by id_empresa regardless of stage (Colppy-only + facturacion no deal). See [RECONCILE_REPORT_GROUPS.md](./RECONCILE_REPORT_GROUPS.md).

---

## 6.2 Colppy ↔ HubSpot: 4-Group Report Structure

**Full reference:** [RECONCILE_REPORT_GROUPS.md](./RECONCILE_REPORT_GROUPS.md)

The reconciliation report is organized into **4 groups**:

| Group | Meaning |
|-------|---------|
| **1. Match same month** | fechaPago ≠ close_date (same month, wrong day). Action: Set HubSpot close_date = Colppy fechaPago. |
| **2. Match different month** | HubSpot deal exists but close_date in another month. Action: Set HubSpot close_date = Colppy fechaPago. |
| **3. Wrong Stage** | COLPPY_NOT_ACTIVE (activa≠0), WRONG_STAGE (deal e.g. Cerrado Churn), NO_HUBSPOT_DEAL. |
| **4. HubSpot only** | Closed-won this month; Colppy first payment in different month or absent. |

**Data sources:** colppy_export.db | facturacion_hubspot.db (deals + deals_any_stage)

**Usage:**
```bash
# 1. HubSpot refresh with --fetch-wrong-stage (populates deals_any_stage for WRONG_STAGE)
python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year 2026 --month 2 --fetch-wrong-stage

# 2. Run reconciliation
python tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py --year 2026 --month 2 --output tools/outputs/reconcile_202602_db.md
```

---

## 6.3 Export Snapshot for Plugin & Full Refresh

**Export snapshots** (for Claude plugin):
- `export_reconciliation_snapshot.py` — first payments + facturacion.
- `export_reconciliation_db_snapshot.py` — Colppy ↔ HubSpot reconciliation by month.

```bash
python tools/scripts/colppy/export_reconciliation_snapshot.py --months 62
python tools/scripts/colppy/export_reconciliation_db_snapshot.py --months 14
# Outputs: plugins/colppy-revops/docs/colppy_*_snapshot.json
```

**Full refresh from Jan 2025** (HubSpot all months + export + publish):
```bash
./tools/scripts/run_full_refresh_and_publish.sh
# Log: /tmp/full_refresh_publish.log
# Runs in background; ~35–50 min for 14 months
```

---

## 7. First Payments Reconciliation (by Month)

**Script:** `tools/scripts/colppy/first_payments_reconciliation.py`

Queries first payments (primerPago=1) for a given month, joins Colppy facturacion (cuit_invoicing), mrr_calculo (MRR), and matches against billing (facturacion.csv) by CUIT.

**Usage:**
```bash
# By month
python tools/scripts/colppy/first_payments_reconciliation.py --month 2026-01

# By date range
python tools/scripts/colppy/first_payments_reconciliation.py --start 2026-01-01 --end 2026-01-31

# Export to CSV
python tools/scripts/colppy/first_payments_reconciliation.py --month 2026-01 --csv

# Use local SQLite (no MySQL): run export_colppy_to_sqlite.py first
python tools/scripts/colppy/first_payments_reconciliation.py --month 2026-01 --local
```

**Output:** idPago, idEmpresa, plan_name, fechaPago, importe, medioPago, cuit_invoicing, mrrLocal, mrrUsd, match_type, csv_id_empresa, csv_email, csv_plan.

**Note:** With `--local`, mrrLocal and mrrUsd are empty (mrr_calculo is not in the SQLite export).

---

## 8. Local SQLite Export (When Staging DB Unavailable)

When you don't have access to Colppy staging MySQL, export key tables to a local SQLite DB for offline reconciliation.

**Script:** `tools/scripts/colppy/export_colppy_to_sqlite.py`

**Usage:**
```bash
# Full export (default output: tools/data/colppy_export.db)
python tools/scripts/colppy/export_colppy_to_sqlite.py

# Custom output path
python tools/scripts/colppy/export_colppy_to_sqlite.py --output tools/data/colppy_export.db

# Timeframe-only refresh (merge first payments for given month)
python tools/scripts/colppy/export_colppy_to_sqlite.py --year 2026 --month 1

# Dry-run: count rows only, no write
python tools/scripts/colppy/export_colppy_to_sqlite.py --dry-run
```

### Tables Exported

| Table | Rows | Purpose |
|-------|------|---------|
| plan | ~635 | Plans |
| facturacion | ~28k | Colppy facturacion (Colppy internal billing records) |
| pago | ~33k | Payments (first + recurring) |
| payment_detail | ~5k | CBU payment details |
| empresa | ~68k | Companies |
| **Total** | **~135k** | |

### Size & Time

| Metric | Typical |
|--------|---------|
| **SQLite file** | ~33 MB |
| **Export time** | ~30 s |
| **Output** | `tools/data/colppy_export.db` |

Run when staging MySQL is available; use the resulting SQLite for offline reconciliation when staging is down.

---

## 9. Related Documentation

- [RECONCILE_REPORT_GROUPS.md](./RECONCILE_REPORT_GROUPS.md) — 4-group structure, column definitions, data sources
- [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md) — deal–company associations, facturacion as master
- [HUBSPOT_SCRIPTS_DOCUMENTATION.md](./HUBSPOT_SCRIPTS_DOCUMENTATION.md) — build script, reconcile_closedwon_facturacion
- [MRR_DASHBOARD_DEFINITIONS.md](./MRR_DASHBOARD_DEFINITIONS.md) — billing as master for MRR
- [COLPPY_MYSQL_SCHEMA.md](./COLPPY_MYSQL_SCHEMA.md) — Colppy MySQL schema
