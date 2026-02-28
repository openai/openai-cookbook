# Billing & Reconciliation — Documentation Index

**Purpose:** Entry point for AI context and developers working on Colppy billing, HubSpot–Colppy reconciliation, and facturación data flows.

**Last Updated:** 2026-02-12

---

## Terminology (Standard)

**Use consistent terms.** See [DATA_SOURCES_TERMINOLOGY.md](./DATA_SOURCES_TERMINOLOGY.md) for full definitions.

| Term | Meaning |
|------|---------|
| **Billing** | The billing system; produces `facturacion.csv` (manual export for CRM mapping). |
| **HubSpot** | CRM: deals and companies. One product = one deal, billed to primary company. |
| **Colppy** | Colppy MySQL DB where payments happen; has its own `facturacion` table (Colppy facturacion). |
| **Service holder CUIT** | Company that uses the product (empresa.CUIT; billing product_cuit). HubSpot primary company must match this. |
| **Invoice recipient CUIT** | Entity we send the invoice to (Colppy facturacion.CUIT; billing customer_cuit). May differ from service holder in channel billing. |

In `facturacion_hubspot.db`, the `facturacion` table comes from **billing** (facturacion.csv), not from Colppy.

---

## Quick Reference

| Topic | Document | Key Scripts |
|-------|----------|-------------|
| **Terminology (Billing, HubSpot, Colppy)** | [DATA_SOURCES_TERMINOLOGY.md](./DATA_SOURCES_TERMINOLOGY.md) | — |
| **Billing ↔ Colppy reconciliation** | [FACTURACION_COLPPY_RECONCILIATION.md](./FACTURACION_COLPPY_RECONCILIATION.md) | `reconcile_facturacion_colppy.py`, `reconcile_colppy_hubspot_db_only.py`, `reconcile_with_recovery_check.py`, `export_reconciliation_db_snapshot.py` |
| **4-group report structure** | [RECONCILE_REPORT_GROUPS.md](./RECONCILE_REPORT_GROUPS.md) | — |
| **HubSpot ↔ Billing (deals)** | [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md) | `reconcile_hubspot_deals_facturacion.py` |
| **HubSpot ↔ Colppy DB CUIT** | [COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md](./COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md) | `reconcile_cuit_hubspot_colppy_db.py` |
| **Fix Colppy id_empresa on deals** | [DATA_SOURCES_TERMINOLOGY.md](./DATA_SOURCES_TERMINOLOGY.md) §4.1 | `fix_colppy_id_empresa_on_deals.py` |
| **HubSpot mapping** | [HUBSPOT_SCRIPTS_DOCUMENTATION.md](./HUBSPOT_SCRIPTS_DOCUMENTATION.md) | `build_facturacion_hubspot_mapping.py` |
| **Colppy MySQL schema** | [COLPPY_MYSQL_SCHEMA.md](./COLPPY_MYSQL_SCHEMA.md) | — |
| **colppy_export.db refresh strategy** | [COLPPY_EXPORT_REFRESH_STRATEGY.md](./COLPPY_EXPORT_REFRESH_STRATEGY.md) | Transactional vs snapshot; incremental pago |
| **MRR definitions** | [MRR_DASHBOARD_DEFINITIONS.md](./MRR_DASHBOARD_DEFINITIONS.md) | — |
| **Reconciliation MCP** | [tools/scripts/reconciliation/README.md](../scripts/reconciliation/README.md) | `mcp_reconciliation_server.py` — MCP tools for refresh + reconcile |

---

## Data Flow Overview

```
Billing (facturacion.csv) ──┐
                            ├──► facturacion_hubspot.db ──► Reconciliation
HubSpot API (deals) ────────┤         (SQLite)
                            │
Colppy MySQL (live) ────────┘
```

- **Billing** = `facturacion.csv` from the billing process; manual export for CRM mapping; may have custom amounts.
- **HubSpot** = deals and companies from HubSpot API.
- **Colppy MySQL** = Colppy product DB; source of truth for payments (pago, facturacion, empresa, plan). Colppy has its own `facturacion` table — Colppy facturacion, not billing.
- **facturacion_hubspot.db** = SQLite built from billing CSV + HubSpot; `facturacion` table = billing data.

---

## Monthly Workflow (Timeframe-Specific)

**Before reconciliation:** Always refresh **both** HubSpot and Colppy database. Do not run reconciliation with stale data.

