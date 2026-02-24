# HubSpot Funnel Report: Contact Created to Deal Created Methodology

**Last Updated:** 2025-12-26  
**Source:** HubSpot Official Documentation + Codebase Analysis

---

## Overview

HubSpot's funnel reports track how contacts progress through lifecycle stages over time. When building a funnel from "Contact Created" to "Deal Created," HubSpot uses a combination of contact properties, lifecycle stages, and associations to trace the relationship.

---

## How HubSpot Builds the Funnel

### 1. **Entry Point: Contact Creation Date**

- **Field Used:** `createdate` (Contact property)
- **Filter:** Only contacts created within the specified date range are included
- **Object:** Contact object (`crm/v3/objects/contacts`)

**Key Point:** The funnel report uses the contact's actual creation timestamp, not manually modified dates. This ensures accuracy even if the `createdate` property is changed later.

### 2. **Stage Progression: Lifecycle Stages**

HubSpot tracks contacts through predefined **lifecycle stages**:

- **Subscriber** → **Lead** → **Marketing Qualified Lead (MQL)** → **Sales Qualified Lead (SQL)** → **Opportunity** → **Customer**

**Fields Used:**
- `lifecyclestage` - Current lifecycle stage of the contact
- `hs_lifecycle_stage_lead_date` - Date contact entered "Lead" stage
- `hs_lifecycle_stage_marketingqualifiedlead_date` - Date contact entered "MQL" stage
- `hs_lifecycle_stage_salesqualifiedlead_date` - Date contact entered "SQL" stage
- `hs_lifecycle_stage_opportunity_date` - Date contact entered "Opportunity" stage
- `hs_v2_date_entered_opportunity` - **KEY FIELD** - Date contact entered "Opportunity" stage (SQL conversion)

### 3. **Tracing Contact to Deal: Associations**

HubSpot links contacts to deals through **associations**:

**Association API:** `crm/v4/objects/contacts/{contactId}/associations/deals`

