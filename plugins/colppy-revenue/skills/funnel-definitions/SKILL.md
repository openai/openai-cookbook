---
name: funnel-definitions
description: Definitions and business logic for the MQL → PQL → SQL → Deal → Customer funnel. Use when analyzing HubSpot contacts, deals, conversion rates, or funnel performance. Triggers on questions about MQLs, PQLs, SQLs, funnel stages, conversion rates, or lifecycle stages.
---

# Funnel Stage Definitions

This skill encodes the exact business definitions for each funnel stage at Virulana. These definitions have been validated against HubSpot's journey reports and should be used consistently across all analyses.

## MQL (Marketing Qualified Lead)

**Definition**: Any contact created in HubSpot, excluding `Usuario Invitado`.

**Logic**:
- A contact is created when a user signs up for the 7-day trial and validates their email
- Email validation triggers contact creation in HubSpot
- Therefore: Contact created = MQL (they took a meaningful action)

**Exclusion**: Contacts with `lead_source = 'Usuario Invitado'` are NOT MQLs. These are team member invitations sent by existing customers — they didn't sign up organically.

**HubSpot field**: `createdate`

## PQL (Product Qualified Lead)

**Definition**: A contact that activated during their trial period.

**Logic**:
- The product sets `activo = true` when the user completes meaningful actions during trial
- `fecha_activo` records WHEN activation happened

**HubSpot fields**:
- `activo` = `true` (boolean flag indicating product activation)
- `fecha_activo` = timestamp of activation (the PQL date)

**Both conditions required**: `activo = true` AND `fecha_activo` is populated.

## SQL (Sales Qualified Lead)

**Definition**: A contact that has been associated with at least one deal AND has an opportunity lifecycle stage date.

**Logic**:
- When a contact (starting as "lead") gets associated to a deal, HubSpot automatically changes their lifecycle stage to "Oportunidad" (Opportunity)
- This lifecycle change sets `hs_v2_date_entered_opportunity`
- The deal association event IS the SQL conversion, regardless of when the deal itself was created

**HubSpot fields**:
- `hs_v2_date_entered_opportunity` = timestamp of SQL conversion (when contact was associated to deal)
- `num_associated_deals` > 0 (must have at least one deal)

**CRITICAL VALIDATION**: Both conditions must be true:
1. `hs_v2_date_entered_opportunity` is populated
2. Contact has at least one deal associated

Contacts with `hs_v2_date_entered_opportunity` but ZERO deals are **manual lifecycle overrides** — someone changed their lifecycle stage by hand. These are NOT real SQLs and must be excluded.

## Deal Won / Customer

**Definition**: A contact whose associated deal was closed-won.

**HubSpot fields**:
- Deal: `hs_is_closed_won = true`
- Contact: `hs_v2_date_entered_customer` or `lifecyclestage = customer`

**Revenue**: Only count `amount` from won deals. Unwon deals contribute $0 revenue, even if they have a pipeline amount.

---

# Filtering Rules

## Excluding "Usuario Invitado"

When filtering contacts via HubSpot API, ALWAYS use TWO filters together:

```
{"propertyName": "lead_source", "operator": "HAS_PROPERTY"}
{"propertyName": "lead_source", "operator": "NEQ", "value": "Usuario Invitado"}
```

**Why both?** HubSpot's API `NEQ` operator includes contacts where the property is NULL/not set. HubSpot UI's "is none of" excludes nulls. Using HAS_PROPERTY first ensures contacts without `lead_source` are excluded, matching the HubSpot UI behavior.

Using only `NEQ` will return ~25-30 extra contacts with null `lead_source`.

## Timezone Awareness

- **HubSpot API**: Returns timestamps in UTC
- **HubSpot UI/Reports**: Uses account timezone (Argentina, UTC-3)
- **Impact**: ~25 contacts created between 00:00-02:59 UTC on the 1st of the month are actually in the PREVIOUS month in Argentina time (21:00-23:59 on the last day)
- **Acceptable**: This ~25 contact difference at month boundaries is expected and does not affect SQL/deal analysis

---

# Funnel Flow Diagram

```
Contact Created (MQL)
  │
  ├─── activo=true + fecha_activo → PQL
  │
  ├─── Associated to Deal → SQL (hs_v2_date_entered_opportunity set)
  │         │
  │         ├─── Deal Won → Customer + Revenue
  │         └─── Deal Open/Lost → SQL but no revenue
  │
  └─── No deal, no activation → MQL only
```

---

# Standard Properties to Fetch

When analyzing contacts, always request these properties:

```
email, firstname, lastname, createdate, lifecyclestage, lead_source,
activo, fecha_activo, hs_v2_date_entered_opportunity,
hs_v2_date_entered_customer, num_associated_deals, fit_score_contador
```

When analyzing deals, always request:

```
dealname, amount, dealstage, closedate, pipeline,
hs_is_closed_won, createdate, hubspot_owner_id
```

## Related Skills

- **funnel-analysis** — Analysis scripts, two-channel funnels, PQL scoring methodology
