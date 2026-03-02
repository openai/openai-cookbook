# UTM Campaign vs Scoring Correlation Analysis - Official Documentation

## Overview

This document describes the methodology for analyzing the correlation between UTM campaigns and lead scoring to identify which marketing channels bring high-quality leads and optimize lead assignment to sales teams.

## Purpose

1. **Identify High-Quality Campaigns**: Find which UTM campaigns consistently bring leads with high fit scores
2. **Optimize Marketing Spend**: Allocate budget to campaigns that generate convertible leads
3. **Improve Lead Assignment**: Route leads to appropriate teams based on campaign quality
4. **Detect Tracking Gaps**: Identify campaigns with missing UTM tracking that mask true lead sources

## Key Definitions

### UTM Campaign Field
- **Primary Field**: `utm_campaign` (Contact property)
- **Field Type**: String
- **Purpose**: Identifies the specific marketing campaign that generated the lead
- **Blank Handling**: If `utm_campaign` is null or empty, categorize as "Organic or Direct"

### Scoring Fields
- **Primary Field**: `fit_score_contador` (used for SMBs and accountants)
- **Field Type**: Number (0-100 scale)
- **Purpose**: Predicts lead quality and conversion likelihood
- **Note**: Despite the name "contador", this field is used for both SMBs (PyMEs) and accountants in sales workflow assignments

### Lead Quality Categories
- **High-Quality**: Score ≥ 40 (40-100 range)
- **Medium-Quality**: Score 30-39
- **Low-Quality**: Score < 30 (0-29 range)

### Conversion Metrics
- **SQL (Sales Qualified Lead)**: Contact converted to Opportunity stage
  - **Field**: `hs_v2_date_entered_opportunity`
  - **Type**: Datetime (ISO format with timezone)
- **PQL (Product Qualified Lead)**: Contact activated in product
  - **Fields**: `activo` (boolean flag) and `fecha_activo` (date)

## Methodology

### Step 1: Data Collection

**CRITICAL**: Must fetch ALL contacts using pagination to ensure complete dataset.

#### Required Fields for Analysis

```python
properties = [
    # Core identification
    'email',
    'createdate',
    
    # Scoring field
    'fit_score_contador',          # Primary scoring field (used for SMBs and accountants)
    
    # UTM Campaign (PRIMARY FIELD)
    'utm_campaign',                # Main field for campaign analysis
    
    # Conversion tracking
    'hs_v2_date_entered_opportunity',  # SQL conversion date
    'activo',                           # PQL flag
    'fecha_activo',                     # PQL activation date
]
```

#### Date Range Filtering

```python
from datetime import datetime, timezone

# Define analysis period
start_date = datetime(2025, 10, 1, tzinfo=timezone.utc)
end_date = datetime(2025, 11, 15, 23, 59, 59, tzinfo=timezone.utc)

# Filter contacts created in period
filter_groups = [{
    'filters': [
        {
            'propertyName': 'createdate',
            'operator': 'GTE',
            'value': start_date.isoformat()
        },
        {
            'propertyName': 'createdate',
            'operator': 'LTE',
            'value': end_date.isoformat()
        }
    ]
}]
```

#### Pagination Implementation

```python
# Using MCP HubSpot Tools
all_contacts = []
after = None

while True:
    response = hubspot_search_objects(
        objectType='contacts',
        filterGroups=filter_groups,
        properties=properties,
        limit=100,
        after=after
    )
    
    all_contacts.extend(response['results'])
    
    if 'paging' not in response or 'next' not in response['paging']:
        break
    
    after = response['paging']['next']['after']
```

### Step 2: UTM Campaign Categorization

#### Campaign Identification Logic

```python
def get_utm_campaign(contact):
    """
    Extract UTM campaign from contact.
    
    CRITICAL: Only use utm_campaign field, NOT other source fields.
    If blank, categorize as 'Organic or Direct'.
    """
    props = contact.get('properties', {})
    utm_campaign = props.get('utm_campaign')
    
    # Handle blank/null values
    if not utm_campaign or utm_campaign == '' or utm_campaign is None:
        return 'Organic or Direct'
    
    return utm_campaign
```

