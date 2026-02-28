# HubSpot Scripts and Workflows

**Last Updated:** 2026-02-12  
**Purpose:** Centralized HubSpot analysis scripts and custom code workflows

---

## 📁 Directory Structure

```
tools/scripts/hubspot/
├── README.md                           # This file
├── analysis/                           # Analysis scripts
│   ├── complete_november_analysis.py  # Comprehensive November 2025 analysis
│   └── unengaged_contacts_analysis.py # Unengaged contacts analysis
├── custom_code/                        # HubSpot custom code workflows (JavaScript)
│   ├── hubspot_first_deal_won_calculations.js
│   ├── hubspot_accountant_channel_deal_workflow.js
│   ├── hubspot_additional_product_created.js
│   ├── hubspot_company_blank_field_validator.js
│   ├── hubspot_deal_stage_update_workflow.js
│   ├── hubspot_contact_creation_business_hours.js
│   └── hubspot_industry_enrichment.js
├── utils/                              # Shared utilities (NEW)
│   ├── __init__.py
│   ├── datetime_utils.py              # Date parsing and formatting
│   └── constants.py                   # HubSpot field names and constants
├── fix_close_date_from_history.py      # Fix deal close dates from property history
└── *.py                                # Main analysis scripts
```

---

## 📚 Documentation

- **[HUBSPOT_SCRIPTS_DOCUMENTATION.md](../../docs/HUBSPOT_SCRIPTS_DOCUMENTATION.md)** - Complete documentation of all Python analysis scripts
- **[HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md](../../docs/HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md)** - **NEW** Complete PQL analysis documentation
  - PQL → SQL → Deal relationship analysis
  - Measurement methodology
  - Monthly comparison results
  - Script usage and recommendations
- **[HUBSPOT_FUNNEL_CONTACT_TO_DEAL_METHODOLOGY.md](../../docs/HUBSPOT_FUNNEL_CONTACT_TO_DEAL_METHODOLOGY.md)** - **NEW** How HubSpot builds funnels from Contact Created to Deal Created
  - HubSpot's official funnel report methodology
  - Fields and objects used (createdate, lifecycle stages, associations)
  - How contacts are traced to deals
  - Comparison with our script approach
- **[HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md](../../docs/HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md)** - Scoring and contactability analysis guide
- **[HUBSPOT_CUSTOM_CODE_WORKFLOW_MAPPING.md](../../docs/HUBSPOT_CUSTOM_CODE_WORKFLOW_MAPPING.md)** - Documentation of HubSpot workflow custom codes
- **[MRR_DASHBOARD_DEFINITIONS.md](../../docs/MRR_DASHBOARD_DEFINITIONS.md)** - **Team-shareable** MRR dashboard definitions, formulas, and how it works

---

## 🔧 Scripts Overview

### Analysis Scripts

#### Scoring & Contactability Analysis (Primary)
- **High Score Sales Handling:** `high_score_sales_handling_analysis.py` - **MAIN SCRIPT** for analyzing score 40+ contacts
  - Contactability analysis (contact rates, time to contact)
  - Owner performance metrics
  - SQL/PQL conversion rates by owner
  - Uncontacted contacts identification
  - **Automatically excludes inactive owners and "Usuario Invitado" contacts**
  - See detailed documentation below

- **MTD Scoring:** `mtd_scoring_full_pagination.py` - Month-to-date scoring analysis with period comparison
  - Score distribution analysis
  - SQL/PQL conversion rates by score range
  - Cycle time calculations

#### Lead Status & Quality Analysis
- **Uncontacted Lead Status:** `analyze_uncontacted_lead_status.py` - Analyzes contacts without Lead Status
  - Identifies contacts without Lead objects
  - Month-to-month comparison
  - Owner breakdown

- **Owner Status Check:** `check_owner_status.py` - Checks which owners are active/inactive
- **Owner Status Comparison:** `compare_owner_status_months.py` - Compares owner status across months

