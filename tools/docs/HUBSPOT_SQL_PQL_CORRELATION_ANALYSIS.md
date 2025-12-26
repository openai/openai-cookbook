# SQL-PQL Correlation Analysis - Official Documentation

## Overview

This document describes the methodology for analyzing the correlation between SQL (Sales Qualified Lead) and PQL (Product Qualified Lead) conversions to understand the relationship between sales engagement and product activation.

## Purpose

Measure and analyze the overlap between sales-driven conversions (SQL) and product-driven conversions (PQL) to:
1. Understand if product activation leads to sales opportunities (PLG effectiveness)
2. Identify if sales engagement drives product activation (sales-led adoption)
3. Detect gaps in the customer journey (PQLs not followed up, SQLs not activating)
4. Optimize the handoff between product and sales teams

## Key Definitions

### SQL (Sales Qualified Lead)
- **Definition**: Contact that converted to Opportunity lifecycle stage **with validated deal association**
- **HubSpot Field**: `hs_v2_date_entered_opportunity`
- **Field Type**: Datetime (ISO format with timezone)
- **Example**: `2025-11-03T12:56:32.703Z`
- **NEW VALIDATION REQUIREMENT**: Contact must have a deal associated that was created between `createdate` and SQL date (within the analysis period)
- **Complete Definition**: SQL = MQL (contact created in period, excluding 'Usuario Invitado') + `hs_v2_date_entered_opportunity` in period + deal created between contact creation and SQL date (within period)

### PQL (Product Qualified Lead)
- **Definition**: Contact that activated in the product during trial
- **HubSpot Fields**: 
  - `activo` (string: 'true' or null) - Activation flag
  - `fecha_activo` (date string: 'YYYY-MM-DD') - Activation date
- **Field Type**: Custom Colppy fields
- **Example**: `activo='true'` and `fecha_activo='2025-11-07'`

### Analysis Period
- **Base Cohort**: Contacts created in the target month (MQL - excluding 'Usuario Invitado')
- **SQL Cohort**: Contacts created AND converted to SQL in the target month **WITH validated deal association** (deal created between contact creation and SQL date, within the month)
- **PQL Cohort**: Contacts created AND activated (PQL) in the target month
- **Overlap**: Contacts that are BOTH SQL and PQL in the target month

## Methodology

### Step 1: Fetch Complete Dataset

**CRITICAL**: Must fetch ALL contacts using pagination.

```python
# Using MCP HubSpot Tools
filter_groups = [{
    "filters": [
        {"propertyName": "createdate", "operator": "GTE", "value": "YYYY-MM-01T00:00:00.000Z"},
        {"propertyName": "createdate", "operator": "LTE", "value": "YYYY-MM-30T23:59:59.999Z"}
    ]
}]

properties = [
    "email",
    "createdate",
    "lifecyclestage",
    "hs_v2_date_entered_opportunity",  # SQL date
    "activo",                           # PQL flag
    "fecha_activo"                      # PQL date
]

# Paginate through ALL results
after = None
all_contacts = []
while True:
    result = mcp_hubspot_hubspot-search-objects(
        objectType="contacts",
        filterGroups=filter_groups,
        properties=properties,
        limit=100,
        after=after
    )
    
    all_contacts.extend(result['results'])
    
    if 'paging' not in result or 'next' not in result['paging']:
        break
    after = result['paging']['next']['after']
```

**Pagination Rules**:
- HubSpot returns max 100 contacts per page
- MUST continue until `paging.next` is null
- Use `after` cursor for next page
- Typical month has 500-600 contacts (5-6 pages)

### Step 2: Categorize Contacts

For each contact, determine category based on conversions in target month:

