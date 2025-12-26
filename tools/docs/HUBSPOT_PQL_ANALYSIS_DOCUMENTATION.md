# PQL (Product Qualified Lead) Analysis - Complete Documentation

**Last Updated:** 2025-12-20  
**Purpose:** Comprehensive documentation of all PQL analysis scripts and methodologies

---

## 📋 Overview

This document describes all scripts used for analyzing Product Qualified Leads (PQL) and their relationship with SQL (Sales Qualified Leads) and deal creation. PQL analysis helps understand:

1. **PQL Effectiveness:** How PQLs convert to SQL (deal creation) compared to non-PQLs
2. **Deal Creation Impact:** Whether PQLs create more deals than non-PQLs
3. **Deal Close Rates:** Whether PQLs have higher deal win rates
4. **Timing Relationships:** When PQL occurs relative to SQL and deal creation
5. **Customer Journey:** Different paths contacts take (PQL → SQL → Deal, PQL → Deal direct, etc.)

---

## 🔑 Key Definitions

### PQL (Product Qualified Lead)
- **Field:** `activo = 'true'` (boolean flag)
- **Date Field:** `fecha_activo` (date-only string 'YYYY-MM-DD', no time component)
- **Definition:** Contact that activated in the product during trial
- **Logic:** `contact['activo'] == 'true'` AND `fecha_activo` is populated
- **Cycle Time Note:** When calculating PQL cycle time (`fecha_activo - createdate`), if both dates are on the same calendar day, cycle time = 0.0 days (same day conversion). This is because `fecha_activo` defaults to 00:00:00 when parsed, while `createdate` has a full timestamp.

### SQL (Sales Qualified Lead) = Deal Creation (Validated)
- **Field:** `hs_v2_date_entered_opportunity` (datetime, not null)
- **Definition:** Contact that entered 'Oportunidad' lifecycle stage **with validated deal association**
- **Key Assumption:** **SQL = Deal Creation** - When a contact becomes SQL, a deal is created
- **NEW VALIDATION REQUIREMENT:** Contact must have a deal associated that was created between `createdate` and SQL date (within the analysis period)
- **Logic:** `sql_date is not None` (where `sql_date = hs_v2_date_entered_opportunity`) **AND** contact has validated deal association

### Deal Close (Won)
- **Field:** `dealstage = 'closedwon'` or specific won stage ID
- **Definition:** Deal associated with contact that was won
- **Note:** Currently measured separately, not included in main PQL vs Non-PQL comparison

---

## 📊 PQL Analysis Scripts

### 1. PQL → SQL → Deal Relationship Analysis ⭐ **PRIMARY SCRIPT**

**File:** `tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py`

**Purpose:** Comprehensive analysis of how PQL affects SQL (deal creation) and deal close rates.

**Key Features:**
- **Funnel Analysis:** Total Contacts → PQL → SQL (Deal Creation) → Deal Close
- **PQL vs Non-PQL Comparison:** Deal creation rates, advantages, revenue
- **Timing Analysis:** PQL before/after SQL, deal timing relative to PQL
- **Customer Journey Paths:** PQL → SQL → Deal, PQL → Deal (direct), SQL → Deal (no PQL), etc.
- **Monthly Comparison:** Supports full month and month-to-date analysis

**Usage:**
```bash
# Full month analysis
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month 2025-11

# Month-to-date analysis
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month-mtd 2025-12

# Custom date range
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
```

**Output Metrics:**
- PQL Deal Creation Rate: % of PQLs that became SQL (created deals)
- Non-PQL Deal Creation Rate: % of non-PQLs that became SQL (created deals)
- PQL Advantage: Difference in percentage points
- Funnel stages with conversion rates and drop-offs
- Timing analysis (days between PQL and SQL)

**Key Assumptions:**
1. **SQL = Deal Creation:** When contact enters 'Oportunidad' stage, deal is created
2. **Cohort:** Contacts created in the period (measures conversion for contacts created in period)
3. **No Temporal Filtering:** Counts any SQL conversion, regardless of when it occurred

