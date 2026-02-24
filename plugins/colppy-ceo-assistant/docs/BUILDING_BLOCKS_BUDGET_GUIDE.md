# Building Blocks Budget — Fetch, Query, Dashboard Guide

## Overview

Colppy's Building Blocks budget data lives in Google Sheets. This guide explains how to fetch, query, and create dashboards from that data using the **Google Sheets Registry** — no URL needed.

## Registry

**File:** `docs/GOOGLE_SHEETS_REGISTRY.json` (bundled in plugin)

Each tab entry has:
- `id` — Short identifier (e.g. `colppy_budget`)
- `tab_name` — Exact Google Sheets tab name
- `file_id` — Spreadsheet ID from the URL
- `gid` — Tab/sheet ID (GID)
- `notes` — What the tab contains

## Fetch URL

```
https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}
```

**Requirement:** Sheet must be shared as "Anyone with the link can view".

**Command:**
```bash
curl -sL "https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}"
```

Do NOT use `mcp_web_fetch` for Google Sheets — it often returns 500 errors.

## Key Tabs for Building Blocks

| id | tab_name | Content |
|----|----------|---------|
| colppy_budget | Building Blocks Por Producto - Q4'25 HLT | Budget vs Real MRR (New Product, Upsell, Cross sell, EoP). Has Budget section and REAL section. |
| asp_forecast_2026 | ASP Forecast 2026 & Actual | Budget vs Actual Average Ticket (ASP) by product line. Same Budget/REAL structure. |
| colppy_budget_first | Building Blocks Budget & Forecast 2026 | Contabilidad, New MRR, Churn by product line (Contabilidad, Remuneraciones, Facturación, etc.). |
| colppy_budget_aprobado | Budget Aprobado | KPIs, Net ASP, Gross Margin, CAC, Churn, LTV, NRR, P&L. |

## CSV Structure (colppy_budget)

- **Header row:** Row 2 (0-indexed). Columns: Item (col 4), Unit, Dec-2023 … Dec-2026, Q4'25, Q1', Q2', Q3', Q4', FY '25, FY '26, % Dif
- **Budget section:** Rows 3–38. Item in col 4.

- **REAL section:** Starts at row with "REAL" in col 4. Same column layout for actuals.

- **Jan-2026 column:** Use for current month comparison. Find column index by header "Jan-2026".

## CSV Structure (asp_forecast_2026)

- Same layout: Budget rows first, then REAL section.
- Item = "Item Ticket Promedio" (Average Ticket).
- New Product, Upsell, Cross sell lines by product (Administración ICP Pyme, Sueldos ICP Operador, etc.).

## Deviation Analysis

1. **Fetch** both tabs via curl.
2. **Parse** Budget and REAL sections for target month (e.g. Jan-2026).
3. **Match** items by name (normalize typos: Admnisitración vs Administración).
4. **Compute:** deviation = Actual − Budget, % var = (deviation / Budget) × 100.

## Dashboard Output

**Location:** `docs/budget_dashboard.html` (workspace root = openai-cookbook)

**Sections:**
1. Summary cards (New Product MRR, Upsell MRR, Cross Sell, EoP, Avg Ticket New, Avg Ticket Upselling)
2. MRR table by product line
3. Average Ticket table by product line
4. Key insights

**Formatting:** Argentina conventions — $, comma decimals, period thousands.

## Refresh Script

**Script:** `tools/scripts/refresh_budget_dashboard.py`

Fetches colppy_budget and asp_forecast_2026 from Google Sheets, parses Budget vs REAL for Jan-2026, and generates `docs/budget_dashboard.html`.

```bash
python tools/scripts/refresh_budget_dashboard.py --output docs/budget_dashboard.html
```

Also runs as part of full dashboard refresh: `./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs`

## Fetch Verification

Run from terminal to verify tabs are accessible (sheet must be "Anyone with the link can view"):

```bash
FILE_ID="1vouNcGMeNbpWW6znS8SZZdjUvG6ZzUIq_rh0zr4mJlY"
curl -sL "https://docs.google.com/spreadsheets/d/${FILE_ID}/export?format=csv&gid=1622687073" | head -1  # colppy_budget
curl -sL "https://docs.google.com/spreadsheets/d/${FILE_ID}/export?format=csv&gid=418547797" | head -1   # asp_forecast_2026
```

If you get CSV (rows starting with commas or quoted text), the tab is OK. If you get HTML ("No se pudo abrir"), the tab is not accessible or the gid is wrong.

## Troubleshooting: Tab returns HTML error

If a tab returns an HTML error ("No se pudo abrir") instead of CSV, the gid in the registry may be wrong. Google Sheets gids are persistent IDs; they change if tabs are reordered or deleted.

**To fix:** Open the spreadsheet, click the tab, copy the number after `gid=` from the URL, and update both registry files with that gid.

## Cloud AI / Portable Use

- **Registry:** `docs/GOOGLE_SHEETS_REGISTRY.json` is bundled in the plugin.
- **Workspace:** If `tools/docs/GOOGLE_SHEETS_REGISTRY.json` exists in the workspace, use it as canonical; plugin copy is fallback.
- **Fetch:** Requires terminal (curl). If not available, instruct user to run locally or use another integration.
