# HubSpot Scoring & Contactability Analysis Documentation

**Last Updated:** 2026-01-26  
**Purpose:** Complete documentation for scoring and contactability analysis scripts

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Main Script: High Score Sales Handling Analysis](#main-script-high-score-sales-handling-analysis)
3. [Supporting Scripts](#supporting-scripts)
4. [Key Metrics Explained](#key-metrics-explained)
5. [Data Filters & Exclusions](#data-filters--exclusions)
6. [Usage Examples](#usage-examples)
7. [Output Files](#output-files)

---

## Overview

The scoring and contactability analysis suite provides comprehensive insights into:
- **Lead Scoring**: Distribution and quality of contacts by score (40+)
- **Contactability**: How quickly and effectively the sales team contacts high-score leads
- **Owner Performance**: Individual sales team member metrics
- **Conversion Tracking**: SQL and PQL conversion rates by owner and score range
- **Lead Quality**: Analysis of contacts without Lead objects

---

## Main Script: High Score Sales Handling Analysis

### `high_score_sales_handling_analysis.py`

**Purpose:** Primary script for analyzing how the sales team handles contacts with score 40+.

#### Key Features

1. **Scoring Analysis**
   - Uses `fit_score_contador` field exclusively
   - Analyzes contacts with score ≥ 40
   - Score distribution and averages

2. **Contactability Analysis**
   - Contact rate by owner
   - Time to first contact (average days)
   - Time distribution (0-1 day, 1-3 days, 3-7 days, 7+ days)
   - Contact method identification (First Outreach, First Engagement, Lead Status)

3. **Conversion Analysis**
   - SQL (Sales Qualified Lead) conversions
   - PQL (Product Qualified Lead) conversions
   - Conversion rates by owner
   - Cycle time calculations

4. **Owner Performance**
   - Total contacts assigned
   - Contact rate percentage
   - Average time to contact
   - SQL and PQL conversion rates
   - Uncontacted contacts breakdown

5. **Uncontacted Contacts**
   - List of all uncontacted high-score contacts
   - Breakdown by owner
   - Direct HubSpot links for each contact
   - Sample of first 20 contacts

#### Usage

```bash
# Current month-to-date (recommended)
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --current-mtd

# Specific month
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --month 2025-12

# Custom date range
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --start-date 2025-12-01 --end-date 2025-12-20
```

**Multi-month comparison:** Run for multiple months (e.g. `--month 2025-10`, `--month 2025-11`, etc.) to compare agent-by-agent performance over time.

#### Output Metrics

| Metric | Description |
|--------|-------------|
| **Total Contacts** | Count of contacts with score 40+ in period |
| **Average Score** | Mean score of all contacts |
| **Score Range** | Min and max scores |
| **Contact Rate** | Percentage of contacts that were contacted |
| **Average Time to Contact** | Mean days from creation to first contact |
| **SQL Conversion Rate** | Percentage of contacts that became SQL |
| **PQL Conversion Rate** | Percentage of contacts that became PQL |
| **Uncontacted Count** | Number of contacts never contacted |

#### Owner Performance Table

For each owner, the script displays:
- Total contacts assigned
- Number contacted
- Contact rate percentage
- Average days to contact
- SQL count and rate
- PQL count and rate

---

## Supporting Scripts

### `analyze_uncontacted_lead_status.py`

**Purpose:** Analyzes uncontacted contacts to identify those without Lead Status (and therefore no Lead object).

#### Key Features

- Identifies contacts without `hs_lead_status` field
- Verifies Lead object associations via API
- Confirms relationship: No Lead Status = No Lead Object
- Month-to-month comparison
- Owner breakdown

#### Usage

```bash
# Single file analysis
python tools/scripts/hubspot/analyze_uncontacted_lead_status.py --contacts-file path/to/file.csv

# Compare across months
python tools/scripts/hubspot/analyze_uncontacted_lead_status.py --compare-months
```

#### Key Finding

**Confirmed:** If a contact has no Lead Status field, it has no Lead object associated (100% correlation).

### `check_owner_status.py`

**Purpose:** Checks which owners are active or inactive in HubSpot.

#### Usage

```bash
python tools/scripts/hubspot/check_owner_status.py --contacts-file path/to/file.csv
```

### `compare_owner_status_months.py`

**Purpose:** Compares owner status (active/inactive) across multiple months.

#### Usage

```bash
python tools/scripts/hubspot/compare_owner_status_months.py
```

### `generate_visualization_report.py`

**Purpose:** Generates comprehensive HTML report with visualizations.

#### Features

- Owner performance charts (4 metrics)
- Engagement metrics pie charts
- Time distribution charts
- Score distribution histograms
- Uncontacted contacts breakdown
- Conversion funnel visualization
- Interactive tables

#### Usage

```bash
python tools/scripts/hubspot/generate_visualization_report.py
```

Output: `tools/outputs/high_score_visualization_report.html`

---

## Key Metrics Explained

### Contactability Metrics

1. **Contact Rate**
   - Formula: `(Contacts Contacted / Total Contacts) × 100`
   - Target: > 80% for score 40+ contacts
   - Indicates: Sales team responsiveness

2. **Time to Contact**
   - Formula: `Days from contact creation to first outreach/engagement`
   - Target: < 1 day for score 40+ contacts
   - Indicates: Speed of response

3. **Contact Method**
   - **First Outreach**: `hs_first_outreach_date` is populated
   - **First Engagement**: `hs_sa_first_engagement_date` is populated
   - **Lead Status**: `hs_lead_status` changed (indicates contact)

### Conversion Metrics

1. **SQL (Sales Qualified Lead)**
   - Definition: Contact has `hs_v2_date_entered_opportunity` populated
   - Indicates: Contact entered opportunity stage (has associated deal)

2. **PQL (Product Qualified Lead)**
   - Definition: `activo = 'true'` AND `fecha_activo` is populated
   - Indicates: Contact activated product account

3. **Conversion Rate**
   - Formula: `(Converted Contacts / Total Contacts) × 100`
   - Indicates: Lead quality and sales effectiveness

### Cycle Time

- **SQL Cycle Time**: Days from contact creation to SQL conversion
- **PQL Cycle Time**: Days from contact creation to PQL conversion
  - **IMPORTANT**: `fecha_activo` is date-only (no time component), while `createdate` has full timestamp. If both dates are on the same calendar day, cycle time = 0.0 days (same day conversion). This prevents negative cycle times for same-day activations.
- Indicates: Sales process efficiency

---

## Data Filters & Exclusions

### Automatic Exclusions

1. **"Usuario Invitado" Contacts**
   - Filter: `lead_source != "Usuario Invitado"`
   - Reason: Internal invited users, not real leads
   - Applied: At API query level (not post-fetch)

2. **Inactive Owners**
   - Filter: Only includes contacts assigned to active owners
   - Reason: Inactive owners cannot handle contacts
   - Applied: After fetching, before analysis

3. **Score Threshold**
   - Filter: Only `fit_score_contador >= 40`
   - Reason: Focus on high-quality leads
   - Applied: At API query level

### Owner Status Check

The scripts automatically:
- Fetch owner status from HubSpot API
- Cache owner names and status
- Display active/inactive status in reports
- Exclude contacts from inactive owners from analysis

---

## Usage Examples

### Example 1: Monthly Analysis

```bash
# Analyze December month-to-date
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --current-mtd
```

**Output:**
- Console report with all metrics
- CSV files: `high_score_contacts_2025_12_01_2025_12_20.csv`
- CSV files: `high_score_owner_performance_2025_12_01_2025_12_20.csv`

### Example 2: Month Comparison

```bash
# October
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --month 2025-10

# November
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --month 2025-11

# December
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --current-mtd
```

Then compare the CSV files or use the visualization report.

### Example 3: Lead Status Analysis

```bash
# Compare uncontacted contacts without Lead Status across months
python tools/scripts/hubspot/analyze_uncontacted_lead_status.py --compare-months
```

### Example 4: Generate Visualization Report

```bash
# Generate HTML report with charts
python tools/scripts/hubspot/generate_visualization_report.py

# Open in browser
open tools/outputs/high_score_visualization_report.html
```

---

## Output Files

### Contact CSV (`high_score_contacts_YYYY_MM_DD_YYYY_MM_DD.csv`)

**Columns:**
- `contact_id` - HubSpot contact ID
- `email` - Contact email
- `firstname`, `lastname` - Contact name
- `createdate` - Contact creation date
- `score` - fit_score_contador value
- `owner_id`, `owner_name` - Assigned owner
- `days_to_contact` - Days from creation to contact
- `contact_method` - How contact was made
- `contact_date` - Date of first contact
- `is_contacted` - Boolean: was contact made
- `is_sql`, `is_pql` - Boolean: conversion status
- `sql_date`, `pql_date` - Conversion dates
- `lifecyclestage` - Current lifecycle stage
- `hs_lead_status` - Lead status field

### Owner Performance CSV (`high_score_owner_performance_YYYY_MM_DD_YYYY_MM_DD.csv`)

**Columns:**
- `owner_id` - HubSpot owner ID
- `owner_name` - Owner full name
- `is_active` - Boolean: owner is active
- `total_contacts` - Total contacts assigned
- `contacted` - Number contacted
- `contact_rate` - Percentage contacted
- `avg_time_to_contact` - Average days to contact
- `sql_count`, `sql_rate` - SQL metrics
- `pql_count`, `pql_rate` - PQL metrics

### Visualization Report (`high_score_visualization_report.html`)

**Sections:**
1. Summary metrics cards
2. Owner performance charts (4 metrics)
3. Engagement metrics pie charts
4. Time distribution chart
5. Score distribution histogram
6. Uncontacted contacts breakdown
7. Conversion funnel
8. Owner performance table

---

## Best Practices

1. **Run Monthly Analysis**
   - Use `--current-mtd` at the beginning of each month
   - Compare with previous months using CSV files

2. **Monitor Contact Rates**
   - Target: > 80% contact rate for score 40+
   - Investigate owners with < 50% contact rate

3. **Track Time to Contact**
   - Target: < 1 day for score 40+
   - Flag contacts taking > 7 days

4. **Review Uncontacted Contacts**
   - Weekly review of uncontacted high-score contacts
   - Reassign if owner is inactive or overloaded

5. **Lead Status Quality**
   - Monthly check for contacts without Lead Status
   - Investigate why workflow didn't create Lead object

---

## Troubleshooting

### Issue: No contacts found

**Possible causes:**
- Date range too narrow
- All contacts filtered out (score < 40, inactive owners, etc.)
- API connection issue

**Solution:**
- Check date range
- Verify API key in `.env`
- Check console output for filter messages

### Issue: Owner shows as "Unknown (ID)"

**Solution:**
- Script automatically fetches owner names from API
- If still showing "Unknown", owner may not exist in HubSpot
- Check `owner_utils.py` for static mapping

### Issue: CSV missing `hs_lead_status` column

**Solution:**
- Regenerate CSV with latest script version
- Script now includes `hs_lead_status` in exports

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
- Owner performance tables
- Any tabular data displayed in chatbot responses

### Script Output Guidelines

- Scripts that print to console should use markdown table format
- CSV/Excel exports can remain in their native format
- When displaying results in chatbot, always convert to markdown tables
- Python scripts generating output should format as markdown tables for chatbot display

---

## Related Documentation

- **[HUBSPOT_SCRIPTS_DOCUMENTATION.md](./HUBSPOT_SCRIPTS_DOCUMENTATION.md)** - Complete script documentation
- **[README_HUBSPOT_CONFIGURATION.md](./README_HUBSPOT_CONFIGURATION.md)** - HubSpot configuration and field definitions
- **[COLPPY_FUNNEL_MAPPING_COMPLETE.md](./COLPPY_FUNNEL_MAPPING_COMPLETE.md)** - Funnel and Lead definitions

---

**Last Updated:** 2025-12-20  
**Maintained By:** Colppy Analytics Team

