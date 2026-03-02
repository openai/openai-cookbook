---
name: icp-classification
description: Colppy's ICP (Ideal Customer Profile) classification system. Defines how to classify deals as ICP Operador (accountant billing) vs ICP PYME (SMB billing) based on the PRIMARY company type. Critical for all funnel, billing, and revenue analysis. Trigger when discussing ICP, billing, accountant channel, deal classification, or company types.
---

# ICP Classification — Colppy

Defines how Colppy classifies deals for billing and revenue analysis. This is the source of truth for all ICP-related questions.

## Core Rule

**ICP Operador (billing)**: Determined ONLY by the PRIMARY company type (association typeId 5) of the deal.

```
ACCOUNTANT_COMPANY_TYPES = ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']
```

- If the PRIMARY company `type` is in `ACCOUNTANT_COMPANY_TYPES` → **ICP Operador** (we bill the accountant)
- Any other type → **ICP PYME** (we bill the SMB)

---

## What Defines ICP Operador

| Check | Source | Result |
|-------|--------|--------|
| Primary company `type` = `Cuenta Contador` | Deal → Company association typeId 5 → `type` field | ICP Operador |
| Primary company `type` = `Cuenta Contador y Reseller` | Deal → Company association typeId 5 → `type` field | ICP Operador |
| Primary company `type` = `Contador Robado` | Deal → Company association typeId 5 → `type` field | ICP Operador |
| Any other `type` value | Deal → Company association typeId 5 → `type` field | ICP PYME |
| No primary company | Missing association typeId 5 | NOT CLASSIFIABLE — data quality issue |

---

## What Does NOT Define ICP Operador

| Field | Why NOT used |
|-------|-------------|
| **Plan name** (`nombre_del_plan`) | A referred SMB can have plan "ICP Contador" but we still bill the SMB, not the accountant |
| **Association type 8** (Estudio Contable) | Indicates accountant involvement/referral channel, NOT who we bill |
| **`tipo_icp_contador`** field | Used for NPS/enrichment profiling only (Hibrido, Operador, Asesor). NOT for billing classification |

---

## Company Type Values

| Value | Description | ICP Classification |
|-------|-------------|-------------------|
| **Cuenta Contador** | Accounting firm / accountant account | ICP Operador |
| **Cuenta Contador y Reseller** | Accountant who also resells | ICP Operador |
| **Contador Robado** | Accountant discovered via SMB client | ICP Operador |
| **Cuenta Pyme** | Standard SMB | ICP PYME |
| Alianza, Integracion, Reseller, etc. | Partnerships, others | NOT ICP Operador |

---

## Deal-Company Associations

| TypeId | Label | Usage |
|--------|-------|-------|
| **5** | PRIMARY | Primary company of deal. ONLY this defines ICP Operador vs PYME (via `type` field) |
| **8** | Estudio Contable / Asesor / Consultor Externo | Accountant channel / referral. Does NOT define billing |
| 341 | Default | Standard association. Not used for ICP classification |

---

## Key Assumptions in Scripts

1. **Primary company is source of truth for billing** — "who we bill" = type of the primary company (association 5)
2. **Plan name does NOT define ICP** — Only company `type` matters
3. **Scripts use `primary_company_type`** when available on the deal, falling back to API lookup of the primary company
4. **Deals without primary company cannot be classified** — Reported as data quality issues
5. **Association type 8 ≠ ICP Operador** — Type 8 = accountant referral channel, not billing
6. **The constant `ACCOUNTANT_COMPANY_TYPES` is the single source** used across all scripts

---

## Billing Ground Truth

The file `tools/outputs/facturacion.csv` contains actual billing data (~2,635 rows) and serves as ground truth for ICP validation.

**Key signal**: When **Customer CUIT ≠ Product CUIT** in the billing file, the accountant is paying → ICP Operador in reality, regardless of what HubSpot says.

- **IdEmpresa** column links to HubSpot deals via `id_empresa`
- ~20% of billing rows show CUIT mismatches (accountant billing)
- ~240 of those are on generic plans (not labeled as accountant plans)

**Always cross-reference billing data when auditing ICP consistency.** See the `billing-reconciliation` skill for the full methodology.

---

## Related Skills

- **billing-reconciliation** — Cross-reference HubSpot ICP with actual billing data
- **hubspot-configuration** — Full HubSpot field mappings and associations
- **funnel-analysis** — How ICP classification feeds into funnel metrics
