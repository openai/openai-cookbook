---
name: building-blocks-budget
description: Fetch, query, and create dashboards from Colppy Building Blocks budget data (Budget vs Actual MRR, Average Ticket). Uses Google Sheets registry — no URL needed. Use when the user asks about budget vs actual, deviations, forecast, building blocks, or wants to refresh/query budget data.
---

# Building Blocks Budget — Fetch, Query, Dashboard

## Trigger

User asks about:
- Budget vs actual
- Building blocks deviations
- Forecast vs real
- Refresh budget data
- Create/update budget dashboard
- MRR by product line (Administración, Sueldos, Upsell, Cross sell)
- Average ticket (ASP) by product

## Registry (No URL Needed)

**Read:** `docs/GOOGLE_SHEETS_REGISTRY.json` (bundled in plugin)

The registry lists all Colppy budget tabs. Each entry has: `id`, `tab_name`, `file_id`, `gid`, `notes`.

### Key Tabs for Building Blocks

| id | tab_name | Use For |
|----|----------|---------|
| colppy_budget | Building Blocks Por Producto - Q4'25 HLT | Budget vs Real MRR (New Product, Upsell, Cross sell, EoP) |
| asp_forecast_2026 | ASP Forecast 2026 & Actual | Budget vs Actual Average Ticket (ASP) |
| colppy_budget_first | Building Blocks Budget & Forecast 2026 | Contabilidad, New MRR, Churn by product line |
| colppy_budget_aprobado | Budget Aprobado | KPIs, Net ASP, Gross Margin, CAC, P&L |

## Fetch URL Pattern

```
https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}
```

**Requirement:** Sheet must be shared as "Anyone with the link can view".

**Run:** `curl -sL "https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}"` from the terminal. Do NOT use `mcp_web_fetch` for Google Sheets (unreliable).

## Workflow

### 1. Refresh Data

When user says "refresh", "fetch", "grab", or "get the data":
1. Read `docs/GOOGLE_SHEETS_REGISTRY.json`
2. Identify the tab(s) needed (e.g. colppy_budget for MRR, asp_forecast_2026 for ASP)
3. Run `curl -sL "https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}"` for each tab
4. Parse CSV and present or analyze

### 2. Query / Deviation Analysis

For Budget vs Actual:
- **MRR:** colppy_budget tab — Budget section has `Item` in col 4, `Jan-2026` (or target month) in the date column. REAL section has actuals below.
- **ASP:** asp_forecast_2026 tab — Same structure: Budget rows, then REAL rows.

Compute: deviation = Actual − Budget, % variance = (deviation / Budget) × 100.

### 3. Create Dashboard

When user wants a dashboard:
1. Fetch colppy_budget and asp_forecast_2026
2. Parse Budget vs Real for target month (e.g. Jan-2026)
3. Generate HTML (or update existing `docs/budget_dashboard.html` in workspace)
4. Include: summary cards, MRR table, ASP table, key insights

**Dashboard location:** `docs/budget_dashboard.html` (workspace root = openai-cookbook)

**Refresh script:** `tools/scripts/refresh_budget_dashboard.py` — fetches both tabs, parses Budget vs REAL for Jan-2026, generates HTML. Run: `python tools/scripts/refresh_budget_dashboard.py --output docs/budget_dashboard.html`. Also runs as part of `./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs`.

**Related:** `docs/DASHBOARD_REFRESH_GUIDE.md` for full dashboard refresh workflow.

## Output Formatting

- Currency: `$` prefix, comma as decimal separator (Argentina)
- Percent: `+1,3%` or `-78,6%`
- Include `tab_name` in responses so user knows which tab is referenced

## Cloud AI / Portable Use

When the plugin is used in Cloud AI or another environment:
- The registry is in `docs/GOOGLE_SHEETS_REGISTRY.json` (relative to plugin root)
- If the workspace has `tools/docs/GOOGLE_SHEETS_REGISTRY.json`, that is the canonical source; the plugin's copy is a fallback
- Fetch requires terminal access (curl). If not available, instruct the user to run the curl locally or use a different integration
