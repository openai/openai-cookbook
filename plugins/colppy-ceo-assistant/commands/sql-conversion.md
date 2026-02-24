---
name: sql-conversion
description: SQL conversion deep-dive — MQL-to-SQL conversion rates, cycle times, and monthly trends
---

# /sql-conversion

Deep-dive into SQL (Sales Qualified Lead) conversion: monthly MQL→SQL rates, conversion cycle times, same-day conversions, and contact-level detail.

## Usage

```
/colppy-ceo-assistant:sql-conversion 2025-07
/colppy-ceo-assistant:sql-conversion july 2025
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                SQL CONVERSION ANALYSIS                           │
├─────────────────────────────────────────────────────────────────┤
│  1. For each month (start month → current): fetch MQL contacts  │
│  2. Identify SQLs: opportunity date in period + has deals       │
│  3. Validate deal associations (v4 API, v3 fallback)            │
│  4. Calculate conversion rates and cycle times                  │
│  5. Show monthly trend + contact-level detail                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## What I Need From You

- **Start month**: The first month to analyze (e.g. "2025-07"). Analysis runs monthly from this month through the current month.
- Default start: 2025-07 if not specified

---

## Step-by-Step Execution

### Step 1: Determine Analysis Range

Calculate months from the start month through the current month. Each month is analyzed independently.

### Step 2: For Each Month, Fetch MQL Contacts

Search HubSpot contacts with these filters (ALL must match):
- `createdate` GTE `{month}-01T00:00:00Z`
- `createdate` LTE `{last-day-of-month}T23:59:59Z`
- `lead_source` HAS_PROPERTY (exclude nulls)
- `lead_source` NEQ `Usuario Invitado` (exclude team invitations)

**CRITICAL**: Always use HAS_PROPERTY + NEQ together for lead_source filtering.

Fetch these properties:
`email, firstname, lastname, createdate, fit_score_contador, hs_v2_date_entered_opportunity, activo, fecha_activo, lifecyclestage, lead_source`

### Step 3: Identify SQL Contacts

A contact is SQL if ALL of these are true:
- `hs_v2_date_entered_opportunity` is populated
- The opportunity date falls within the contact's creation month (or the analysis period)
- Contact has **at least 1 deal associated**

**Deal association validation**:
- Check via associations API: contacts → deals
- Try v4 endpoint first (`/crm/v4/objects/contacts/{id}/associations/deals`)
- If v4 fails, fallback to v3 endpoint (`/crm/v3/objects/contacts/{id}/associations/deals`)

**IMPORTANT**: Contacts with `hs_v2_date_entered_opportunity` but 0 deals are NOT real SQLs — they are manual lifecycle overrides. Exclude them from SQL count.

### Step 4: Calculate SQL Cycle Time

For each SQL contact:
- **Cycle time** = `hs_v2_date_entered_opportunity` - `createdate` (in days)
- **Same-day conversion**: cycle time < 1 day

### Step 5: Build Monthly Trend Table

```
Month       │ MQLs   │ SQLs   │ SQL Rate │ Avg Cycle │ Median Cycle │ Same-Day │ Same-Day %
────────────┼────────┼────────┼──────────┼───────────┼──────────────┼──────────┼───────────
{month_1}   │ {n}    │ {n}    │ {x}%     │ {x} days  │ {x} days     │ {n}      │ {x}%
{month_2}   │ {n}    │ {n}    │ {x}%     │ {x} days  │ {x} days     │ {n}      │ {x}%
...
────────────┼────────┼────────┼──────────┼───────────┼──────────────┼──────────┼───────────
TOTAL/AVG   │ {n}    │ {n}    │ {x}%     │ {x} days  │ {x} days     │ {n}      │ {x}%
```

### Step 6: Cycle Time Statistics (Overall)

```
Metric                         │ Value
───────────────────────────────┼──────────
Average Cycle Time             │ {x} days
Median Cycle Time              │ {x} days
Minimum Cycle Time             │ {x} days
Maximum Cycle Time             │ {x} days
Same-Day Conversions           │ {n} ({x}%)
```

### Step 7: SQL Contact Detail Table

For each SQL contact, show:

| Email | Name | Created | SQL Date | Cycle (days) | Same Day? | Score | PQL? | Lead Source | HubSpot Link |
|-------|------|---------|----------|-------------|-----------|-------|------|-------------|--------------|

Generate HubSpot links: `https://app.hubspot.com/contacts/19877595/contact/{contact_id}`

### Step 8: Key Insights

Highlight:
- **SQL rate trend**: Is it improving, stable, or declining month-over-month?
- **Speed trend**: Are cycle times getting shorter or longer?
- **Same-day pattern**: What percentage convert on the same day? Is this healthy or concerning?
- **High-score SQLs**: Among SQLs, what's the average fit_score_contador?
- **PQL overlap**: What percentage of SQLs are also PQLs?

---

## Important Notes

- **SQL definition**: MQL + `hs_v2_date_entered_opportunity` in period + at least one deal associated. No deal-createdate window requirement.
- **No deal-date constraint**: Unlike the SMB funnel, we don't require the deal to be created after the contact or within the same period. We just need a deal to exist.
- **Cycle time**: Measured from contact creation to opportunity date, not to deal creation.
- **Same-day conversion**: Contact created and entered opportunity stage on the same calendar day (< 1 day difference).
- The standard lead_source filter applies: HAS_PROPERTY + NEQ 'Usuario Invitado'.
- HubSpot portal: 19877595 (for contact links).
- HubSpot API uses UTC. UI uses Argentina (UTC-3). ~25 contact difference at month boundaries.
