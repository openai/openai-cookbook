# HubSpot Monthly Analysis Guide

**Last Updated:** 2025-12-21  
**Purpose:** Comprehensive guide to monthly HubSpot analyses and their capabilities

---

## 📋 Overview

This guide outlines all available HubSpot analysis scripts and their monthly analysis capabilities. Use this document to understand what metrics and insights can be generated each month.

---

## 🎯 PRIMARY MONTHLY ANALYSES

### 1. PQL → SQL → Deal Relationship Analysis
**Script:** `pql_sql_deal_relationship_analysis.py`  
**Status:** ⭐ **PRIMARY ANALYSIS** - Run every month

#### Purpose
Comprehensive analysis of how PQL (Product Qualified Leads) affects SQL (deal creation) and deal close rates, including customer conversion.

#### Key Metrics
- **Funnel Analysis:**
  - Total Contacts → PQL → SQL (Deal Creation) → Deal Close → Customer
  - Conversion rates at each stage
  - Drop-off rates
  
- **PQL vs Non-PQL Comparison:**
  - PQL Deal Creation Rate vs Non-PQL Deal Creation Rate
  - PQL Deal Win Rate vs Non-PQL Deal Win Rate
  - PQL Advantage (percentage points)
  
- **Customer Conversion:**
  - Customer conversion rate (using deal close dates)
  - Customer journey paths (PQL → SQL → Customer, etc.)
  - Revenue per contact by path

- **Timing Analysis:**
  - PQL before/after SQL conversion
  - Days between PQL and SQL
  - Deal timing relative to PQL

#### Monthly Output
- Total contacts created
- PQL count and conversion rate
- SQL (deal creation) count and rate
- Deal win rate
- Customer count and conversion rate
- PQL advantage metrics
- Customer journey path distribution
- Revenue metrics

#### Command
```bash
# Full month
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month 2025-11

# Month-to-date
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --month-mtd 2025-12

# Custom date range
python tools/scripts/hubspot/pql_sql_deal_relationship_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
```

#### Key Assumptions
- **SQL = Deal Creation:** When a contact enters 'Oportunidad' stage (`hs_v2_date_entered_opportunity`), a deal is created
- **Customer Date:** Determined by earliest deal close date (not contact-level field)
- **MQL Definition:** All contacts (excluding 'Usuario Invitado') are MQLs (signed up for 7-day trial and validated email)

---

### 2. High Score Sales Handling Analysis
**Script:** `high_score_sales_handling_analysis.py`  
**Status:** ⭐ **PRIMARY ANALYSIS** - Run every month

#### Purpose
Analyzes how the sales team handles contacts with score 40+ (high-value leads).

#### Key Metrics
- **Contactability:**
  - Contacted vs uncontacted rates
  - Time to first contact
  - Contact rate by owner
  
- **Owner Performance:**
  - Contactability by owner (active owners only)
  - SQL/PQL conversion rates by owner
  - Average time to contact by owner
  
- **Uncontacted Contacts:**
  - List of uncontacted high-score contacts
  - Days since creation
  - Owner assignment

#### Monthly Output
- High-score contacts volume (score 40+)
- Contact rate (overall and by owner)
- Average time to first contact
- Conversion rates by owner
- Uncontacted contacts list with details
- Owner performance table

#### Command
```bash
# Current month-to-date
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --current-mtd

# Specific month
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --month 2025-12

# Custom date range
python tools/scripts/hubspot/high_score_sales_handling_analysis.py --start-date 2025-12-01 --end-date 2025-12-20
```

#### Key Features
- Automatically excludes inactive owners
- Excludes "Usuario Invitado" contacts
- Generates owner performance CSV
- Generates uncontacted contacts CSV

---

### 3. Scoring Distribution & Conversion Analysis
**Script:** `mtd_scoring_full_pagination.py`  
**Status:** ⭐ **PRIMARY ANALYSIS** - Run every month

#### Purpose
Analyzes score distribution and how scoring affects SQL/PQL conversion rates.

#### Key Metrics
- **Score Distribution:**
  - Percentage of contacts in each score range
  - Volume by score range
  
- **Conversion by Score:**
  - SQL conversion rate by score range
  - PQL conversion rate by score range
  - Conversion rate trends
  
- **Cycle Time:**
  - Average days to SQL conversion
  - Average days to PQL conversion
  - Cycle time by score range
  - **Note**: PQL cycle time uses same-day handling (0.0 days if fecha_activo and createdate are on same calendar day, since fecha_activo is date-only)

