---
name: sales-ramp
description: Sales rep ramp cohort analysis — monthly deal performance from each rep's start date
---

# /sales-ramp

Analyze sales rep performance as a cohort from their start date. Shows deals closed per month since onboarding, comparing reps at the same tenure stage.

## Usage

```
/colppy-ceo-assistant:sales-ramp
/colppy-ceo-assistant:sales-ramp closers
/colppy-ceo-assistant:sales-ramp accountant channel
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                 SALES RAMP COHORT ANALYSIS                      │
├─────────────────────────────────────────────────────────────────┤
│  1. Get active sales reps and their start dates                 │
│  2. Fetch all closed-won + recovery deals                       │
│  3. Attribute deals to owners (+ collaborators for Acct Chan)   │
│  4. Map each deal to cohort month (months since rep start)      │
│  5. Build cohort grid: rep × month since start                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## What I Need From You

- **Team filter** (optional): "closers", "accountant channel", or a specific rep name
- If no filter, I'll show all reps

---

## Step-by-Step Execution

### Step 1: Sales Rep Start Dates

Use these hardcoded start dates for active sales reps:

| Rep Name                  | Start Date      | Team               |
|---------------------------|-----------------|---------------------|
| Karina Lorena Russo       | September 2024  | (determine via API)  |
| Rocio Luque               | April 2024      | (determine via API)  |
| Estefania Sol Arregui     | March 2025      | (determine via API)  |
| Tatiana Amaya             | July 2025       | (determine via API)  |
| Jair Josue Calas          | September 2025  | (determine via API)  |

**Excluded reps**: Mariano Alvarez, Sofia Celentano (no longer active in sales role).

To determine each rep's team, look up their owner ID via the HubSpot owners API and check their team assignment. Two teams exist:
- **Closers**
- **Accountant Channel**

### Step 2: Fetch All Relevant Deals

Search HubSpot deals with these filters (use OR filterGroups):

**FilterGroup 1**: `dealstage` EQ `closedwon`
**FilterGroup 2**: `dealstage` EQ `34692158` (recovery stage)

Fetch these properties:
`dealname, amount, dealstage, closedate, createdate, hubspot_owner_id, hs_all_collaborator_owner_ids`

Paginate through ALL results — there may be hundreds of deals.

### Step 3: Attribute Deals to Reps

For each deal, determine which rep(s) get credit:

**Closers team**: Only count deals where the rep is the **owner** (`hubspot_owner_id` matches).

**Accountant Channel team**: Count deals where the rep is the **owner** OR a **collaborator** (`hs_all_collaborator_owner_ids` — this is a semicolon-separated list of owner IDs).

**IMPORTANT**: A single deal may be attributed to multiple reps if one is the owner and another is a collaborator.

### Step 4: Map Deals to Cohort Months

For each deal attributed to a rep:
- Get the deal's `closedate` month
- Calculate **cohort month** = months since the rep's start date
  - Month 0 = the rep's start month
  - Month 1 = one month after start
  - etc.
- Only include deals closed ON or AFTER the rep's start date

### Step 5: Build Deals Per Month Table

```
Rep Name            │ Team      │ Month 0 │ Month 1 │ Month 2 │ ... │ Total
────────────────────┼───────────┼─────────┼─────────┼─────────┼─────┼──────
{rep_name}          │ {team}    │ {n}     │ {n}     │ {n}     │ ... │ {n}
{rep_name}          │ {team}    │ {n}     │ {n}     │ {n}     │ ... │ {n}
```

### Step 6: Revenue Per Month Table

Same structure as above but showing revenue (sum of deal `amount`) instead of deal count:

```
Rep Name            │ Team      │ Month 0  │ Month 1  │ Month 2  │ ... │ Total
────────────────────┼───────────┼──────────┼──────────┼──────────┼─────┼────────
{rep_name}          │ {team}    │ ${x}     │ ${x}     │ ${x}     │ ... │ ${x}
```

### Step 7: Cohort Comparison

Compare reps at the same tenure stage:

```
Cohort Month │ {Rep1} │ {Rep2} │ {Rep3} │ ... │ Average
─────────────┼────────┼────────┼────────┼─────┼────────
Month 0      │ {n}    │ {n}    │ {n}    │ ... │ {avg}
Month 1      │ {n}    │ {n}    │ {n}    │ ... │ {avg}
Month 2      │ {n}    │ {n}    │ {n}    │ ... │ {avg}
...
```

Use "—" for months a rep hasn't reached yet.

### Step 8: Key Insights

Calculate and highlight:
- **Fastest ramp**: Which rep hit their first deal earliest?
- **Highest Month 3**: Who had the best performance at 3 months tenure?
- **Current run rate**: Each rep's deals in the most recent complete month
- **Cumulative deals**: Total deals per rep since start
- **Average deal size**: Per rep across their tenure

---

## Important Notes

- **Recovery stage (34692158)**: Deals in this stage count as wins alongside `closedwon`. These are recovered/reactivated accounts.
- **Collaborator attribution**: `hs_all_collaborator_owner_ids` is semicolon-separated (e.g., "12345;67890"). Split and match each ID.
- **Closers vs Accountant Channel**: Different attribution rules. Closers = owner only. Accountant Channel = owner + collaborator.
- **Month 0**: The rep's first month. If start date is September 2024, then September 2024 = Month 0, October 2024 = Month 1, etc.
- **Start dates are hardcoded** because they reflect actual onboarding dates, not HubSpot user creation dates.