#### Why Only `utm_campaign`?

- **Consistency**: `utm_campaign` is the standard field for campaign tracking
- **Precision**: Other fields (`utm_source`, `hs_analytics_source`) may not reflect campaign intent
- **Clarity**: Campaign name directly identifies marketing initiative
- **Blank Handling**: Missing UTM indicates organic/direct traffic, which is valuable information

### Step 3: Scoring Analysis

#### Score Extraction Logic

```python
def get_contact_score(contact):
    """
    Extract scoring value using fit_score_contador.
    
    Note: Despite the name "contador", this field is used for both SMBs (PyMEs) 
    and accountants in sales workflow assignments.
    """
    props = contact.get('properties', {})
    
    # Use fit_score_contador (primary scoring field)
    score = props.get('fit_score_contador')
    if score and score != '':
        try:
            return float(score)
        except:
            pass
    
    return None  # No score available
```

#### Score Range Categorization

```python
def categorize_score(score):
    """Categorize score into quality ranges."""
    if score < 20:
        return '0-20'
    elif score < 30:
        return '20-30'
    elif score < 40:
        return '30-40'
    elif score < 50:
        return '40-50'
    elif score < 60:
        return '50-60'
    elif score < 70:
        return '60-70'
    elif score < 80:
        return '70-80'
    elif score < 90:
        return '80-90'
    else:
        return '90-100'
```

### Step 4: Campaign Aggregation

#### Campaign Statistics Calculation

```python
from collections import defaultdict

campaign_stats = defaultdict(lambda: {
    'contacts': [],
    'scores': [],
    'total': 0,
    'sqls': 0,
    'pqls': 0,
    'score_ranges': defaultdict(int)
})

for contact in all_contacts:
    # Get campaign
    campaign = get_utm_campaign(contact)
    
    # Get score
    score = get_contact_score(contact)
    if score is None:
        continue  # Skip contacts without scores
    
    # Categorize score
    score_range = categorize_score(score)
    
    # Check conversions
    has_sql = check_sql_conversion(contact, start_date, end_date)
    has_pql = check_pql_conversion(contact)
    
    # Aggregate
    campaign_stats[campaign]['contacts'].append(contact)
    campaign_stats[campaign]['scores'].append(score)
    campaign_stats[campaign]['total'] += 1
    campaign_stats[campaign]['score_ranges'][score_range] += 1
    
    if has_sql:
        campaign_stats[campaign]['sqls'] += 1
    if has_pql:
        campaign_stats[campaign]['pqls'] += 1
```

#### Calculate Campaign Metrics

```python
def calculate_campaign_metrics(campaign_data):
    """Calculate comprehensive metrics for each campaign."""
    scores = campaign_data['scores']
    total = campaign_data['total']
    
    if total == 0:
        return None
    
    # Average score
    avg_score = sum(scores) / len(scores) if scores else 0
    
    # Score distribution percentages
    score_ranges = campaign_data['score_ranges']
    high_quality_pct = (
        (score_ranges.get('40-50', 0) + 
         score_ranges.get('50-60', 0) + 
         score_ranges.get('60-70', 0) + 
         score_ranges.get('70-80', 0) + 
         score_ranges.get('80-90', 0) + 
         score_ranges.get('90-100', 0)) / total * 100
    )
    
    low_quality_pct = (
        (score_ranges.get('0-20', 0) + 
         score_ranges.get('20-30', 0)) / total * 100
    )
    
    # Conversion rates
    sql_rate = (campaign_data['sqls'] / total * 100) if total > 0 else 0
    pql_rate = (campaign_data['pqls'] / total * 100) if total > 0 else 0
    
    return {
        'campaign': campaign_name,
        'total': total,
        'avg_score': avg_score,
        'sqls': campaign_data['sqls'],
        'sql_rate': sql_rate,
        'pqls': campaign_data['pqls'],
        'pql_rate': pql_rate,
        'high_quality_pct': high_quality_pct,
        'low_quality_pct': low_quality_pct,
        'score_ranges': dict(score_ranges)
    }
```

