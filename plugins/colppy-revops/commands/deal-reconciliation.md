---
name: deal-reconciliation
description: Reconcile script/report results against HubSpot deal data — verify SQL contacts and their deals match
---

# /deal-reconciliation

Verify that SQL contacts and their deal associations match between analysis results and HubSpot's actual data. Use this to validate funnel numbers or debug discrepancies.

## Usage

```
/colppy-revops:deal-reconciliation 2026-02
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                  DEAL RECONCILIATION                             │
├─────────────────────────────────────────────────────────────────┤
│  1. Find all SQL contacts for the month                          │
│  2. Look up every deal associated with each contact              │
│  3. Check deal stage, amount, close date, won status             │
│  4. Compare against HubSpot journey report numbers               │
│  5. Flag any discrepancies                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Execution

### Step 1: Find SQL Contacts

Search contacts created in the month with:
- `hs_v2_date_entered_opportunity` populated (in period)
- `lead_source` HAS_PROPERTY + NEQ `Usuario Invitado`
- Then verify each has `num_associated_deals` > 0

### Step 2: For Each SQL Contact, Get Deal Details

Use HubSpot associations API to get deals for each contact.
For each deal, fetch: `dealname, amount, dealstage, closedate, pipeline, hs_is_closed_won, createdate`

### Step 3: Build Reconciliation Table

| Contact Email | SQL Date | # Deals | Deal Names | Won? | Revenue (Won) | Deal Stage |
|--------------|----------|---------|------------|------|---------------|------------|

### Step 4: Summary Totals

```
Total SQL contacts: {n}
Total deals associated: {n}
Won deals: {n}
Total won revenue: ${x}
```

### Step 5: Flag Issues

Check for:
- **False SQLs**: Contacts with `hs_v2_date_entered_opportunity` but 0 deals → manual lifecycle override
- **Revenue mismatches**: Unwon deals should show $0 revenue (not pipeline amount)
- **Missing contacts**: If HubSpot journey report shows different count, check timezone (UTC vs Argentina UTC-3) and null lead_source contacts

---

## Common Discrepancies & Explanations

| Issue | Explanation |
|-------|-------------|
| Script has more contacts than HubSpot report | HubSpot UI uses account timezone (UTC-3), API uses UTC. ~25 contacts at month boundary may shift. |
| Contact has SQL date but 0 deals | Manual lifecycle override — not a real SQL. Should be excluded. |
| Revenue doesn't match HubSpot | Only won deals count revenue. Unwon deals = $0 in analysis. HubSpot may show pipeline amount. |
| Contact appears in script but not HubSpot | Check if contact has null lead_source (should be excluded with HAS_PROPERTY filter). |
