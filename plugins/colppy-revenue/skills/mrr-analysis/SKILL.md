---
name: mrr-analysis
description: Guided workflow for generating MRR dashboards, MRR movement analysis, and revenue trend reports. Use when the user asks about MRR, revenue, subscription metrics, or monthly billing performance.
---

# MRR Analysis Workflow

## Trigger

User asks about MRR, revenue trends, subscription metrics, or wants an MRR dashboard generated.

## Required Inputs

- **Period**: Month or date range to analyze (e.g., `2026-02`, `Q1 2026`, `last 6 months`)
- **Granularity**: Monthly (default), weekly, or daily
- **Segment** (optional): Plan type, acquisition channel, accountant vs direct

## Workflow

### Step 1: Identify Data Source

Check for existing billing data:
1. Look for `facturacion_hubspot.db` in the workspace — this is the primary billing database
2. If not available, fall back to HubSpot deals with `dealstage = closedwon`
3. Note which source is used in the output metadata

### Step 2: Calculate MRR Components

For the requested period, compute:

| Component    | Calculation                                                    |
|-------------|----------------------------------------------------------------|
| Starting MRR | Sum of active subscriptions at period start                    |
| New MRR      | MRR from CUITs with first-ever payment in this period          |
| Expansion    | MRR increase from CUITs that upgraded                          |
| Contraction  | MRR decrease from CUITs that downgraded                        |
| Churn        | MRR lost from CUITs that cancelled                             |
| Reactivation | MRR from CUITs returning after previous churn                  |
| Ending MRR   | Starting + New + Expansion + Reactivation − Contraction − Churn|

### Step 3: Calculate Derived Metrics

- **Net New MRR** = New + Expansion + Reactivation − Contraction − Churn
- **Gross Churn Rate** = Churned MRR ÷ Starting MRR
- **Net Revenue Retention** = Ending MRR ÷ Starting MRR
- **Quick Ratio** = (New + Expansion + Reactivation) ÷ (Contraction + Churn)

### Step 4: Trend Visualization

If multiple months are requested:
- MRR waterfall chart (stacked bar showing movements)
- MRR trend line (ending MRR over time)
- Churn rate trend

### Step 5: Present Results

Format all output following Argentina conventions:
- Currency with `$`, comma decimals, period thousands
- Include metadata: date range, data source, record count, filters

## Guardrails

- Never invent revenue numbers — only use verified billing data
- Always show the data source and record count
- Flag any months with incomplete data (e.g., current month = MTD)
- If MRR components don't reconcile (Starting + movements ≠ Ending), flag the discrepancy
