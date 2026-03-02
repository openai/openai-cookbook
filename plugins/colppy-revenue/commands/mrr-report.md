---
name: mrr-report
description: Generate a monthly MRR waterfall report showing new, expansion, contraction, churn, and reactivation
---

# /mrr-report

Generate a complete MRR waterfall report for a given month or range of months.

## Usage

```
/colppy-revenue:mrr-report 2026-02
/colppy-revenue:mrr-report 2025-07 to 2026-01
```

---

## What You Get

1. **MRR Waterfall Table** — Starting MRR, New, Expansion, Reactivation, Contraction, Churn, Ending MRR
2. **Derived Metrics** — Net New MRR, Gross Churn Rate, Net Revenue Retention, Quick Ratio
3. **Trend Chart** (if multiple months) — MRR evolution over time
4. **Top Movers** — Largest new accounts, biggest expansions, biggest churns

---

## Step-by-Step Execution

### Step 1: Load Billing Data

Look for `facturacion_hubspot.db` as the primary billing source. If unavailable, fall back to HubSpot closed-won deals.

### Step 2: Calculate MRR Components

For each month in the requested range:

```
Starting MRR     = Ending MRR of previous month
New MRR          = First-ever payment CUITs
Expansion MRR    = Existing CUITs that increased MRR
Contraction MRR  = Existing CUITs that decreased MRR
Churned MRR      = CUITs that went to $0
Reactivation MRR = Previously churned CUITs that returned
Ending MRR       = Starting + New + Expansion + Reactivation − Contraction − Churn
```

### Step 3: Present Results

```
Month     │ Starting  │ New     │ Expan  │ React  │ Contr  │ Churn  │ Ending    │ Net New
──────────┼───────────┼────────┼────────┼────────┼────────┼────────┼───────────┼────────
2026-01   │ $X.XXX    │ $X.XXX │ $XXX   │ $XXX   │ -$XXX  │ -$XXX  │ $X.XXX    │ $X.XXX
2026-02   │ $X.XXX    │ $X.XXX │ $XXX   │ $XXX   │ -$XXX  │ -$XXX  │ $X.XXX    │ $X.XXX
```

### Step 4: Metadata

Always include at the bottom:
- Date range analyzed
- Data source used
- Total records processed
- Any filters applied

---

## Tips

- **Compare periods**: "Generate MRR report for Q4 2025 vs Q1 2026"
- **Segment by plan**: "Show MRR waterfall by plan type for January 2026"
- **Drill into churn**: "Which CUITs churned in February 2026 and what were their plans?"