#### PQL (Product Qualified Lead) Analysis Scripts ⭐ **NEW**
- **PQL → SQL → Deal Relationship:** `pql_sql_deal_relationship_analysis.py` - **PRIMARY PQL ANALYSIS SCRIPT**
  - Comprehensive analysis of how PQL affects SQL (deal creation) and deal close rates
  - Funnel analysis: Total Contacts → PQL → SQL (Deal Creation) → Deal Close
  - PQL vs Non-PQL comparison (deal creation rates, advantages)
  - Timing analysis (PQL before/after SQL)
  - Customer journey path analysis
  - **Key Assumption:** SQL = Deal Creation (when contact enters 'Oportunidad' stage, deal is created)
  - Supports full month and month-to-date analysis
  - See detailed documentation below

- **SQL/PQL Timing Analysis:** `sql_pql_conversion_analysis.py` - SQL/PQL timing relationship
  - Analyzes if SQLs were PQL before or after SQL conversion
  - Measures PQL → SQL timing (days between PQL and SQL)
  - Cohort: Contacts created AND converted to SQL in the same period

- **Deal-Focused PQL Analysis:** `deal_focused_pql_analysis.py` - PQL effectiveness via actual deals
  - Deal attachment rates (PQL vs Non-PQL)
  - Deal win rates
  - Revenue per contact
  - Sales velocity metrics

- **Monthly PQL Reporting:** `monthly_pql_analysis.py` - Monthly PQL reporting and trends

#### Funnel Analysis Scripts ⭐ **NEW**
- **Accountant MQL Funnel:** `analyze_accountant_mql_funnel.py` - **ACCOUNTANT CHANNEL FUNNEL ANALYSIS**
  - Analyzes funnel from MQL Contador to Closed Won deals
  - **STRICT FUNNEL PATH**: MQL → Deal Created → Won (only counts deals that went through the complete path)
  - **Funnel Stages**:
    - MQL Contador: Contacts created in period with `rol_wizard` indicating accountant role
    - Deal Created: Deals created in period (associated with MQL contacts)
    - Deal Closed Won: Deals closed won in period (both `createdate` and `closedate` in period)
  - **SQL Metrics**: Shown as informational only (not part of strict funnel calculation)
    - SQL: Contacts with `hs_v2_date_entered_opportunity` in period with at least one deal associated (any deal)
    - Edge case tracking: Deals created before contacts, no deals associated, etc.
  - **Conversion Rates**: MQL→Deal, Deal→Won, MQL→Won (strict funnel)
  - ICP Classification: Based on PRIMARY company type (ICP Operador vs ICP PYME)
  - Supports single month, multiple months, or custom date range
  - **Output**: Terminal (markdown tables) + CSV export to `tools/outputs/accountant_mql_funnel_*.csv`
  - **CSV Filenames**: `accountant_mql_funnel_YYYYMMDD_YYYYMMDD.csv` (single period) or `accountant_mql_funnel_YYYYMM_YYYYMM.csv` (multi-month)

