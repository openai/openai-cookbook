---
name: reconciliation-patterns
description: ARCA vs Colppy reconciliation patterns and workflows
---

# ARCA ↔ Colppy Reconciliation

## Reconciliation Types

### 1. Emitidos (Issued Invoices)
- ARCA emitidos ↔ Colppy facturas de venta
- Match by: CUIT del receptor, fecha, importe total, tipo de comprobante
- Common discrepancies: missing in Colppy (not synced), amount differences (rounding)

### 2. Recibidos (Received Invoices)
- ARCA recibidos ↔ Colppy facturas de compra
- Match by: CUIT del emisor, fecha, importe total
- Common discrepancies: supplier invoices not entered in Colppy

### 3. Retenciones vs Comprobantes
- Cross-reference retenciones/percepciones against related invoices
- Match by: CUIT, período, régimen
- Identifies: retenciones without matching invoice, orphaned records

## MCP Tools

- `reconcile_arca_vs_colppy` — runs emitidos/recibidos reconciliation
- `reconcile_retenciones_vs_comprobantes` — retenciones matching
- `search_invoices` — natural language search across reconciled data

## Workflow

1. Fetch ARCA comprobantes for the period (`get_comprobantes`)
2. Fetch Colppy invoices for the same period (`get_colppy_comprobantes`)
3. Run reconciliation (`reconcile_arca_vs_colppy`)
4. Review discrepancies — investigate missing or mismatched records
5. For retenciones: `get_retenciones` → `reconcile_retenciones_vs_comprobantes`
