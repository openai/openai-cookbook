---
name: cohort-retention
description: Guided workflow for building cohort retention tables and visualizations. Use when the user asks about retention, cohort analysis, customer lifetime, or survival curves.
---

# Cohort Retention Analysis

## Trigger

User asks about customer retention, cohort performance, survival analysis, or lifetime value trends.

## Required Inputs

- **Cohort window**: Range of cohort months to include (e.g., `2025-06 to 2025-12`)
- **Metric**: Logo retention (default) or revenue retention
- **Segment** (optional): Plan type, acquisition channel, accountant-referred vs direct

## Workflow

### Step 1: Build Cohort Definition

- **Cohort month** = month of first paid subscription for each CUIT
- Exclude trial-only accounts (never converted)
- Each CUIT appears in exactly one cohort (its first payment month)

### Step 2: Measure Monthly Retention

For each cohort, check each subsequent month:
- **Logo retention**: CUIT has any active subscription → retained
- **Revenue retention**: Sum of MRR from cohort CUITs ÷ cohort's Month 0 MRR

### Step 3: Build Retention Table

```
Cohort    │ M0    │ M1    │ M2    │ M3    │ M4    │ M5    │ M6
──────────┼───────┼───────┼───────┼───────┼───────┼───────┼──────
2025-06   │ 100%  │ 85%   │ 78%   │ ...   │       │       │
2025-07   │ 100%  │ 82%   │ ...   │       │       │       │
...
```

### Step 4: Visualizations

Generate:
1. **Retention heatmap** — Color-coded table (green = high retention, red = low)
2. **Retention curves** — Line chart with one line per cohort (M0 → Mn)
3. **Average retention curve** — Single line showing average across all cohorts

### Step 5: Insights

Calculate and highlight:
- **Month with steepest drop** (where most churn happens)
- **Stabilization point** (month where retention flattens)
- **Best/worst performing cohorts** and hypotheses for why
- **Revenue retention vs logo retention gap** (expansion signal)

## Guardrails

- Only include months with complete data (not partial months)
- Minimum cohort size of 10 CUITs to be statistically meaningful
- Always label whether showing logo or revenue retention
- Format percentages with comma decimal separator (Argentina standard)
