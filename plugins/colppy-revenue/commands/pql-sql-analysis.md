---
name: pql-sql-analysis
description: Analyze PQL → SQL timing — did product activation happen before or after sales engagement?
---

# /pql-sql-analysis

Analyze the timing relationship between PQL (product activation) and SQL (sales engagement) for contacts created in a given month. Answers: "Do contacts activate in the product BEFORE or AFTER sales gets involved?"

## Usage

```
/colppy-revenue:pql-sql-analysis 2026-02
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                  PQL → SQL TIMING ANALYSIS                       │
├─────────────────────────────────────────────────────────────────┤
│  For each SQL contact created in the month:                      │
│  1. Was the contact PQL BEFORE becoming SQL?                     │
│     → Product-led: user activated, then sales engaged            │
│  2. Was the contact PQL AFTER becoming SQL?                      │
│     → Sales-led: sales engaged first, then user activated        │
│  3. Was the contact NEVER PQL?                                   │
│     → Sales-only: user never activated in product                │
└─────────────────────────────────────────────────────────────────┘
```

---

## What I Need From You

- **Month**: Which month to analyze (e.g. "2026-02", "february 2026")

---

## Step-by-Step Execution

### Step 1: Fetch ALL Contacts Created in Period

Search HubSpot contacts with filters:
- `createdate` GTE `{month}-01T00:00:00Z`
- `createdate` LTE `{last-day}T23:59:59Z`
- `lead_source` HAS_PROPERTY
- `lead_source` NEQ `Usuario Invitado`

Properties to fetch:
`email, firstname, lastname, createdate, lifecyclestage, activo, fecha_activo, hs_v2_date_entered_opportunity, num_associated_deals, lead_source`

Record total contact count — this is the denominator for conversion rates.

### Step 2: Identify SQL Contacts

From all contacts, filter to SQL cohort:
- `hs_v2_date_entered_opportunity` is populated (has a date within the period)
- `num_associated_deals` > 0 (has at least one deal)
- Both conditions MUST be true — contacts with opportunity date but 0 deals are manual overrides, not real SQLs

### Step 3: For Each SQL Contact, Classify PQL Timing

For each SQL contact, compare `fecha_activo` (PQL date) with `hs_v2_date_entered_opportunity` (SQL date):

- **PQL Before SQL**: `fecha_activo` < `hs_v2_date_entered_opportunity`
  → Product-led growth signal. User activated before sales engaged.
  → Calculate days between PQL and SQL.

- **PQL After SQL**: `fecha_activo` >= `hs_v2_date_entered_opportunity`
  → Sales-led. Sales engaged first, product activation came later.
  → Calculate days between SQL and PQL.

- **Never PQL**: `activo` != `true` OR `fecha_activo` is null
  → Sales-only conversion. Contact never activated in product.

### Step 4: Present Results

**Summary Table:**

```
Category                │ Count   │ % of SQLs │ Avg Days Gap
────────────────────────┼─────────┼───────────┼─────────────
PQL Before SQL          │ {n}     │ {x}%      │ {x} days
PQL After SQL           │ {n}     │ {x}%      │ {x} days
Never PQL               │ {n}     │ {x}%      │ —
────────────────────────┼─────────┼───────────┼─────────────
Total SQLs              │ {n}     │ 100%      │
```

**Conversion Context:**
```
Total contacts created in period: {n}
SQL conversions: {n} ({x}%)
PQL contacts in SQL cohort: {n} ({x}% of SQLs)
```

**Detail Table (each SQL contact):**

| Email | Created | SQL Date | PQL Date | PQL Timing | Days Gap | Lifecycle | Deals |
|-------|---------|----------|----------|------------|----------|-----------|-------|

### Step 5: Key Insight

State clearly:
- "{X}% of SQLs were PQL before sales engagement — this indicates product-led growth effectiveness"
- Or: "Most SQLs were never PQL — sales pipeline is primarily outbound/sales-driven"
