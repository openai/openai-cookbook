# Colppy Product Engagement Score - Implementation Proposal

## Overview

This document proposes a comprehensive **Product Engagement Score (PES)** implementation for Colppy using Mixpanel events. The score will help identify highly engaged users, predict churn risk, optimize product-led growth strategies, and improve customer success prioritization.

**Project ID:** 2201475 (Production)  
**Last Updated:** 2024-12-24  
**Status:** 📋 Proposal - Ready for Implementation

---

## Engagement Score Framework

### Core Dimensions

The engagement score combines **four key dimensions** of user behavior:

1. **Frequency** (40% weight) - How often users engage with the product
2. **Recency** (25% weight) - How recently users last engaged
3. **Breadth** (20% weight) - How many different features/modules users explore
4. **Depth** (15% weight) - How deeply users use core features

**Total Score Range:** 0-100 points

---

## Event Categories & Weights

### Tier 1: Core Value Events (Highest Weight)
*These events represent the core value proposition of Colppy*

| Event | Weight | Category | Rationale |
|-------|--------|----------|-----------|
| `Generó comprobante de venta` | **10** | Core Value | Primary product value - invoice generation |
| `app generó comprobante de venta` | **10** | Core Value | Mobile invoice generation |
| `Liquidar sueldo` | **8** | Core Value | Payroll processing - high-value feature |
| `Conectó el banco` | **7** | Core Value | Banking integration - advanced usage |
| `Finalizó importación` | **6** | Core Value | Data import completion - setup milestone |

### Tier 2: Feature Adoption Events (Medium Weight)
*These events show users exploring and adopting features*

| Event | Weight | Category | Rationale |
|-------|--------|----------|-----------|
| `Abrió el módulo clientes` | **3** | Feature Adoption | Clients module usage |
| `Abrió el módulo contabilidad` | **3** | Feature Adoption | Accounting module usage |
| `Abrió el módulo inventario` | **3** | Feature Adoption | Inventory module usage |
| `Abrió el módulo proveedores` | **3** | Feature Adoption | Suppliers module usage |
| `Abrió el módulo tesorería` | **3** | Feature Adoption | Treasury module usage |
| `Descargó el balance` | **4** | Feature Adoption | Financial reporting usage |
| `Descargó el estado de resultados` | **4** | Feature Adoption | P&L reporting usage |
| `Generó recibo de cobro` | **5** | Feature Adoption | Payment receipt generation |
| `Generó orden de pago` | **5** | Feature Adoption | Payment order generation |

### Tier 3: Engagement & Activity Events (Lower Weight)
*These events show general product engagement*

| Event | Weight | Category | Rationale |
|-------|--------|----------|-----------|
| `Login` | **2** | Engagement | Daily login activity |
| `app login` | **2** | Engagement | Mobile login activity |
| `Click Tablero` | **1** | Engagement | Dashboard interaction |
| `Abrió el módulo configuración de empresa` | **2** | Engagement | Configuration activity |
| `Click en ayuda` | **1** | Engagement | Help-seeking behavior |
| `Click en capacitaciones` | **2** | Engagement | Learning intent |

### Tier 4: Negative Signals (Subtract Points)
*These events indicate potential disengagement*

| Event | Weight | Category | Rationale |
|-------|--------|----------|-----------|
| `No generó comprobante de venta` | **-3** | Negative Signal | Failed invoice generation |
| `$mp_rage_click` | **-1** | Negative Signal | UX frustration indicator |

---

## Score Calculation Methodology

### Step 1: Frequency Score (40% of total)

**Formula:**
```
Frequency Score = (Total Weighted Events in Last 30 Days / Expected Events) × 40
```

**Expected Events Baseline:**
- **Active User:** 20+ weighted events per 30 days
- **Moderate User:** 10-19 weighted events per 30 days
- **Low User:** <10 weighted events per 30 days

