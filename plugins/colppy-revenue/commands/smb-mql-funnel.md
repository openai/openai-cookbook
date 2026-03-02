---
name: smb-mql-funnel
description: Full SMB (PYME) funnel analysis — MQL → SQL → Deal Created → Deal Closed Won with ICP classification
---

# /smb-mql-funnel

Run a complete SMB (PYME) funnel analysis: MQL PYME → SQL → Deal Created → Deal Closed Won, with ICP classification on won deals.

## Usage

```
/colppy-revenue:smb-mql-funnel 2026-02
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                   SMB MQL FUNNEL                                │
├─────────────────────────────────────────────────────────────────┤
│  1. Fetch contacts created in month with SMB rol_wizard         │
│  2. Identify SQLs (opportunity date + deals in period)          │
│  3. Fetch deal details for SQL contacts                         │
│  4. Filter closed-won deals (created + closed in period)        │
│  5. Classify won deals by ICP (PRIMARY company type)            │
│  6. Build funnel + conversion rates + revenue analysis          │
└─────────────────────────────────────────────────────────────────┘
```

---

## What I Need From You

- **Month**: Which month to analyze (e.g. "2026-02", "january 2026", "last month")
- **MTD or full month**: If current month, I'll do month-to-date automatically

---

## Step-by-Step Execution

### Step 1: Fetch SMB Contacts Created in Period

Search HubSpot contacts with these filters (ALL must match):
- `createdate` GTE `{month}-01T00:00:00Z`
- `createdate` LTE `{last-day-of-month}T23:59:59Z`
- `lead_source` HAS_PROPERTY (exclude nulls)
- `lead_source` NEQ `Usuario Invitado` (exclude team invitations)

**CRITICAL**: Always use HAS_PROPERTY + NEQ together for lead_source filtering. Using only NEQ includes contacts where lead_source is null.

Fetch these properties:
`email, createdate, firstname, lastname, lead_source, rol_wizard, hs_v2_date_entered_opportunity`

### Step 2: Filter to SMB Contacts Only

From the fetched contacts, keep only those with an **SMB rol_wizard**:

**Exclude** contacts where `rol_wizard` is:
- `null` or empty (unknown role — exclude)
- `contador` (accountant)
- `estudio contable` (accounting firm)
- `contador público` (public accountant)
- `asesor contable` (accounting advisor)

All other rol_wizard values are SMB. This is the **MQL PYME** count.

### Step 3: Identify SQL Contacts

A contact is SQL if ALL of these are true:
- `hs_v2_date_entered_opportunity` is populated
- The opportunity date falls within the analysis period
- Contact has **at least 1 deal associated** (check via associations API)

**IMPORTANT**: Contacts with `hs_v2_date_entered_opportunity` but 0 deals are NOT real SQLs — they are manual lifecycle overrides. Exclude them.

For each SQL contact, fetch associated deals using: contacts → deals associations.

### Step 4: Fetch Deal Details and Apply Strict Funnel Rules

For each deal associated with SQL contacts, fetch:
`dealname, createdate, closedate, dealstage, amount, hs_archived`

**Strict funnel rule**: The contact must have been created BEFORE the deal:
- `contact_createdate < deal_createdate`
- If a deal was created before the contact, exclude it from this funnel (it belongs to a different acquisition path)

**Deal Created in Period**: Deal `createdate` falls within the analysis month.

### Step 5: Identify Closed-Won Deals

A deal is closed-won if ALL of these are true:
- `dealstage` = `closedwon`
- `createdate` falls within the analysis period
- `closedate` falls within the analysis period
- Not archived (`hs_archived` != true)

**Revenue**: Only count amounts from closed-won deals.

### Step 6: Classify Won Deals by ICP (PRIMARY Company)

For each closed-won deal:
- Get associated companies via deals → companies associations
- Find the **PRIMARY company** (association Type ID 5)
- Get the company `type` property

**Accountant**: Company type is `Cuenta Contador`, `Cuenta Contador y Reseller`, or `Contador Robado`
**SMB**: Any other company type

### Step 7: Build Funnel Table

```
Stage                              │ Count    │ % of Previous │ % of MQL
───────────────────────────────────┼──────────┼───────────────┼──────────
1. MQL PYME (SMB contacts)         │ {n}      │ —             │ 100.0%
2. SQL (Opportunity + Deal)        │ {n}      │ {x}%          │ {x}%
3. Deal Created (in period)        │ {n}      │ {x}%          │ {x}%
4. Deal Closed Won (in period)     │ {n}      │ {x}%          │ {x}%
```

### Step 8: ICP Classification of Won Deals

```
ICP (Won Deals)     │ Deals  │ Revenue    │ % of Won Deals │ % of Revenue
────────────────────┼────────┼────────────┼────────────────┼─────────────
Contador            │ {n}    │ ${x}       │ {x}%           │ {x}%
PYME                │ {n}    │ ${x}       │ {x}%           │ {x}%
Unclassified        │ {n}    │ ${x}       │ {x}%           │ {x}%
```

### Step 9: SQL Contact Detail Table

For each SQL contact, show:

| Email | Created | SQL Date | Rol Wizard | Deals | Won | Revenue | ICP |
|-------|---------|----------|------------|-------|-----|---------|-----|

### Step 10: Edge Cases Report

Track and report:
- SQL contacts with `hs_v2_date_entered_opportunity` but no deals (excluded from SQL count)
- Deals created before the contact (excluded from funnel)
- Won deals without PRIMARY company (data quality flag)

---

## Important Notes

- **SMB definition**: Any `rol_wizard` that is NOT an accountant role and NOT null/empty.
- **Accountant roles** (case-insensitive): `contador`, `estudio contable`, `contador público`, `asesor contable`
- **Strict funnel**: Contact must be created BEFORE the deal (contact_created < deal_created).
- **Revenue**: Only from closed-won deals where both `createdate` and `closedate` fall in the period.
- HubSpot API uses UTC. UI uses Argentina (UTC-3). ~25 contact difference at month boundaries.
- ICP is based on PRIMARY company type (Type ID 5), not plan name.
