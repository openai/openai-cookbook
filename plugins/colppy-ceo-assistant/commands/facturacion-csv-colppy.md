---
name: facturacion-csv-colppy
description: Reconcile facturacion.csv vs Colppy billing. User must attach facturacion.csv.
---

# /facturacion-csv-colppy

Reconcile facturacion.csv (manual billing export) with Colppy's active billing. Uses bundled Colppy snapshot + user-attached CSV.

## Usage

1. **Attach facturacion.csv** to the conversation (upload or paste content)
2. Run: `/colppy-ceo-assistant:facturacion-csv-colppy`

Or ask: "Reconcile facturacion.csv vs Colppy billing" (with the CSV attached).

## Execution

1. Parse the attached facturacion.csv (semicolon-separated, header has Email + Customer Cuit)
2. Read `docs/colppy_facturacion_snapshot.json` for Colppy billing
3. Merge by id_empresa → In both, In CSV only, In Colppy only
4. For "In both", compare plan, amount, customer_cuit, product_cuit
5. Output reconciliation table with counts and samples

## Snapshot Update

Colppy snapshot is refreshed when running `./publish.sh` (if colppy_export.db exists). To refresh: run `export_colppy_to_sqlite.py` when on VPN, then `export_reconciliation_snapshot.py`, then `./publish.sh`.
