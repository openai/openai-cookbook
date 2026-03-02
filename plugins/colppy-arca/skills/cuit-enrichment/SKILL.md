---
name: cuit-enrichment
description: CUIT lookup and enrichment patterns using AFIP live API and RNS open datasets
---

# CUIT Enrichment

## Data Sources

### AFIP Live API (via TusFacturas.app)
- Script: `tools/scripts/afip_cuit_lookup.py`
- Returns: company name, IVA condition, activities with `periodo` field, address
- Rate limits apply — use for individual lookups, not bulk

### RNS Open Data
- Script: `tools/scripts/rns_dataset_lookup.py`
- Dataset: `tools/scripts/rns_datasets/` — 3M+ records
- Returns: `fecha_contrato_social`, `actividad_descripcion`, incorporation dates
- Best for: bulk lookups, business age analysis

### Combined Enrichment
- MCP tool: `enrich_cuit` — combines both sources
- MCP tool: `search_company_by_name` — name-to-CUIT from 1.24M companies
- Pipeline: `tools/scripts/automated_cuit_enrichment.py` — CUIT → HubSpot property sync

## Business Age Signal

Business age (from CUIT/RNS `fecha_contrato_social`) is a validated lead quality signal:
- 5.1pp conversion spread between newer and older businesses
- Used in HubSpot lead scoring via `business_age_months` property

## Key Patterns

- CUIT format: XX-XXXXXXXX-X (11 digits, type-number-verifier)
- Type 20 = person, 30 = company, 33 = state entity, 34 = foreign
- Always validate CUIT format before API calls
- RNS dataset lookup is free and fast — prefer for bulk operations
