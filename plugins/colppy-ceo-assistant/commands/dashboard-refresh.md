---
name: dashboard-refresh
description: Refresh MRR, ICP, and Building Blocks dashboards. Outputs the exact commands to run locally.
---

# /dashboard-refresh

Refresh Colppy dashboards (MRR, ICP, Building Blocks). Use when facturacion.csv or Building Blocks Google Sheets were updated.

## Usage

```
/colppy-ceo-assistant:dashboard-refresh
/colppy-ceo-assistant:dashboard-refresh full
/colppy-ceo-assistant:dashboard-refresh building-blocks
/colppy-ceo-assistant:dashboard-refresh dashboard-only
```

---

## What You Get

1. **Full** (default when user says "refresh"): facturacion + HubSpot + all dashboards
2. **Building Blocks only**: Fetch from Google Sheets, regenerate budget dashboard
3. **Dashboard only**: Regenerate HTML from existing DB (no API calls)

---

## Step-by-Step

### 1. Read DASHBOARD_REFRESH_GUIDE

Read `docs/DASHBOARD_REFRESH_GUIDE.md` for commands and context.

### 2. Determine Which Refresh

| User said / scenario | Command to output |
|----------------------|-------------------|
| "Refresh everything", "facturacion was updated" | Full refresh |
| "Building blocks updated", "budget dashboard" | Building Blocks only |
| "Just regenerate dashboards", "no new data" | Dashboard only |

### 3. Output Commands

**Full refresh:**
```bash
cd /path/to/openai-cookbook
./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs
```

**Building Blocks only:**
```bash
python tools/scripts/refresh_budget_dashboard.py --output docs/budget_dashboard.html
```

**Dashboard only:**
```bash
./tools/scripts/hubspot/refresh_dashboard.sh --dashboard-only --output-dir docs
```

### 4. Claude (Cloud AI) Limitation

Claude cannot run local scripts. Always output the commands for the user to run in their terminal. Explain what each command does and expected duration.

---

## Tips

- "Refresh dashboards" → ask: "Did you update facturacion.csv or only Building Blocks?" then output the right command
- "Building blocks CSV updated" → Building Blocks only (data comes from Google Sheets, not local CSV)
- User has no terminal → explain they need to run from a machine with the openai-cookbook repo
