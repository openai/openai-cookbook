---
name: enrich-cuit
description: Look up and enrich a CUIT with company data from AFIP and RNS
---

Enrich a CUIT (Argentine tax ID) with company information from multiple sources.

## Steps

1. Use `enrich_cuit` MCP tool with the target CUIT (format: XX-XXXXXXXX-X or 11 digits)
2. The tool combines:
   - **AFIP Live API**: current IVA condition, activities, registered address
   - **RNS Open Data**: incorporation date (`fecha_contrato_social`), activity description
3. Review the enriched data for lead scoring signals:
   - Business age (from `fecha_contrato_social`)
   - IVA condition (Responsable Inscripto vs Monotributo)
   - Activity type (industry classification)
4. For name-to-CUIT lookup, use `search_company_by_name` instead
