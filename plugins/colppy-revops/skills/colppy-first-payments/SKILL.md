---
name: colppy-first-payments
description: Query Colppy first payments (primerPago=1) by month. Use when the user asks how many first payments in a given month, first payment count, new customers by month, or Colppy billing activation by period. Uses bundled JSON snapshot (no VPN/MySQL required).
---

# Colppy First Payments by Month

Query first payments (primerPago=1) from Colppy by month. Works in Claude AI without VPN/MySQL by using the pre-exported JSON snapshot.

## Data Source

| Source | Location | How to Access |
|--------|----------|---------------|
| **Colppy first payments** | `docs/colppy_first_payments_snapshot.json` | Read file from plugin |

## Snapshot Structure

```json
{
  "metadata": { "exported_at": "...", "source": "colppy_export.db", "months_included": 62 },
  "first_payments_by_month": {
    "2026-01": [ { "idPago": ..., "idEmpresa": ..., "plan_name": "...", "fechaPago": "...", "importe": ... }, ... ],
    "2026-02": [...],
    ...
  }
}
```

## How to Answer "How many first payments in [month]?"

1. Read `docs/colppy_first_payments_snapshot.json`
2. Extract `first_payments_by_month["YYYY-MM"]` for the requested month (e.g. `"2026-01"`)
3. Count: `len(first_payments_by_month["2026-01"])`
4. Report: "Colppy first payments in January 2026: **50**" (or the actual count)

## Output Format

- **Count:** "Colppy first payments in [Month] [Year]: **N**"
- **Source note:** "Source: colppy_first_payments_snapshot.json (exported from colppy_export.db)"
- **Currency:** Use `$` prefix, comma as decimal separator (Argentina)

## Snapshot Freshness

The snapshot is generated from `colppy_export.db` (local SQLite export of Colppy MySQL). To refresh:

1. Run `export_colppy_to_sqlite.py` when on VPN (connects to Colppy MySQL)
2. Run `export_reconciliation_snapshot.py` to regenerate the JSON
3. Run `./publish.sh` in the plugin directory
4. Re-upload the plugin to Claude Cowork

## Related Skills

- **colppy-hubspot-reconciliation** — Reconcile first payments vs HubSpot closed won by id_empresa
- **docs-reference** — Full doc index including COLPPY_HUBSPOT_RECONCILIATION.md
