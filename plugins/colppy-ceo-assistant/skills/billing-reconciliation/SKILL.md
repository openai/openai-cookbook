---
name: billing-reconciliation
description: Cross-reference HubSpot ICP classifications against actual Colppy billing data (facturacion.csv). Use this whenever checking ICP consistency, validating deal classifications, or auditing accountant billing vs SMB billing. The billing file is the ground truth for who actually pays.
---

# Billing Reconciliation — Colppy

Cross-reference HubSpot ICP classifications against actual billing data to detect mismatches and ensure data consistency.

---

## Billing Data Source

**File**: `tools/outputs/facturacion.csv`
**Format**: Semicolon-delimited CSV, ~2,635 active billing rows
**Encoding**: UTF-8

### Columns

| Column | Name | Description |
|--------|------|-------------|
| 1 | **Email** | Customer contact email |
| 2 | **Customer Cuit** | CUIT of the entity being billed (who pays). May be `#N/A` |
| 3 | **Plan description** | Plan name (e.g., Enterprise, Platinum, Consultoras y Estudios) |
| 4 | **Id Plan** | Plan ID number |
| 5 | **Amount** | Billing amount |
| 6 | **Product CUIT** | CUIT of the entity using the product (who uses Colppy) |
| 7 | **IdEmpresa** | Colppy empresa ID — **links to HubSpot deals via `id_empresa` field** |

---

## Key Insight: Customer CUIT vs Product CUIT

The critical signal for ICP Operador is when **Customer CUIT ≠ Product CUIT**:

- **Customer CUIT = Product CUIT** → The company bills itself → likely **ICP PYME**
- **Customer CUIT ≠ Product CUIT** → Someone else pays for this product → likely **ICP Operador** (accountant billing)

### Stats from Current Data
- ~512 rows (20%) have Customer CUIT ≠ Product CUIT
- 272 rows are on explicit accountant plans (Consultoras y Estudios, Contador Independiente, etc.)
- ~240 rows have CUIT mismatches on generic plans (Enterprise, Essential, Platinum)
- This proves: **plan name alone is NOT reliable for ICP classification**

---

## Plan Types in Billing

### Accountant-Specific Plans
| Plan | Count | Signal |
|------|-------|--------|
| Consultoras y Estudios | 122 | Strong accountant signal |
| Contador Independiente | 99 | Strong accountant signal |
| Consultoras y Estudios + Sueldos + Portal | 31 | Accountant + payroll |
| Contador Independiente + Sueldos | 14 | Accountant + payroll |
| Contador Inicio + Sueldos | 6 | Accountant starter |

### Generic Plans (may still be accountant-billed)
Enterprise (1,103), Platinum (405), Full (330), Essential (310), Premium (28), Inicio (25), etc.

**Important**: A company on "Enterprise" plan can still be ICP Operador if the accountant is the one paying (Customer CUIT ≠ Product CUIT).

---

## How to Use for Reconciliation

### Step 1: Link Billing to HubSpot
- **IdEmpresa** column → matches HubSpot deal property `id_empresa`
- **Customer Cuit** → matches HubSpot company `cuit` field
- **Email** → matches HubSpot contact `email`

### Step 2: Determine Billing ICP from File
```
IF Customer_CUIT != Product_CUIT AND Customer_CUIT is valid (not #N/A):
    → Billing says: ICP Operador (someone else pays)
ELSE:
    → Billing says: ICP PYME (self-billing)
```

### Step 3: Compare with HubSpot ICP
```
HubSpot ICP = PRIMARY company (association type 5) → type field
    → type in ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado'] = ICP Operador
    → any other type = ICP PYME

Compare:
- Billing says Operador + HubSpot says Operador = ✅ Consistent
- Billing says Operador + HubSpot says PYME = ⚠️ MISMATCH — HubSpot may be wrong
- Billing says PYME + HubSpot says Operador = ⚠️ MISMATCH — investigate
- Billing says PYME + HubSpot says PYME = ✅ Consistent
```

### Step 4: Report Mismatches
Flag for RevOps review:
- Deals where billing CUIT pattern contradicts HubSpot ICP classification
- Companies on accountant plans but classified as PYME in HubSpot
- Companies with CUIT mismatches but no primary company association in HubSpot

---

## Common Reconciliation Queries

### Find deals with billing data
```
1. Get IdEmpresa from facturacion.csv
2. Search HubSpot deals: filter by id_empresa = IdEmpresa
3. Get primary company (association type 5) → check type
4. Compare with billing CUIT pattern
```

### Audit accountant plan companies
```
1. Filter facturacion.csv for Plan = "Consultoras y Estudios" or "Contador Independiente"
2. Get their IdEmpresa values
3. Search HubSpot deals by id_empresa
4. Verify primary company type = "Cuenta Contador" or similar
5. Flag any classified as "Cuenta Pyme"
```

### Find hidden accountant billing
```
1. Filter facturacion.csv where Customer_CUIT != Product_CUIT
2. Exclude rows already on accountant plans
3. These are companies on generic plans but billed through accountants
4. Cross-reference with HubSpot to check if properly classified
```

---

## Data Quality Notes

- Some Customer CUIT values are `#N/A` → skip for CUIT comparison
- Some Product CUIT values are `00-00000000-0` → placeholder/missing
- Amount is in ARS (Argentine Pesos)
- File is a point-in-time snapshot — may need periodic refresh

---

## Related Skills

- **icp-classification** — HubSpot ICP rules (primary company type)
- **hubspot-configuration** — Field mappings for id_empresa, cuit, associations
- **funnel-analysis** — How ICP feeds into funnel segmentation
- **facturacion-csv-colppy** — Different workflow: reconcile facturacion.csv vs Colppy billing snapshot
- **colppy-hubspot-reconciliation** — Different workflow: Colppy first payments vs HubSpot closed won by month
