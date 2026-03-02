---
name: icp-check
description: Check ICP classification for a specific deal or set of deals. Determines if a deal is ICP Operador (accountant billing) or ICP PYME (SMB billing) based on the primary company type.
---

# ICP Check

Classify deals as ICP Operador or ICP PYME.

## Steps

1. **Identify the deal(s)** to classify:
   - By deal ID
   - By company name
   - By date range or pipeline stage

2. **Get primary company** for each deal:
   - Fetch deal-company associations
   - Find association with typeId 5 (PRIMARY)
   - If no primary company → flag as data quality issue

3. **Read company type**:
   - Check deal property `primary_company_type` first (avoids extra API call)
   - If not available, read the primary company's `type` field

4. **Classify**:
   - `type` in `['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']` → **ICP Operador** (we bill the accountant)
   - Any other type → **ICP PYME** (we bill the SMB)

5. **Report results** in a markdown table:
   | Deal | Primary Company | Type | ICP Classification |
   |------|----------------|------|-------------------|

6. **Important reminders**:
   - Plan name does NOT determine ICP
   - Association type 8 (Estudio Contable) does NOT determine ICP
   - Only the PRIMARY company (type 5) `type` field matters
