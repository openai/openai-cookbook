# Dashboard Refresh Guide — MRR, ICP, Building Blocks

**Purpose:** How to refresh all Colppy dashboards. Use when facturacion.csv or Building Blocks Google Sheets are updated.

---

## 1. Dashboards Overview

| Dashboard | Location | Data Source | What It Shows |
|-----------|----------|-------------|---------------|
| **MRR Dashboard** | `docs/mrr_dashboard.html` | facturacion.csv + HubSpot | Accountant portfolio matrix, growth buckets, MRR by portfolio size, churn |
| **ICP Dashboard** | `docs/icp_dashboard.html` | facturacion_hubspot.db | Company-wide ICP breakdown, deal stage distribution |
| **Building Blocks Budget** | `docs/budget_dashboard.html` | Google Sheets (colppy_budget, asp_forecast_2026) | Budget vs Actual MRR and ASP by product line |

---

## 2. Prerequisites

- **For full refresh (MRR + ICP):**
  - `tools/outputs/facturacion.csv` — fresh export from billing (Colppy/building blocks)
  - `HUBSPOT_API_KEY` in `.env` (or `COLPPY_CRM_AUTOMATIONS`)
  - OpenAI cookbook repo cloned locally

- **For Building Blocks only:**
  - Google Sheets shared as "Anyone with the link can view"
  - `docs/GOOGLE_SHEETS_REGISTRY.json` (bundled in plugin)

---

## 3. Refresh Commands

### Full Refresh (facturacion + HubSpot + all dashboards)

When facturacion.csv was updated:

```bash
cd /path/to/openai-cookbook
./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs
```

**Runs:**
1. Build facturacion–HubSpot mapping (facturacion_hubspot.db)
2. Populate deal associations (HubSpot API)
3. Populate accountant deals (incl. churned)
4. Regenerate MRR dashboard
5. Regenerate ICP dashboard
6. Fetch Building Blocks from Google Sheets and regenerate budget dashboard

**Duration:** ~30 min (due to HubSpot API rate limits)

---

### Dashboard Only (no new billing/HubSpot data)

When only regenerating HTML from existing DB:

```bash
./tools/scripts/hubspot/refresh_dashboard.sh --dashboard-only --output-dir docs
```

**Runs:** MRR + ICP + Building Blocks dashboards from existing facturacion_hubspot.db and fresh Google Sheets fetch.

**Duration:** ~2 min

---

### Building Blocks Only

When only Building Blocks Google Sheets were updated:

```bash
python tools/scripts/refresh_budget_dashboard.py --output docs/budget_dashboard.html
```

**Runs:** Fetch colppy_budget and asp_forecast_2026 from Google Sheets, parse Budget vs REAL for Jan-2026, generate HTML.

**Duration:** ~2 s

---

## 4. Data Chain (Full Refresh)

| Step | Input | Output |
|------|-------|--------|
| 1. Billing export | Colppy/billing system | `tools/outputs/facturacion.csv` (manual export) |
| 2. Build | facturacion.csv + HubSpot API | `tools/data/facturacion_hubspot.db` |
| 3. Populate associations | DB + HubSpot API | `deal_associations` in DB |
| 4. Populate accountant deals | DB + HubSpot API | Churned deals in DB |
| 5. MRR dashboard | DB | `docs/mrr_dashboard.html` |
| 6. ICP dashboard | DB | `docs/icp_dashboard.html` |
| 7. Building Blocks | Google Sheets (curl) | `docs/budget_dashboard.html` |

---

## 5. Running on Claude (Cloud AI)

**Claude cannot execute local scripts.** When the user asks to "refresh dashboard" or "refresh building blocks":

1. **Read** this guide and `docs/BUILDING_BLOCKS_BUDGET_GUIDE.md`, `docs/MRR_DASHBOARD_DEFINITIONS.md`
2. **Output** the exact commands the user must run locally (see Section 3)
3. **Explain** which command to use based on what changed:
   - facturacion.csv updated → full refresh
   - Building Blocks sheets updated → Building Blocks only
   - Nothing changed, just want fresh HTML → dashboard-only

**Example response:**

> To refresh the dashboards after updating facturacion.csv, run this in your terminal (from the openai-cookbook repo):
>
> ```bash
> ./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs
> ```
>
> This will rebuild the DB from facturacion + HubSpot, populate associations, and regenerate all three dashboards (MRR, ICP, Building Blocks). Expect ~30 minutes.
>
> If only Building Blocks Google Sheets were updated, run instead:
>
> ```bash
> python tools/scripts/refresh_budget_dashboard.py --output docs/budget_dashboard.html
> ```

---

## 6. Script Options

| Script | Key Options |
|--------|-------------|
| `refresh_dashboard.sh` | `--dashboard-only` (skip build/populate), `--output-dir DIR`, `--facturacion PATH`, `--db PATH` |
| `refresh_budget_dashboard.py` | `--output PATH`, `--registry PATH` |

---

## 7. Related Docs

- [MRR_DASHBOARD_DEFINITIONS.md](./MRR_DASHBOARD_DEFINITIONS.md) — MRR formulas, buckets, refresh pipeline
- [BUILDING_BLOCKS_BUDGET_GUIDE.md](./BUILDING_BLOCKS_BUDGET_GUIDE.md) — Google Sheets fetch, CSV structure, deviation analysis
- [GOOGLE_SHEETS_REGISTRY.json](./GOOGLE_SHEETS_REGISTRY.json) — Tab IDs, file_id, gid for Building Blocks
- [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md) — Section 9: Keeping the dashboard up to date