**Example Output (September 2025):**
```
PQL Deal Creation Rate: 37.8% (14 of 37 PQLs)
Non-PQL Deal Creation Rate: 7.4% (53 of 720 non-PQLs)
PQL Advantage: +30.5 percentage points
```

---

### 2. SQL/PQL Timing Analysis

**File:** `tools/scripts/hubspot/sql_pql_conversion_analysis.py`

**Purpose:** Analyzes SQL contacts to determine if they were PQL before or after SQL conversion.

**Key Features:**
- PQL timing relative to SQL (before/after)
- Days between PQL and SQL conversion
- Cohort: Contacts CREATED AND converted to SQL in the same period

**Usage:**
```bash
python tools/scripts/hubspot/sql_pql_conversion_analysis.py --month 2025-11
python tools/scripts/hubspot/sql_pql_conversion_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
```

**Output Metrics:**
- PQL BEFORE SQL: Count and percentage
- PQL AFTER SQL: Count and percentage
- NEVER PQL: Count and percentage
- Average days between PQL and SQL

**Key Difference from Primary Script:**
- This script focuses on SQL contacts and their PQL timing
- Primary script focuses on all contacts and their conversion paths

---

### 3. Deal-Focused PQL Analysis

**File:** `tools/scripts/hubspot/deal_focused_pql_analysis.py`

**Purpose:** Analyzes PQL effectiveness based on actual deal wins and revenue, not lifecycle stage changes.

**Key Features:**
- Deal attachment rates (PQL vs Non-PQL)
- Deal win rates
- Revenue per contact
- Sales velocity metrics

**Usage:**
```bash
python tools/scripts/hubspot/deal_focused_pql_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
```

**Output Metrics:**
- Deal Attachment Rate: % of contacts with associated deals
- Deal Win Rate: % of contacts with won deals
- Revenue per Contact: Average revenue generated
- Total Revenue: Sum of won deal amounts

---

### 4. Monthly PQL Reporting

**File:** `tools/scripts/hubspot/monthly_pql_analysis.py`

**Purpose:** Monthly PQL reporting and trend analysis.

**Usage:**
```bash
python tools/scripts/hubspot/monthly_pql_analysis.py
```

---

## 📈 Measurement Methodology

### PQL Deal Creation Rate

**Formula:**
```
PQL Deal Creation Rate = (PQLs that became SQL) / (Total PQLs) × 100
```

**Example (September 2025):**
- PQLs that became SQL: 14 contacts
- Total PQLs: 37 contacts
- Calculation: (14 / 37) × 100 = 37.8%

**What it measures:**
- Of all PQL contacts created in the period, what percentage eventually created deals (became SQL)
- **Does NOT consider:** Whether the deal was won (only measures deal creation)

### Non-PQL Deal Creation Rate

**Formula:**
```
Non-PQL Deal Creation Rate = (Non-PQLs that became SQL) / (Total Non-PQLs) × 100
```

**Example (September 2025):**
- Non-PQLs that became SQL: 53 contacts
- Total Non-PQLs: 720 contacts (757 total - 37 PQLs)
- Calculation: (53 / 720) × 100 = 7.4%

### PQL Advantage

**Formula:**
```
PQL Advantage = PQL Deal Creation Rate - Non-PQL Deal Creation Rate
```

**Example (September 2025):**
- PQL Deal Creation Rate: 37.8%
- Non-PQL Deal Creation Rate: 7.4%
- PQL Advantage: +30.5 percentage points

**Interpretation:**
- PQLs are 30.5pp more likely to create deals than non-PQLs
- This means PQLs are approximately 5x more likely to create deals (37.8% vs 7.4%)

---

## 📊 Monthly Comparison Results

### Summary Table (September - December 2025)

