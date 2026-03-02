---
name: facturacion-csv-colppy
description: Reconcile facturacion.csv (manual billing export) vs Colppy billing. Uses bundled colppy_facturacion_snapshot.json + user-attached facturacion.csv. Use when the user asks to reconcile facturacion, billing CSV vs Colppy, or compare billing sources.
---

# Facturación CSV vs Colppy Billing Reconciliation

Reconcile facturacion.csv (manual billing export) with Colppy's active billing. Works in Claude AI without VPN/MySQL by using a pre-exported Colppy snapshot. **User must attach facturacion.csv** to the conversation.

## Data Sources

| Source | Location | How to Access |
|--------|----------|---------------|
| **Colppy billing** | `docs/colppy_facturacion_snapshot.json` | Read file from plugin |
| **facturacion.csv** | User attachment | User attaches/pastes the CSV |

## facturacion.csv Format

Semicolon-separated. Header contains "Email" and "Customer Cuit". Columns:
- Col 0: Email
- Col 1: Customer Cuit
- Col 2: Plan
- Col 3: Id Plan
- Col 4: Amount
- Col 5: Product CUIT
- Col 6: Id Empresa

Parse: split by `;`, skip header row, use col 6 as id_empresa (must be numeric).

## Colppy Snapshot Structure

`colppy_facturacion_snapshot.json`:
```json
{
  "metadata": { "exported_at": "...", "description": "Active billing (fechaBaja IS NULL)" },
  "facturacion": [
    { "id_empresa": "102", "email": "...", "customer_cuit": "30613918716", "product_cuit": "...", "plan": "Platinum", "id_plan": "641", "amount": "177265", "razonSocial": "..." }
  ]
}
```

## Reconciliation Workflow

### 1. Load facturacion.csv

From user attachment: parse CSV (semicolon), extract id_empresa, email, customer_cuit, product_cuit, plan, id_plan, amount. Normalize CUITs to 11 digits (strip hyphens, spaces). Build `csv_by_id = {id_empresa: row}`.

### 2. Load Colppy Snapshot

Read `docs/colppy_facturacion_snapshot.json` → `facturacion` array. Build `colppy_by_id = {id_empresa: row}`.

### 3. Reconcile by id_empresa

| Category | Meaning |
|----------|---------|
| **In both** | id_empresa in CSV and Colppy → compare plan, amount, customer_cuit, product_cuit |
| **In CSV only** | id_empresa in CSV but not in Colppy (likely churned or fechaBaja set) |
| **In Colppy only** | id_empresa in Colppy but not in CSV (CSV may be filtered) |

### 4. For "In both" — Flag Differences

Compare: plan, amount, customer_cuit, product_cuit. Note: amount differences are common (custom pricing in CSV). Plan/cuit differences need investigation.

### 5. Output Format

```
## Facturación Reconciliation: CSV vs Colppy

| Category | Count |
|----------|-------|
| In both | n |
| In CSV only | n |
| In Colppy only | n |
| Differences (in both) | n |

### In CSV only (sample)
| id_empresa | email | plan | amount |

### In Colppy only (sample)
| id_empresa | email | plan | amount |

### Differences (in both, sample)
| id_empresa | CSV plan | Colppy plan | CSV amount | Colppy amount |
```

## CUIT Normalization

Both sources: strip non-digits, require 11 digits. Treat `33-70889931-9` and `33708899319` as same.

## Currency Formatting

Use `$` prefix, comma as decimal separator (Argentina). Example: $18.150