### Step 5: Campaign Categorization

#### Quality-Based Categorization

```python
def categorize_campaign(metrics):
    """Categorize campaign by quality and conversion."""
    avg_score = metrics['avg_score']
    high_q_pct = metrics['high_quality_pct']
    sql_rate = metrics['sql_rate']
    
    # High-Quality Campaigns
    if avg_score >= 45 and high_q_pct >= 40:
        return {
            'category': 'HIGH_QUALITY',
            'recommendation': 'SCALE',
            'priority': 'HIGH'
        }
    
    # Medium-Quality Campaigns
    elif 35 <= avg_score < 45 or (avg_score >= 45 and high_q_pct < 40):
        return {
            'category': 'MEDIUM_QUALITY',
            'recommendation': 'OPTIMIZE',
            'priority': 'MEDIUM'
        }
    
    # Low-Quality Campaigns
    elif avg_score < 35 or metrics['low_quality_pct'] > 50:
        return {
            'category': 'LOW_QUALITY',
            'recommendation': 'FIX_OR_PAUSE',
            'priority': 'LOW'
        }
    
    # Conversion Paradox (high conversion but low quality)
    elif sql_rate > 20 and avg_score < 35:
        return {
            'category': 'PARADOX',
            'recommendation': 'REVIEW',
            'priority': 'MEDIUM'
        }
```

## Key Metrics

### Campaign Quality Metrics

1. **Average Score**: Mean fit score for all contacts from campaign
   - **Formula**: `sum(scores) / count(contacts)`
   - **Interpretation**: Higher = better lead quality

2. **High-Quality Percentage**: % of contacts with score ≥ 40
   - **Formula**: `(contacts with score ≥ 40) / total contacts × 100`
   - **Target**: ≥ 40% for high-quality campaigns

3. **Low-Quality Percentage**: % of contacts with score < 30
   - **Formula**: `(contacts with score < 30) / total contacts × 100`
   - **Target**: < 30% for acceptable campaigns

### Conversion Metrics

1. **SQL Conversion Rate**: % of contacts that became SQL
   - **Formula**: `(SQL count / total contacts) × 100`
   - **Context**: Compare against overall average (typically 3-8%)

2. **PQL Conversion Rate**: % of contacts that became PQL
   - **Formula**: `(PQL count / total contacts) × 100`
   - **Context**: Compare against overall average (typically 2-5%)

### Volume Metrics

1. **Total Contacts**: Number of contacts from campaign
2. **Monthly Projection**: Extrapolate from partial month data
   - **Formula**: `(contacts in period / days in period) × 30`

## Lead Assignment Criteria

### Team Structure

- **3 Closers**: Push leads from Lead → SQL (Sales Qualified Lead) for non-accountant contacts
- **4 Channel Managers**: Handle accountants (channel partners) and build relationships

### Accountant Identification

A contact is identified as an **ACCOUNTANT** if **ANY** of the following is true:

1. **Boolean Flag**: `es_contador = 'true'`
2. **Company Type**: `company.type IN ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']`
3. **UTM Campaign**: `utm_campaign CONTAINS 'conta'` (case-insensitive)
4. **Association**: Has association type `8` (Estudio Contable / Asesor / Consultor Externo)
5. **Referral**: `colppy_es_referido_del_contador = 'true'` (on associated deal)

### Assignment Framework

#### Closers Assignment (3 team members)

**Assign to Closers when ALL conditions are met:**