**Official Documentation:**
- **[HubSpot API: Associations v4](https://developers.hubspot.com/docs/guides/api/crm/associations/associations-v4)** - Complete guide on how HubSpot manages associations between CRM objects
- [HubSpot: Create and Use Association Labels](https://knowledge.hubspot.com/crm-setup/create-and-use-association-labels) - How to create custom association labels

**How It Works:**
1. When a contact enters the "Opportunity" lifecycle stage, `hs_v2_date_entered_opportunity` is set
2. HubSpot creates an association between the contact and the deal
3. The association type determines the relationship (e.g., primary contact, associated contact)

**Association Types:**
- **Type 3:** Contact to Deal (default association)
- **Type 5:** Primary Company to Deal (for company associations)

**API Endpoint Examples:**
- Get associations: `GET /crm/v4/objects/contacts/{contactId}/associations/deals`
- Create association: `PUT /crm/v4/objects/contacts/{contactId}/associations/deals/{dealId}/3`
- Batch create: `POST /crm/v4/associations/batch/create`

### 4. **Deal Creation Tracking**

**Fields Used:**
- `createdate` (Deal property) - When the deal was created
- `closedate` (Deal property) - When the deal was closed
- `dealstage` (Deal property) - Current stage of the deal

**Object:** Deal object (`crm/v3/objects/deals`)

---

## HubSpot's Funnel Report Logic

### **"All" Type Funnel Report**

Tracks contacts that have moved through **ALL** selected stages within the date range:

1. **Contact Created** (within date range) → Entry point
2. **Lifecycle Stage Changes** → Tracked via lifecycle stage date properties
3. **Opportunity Stage** → `hs_v2_date_entered_opportunity` is set
4. **Deal Created** → Deal `createdate` within date range
5. **Deal Closed** → Deal `closedate` within date range (if applicable)

### **"Any" Type Funnel Report**

Tracks contacts that have moved through **ANY** of the selected stages within the date range.

---

## Key Fields and Objects Used

### **Contact Object Properties:**
- `createdate` - Contact creation timestamp
- `lifecyclestage` - Current lifecycle stage
- `hs_v2_date_entered_opportunity` - **Critical field** for SQL/Opportunity tracking
- `hs_lifecycle_stage_*_date` - Date properties for each lifecycle stage

### **Deal Object Properties:**
- `createdate` - Deal creation timestamp
- `closedate` - Deal close timestamp
- `dealstage` - Current deal stage

### **Association Objects:**
- Contact-Deal associations (via `crm/v4/objects/contacts/{id}/associations/deals`)
- Company-Deal associations (via `crm/v4/objects/companies/{id}/associations/deals`)

---

## Important Considerations

### **1. Date Range Filtering**
- Only contacts created within the specified date range are included
- Contacts created before the date range are excluded, even if they progressed through stages during the period
- This ensures the funnel focuses on contacts generated during the specified timeframe

### **2. Stage Movement Timing**
- HubSpot tracks when contacts move between lifecycle stages
- The `hs_v2_date_entered_opportunity` field is set when a contact enters the "Opportunity" stage
- This typically corresponds to deal creation, but not always

### **3. Association Requirements**
- For a contact to be linked to a deal in the funnel, there must be an association
- Associations can be created automatically (when deal is created with contact) or manually
- Multiple contacts can be associated with the same deal

### **4. Edge Cases**
- **Deals created before contact:** Self-serve pattern where product is added before user registration
- **Contacts without deals:** SQL date exists but no deal association
- **Multiple contacts per deal:** Deal may have multiple associated contacts (earliest contact is typically used for validation)

---

## How Our Scripts Align with HubSpot's Methodology

### **Our Approach (`analyze_accountant_mql_funnel.py`):**

1. **MQL Stage:** 
   - Filter contacts by `createdate` in period
   - Filter by `rol_wizard` containing "conta" (accountant role)
   - Exclude "Usuario Invitado" from `lead_source`

2. **SQL Stage:**
   - Use `hs_v2_date_entered_opportunity` to identify SQL conversion
   - **Validate with deal association:** Contact must have a deal created between contact creation and SQL date
   - This matches HubSpot's logic of requiring associations

3. **Deal Created Stage:**
   - Fetch deals created in period
   - Filter deals that have associated MQL contacts (created before deal)
   - Uses Contact-Deal associations via `crm/v4/objects/contacts/{id}/associations/deals`

4. **Deal Closed Won Stage:**
   - Filter deals that are `closedwon` and have both `createdate` and `closedate` in period

### **Key Differences:**
- **HubSpot's funnel reports** use lifecycle stages as the primary tracking mechanism
- **Our scripts** use a **strict funnel path** (MQL → Deal Created → Won) and validate with associations
- **Our scripts** track edge cases (deals before contacts, missing associations, etc.)

---

## References

### Funnel Reports
- [HubSpot: Create Custom Funnel Reports](https://knowledge.hubspot.com/reports/create-custom-funnel-reports)
- [HubSpot: Differences Between Funnel Report Types](https://knowledge.hubspot.com/reports/differences-between-funnel-reports-types)

### Contact Properties
- [HubSpot: Default Contact Properties](https://knowledge.hubspot.com/contacts/hubspots-default-contact-properties)

### Contact-to-Deal Associations (Official Documentation)
- **[HubSpot API: Associations v4](https://developers.hubspot.com/docs/guides/api/crm/associations/associations-v4)** - **PRIMARY DOCUMENTATION** - How to create, retrieve, and manage associations between CRM objects
- [HubSpot: Create and Use Association Labels](https://knowledge.hubspot.com/crm-setup/create-and-use-association-labels) - How to create custom association labels for contact-deal relationships
- [HubSpot API: Associations Reference](https://developers.hubspot.com/docs/api/crm/associations) - API reference for associations endpoints

### Association Type IDs
- **Contact to Deal Association Type ID: 3** (default association)
- **Company to Deal Association Type ID: 5** (primary company association)

---

## Summary

**HubSpot's funnel methodology:**
1. Uses `createdate` to filter contacts by creation date
2. Tracks progression through lifecycle stages using date properties
3. Links contacts to deals through associations
4. Uses `hs_v2_date_entered_opportunity` as the key field for SQL/Opportunity tracking
5. Validates relationships through Contact-Deal associations

**Our scripts enhance this by:**
- Adding role-based filtering (accountant vs SMB)
- Validating deal associations for SQL stage
- Tracking edge cases and providing detailed analysis
- Using strict funnel path (MQL → Deal → Won) for accuracy