```python
from datetime import datetime, timezone

month_start = datetime(YYYY, MM, 1, tzinfo=timezone.utc)
month_end = datetime(YYYY, MM, last_day, 23, 59, 59, tzinfo=timezone.utc)

categories = {
    'sql_only': [],      # SQL but not PQL
    'pql_only': [],      # PQL but not SQL
    'both': [],          # Both SQL and PQL
    'neither': []        # Neither SQL nor PQL
}

for contact in all_contacts:
    props = contact['properties']
    
    # Check SQL (created AND converted in month)
    has_sql = False
    if props.get('hs_v2_date_entered_opportunity'):
        sql_date = datetime.fromisoformat(props['hs_v2_date_entered_opportunity'].replace('Z', '+00:00'))
        if month_start <= sql_date <= month_end:
            has_sql = True
    
    # Check PQL (created AND activated in month)
    has_pql = False
    if props.get('activo') == 'true' and props.get('fecha_activo'):
        # Note: fecha_activo is date-only, must append time
        pql_date = datetime.fromisoformat(props['fecha_activo'] + "T00:00:00+00:00")
        if month_start <= pql_date <= month_end:
            has_pql = True
    
    # Categorize
    if has_sql and has_pql:
        categories['both'].append(contact)
    elif has_sql:
        categories['sql_only'].append(contact)
    elif has_pql:
        categories['pql_only'].append(contact)
    else:
        categories['neither'].append(contact)
```

### Step 3: Timing Analysis

For contacts with both SQL and PQL, determine which came first:

```python
def analyze_timing(contact):
    """Analyze which event happened first and calculate time between events"""
    props = contact['properties']
    
    sql_date = datetime.fromisoformat(props['hs_v2_date_entered_opportunity'].replace('Z', '+00:00'))
    pql_date = datetime.fromisoformat(props['fecha_activo'] + "T00:00:00+00:00")
    create_date = datetime.fromisoformat(props['createdate'].replace('Z', '+00:00'))
    
    if pql_date < sql_date:
        pattern = "PQL → SQL"  # Product-led growth
        time_between = (sql_date - pql_date).total_seconds() / 3600  # hours
        first_event = "PQL"
    else:
        pattern = "SQL → PQL"  # Sales-led adoption
        time_between = (pql_date - sql_date).total_seconds() / 3600  # hours
        first_event = "SQL"
    
    return {
        'pattern': pattern,
        'first_event': first_event,
        'hours_between': time_between,
        'time_to_pql': (pql_date - create_date).total_seconds() / 3600,
        'time_to_sql': (sql_date - create_date).total_seconds() / 3600
    }
```

### Step 4: Calculate Correlation Metrics

```python
total = len(all_contacts)
sql_count = len(categories['sql_only']) + len(categories['both'])
pql_count = len(categories['pql_only']) + len(categories['both'])
overlap = len(categories['both'])

# Conversion rates
sql_rate = sql_count / total * 100
pql_rate = pql_count / total * 100

# Overlap analysis
sql_overlap_rate = overlap / sql_count * 100 if sql_count > 0 else 0
pql_overlap_rate = overlap / pql_count * 100 if pql_count > 0 else 0

# Statistical correlation
P_sql = sql_count / total
P_pql = pql_count / total
P_both_observed = overlap / total
P_both_expected = P_sql * P_pql  # If independent

correlation_ratio = P_both_observed / P_both_expected if P_both_expected > 0 else 0
```

**Correlation Interpretation**:
- **< 0.5**: Negative correlation (avoid each other)
- **0.5 - 1.5**: Near independence (no correlation)
- **> 1.5**: Positive correlation (reinforce each other)

## Key Metrics

### Conversion Matrix

```
                 │  Became PQL  │  Did NOT become PQL  │  TOTAL
─────────────────┼──────────────┼─────────────────────┼────────
Became SQL       │   overlap    │     sql_only        │   SQL total
Did NOT get SQL  │   pql_only   │     neither         │   non-SQL total
─────────────────┼──────────────┼─────────────────────┼────────
TOTAL            │  PQL total   │   non-PQL total     │   Grand total
```

### Primary Metrics

1. **SQL Conversion Rate**: (SQL count / Total contacts) × 100
2. **PQL Conversion Rate**: (PQL count / Total contacts) × 100
3. **Overlap Rate (from SQL perspective)**: (Overlap / SQL count) × 100
4. **Overlap Rate (from PQL perspective)**: (Overlap / PQL count) × 100
5. **Correlation Strength**: P(SQL ∩ PQL) / [P(SQL) × P(PQL)]

### Timing Metrics

