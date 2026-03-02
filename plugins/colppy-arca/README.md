# Colppy ARCA Plugin

ARCA/AFIP tax operations for Colppy — comprobantes, retenciones, libro IVA, CUIT enrichment, bank statement extraction, and invoice reconciliation.

## Skills

| Skill | Purpose |
|-------|---------|
| `arca-context` | AFIP/ARCA terminology, DFE workflow, system overview |
| `cuit-enrichment` | CUIT lookup patterns, RNS datasets, business age signal |
| `reconciliation-patterns` | ARCA vs Colppy reconciliation workflows |

## Commands

| Command | Description |
|---------|-------------|
| `/generate-libro-iva` | Generate AFIP Libro IVA for a period |
| `/reconcile-arca-colppy` | Reconcile ARCA invoices vs Colppy records |
| `/enrich-cuit` | Enrich a CUIT with company data |

## MCP Tools (arca — 14 tools)

| Tool | Domain | Description |
|------|--------|-------------|
| `get_comprobantes` | ARCA | Fetch invoices (emitidos/recibidos) |
| `get_retenciones` | ARCA | Retenciones/percepciones from Mirequa |
| `get_notificaciones` | ARCA | DFE notifications |
| `get_representados` | ARCA | List represented CUITs |
| `generate_libro_iva` | ARCA | Generate Libro IVA ZIP |
| `test_wsaa_auth` | ARCA | Test X.509 auth |
| `get_colppy_empresas` | Colppy | List companies |
| `get_colppy_comprobantes` | Colppy | Fetch invoices |
| `reconcile_arca_vs_colppy` | Recon | ARCA ↔ Colppy cross-reference |
| `reconcile_retenciones_vs_comprobantes` | Recon | Retenciones vs invoices |
| `search_invoices` | Recon | LLM-powered invoice search |
| `enrich_cuit` | CUIT | AFIP + RNS combined lookup |
| `search_company_by_name` | CUIT | Name-to-CUIT (1.24M records) |
| `get_bank_transactions` | Bank | Banco Galicia statement extraction |

## Setup

Requires the ARCA prototype backend:
- Python 3.11 at `/opt/homebrew/bin/python3.11`
- ARCA X.509 certificates configured
- Colppy API credentials in `.env`