- **SMB MQL Funnel:** `analyze_smb_mql_funnel.py` - **SMB CHANNEL FUNNEL ANALYSIS**
  - Analyzes funnel from MQL PYME to Closed Won deals
  - **STRICT FUNNEL PATH**: MQL → Deal Created → Won (only counts deals that went through the complete path)
  - **Funnel Stages**:
    - MQL PYME: Contacts created in period with `rol_wizard` indicating SMB role (NOT accountant)
    - Deal Created: Deals created in period (associated with MQL contacts)
    - Deal Closed Won: Deals closed won in period (both `createdate` and `closedate` in period)
  - **SQL Metrics**: Shown as informational only (not part of strict funnel calculation)
    - SQL: Contacts with `hs_v2_date_entered_opportunity` in period with at least one deal associated (any deal)
    - Edge case tracking: Deals created before contacts, no deals associated, etc.
  - **Conversion Rates**: MQL→Deal, Deal→Won, MQL→Won (strict funnel)
  - ICP Classification: Based on PRIMARY company type (ICP Operador vs ICP PYME)
  - Supports single month, multiple months, or custom date range
  - **Output**: Terminal (markdown tables) + CSV export to `tools/outputs/smb_mql_funnel_*.csv`
  - **CSV Filenames**: `smb_mql_funnel_YYYYMMDD_YYYYMMDD.csv` (single period) or `smb_mql_funnel_YYYYMM_YYYYMM.csv` (multi-month)
  - **Edge Cases & Data Quality Notes**:
    - Scripts use API-based queries which are the **source of truth** for contact counts
    - CSV exports from HubSpot may have filters that exclude edge cases:
      - Contacts without owners (usually exceptions, but valid contacts)
      - Contacts without lifecycle stages
      - Contacts with lead status internal IDs vs display names
    - **API results are authoritative** - if comparing with CSV exports, expect small discrepancies due to export filtering
    - Edge cases are tracked and reported in script output for transparency

#### Other Analysis Scripts
- **Cycle Time:** `time_to_contact_analysis_nov_2025.py` - Time to first contact analysis
- **Conversion Rates:** `hubspot_conversion_analysis.py` - Comprehensive conversion analysis
- **ICP Operador Billing:** `analyze_icp_operador_billing.py` - Analyzes closed deals to determine "who we bill" (Accountant billing)

### Data Fetching Scripts
- `fetch_unengaged_contacts.py` - Fetch unengaged contacts
- `fetch_hubspot_deals_with_company.py` - Fetch deals with company associations
- `get_hubspot_owners.py` - Fetch HubSpot owners

### Reconciliation & Billing Mapping
- **build_facturacion_hubspot_mapping.py** - Builds `facturacion_hubspot.db` from billing CSV + HubSpot API
  - **Full build:** Loads facturacion.csv, fetches companies by CUIT, fetches deals by id_empresa. Logs to `hubspot_refresh_logs` (period=full).
  - **Refresh deals only:** `--refresh-deals-only --year YYYY --month M` — updates deals for a given month
  - **Fetch wrong stage:** `--fetch-wrong-stage` — populates `deals_any_stage` for WRONG_STAGE detection (Cerrado Churn, etc.). Fetches deals by id_empresa for Colppy-only + facturacion no deal.
  - **Usage:**
    ```bash
    # Full build (requires facturacion.csv)
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py

    # Refresh deals for a month (for Colppy ↔ HubSpot reconciliation)
    python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py --refresh-deals-only --year 2026 --month 2 --fetch-wrong-stage
    ```
  - See [FACTURACION_COLPPY_RECONCILIATION.md](../../docs/FACTURACION_COLPPY_RECONCILIATION.md), [RECONCILE_REPORT_GROUPS.md](../../docs/RECONCILE_REPORT_GROUPS.md)

- **populate_deal_associations.py** - Fetches deal–company associations from HubSpot and stores them in `deal_associations` table
  - **Prerequisite:** Run `build_facturacion_hubspot_mapping.py` first.
  - **Batch mode:** `--batch` — uses batch API (100 deals/request), ~2–3 min for full refresh. Recommended for full refresh.
  - **Debug mode:** `--debug-batch OFFSET` — fetches one batch at given offset and prints raw API response (for investigating failures).
  - **Incremental:** `--deals 123,456,789` — refresh only specific deal IDs.
  - Logs to `hubspot_deal_associations_refresh_logs` in `facturacion_hubspot.db`.
  - **Usage:**
    ```bash
    # Full refresh (batch mode, recommended)
    python tools/scripts/hubspot/populate_deal_associations.py --batch

    # Individual API (slower, for small sets)
    python tools/scripts/hubspot/populate_deal_associations.py

    # Incremental refresh for specific deals
    python tools/scripts/hubspot/populate_deal_associations.py --deals 123,456,789

    # Debug batch API response
    python tools/scripts/hubspot/populate_deal_associations.py --debug-batch 0
    ```

