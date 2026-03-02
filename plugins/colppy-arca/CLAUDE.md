# Colppy ARCA — Instructions

## Tool Usage Hierarchy

### Use commands for common workflows

| Task | Use command |
|------|------------|
| Generate Libro IVA for a period | `/generate-libro-iva` |
| Compare ARCA vs Colppy invoices | `/reconcile-arca-colppy` |
| Look up company data by CUIT | `/enrich-cuit` |

### ARCA MCP tools are already the right abstraction

Unlike other plugins, the ARCA MCP tools (`get_comprobantes`, `reconcile_arca_vs_colppy`, etc.) are purpose-built and can be used directly. They handle:

- WSAA X.509 authentication automatically
- Pagination for large result sets
- CUIT formatting and validation

### Tool grouping by domain

| Domain | Tools | When to use |
|--------|-------|-------------|
| **ARCA tax** | `get_comprobantes`, `get_retenciones`, `get_notificaciones`, `generate_libro_iva` | Fetching tax data from ARCA/AFIP |
| **Colppy** | `get_colppy_empresas`, `get_colppy_comprobantes` | Fetching invoice data from Colppy |
| **Reconciliation** | `reconcile_arca_vs_colppy`, `reconcile_retenciones_vs_comprobantes`, `search_invoices` | Cross-referencing between systems |
| **CUIT enrichment** | `enrich_cuit`, `search_company_by_name` | Company lookup and data enrichment |
| **Banking** | `get_bank_transactions` | Banco Galicia statement extraction |

### Do NOT

- **Do NOT** call ARCA/AFIP APIs directly via HTTP — always use the MCP tools which handle WSAA auth
- **Do NOT** manually parse XML responses from AFIP — the tools return structured JSON
- **Do NOT** use `get_bank_transactions` without confirming with the user — it launches a browser automation session on Banco Galicia

## CUIT Format

Always use CUITs in their canonical format: `XX-XXXXXXXX-X` (with hyphens). The MCP tools accept both formats but output with hyphens.

## Terminology

- **Comprobantes emitidos** = invoices issued (sales)
- **Comprobantes recibidos** = invoices received (purchases)
- **Retenciones** = tax withholdings
- **Libro IVA** = VAT ledger (required monthly AFIP filing)
- **DFE** = Domicilio Fiscal Electrónico (electronic tax notifications)

See the `arca-context` skill for the full glossary.
