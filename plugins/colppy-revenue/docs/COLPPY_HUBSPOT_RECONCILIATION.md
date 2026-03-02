# Colppy Reconciliation in Claude AI

Reconcile Colppy data in Claude AI without VPN/MySQL. Three workflows:

1. **First payments vs HubSpot deals** — by id_empresa (4-group structure, includes WRONG_STAGE)
2. **facturacion.csv vs Colppy billing** — user attaches CSV
3. **Colppy DB facturacion ↔ HubSpot primary company CUIT** — match billing CUIT for correct label associations

## Data Flow

```
colppy_export.db (local SQLite)     →  colppy_first_payments_snapshot.json  →  Plugin (bundled)
facturacion_hubspot.db                      colppy_facturacion_snapshot.json
        |                                   colppy_cuit_snapshot.json
        |                                   colppy_hubspot_reconciliation_snapshot.json
        ↑
  export_colppy_to_sqlite.py (run when on VPN)
  build_facturacion_hubspot_mapping.py --refresh-deals-only --fetch-wrong-stage
  export_reconciliation_snapshot.py
  export_colppy_cuit_snapshot.py
  export_reconciliation_db_snapshot.py
```

## Refresh Snapshot (Before Publishing Plugin)

1. **Export Colppy to SQLite** (requires VPN + Colppy MySQL):
   ```bash
   python tools/scripts/colppy/export_colppy_to_sqlite.py
   ```

2. **HubSpot refresh** (for WRONG_STAGE / Cerrado Churn detection):
   ```bash
   python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year YYYY --month M --fetch-wrong-stage
   ```
   Run for each month you need, or run in background.

3. **Export reconciliation snapshots**:
   ```bash
   python tools/scripts/colppy/export_reconciliation_snapshot.py --months 62
   python tools/scripts/colppy/export_reconciliation_db_snapshot.py --months 14
   ```

4. **Publish plugin**:
   ```bash
   cd plugins/colppy-revenue && ./publish.sh
   ```

5. Upload `tools/outputs/colppy-revenue-plugin-full.zip` to Claude Cowork.

**Full refresh** (HubSpot all months + export + publish, ~35–50 min):
```bash
./tools/scripts/run_full_refresh_and_publish.sh
# Log: /tmp/full_refresh_publish.log
```

## First Payments vs HubSpot (4-Group Structure)

| Group | Meaning |
|-------|---------|
| **1. Match same month** | fechaPago ≠ close_date (same month, wrong day). Action: Set HubSpot close_date = Colppy fechaPago. |
| **2. Match different month** | HubSpot deal exists but close_date in another month. Action: Set HubSpot close_date = Colppy fechaPago. |
| **3. Wrong Stage** | COLPPY_NOT_ACTIVE (activa≠0), WRONG_STAGE (deal e.g. Cerrado Churn), NO_HUBSPOT_DEAL. Each row includes **Expected stage** and **Explanation** for the recommended action. |
| **4. HubSpot only** | Closed-won this month; Colppy first payment in different month or absent. |

**Match by id_empresa regardless of stage** — deals in Cerrado Churn appear in Group 3 (WRONG_STAGE).

## facturacion.csv vs Colppy Billing

| Category | Meaning |
|----------|---------|
| **In both** | id_empresa in CSV and Colppy — compare plan, amount, CUITs |
| **In CSV only** | id_empresa in CSV but not in Colppy (likely churned) |
| **In Colppy only** | id_empresa in Colppy but not in CSV (CSV may be filtered) |

**User must attach facturacion.csv** to the conversation. Command: `/facturacion-csv-colppy`

## Colppy DB CUIT ↔ HubSpot Primary Company

**Purpose:** Reconcile HubSpot deal primary company (type 5) CUIT with Colppy DB CUIT (who we invoice). Use to ensure correct label associations in HubSpot for billing.

**Source:** Colppy DB (facturacion.CUIT / empresa.CUIT) — alternative to facturacion.csv.

**Script:** `reconcile_cuit_hubspot_colppy_db.py` (run locally; outputs `cuit_reconcile_colppy_db_YYYYMM.md`)

**Status categories:** MATCH, MISMATCH, NO_PRIMARY, NO_COLPPY_CUIT, NO_HUBSPOT_CUIT.

**Reconciling associations:** For NO_PRIMARY — add primary company with Colppy CUIT. For MISMATCH — change primary to company with Colppy CUIT. See `tools/docs/COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md`.

---

## Chatbot Output Instructions

**When presenting reconciliation results in the chatbot**, always:

1. **Display in chat** — Do not only reference .md files. Show summary tables and deal lists directly.
2. **Output MUST be identical every time** — NEVER abbreviate, summarize, or say "same as Group X". Show the full markdown table for **each** of the 4 groups (Group 1, Group 2, Group 3, Group 4) with all rows and all columns. Each group has its own table; display every group in full.
3. **All deals with clickable links** — For every deal mentioned, generate `[Deal Name](https://app.hubspot.com/contacts/19877595/deal/DEAL_ID)`.
4. **Required outputs:**
   - Colppy ↔ HubSpot: 4-group summary + full table for Group 1 + full table for Group 2 + full table for Group 3 (with Expected stage, Explanation) + full table for Group 4
   - CUIT reconciliation: MATCH/MISMATCH/NO_PRIMARY summary + deal lists with links

**Output files** (written to `tools/outputs/`):
- `reconcile_YYYYMM_db.md` — Colppy first payments ↔ HubSpot
- `cuit_reconcile_colppy_db_YYYYMM.md` — HubSpot primary CUIT vs Colppy DB CUIT
- `hubspot_facturacion_reconcile_YYYYMM.md` — HubSpot vs billing facturacion.csv

---

## Reference

- Full reconciliation doc: `tools/docs/FACTURACION_COLPPY_RECONCILIATION.md` (in main repo)
- Colppy DB CUIT reconciliation: `tools/docs/COLPPY_DB_CUIT_HUBSPOT_RECONCILIATION.md`
- Group definitions: `docs/RECONCILE_REPORT_GROUPS.md` (bundled in plugin)