```bash
# 1. Refresh Colppy first payments for a month (requires Colppy MySQL access)
python tools/scripts/colppy/export_colppy_to_sqlite.py --year 2026 --month 2

# 2. Refresh HubSpot closed-won deals for that month (logs evolution)
#    Use --fetch-wrong-stage to populate deals_any_stage (WRONG_STAGE / Cerrado Churn detection)
python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year 2026 --month 2 --fetch-wrong-stage

# 2b. Refresh deal–company associations (required before CUIT reconciliation)
python tools/scripts/hubspot/populate_deal_associations.py --batch

# 3. Reconcile Colppy vs HubSpot (DB-only, 4-group report)
python tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py --year 2026 --month 2 --output tools/outputs/reconcile_202602_db.md

# 3a. Post report to Slack DM (optional)
# Requires .env: SLACK_BOT_TOKEN (xoxb-...), SLACK_DM_USER_ID (e.g. U01234567)
# Get Slack user ID: Profile > Copy member ID. See plugins/colppy-ceo-assistant/docs/SLACKUSER_MENTION_MAP_COMPLETE_GUIDE.md
python tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py --year 2026 --month 2 --post-slack-dm
# Or override user: --post-slack-dm --slack-user-id U01234567

# 3b. With recovery check (flags potential_recovered, confirms with Colppy recurring payments)
python tools/scripts/colppy/reconcile_with_recovery_check.py --year 2026 --month 2

# 4. HubSpot ↔ Billing: verify deal id_empresa + primary company CUIT = billing customer_cuit
python tools/scripts/hubspot/reconcile_hubspot_deals_facturacion.py --year 2026 --month 2 --output tools/outputs/hubspot_facturacion_reconcile_202602.md

# 4b. HubSpot ↔ Colppy DB CUIT: same as 4 but using Colppy DB as source (alternative to facturacion.csv)
python tools/scripts/colppy/reconcile_cuit_hubspot_colppy_db.py --year 2026 --month 2 --output tools/outputs/cuit_reconcile_colppy_db_202602.md

# 5. Fix Colppy id_empresa on deals (when HubSpot has CRM id instead of Colppy id)
python tools/scripts/hubspot/fix_colppy_id_empresa_on_deals.py --dry-run
python tools/scripts/hubspot/fix_colppy_id_empresa_on_deals.py --apply
```

**Steps 1, 2, and 2b are required** before reconciliation. Step 2b (`populate_deal_associations --batch`) is required before CUIT reconciliation (steps 4, 4b) and fix_deal_associations. If Colppy MySQL is unreachable (timeout), reconciliation will use existing `colppy_export.db` — results may be stale.

### MCP (Natural Language)

Use the **Reconciliation MCP** for natural-language interaction. Add to `~/.cursor/mcp.json`:

```json
"reconciliation": {
  "command": "python",
  "args": ["tools/scripts/reconciliation/mcp_reconciliation_server.py"],
  "cwd": "/path/to/openai-cookbook"
}
```

Then ask e.g. "Refresh Colppy and HubSpot for Feb 2026, then run reconciliation" or "Run reconciliation for 2026-02". See [tools/scripts/reconciliation/README.md](../scripts/reconciliation/README.md).

## Full Refresh (Jan 2025 → Current)

Run all months + populate deal associations (fixed batch API) + export snapshot + publish plugin:
```bash
./tools/scripts/run_full_refresh_and_publish.sh
# 1. HubSpot deals refresh (all months)
# 2. populate_deal_associations --batch (null-safe, fixed)
# 3. Export snapshot, publish plugin
# Log: /tmp/full_refresh_publish.log (~35–50 min)
```

---

## Stale Data Cleanup (No Outdated Data)

All refresh operations remove outdated data to avoid discrepancies:

| Operation | Cleanup behavior |
|-----------|------------------|
| Full build | `DELETE FROM deals` before populate; run `--refresh-deals-only` for each month needed |
| refresh-deals-only | Deletes deals HubSpot no longer returns for that month |
| export_colppy (timeframe) | Deletes existing rows for that month before insert |
| facturacion (billing table) | Full replace on every build |
| companies | Full replace (DROP + CREATE) on every build |

---

## Logging & History

| Log | Table | Script |
|-----|-------|--------|
| Reconciliation runs | `reconciliation_logs` | `show_reconciliation_history.py` |
| HubSpot refresh evolution | `hubspot_refresh_logs` | `show_hubspot_refresh_history.py` |
| Deal associations refresh | `hubspot_deal_associations_refresh_logs` (in facturacion_hubspot.db) | `populate_deal_associations.py` |
| Colppy export refresh | `colppy_export_refresh_logs` (in colppy_export.db) | `export_colppy_to_sqlite.py` |

All use **Argentina timezone** for timestamps.

---

## Chatbot Output Instructions

**When presenting reconciliation results in the chatbot**, always include:

### Required Outputs (display in chat, not only as .md files)

| Output | Format | Content |
|--------|--------|---------|
| **Colppy ↔ HubSpot reconciliation** | Summary table + full deal list | 4-group structure; all deals with clickable HubSpot URLs |
| **CUIT reconciliation (Colppy DB)** | Summary table + deal lists | MATCH, MISMATCH, NO_PRIMARY, NO_COLPPY_CUIT, NO_HUBSPOT_CUIT |
| **Deal links** | Clickable markdown | `[Deal Name](https://app.hubspot.com/contacts/19877595/deal/DEAL_ID)` for every deal mentioned |

