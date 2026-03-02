---
name: funnel-analysis
description: Colppy's funnel definitions and analysis methodology. Covers MQL to Deal Won strict funnel path, PQL analysis, scoring/contactability, and conversion metrics. Trigger when discussing funnels, conversion rates, MQL, SQL, PQL, pipeline, or sales performance.
---

# Funnel Analysis — Colppy

Defines Colppy's sales funnel stages, conversion methodology, and analysis scripts.

---

## Strict Funnel Path

```
MQL → Deal Created → Deal Closed Won
```

- SQL metrics are shown as **informational only** (not part of strict funnel calculation)
- Conversion rates: MQL→Deal, Deal→Won, MQL→Won

---

## Funnel Stage Definitions

### MQL (Marketing Qualified Lead)
- **MQL Contador**: Contacts created in period with `rol_wizard` indicating accountant role
- **MQL PYME**: Contacts created in period with `rol_wizard` NOT indicating accountant role
- Determined by the signup wizard role selection

### SQL (Sales Qualified Lead)
- Contact with `hs_v2_date_entered_opportunity` set in period
- PLUS at least one deal associated (any deal)
- SQL = Deal Creation (when contact enters 'Oportunidad' stage, deal is created)
- **Informational metric only** — not part of strict funnel

### Deal Created
- Deals with `createdate` in the analysis period
- Must be associated with an MQL contact from the same period

### Deal Closed Won
- Deals with both `createdate` AND `closedate` in the period
- Must have gone through the complete MQL → Deal Created path

---

## Two Channel Funnels

### Accountant Channel Funnel
- Script: `analyze_accountant_mql_funnel.py`
- Path: MQL Contador → Deal Created → Won
- ICP classification by PRIMARY company type
- Output: Terminal (markdown) + CSV to `tools/outputs/accountant_mql_funnel_*.csv`

### SMB Channel Funnel
- Script: `analyze_smb_mql_funnel.py`
- Path: MQL PYME → Deal Created → Won
- Same structure as accountant funnel but for SMB contacts
- Output: Terminal (markdown) + CSV to `tools/outputs/smb_mql_funnel_*.csv`

### SMB WITH vs WITHOUT Accountant Comparison
- Script: `analyze_smb_accountant_involved_funnel.py`
- **Definition:** Accountant involvement = SMB deal closed + accountant company (association type 8) on the deal. We bill to the SMB. NOT ICP Operador (we bill to the accountant).
- **Single run** produces both analyses and comparison
- WITH: Deals with `tiene_cuenta_contador > 0` OR association type 8 + contacts
- WITHOUT: Deals with `tiene_cuenta_contador = 0` or null, no type 8
- Output: `tools/outputs/smb_accountant_funnel_comparison_{dates}.csv`
- Command: `/colppy-revenue:smb-accountant-comparison` with date range

```bash
python tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py --start-date 2025-10-01 --end-date 2026-02-01
# Add --minimal for fastest run (~5 min); add --dual-criteria for type 8 check per deal (slower)
```

---

## PQL (Product Qualified Lead) Analysis

PQL = determined by product usage signals (from Mixpanel).

### PQL Analysis Scripts
- **Primary**: `pql_sql_deal_relationship_analysis.py` — PQL → SQL → Deal relationship
- `sql_pql_conversion_analysis.py` — SQL/PQL timing
- `deal_focused_pql_analysis.py` — PQL effectiveness via actual deals
- `monthly_pql_analysis.py` — Monthly PQL trends

### Key PQL Metrics
- Total Contacts → PQL → SQL (Deal Creation) → Deal Close
- PQL vs Non-PQL comparison (deal creation rates, advantages)
- Timing analysis (PQL before/after SQL)
- Customer journey path analysis

---

## Scoring & Contactability

### Main Script
`high_score_sales_handling_analysis.py` — Score 40+ contacts analysis

### Metrics
- Contact rates, time to contact
- Owner performance
- SQL/PQL conversion rates by owner
- Uncontacted contacts identification
- Automatically excludes inactive owners and "Usuario Invitado" contacts

### MTD Scoring
`mtd_scoring_full_pagination.py` — Month-to-date with period comparison

---

## HubSpot Analysis MCP (Preferred When Available)

When the **hubspot-analysis** MCP is configured, use these tools instead of CLI for funnel and scoring:

| Tool | Purpose |
|------|---------|
| `run_smb_mql_funnel` | SMB MQL funnel. Pass months as space-separated (e.g. "2025-12 2026-01 2026-02") |
| `run_accountant_mql_funnel` | Accountant MQL funnel. Pass months |
| `run_smb_accountant_involved_funnel` | SMB WITH vs WITHOUT accountant. Pass months; optional minimal, dual_criteria |
| `run_high_score_analysis` | Score 40+ contactability. Pass month (YYYY-MM), or start_date+end_date, or current_mtd=True |
| `run_mtd_scoring` | MTD scoring comparison. Pass month1, month2 (e.g. "2026-01", "2026-02") |
| `run_visualization_report` | HTML report from high_score CSV. Pass month; run run_high_score_analysis first |

**Scoring examples:**
- "Run scoring for Feb 2026" → `run_high_score_analysis(month="2026-02")`
- "Compare scoring Jan vs Feb 2026" → `run_mtd_scoring(month1="2026-01", month2="2026-02")`
- "Current month scoring" → `run_high_score_analysis(current_mtd=True)`

---

## Running Funnel Scripts

```bash
# Accountant funnel
python tools/scripts/hubspot/analyze_accountant_mql_funnel.py --month 2025-12
python tools/scripts/hubspot/analyze_accountant_mql_funnel.py --months 2025-11 2025-12

# SMB funnel
python tools/scripts/hubspot/analyze_smb_mql_funnel.py --month 2025-12

# SMB WITH vs WITHOUT accountant comparison (single run, both analyses; default fast mode)
python tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py --start-date 2025-10-01 --end-date 2026-02-01
# Add --minimal for fastest run (~5 min); add --dual-criteria for type 8 check per deal (slower)

# PQL analysis
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month 2025-11

# Scoring
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --current-mtd
```

---

## Data Quality Notes

- API-based queries are the **source of truth** for contact counts
- CSV exports from HubSpot may exclude edge cases (contacts without owners, lifecycle stages, etc.)
- Edge cases are tracked and reported in script output
- Contacts without owners are exceptions but valid contacts

---

## Related Skills

- **funnel-definitions** — Exact HubSpot field definitions (activo, fecha_activo, hs_v2_date_entered_opportunity)
- **icp-classification** — How ICP feeds into funnel segmentation
- **hubspot-configuration** — Field definitions used in funnels