For contacts with both SQL and PQL:
- **Pattern Distribution**: % PQL→SQL vs % SQL→PQL
- **Average Time Between**: Hours between first and second event
- **Cycle Times**: Average time from creation to each event

## Cycle Time Calculation Methodology

**Definition**: Cycle time measures the duration from contact creation to conversion (SQL or PQL). This metric helps understand conversion velocity and identify bottlenecks in the customer journey.

### SQL Cycle Time Calculation

**Formula**: `SQL Cycle Time = hs_v2_date_entered_opportunity - createdate`

**Requirements**:
1. Contact must be created in the target period (`createdate` within period)
2. Contact must convert to SQL in the same period (`hs_v2_date_entered_opportunity` within period)
3. Both dates must be timezone-aware (UTC)

**Implementation**:
```python
from datetime import datetime, timezone

def calculate_sql_cycle_time(contact, period_start, period_end):
    """
    Calculate SQL cycle time for contacts created and converted in the period.
    
    Returns cycle time in days, or None if not applicable.
    """
    props = contact.get('properties', {})
    
    # Get creation date
    created_str = props.get('createdate')
    if not created_str:
        return None
    
    created_date = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
    
    # Check if created in period
    if not (period_start <= created_date <= period_end):
        return None
    
    # Get SQL conversion date
    sql_str = props.get('hs_v2_date_entered_opportunity')
    if not sql_str:
        return None
    
    sql_date = datetime.fromisoformat(sql_str.replace('Z', '+00:00'))
    
    # Check if converted in period
    if not (period_start <= sql_date <= period_end):
        return None
    
    # Calculate cycle time in days
    cycle_days = (sql_date - created_date).total_seconds() / 86400
    
    # Only return positive cycle times
    return cycle_days if cycle_days >= 0 else None
```

**Key Points**:
- Cycle time is measured in days (can be fractional, e.g., 0.5 = 12 hours)
- Only contacts that BOTH created AND converted in the period are included
- Negative cycle times are excluded (data quality check)
- Typical SQL cycle times: 0-7 days (most convert same-day or within 1-2 days)

### PQL Cycle Time Calculation

**Formula**: `PQL Cycle Time = fecha_activo - createdate`

**Requirements**:
1. Contact must be created in the target period (`createdate` within period)
2. Contact must activate (PQL) in the same period (`fecha_activo` within period)
3. `activo` must equal 'true'
4. Both dates must be timezone-aware (UTC)

**Implementation**:
```python
from datetime import datetime, timezone

def calculate_pql_cycle_time(contact, period_start, period_end):
    """
    Calculate PQL cycle time for contacts created and activated in the period.
    
    Returns cycle time in days, or None if not applicable.
    """
    props = contact.get('properties', {})
    
    # Check PQL flag
    if props.get('activo') != 'true':
        return None
    
    # Get creation date
    created_str = props.get('createdate')
    if not created_str:
        return None
    
    created_date = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
    
    # Check if created in period
    if not (period_start <= created_date <= period_end):
        return None
    
    # Get PQL activation date
    fecha_activo_str = props.get('fecha_activo')
    if not fecha_activo_str:
        return None
    
    # IMPORTANT: fecha_activo is date-only, must append time
    pql_date = datetime.fromisoformat(fecha_activo_str + "T00:00:00+00:00")
    
    # Check if activated in period
    if not (period_start <= pql_date <= period_end):
        return None
    
    # IMPORTANT: fecha_activo is date-only (no time), while createdate has full timestamp
    # If both dates are on the same calendar day, consider as same day (0 days)
    if pql_date.date() == created_date.date():
        return 0.0  # Same day conversion
    
    # Calculate cycle time in days
    cycle_days = (pql_date - created_date).total_seconds() / 86400
    
    # If still negative after same-day check, treat as same day
    if cycle_days < 0:
        return 0.0
    
    return cycle_days
```

**Key Points**:
- `fecha_activo` is date-only (YYYY-MM-DD), must append time when parsing
- **IMPORTANT:** `fecha_activo` has no time component (defaults to 00:00:00), while `createdate` has full timestamp
- **Same-Day Handling:** If both dates are on the same calendar day, cycle time is set to 0.0 (same day conversion)
- Cycle time is measured in days (can be fractional)
- Only contacts that BOTH created AND activated in the period are included
- Negative cycle times are corrected to 0.0 for same-day conversions (not a data quality issue)
- Typical PQL cycle times: 0-3 days (most activate same-day or within 1 day)

