---
name: reconcile-arca-colppy
description: Reconcile ARCA invoices against Colppy records
---

Run a reconciliation between ARCA (tax authority) and Colppy (accounting system) for a given period.

## Steps

1. Use `reconcile_arca_vs_colppy` MCP tool with:
   - `period`: target month (YYYY-MM)
   - `tipo`: emitidos (issued) or recibidos (received)
2. Review the discrepancy report:
   - **In ARCA but not Colppy**: invoices issued/received that aren't recorded in the system
   - **In Colppy but not ARCA**: records in Colppy that don't appear in ARCA (possible sync issues)
   - **Amount mismatches**: same invoice with different totals
3. For deeper investigation, use `search_invoices` with natural language queries
4. For retenciones reconciliation, use `reconcile_retenciones_vs_comprobantes`
