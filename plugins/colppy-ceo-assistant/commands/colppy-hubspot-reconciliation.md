---
name: colppy-hubspot-reconciliation
description: Reconcile Colppy first payments vs HubSpot deals by id_empresa for a given month (4-group structure)
---

# /colppy-hubspot-reconciliation

Reconcile Colppy first payments (primerPago=1) with HubSpot deals by `id_empresa`. Uses bundled snapshot. **4 groups:** Match same/different month, Wrong Stage (incl. Cerrado Churn), HubSpot only.

## Usage

```
/colppy-hubspot-reconciliation 2025-04
/colppy-hubspot-reconciliation 2026-02
```

## Execution

1. Read `docs/colppy_hubspot_reconciliation_snapshot.json` → extract `reports_by_month[YYYY-MM]`
2. If month not in snapshot, instruct user to run locally and republish
3. **Output in chatbot:** Summary table + 4 groups + **all deals with clickable HubSpot links** (`[Deal Name](https://app.hubspot.com/contacts/19877595/deal/DEAL_ID)`). Display in chat, not only in .md files.

## Snapshot Update

If the month is not in the snapshot or data is stale, instruct the user to run locally:
```bash
python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year YYYY --month M --fetch-wrong-stage
python tools/scripts/colppy/export_reconciliation_db_snapshot.py --year YYYY --month M
./plugins/colppy-ceo-assistant/publish.sh
```
Then re-upload the plugin.