### Cycle Time Aggregation by Scoring Ranges

When analyzing cycle times by scoring ranges:

1. **Categorize contacts by score**: Use `fit_score_contador` (primary scoring field used for SMBs and accountants)
2. **Group into ranges**: 0-20, 20-30, 30-40, 40-50, 50-60, 60-70, 70-80, 80-90, 90-100
3. **Calculate statistics per range**:
   - Average cycle time
   - Median cycle time
   - Minimum cycle time
   - Maximum cycle time
   - Count of conversions

**Example Aggregation**:
```python
from collections import defaultdict

def aggregate_cycle_times_by_score(contacts, period_start, period_end):
    """
    Aggregate cycle times by scoring ranges.
    """
    score_ranges = defaultdict(lambda: {
        'sql_cycles': [],
        'pql_cycles': []
    })
    
    for contact in contacts:
        score = get_score(contact)  # Use fit_score_contador (primary scoring field)
        if score is None:
            continue
        
        score_range = categorize_score(score)  # Returns '0-20', '20-30', etc.
        
        # Calculate SQL cycle time
        sql_cycle = calculate_sql_cycle_time(contact, period_start, period_end)
        if sql_cycle is not None:
            score_ranges[score_range]['sql_cycles'].append(sql_cycle)
        
        # Calculate PQL cycle time
        pql_cycle = calculate_pql_cycle_time(contact, period_start, period_end)
        if pql_cycle is not None:
            score_ranges[score_range]['pql_cycles'].append(pql_cycle)
    
    # Calculate statistics per range
    results = {}
    for range_name, data in score_ranges.items():
        sql_cycles = data['sql_cycles']
        pql_cycles = data['pql_cycles']
        
        results[range_name] = {
            'sql_count': len(sql_cycles),
            'pql_count': len(pql_cycles),
            'avg_sql_cycle': sum(sql_cycles) / len(sql_cycles) if sql_cycles else None,
            'avg_pql_cycle': sum(pql_cycles) / len(pql_cycles) if pql_cycles else None,
            'median_sql_cycle': sorted(sql_cycles)[len(sql_cycles)//2] if sql_cycles else None,
            'median_pql_cycle': sorted(pql_cycles)[len(pql_cycles)//2] if pql_cycles else None,
            'min_sql_cycle': min(sql_cycles) if sql_cycles else None,
            'max_sql_cycle': max(sql_cycles) if sql_cycles else None,
            'min_pql_cycle': min(pql_cycles) if pql_cycles else None,
            'max_pql_cycle': max(pql_cycles) if pql_cycles else None,
        }
    
    return results
```

### Critical Considerations for Cycle Time Analysis

**Cohort Definition**:
- **MUST** include only contacts created AND converted in the same period
- Contacts created in period but converted later are excluded (not in conversion cohort)
- Contacts created earlier but converted in period are excluded (not in base cohort)

**Timezone Handling**:
- All datetime comparisons must use timezone-aware datetimes (UTC)
- `createdate` and `hs_v2_date_entered_opportunity` are ISO format with timezone
- `fecha_activo` is date-only, must append `T00:00:00+00:00` when parsing

