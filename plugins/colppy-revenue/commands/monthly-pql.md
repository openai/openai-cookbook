---
name: monthly-pql
description: Monthly PQL rate analysis — PQL conversion rate per month with month-over-month trends
---

# /monthly-pql

Track PQL (Product Qualified Lead) conversion rate over time: what percentage of new contacts become active product users each month.

## Usage

```
/colppy-revenue:monthly-pql 2026-02
/colppy-revenue:monthly-pql 2025-07,2025-08,2025-09,2025-10,2025-11,2025-12
/colppy-revenue:monthly-pql last 6 months
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                  MONTHLY PQL ANALYSIS                            │
├─────────────────────────────────────────────────────────────────┤
│  1. For each month: fetch all contacts created                  │
│  2. Count how many have activo = true (PQLs)                    │
│  3. Calculate PQL rate = PQLs / Total Contacts                  │
│  4. Compare month-over-month with deltas                        │
│  5. Identify trends and best/worst months                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## What I Need From You

- **Month(s)**: Which month(s) to analyze. Can be a single month, comma-separated list, or a range like "last 6 months"
- If current month, I'll do month-to-date automatically

---

## Step-by-Step Execution

### Step 1: For Each Month, Fetch All Contacts Created

For each month in the analysis period, search HubSpot contacts:

Filters (ALL must match):
- `createdate` GTE `{month}-01T00:00:00Z`
- `createdate` LTE `{last-day-of-month}T23:59:59Z`
- `lead_source` HAS_PROPERTY (exclude nulls)
- `lead_source` NEQ `Usuario Invitado` (exclude team invitations)

**CRITICAL**: Always use HAS_PROPERTY + NEQ together for lead_source filtering.

Fetch these properties:
`email, createdate, activo, fecha_activo`

### Step 2: Count PQLs

A contact is a **PQL (Product Qualified Lead)** if:
- `activo` = `true`

Count total contacts and PQL contacts for each month.

**PQL Rate** = PQL count / Total contacts × 100

### Step 3: Build Monthly Comparison Table

```
Month       │ Total Contacts │ PQLs   │ PQL Rate │ MoM Δ Contacts │ MoM Δ PQL Rate │ MoM Δ PQLs
────────────┼────────────────┼────────┼──────────┼────────────────┼────────────────┼───────────
{month_1}   │ {n}            │ {n}    │ {x}%     │ —              │ —              │ —
{month_2}   │ {n}            │ {n}    │ {x}%     │ {+/-n}         │ {+/-x}pp       │ {+/-n}
{month_3}   │ {n}            │ {n}    │ {x}%     │ {+/-n}         │ {+/-x}pp       │ {+/-n}
...
```

Where:
- **MoM Δ Contacts** = change in total contacts vs previous month
- **MoM Δ PQL Rate** = change in PQL rate percentage points vs previous month
- **MoM Δ PQLs** = change in PQL count vs previous month

### Step 4: Key Insights

Calculate and highlight:

- **Contact volume trend**: Is the number of new contacts growing, flat, or declining?
- **PQL conversion trend**: Is the PQL rate improving, stable, or declining?
- **Best month**: Which month had the highest PQL rate?
- **Current vs best**: How does the most recent month compare to the best month?
- **Average PQL rate**: Across all analyzed months

### Step 5: Summary Stats

```
Metric                         │ Value
───────────────────────────────┼────────
Total Contacts (all months)    │ {n}
Total PQLs (all months)        │ {n}
Overall PQL Rate               │ {x}%
Best Month                     │ {month} ({x}%)
Worst Month                    │ {month} ({x}%)
Average Monthly PQL Rate       │ {x}%
```

---

## Important Notes

- **PQL definition**: `activo` = `true`. This means the contact has activated their product account and is using it.
- **PQL is a lagging indicator**: Contacts created in the current month may not have activated yet. MTD PQL rates will naturally be lower.
- **The standard lead_source filter applies**: HAS_PROPERTY + NEQ 'Usuario Invitado' together.
- HubSpot API uses UTC. UI uses Argentina (UTC-3). ~25 contact difference at month boundaries.
- When comparing months, always note if any month is MTD (incomplete).
