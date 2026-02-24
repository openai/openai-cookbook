---
name: churn-analysis
description: Analyze customer churn — logo and revenue churn rates, churn reasons, and at-risk accounts
---

# /churn-analysis

Run a comprehensive churn analysis for a given period.

## Usage

```
/colppy-ceo-assistant:churn-analysis 2026-02
/colppy-ceo-assistant:churn-analysis last 6 months
```

---

## What You Get

1. **Churn Summary** — Logo churn rate, revenue churn rate, count of churned CUITs
2. **Churn by Segment** — Breakdown by plan type, tenure, acquisition channel
3. **Churn Trend** (if multiple months) — Evolution of churn rate over time
4. **At-Risk Accounts** — Accounts showing churn signals (downgrades, low usage, support tickets)
5. **Revenue Impact** — Total MRR lost and projected annual impact

---

## Step-by-Step Execution

### Step 1: Identify Churned Accounts

A CUIT is churned if:
- Had an active subscription in the previous month
- Has no active subscription in the current month
- MRR went from >$0 to $0

### Step 2: Calculate Churn Metrics

```
Logo Churn Rate    = Churned CUITs ÷ Starting CUITs
Revenue Churn Rate = Churned MRR ÷ Starting MRR
Net Revenue Churn  = (Churned MRR − Expansion MRR) ÷ Starting MRR
```

### Step 3: Segment Analysis

Break down churned accounts by:
- **Plan type** — Which plans churn most?
- **Tenure** — How long were they customers before churning?
- **Acquisition channel** — Accountant-referred vs direct vs integrator
- **MRR tier** — Small ($1-5k), medium ($5-15k), large ($15k+)

### Step 4: Present Results

Format with Argentina conventions ($, comma decimals). Include metadata footer with date range, source, and record count.

---

## Tips

- **Churn cohort view**: "Show churn by month of original signup"
- **Recovery opportunities**: "Which churned accounts had high usage before leaving?"
- **Benchmark comparison**: "How does our churn compare to SaaS benchmarks?"
