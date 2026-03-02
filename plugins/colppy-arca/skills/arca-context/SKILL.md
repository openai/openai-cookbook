---
name: arca-context
description: ARCA/AFIP tax system context for Argentine accounting operations
---

# ARCA/AFIP Context

## System Overview

ARCA (formerly AFIP) is Argentina's tax authority. Colppy integrates with ARCA for electronic invoicing, tax reporting, and compliance.

## Key Concepts

- **CUIT**: Clave Única de Identificación Tributaria — unique tax ID for companies and individuals
- **DFE (Domicilio Fiscal Electrónico)**: Electronic fiscal address for receiving tax notifications
- **Comprobantes**: Tax documents (invoices, credit notes, debit notes) — emitidos (issued) and recibidos (received)
- **Retenciones/Percepciones**: Tax withholdings and surcharges applied by third parties
- **Libro IVA**: VAT ledger required by ARCA — monthly report of all invoices with IVA breakdown
- **Talonario/Punto de Venta**: Invoice numbering system registered with ARCA
- **Factura Electrónica**: Electronic invoicing — requires ARCA delegation and punto de venta setup
- **Condición IVA**: VAT condition (Responsable Inscripto, Monotributo, Exento, etc.)

## MCP Tools (arca server)

### ARCA/AFIP Operations
- `get_comprobantes` — fetch invoices (emitidos/recibidos) with date and CUIT filters
- `get_retenciones` — retenciones/percepciones from Mirequa service
- `get_notificaciones` — DFE notifications
- `get_representados` — list CUITs the account represents
- `generate_libro_iva` — generate AFIP Libro IVA ZIP for a period
- `test_wsaa_auth` — test X.509 certificate authentication

### Colppy Integration
- `get_colppy_empresas` — list Colppy companies
- `get_colppy_comprobantes` — fetch Colppy invoices (venta/compra)

### Reconciliation
- `reconcile_arca_vs_colppy` — cross-reference ARCA vs Colppy invoices
- `reconcile_retenciones_vs_comprobantes` — match retenciones against invoices
- `search_invoices` — LLM-powered natural language invoice search

### CUIT Enrichment
- `enrich_cuit` — AFIP live API + RNS dataset combined lookup
- `search_company_by_name` — name-to-CUIT search from 1.24M companies

### Bank
- `get_bank_transactions` — Banco Galicia transaction extraction

## Authentication

ARCA uses X.509 certificate-based authentication (WSAA). The prototype handles login via Playwright automation for DFE access. Colppy API uses two-layer auth: dev credentials (MD5) + user session (claveSesion).