**Calculation:**
```python
def calculate_frequency_score(user_events_last_30d):
    """
    Calculate frequency component of engagement score.
    
    Args:
        user_events_last_30d: List of events with weights in last 30 days
    
    Returns:
        Frequency score (0-40 points)
    """
    total_weighted_events = sum(event['weight'] for event in user_events_last_30d)
    
    # Normalize to 0-40 scale
    # Baseline: 20 events = 30 points (moderate engagement)
    # Maximum: 50+ events = 40 points (high engagement)
    
    if total_weighted_events >= 50:
        return 40
    elif total_weighted_events >= 30:
        # Linear interpolation between 30-50 events
        return 30 + ((total_weighted_events - 30) / 20) * 10
    elif total_weighted_events >= 20:
        # Linear interpolation between 20-30 events
        return 20 + ((total_weighted_events - 20) / 10) * 10
    elif total_weighted_events >= 10:
        # Linear interpolation between 10-20 events
        return 10 + ((total_weighted_events - 10) / 10) * 10
    else:
        # Below 10 events = low engagement
        return (total_weighted_events / 10) * 10
```

### Step 2: Recency Score (25% of total)

**Formula:**
```
Recency Score = Days Since Last Event → Score Mapping × 25
```

**Recency Mapping:**
| Days Since Last Event | Score Multiplier | Points (×25) |
|----------------------|------------------|--------------|
| 0-1 days | 1.0 | 25 |
| 2-3 days | 0.9 | 22.5 |
| 4-7 days | 0.7 | 17.5 |
| 8-14 days | 0.5 | 12.5 |
| 15-21 days | 0.3 | 7.5 |
| 22-30 days | 0.1 | 2.5 |
| 31+ days | 0.0 | 0 |

**Calculation:**
```python
def calculate_recency_score(days_since_last_event):
    """
    Calculate recency component of engagement score.
    
    Args:
        days_since_last_event: Number of days since user's last event
    
    Returns:
        Recency score (0-25 points)
    """
    if days_since_last_event <= 1:
        return 25
    elif days_since_last_event <= 3:
        return 22.5
    elif days_since_last_event <= 7:
        return 17.5
    elif days_since_last_event <= 14:
        return 12.5
    elif days_since_last_event <= 21:
        return 7.5
    elif days_since_last_event <= 30:
        return 2.5
    else:
        return 0
```

### Step 3: Breadth Score (20% of total)

**Formula:**
```
Breadth Score = (Unique Modules/Features Used / Total Available) × 20
```

**Module/Feature Categories:**
1. **Core Modules:** Clientes, Proveedores, Contabilidad, Inventario, Tesorería
2. **Core Features:** Invoice Generation, Payroll, Banking, Reports
3. **Advanced Features:** Imports, Exports, Configuration

**Total Available Features:** 12-15 (depending on plan)

**Calculation:**
```python
def calculate_breadth_score(unique_features_used, total_available_features=15):
    """
    Calculate breadth component of engagement score.
    
    Args:
        unique_features_used: Number of unique features/modules used
        total_available_features: Total features available (default: 15)
    
    Returns:
        Breadth score (0-20 points)
    """
    feature_ratio = unique_features_used / total_available_features
    
    # Reward exploration: 50% feature usage = 15 points
    # Full usage = 20 points
    if feature_ratio >= 0.8:
        return 20
    elif feature_ratio >= 0.5:
        return 15 + ((feature_ratio - 0.5) / 0.3) * 5
    elif feature_ratio >= 0.3:
        return 10 + ((feature_ratio - 0.3) / 0.2) * 5
    else:
        return (feature_ratio / 0.3) * 10
```

**Feature Mapping:**
```python
FEATURE_CATEGORIES = {
    'core_modules': [
        'Abrió el módulo clientes',
        'Abrió el módulo proveedores',
        'Abrió el módulo contabilidad',
        'Abrió el módulo inventario',
        'Abrió el módulo tesorería'
    ],
    'core_features': [
        'Generó comprobante de venta',
        'Liquidar sueldo',
        'Conectó el banco',
        'Descargó el balance',
        'Descargó el estado de resultados'
    ],
    'advanced_features': [
        'Finalizó importación',
        'Subió archivo para importar',
        'Descargó el libro iva ventas',
        'Abrió el módulo configuración de empresa'
    ]
}
```

