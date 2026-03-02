---
name: referral-funnel
description: Accountant referral funnel — deals sourced by accountant referrals, from creation to close-won
---

# /referral-funnel

Analyze the accountant referral pipeline: deals sourced via external accountant referrals, their close rates, revenue, and referring accountant firms.

## Usage

```
/colppy-revenue:referral-funnel 2026-02
/colppy-revenue:referral-funnel 2025-07 to 2025-12
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│               ACCOUNTANT REFERRAL FUNNEL                        │
├─────────────────────────────────────────────────────────────────┤
│  1. Fetch deals with lead_source = 'Referencia Externa          │
│     Contador' created in period                                 │
│  2. Validate accountant association (Type 8) on each deal       │
│  3. Identify closed-won deals (created + closed in period)      │
│  4. Classify by ICP and analyze revenue                         │
│  5. Rank referring accountant firms                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## What I Need From You

- **Period**: Which month(s) to analyze (e.g. "2026-02", "last quarter", "2025-07 to 2025-12")
- **Comparison**: If multiple months, I'll show trends

---

## Step-by-Step Execution

### Step 1: Fetch Referral Deals Created in Period

Search HubSpot deals with these filters:
- `createdate` GTE `{start-date}T00:00:00Z`
- `createdate` LTE `{end-date}T23:59:59Z`
- `lead_source` EQ `Referencia Externa Contador`

Fetch these properties:
`dealname, createdate, closedate, dealstage, amount, lead_source, primary_company_type`

### Step 2: Validate Accountant Association (Type 8)

For each deal, check for an accountant company association:
- Use v4 associations endpoint: deals → companies
- Look for association **Type ID 8** = "Estudio Contable / Asesor / Consultor Externo del negocio"

**IMPORTANT**: Type 8 is the accountant/advisor association. Do NOT use Type 2 (referrer) — salespeople don't use it reliably.

Two criteria must BOTH be true for a valid referral deal:
1. `lead_source` = `Referencia Externa Contador`
2. Deal has at least one Type 8 company association

Track deals that have the lead_source but no Type 8 association as data quality issues.

For each Type 8 company, fetch: `name, type` (company properties)

### Step 3: Identify Closed-Won Referral Deals

A deal is closed-won in period if:
- `dealstage` = `closedwon`
- `createdate` falls within the analysis period
- `closedate` falls within the analysis period

### Step 4: Classify Won Deals by ICP

For each closed-won deal, determine ICP via PRIMARY company (Type ID 5):
- Get associated companies, find Type ID 5
- **Accountant**: `Cuenta Contador`, `Cuenta Contador y Reseller`, `Contador Robado`
- **SMB**: Any other company type

### Step 5: Build Referral Funnel

```
Stage                              │ Count    │ % of Previous │ % of Total
───────────────────────────────────┼──────────┼───────────────┼──────────
1. Deals Created (referral)        │ {n}      │ —             │ 100.0%
   └─ With Type 8 association      │ {n}      │ {x}%          │ {x}%
   └─ Without Type 8 (⚠️)          │ {n}      │ {x}%          │ {x}%
2. Deal Closed Won                 │ {n}      │ {x}%          │ {x}%
```

**Revenue Summary:**
```
Total Revenue (Won)    │ ${x}
Average Deal Size      │ ${x}
Avg Time to Close      │ {x} days
```

### Step 6: ICP Breakdown of Won Deals

```
ICP (Won Deals)     │ Deals  │ Revenue    │ % of Won Deals │ Avg Deal Size
────────────────────┼────────┼────────────┼────────────────┼──────────────
Contador            │ {n}    │ ${x}       │ {x}%           │ ${x}
PYME                │ {n}    │ ${x}       │ {x}%           │ ${x}
Unclassified        │ {n}    │ ${x}       │ {x}%           │ ${x}
```

### Step 7: Top Referring Accountant Firms

Rank the Type 8 companies by number of deals referred:

```
Rank │ Accountant Firm           │ Deals Referred │ Won │ Revenue    │ Win Rate
─────┼───────────────────────────┼────────────────┼─────┼────────────┼─────────
1    │ {company_name}            │ {n}            │ {n} │ ${x}       │ {x}%
2    │ {company_name}            │ {n}            │ {n} │ ${x}       │ {x}%
...  │ (top 10)                  │                │     │            │
```

Also report:
- Total unique accountant firms referring deals
- Average deals per accountant firm
- Average accountants associated per deal

### Step 8: Deal Detail Table

For each referral deal, show:

| Deal Name | Amount | Created | Closed | Stage | Won? | Accountant Firm(s) | ICP |
|-----------|--------|---------|--------|-------|------|--------------------|-----|

---

## Important Notes

- **Two criteria required**: `lead_source = 'Referencia Externa Contador'` AND Type 8 company association. Both must be present.
- **Type 8** = "Estudio Contable / Asesor / Consultor Externo del negocio" — this is the accountant/advisor link.
- **Do NOT use Type 2** (referrer association) — sales reps don't use it consistently.
- Revenue = deal `amount` for closed-won deals only.
- Closed-won requires both `createdate` AND `closedate` within the period.
- Average time to close = closedate - createdate in days.
- HubSpot API uses UTC. UI uses Argentina (UTC-3). Small differences at month boundaries.