- **fix_deal_associations.py** - Fixes deal–company associations (NO_PRIMARY, billing not primary, accountant missing type 8)
  - **Group 1:** Missing billing company → add PRIMARY. Uses facturacion.csv (billing) or `--colppy-db` (Colppy DB CUIT) for deals not in billing.
  - **Group 2:** Billing associated but not PRIMARY → add PRIMARY.
  - **Group 3:** Accountant company matches customer_cuit but not associated → add type 8 (Estudio Contable).
  - **Colppy DB mode:** `--colppy-db --year YYYY --month M` — uses `colppy_export.db` for CUIT mapping; fixes NO_PRIMARY deals even when not in billing.
  - **Usage:**
    ```bash
    # Group 1 with billing (facturacion.csv)
    python tools/scripts/hubspot/fix_deal_associations.py --group 1 --batch 5 --dry-run

    # Group 1 with Colppy DB (fixes NO_PRIMARY deals not in billing)
    python tools/scripts/hubspot/fix_deal_associations.py --group 1 --colppy-db --year 2026 --month 2 --dry-run

    # Group 2: billing not PRIMARY
    python tools/scripts/hubspot/fix_deal_associations.py --group 2 --batch 10

    # Fix label (type 11 → 8 for accountant)
    python tools/scripts/hubspot/fix_deal_associations.py --fix-label 9424153860 9019047084 --remove 11 --add 8
    ```
  - See [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](../../docs/HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md)

### Data Management & Fixing Scripts
- **Fix Close Date from History:** `fix_close_date_from_history.py` - Fixes deal close dates by finding the earliest close date from property history
  - Retrieves property history for deals to find when they were first closed
  - Useful for fixing deals where close date was updated incorrectly
  - Supports single company/deal or bulk processing via CSV
  - **Usage:**
    ```bash
    # Process a single company
    python fix_close_date_from_history.py --company-id 17655187038
    
    # Process a single deal
    python fix_close_date_from_history.py --deal-id 15583212916
    
    # Process from CSV (with company_id or deal_id columns)
    python fix_close_date_from_history.py --csv input.csv
    
    # Apply updates (default is dry run)
    python fix_close_date_from_history.py --csv input.csv --update
    
    # Save results to CSV
    python fix_close_date_from_history.py --csv input.csv --output results.csv
    ```
  - **CSV Format:** CSV should contain `company_id` column (fetches all deals) or `deal_id` column (processes specific deals), or both
  - **Output:** CSV with columns: `deal_id`, `deal_name`, `status`, `old_date`, `new_date`, `old_date_only`, `new_date_only`, `message`

