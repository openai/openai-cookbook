---
name: growth-kpis
description: Generate a CEO-level growth KPI summary with key SaaS metrics and trends
---

# /growth-kpis

Generate a high-level growth KPI dashboard for the CEO.

## Usage

```
/colppy-ceo-assistant:growth-kpis 2026-02
/colppy-ceo-assistant:growth-kpis Q1 2026
```

---

## What You Get

A single-page executive summary with:

### Revenue Metrics
- Ending MRR / ARR
- Net New MRR (and MoM change)
- Quick Ratio
- Net Revenue Retention (NRR)

### Customer Metrics
- Total active CUITs (paid accounts)
- New customers this period
- Churned customers this period
- Logo churn rate

### Growth Efficiency
- MRR growth rate (MoM and YoY if data available)
- Expansion rate (expansion MRR ÷ starting MRR)
- Reactivation count and MRR

### PLG Funnel (from HubSpot + Mixpanel)
- Trial signups (MQLs)
- PQL rate (activated trials)
- Trial-to-paid conversion rate
- Average days to convert

---

## Step-by-Step Execution

### Step 1: Gather Data

Pull from all three sources:
1. **Billing DB**: MRR, subscriptions, CUIT counts
2. **HubSpot**: Contacts created, PQLs, SQLs, deals
3. **Mixpanel**: Product activation, feature usage (if accessible)

### Step 2: Calculate All Metrics

Use the definitions from the `saas-metrics-conventions` skill for consistent calculations.

### Step 3: Format as Executive Summary

```
╔══════════════════════════════════════════════════════════════╗
║                COLPPY GROWTH KPIs — {MONTH}                  ║
╠══════════════════════════════════════════════════════════════╣
║  MRR: $X.XXX.XXX    │  ARR: $XX.XXX.XXX   │  NRR: XXX,X%   ║
║  Net New: +$XXX.XXX  │  Quick Ratio: X,X    │  Churn: X,X%   ║
╠══════════════════════════════════════════════════════════════╣
║  Customers: X.XXX    │  New: +XXX           │  Churned: -XX   ║
║  PQL Rate: XX,X%     │  Conversion: X,X%    │  Avg Days: XX   ║
╚══════════════════════════════════════════════════════════════╝
```

### Step 4: Highlights & Alerts

- Flag any metric that changed >20% MoM
- Highlight positive trends in green, negative in red
- Include 1-2 actionable recommendations based on the data

---

## Tips

- **Board-ready**: "Generate growth KPIs for Q4 2025 in presentation format"
- **Comparison**: "Compare growth KPIs for January vs February 2026"
- **Deep dive**: "Growth KPIs for February, then drill into the churn increase"
