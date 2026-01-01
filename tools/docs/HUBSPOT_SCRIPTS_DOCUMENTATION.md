# HubSpot Scripts Documentation

**Last Updated:** 2025-12-21  
**Purpose:** Complete documentation of all HubSpot analysis scripts and their usage

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Directory Structure](#directory-structure)
3. [Script Documentation](#script-documentation)
4. [Quick Reference](#quick-reference)
5. [Dependencies](#dependencies)

---

## 📚 Specialized Documentation

For detailed documentation on specific analysis types, see:

- **[HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md](./HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md)** - **NEW** Complete PQL analysis documentation
  - PQL → SQL → Deal relationship analysis (PRIMARY SCRIPT)
  - SQL/PQL timing analysis
  - Deal-focused PQL analysis
  - Measurement methodology and monthly comparisons
  
- **[HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md](./HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md)** - Complete guide to scoring and contactability analysis scripts
  - High Score Sales Handling Analysis
  - Lead Status Analysis
  - Owner Performance Tracking
  - Visualization Reports

---

## Overview

This directory contains HubSpot analysis scripts for CRM data analysis. The scripts cover:
- **Lead Scoring Analysis** (MTD scoring by `fit_score_contador`)
- **Contactability Analysis** (Contact rates, time to contact, owner performance) - **See [HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md](./HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md)**
- **SQL/PQL Conversion Analysis** (Sales and Product Qualified Leads)
- **Cycle Time Analysis** (Time to contact, time to conversion)
- **Monthly Reporting** (PQL rates, conversion metrics)
- **Period Comparisons** (April vs May, month-over-month)
- **Data Fetching** (Contacts, deals, owners)
- **Data Management** (Company identification, associations, enrichment)
- **Owner Status Tracking** (Active/inactive owner monitoring)

---

## Directory Structure

```
tools/scripts/hubspot/
├── analysis/              # Analysis scripts (engaged/unengaged contacts)
│   └── unengaged_contacts_analysis.py
├── data_management/       # Data management utilities
│   ├── hubspot_hybrid_identifier_implementation.py
│   ├── hubspot_list_contactability_analysis.py
│   ├── hubspot_lists_api_working.py
│   ├── switch_primary_company.py
│   └── update_companies_via_deals.py
├── archive/               # Archived specific use case scripts
│   ├── make_accountant_primary.py
│   ├── preview_referencia_updates.py
│   ├── update_referencia_empresa_primaries.py
│   └── update_single_deal.py
├── workflows/             # HubSpot custom code workflows (JavaScript)
│   ├── hubspot_first_deal_won_calculations.js
│   ├── hubspot_accountant_channel_deal_workflow.js
│   ├── hubspot_additional_product_created.js
│   ├── hubspot_company_blank_field_validator.js
│   └── hubspot_deal_stage_update_workflow.js
├── utils/                 # Shared utilities
│   ├── datetime_utils.py
│   └── constants.py
└── [main analysis scripts]
```

**Note:** HubSpot custom code workflow files (JavaScript) are located in `workflows/` subdirectory. See `HUBSPOT_CUSTOM_CODE_WORKFLOW_MAPPING.md` for workflow documentation.

---

## Script Documentation

### High Score Sales Handling Analysis ⭐ **PRIMARY SCRIPT**

#### `high_score_sales_handling_analysis.py`

**Purpose:** Main script for analyzing scoring and contactability of high-score (40+) contacts.

**Key Features:**
- Contactability analysis (contact rates, time to contact)
- Owner performance metrics
- SQL/PQL conversion tracking
- Uncontacted contacts identification
- Automatic exclusion of inactive owners and "Usuario Invitado" contacts

**For complete documentation, see:** [HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md](./HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md)

**Quick Usage:**
```bash
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --current-mtd
```

---

### MTD Scoring Analysis

#### `mtd_scoring_full_pagination.py`
**Purpose:** Month-to-date scoring analysis using `fit_score_contador` field for October vs November 2025 comparison.

**Key Features:**
- Uses `fit_score_contador` field only
- Automatically finds all pages using `find_all_pages_for_period()`
- Full pagination coverage (100% data)
- Analyzes SQL and PQL conversion rates by score range
- Calculates cycle times by score range
  - **PQL Cycle Time**: Handles same-day conversions correctly (fecha_activo is date-only, createdate has timestamp)
- Saves results to CSV

**Metrics Calculated:**
- Total contacts by score range (40+, 30-39, 20-29, 10-19, 0-9)
- SQL conversion rate by score range
- PQL conversion rate by score range
- Average cycle time (days) by score range
  - **Note**: PQL cycle time uses same-day handling (0.0 days if fecha_activo and createdate are on same calendar day)

**Output Files:**
- `oct_mtd_scoring_fit_score_contador_FULL.csv`
- `nov_mtd_scoring_fit_score_contador_FULL.csv`

---

### PQL (Product Qualified Lead) Analysis ⭐ **NEW**

#### `pql_sql_deal_relationship_analysis.py` ⭐ **PRIMARY PQL SCRIPT**
**Purpose:** Comprehensive analysis of how PQL affects SQL (deal creation) and deal close rates.

**Key Features:**
- **Funnel Analysis:** Total Contacts → PQL → SQL (Deal Creation) → Deal Close
- **PQL vs Non-PQL Comparison:** Deal creation rates, advantages, revenue metrics
- **Timing Analysis:** PQL before/after SQL, deal timing relative to PQL
- **Customer Journey Paths:** Multiple conversion paths analysis
- **Monthly Comparison:** Supports full month and month-to-date analysis
- **Key Assumption:** SQL = Deal Creation (when contact enters 'Oportunidad' stage, deal is created)

**PQL Definition:**
- `activo = 'true'` (boolean flag)
- `fecha_activo` (timestamp when activation occurred)

**SQL Definition (Deal Creation):**
- `hs_v2_date_entered_opportunity` (when contact entered 'Oportunidad' stage)
- **Assumption:** SQL conversion = Deal creation

**Output Metrics:**
- PQL Deal Creation Rate: % of PQLs that became SQL
- Non-PQL Deal Creation Rate: % of non-PQLs that became SQL
- PQL Advantage: Difference in percentage points
- Funnel stages with conversion rates
- Timing analysis (days between PQL and SQL)

**Usage:**
```bash
# Full month analysis
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month 2025-11

# Month-to-date analysis
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month-mtd 2025-12

# Custom date range
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
```

**Output Files:**
- `pql_sql_deal_relationship_{period}_{timestamp}.csv` - Detailed contact-level data

**For complete documentation, see:** [HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md](./HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md)

---

### SQL/PQL Conversion Analysis

#### `sql_pql_conversion_analysis.py`
**Purpose:** Analyzes SQL contacts to determine if they were PQL before or after SQL conversion.

**Key Features:**
- Fetches data directly from HubSpot API (standalone)
- Analyzes SQL → PQL timing relationship
- Supports command-line arguments (`--month`, `--start-date`, `--end-date`)
- Comprehensive cohort definition (created AND converted in period)
- Saves detailed CSV and summary JSON

**SQL Definition (Updated - with Deal Validation):**
- Contact that converted to Opportunity (entered 'Oportunidad' lifecycle stage)
- Field: `hs_v2_date_entered_opportunity`
- **NEW REQUIREMENT**: Contact must have a deal associated that was created between `createdate` and SQL date (within the analysis period)
- **Validation**: SQL = MQL + `hs_v2_date_entered_opportunity` in period + deal created between contact creation and SQL date (within period)

**PQL Definition:**
- Contact that activated during trial
- Fields: `activo = 'true'`, `fecha_activo` populated

**Cohort Definition (Updated - with Deal Validation):**
- Contacts **CREATED** in period that **ALSO converted to SQL** in same period **with validated deal association**
- Requirements:
  1. `createdate` must be within the specified date range (MQL - excluding 'Usuario Invitado')
  2. `hs_v2_date_entered_opportunity` must be within the same date range
  3. Contact must have a deal associated that was created between `createdate` and SQL date (within the same period)

**Output Files:**
- `sql_pql_analysis_{period}_{timestamp}.csv` - Detailed results
- `sql_pql_analysis_{period}_{timestamp}.json` - Summary with methodology

**Usage:**
```bash
python sql_pql_conversion_analysis.py --month 2025-11
python sql_pql_conversion_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
```

**Key Difference from Primary Script:**
- This script focuses on SQL contacts and their PQL timing
- Primary script focuses on all contacts and their conversion paths

---

#### `analyze_sql_pql_from_mcp.py`
**Purpose:** Analyze SQL → PQL timing relationship from MCP tool data.

**Key Features:**
- Analyzes contacts fetched via MCP HubSpot tools
- Determines if contacts were PQL before or after SQL conversion
- Requires pre-fetched data (doesn't fetch itself)

**Analysis Types:**
- `pql_before_sql` - Activated in product BEFORE sales engagement
- `pql_after_sql` - Activated AFTER sales engagement
- `never_pql` - Never activated
- `pql_no_date` - Data quality issue (marked PQL but no date)

---

### Cycle Time Analysis

**Note:** Time-to-contact analysis is included in `high_score_sales_handling_analysis.py`. See [High Score Sales Handling Analysis](#high-score-sales-handling-analysis--primary-script) section above for details.

---

### Monthly PQL Analysis

#### `monthly_pql_analysis.py`
**Purpose:** Standardized monthly PQL analysis with automated reporting.

**Key Features:**
- Uses `deal_focused_pql_analysis` module for data fetching
- Supports multiple analysis modes:
  - Current month-to-date
  - Specific month (`--month 2025-08`)
  - Date range (`--start-date`, `--end-date`)
  - Multi-month comparison (`--months 2025-05,2025-06,2025-07`)
- Output formats: JSON, CSV, or both

**Metrics:**
- Total contacts created
- PQL contacts (`activo = true`)
- PQL rate (PQLs / All Contacts)
- Lifecycle stage breakdown
- Lead status breakdown

**Usage:**
```bash
python monthly_pql_analysis.py  # Current month-to-date
python monthly_pql_analysis.py --month 2025-08
python monthly_pql_analysis.py --months 2025-05,2025-06,2025-07,2025-08
```

---

#### `deal_focused_pql_analysis.py`
**Purpose:** Deal-focused PQL analysis based on actual deal wins and revenue.

**Key Features:**
- Analyzes PQL effectiveness based on deals (not lifecycle stages)
- Fetches contacts with deal associations
- Used by `monthly_pql_analysis.py` as a module

**Metrics:**
- Deal Attachment Rate: % of contacts associated with deals
- Deal Win Rate: % of contacts with won deals
- Revenue per Contact: Average revenue per contact segment
- Sales Velocity: Time from contact → deal → win

**PQL Definition:**
- `activo = 'true'` (boolean flag)
- `fecha_activo` (activation timestamp)

---

### Conversion Rate Analysis

#### `hubspot_conversion_analysis.py`
**Purpose:** Comprehensive conversion rate analysis for any date range.

**Key Features:**
- Analyzes conversion rates from contacts/leads to deals
- Supports multiple date range formats:
  - `--start-date` and `--end-date`
  - `--month YYYY-MM`
  - `--year` and `--month-num`
- Generates visualizations (matplotlib/seaborn)

**Metrics:**
- Contact to Deal conversion
- Contact to Closed Won conversion
- Deal Win Rate
- Deal Loss Rate
- Average Deal Amount
- Sales Cycle Time

**Output:**
- CSV files with metrics
- Visualization charts (if matplotlib available)
- Detailed console reports

**Usage:**
```bash
python hubspot_conversion_analysis.py --month 2025-05
python hubspot_conversion_analysis.py --start-date 2025-05-01 --end-date 2025-06-01
```

---

### Period Comparison

#### `hubspot_april_may_comparison.py`
**Purpose:** Comprehensive April vs May 2025 conversion comparison.

**Key Features:**
- Loads pre-calculated metrics from CSV files
- Calculates month-over-month changes and growth rates
- Creates comprehensive visualizations:
  - Volume comparison charts
  - Conversion rate comparisons
  - Growth rate analysis
  - Trend visualizations

**Data Sources:**
- `outputs/csv_data/hubspot/hubspot_conversion_metrics_2025_04.csv`
- `outputs/csv_data/hubspot/hubspot_conversion_metrics_2025_05.csv`

---

### Data Fetching Utilities

#### `fetch_unengaged_contacts.py`
**Purpose:** Fetch all unengaged contacts with pagination.

**Key Features:**
- Fetches contacts that were never engaged
- Handles pagination automatically
- Groups contacts by owner
- Generates HubSpot contact links
- Owner mapping included

---

#### `fetch_hubspot_deals_with_company.py`
**Purpose:** Fetch HubSpot deals with company associations.

**Key Features:**
- Fetches deals by date range and deal stage
- Supports filtering by `closedate` or `createdate` (single filter)
- Supports filtering by **BOTH** `createdate` AND `closedate` (for monthly analysis - matches HubSpot report standard)
- Includes company associations
- Captures UTM and campaign properties
- Saves to CSV with company information
- Optional ICP Operador billing analysis (automatically uses both date filters)

**Usage:**
```bash
# Single date filter (closedate or createdate)
python fetch_hubspot_deals_with_company.py --start-date START_DATE --end-date END_DATE --deal-stage DEAL_STAGE [--filter-type closedate|createdate]

# Both date filters (matches HubSpot report standard for monthly analysis)
python fetch_hubspot_deals_with_company.py --start-date START_DATE --end-date END_DATE --deal-stage DEAL_STAGE --filter-both-dates

# Monthly analysis with ICP Operador (automatically uses both date filters)
python fetch_hubspot_deals_with_company.py --month YYYY-MM --deal-stage closedwon --analyze-icp-operador
```

**Examples:**
```bash
# Filter by closed date only
python fetch_hubspot_deals_with_company.py --start-date 2025-12-01 --end-date 2026-01-01 --deal-stage closedwon --filter-type closedate

# Filter by BOTH createdate AND closedate (monthly analysis standard)
python fetch_hubspot_deals_with_company.py --month 2025-12 --deal-stage closedwon --filter-both-dates

# ICP Operador analysis (automatically uses both date filters)
python fetch_hubspot_deals_with_company.py --month 2025-12 --deal-stage closedwon --analyze-icp-operador
```

**⚠️ Important:** For monthly analysis of closed deals, use `--filter-both-dates` to match HubSpot report standard (deals created AND closed in the same month). See [Deal Date Filtering Standard](../README_HUBSPOT_CONFIGURATION.md#deal-date-filtering-standard) for details.

---

#### `analyze_smb_accountant_involved_funnel.py` ⭐ **NEW**
**Purpose:** Analyze SMB funnel comparing deals WITH vs WITHOUT accountant involvement, using dual-criteria detection.

**Key Features:**
- **Dual-Criteria Accountant Detection**: Uses TWO methods to identify accountant involvement:
  - **Method 1 (Formula Field)**: `tiene_cuenta_contador > 0` - Formula field that counts associated accountant companies
  - **Method 2 (Rollup Field Logic)**: Has companies with association type 8 ("Estudio Contable / Asesor / Consultor Externo del negocio") - Rollup field that counts companies with the accountant association label
- **Side-by-Side Comparison**: Generates funnels for both WITH and WITHOUT accountant involvement
- **Overlap Analysis**: Tracks which deals are identified by both methods, only Method 1, or only Method 2
- **Funnel Stages**: Deal Created → Deal Closed Won (starts directly from deals, not MQL/SQL, as accountant referrals often skip traditional paths)
- **ICP Classification**: Classifies closed won deals by ICP Operador vs ICP PYME
- **Revenue Analysis**: Calculates total revenue, ICP Operador revenue, and ICP PYME revenue
- **Visualization**: Creates comprehensive comparison charts showing both funnels side-by-side

**Funnel Logic:**
1. **WITH Accountant**: Deals created in period where EITHER:
   - `tiene_cuenta_contador > 0` (Formula field method), OR
   - Has companies with association type 8 (Rollup field method)
2. **WITHOUT Accountant**: Deals created in period where:
   - `tiene_cuenta_contador = 0` or null, AND
   - Does NOT have companies with association type 8
3. **Contact Filtering**: All deals must have at least one associated contact (all contact types included - SMB, accountant, or no rol_wizard)
4. **Closed Won**: Deals where both `createdate` and `closedate` are in the period

**Usage:**
```bash
# Single month analysis
python tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py --month 2025-12

# Multiple months comparison
python tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py --months 2025-10 2025-11 2025-12

# Custom date range
python tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py --start-date 2025-12-01 --end-date 2026-01-01

# Visualization only (from existing CSV)
python tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py --csv smb_accountant_funnel_comparison_20251201_20260101.csv
```

**Output Files:**
- `smb_accountant_funnel_comparison_{start_date}_{end_date}.csv` - Comparison results with both funnels
- `smb_accountant_funnel_comparison_{start_date}_{end_date}_visualization.png` - Side-by-side comparison charts

**Key Metrics:**
- Deal Created counts (WITH vs WITHOUT)
- Deal Closed Won counts (WITH vs WITHOUT)
- Deal→Won conversion rates (WITH vs WITHOUT)
- Total Revenue (WITH vs WITHOUT)
- ICP Operador vs ICP PYME breakdown
- Overlap analysis between detection methods

**Dual-Criteria Detection Details:**
- **Overlap Tracking**: Shows deals identified by BOTH methods, ONLY by Method 1, or ONLY by Method 2
- **Data Quality Validation**: Helps identify discrepancies between Formula field and Rollup field calculations
- **Comprehensive Coverage**: Ensures all deals with accountant involvement are captured regardless of which method identifies them

**Related Documentation:**
- See README_HUBSPOT_CONFIGURATION.md for accountant company types and deal-company associations
- See association type 8 documentation for Rollup field logic

---

#### `analyze_icp_operador_billing.py`
**Purpose:** Analyze closed deals to determine "who we bill" (ICP Operador = Accountant billing).

**Definition of "ICP Operador" (Accountant Billing):**

**PRIMARY COMPANY METHOD (ONLY RELIABLE METHOD)**:
   - Find the primary company in deal-company associations (Type ID 5)
   - If company type is one of: "Cuenta Contador", "Cuenta Contador y Reseller", "Contador Robado"
   → Then we bill an accountant (ICP Operador)

**⚠️ IMPORTANT:** Plan name method is **NOT reliable** because PYMEs can have "ICP Contador" plans when an accountant refers them, but we still bill the PYME (not the accountant). The only reliable way to determine who we bill is by checking the PRIMARY company type.

**Key Features:**
- Analyzes closed won deals for accountant billing identification
- Uses **ONLY** PRIMARY company type method (only reliable method)
- **Validates data quality** - detects and reports deals without primary company association
- Provides additional information on plan names for reference
- Generates summary statistics and detailed CSV output

**Validations:**
- ✅ Validates that deals have a PRIMARY company association (Type ID 5)
- ⚠️ Reports deals without primary company (these need data quality attention)
- ICP Operador classification is only calculated for deals WITH primary company

**Usage:**
```bash
# By month
python tools/scripts/hubspot/analyze_icp_operador_billing.py --month 2025-12

# By date range
python tools/scripts/hubspot/analyze_icp_operador_billing.py --start-date 2025-12-01 --end-date 2026-01-01
```

**Output Metrics:**
- Total closed deals
- Deals WITH primary company (can be classified)
- Deals WITHOUT primary company ⚠️ (validation issue - cannot be classified)
- ICP Operador count and percentage (billed to accountant) - **based ONLY on PRIMARY company type**
- Non-ICP Operador count and percentage (billed to SMB)
- Additional information (plan names for reference only)

**Example Output:**
```
Total Closed Deals: 24
Deals WITH Primary Company: 22 (91.7%)
Deals WITHOUT Primary Company ⚠️: 2 (8.3%)
ICP Operador (Billed to Accountant): 2 (9.1% of deals with primary company)
Non-ICP Operador (Billed to SMB): 20 (90.9% of deals with primary company)

⚠️ VALIDATION ISSUES: Deals Without Primary Company
- 71031 - POWER PRINT GRAPHIC SOLUTIONS S.R.L. (Deal ID: 51020357538)
- 104676 - FUNDACION ATREVERSE (Deal ID: 51244044435)

Additional Information:
- Deals with 'ICP Contador' plan name: 10 (informational only)
- Accountant companies with non-ICP Contador plan: 2
```

**Related Documentation:**
- See README_HUBSPOT_CONFIGURATION.md for accountant company types and deal-company associations

---

#### `get_hubspot_owners.py`
**Purpose:** Fetch all HubSpot owners (active and archived).

**Key Features:**
- Fetches all active owners
- Fetches all archived owners
- Includes team information
- Saves to JSON and text file formats
- Creates owner mapping table

**Output Files:**
- `hubspot_owners.json` - Full owner data in JSON
- `hubspot_owner_list_updated.txt` - Markdown table format

**Usage:**
```bash
python get_hubspot_owners.py
python get_hubspot_owners.py --api-key YOUR_API_KEY
```

---

### Lead Qualification

#### `lead_qualification_analysis.py`
**Purpose:** Deep dive analysis of lead qualification quality.

**Key Features:**
- Investigates why more contacts generate fewer deals
- Analyzes contact quality differences between periods
- Breakdowns by:
  - Lead source
  - Lifecycle stage
  - Lead status
  - Owner performance
  - Deal attachment rates

**Data Sources:**
- Requires pre-fetched CSV files from `outputs/csv_data/hubspot/`

---

### Analysis Subdirectory

**Note:** `analysis/complete_november_analysis.py` has been moved to `archive/analysis/` as it was hardcoded for November 2025. Its functionality is covered by:
- `high_score_sales_handling_analysis.py` - Time to contact analysis (parametrized)
- `fetch_unengaged_contacts.py` - Unengaged contacts analysis (utility function)

---

#### `analysis/unengaged_contacts_analysis.py`
**Purpose:** Analysis of unengaged contacts from November 2025.

**Key Features:**
- Processes unengaged contacts
- Groups by owner
- Generates reports with HubSpot links

---

### Data Management Utilities

#### `data_management/hubspot_hybrid_identifier_implementation.py`
**Purpose:** Company identification system using both CUIT and normalized names.

**Key Features:**
- Normalizes company names for consistent matching
- Cleans CUIT values
- Hybrid identification approach (CUIT + Name)

---

#### `data_management/hubspot_list_contactability_analysis.py`
**Purpose:** Detailed contactability analysis for HubSpot lists.

**Key Features:**
- Analyzes list contactability
- Company search functionality
- Uses HubSpot Lists API

---

#### `data_management/hubspot_lists_api_working.py`
**Purpose:** Working HubSpot Lists API implementation using direct REST API calls.

**Key Features:**
- Direct REST API calls (beyond MCP tools)
- List details retrieval
- List membership operations
- Comprehensive API client class

---

#### `data_management/switch_primary_company.py`
**Purpose:** Generic primary company switcher for deals.

**Key Features:**
- Switches primary company while preserving ALL associations
- Uses PUT instead of DELETE to avoid losing associations
- Generic, reusable function
- Command-line interface

**Usage:**
```bash
python switch_primary_company.py <deal_id> <new_primary_company_id> [current_primary_company_id]
```

---

#### `data_management/update_companies_via_deals.py`
**Purpose:** Updates companies with CUITs via deal associations.

**Key Features:**
- Gets closed won deals from a period
- Finds associated companies
- Updates missing CUITs from Colppy database
- Integrates HubSpot API with Colppy database

---

## Quick Reference

### Scripts by Purpose

| Purpose | Script |
|---------|--------|
| **MTD Scoring** | `mtd_scoring_full_pagination.py` |
| **SQL/PQL Analysis** | `sql_pql_conversion_analysis.py`, `analyze_sql_pql_from_mcp.py` |
| **Cycle Time** | `high_score_sales_handling_analysis.py` (includes time to contact) |
| **Monthly PQL** | `monthly_pql_analysis.py`, `deal_focused_pql_analysis.py` |
| **Conversion Rates** | `hubspot_conversion_analysis.py` |
| **Period Comparison** | `hubspot_april_may_comparison.py` |
| **Lead Qualification** | `lead_qualification_analysis.py` |
| **Fetch Contacts** | `fetch_unengaged_contacts.py` |
| **Fetch Deals** | `fetch_hubspot_deals_with_company.py` |
| **Fetch Owners** | `get_hubspot_owners.py` |
| **ICP Operador Billing** | `analyze_icp_operador_billing.py` |
| **SMB Accountant Involved Funnel** | `analyze_smb_accountant_involved_funnel.py` |
| **Data Management** | `data_management/*.py` |

### Scripts by Data Source

| Data Source | Scripts |
|------------|---------|
| **HubSpot API Direct** | `sql_pql_conversion_analysis.py`, `hubspot_conversion_analysis.py`, `deal_focused_pql_analysis.py`, `monthly_pql_analysis.py`, `fetch_*` scripts |
| **MCP Tools** | `mtd_scoring_full_pagination.py`, `analyze_sql_pql_from_mcp.py` |
| **Pre-fetched CSV** | `lead_qualification_analysis.py`, `hubspot_april_may_comparison.py` |

### Scripts by Output Format

| Output Format | Scripts |
|---------------|---------|
| **Console Only** | `lead_qualification_analysis.py` |
| **CSV Files** | `mtd_scoring_full_pagination.py`, `sql_pql_conversion_analysis.py`, `fetch_*` scripts |
| **JSON Files** | `sql_pql_conversion_analysis.py`, `get_hubspot_owners.py` |
| **Visualizations** | `hubspot_conversion_analysis.py`, `hubspot_april_may_comparison.py` |

---

## Key Metrics Tracked

### Lead Scoring Metrics
- Score distribution by range (40+, 30-39, 20-29, 10-19, 0-9)
- SQL conversion rate by score range
- PQL conversion rate by score range
- Average cycle time by score range

### Conversion Metrics
- Contact → Deal conversion rate
- Contact → SQL conversion rate
- Contact → PQL conversion rate
- Contact → Closed Won conversion rate
- Deal Win Rate
- Deal Loss Rate

### Cycle Time Metrics
- Time to First Contact (MQL → Contact)
- Time to SQL (Contact → SQL)
- Time to PQL (Contact → PQL)
  - **Same-Day Handling**: `fecha_activo` is date-only (no time), while `createdate` has full timestamp. If both dates are on the same calendar day, cycle time = 0.0 days.
- Sales Cycle Time (Contact → Deal → Win)

### Volume Metrics
- Total contacts created
- Total deals created
- Closed Won deals
- Closed Lost deals
- Unengaged contacts

---

## Dependencies

### Required Python Packages
- `pandas` - Data manipulation
- `numpy` - Numerical operations
- `requests` - API calls
- `python-dotenv` - Environment variable management
- `matplotlib` - Visualizations (optional)
- `seaborn` - Statistical visualizations (optional)
- `pytz` - Timezone handling (for cycle time scripts)

### Environment Variables
- `HUBSPOT_API_KEY` - HubSpot API access token
- `ColppyCRMAutomations` - HubSpot Private App token (for workflow scripts)

---

## Maintenance Notes

### Adding New Scripts

When adding new HubSpot analysis scripts:

1. Add comprehensive docstring with purpose and usage
2. Include command-line argument support for date ranges
3. Use consistent output formats (CSV, JSON, or both)
4. Include error handling and logging
5. Document data sources and dependencies
6. Update this documentation

### Updating Existing Scripts

When updating scripts:

1. Update version/date in docstring
2. Document changes in this file
3. Maintain backward compatibility if possible
4. Test with sample data before production use

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

### Script Output Guidelines

- Scripts that print to console should use markdown table format
- CSV/Excel exports can remain in their native format
- When displaying results in chatbot, always convert to markdown tables
- Python scripts generating output should format as markdown tables for chatbot display

---

**End of Documentation**
