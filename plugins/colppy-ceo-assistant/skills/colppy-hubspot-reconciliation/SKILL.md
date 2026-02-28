---
name: colppy-hubspot-reconciliation
description: Reconcile Colppy first payments vs HubSpot deals by id_empresa. Uses bundled JSON snapshot (4-group structure). Match by id_empresa regardless of stage; WRONG_STAGE includes Cerrado Churn. Use when the user asks for first payments reconciliation, Colppy vs HubSpot match, or closed won vs billing alignment.
---

# Colppy–HubSpot First Payments Reconciliation (DB Snapshot)

Reconcile Colppy first payments (primerPago=1) with HubSpot deals by `id_empresa`. Uses a pre-exported JSON snapshot with **4 groups**. Matches by id_empresa regardless of HubSpot stage (including Cerrado Churn → WRONG_STAGE).

## Data Source

| Source | Location |
|--------|----------|
| **Reconciliation snapshot** | `docs/colppy_hubspot_reconciliation_snapshot.json` |

## Snapshot Structure

```json
{
  "metadata": {
    "exported_at": "...",
    "source": "reconcile_colppy_hubspot_db_only",
    "months_included": ["2025-04", "2025-05", ...]
  },
  "reports_by_month": {
    "2025-04": {
      "month_key": "2025-04",
      "summary": {
        "match_count": 53,
        "group1_count": 1,
        "group2_count": 4,
        "group3_count": 8,
        "group4_count": 14,
        "colppy_total": 67,
        "hubspot_total": 71
      },
      "group1": [...],
      "group2": [...],
      "group3": [...],
      "group4": [...]
    }
  }
}
```

## 4-Group Structure

| Group | Meaning |
|-------|---------|
| **1. Match but Mismatch same month** | Both in same month; fechaPago ≠ close_date (exact day differs). Action: Set HubSpot close_date = Colppy fechaPago. |
| **2. Match but Mismatch different month** | Colppy first payment this month; HubSpot deal exists but close_date in another month. Action: Set HubSpot close_date = Colppy fechaPago. |
| **3. Wrong Stage** | **COLPPY_NOT_ACTIVE:** Colppy activa ≠ 0, HubSpot closed-won. **WRONG_STAGE:** Deal exists (e.g. Cerrado Churn) but not closed-won. **NO_HUBSPOT_DEAL:** No deal in HubSpot. Each row includes **expected_stage** and **explanation** for the recommended action. |
| **4. HubSpot only** | HubSpot closed-won this month; Colppy first payment in different month or absent. Reasons: NOT_IN_COLPPY, IN_EMPRESA_NO_PAGO, PRIMER_PAGO_OTHER_MONTH, etc. |

## Row Fields (per group)

Each row in group1–4 has:
- `id_empresa`, `reason` (group3 only), `expected_stage`, `explanation` (group3 only)
- `colppy_id_plan`, `hubspot_id_plan`, `hubspot_plan_name`, `hubspot_deal_type`
- `colppy_fecha_pago`, `hubspot_close_date`, `hubspot_fecha_primer_pago`
- `activa`, `hubspot_stage`
- `colppy_medio_pago`, `colppy_amount`, `hubspot_amount`
- `hubspot_deal_url`, `hubspot_deal_name`

## Workflow

1. Read `docs/colppy_hubspot_reconciliation_snapshot.json`
2. Extract `reports_by_month[YYYY-MM]` for the requested month
3. If month not in snapshot, tell the user to run locally and republish (single-month refresh):
   ```bash
   python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year YYYY --month M --fetch-wrong-stage
   python tools/scripts/colppy/reconcile_colppy_hubspot_db_only.py --year YYYY --month M
   python tools/scripts/colppy/export_reconciliation_db_snapshot.py --year YYYY --month M
   ./plugins/colppy-ceo-assistant/publish.sh
   ```
   For full refresh of last 14 months, use `--months 14` instead of `--year/--month`.
4. **Present in chatbot:** Output MUST be identical every time. NEVER abbreviate or say "same as Group X". Display: Summary table + **full markdown table for Group 1** (all rows, all columns) + **full markdown table for Group 2** (all rows, all columns) + **full markdown table for Group 3** (all rows, all columns including expected_stage, explanation) + **full markdown table for Group 4** (all rows, all columns). All deals with clickable HubSpot links. Do not only reference .md files — display the complete output in chat.
5. **Deal links:** For every deal, generate `[Deal Name](https://app.hubspot.com/contacts/19877595/deal/DEAL_ID)`.

## Snapshot Refresh (Before Publishing)

1. **HubSpot refresh** (populates deals_any_stage for WRONG_STAGE):
   ```bash
   python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year YYYY --month M --fetch-wrong-stage
   ```
2. **Export reconciliation snapshot**:
   ```bash
   python tools/scripts/colppy/export_reconciliation_db_snapshot.py --months 14
   ```
3. **Publish plugin**:
   ```bash
   cd plugins/colppy-ceo-assistant && ./publish.sh
   ```

## Currency Formatting

- Use `$` prefix, comma as decimal separator (Argentina)
- Example: $60.621,00
