---
name: facturacion-csv-colppy
description: Reconcile monthly billing cartera (facturacion CSV) vs Colppy billing. Uses bundled colppy_facturacion_snapshot.json + monthly facturacion_YYYY_MM.csv files. Use when the user asks to reconcile facturacion, billing CSV vs Colppy, or compare billing sources.
---

# Facturación CSV vs Colppy Billing Reconciliation

Reconcile monthly billing cartera with Colppy's active billing. Works without VPN/MySQL by using pre-exported snapshots. **Monthly files are already saved in `docs/`** — no need for user to attach a CSV.

## Data Sources

| Source | Location | How to Access |
| --- | --- | --- |
| **Colppy billing** | `docs/colppy_facturacion_snapshot.json` | Read file from plugin |
| **Monthly cartera CSV** | `docs/facturacion_YYYY_MM.csv` | Read file from plugin (e.g. `facturacion_2026_02.csv`) |
| **Monthly cartera JSON** | `docs/cartera_MMMYYYY_snapshot.json` | Richer snapshot with metadata |

### Available Monthly Files

| Month | CSV | Snapshot JSON | Rows | Total $ Cartera |
| --- | --- | --- | --- | --- |
| Jan 2026 | `facturacion_2026_01.csv` | `cartera_jan2026_snapshot.json` | 2,634 | $622,380,777 |
| Feb 2026 | `facturacion_2026_02.csv` | `cartera_feb2026_snapshot.json` | 2,659 | $624,626,951 |

### How to Add a New Month

1. Open the "Cartera Clientes [Month] [Year]" Google Sheet
2. Navigate to the "Cartera [Month] [Year]" tab
3. Get GID from URL: `...edit?gid={GID}`
4. Download: `curl -sL "https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=csv&gid={GID}"`
5. **Inspect column positions** — the sheet layout shifts between months. Always check header indices before mapping.
6. Map to standard format (see column guide below) and save as `facturacion_YYYY_MM.csv`

## facturacion.csv Format

Semicolon-separated. Header: `Email;Customer Cuit;Plan;Id Plan;Amount;Product CUIT;Id Empresa`

| Field | Feb 2026 col | Jan 2026 col | Notes |
| --- | --- | --- | --- |
| Id Empresa | [1] ID | [1] ID | Must be numeric |
| Email | [2] Email | [2] Email | |
| Customer Cuit (Billing) | [5] `hacer el cruce...` | [4] `CUIT "Real" Extraido de Diciembre` | Billing CUIT |
| Product CUIT | [6] `CUIT BD` | [5] `CUIT` | Account CUIT |
| Plan | [7] Plan | [6] Plan | |
| Id Plan | [8] N° Plan | [7] N° Plan | |
| Amount | [22] `$ Cartera` | [19] `$ Cartera` | Net after discount |

**Always match by column name (`$ Cartera`, `CUIT BD`, etc.), not by index — indices shift between months.**

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
