---
name: generate-libro-iva
description: Generate AFIP Libro IVA for a period
---

Generate the Libro IVA (VAT ledger) for a specific period using the ARCA MCP.

## Steps

1. Use `generate_libro_iva` MCP tool with the target period (YYYY-MM format)
2. The tool generates a ZIP file containing the Libro IVA in AFIP-required format
3. Review the output for completeness — check that all comprobantes are included
4. If discrepancies, cross-reference with `get_comprobantes` for the same period