### Step 4: Depth Score (15% of total)

**Formula:**
```
Depth Score = (Core Value Events / Expected Core Events) × 15
```

**Core Value Events:** Invoice generation, payroll, banking integration

**Expected Core Events:** 
- **High Depth:** 10+ core value events per 30 days
- **Moderate Depth:** 5-9 core value events per 30 days
- **Low Depth:** <5 core value events per 30 days

**Calculation:**
```python
def calculate_depth_score(core_value_events_count):
    """
    Calculate depth component of engagement score.
    
    Args:
        core_value_events_count: Number of core value events (invoices, payroll, etc.)
    
    Returns:
        Depth score (0-15 points)
    """
    if core_value_events_count >= 10:
        return 15
    elif core_value_events_count >= 5:
        # Linear interpolation between 5-10 events
        return 10 + ((core_value_events_count - 5) / 5) * 5
    elif core_value_events_count >= 1:
        # Linear interpolation between 1-5 events
        return (core_value_events_count / 5) * 10
    else:
        return 0
```

### Step 5: Negative Signal Adjustment

**Subtract points for negative signals:**
```python
def apply_negative_signals(base_score, negative_events):
    """
    Apply negative signal adjustments to engagement score.
    
    Args:
        base_score: Calculated score before adjustments
        negative_events: List of negative signal events
    
    Returns:
        Adjusted score (minimum 0)
    """
    penalty = 0
    
    for event in negative_events:
        if event == 'No generó comprobante de venta':
            penalty += 3
        elif event == '$mp_rage_click':
            penalty += 1
    
    return max(0, base_score - penalty)
```

### Final Score Calculation

```python
def calculate_engagement_score(user_id, events_data):
    """
    Calculate complete engagement score for a user.
    
    Args:
        user_id: Mixpanel distinct_id
        events_data: User's event data from Mixpanel
    
    Returns:
        Engagement score (0-100)
    """
    # Step 1: Frequency Score (40%)
    frequency_score = calculate_frequency_score(
        get_events_last_30_days(events_data)
    )
    
    # Step 2: Recency Score (25%)
    days_since_last = get_days_since_last_event(events_data)
    recency_score = calculate_recency_score(days_since_last)
    
    # Step 3: Breadth Score (20%)
    unique_features = get_unique_features_used(events_data)
    breadth_score = calculate_breadth_score(unique_features)
    
    # Step 4: Depth Score (15%)
    core_value_events = get_core_value_events_count(events_data)
    depth_score = calculate_depth_score(core_value_events)
    
    # Step 5: Base Score
    base_score = frequency_score + recency_score + breadth_score + depth_score
    
    # Step 6: Apply Negative Signals
    negative_events = get_negative_signal_events(events_data)
    final_score = apply_negative_signals(base_score, negative_events)
    
    return round(final_score, 2)
```

---

## Engagement Score Tiers

### Score Segmentation

| Score Range | Tier | Label | Description | Action |
|-------------|------|-------|-------------|--------|
| 80-100 | **Tier 1** | **Champion** | Highly engaged, power users | Upsell opportunities, case studies |
| 60-79 | **Tier 2** | **Engaged** | Regular users, good adoption | Monitor, nurture, feature education |
| 40-59 | **Tier 3** | **Moderate** | Occasional users, limited adoption | Proactive outreach, onboarding help |
| 20-39 | **Tier 4** | **At Risk** | Low engagement, potential churn | High-touch intervention, win-back campaigns |
| 0-19 | **Tier 5** | **Churned** | Very low/no engagement | Reactivation campaigns, exit surveys |

---

