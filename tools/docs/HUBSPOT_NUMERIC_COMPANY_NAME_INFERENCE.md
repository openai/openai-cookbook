# HubSpot: Numeric Company Name Inference Rule

**Rule:** When a company in HubSpot has a name that is **only a number** (e.g. `64481`, `53114`), treat it as a likely internal id or `id_empresa`. Infer a better name from available data and rename the company.

## Data Sources for Inference

1. **Deal names** (primary): When this company bills for deals (via facturacion `customer_cuit`), extract the business name from `deal_name`:
   - `"95973 - PayGoal Uruguay"` → `PayGoal Uruguay`
   - `"55406 Coordline"` → `Coordline`
   - `"61255 - INDUSTRIAS PETROLA SRL"` → `INDUSTRIAS PETROLA SRL`

2. **Email domain** (fallback): Extract domain from facturacion emails and convert to company name:
   - `admin@paygoal.io` → `PayGoal`
   - Skips personal domains: gmail, hotmail, yahoo, outlook, live, icloud

## Proposed Format

Keep the numeric id for traceability: **`{id} - {InferredName}`**

Examples:
- `64481` → `64481 - PayGoal Uruguay`
- `53114` → `53114 - Gran Hotel Argentino`

## Implementation

**Script:** `tools/scripts/hubspot/infer_numeric_company_names.py`

**Usage:**
```bash
# Dry-run (default): show proposed changes, no updates
python tools/scripts/hubspot/infer_numeric_company_names.py

# Apply updates to HubSpot
python tools/scripts/hubspot/infer_numeric_company_names.py --apply

# Custom DB path
python tools/scripts/hubspot/infer_numeric_company_names.py --db path/to/facturacion_hubspot.db
```

**Prerequisites:**
- `tools/outputs/facturacion_hubspot.db` (from `build_facturacion_hubspot_mapping.py`)
- Tables: `companies`, `deals`, `facturacion`

## When to Use

- During data quality reviews
- After importing companies that may have been created with numeric ids
- As part of CRM hygiene workflows

## No Inference Cases

When neither deal names nor professional email domains yield a name, the company is listed for **manual review**. Example: company `66235` with only `mcsa.hidraulica@gmail.com` (personal domain).