#### Monthly Output
- Score distribution percentages
- Conversion rates by score bucket
- Average cycle times
- Volume trends
- Period comparison (if comparing months)

#### Command
```bash
# Month-to-date
python tools/scripts/hubspot/mtd_scoring_full_pagination.py --month-mtd 2025-12

# Full month
python tools/scripts/hubspot/mtd_scoring_full_pagination.py --month 2025-11
```

---

## 🔍 SUPPORTING MONTHLY ANALYSES

### 4. Uncontacted Lead Status Analysis
**Script:** `analyze_uncontacted_lead_status.py`  
**Status:** Supporting - Run monthly for quality checks

#### Purpose
Identifies contacts without Lead Status field and verifies if they have associated Lead objects.

#### Key Metrics
- Contacts without Lead Status field
- Contacts without Lead objects
- Owner breakdown of uncontacted contacts
- Month-to-month comparison

#### Monthly Output
- Uncontacted contacts count
- Missing Lead Status count
- Missing Lead objects count
- Owner distribution
- Month-over-month comparison table

#### Command
```bash
python tools/scripts/hubspot/analyze_uncontacted_lead_status.py --compare-months
```

---

### 5. Owner Status Check
**Script:** `check_owner_status.py`  
**Status:** Supporting - Run monthly

#### Purpose
Checks which HubSpot owners are active or inactive.

#### Key Metrics
- Active vs inactive owners
- Owner distribution
- Contact assignment by owner status

#### Monthly Output
- Active owner count and list
- Inactive owner count and list
- Owner status table

#### Command
```bash
python tools/scripts/hubspot/check_owner_status.py
```

---

### 6. Owner Status Month Comparison
**Script:** `compare_owner_status_months.py`  
**Status:** Supporting - Run monthly

#### Purpose
Compares owner status and contact distribution across multiple months.

#### Key Metrics
- Owner status changes month-over-month
- Contact distribution by owner status
- Active owner trends

#### Monthly Output
- Owner status comparison table
- Contact assignment trends
- Month-over-month changes

#### Command
```bash
python tools/scripts/hubspot/compare_owner_status_months.py
```

---

## 🔬 SPECIALIZED ANALYSES

### 7. SQL/PQL Timing Analysis
**Script:** `sql_pql_conversion_analysis.py`  
**Status:** Specialized - Run as needed

#### Purpose
Analyzes the timing relationship between SQL and PQL conversions.

#### Key Metrics
- PQL → SQL timing (days between)
- SQLs that were PQL before/after SQL conversion
- Conversion timing patterns

#### Monthly Output
- PQL → SQL conversion timing distribution
- Timing statistics
- Before/after SQL breakdown

#### Command
```bash
python tools/scripts/hubspot/sql_pql_conversion_analysis.py --month 2025-11
```

---

### 8. Deal-Focused PQL Analysis
**Script:** `deal_focused_pql_analysis.py`  
**Status:** Specialized - Run as needed

#### Purpose
Analyzes PQL effectiveness based on actual deal attachment and win rates.

#### Key Metrics
- Deal attachment rates (PQL vs Non-PQL)
- Deal win rates
- Revenue per contact
- Sales velocity metrics

#### Monthly Output
- PQL deal attachment rate
- Revenue metrics
- Win rate comparison
- Sales velocity

#### Command
```bash
python tools/scripts/hubspot/deal_focused_pql_analysis.py --start-date 2025-11-01 --end-date 2025-11-30
```

---

### 9. ICP Operador Billing Analysis
**Script:** `analyze_icp_operador_billing.py`  
**Status:** Monthly - Run every month to track accountant channel revenue

#### Purpose
Analyzes closed deals to determine "who we bill" - identifying deals billed to accountants (ICP Operador) vs SMBs.

#### Key Metrics
- **ICP Operador Identification:**
  - Deals billed to accountants (by PRIMARY company type **ONLY** - only reliable method)
  - Deals billed to SMBs
  - Percentage breakdown
  
- **Additional Information:**
  - Deals with 'ICP Contador' plan name (informational only - not used for classification)
  - Accountant companies with non-ICP Contador plan (informational)
  
**⚠️ IMPORTANT:** Plan name method is NOT reliable because PYMEs can have "ICP Contador" plans when an accountant refers them, but we still bill the PYME (not the accountant).