1. **Score Threshold**: `fit_score_contador >= 30`
2. **NOT Accountant**: `es_contador != 'true'` AND `company.type NOT IN ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']`
3. **NOT a PQL**: `activo != 'true'` (PQLs convert at 31% self-service rate)
4. **NOT Already SQL**: `hs_v2_date_entered_opportunity` is empty
5. **Recency**: `createdate >= TODAY - 7 days` (focus on fresh leads)

**Prioritization**:
- **Priority 1 (High)**: Score ≥ 40 (6-17% SQL conversion rate)
- **Priority 2 (Medium)**: Score 30-39 (2-5% SQL conversion rate)

**Distribution**: Round-robin across 3 closers, balanced by count

#### Channel Managers Assignment (4 team members)

**Assign to Channel Managers when ALL conditions are met:**

1. **IS Accountant**: `es_contador = 'true'` OR `company.type` is accountant-related OR `utm_campaign CONTAINS 'conta'`
2. **Score Threshold**: `fit_score_contador >= 20` (lower threshold for accountants)
3. **NOT Already SQL**: `hs_v2_date_entered_opportunity` is empty
4. **Recency**: `createdate >= TODAY - 7 days`

**Prioritization**:
- **Priority 1 (High)**: Score ≥ 40 (best quality)
- **Priority 2 (Medium)**: Score 30-39 (good quality)
- **Priority 3 (Low)**: Score 20-29 (acceptable quality for accountants)

**Distribution**: Round-robin across 4 channel managers, balanced by count

#### HubSpot Workflow Criteria - Closers

```javascript
// HubSpot Workflow Property Conditions (ALL must be true):
(
  (fit_score_contador >= 30)
) AND
(es_contador != 'true') AND
(company.type NOT IN ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']) AND
(activo != 'true') AND
(hs_v2_date_entered_opportunity is empty) AND
(createdate >= TODAY - 7 days)
```

#### HubSpot Workflow Criteria - Channel Managers

```javascript
// HubSpot Workflow Property Conditions (ALL must be true):
(
  (es_contador = 'true') OR
  (company.type IN ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']) OR
  (utm_campaign CONTAINS 'conta')
) AND
(
  (fit_score_contador >= 20)
) AND
(hs_v2_date_entered_opportunity is empty) AND
(createdate >= TODAY - 7 days)
```

#### Assignment Actions

**For Closers**:
1. Add to "Closer Queue" list/segment
2. Set priority based on score (≥40 = High, 30-39 = Medium)
3. Round-robin assign to one of 3 closers
4. Send notification to assigned closer

**For Channel Managers**:
1. Add to "Channel Manager Queue" list/segment
2. Set priority based on score (≥40 = High, 30-39 = Medium, 20-29 = Low)
3. Round-robin assign to one of 4 channel managers
4. Send notification to assigned channel manager

### Exclusion Rules

**DO NOT ASSIGN:**

1. **PQLs**: `activo = 'true'`
   - **Reason**: Convert at 31% self-service rate
   - **Action**: Let product handle these leads

2. **Low Score**: 
   - **For Closers**: Score < 30 (0-3% conversion rate, too low)
   - **For Channel Managers**: Score < 20 (0-1% conversion rate, too low)
   - **Action**: Automation only, no manual calls

3. **Already SQL**: `hs_v2_date_entered_opportunity` has value
   - **Reason**: Already converted, no action needed

4. **Stale Leads**: Created > 7 days ago
   - **Reason**: Lower response rates
   - **Action**: Focus on fresh opportunities

### Expected Results

**Based on Analysis:**

**Closers (Score ≥30, Non-Accountants)**:
- **Volume**: ~276 leads/month assigned to 3 closers
- **SQL Conversions**: ~24 SQLs/month (8.7% conversion rate)
- **Per Closer**: ~92 leads/month, ~8 SQLs/month
- **Efficiency**: 38% better conversion than calling all leads (6.3%)
- **Time Saved**: ~115 fewer calls/month (28.8 hours saved)