| Month | Period | Total | PQL | PQL % | SQL | SQL % | PQL→SQL | PQL→SQL % | PQL Adv |
|-------|--------|-------|-----|-------|-----|-------|---------|-----------|---------|
| **September 2025** | Full Month | 757 | 37 | 4.9% | 67 | 8.9% | 14 | 37.8% | +30.5pp |
| **October 2025** | Full Month | 552 | 44 | 8.0% | 61 | 11.1% | 7 | 15.9% | +5.3pp |
| **November 2025** | Full Month | 1,175 | 45 | 3.8% | 42 | 3.6% | 11 | 24.4% | +21.7pp |
| **December 2025** | Month-to-Date (1-20) | 1,256 | 29 | 2.3% | 32 | 2.5% | 4 | 13.8% | +11.5pp |

### Key Insights

1. **September:** Strongest PQL → SQL conversion (37.8%) and highest advantage (+30.5pp)
2. **October:** Lowest PQL advantage (+5.3pp) due to higher non-PQL SQL rate (10.6%)
3. **November:** Strong performance (24.4% PQL → SQL, +21.7pp advantage)
4. **December (partial):** Moderate performance (13.8% PQL → SQL, +11.5pp advantage)

**Average (Full Months):**
- Average PQL → SQL Conversion: 26.0%
- Average PQL Advantage: +19.2 percentage points

---

## ⚠️ Important Notes

### What We Measure

✅ **Deal Creation (SQL Conversion):**
- When contact becomes SQL (enters 'Oportunidad' stage)
- This is our proxy for deal creation
- Field: `hs_v2_date_entered_opportunity`

❌ **Deal Close/Win (Currently NOT in Main Comparison):**
- Deal win rate is shown separately in Stage 4 of funnel
- Not included in PQL vs Non-PQL comparison table
- Can be added if needed

### Cohort Definition

- **Base Cohort:** Contacts CREATED in the period
- **Measures:** Conversion rates for contacts created in the period
- **No Temporal Filtering:** Counts any SQL conversion, regardless of when it occurred relative to contact creation

### Exclusions

- **"Usuario Invitado" contacts:** Automatically excluded at API query level
- **Inactive owners:** Filtered out in owner performance analysis

---

## 🔄 Script Relationships

```
pql_sql_deal_relationship_analysis.py (PRIMARY)
    ├─ Comprehensive PQL → SQL → Deal analysis
    ├─ Funnel visualization
    ├─ PQL vs Non-PQL comparison
    └─ Monthly comparison support

sql_pql_conversion_analysis.py
    ├─ SQL-focused analysis
    ├─ PQL timing relative to SQL
    └─ Cohort: Created AND converted in period

deal_focused_pql_analysis.py
    ├─ Deal-focused metrics
    ├─ Revenue analysis
    └─ Win rate analysis

monthly_pql_analysis.py
    └─ Monthly reporting and trends
```

---

## 📝 Usage Recommendations

### For Comprehensive Analysis
**Use:** `pql_sql_deal_relationship_analysis.py`
- Best for understanding overall PQL effectiveness
- Provides complete funnel view
- Supports monthly comparisons

### For SQL-Focused Analysis
**Use:** `sql_pql_conversion_analysis.py`
- Best for understanding SQL contacts and their PQL history
- Focuses on timing relationships

### For Revenue Analysis
**Use:** `deal_focused_pql_analysis.py`
- Best for understanding revenue impact
- Focuses on actual deal wins and revenue

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
- Comparison tables (month-over-month, PQL vs Non-PQL, etc.)
- Summary statistics
- Funnel analysis tables
- Deal conversion tables
- Any tabular data displayed in chatbot responses

### Script Output Guidelines

- Scripts that print to console should use markdown table format
- CSV/Excel exports can remain in their native format
- When displaying results in chatbot, always convert to markdown tables
- Python scripts generating output should format as markdown tables for chatbot display

---

## 🔗 Related Documentation

- **[HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md](./HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md)** - Scoring and contactability analysis
- **[HUBSPOT_SCRIPTS_DOCUMENTATION.md](./HUBSPOT_SCRIPTS_DOCUMENTATION.md)** - Complete scripts documentation
- **[SQL_PQL_ANALYSIS_README.md](./SQL_PQL_ANALYSIS_README.md)** - SQL/PQL correlation analysis

---

**Last Updated:** 2025-12-20