## Implementation in Mixpanel

### Option 1: User Property (Recommended)

**Store engagement score as a Mixpanel user property:**

```python
def update_engagement_score_in_mixpanel(user_id, score, tier):
    """
    Update engagement score as Mixpanel user property.
    
    This allows:
    - Segmentation by engagement tier
    - Cohort analysis
    - Funnel analysis
    - Retention analysis
    """
    mixpanel.people.set(user_id, {
        'engagement_score': score,
        'engagement_tier': tier,
        'engagement_score_last_updated': datetime.now().isoformat()
    })
```

**Properties to Set:**
- `engagement_score` (number, 0-100)
- `engagement_tier` (string: Champion, Engaged, Moderate, At Risk, Churned)
- `engagement_score_last_updated` (datetime)
- `frequency_score` (number, 0-40)
- `recency_score` (number, 0-25)
- `breadth_score` (number, 0-20)
- `depth_score` (number, 0-15)

### Option 2: Calculated Property (Mixpanel Formula)

**Create calculated properties in Mixpanel:**

1. **Frequency Component:**
   - Count weighted events in last 30 days
   - Use Mixpanel's formula: `sum(if(event in ['Generó comprobante de venta', ...], 10, ...))`

2. **Recency Component:**
   - Days since last event: `days_between(last_event_date, today())`
   - Map to score using conditional logic

3. **Breadth Component:**
   - Count unique modules/features: `count_distinct(module_name)`
   - Normalize to 0-20 scale

4. **Depth Component:**
   - Count core value events: `count(if(event in core_value_events))`
   - Normalize to 0-15 scale

### Option 3: Cohort-Based Analysis

**Create engagement cohorts:**

1. **Champion Users:** `engagement_score >= 80`
2. **Engaged Users:** `engagement_score >= 60 AND engagement_score < 80`
3. **Moderate Users:** `engagement_score >= 40 AND engagement_score < 60`
4. **At Risk Users:** `engagement_score >= 20 AND engagement_score < 40`
5. **Churned Users:** `engagement_score < 20`

**Use Cases:**
- Retention analysis by engagement tier
- Conversion funnel analysis
- Feature adoption by tier
- Churn prediction

---

## Mixpanel Query Examples

### Query 1: Calculate Engagement Score Distribution

```python
# Mixpanel JQL Query
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-12-24'
  })
  .groupByUser([
    'engagement_score',
    'engagement_tier'
  ])
  .groupBy(['engagement_tier'], mixpanel.reducer.count())
}
```

### Query 2: Engagement Score vs. Retention

```python
# Analyze retention by engagement tier
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-12-24'
  })
  .groupByUser([
    'engagement_tier'
  ])
  .groupBy(['engagement_tier'], mixpanel.reducer.count())
  .join(Retention({
    from_date: '2024-01-01',
    to_date: '2024-12-24',
    born_event: 'Login',
    event: 'Login'
  }))
}
```

### Query 3: Feature Adoption by Engagement Tier

```python
# Analyze which features are used by each engagement tier
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-12-24',
    event_selectors: [
      {'event': 'Abrió el módulo clientes'},
      {'event': 'Abrió el módulo proveedores'},
      {'event': 'Abrió el módulo contabilidad'},
      {'event': 'Abrió el módulo inventario'},
      {'event': 'Abrió el módulo tesorería'}
    ]
  })
  .groupByUser(['engagement_tier'])
  .groupBy(['engagement_tier', 'event'], mixpanel.reducer.count())
}
```

---

## Use Cases & Applications

### 1. Customer Success Prioritization

**Action:** Prioritize users with scores 20-39 (At Risk) for proactive outreach

**Mixpanel Query:**
```python
# Get At Risk users
Users({
  where: 'properties["engagement_score"] >= 20 AND properties["engagement_score"] < 40'
})
```

### 2. Product-Led Growth Optimization

**Action:** Identify which features drive higher engagement scores

