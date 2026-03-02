---
name: icp-analysis
description: Analyze closed-won deals to determine ICP Operador billing target (Accountant vs SMB) for a given period
---

# /icp-analysis

Analyze closed-won deals to determine whether revenue comes from Accountant-billed or SMB-billed customers (ICP Operador classification), and profile the initial MQL contact for each deal.

## Usage

```
/colppy-revenue:icp-analysis 2026-02
/colppy-revenue:icp-analysis 2025-07 to 2025-12
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                  ICP OPERADOR ANALYSIS                          │
├─────────────────────────────────────────────────────────────────┤
│  1. Fetch closed-won deals created AND closed in period         │
│  2. Find PRIMARY company (Type ID 5) for each deal              │
│  3. Classify: Accountant vs SMB based on company type           │
│  4. Find initial MQL contact (Type ID 14, fallback earliest)    │
│  5. Aggregate revenue, rol_wizard distribution, plan names      │
└─────────────────────────────────────────────────────────────────┘
```

---

## What I Need From You

- **Period**: Which month(s) to analyze (e.g. "2026-02", "january 2026", "last 3 months")
- **Comparison**: If multiple months, I'll show month-over-month trends

---

## Step-by-Step Execution

### Step 1: Fetch Closed-Won Deals in Period

Search HubSpot deals with ALL of these filters:
- `dealstage` EQ `closedwon`
- `createdate` GTE `{start-date}T00:00:00Z`
- `createdate` LTE `{end-date}T23:59:59Z`
- `closedate` GTE `{start-date}T00:00:00Z`
- `closedate` LTE `{end-date}T23:59:59Z`

**IMPORTANT**: Deals must be BOTH created AND closed within the period. This ensures we're measuring deals that originated and converted in the same window.

Fetch these properties for each deal:
`dealname, dealstage, closedate, createdate, amount, nombre_del_plan_del_negocio`

### Step 2: Find PRIMARY Company for Each Deal (ICP Operador)

For each deal, look up associated companies using:
- HubSpot associations API: deals → companies
- Use the **v4 associations endpoint** to get association type labels
- Look for association **Type ID 5** = PRIMARY company ("Empresa Primaria del Negocio")

**CRITICAL**: ICP Operador is determined by the PRIMARY company type, NOT by the plan name. Plan names are unreliable for this classification.

### Step 3: Classify Each Deal

Get the `type` property of each PRIMARY company. Classify as:

**Accountant (Contador)**:
- Company type is one of: `Cuenta Contador`, `Cuenta Contador y Reseller`, `Contador Robado`

**SMB (PYME)**:
- Any other company type (typically `Cuenta PYME`, `Cuenta PYME - Free`, etc.)

**Unclassified**:
- No PRIMARY company found (data quality issue — flag these)

### Step 4: Find Initial MQL Contact for Each Deal

For each deal, find associated contacts using:
- HubSpot associations API: deals → contacts
- Look for association **Type ID 14** = "Contacto Inicial que da el Alta del Negocio" (initial MQL contact)
- If Type ID 14 is not found, **fallback**: use the earliest-created contact associated with the deal, excluding contacts where lead_source is null or 'Usuario Invitado'

For each initial MQL contact, fetch:
`email, createdate, firstname, lastname, lead_source, rol_wizard`

### Step 5: Build Summary Tables

**ICP Operador Breakdown:**

```
ICP Operador        │ Deals  │ Revenue    │ % of Deals │ % of Revenue │ Avg Deal Size
────────────────────┼────────┼────────────┼────────────┼──────────────┼──────────────
Contador            │ {n}    │ ${x}       │ {x}%       │ {x}%         │ ${x}
PYME                │ {n}    │ ${x}       │ {x}%       │ {x}%         │ ${x}
Unclassified        │ {n}    │ ${x}       │ {x}%       │ {x}%         │ ${x}
────────────────────┼────────┼────────────┼────────────┼──────────────┼──────────────
TOTAL               │ {n}    │ ${x}       │ 100%       │ 100%         │ ${x}
```

**Rol Wizard Distribution (from initial MQL contacts):**

```
Rol Wizard              │ Count  │ % of Total
────────────────────────┼────────┼───────────
{rol_wizard_value}      │ {n}    │ {x}%
...
```

### Step 6: Deal Detail Table

For each deal, show:

| Deal Name | Amount | Close Date | ICP | Primary Company | MQL Contact | Rol Wizard | Lead Source | Plan |
|-----------|--------|------------|-----|-----------------|-------------|------------|-------------|------|

### Step 7: Data Quality Report

Report any issues found:
- Deals without a PRIMARY company association (Type ID 5)
- Deals where initial MQL contact couldn't be identified
- Show identification method stats: Type ID 14 vs earliest-contact fallback

---

## Important Notes

- **ICP is based on PRIMARY company type (Type ID 5), NOT plan name.** Plan names can be misleading.
- Accountant company types: `Cuenta Contador`, `Cuenta Contador y Reseller`, `Contador Robado`
- The HubSpot API uses UTC timestamps. The HubSpot UI uses Argentina timezone (UTC-3). There may be ~25 deal difference at month boundaries.
- Revenue = deal `amount` field for closed-won deals only.
- When running for multiple months, show a comparison table with MoM trends.
