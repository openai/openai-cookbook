---
name: budget-dashboard
description: Refresh Building Blocks budget data, run deviation analysis, and create or update the budget dashboard
---

# /budget-dashboard

Refresh, query, or generate the Building Blocks Budget vs Actual dashboard.

## Usage

```
/colppy-ceo-assistant:budget-dashboard
/colppy-ceo-assistant:budget-dashboard refresh
/colppy-ceo-assistant:budget-dashboard deviation
```

---

## What You Get

1. **Refresh:** Fetch latest data from Google Sheets (colppy_budget, asp_forecast_2026) using the registry
2. **Deviation:** Budget vs Actual MRR and Average Ticket by product line
3. **Dashboard:** Create or update `docs/budget_dashboard.html` with summary cards, tables, and insights

---

## Step-by-Step Execution

### Step 1: Read Registry

Read `docs/GOOGLE_SHEETS_REGISTRY.json` (bundled in plugin). If workspace has `tools/docs/GOOGLE_SHEETS_REGISTRY.json`, that is canonical.

### Step 2: Fetch Data

```bash
curl -sL "https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}"
```

- **colppy_budget** (gid 1622687073) — Budget vs Real MRR
- **asp_forecast_2026** (gid 418547797) — Budget vs Actual ASP

### Step 3: Parse

- Budget section: rows before "REAL"
- REAL section: rows after "REAL"
- Match items by name (normalize Admnisitración vs Administración)
- Target month: Jan-2026 (or user-specified)

### Step 4: Output

- **Query only:** Present deviation table in chat
- **Dashboard:** Update `docs/budget_dashboard.html` with new data
- Include metadata: date range, tab names, record count

---

## Tips

- "Refresh data and show deviation" — fetch + parse + present in chat
- "Update the budget dashboard" — fetch + parse + write HTML
- "What's the deviation for New Product Sueldos ICP Pyme?" — fetch + parse + answer