- **Classify Deal Age from History:** `classify_deal_age_from_history.py` - Distinguishes fresh closes vs old deals with date corrections
  - Fetches createdate, closedate, dealstage history from HubSpot API
  - Classifies: **fresh_close** (created and closed in same period), **old_deal_date_correction** (first closed long ago, closedate updated later), **slow_close** (created long ago, first closed in period)
  - **Usage:**
    ```bash
    # Deals from facturacion_hubspot.db for a month
    python classify_deal_age_from_history.py --year 2026 --month 2

    # Specific deal IDs
    python classify_deal_age_from_history.py --deal-ids 13424641957

    # Export to CSV
    python classify_deal_age_from_history.py --year 2026 --month 2 --output results.csv
    ```
  - See [FACTURACION_COLPPY_RECONCILIATION.md](../../docs/FACTURACION_COLPPY_RECONCILIATION.md#deal-age-classification-fresh-vs-old-deal)

### Visualization & Reporting
- `generate_visualization_report.py` - Generates HTML reports with charts and visualizations

### Workflow Custom Codes (JavaScript)
All workflow custom codes are in the `custom_code/` directory. These are JavaScript files designed to run in HubSpot's workflow automation system.

See **[HUBSPOT_CUSTOM_CODE_WORKFLOW_MAPPING.md](../../docs/HUBSPOT_CUSTOM_CODE_WORKFLOW_MAPPING.md)** for complete workflow documentation.

---

## 🚀 Quick Start

### Running Analysis Scripts

#### High Score Sales Handling Analysis (Recommended)
```bash
# Current month-to-date
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --current-mtd

# Specific month
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --month 2025-12

# Custom date range
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --start-date 2025-12-01 --end-date 2025-12-20
```

#### PQL Analysis Scripts
```bash
# PQL → SQL → Deal Relationship Analysis (PRIMARY)
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month 2025-11
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month-mtd 2025-12
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --start-date 2025-11-01 --end-date 2025-11-30

# SQL/PQL Timing Analysis
python tools/scripts/hubspot/sql_pql_conversion_analysis.py --month 2025-11

# Deal-Focused PQL Analysis
python tools/scripts/hubspot/deal_focused_pql_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
```

#### Funnel Analysis Scripts
```bash
# Accountant MQL Funnel Analysis
python tools/scripts/hubspot/analyze_accountant_mql_funnel.py --month 2025-12
python tools/scripts/hubspot/analyze_accountant_mql_funnel.py --months 2025-11 2025-12
python tools/scripts/hubspot/analyze_accountant_mql_funnel.py --start-date 2025-12-01 --end-date 2026-01-01

# SMB MQL Funnel Analysis
python tools/scripts/hubspot/analyze_smb_mql_funnel.py --month 2025-12
python tools/scripts/hubspot/analyze_smb_mql_funnel.py --months 2025-11 2025-12
python tools/scripts/hubspot/analyze_smb_mql_funnel.py --start-date 2025-12-01 --end-date 2026-01-01
```

#### Other Analysis Scripts
```bash
# MTD Scoring Analysis
python tools/scripts/hubspot/mtd_scoring_full_pagination.py --month-mtd 2025-12

# Uncontacted Lead Status Analysis
python tools/scripts/hubspot/analyze_uncontacted_lead_status.py --compare-months

# Owner Status Check
python tools/scripts/hubspot/check_owner_status.py

# Generate Visualization Report
python tools/scripts/hubspot/generate_visualization_report.py
```

#### Data Management & Fixing Scripts
```bash
# Populate deal associations (full refresh, batch mode)
python tools/scripts/hubspot/populate_deal_associations.py --batch

# Fix deal associations (NO_PRIMARY, billing not primary)
python tools/scripts/hubspot/fix_deal_associations.py --group 1 --colppy-db --year 2026 --month 2 --dry-run
python tools/scripts/hubspot/fix_deal_associations.py --group 2 --batch 10

# Fix close date for a single company
python tools/scripts/hubspot/fix_close_date_from_history.py --company-id 17655187038

# Fix close date for a single deal
python tools/scripts/hubspot/fix_close_date_from_history.py --deal-id 15583212916

# Process from CSV (dry run)
python tools/scripts/hubspot/fix_close_date_from_history.py --csv input.csv --output results.csv

# Process from CSV and apply updates
python tools/scripts/hubspot/fix_close_date_from_history.py --csv input.csv --update --output results.csv
```

### Using Workflow Custom Codes

1. Navigate to HubSpot Workflows
2. Open the workflow containing the custom code action
3. Copy the JavaScript code from the corresponding file in `workflows/`
4. Paste into HubSpot's custom code editor
5. Save and test

---

## 🔄 Recent Changes

**2026-02-12:**
- ✅ **populate_deal_associations.py** – Batch API hardening and debug tool
  - `--batch`: Uses batch API (100 deals/request); ~2–3 min for full refresh
  - `--debug-batch OFFSET`: Inspect raw API response for a specific batch (investigating failures)
  - Null checks in batch response parsing (fixes `'NoneType' object has no attribute 'get'` when API returns null)
  - Logs to `hubspot_deal_associations_refresh_logs`
- ✅ **fix_deal_associations.py** – `--colppy-db` mode for NO_PRIMARY deals
  - `--colppy-db --year YYYY --month M`: Uses Colppy DB CUIT instead of facturacion; fixes NO_PRIMARY deals not in billing
  - `--colppy-db-path`: Override path to colppy_export.db
- ✅ **Refresh logging** – All refresh operations now log timestamps
  - `hubspot_deal_associations_refresh_logs` (populate_deal_associations)
  - `colppy_export_refresh_logs` (export_colppy_to_sqlite)
  - `hubspot_refresh_logs` (build_facturacion_hubspot_mapping full build)

**2026-02-16:**
- ✅ **fix_deal_associations.py** – Group 4 (accountant missing type 8), redundant type 8 removal fix
  - Group 4: Adds type 8 to non-primary Cuenta Contador companies that have only 341
  - `--remove-redundant-type8`: Removes type 8 when same company has both Primary and Estudio Contable (no longer requires company in `companies` table)
- ✅ **MRR_DASHBOARD_DEFINITIONS.md** – New team-shareable doc with dashboard formulas and definitions

**2026-01-26:**
- ✅ PQL script rate limit improvements (`pql_sql_deal_relationship_analysis.py`)
  - `HUBSPOT_RATE_LIMIT_DELAY` default 0,5 s; `HUBSPOT_INITIAL_DELAY` 1,0 s for first 5 requests
  - Delay before first request to avoid burst 429; configurable via `.env`
- ✅ Funnel scripts SQL validation relaxed (accountant, SMB): SQL = contact with at least one deal associated (any deal)
- ✅ Scoring study: `high_score_sales_handling_analysis.py` supports multi-month runs for agent-by-agent comparison

**2025-12-30:**
- ✅ Added `fix_close_date_from_history.py` - **DATA FIXING SCRIPT** for correcting deal close dates
  - Retrieves property history to find earliest close date when deal was first won
  - Supports single company/deal processing or bulk CSV processing
  - Includes dry-run mode and CSV output for results tracking
  - Useful for fixing deals where close date was incorrectly updated

**2025-12-26:**
- ✅ Documented edge cases and CSV export discrepancies for funnel analysis scripts
  - API-based queries are the source of truth for contact counts
  - CSV exports may exclude edge cases (contacts without owners, lifecycle stages, etc.)
  - Edge cases are tracked and reported in script output
  - **Note**: Contacts without owners are exceptions but valid contacts
- ✅ Added `HUBSPOT_FUNNEL_CONTACT_TO_DEAL_METHODOLOGY.md` documentation
  - How HubSpot builds funnels from Contact Created to Deal Created
  - Fields and objects used: `createdate`, lifecycle stages, `hs_v2_date_entered_opportunity`, associations
  - How contacts are traced to deals via Contact-Deal associations
  - Comparison with our script methodology

**2025-12-24:**
- ✅ Added `analyze_accountant_mql_funnel.py` - **ACCOUNTANT CHANNEL FUNNEL ANALYSIS**
  - **STRICT FUNNEL PATH**: MQL Contador → Deal Created → Deal Closed Won
  - SQL metrics shown as informational only (not part of strict funnel)
  - SQL validation with deal association requirement
  - ICP Operador vs ICP PYME classification
  - Edge case tracking and deep investigation
  - CSV export to `tools/outputs/accountant_mql_funnel_*.csv` with date-based filenames
  - Supports single month, multiple months, or custom date range
  - Terminal output with markdown tables + CSV export
- ✅ Added `analyze_smb_mql_funnel.py` - **SMB CHANNEL FUNNEL ANALYSIS**
  - **STRICT FUNNEL PATH**: MQL PYME → Deal Created → Deal Closed Won
  - SQL metrics shown as informational only (not part of strict funnel)
  - Same structure as accountant funnel but for SMB contacts (NOT accountant role)
  - CSV export to `tools/outputs/smb_mql_funnel_*.csv` with date-based filenames
  - Supports single month, multiple months, or custom date range
  - Terminal output with markdown tables + CSV export

**2025-12-20:**
- ✅ Added `pql_sql_deal_relationship_analysis.py` - **PRIMARY PQL ANALYSIS SCRIPT** - Comprehensive PQL → SQL → Deal relationship analysis
  - Funnel analysis: Total Contacts → PQL → SQL (Deal Creation) → Deal Close
  - PQL vs Non-PQL comparison with deal creation rates
  - Timing analysis and customer journey paths
  - Supports full month and month-to-date analysis
  - **Key Assumption:** SQL = Deal Creation (hs_v2_date_entered_opportunity)
- ✅ Added `high_score_sales_handling_analysis.py` - Main script for scoring and contactability analysis
- ✅ Added `analyze_uncontacted_lead_status.py` - Lead Status analysis for uncontacted contacts
- ✅ Added `check_owner_status.py` and `compare_owner_status_months.py` - Owner status tracking
- ✅ Added `generate_visualization_report.py` - HTML report generation with charts
- ✅ Updated all scripts to automatically exclude inactive owners
- ✅ Added `hs_lead_status` field to contact exports
- ✅ Created `owner_utils.py` - Centralized owner name and status fetching


**2025-01-27:**
- ✅ Moved all HubSpot custom code workflow files to `workflows/` subdirectory
- ✅ Removed 5 duplicate scripts
- ✅ Created `utils/` directory for shared utilities
- ✅ Updated documentation with new file paths

---

## 📊 Output Formatting Standards

**IMPORTANT:** All tabular data output must be formatted as **Markdown tables** for proper display in the chatbot interface.

### Markdown Table Format Requirements

1. **Table Syntax:**
   ```markdown
   | Column 1 | Column 2 | Column 3 |
   |----------|----------|----------|
   | Value 1   | Value 2   | Value 3   |
   ```

2. **Header Row:** Always include a header row with column names
3. **Separator Row:** Use `|----------|` or `|:--------:|` for alignment
4. **Alignment:** Use `:---` (left), `---:` (right), or `:---:` (center) for column alignment
5. **No ASCII Art:** Do not use ASCII art tables (┌─┐│└┘ characters) - use standard markdown syntax only

### Example

**✅ Correct (Markdown Table):**
```markdown
| Metric | Value | % of Total |
|--------|-------|------------|
| Total Contacts | 1,175 | 100.0% |
| PQL Contacts | 45 | 3.8% |
```

**❌ Incorrect (ASCII Art):**
```
┌─────────────┬─────────┬────────────┐
│ Metric      │ Value   │ % of Total │
├─────────────┼─────────┼────────────┤
│ Total       │ 1,175   │ 100.0%     │
└─────────────┴─────────┴────────────┘
```

### When to Use Markdown Tables

- All analysis results with multiple rows/columns
- Comparison tables (month-over-month, score ranges, etc.)
- Summary statistics
- Distribution tables
- Any tabular data displayed in chatbot responses

### Script Output

- Scripts that print to console should use markdown table format
- CSV/Excel exports can remain in their native format
- When displaying results in chatbot, always convert to markdown tables

---

## 📝 Notes

- All scripts require `HUBSPOT_API_KEY` environment variable
- Workflow custom codes require `ColppyCRMAutomations` environment variable in HubSpot
- Most scripts support command-line arguments for date ranges
- Output files are saved to `tools/outputs/` directory
- **All tabular output must use markdown table format for chatbot display**
- **Data Quality**: API-based queries are authoritative. CSV exports may exclude edge cases (contacts without owners, lifecycle stages, etc.). These are exceptions but valid contacts.

---

**For detailed documentation, see the docs in `tools/docs/`**