### Output Files (written to `tools/outputs/`)

| File | Script | Content |
|------|--------|---------|
| `reconcile_YYYYMM_db.md` | `reconcile_colppy_hubspot_db_only.py` | Colppy first payments ↔ HubSpot (4 groups) |
| `cuit_reconcile_colppy_db_YYYYMM.md` | `reconcile_cuit_hubspot_colppy_db.py` | HubSpot primary company CUIT vs Colppy DB CUIT |
| `hubspot_facturacion_reconcile_YYYYMM.md` | `reconcile_hubspot_deals_facturacion.py` | HubSpot vs billing facturacion.csv |

### Rule: Reconciliation Output Must Be Identical Every Time

**When presenting Colppy ↔ HubSpot reconciliation results, the output MUST always be the same full detailed format.** NEVER abbreviate, summarize, or say "same as Group X". Display:

1. Summary table
2. **Full markdown table for Group 1** — all rows, all columns
3. **Full markdown table for Group 2** — all rows, all columns (do NOT say "same as Group 1")
4. **Full markdown table for Group 3** — all rows, all columns (including Expected stage, Explanation)
5. **Full markdown table for Group 4** — all rows, all columns

Each group has its own table; show every group in full. Display the complete output directly in the chat, not only in the .md file.

### Rule: Always Show Deals in Chat

Per Object Reference rules: **generate clickable HubSpot URLs** for every deal mentioned. Present all deals in the chatbot response, not only in the .md file. Example: list all 40 deals with links when reporting Feb 2026.

---

## Colppy DB CUIT Reconciliation (Alternative to facturacion.csv)

**Purpose:** Reconcile HubSpot deal primary company CUIT with Colppy DB CUIT (who we invoice). Uses Colppy DB as source of truth instead of billing facturacion.csv.

**Logic:** For each deal, the PRIMARY company (association type 5) CUIT must match Colppy DB CUIT (from facturacion.CUIT / empresa.CUIT).

**Script:** `reconcile_cuit_hubspot_colppy_db.py`

**Status categories:**

| Status | Meaning |
|-------|---------|
| MATCH | HubSpot primary company CUIT = Colppy DB CUIT |
| MISMATCH | HubSpot primary CUIT ≠ Colppy DB CUIT — fix primary association |
| NO_PRIMARY | Deal has no type 5 association — add primary company |
| NO_COLPPY_CUIT | id_empresa not in Colppy DB |
| NO_HUBSPOT_CUIT | Primary company exists but no CUIT in companies table |

**Prerequisite:** Run `populate_deal_associations.py` to ensure deal_associations is current.

**See:** [COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md](./COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md)

---

## Reconciling Label Associations in HubSpot

**Purpose:** Ensure deal–company associations have correct labels (PRIMARY = type 5, Estudio Contable = type 8, etc.) so billing CUIT aligns with the primary company.

**Workflow:**

1. **Run CUIT reconciliation** (`reconcile_cuit_hubspot_colppy_db.py`) to identify MISMATCH and NO_PRIMARY.
2. **For NO_PRIMARY:** Add primary company association (type 5) with the company whose CUIT matches Colppy DB. Use `fix_deal_associations.py` (with `--colppy-db --year YYYY --month M` for deals not in billing) or HubSpot UI.
3. **For MISMATCH:** Use `fix_deal_associations.py --group 5 --colppy-db --year YYYY --month M` to swap primary to the company with Colppy DB CUIT. When multiple companies share the same CUIT, disambiguates by id_empresa in name, then razon_social/empresa_nombre.
4. **For non-primary labels:** Use `fix_deal_associations.py --fix-label` to correct type 8 (Estudio Contable) vs type 11 (Múltiples Negocios). See [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md) §0.1.

**Scripts:** `fix_deal_associations.py`, `populate_deal_associations.py`, `merge_duplicate_companies.py`

---

## Related Documentation

- [RECONCILE_REPORT_GROUPS.md](./RECONCILE_REPORT_GROUPS.md) — 4-group structure, WRONG_STAGE, deals_any_stage
- [COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md](./COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md) — Colppy DB facturacion ↔ HubSpot primary company CUIT
- [FACTURACION_COLPPY_RECONCILIATION.md](./FACTURACION_COLPPY_RECONCILIATION.md) — full reconciliation design
- [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md) — deal–company associations
- [COLPPY_PAYMENT_TO_CRM_FLOW.md](./COLPPY_PAYMENT_TO_CRM_FLOW.md) — payment → CRM flow
- [FIRST_PAYMENT_ENTRY_POINTS.md](./FIRST_PAYMENT_ENTRY_POINTS.md) — first payment definitions
