---
name: lead-scoring
description: High-score lead handling analysis — contacts with fit_score_contador ≥ 40, owner performance, engagement speed
---

# /lead-scoring

Analyze how high-score leads (fit_score_contador ≥ 40) are being handled by sales reps: assignment distribution, time to first contact, engagement rates, and conversion outcomes.

## MCP (Preferred When Available)

If **hubspot-analysis** MCP is configured, call:
- `run_high_score_analysis(month="2026-02")` for a specific month
- `run_high_score_analysis(current_mtd=True)` for current month-to-date

Present the output directly. Otherwise follow the manual steps below.

## Usage

```
/colppy-revenue:lead-scoring 2026-02
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│              HIGH-SCORE LEAD HANDLING ANALYSIS                   │
├─────────────────────────────────────────────────────────────────┤
│  1. Fetch contacts with fit_score_contador >= 40 in period      │
│  2. Exclude inactive owners                                     │
│  3. Calculate time to first contact (business hours + total)    │
│  4. Measure engagement rates and conversion by owner            │
│  5. Break down by score range (40-49, 50-59, ... 90-100)       │
│  6. Report unengaged contacts                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## What I Need From You

- **Month**: Which month to analyze (e.g. "2026-02", "january 2026")
- **MTD or full month**: If current month, I'll do month-to-date automatically

---

## Step-by-Step Execution

### Step 1: Fetch High-Score Contacts Created in Period

Search HubSpot contacts with these filters (ALL must match):
- `createdate` GTE `{month}-01T00:00:00Z`
- `createdate` LTE `{last-day-of-month}T23:59:59Z`
- `fit_score_contador` GTE `40`
- `lead_source` HAS_PROPERTY (exclude nulls)
- `lead_source` NEQ `Usuario Invitado` (exclude team invitations)

**CRITICAL**: Always use HAS_PROPERTY + NEQ together for lead_source filtering.

Fetch these properties:
`email, firstname, lastname, createdate, fit_score_contador, hubspot_owner_id, hs_first_outreach_date, hs_sa_first_engagement_date, hs_lead_status, last_lead_status_date, hs_v2_date_entered_opportunity, activo, fecha_activo, lifecyclestage, lead_source`

### Step 2: Resolve Owners and Exclude Inactive

For each contact with a `hubspot_owner_id`:
- Look up the owner name and active status via the owners API
- **Exclude contacts assigned to inactive owners** from the analysis

Build a list of active owners with their assigned contacts.

### Step 3: Determine First Contact Date

For each contact, determine when sales first reached out using these priorities (use the FIRST available):

1. **`hs_first_outreach_date`** — Best signal: direct outreach recorded
2. **`hs_sa_first_engagement_date`** — Second best: any sales engagement
3. **`last_lead_status_date`** — Fallback: only if lead_status changed from 'Nuevo Lead' (this indicates intentional status change)

If none of these are available, the contact is **unengaged**.

### Step 4: Calculate Time to First Contact

For engaged contacts, calculate two metrics:

**Total Hours**: Simple difference between `createdate` and first contact date in hours.

**Business Hours**: Only count hours during Argentina business time:
- **Working hours**: 9:00 AM – 6:00 PM (Argentina, UTC-3)
- **Working days**: Monday through Friday
- **Exclude Argentina holidays** (for 2025: Jan 1, Mar 3-4, Mar 24, Apr 2, Apr 18-19, May 1, May 25, Jun 16, Jun 20, Jul 9, Aug 17, Oct 12, Nov 20, Dec 8, Dec 25)

### Step 5: Owner Performance Table

```
Owner               │ Total │ Contacted │ Contact % │ Avg Biz Hrs │ Avg Total Hrs │ SQL │ SQL % │ PQL │ PQL %
─────────────────────┼───────┼───────────┼───────────┼─────────────┼───────────────┼─────┼───────┼─────┼──────
{owner_name}         │ {n}   │ {n}       │ {x}%      │ {x}h        │ {x}h          │ {n} │ {x}%  │ {n} │ {x}%
...
─────────────────────┼───────┼───────────┼───────────┼─────────────┼───────────────┼─────┼───────┼─────┼──────
TOTAL                │ {n}   │ {n}       │ {x}%      │ {x}h        │ {x}h          │ {n} │ {x}%  │ {n} │ {x}%
```

Where:
- **SQL**: Contact has `hs_v2_date_entered_opportunity` populated
- **PQL**: Contact has `activo` = true

### Step 6: Score Range Analysis

Break down by score buckets:

```
Score Range │ Count │ Contacted % │ Avg Biz Hrs │ SQL Rate │ PQL Rate
────────────┼───────┼─────────────┼─────────────┼──────────┼─────────
90-100      │ {n}   │ {x}%        │ {x}h        │ {x}%     │ {x}%
80-89       │ {n}   │ {x}%        │ {x}h        │ {x}%     │ {x}%
70-79       │ {n}   │ {x}%        │ {x}h        │ {x}%     │ {x}%
60-69       │ {n}   │ {x}%        │ {x}h        │ {x}%     │ {x}%
50-59       │ {n}   │ {x}%        │ {x}h        │ {x}%     │ {x}%
40-49       │ {n}   │ {x}%        │ {x}h        │ {x}%     │ {x}%
```

### Step 7: Time to Contact Distribution

```
Time Bucket          │ Count │ % of Contacted
─────────────────────┼───────┼───────────────
0-1 business day     │ {n}   │ {x}%
1-3 business days    │ {n}   │ {x}%
3-7 business days    │ {n}   │ {x}%
7+ business days     │ {n}   │ {x}%
```

### Step 8: Unengaged High-Score Contacts

List contacts with fit_score >= 40 that have NOT been contacted:

| Email | Name | Score | Created | Owner | Days Since Created | HubSpot Link |
|-------|------|-------|---------|-------|--------------------|--------------|

Generate HubSpot links: `https://app.hubspot.com/contacts/19877595/contact/{contact_id}`

---

## Important Notes

- **Threshold**: fit_score_contador ≥ 40. This represents high-fit leads that should be prioritized by sales.
- **Business hours**: Argentina timezone (UTC-3), 9 AM – 6 PM, weekdays only, excluding national holidays.
- **Contact methods priority**: hs_first_outreach_date > hs_sa_first_engagement_date > last_lead_status_date (only from 'Nuevo Lead').
- **Inactive owners excluded**: Contacts assigned to deactivated HubSpot users are removed from analysis.
- **HubSpot portal**: 19877595 (for generating contact links).
