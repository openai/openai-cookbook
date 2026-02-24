# Colppy Scripts — Reconciliation & Export

**Purpose:** Colppy data export, Colppy ↔ HubSpot reconciliation, and snapshot generation for the Claude plugin.

**Last Updated:** 2026-02-24

---

## Scripts Overview

| Script | Purpose |
|--------|---------|
| **export_colppy_to_sqlite.py** | Export Colppy MySQL → colppy_export.db (requires VPN) |
| **reconcile_colppy_hubspot_db_only.py** | Colppy ↔ HubSpot reconciliation (4-group report) |
| **export_reconciliation_db_snapshot.py** | Export reconciliation to JSON for plugin |
| **export_reconciliation_snapshot.py** | Export first payments + facturacion to JSON |
| **export_colppy_cuit_snapshot.py** | Export id_empresa → CUIT from Colppy DB (for HubSpot CUIT reconciliation) |
| **reconcile_cuit_hubspot_colppy_db.py** | HubSpot primary company CUIT vs Colppy DB CUIT (alternative to facturacion.csv) |
| **reconcile_facturacion_colppy.py** | Billing CSV vs Colppy reconciliation |
| **reconcile_with_recovery_check.py** | Recovery check for HubSpot-only deals |
| **first_payments_reconciliation.py** | First payments vs billing by CUIT |
| **show_reconciliation_history.py** | View reconciliation run history |

---

## Colppy ↔ HubSpot Reconciliation (4-Group Structure)

**Primary script:** `reconcile_colppy_hubspot_db_only.py`

**Data sources:** colppy_export.db | facturacion_hubspot.db (deals + deals_any_stage)

**Report structure:** See [RECONCILE_REPORT_GROUPS.md](../../docs/RECONCILE_REPORT_GROUPS.md)

| Group | Meaning |
|-------|---------|
| 1. Match same month | fechaPago ≠ close_date (same month, wrong day) |
| 2. Match different month | HubSpot deal exists but close_date in another month |
| 3. Wrong Stage | COLPPY_NOT_ACTIVE, WRONG_STAGE (e.g. Cerrado Churn), NO_HUBSPOT_DEAL |
| 4. HubSpot only | Closed-won this month; Colppy first payment absent or in different month |

### Usage

```bash
# 1. HubSpot refresh with --fetch-wrong-stage (populates deals_any_stage)
python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year 2026 --month 2 --fetch-wrong-stage

# 2. Run reconciliation
python tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py --year 2026 --month 2 --output tools/outputs/reconcile_202602_db.md
```

---

## Export Snapshots (for Claude Plugin)

```bash
# First payments + facturacion (from colppy_export.db)
python tools/scripts/colppy/export_reconciliation_snapshot.py --months 62

# Colppy ↔ HubSpot reconciliation (from both DBs)
python tools/scripts/colppy/export_reconciliation_db_snapshot.py --months 14
# Output: plugins/colppy-ceo-assistant/docs/colppy_hubspot_reconciliation_snapshot.json

# id_empresa → CUIT from Colppy DB (different from billing facturacion.csv)
python tools/scripts/colppy/export_colppy_cuit_snapshot.py
# Output: plugins/colppy-ceo-assistant/docs/colppy_cuit_snapshot.json
```

---

## Full Refresh (All Months + Publish)

```bash
./tools/scripts/run_full_refresh_and_publish.sh
# HubSpot refresh Jan 2025 → current, export snapshot, publish plugin
# Log: /tmp/full_refresh_publish.log (~35–50 min)
```

---

## Output Files & Chatbot Instructions

| Output | Path | Chatbot rule |
|--------|------|--------------|
| Colppy ↔ HubSpot | `tools/outputs/reconcile_YYYYMM_db.md` | Display in chat; all deals with clickable HubSpot links |
| CUIT (Colppy DB) | `tools/outputs/cuit_reconcile_colppy_db_YYYYMM.md` | Display in chat; all deals with clickable links |
| HubSpot ↔ Billing | `tools/outputs/hubspot_facturacion_reconcile_YYYYMM.md` | Display in chat; all deals with clickable links |

**Rule:** When presenting reconciliation, show summary + full deal list in the chatbot. Generate `[Deal Name](https://app.hubspot.com/contacts/19877595/deal/DEAL_ID)` for every deal.

---

## Colppy DB CUIT Reconciliation

**Script:** `reconcile_cuit_hubspot_colppy_db.py`

Reconciles HubSpot primary company (type 5) CUIT with Colppy DB CUIT (facturacion.CUIT / empresa.CUIT). Use to ensure correct label associations in HubSpot for billing. See [COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md](../../docs/COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md).

---

## Related Documentation

- [FACTURACION_COLPPY_RECONCILIATION.md](../../docs/FACTURACION_COLPPY_RECONCILIATION.md) — full reconciliation design
- [COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md](../../docs/COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md) — Colppy DB facturacion ↔ HubSpot primary CUIT
- [RECONCILE_REPORT_GROUPS.md](../../docs/RECONCILE_REPORT_GROUPS.md) — 4-group structure
- [README_BILLING_RECONCILIATION.md](../../docs/README_BILLING_RECONCILIATION.md) — billing & reconciliation index, chatbot output instructions