**Analysis:**
- Compare engagement scores of users who use Feature A vs. those who don't
- Identify features that correlate with score increases
- Optimize onboarding to drive early feature adoption

### 3. Churn Prediction

**Action:** Predict churn risk based on engagement score trends

**Indicators:**
- Score dropping from Tier 2 → Tier 3 → Tier 4
- Score < 30 for 14+ days
- Recency score = 0 (no activity in 30+ days)

### 4. Upsell Opportunities

**Action:** Target Champion users (80-100) for premium features

**Criteria:**
- `engagement_score >= 80`
- `Tipo Plan Empresa` = 'Basic' or 'Standard'
- High depth score (using many core features)

### 5. Product Development Priorities

**Action:** Analyze which features are missing from high-engagement users

**Analysis:**
- Compare feature usage between Champion and Moderate users
- Identify gaps in feature adoption
- Prioritize features that drive engagement score increases

---

## Implementation Roadmap

### Phase 1: Data Collection & Calculation (Week 1-2)

1. **Set up event tracking** (if not already done)
   - Verify all Tier 1-3 events are tracked
   - Add negative signal tracking if missing

2. **Build calculation script**
   - Python script to calculate scores from Mixpanel data
   - Test with sample users
   - Validate score distributions

3. **Create Mixpanel user properties**
   - Set up `engagement_score` property
   - Set up `engagement_tier` property
   - Set up component scores (frequency, recency, breadth, depth)

### Phase 2: Automation & Updates (Week 3-4)

1. **Automate score calculation**
   - Daily batch job to recalculate scores
   - Update Mixpanel user properties
   - Set up monitoring/alerts

2. **Create Mixpanel cohorts**
   - Champion Users cohort
   - Engaged Users cohort
   - Moderate Users cohort
   - At Risk Users cohort
   - Churned Users cohort

3. **Build dashboards**
   - Engagement score distribution dashboard
   - Score trends over time
   - Tier migration analysis

### Phase 3: Integration & Action (Week 5-6)

1. **Integrate with Customer Success tools**
   - Export At Risk users to HubSpot
   - Create alerts for score drops
   - Set up automated workflows

2. **Product team integration**
   - Share engagement score data with product team
   - Analyze feature adoption by score tier
   - Identify product improvement opportunities

3. **Marketing integration**
   - Use engagement tiers for segmentation
   - Create targeted campaigns by tier
   - Measure campaign impact on scores

---

## Monitoring & Validation

### Key Metrics to Track

1. **Score Distribution:**
   - % of users in each tier
   - Average score by tier
   - Score trends over time

2. **Score Accuracy:**
   - Correlation with churn (score should predict churn)
   - Correlation with feature adoption
   - Correlation with trial-to-paid conversion

3. **Score Stability:**
   - Score variance over time (should be relatively stable)
   - Score changes when users adopt new features
   - Score recovery after interventions

### Validation Criteria

**Engagement Score Should:**
- ✅ Predict churn with 70%+ accuracy
- ✅ Correlate with feature adoption (r > 0.5)
- ✅ Differentiate between active and inactive users
- ✅ Respond to product improvements (scores increase when features improve)

---

## Next Steps

1. **Review & Approve:** Review this proposal and approve the methodology
2. **Data Validation:** Verify all required events are tracked in Mixpanel
3. **Pilot Test:** Calculate scores for 100 users and validate results
4. **Full Implementation:** Roll out to all users and automate updates
5. **Iterate:** Refine weights and methodology based on results

---

## References

- [Mixpanel User Properties Documentation](https://docs.mixpanel.com/docs/user-profiles)
- [Mixpanel Cohort Analysis](https://docs.mixpanel.com/docs/analysis/cohorts)
- [Product Engagement Scoring Best Practices](https://mixpanel.com/blog/product-engagement-score/)

---

*Last Updated: 2024-12-24*  
*Status: 📋 Proposal - Ready for Implementation*  
*Next Review: After pilot test completion*