**Channel Managers (Score ≥20, Accountants)**:
- **Volume**: ~45-60 leads/month assigned to 4 channel managers
- **SQL Conversions**: ~3-5 SQLs/month (6-8% conversion rate, estimated)
- **Per Channel Manager**: ~11-15 leads/month, ~1 SQL/month
- **Focus**: Channel partner relationship building

**Note**: Conversion rates vary significantly between periods. Adjust expectations based on current month performance.

## Campaign Recommendations

### High-Quality Campaigns (Score ≥45, High Q% ≥40%)

**Action**: SCALE investment

**Characteristics**:
- Average score ≥ 45
- ≥ 40% high-quality leads (score ≥ 40)
- Examples: `PyMEs_lead_gen`, `Search_Branding_Leads_ARG`, `GRAL_lead_gen`

**Recommendations**:
1. Increase budget allocation
2. Expand targeting (if volume is low)
3. Improve nurturing (if SQL rate is low despite high scores)

### Medium-Quality Campaigns (Score 35-44)

**Action**: OPTIMIZE

**Characteristics**:
- Average score 35-44
- Mixed quality distribution
- Examples: `Organic or Direct` (when segmented)

**Recommendations**:
1. Segment by sub-source to find high-quality segments
2. Tighten targeting criteria
3. A/B test messaging and creative

### Low-Quality Campaigns (Score <35, Low Q% >50%)

**Action**: FIX OR PAUSE

**Characteristics**:
- Average score < 35
- > 50% low-quality leads (score < 30)
- Low SQL conversion rate
- Examples: `PMax_PyMEs_lead_gen`

**Recommendations**:
1. Review targeting criteria
2. Tighten audience parameters
3. Pause if quality doesn't improve within 30 days
4. Reallocate budget to high-quality campaigns

### Paradox Campaigns (High Conversion but Low Quality)

**Action**: REVIEW

**Characteristics**:
- SQL conversion rate > 20%
- But average score < 35
- Small sample size often

**Recommendations**:
1. Investigate why low-scoring leads convert
2. May indicate scoring model needs adjustment
3. Monitor closely with larger sample

## Critical Considerations

### UTM Tracking Gaps

**Problem**: Missing UTM campaigns mask true lead sources

**Impact**:
- Large portion of leads categorized as "Organic or Direct"
- Cannot optimize specific campaigns
- Budget allocation decisions lack data

**Solution**:
1. Implement UTM tracking on ALL marketing channels
2. Use consistent naming conventions
3. Include UTM parameters in all links
4. Regular audits to ensure tracking is working

### Scoring Field