#### Monthly Output
- Total closed deals count
- ICP Operador count and percentage (based ONLY on PRIMARY company type)
- Non-ICP Operador count and percentage
- Additional information (plan names for reference only)
- Detailed CSV with all deal-level data

#### Command
```bash
# By month
python tools/scripts/hubspot/analyze_icp_operador_billing.py --month 2025-12

# By date range
python tools/scripts/hubspot/analyze_icp_operador_billing.py --start-date 2025-12-01 --end-date 2026-01-01
```

#### Key Definitions
- **ICP Operador**: Deal is billed to an accountant (identified **ONLY** by PRIMARY company type - plan name is not reliable)
- **Accountant Company Types**: "Cuenta Contador", "Cuenta Contador y Reseller", "Contador Robado"
- **PRIMARY Company**: Company with association Type ID 5 in deal-company associations (determines who we bill)

---

### 10. Visualization Report Generation
**Script:** `generate_visualization_report.py`  
**Status:** Specialized - Run for presentations

#### Purpose
Generates HTML reports with interactive charts and visualizations.

#### Key Metrics
- Funnel visualizations
- Score distribution charts
- Conversion rate charts
- Owner performance charts

#### Monthly Output
- HTML visualization report
- Interactive charts
- Exportable visualizations

#### Command
```bash
python tools/scripts/hubspot/generate_visualization_report.py
```

---

## 📅 RECOMMENDED MONTHLY WORKFLOW

### Step 1: Primary Analyses (Run Every Month)
1. **PQL → SQL → Deal Relationship Analysis**
   - Provides complete funnel and conversion metrics
   - Shows PQL effectiveness
   - Customer conversion analysis

2. **High Score Sales Handling Analysis**
   - Sales team performance on high-value leads
   - Contactability metrics
   - Owner performance

3. **Scoring Distribution Analysis**
   - Score distribution trends
   - Conversion by score range
   - Cycle time metrics

4. **ICP Operador Billing Analysis**
   - Accountant channel revenue identification
   - Who we bill (accountant vs SMB)
   - Channel attribution for closed deals

### Step 2: Supporting Analyses (Monthly Quality Checks)
1. **Uncontacted Lead Status Analysis**
   - Data quality verification
   - Missing Lead objects identification

2. **Owner Status Check**
   - Ensure only active owners are analyzed
   - Track owner status changes

### Step 3: Visualization (Optional, for Presentations)
1. **Generate Visualization Report**
   - Create HTML reports with charts
   - Export for presentations

---

## 📊 KEY INSIGHTS FROM MONTHLY ANALYSES

### Funnel Metrics
- Total contacts created
- PQL conversion rate
- SQL (deal creation) rate
- Deal win rate
- Customer conversion rate

### PQL Effectiveness
- PQL vs Non-PQL deal creation rates
- PQL vs Non-PQL win rates
- PQL advantage (percentage points)
- Revenue per contact by path

### Sales Performance
- Contactability rates by owner
- Time to first contact
- Conversion rates by owner
- Uncontacted high-score contacts

### Trends
- Month-over-month comparison
- Score distribution changes
- Conversion rate trends
- Owner performance trends

---

## 🎯 MONTHLY ANALYSIS CHECKLIST

### Required (Every Month)
- [ ] Run PQL → SQL → Deal Relationship Analysis
- [ ] Run High Score Sales Handling Analysis
- [ ] Run Scoring Distribution Analysis
- [ ] Run ICP Operador Billing Analysis
- [ ] Check Owner Status
- [ ] Review Uncontacted Lead Status

### Optional (As Needed)
- [ ] Run SQL/PQL Timing Analysis
- [ ] Run Deal-Focused PQL Analysis
- [ ] Generate Visualization Report
- [ ] Compare Owner Status Across Months

---

## 📝 Notes

- All scripts automatically exclude "Usuario Invitado" contacts
- All scripts filter out inactive owners (where applicable)
- Customer date is determined by deal close date (earliest if multiple deals)
- SQL = Deal Creation (when contact enters 'Oportunidad' stage)
- All contacts (excluding 'Usuario Invitado') are considered MQLs

---

## 🔗 Related Documentation

- **[HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md](./HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md)** - Complete PQL analysis documentation
- **[HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md](./HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md)** - Scoring and contactability guide
- **[HUBSPOT_SCRIPTS_DOCUMENTATION.md](./HUBSPOT_SCRIPTS_DOCUMENTATION.md)** - Complete scripts documentation

---

**For questions or issues, refer to the main README: `tools/scripts/hubspot/README.md`**