**Data Quality**:
- Exclude negative cycle times (indicates data quality issue)
- Handle missing fields gracefully (return None, don't crash)
- Verify both creation and conversion dates exist before calculating

**Typical Patterns**:
- **SQL cycle times**: Typically 0-7 days, with most converting same-day or within 1-2 days
- **PQL cycle times**: Typically 0-3 days, with most activating same-day or within 1 day
- **Higher scores**: Tend to convert faster (shorter cycle times)
- **PQL vs SQL**: PQL typically faster than SQL (product activation is self-service)

**Use Cases**:
- Measure conversion velocity by scoring range
- Identify bottlenecks in customer journey
- Compare SQL vs PQL conversion speed
- Optimize sales and product activation processes
- Prioritize leads based on expected conversion speed

## Typical Patterns and Interpretations

### Pattern 1: Low Overlap (< 10%)

**Characteristics**:
- Few contacts achieve both SQL and PQL
- SQL-only and PQL-only cohorts are large
- Correlation ratio < 1.5

**Interpretation**:
- SQL and PQL represent independent customer journeys
- Different customer segments follow different paths
- Sales and product teams engaging different contacts

**Action Items**:
1. Build PQL → SQL handoff workflow
2. Encourage SQL contacts to trial product
3. Investigate why paths don't converge

### Pattern 2: Product-Led (PQL → SQL)

**Characteristics**:
- When overlap exists, PQL happens first
- Time between PQL and SQL: 1-5 days typically
- PQL overlap rate > SQL overlap rate

**Interpretation**:
- Users try product first, then sales engages
- Product activation signals sales opportunity
- PLG model is working

**Action Items**:
1. Optimize PQL → SQL conversion time
2. Automate sales alerts on PQL events
3. Scale this as primary growth model

### Pattern 3: Sales-Led (SQL → PQL)

**Characteristics**:
- When overlap exists, SQL happens first
- Time between SQL and PQL: varies widely
- SQL overlap rate > PQL overlap rate

**Interpretation**:
- Sales engages first, then user tries product
- Sales team driving product adoption
- Traditional sales model with product trial

**Action Items**:
1. Sales should encourage faster product trial
2. Improve trial onboarding for SQL contacts
3. Measure SQL → PQL conversion rate

### Pattern 4: High Independence (< 5% overlap on both sides)

**Characteristics**:
- Almost no contacts achieve both
- SQL-only ≈ PQL-only in count
- Large "neither" cohort (> 90%)

**Interpretation**:
- Completely separate customer journeys
- Broken handoff between teams
- Major optimization opportunity

**Action Items**:
1. CRITICAL: Fix team handoff process
2. Implement shared lead scoring
3. Create unified customer journey

## Critical Considerations

### Date Field Differences

**IMPORTANT**: `fecha_activo` vs `hs_v2_date_entered_opportunity`

| Field | Type | Format | Example | Precision |
|-------|------|--------|---------|-----------|
| `hs_v2_date_entered_opportunity` | datetime | ISO with timezone | `2025-11-03T12:56:32.703Z` | Second-level |
| `fecha_activo` | date | Date string | `2025-11-07` | Day-level only |

**Impact on Timing Analysis**:
- `fecha_activo` is set to midnight (00:00:00) when parsed
- If created late in day, `fecha_activo` same-day will show negative hours
- This is EXPECTED and correct behavior
- Use day-level comparison for PQL, hour-level for SQL

### Pagination Requirements

**MUST paginate completely**:
- Typical month: 500-600 contacts = 5-6 API calls
- Stopping early = incomplete analysis
- Always check `paging.next` existence
- Use `after` cursor, not offset-based pagination

### Timezone Handling

**All dates must be timezone-aware**:
```python
from datetime import datetime, timezone

# CORRECT
month_start = datetime(YYYY, MM, 1, tzinfo=timezone.utc)

# WRONG - will cause comparison errors
month_start = datetime(YYYY, MM, 1)
```

### Cohort Definition Precision

**Both creation AND conversion must be in target period**:

For SQL:
- ✅ Created Day 1, SQL Day 5 → Include
- ❌ Created previous month, SQL Day 5 → Exclude (not in base cohort)
- ❌ Created Day 1, SQL next month → Exclude (SQL not in period)

For PQL:
- ✅ Created Day 1, PQL Day 1 → Include
- ❌ Created previous month, PQL Day 5 → Exclude (not in base cohort)
- ❌ Created Day 1, PQL next month → Exclude (PQL not in period)

## Expected Outputs and Typical Results

### Conversion Funnel Example
```
N Total Contacts (base cohort)
├─► X SQL conversions (typically 3-5%)
│   ├─► Most are SQL-only (typically 80-95% of SQLs)
│   └─► Few are both SQL+PQL (typically < 10% of SQLs)
├─► Y PQL conversions (typically 2-4%)
│   ├─► Most are PQL-only (typically 80-95% of PQLs)
│   └─► Few are both SQL+PQL (typically < 10% of PQLs)
└─► Large "neither" group (typically 90-95%)
```

### Typical Patterns

**Low Overlap Pattern (< 10%)**:
- Indicates independent customer journeys
- SQL and PQL represent different segments
- Broken handoff between product and sales teams
- Most common pattern observed

**Key Insights from Low Overlap**:

**PQL-Only Contacts**:
- Typically 80-95% still in "lead" stage
- Activated in product but sales never engaged
- Represents broken PLG handoff
- High-value missed opportunities (hot leads)

**SQL-Only Contacts**:
- Typically 90-95% never activate in product
- Sales qualifying without trial usage
- Missing product adoption opportunity
- Indicates sales-led, not product-led model

**The Gap (Neither SQL nor PQL)**:
- Usually 90-95% of all contacts
- Massive optimization opportunity
- Need better lead qualification OR activation strategies

## Recommended Analysis Workflow

### 1. Data Collection
```bash
# Fetch all contacts for target month
# Paginate until complete
# Verify total count matches expectations
```

### 2. Categorization
```bash
# Split into 4 categories
# Validate: sum of categories = total contacts
```

### 3. Overlap Analysis
```bash
# Calculate overlap rates
# Identify timing patterns
# Measure correlation strength
```

### 4. Gap Analysis
```bash
# Analyze SQL-only: Why no product activation?
# Analyze PQL-only: Why no sales engagement?
# Analyze neither: Why no conversion at all?
```

### 5. Actionable Insights
```bash
# Identify broken handoffs
# Quantify improvement opportunities
# Prioritize optimizations
```

## Tools and Scripts

### Primary Script
Location: `/tools/scripts/hubspot/sql_pql_conversion_analysis.py`

Usage:
```bash
python3 tools/scripts/hubspot/sql_pql_conversion_analysis.py --month YYYY-MM
```

### MCP Direct Analysis
For exploratory analysis, use MCP tools directly:
```python
mcp_hubspot_hubspot-search-objects(
    objectType="contacts",
    filterGroups=[{
        "filters": [
            {"propertyName": "createdate", "operator": "GTE", "value": "YYYY-MM-01T00:00:00.000Z"},
            {"propertyName": "createdate", "operator": "LTE", "value": "YYYY-MM-30T23:59:59.999Z"}
        ]
    }],
    properties=["email", "createdate", "hs_v2_date_entered_opportunity", "activo", "fecha_activo"],
    limit=100
)
```

## HubSpot Link Generation

For contacts of interest, generate direct HubSpot links:

```python
PORTAL_ID = "19877595"
contact_id = "171539441220"
url = f"https://app.hubspot.com/contacts/{PORTAL_ID}/contact/{contact_id}"
```

Present links in markdown format:
```markdown
[email@example.com](https://app.hubspot.com/contacts/19877595/contact/171539441220)
```

## Data Quality Checks

Before analyzing, verify:

1. **Pagination Complete**: No `paging.next` in final result
2. **Field Availability**: All required fields present
3. **Date Validity**: All dates parse correctly
4. **Lifecycle Consistency**: No unexpected lifecycle states
5. **Category Sum**: All 4 categories = total contacts

## Related Documentation

- [SQL Conversion Analysis](./HUBSPOT_SQL_CONVERSION_ANALYSIS_LESSONS.md)
- [PQL Conversion Analysis](./HUBSPOT_PQL_CONVERSION_ANALYSIS_LESSONS.md)
- [Main HubSpot Configuration](./README_HUBSPOT_CONFIGURATION.md)
- [MCP Quick Reference](./HUBSPOT_COMPLETE_RETRIEVAL_QUICK_REFERENCE.md)

## Version History

- **v1.1**: Added Cycle Time Calculation Methodology
  - Documented SQL cycle time calculation (creation to SQL conversion)
  - Documented PQL cycle time calculation (creation to PQL conversion)
  - Added aggregation methodology by scoring ranges
  - Included critical considerations (cohort definition, timezone handling, data quality)
  - Provided reusable code examples for any period analysis

- **v1.0**: Initial documentation
  - Established correlation methodology
  - Documented field differences (fecha_activo vs hs_v2_date_entered_opportunity)
  - Identified pagination requirements
  - Created reusable framework for any period