**Primary Field**: `fit_score_contador`
- Used for both SMBs (PyMEs) and accountants
- Field name may be misleading ("contador" suggests accountant-only, but it's used for all leads)
- Used in sales workflow assignments for lead qualification
- Predicts lead quality and conversion likelihood (SQL and PQL)

### Date Range Precision

**CRITICAL**: Use timezone-aware datetime comparisons

```python
from datetime import datetime, timezone

# Correct: Timezone-aware
start_date = datetime(2025, 10, 1, tzinfo=timezone.utc)
end_date = datetime(2025, 10, 31, 23, 59, 59, tzinfo=timezone.utc)

# Parse HubSpot dates correctly
created_date = datetime.fromisoformat(
    contact['properties']['createdate'].replace('Z', '+00:00')
)

# Compare correctly
if start_date <= created_date <= end_date:
    # Contact is in range
    pass
```

### Pagination Requirements

**CRITICAL**: Always use pagination to fetch complete datasets

- HubSpot API returns max 100 contacts per request
- Use `after` cursor for pagination
- Continue until `paging.next` is null
- Verify total count matches expected volume

## Typical Patterns

### Pattern 1: High-Quality, Low Conversion

**Characteristics**:
- Average score ≥ 50
- High-quality percentage ≥ 60%
- SQL conversion rate < 5%

**Interpretation**:
- Campaign brings excellent leads
- But sales follow-up is insufficient
- Nurturing process needs improvement

**Action Items**:
1. Review sales follow-up process
2. Implement faster response times
3. Improve lead qualification criteria
4. Consider automated nurturing sequences

### Pattern 2: Low-Quality, High Volume

**Characteristics**:
- Average score < 35
- High volume (100+ contacts/month)
- Low SQL conversion rate (< 5%)

**Interpretation**:
- Campaign is flooding pipeline with low-quality leads
- Wasting closer time
- Contributing to overall quality decline

**Action Items**:
1. Pause campaign immediately
2. Review targeting criteria
3. Tighten audience parameters
4. Reallocate budget to high-quality campaigns

### Pattern 3: Missing UTM Tracking

**Characteristics**:
- Large portion of contacts have no UTM campaign
- Categorized as "Organic or Direct"
- Mixed quality distribution

**Interpretation**:
- UTM tracking is not implemented properly
- True lead sources are unknown
- Cannot optimize marketing spend effectively

**Action Items**:
1. Audit all marketing channels for UTM tracking
2. Implement UTM parameters on all links
3. Use consistent naming conventions
4. Regular tracking verification

## Example Output

### Campaign Summary Table

```
UTM Campaign                  │ Total │ Avg Score │ SQL Rate │ High Q% │ Low Q% │ Recommendation
──────────────────────────────┼───────┼───────────┼──────────┼─────────┼────────┼───────────────
PyMEs_lead_gen                │   18  │   56.4    │   0.0%   │  72.2%  │  5.6%  │ SCALE + NURTURE
Search_Branding_Leads_ARG     │   13  │   55.8    │   7.7%   │  61.5%  │ 23.1%  │ SCALE
GRAL_lead_gen                 │   26  │   47.7    │   7.7%   │  50.0%  │ 23.1%  │ SCALE
App Mobile Colppy             │   15  │   46.3    │  13.3%   │  46.7%  │ 13.3%  │ SCALE
Organic or Direct             │  377  │   38.4    │  14.1%   │  38.7%  │ 54.4%  │ SEGMENT
PMax_PyMEs_lead_gen          │  136  │   33.4    │   3.7%   │  16.9%  │ 23.5%  │ FIX OR PAUSE
Contadores_lead_gen           │    9  │   30.6    │  22.2%   │  44.4%  │ 55.6%  │ REVIEW
```

### Campaign Quality Distribution

```
Campaign: PyMEs_lead_gen
Total: 18 contacts
Average Score: 56.4
SQL: 0 (0.0%)
PQL: 0 (0.0%)

Score Distribution:
  0-20:   0 ( 0.0%)
  20-30:  1 ( 5.6%)
  30-40:  4 (22.2%)
  40-50:  0 ( 0.0%)
  50+:   13 (72.2%)

Quality: 72.2% high-quality (40+), 5.6% low-quality (<30)
```

## Implementation Checklist

- [ ] Fetch all contacts with pagination
- [ ] Extract UTM campaign (handle blanks as "Organic or Direct")
- [ ] Extract scoring (use primary field with fallback)
- [ ] Calculate campaign statistics (avg score, conversion rates)
- [ ] Categorize campaigns by quality
- [ ] Generate recommendations
- [ ] Identify UTM tracking gaps
- [ ] Document findings

## Related Documentation

- [HubSpot Configuration](./README_HUBSPOT_CONFIGURATION.md) - Complete field reference
- [SQL-PQL Correlation Analysis](./HUBSPOT_SQL_PQL_CORRELATION_ANALYSIS.md) - Conversion analysis methodology
- [SQL Conversion Analysis](./HUBSPOT_SQL_CONVERSION_ANALYSIS_LESSONS.md) - SQL cohort definitions
- [PQL Conversion Analysis](./HUBSPOT_PQL_CONVERSION_ANALYSIS_LESSONS.md) - PQL cohort definitions

## Version History

- **2025-11-15**: Initial documentation created
  - UTM campaign analysis methodology
  - Scoring correlation framework
  - Lead assignment criteria
  - Campaign categorization system

