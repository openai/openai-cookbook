# SQL PQL Conversion Analysis

**Last Updated:** 2025-12-21  
**Note:** SQL definition updated to include deal validation requirement.

## Overview

This analysis determines if Sales Qualified Leads (SQLs) were Product Qualified Leads (PQLs) **before** they converted to SQL.

## Definitions

### SQL (Sales Qualified Lead)
- **Definition**: Contact that converted from Lead to Opportunity (entered 'Oportunidad' lifecycle stage) **with validated deal association**
- **HubSpot Field**: `hs_v2_date_entered_opportunity` (timestamp when contact entered opportunity stage)
- **NEW REQUIREMENT**: Contact must have a deal associated that was created between `createdate` and SQL date (within the analysis period)
- **Validation**: SQL = MQL + `hs_v2_date_entered_opportunity` in period + deal created between contact creation and SQL date (within period)

### SQL Conversion Cohort
- **Definition**: Contacts **CREATED** in the period that **ALSO converted to SQL** in the same period **with validated deal association**
- **Cohort Requirements**:
  1. `createdate` must be within the specified date range (MQL - excluding 'Usuario Invitado')
  2. `hs_v2_date_entered_opportunity` must be within the same date range
  3. **Contact must have a deal associated that was created between `createdate` and SQL date (within the same period)**
- **Purpose**: Measures conversion rate within the period (e.g., monthly conversion rate) with deal validation
- **Example**: For any given month, includes contacts created in that month that also became SQL in the same month AND have a validated deal association

### PQL (Product Qualified Lead)
- **Definition**: Contact that activated during trial (triggered key event)
- **HubSpot Fields**:
  - `activo` = `'true'` (boolean flag indicating activation)
  - `fecha_activo` (timestamp when activation occurred)

## Analysis Logic

For each SQL contact, determine:

1. **PQL BEFORE SQL**: `fecha_activo < hs_v2_date_entered_opportunity`
   - Contact activated in product BEFORE becoming SQL (sales engagement)
   - Indicates product-led growth effectiveness
   - Measures: Days between PQL activation and SQL conversion

2. **PQL AFTER SQL**: `fecha_activo >= hs_v2_date_entered_opportunity`
   - Contact activated AFTER becoming SQL
   - Sales-driven conversion (sales engagement happened first)
   - Measures: Days between SQL conversion and PQL activation

3. **NEVER PQL**: `activo != 'true'` OR `fecha_activo` is null
   - Contact never activated in product

4. **PQL NO DATE**: `activo = 'true'` BUT `fecha_activo` is null
   - Data quality issue - marked as PQL but timestamp missing

## Usage

```bash
# Analyze any month
python tools/scripts/hubspot/sql_pql_conversion_analysis.py --month YYYY-MM

# Custom date range
python tools/scripts/hubspot/sql_pql_conversion_analysis.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

## Output

### Console Output
- Total SQLs analyzed
- PQL BEFORE SQL count and percentage
- PQL AFTER SQL count and percentage
- NEVER PQL count and percentage
- Average days between PQL and SQL (for PQL-before-SQL contacts)
- Key insights and ratios

### Files Generated
1. **CSV File**: `tools/outputs/sql_pql_analysis_{period}_{timestamp}.csv`
   - Detailed contact-level data with timing analysis

2. **JSON File**: `tools/outputs/sql_pql_analysis_{period}_{timestamp}.json`
   - Summary metrics and methodology documentation

## Methodology

Based on HubSpot documentation:
- **SQL Conversion**: `hs_v2_date_entered_opportunity` field (native HubSpot field) **WITH deal validation**
- **Deal Validation**: Contact must have a deal associated that was created between `createdate` and SQL date (within the analysis period)
- **PQL Identification**: `activo` and `fecha_activo` fields (custom Colppy fields)
- **Timing Comparison**: Direct date comparison in UTC timezone
- **Cohort Definition**: Contacts CREATED in period (MQL - excluding 'Usuario Invitado') that ALSO converted to SQL in the same period WITH validated deal association
- **Conversion Rate**: (Validated SQL conversions / Total contacts created) × 100

## Data Quality Checks

The script reports:
- Contacts marked as PQL but missing `fecha_activo` timestamp
- Date parsing issues
- Missing required fields

## Key Metrics

- **SQL Conversion Rate**: % of contacts created in period that became SQL in the same period
- **PQL-Before-SQL Rate**: % of SQL conversions that were PQL before sales engagement
- **PQL-After-SQL Rate**: % of SQL conversions that activated after sales engagement
- **Product-Led Growth Effectiveness**: Ratio of PQL-before-SQL vs PQL-after-SQL
- **Average Time to SQL**: Average hours/days from contact creation to SQL conversion

## Notes

- All dates are in UTC timezone
- Date comparisons account for timezone differences
- Script handles pagination automatically
- Rate limiting is handled with retry logic

## Typical Results

**Expected Patterns:**
- SQL Conversion Rate: 3-5% (monthly average)
- PQL Before SQL: < 10% (indicates sales-led model)
- Never PQL: > 90% (most SQLs don't activate in product)
- Same-day conversions: 50-70% of SQL conversions

**Activation Patterns:**
- Fast SQL conversions: Most occur within 24 hours
- Same-day conversions indicate immediate sales response
- Multi-day conversions suggest nurture process

## Field Verification

**Confirmed Correct Field Names:**
- ✅ `hs_v2_date_entered_opportunity` - SQL conversion date
- ✅ `hs_v2_date_entered_lead` - Lead date
- ✅ `hs_v2_date_entered_customer` - Customer date
- ✅ `createdate` - Contact creation date
- ✅ `activo` - PQL flag (custom Colppy field)
- ✅ `fecha_activo` - PQL activation date (custom Colppy field)

**Deprecated/Incorrect Names:**
- ❌ `hs_lifecyclestage_opportunity_date` (does not exist)
- ❌ `hs_lifecyclestage_lead_date` (does not exist)
- ❌ `hs_lifecyclestage_customer_date` (does not exist)

