# Colppy Complete Funnel Mapping - Comprehensive Documentation

## 📋 Document Purpose

This document provides a complete mapping of all funnels in Colppy's customer journey, organized by multiple dimensions.

**Last Updated**: 2025-12-24  
**Status**: Living document - update as new funnels are identified  
**Recent Updates**: 
- SQL definition updated to include deal validation requirement (contact must have deal created between `createdate` and `hs_v2_date_entered_opportunity` within analysis period)
- Added MQL Funnel Analysis Scripts documentation with strict funnel logic (MQL → Deal Created → Won)

---

## 🎯 Organization Methods

This document is structured to support multiple ways of analyzing funnels:

1. **By Entry Point** (Starting Point)
2. **By Conversion Type**
3. **By Lifecycle Stage**
4. **By Channel**
5. **By Outcome**
6. **By Time Period**

---

## 🎯 CRITICAL DEFINITION: What is a "Lead" in Colppy?

**Colppy's Definition of a Lead:**
- A "Lead" in Colppy = **Contact with an associated Lead object**
- **NOT** just a contact with `lifecyclestage = 'lead'`
- Requires a **Lead object** to be created and associated with the contact
- A contact **cannot be a Lead** without an associated Lead object, regardless of lifecycle stage

**Key Distinction:**
- `lifecyclestage = 'lead'` is just a property on the contact (lifecycle stage)
- A "Lead" in Colppy requires an actual **Lead object** (separate HubSpot object) associated with the contact
- Contacts can have `lifecyclestage = 'lead'` but still NOT be Leads if they don't have an associated Lead object

**How to Identify if a Contact is a Lead:**
1. Check for associated Lead object using `hubspot-list-associations` (contact → leads)
2. If results exist: Contact HAS Lead object = IS a Lead in Colppy's system
3. If empty: Contact has NO Lead object = NOT a Lead (even if `lifecyclestage = 'lead'`)

**Lead Object Creation Methods:**
1. **Workflow-Created (Automatic)**: HubSpot workflow automatically creates Lead object and associates it with contact
   - Source: `AUTOMATION_PLATFORM`
   - For Colppy integration contacts
2. **Manual Creation**: Salesperson manually creates Lead object and associates it with contact
   - Source: `CRM_UI` (in `hs_created_by_user_id` property history)
   - For Intercom integration contacts

**How to Determine Lead Creation Type:**
1. Get Lead object: `hubspot-batch-read-objects` (leads)
2. Get property history: `propertiesWithHistory=['hs_created_by_user_id']`
3. Check `sourceType` in property history:
   - `CRM_UI` = Manual creation by salesperson
   - `AUTOMATION_PLATFORM` = Workflow creation
   - `INTEGRATION` = Integration creation
4. Compare timing: Lead `createdate` vs Contact `createdate`
   - Manual: Minutes/hours difference
   - Workflow: Seconds difference

---

## 🎯 CRITICAL DISTINCTION: lead_source vs initial_utm

**lead_source (Current Classification):**
- **Purpose**: Current source classification/tracking
- **Can be changed**: Yes, by sales/forms/workflows
- **Represents**: Current categorization (may not reflect original source)
- **Use cases**: 
  - Current channel identification
  - Reporting and segmentation
  - Identifying invitation contacts (`lead_source = 'Usuario Invitado'`)
- **Limitation**: May not reflect original marketing source if reclassified

**initial_utm (Original Marketing Attribution):**
- **Purpose**: Original marketing attribution (first touch)
- **Can be changed**: No (immutable)
- **Represents**: Original marketing source before any reclassification
- **Use cases**:
  - Identifying original MQLs
  - Verifying true marketing attribution
  - Distinguishing reclassified contacts from true channel contacts
- **Advantage**: Preserves original source even when `lead_source` is changed

**Key Implication:**
- **For MQL Identification**: Use `initial_utm_source` (more reliable, shows original marketing source)
- **For Current Classification**: Use `lead_source` (shows how contact is currently categorized)
- **Example**: Contact may have `lead_source = 'Referencia Externa Pyme'` (changed by sales) but `initial_utm_source = 'google'` (original Google PPC source), indicating it was originally an MQL

---

## 🔧 HUBSPOT CONTACT LIFECYCLE MECHANICS

This section explains how contacts move through HubSpot's lifecycle stages and how Colppy's system works. This is NOT a funnel - it's the underlying mechanics that all funnels use.

### Contact Lifecycle Progression

**Lifecycle Stages**:
```
Contact Created (createdate)
    ↓
Lead (lifecyclestage = 'lead')
    ↓
├─► MQL (hs_v2_date_entered_lead) - Marketing Qualified Lead
    │   (Requires: Lead object + Trial signup + Email validated "Validó email" event)
│   └─► SQL (hs_v2_date_entered_opportunity) - Sales Qualified Lead
│       └─► Deal Created
│           └─► Customer (lifecyclestage = 'customer')
│
└─► PQL (activo = 'true', fecha_activo) - Product Qualified Lead
    └─► Customer (lifecyclestage = 'customer')
```

**HubSpot Fields**:
- `createdate` (UI: "Create Date") - Entry point timestamp
- `lifecyclestage` (UI: "Lifecycle Stage") - Current lifecycle stage
- `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") - MQL qualification date
- `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - SQL qualification date
- `activo` (UI: "Hizo evento clave en trial") - PQL key event flag ('true')
- `fecha_activo` (UI: "Fecha de Hizo Evento Clave en Trial") - PQL key event date
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer conversion date

**Cycle Time Calculations**:
- Contact → Lead: Lead objects are created and associated with contacts
  - **Important**: In Colppy, a "Lead" requires an associated Lead object, NOT just `lifecyclestage = 'lead'`
  - **Lead Object Creation**: Lead objects can be created by workflow (automatic) or manually by salesperson
  - **Lifecycle Stage**: `lifecyclestage = 'lead'` is set by integration or workflow, but this alone does NOT make a contact a Lead in Colppy's system
    - **Invitation Exception**: Contacts with `lead_source = 'Usuario Invitado'` do NOT get Lead objects created
    - **Invitation Contacts - Complete Definition**:
      - **What are they?**: Contacts created when existing customers invite team members to their account
      - **Identification**: Should have `lead_source = 'Usuario Invitado'`
      - **Expected Behavior**: Should NOT have Lead object (contact without Lead object = invitation)
      - **Not MQLs**: These are NOT considered MQLs - they are new contacts from the product but have no value, only the record
      - **Why no Lead?**: These users should NOT be contacted by sales team (they're already part of a customer account)
      - **Workflow Logic**: HubSpot workflow identifies invitation contacts and skips lead creation (should not be contacted by sales team)
      - **Data Inconsistencies**: Some invitation contacts may have different `lead_source` values or may have been created before workflow logic was implemented, resulting in Lead status being set
      - **Mixpanel Activity**: Have no product activity (no replays, no "Validó email" event) since they're added to existing customer accounts
      - **Result**: Contact created, but no Lead object associated (not a Lead in Colppy's system)
  - **Lead Object Creation Methods** (for non-invitation contacts):
    1. **Workflow-Created (Automatic)**: HubSpot workflow automatically creates Lead object and associates it with contact
       - Source: `AUTOMATION_PLATFORM` (in Lead object property history)
       - For Colppy integration contacts
       - User signed up for trial, received validation email, entered code → Has "Validó email" event in Mixpanel → Can become MQL
    2. **Manual Creation**: Salesperson manually creates Lead object and associates it with contact
       - Source: `CRM_UI` (in Lead object `hs_created_by_user_id` property history)
       - For Intercom integration contacts
       - Created by sales team → May NOT have "Validó email" event (never signed up or signed up but didn't validate) → Cannot become MQL until user validates email
  - **Critical Distinction**: 
    - **Workflow-Created Leads**: Lead object created automatically by workflow → User signed up for trial → Has "Validó email" event in Mixpanel → Can become MQL
    - **Manual-Created Leads**: Lead object created manually by salesperson → May NOT have "Validó email" event → Cannot become MQL until user validates email
    - **Invitation Contacts**: Created from existing customer invitations → NO Lead object created → Cannot become MQL (not meant for sales contact)
    - **Lifecycle Stage Note**: `lifecyclestage = 'lead'` is set by integration or workflow, but this is separate from Lead object creation. A contact with `lifecyclestage = 'lead'` but no associated Lead object is NOT a Lead in Colppy's system.
- Contact → MQL: `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")
  - **What is MQL?**: Marketing Qualified Lead (HubSpot terminology) - a lead that has signed up for trial AND validated their email in Colppy. **Note**: Qualification is automatic via HubSpot workflows - no marketing person is involved.
  - **SIMPLIFIED MQL DEFINITION FOR ANALYSIS**: 
    - **All contacts created (excluding 'Usuario Invitado') are considered MQLs**
    - When a user signs up for the 7-day free trial and validates their email, a contact is created in HubSpot
    - Therefore: **Contact created (excluding 'Usuario Invitado') = MQL**
    - **EXCLUSION**: Contacts with `lead_source = 'Usuario Invitado'` are NOT MQLs
      → These are team member invitations from existing customers
      → They are NOT new contacts starting from trial period
      → They should be excluded from all analysis
  - **DETAILED MQL Requirements** (for technical verification, ALL must be met):
    1. **Contact must have Lead object**: Contact must have an associated Lead object (created by workflow, not manual)
    2. **User signed up for trial**: User must have signed up for the 7-day free trial in Colppy
    3. **Email validated in Colppy**: Contact must have "Validó email" event in Mixpanel
      - **Critical**: "Validó email" is one of the FIRST events a user does in the platform (part of trial signup/email validation flow)
      - **If this event exists**: User signed up on the signup page, received validation email with code, and entered the code to validate their email → True MQL candidate
      - **If this event does NOT exist**: User signed up on the signup page, platform sent them an email with a code, but the user never entered the code to validate the email → Sales-created lead or incomplete signup → NOT an MQL
    - **How to Verify "Validó email" Event**:
      - Check Mixpanel for "Validó email" event for each email
      - This event occurs when user enters the validation code from the email (one of the FIRST events after signup)
      - If event exists → User signed up, received validation email with code, and entered the code to validate their email → True MQL candidate
      - If event does NOT exist → User signed up on the signup page, platform sent them an email with a code, but the user never entered the code to validate the email → Sales-created lead or incomplete signup
    4. **MQL qualification date set**: `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") must be populated
  - **MQL Characteristics**:
    - **UTM Sources**: MQLs have UTM parameters (`utm_source`, `utm_campaign`, `utm_medium`) set by the visitor at original access
    - **Lead Source**: Lead source doesn't matter for MQL qualification - could be anywhere (organic, paid, referral, etc.)
    - **Lead Object**: Created by workflow (source: `AUTOMATION_PLATFORM`), not manually
  - **Critical Rule**: The ONLY way to have a new Lead MQL in Colppy is:
    - User signs up for trial
    - User validates their email ("Validó email" event)
    - Lead source doesn't matter - could be anywhere
    - UTM sources don't matter for MQL qualification - if there's a new signup, marketing had something to do with it
  - **When is it set?**: `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") is set automatically by HubSpot workflows when a lead meets qualification criteria (via HubSpot lead scoring workflow, triggered automatically after email validation). **Note**: This is an automatic system process - no marketing person is involved in qualification.
  - **Pattern**: MQL qualification happens very quickly (minutes, not days), suggesting automatic qualification via HubSpot lead scoring workflow after email validation
  - **Never (null)**: Many contacts never become MQLs (go directly to SQL, don't validate email, or remain as leads)
  - **Important Note**: Not all contacts become MQLs. Many skip MQL stage and go directly from Lead → SQL, or remain as leads without qualification. For contacts that DO become MQLs, they must have signed up for trial AND validated their email in Colppy ("Validó email" event in Mixpanel).
  - **Sales-Created Leads**: Leads created by sales team (Intercom, manual entry) CANNOT be MQLs until they sign up for trial AND validate their email. These leads may not sign up for trial immediately, so they remain as "Leads" without email validation until they engage with the product.
  - **Contacts without Lead objects**: If a contact doesn't have a Lead object, it's a user invitation (not an MQL). These are considered new contacts from the product but have no value, only the record.
  - **No UTM Sources**: If there are no UTM parameters, the contact was created manually by a HubSpot salesperson via UI (not an MQL until they sign up and validate email).
  - **Incomplete Signups**: Users who sign up on the signup page but never enter the validation code from their email will NOT have the "Validó email" event, and therefore cannot be MQLs even if they have Lead status and MQL qualification in HubSpot.
- Contact → SQL: `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")
- Contact → PQL: `fecha_activo` (UI: "Fecha de Hizo Evento Clave en Trial") - `createdate` (UI: "Create Date")
  - **Note**: `fecha_activo` is date-only (no time). If both dates are on the same calendar day, cycle time = 0.0 days.
- Contact → Customer: `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")

---

## 📊 METHOD 1: FUNNELS BY ENTRY POINT

Organizes funnels based on where contacts first enter the system.

### 1.1 PQL Funnel (Product-Led Entry)

**Entry Point**: User signs up for 7-day free trial

**Critical Characteristics**:
- Same starting point as MQL Funnel: 7-day trial signup
- Product-led entry point
- User self-serves through trial
- Critical events (key product events) drive qualification (required for PQL)

**Funnel Stages**:
```
Trial Signup
    ↓
Critical Events (key events triggered)
    ↓
PQL (activo = 'true', fecha_activo)
    ↓
├─► SQL (hs_v2_date_entered_opportunity) - Sales engagement
│   └─► Deal Created
│       └─► Customer (lifecyclestage = 'customer')
│
└─► Direct Customer (lifecyclestage = 'customer') - Self-service conversion
```

**Key Metrics**:
- **Trial Signup Rate**: Trial signups / website visitors
- **Key Event Rate**: Users with key events / trial signups
- **PQL Conversion Rate**: PQLs / trial signups
- **PQL → SQL Rate**: SQLs from PQL cohort / total PQLs
- **PQL → Customer Rate**: Customers from PQL cohort / total PQLs

**HubSpot Fields**:
- `createdate` - Trial signup date
- `activo` (UI: "Hizo evento clave en trial") - PQL key event flag
- `fecha_activo` (UI: "Fecha de Hizo Evento Clave en Trial") - PQL key event date
- `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - SQL qualification date
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer conversion date

**Mixpanel Events**:
- Invoice Created
- Payment Processed
- Report Generated
- User Login
- Feature Used

**UTM Attribution**:
- `utm_source` - Last touch traffic source
- `utm_campaign` - Last touch campaign name
- `utm_medium` - Last touch marketing medium
- `initial_utm_source` - First touch traffic source (original marketing attribution, immutable)
- `initial_utm_campaign` - First touch campaign name (original marketing attribution, immutable)
- `initial_utm_medium` - First touch marketing medium (original marketing attribution, immutable)

**Cycle Times**:
- Trial → PQL: `fecha_activo` (UI: "Fecha de Hizo Evento Clave en Trial") - `createdate` (UI: "Create Date")
  - **Note**: `fecha_activo` is date-only (no time). If both dates are on the same calendar day, cycle time = 0.0 days.
- PQL → SQL: `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - `fecha_activo` (UI: "Fecha de Hizo Evento Clave en Trial")
  - **Critical**: Chronological order matters - only calculate when PQL comes BEFORE SQL (fecha_activo < hs_v2_date_entered_opportunity)
  - **Purpose**: Identify which comes first to understand the sequence of events (product-led vs sales-led)
- PQL → Customer: `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - `fecha_activo` (UI: "Fecha de Hizo Evento Clave en Trial")

**Patterns/Characteristics**:
- Product-led growth (PLG) model
- Self-service conversion path available
- Sales engagement optional (can convert directly to customer)

**Use Cases**:
- Measuring PLG effectiveness
- Tracking key event rates
- Identifying self-service vs sales-assisted conversions

**Data Quality Considerations**:
- Product events tracked in Mixpanel
- HubSpot and Mixpanel data must be correlated
- Critical events (key product events) drive PQL qualification

---

### 1.2 MQL Funnel (Marketing-Led Entry)

**Entry Point**: User signs up for 7-day free trial

**Critical Characteristics**:
- Same starting point as PQL Funnel: 7-day trial signup
- Marketing-led entry point (user comes from marketing channels)
- Requires email validation for MQL qualification
- User may or may not perform critical events in product (unlike PQL which requires critical events)

**Funnel Stages**:
```
Trial Signup (7-day free trial)
    ↓
Email Validation ("Validó email" event in Mixpanel)
    ↓
Lead (lifecyclestage = 'lead', Lead object created by workflow)
    ↓
MQL (hs_v2_date_entered_lead)
    ↓
SQL (hs_v2_date_entered_opportunity)
    ↓
Deal Created
    ↓
Customer (lifecyclestage = 'customer')
```

**Key Metrics**:
- **Trial Signup Rate**: Trial signups / website visitors
- **Email Validation Rate**: Users with "Validó email" event / trial signups
- **Lead Conversion Rate**: Leads / trial signups
- **MQL Conversion Rate**: MQLs / trial signups
- **SQL Conversion Rate**: SQLs / MQLs
- **Deal Creation Rate**: Deals / SQLs
- **Win Rate**: Won deals / total deals

**HubSpot Fields**:
- `createdate` - Trial signup date
- `lifecyclestage` - Current lifecycle stage
- `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") - MQL qualification date
- `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - SQL qualification date
- `num_associated_deals` - Number of associated deals
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer conversion date

**Mixpanel Events**:
- "Validó email" - Email validation event (required for MQL)
- Product events after trial signup (optional - user may not perform critical events)

**UTM Attribution**:
- `utm_source` - Last touch traffic source
- `utm_campaign` - Last touch campaign name
- `utm_medium` - Last touch marketing medium
- `initial_utm_source` - First touch traffic source (original marketing attribution, immutable)
- `initial_utm_campaign` - First touch campaign name (original marketing attribution, immutable)
- `initial_utm_medium` - First touch marketing medium (original marketing attribution, immutable)

**Cycle Times**:
- Trial Signup → Lead: Lead object creation
- Trial Signup → MQL: `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")
- Trial Signup → SQL: `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")
- Trial Signup → Customer: `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")

**Patterns/Characteristics**:
- Marketing-driven acquisition
- UTM parameters track attribution
- MQL qualification requires trial signup and email validation
- User may not perform critical events in product (unlike PQL which requires critical events)

**Use Cases**:
- Measuring marketing campaign effectiveness
- Tracking trial signup to customer conversion
- Analyzing UTM attribution performance
- Comparing MQL vs PQL conversion paths

**Data Quality Considerations**:
- Trial signup is the starting point (same as PQL funnel)
- Email validation is required for MQL qualification
- User may not perform critical events in product (different from PQL)

---

### 1.3 Intercom → HubSpot Funnel (Sales-Led, No Trial Entry)

**Entry Point**: User contacts sales team through Intercom chat/support

**Critical Characteristics**:
- **NO Trial Signup**: User does NOT sign up for 7-day free trial at this point
- **Contact Creation**: Contact created by Intercom integration in HubSpot
- **Lifecycle Stage**: Integration sets `lifecyclestage = 'lead'` directly (source: `INTEGRATION`)
- **Lead Source Attribution**: `lead_source` is set to "Orgánico" (Label: "Orgánico / Directo") by HubSpot workflow
  - Attribution is Intercom, but we don't know how they got to Intercom at the time of contact creation
  - Set by AUTOMATION_PLATFORM (HubSpot workflow) automatically when contact is created
  - SourceId format: `enrollmentId:XXXXX;actionExecutionIndex:2` (HubSpot workflow enrollment)
  - "Orgánico" includes both organic and direct traffic
  - NOT "Referencia Intercom" (that's only for form submissions, not integration-created contacts)
  - **Important**: Intercom DOES capture UTM parameters when user visits website, but HubSpot integration does NOT pass UTM from Intercom to HubSpot. If user later signs up for trial, `initial_utm_source` may be set retroactively by integration 453475, revealing the REAL original marketing source (e.g., Google PPC) from the original website visit
- **Lead Object Creation**: Lead object is created MANUALLY by salesperson (not automatic)
  - At this point, you only have a contact (not a Lead yet)
  - Salesperson manually creates Lead object and associates it with contact
  - Source: `CRM_UI` (in Lead object `hs_created_by_user_id` property history)
- **Initial State - NOT an MQL**: Initially, this is NOT an MQL because there's no event in the product - it's just a question/lead from Intercom
- **No Product Activity Initially**: No product events in Mixpanel until user later signs up for trial (if directed by sales)
- **Bidirectional Conversation Flow**: Conversations happen in both Intercom and HubSpot, with all interactions integrated into HubSpot
  - User starts chatting in Intercom → Contact created in HubSpot
  - Sales team can continue conversation in HubSpot (notes, emails, calls)
  - Conversation can also continue in Intercom (chat continues)
  - All conversations (both HubSpot and Intercom) are integrated/synced into HubSpot
- **Trial Signup Can Happen Later**: If salesperson directs user to sign up for trial, user can sign up at any point
  - This may create a NEW contact OR update the existing Intercom contact
  - When user signs up and validates email, MQL qualification happens (hs_v2_date_entered_lead)
  - Then user can perform critical events → PQL (activo = 'true', fecha_activo)
  - This MQL/PQL path happens IN PARALLEL with the SQL process
  - User can have both SQL and PQL (overlap scenario)

**Funnel Stages**:
```
User Visits Website → Starts Chatting in Intercom → Talks with Sales Team
    ↓
Contact Created in HubSpot (lead_source = 'Orgánico' - set by workflow)
    ↓
Lifecycle Stage Set (lifecyclestage = 'lead') - Set by Intercom integration directly
    ↓
Lead Object Created - MANUALLY by salesperson (associates Lead object with contact)
    ↓
Sales Engagement in HubSpot:
    ├─► First Outreach (hs_first_outreach_date)
    ├─► First Engagement (hs_sa_first_engagement_date)
    └─► Lead Status Changes (last_lead_status_date)
    ↓
├─► SQL Path (Sales-Led):
│   └─► SQL (hs_v2_date_entered_opportunity)
│       └─► Deal Created
│           └─► Customer (lifecyclestage = 'customer')
│
└─► MQL/PQL Path (If User Signs Up for Trial - Can Happen in Parallel):
    └─► [Optional] Sales Directs User to Sign Up for Trial
        └─► User Signs Up for Trial (7-day free trial)
            └─► Email Validation ("Validó email" event)
                └─► MQL (hs_v2_date_entered_lead) - May be same contact or NEW contact
                    └─► Product Events Start in Mixpanel
                        └─► PQL (activo = 'true', fecha_activo) - If user performs critical events
                            └─► Can happen IN PARALLEL with SQL process
                            └─► User can have both SQL and PQL (overlap scenario)
```

**Key Metrics**:
- **Intercom Contact Rate**: Contacts from Intercom / total Intercom conversations
- **HubSpot Lead Creation Rate**: HubSpot Lead objects created / Intercom contacts
  - **Note**: In Colppy, a "Lead" requires an associated Lead object, NOT just `lifecyclestage = 'lead'`
  - Lead objects for Intercom contacts are created manually by salesperson
- **Qualification Rate**: Qualified leads / Intercom contacts
- **Time to Qualification**: `hs_v2_date_entered_opportunity - createdate`
- **Trial Signup Rate (Later)**: Users who later sign up for trial / Intercom contacts
- **MQL Conversion Rate (After Trial)**: MQLs from Intercom contacts / Intercom contacts who signed up for trial
- **PQL Conversion Rate (After Trial)**: PQLs from Intercom contacts / Intercom contacts who signed up for trial
- **SQL + PQL Overlap Rate**: Contacts with both SQL and PQL / Intercom contacts

**HubSpot Fields**:
- `lead_source = 'Orgánico'` (Label: "Orgánico / Directo") - Source tracking
  - Attribution is Intercom, but we don't know how they got to Intercom
  - Set by AUTOMATION_PLATFORM (workflow) to indicate unknown attribution
  - Includes both organic and direct traffic
  - NOT "Referencia Intercom" (that's only for form submissions)
- `createdate` - Contact creation date in HubSpot
- `lifecyclestage = 'lead'` - Lead lifecycle stage (set by Intercom integration)
- `hs_first_outreach_date` - First sales outreach
- `hs_sa_first_engagement_date` - First engagement with current owner
- `hs_v2_date_entered_lead` - MQL qualification date (set if user later signs up for trial and validates email)
- `hs_v2_date_entered_opportunity` - SQL qualification date
- `last_lead_status_date` - Last lead status change

**Mixpanel Events**:
- **"Qualification"** - Only event fired when HubSpot qualification happens (SQL)
- **"Validó email"** - Email validation event (if user signs up for trial)
  - **Critical**: This event is required for MQL qualification
  - Only appears if user signs up for trial and enters validation code
- **Product events** (Invoice Created, Payment Processed, etc.) only appear if user performs critical events after trial signup
  - These events can happen in parallel with SQL process
  - User can have both SQL and PQL (overlap scenario)

**UTM Attribution**:
- **Intercom Captures UTM**: When user visits website with UTM parameters and clicks Intercom chat, Intercom DOES capture UTM parameters (e.g., `utm_source`, `utm_campaign`, `utm_medium`)
- **HubSpot Integration Does NOT Pass UTM**: When Intercom contact is created in HubSpot via integration, UTM parameters are NOT passed from Intercom to HubSpot
- **At Contact Creation in HubSpot**: Intercom contacts have NO UTM parameters in HubSpot initially (attribution unknown)
- **Retroactive Attribution**: If user later signs up for trial, `initial_utm_source` may be set retroactively by integration 453475
  - This comes from the original website visit (not from Intercom)
  - This reveals the REAL original marketing source (e.g., Google PPC campaigns)
  - Set minutes to days after Intercom contact creation
  - Examples: "google" (Google PPC), "App Mobile Colppy" (App Store campaigns)
- **Pattern**: 
  - Contacts WITHOUT trial signup: `initial_utm_source` remains null
  - Contacts WITH trial signup: `initial_utm_source` set retroactively (reveals original source from website visit)
- **Why This Matters**: Even though `lead_source = 'Orgánico'` (unknown at Intercom creation) and UTM is not passed from Intercom, `initial_utm_source` can reveal the actual marketing channel from the original website visit

**Cycle Times**:
- Contact → Lead: Lead object creation (manual by salesperson)
- Contact → SQL: `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")
- Contact → MQL (if trial signup): `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")
  - **Note**: Only if user signs up for trial and validates email
- Contact → PQL (if critical events): `fecha_activo` (UI: "Fecha de Hizo Evento Clave en Trial") - `createdate` (UI: "Create Date")
  - **Note**: `fecha_activo` is date-only (no time). If both dates are on the same calendar day, cycle time = 0.0 days.
  - **Note**: Only if user performs critical events after trial signup
  - **Critical**: Chronological order matters - identify which comes first (PQL or SQL)
- Contact → Customer: `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")

**Patterns/Characteristics**:
1. **Business Email Domains**: Have business email domains (corporate/organizational email addresses)
2. **Fast Sales Outreach**: Receive sales outreach quickly after creation
3. **Contact Creation**: Contact created by Intercom integration when user starts chatting
4. **Lead Source Attribution**: `lead_source` is set to "Orgánico" (not "Referencia Intercom") by HubSpot workflow
   - Attribution is Intercom, but we don't know how they got to Intercom at the time of contact creation
   - Set by AUTOMATION_PLATFORM (HubSpot workflow) automatically when contact is created
   - SourceId format: `enrollmentId:XXXXX;actionExecutionIndex:2` (HubSpot workflow enrollment)
   - "Orgánico" (Label: "Orgánico / Directo") includes both organic and direct traffic
   - "Referencia Intercom" is only used when Intercom form is submitted (not for integration-created contacts)
   - **Important**: Intercom DOES capture UTM parameters when user visits website, but HubSpot integration does NOT pass UTM from Intercom to HubSpot
   - **Retroactive Attribution**: If user later signs up for trial, `initial_utm_source` may be set retroactively by integration 453475, revealing the REAL original marketing source (e.g., Google PPC campaigns) from the original website visit
5. **Manual Lead Object Creation**: Lead objects are created manually by salesperson (not automatic)
   - At this point, you only have a contact (not a Lead yet)
   - Salesperson manually creates Lead object and associates it with contact
   - Source: `CRM_UI` (in Lead object `hs_created_by_user_id` property history)
6. **Lifecycle Stage**: `lifecyclestage = 'lead'` is set by Intercom integration directly (source: `INTEGRATION`)
   - **Important**: Setting `lifecyclestage = 'lead'` does NOT automatically create a Lead object
   - Lead object must be created separately (manually by salesperson)
7. **Trial Signup Can Trigger MQL/PQL**: If salesperson directs user to sign up for trial:
   - User signs up for trial (may create new contact or update existing)
   - Email validation triggers MQL qualification (hs_v2_date_entered_lead)
   - Critical events can trigger PQL qualification (activo = 'true', fecha_activo)
   - This MQL/PQL path happens IN PARALLEL with SQL process
   - User can have both SQL and PQL (overlap scenario - ideal PLG flow)
8. **Initial State**: Intercom contacts start as NOT MQLs because there's no event in the product - it's just a question/lead from Intercom
9. **Existing Customer Contacts**: If the Intercom contact is from an existing paying company (customer), that's NOT an MQL - it's just a contact from an existing customer.
10. **UTM Sources**: 
    - **Intercom Captures UTM**: When user visits website with UTM parameters and clicks Intercom chat, Intercom DOES capture UTM parameters
    - **HubSpot Integration Does NOT Pass UTM**: When Intercom contact is created in HubSpot via integration, UTM parameters are NOT passed from Intercom to HubSpot
    - **At Contact Creation in HubSpot**: Intercom contacts have NO UTM parameters in HubSpot initially (attribution unknown)
    - **Retroactive Attribution**: If user later signs up for trial, `initial_utm_source` may be set retroactively by integration 453475
      - This comes from the original website visit (not from Intercom)
      - This reveals the REAL original marketing source (e.g., Google PPC campaigns)
      - Examples: "google" (Google PPC), "App Mobile Colppy" (App Store campaigns)
      - Timing: Set minutes to days after Intercom contact creation
    - **Pattern**: Contacts without trial signup have null `initial_utm_source`; contacts with trial signup may have retroactive attribution from original website visit
    - **Why This Matters**: Even though `lead_source = 'Orgánico'` (unknown at Intercom creation) and UTM is not passed from Intercom, `initial_utm_source` can reveal the actual marketing channel from the original website visit
11. **Bidirectional Conversation Flow**: Conversations happen in both Intercom and HubSpot, with all interactions integrated into HubSpot

**Use Cases**:
- Measuring sales-led conversion effectiveness
- Tracking Intercom → HubSpot → Mixpanel integration
- Identifying contacts who qualify but never sign up for trial
- Measuring time between qualification and trial signup (if it happens)

**Data Quality Considerations**:
- Contacts have HubSpot activity but no Mixpanel activity (until trial signup)
- Qualification event in Mixpanel is the ONLY event until trial signup
- Need to track both HubSpot and Mixpanel separately for this funnel
- Gap analysis: Qualified leads that never sign up for trial

---

### 1.4 Accountant Channel Funnel (Partner-Led Entry)

**Entry Point**: Referral from accountant partner

**Critical Characteristics**:
- Partner-led entry point
- Referral from accountant partner
- Higher conversion rate to SQL
- Deal association with Estudio Contable (association type 8)

**Funnel Stages**:
```
Accountant Referral
    ↓
Contact Created (lead_source = 'Referencia Externa Pyme' or Accountant Channel team)
    ↓
Lead (lifecyclestage = 'lead')
    ↓
SQL (hs_v2_date_entered_opportunity) - Higher conversion rate
    ↓
Deal Created (association type 8: Estudio Contable)
    ↓
Customer (lifecyclestage = 'customer')
```

**MQL Funnel Analysis Scripts**:
- **Accountant MQL Funnel** (`analyze_accountant_mql_funnel.py`): Analyzes MQL Contador → Deal Created → Closed Won
  - **STRICT FUNNEL LOGIC**: Only counts deals that went through the complete path (MQL → Deal Created → Won)
  - MQL Definition: Contacts created in period with `rol_wizard` indicating accountant role
  - MQL to Won Rate: Only closed won deals associated with MQL contacts (not proportions, strict funnel)
  - See `tools/scripts/hubspot/README.md` for detailed usage

- **SMB MQL Funnel** (`analyze_smb_mql_funnel.py`): Analyzes MQL PYME → Deal Created → Closed Won
  - **STRICT FUNNEL LOGIC**: Only counts deals that went through the complete path (MQL → Deal Created → Won)
  - MQL Definition: Contacts created in period with `rol_wizard` indicating SMB role (NOT accountant)
  - MQL to Won Rate: Only closed won deals associated with MQL contacts (not proportions, strict funnel)
  - See `tools/scripts/hubspot/README.md` for detailed usage

**Key Metrics**:
- **Referral Rate**: Accountant referrals / total contacts
- **SQL Conversion Rate**: SQLs from accountant channel / accountant referrals
- **Deal Win Rate**: Won deals from accountant channel / total accountant deals
- **Average Deal Size**: Average deal amount from accountant channel

**HubSpot Fields**:
- `lead_source` - Current source classification (can be changed by sales/forms/workflows)
  - **Note**: `lead_source` may not reflect original source if it has been reclassified
  - **Example**: MQL originally from Google PPC may have `lead_source` changed to "Referencia Externa Pyme"
- `initial_utm_source` - Original marketing attribution source (immutable, first touch)
- `initial_utm_medium` - Original marketing attribution medium (immutable, first touch)
- `initial_utm_campaign` - Original marketing attribution campaign (immutable, first touch)
  - **Use**: Identify original MQLs even when `lead_source` has been changed
- `hubspot_owner_id` - Owner from Accountant Channel team
- `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - SQL qualification date
- Deal association type `8` - Estudio Contable relationship
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer conversion date

**Mixpanel Events**:
- Product events after trial signup (if user signs up)

**UTM Attribution**:
- `initial_utm_source` - Original marketing attribution (immutable, first touch)
- `initial_utm_medium` - Original marketing attribution medium (immutable, first touch)
- `initial_utm_campaign` - Original marketing attribution campaign (immutable, first touch)
  - **Use**: Identify original MQLs that were reclassified to Accountant Channel
  - **Note**: Contacts may have `lead_source = 'Referencia Externa Pyme'` but `initial_utm_source` shows original marketing source (e.g., Google PPC)

**Cycle Times**:
- Referral → Lead: Lead object creation
- Referral → SQL: `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")
- Referral → Customer: `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")

**Patterns/Characteristics**:
- Partner-driven acquisition
- Higher SQL conversion rate
- Deal association with Estudio Contable (association type 8)
- Owner from Accountant Channel team
- **lead_source vs initial_utm**: Contacts may have `lead_source = 'Referencia Externa Pyme'` but `initial_utm_source` shows original marketing source
  - **Use `initial_utm_source`** to identify original MQLs that were reclassified
  - **Use `lead_source`** for current classification (can be changed by sales/forms)
  - **Example**: MQL from Google PPC may have `lead_source` changed to "Referencia Externa Pyme" by sales, but `initial_utm_source` preserves original "google" attribution

**Use Cases**:
- Measuring partner channel effectiveness
- Tracking accountant referral performance
- Analyzing deal win rates from partner channel

**Data Quality Considerations**:
- Owner must be in "Accountant Channel" team (use Owners API to verify)
- Deal association type 8 indicates Estudio Contable relationship

---

## 📊 METHOD 2: FUNNELS BY CONVERSION TYPE

Organizes funnels based on the primary conversion mechanism.

### 2.1 SQL Conversion Funnel (Sales-Led)

**Definition**: Contacts that convert via sales qualification (SQL) **WITH validated deal association**

**SQL Definition (Updated - with Deal Validation)**:
A contact is counted as SQL if **ALL THREE** conditions are met:
1. Contact created in the period (MQL - excluding 'Usuario Invitado')
2. `hs_v2_date_entered_opportunity` in the period
3. **Contact has a deal associated that was created between `createdate` and SQL date (within the same period)**

**Important**: Contacts that have `hs_v2_date_entered_opportunity` in the period but do NOT have a valid deal association are **NOT counted as SQL**. These contacts are tracked separately as edge cases for data quality analysis:
- **NO_DEALS_ASSOCIATED**: Contact has SQL date but no deals are associated
- **DEAL_BEFORE_EARLIEST_CONTACT**: Deal was created before any contact associated with it
- **DEAL_AFTER_SQL_DATE**: Deal was created after the SQL date
- **DEAL_OUTSIDE_PERIOD**: Deal was created outside the analysis period
- **DEAL_NO_CREATEDATE**: Deal exists but has no createdate property

These edge cases are reported separately in the funnel analysis scripts but are **excluded from SQL counts** to maintain strict funnel integrity.

**Funnel Stages**:
```
Contact Created
    ↓
Lead (lifecyclestage = 'lead')
    ↓
MQL (hs_v2_date_entered_lead) - Optional stage (many contacts skip this)
    ↓
SQL (hs_v2_date_entered_opportunity + validated deal)
    ↓
Deal Created (validated deal that qualified SQL)
    ↓
Deal Stages:
    ├─► Pendiente de Demo (qualifiedtobuy) - 30% probability
    ├─► Análisis (presentationscheduled) - 50% probability
    ├─► Negociación (decisionmakerboughtin) - 90% probability
    └─► Cerrado Ganado (closedwon) - 100% probability
        └─► Customer (lifecyclestage = 'customer')
```

**Key Metrics**:
- **SQL Conversion Rate**: `(SQLs / total contacts) × 100`
- **SQL Cycle Time**: `hs_v2_date_entered_opportunity - createdate`
- **Deal Creation Rate**: `(deals / SQLs) × 100`
  - **Note**: This rate may exceed 100% because:
    - A contact can have multiple deals
    - Some deals may be created without SQL validation (e.g., deals created after SQL date, or deals from contacts without SQL date in period)
- **Win Rate**: `(won deals / total deals) × 100`
- **Average Sales Cycle**: `dealstage_cerrado_ganado_entered_at - dealstage_pendiente_de_demo_entered_at`

**HubSpot Fields**:
- `hs_v2_date_entered_opportunity` - SQL qualification date
- `num_associated_deals` - Number of associated deals
- Deal `createdate` - Deal creation date (used for SQL validation)
- `dealstage` - Current deal stage
- `dealstage_pendiente_de_demo_entered_at` - First stage entry
- `dealstage_cerrado_ganado_entered_at` - Won stage entry

**Cohort Definition**:
- Contact must be created AND convert to SQL in the same period
- Both `createdate` and `hs_v2_date_entered_opportunity` must be in target period
- **Deal Validation**: Contact must have at least one deal where:
  - `deal.createdate` is between `contact.createdate` and `hs_v2_date_entered_opportunity`
  - `deal.createdate` is within the analysis period
- **Purpose**: Ensures SQL conversion is validated by actual deal creation, providing accurate conversion measurement

**Difference between SQL and Deal Created**:
- **SQL**: Counts **contacts** that meet all validation criteria (including deal timing)
- **Deal Created**: Counts **all deals** created in period (associated with MQL contacts)
- **Why Deal Created > SQL**: 
  - Multiple deals per contact
  - Deals from contacts without SQL date in period
  - Deals created outside the SQL validation window (before contact creation or after SQL date)

---

### 2.2 PQL Conversion Funnel (Product-Led)

**Definition**: Contacts that convert via critical events (key product events) (PQL)

**Funnel Stages**:
```
Contact Created
    ↓
Trial Signup (7-day free trial)
    ↓
Critical Events (key events: Invoice Created, Payment Processed, etc.)
    ↓
PQL (activo = 'true', fecha_activo)
    ↓
├─► SQL (hs_v2_date_entered_opportunity) - Sales engagement
│   └─► Deal Created
│       └─► Customer (lifecyclestage = 'customer')
│
└─► Direct Customer (lifecyclestage = 'customer') - Self-service
```

**Key Metrics**:
- **PQL Conversion Rate**: `(PQLs / total contacts) × 100`
- **PQL Cycle Time**: `fecha_activo - createdate`
  - **IMPORTANT**: `fecha_activo` is date-only (no time), while `createdate` has full timestamp. If both dates are on the same calendar day, cycle time = 0.0 days (same day conversion).
- **PQL → SQL Rate**: `(SQLs from PQL cohort / total PQLs) × 100`
- **PQL → Customer Rate**: `(customers from PQL cohort / total PQLs) × 100`

**HubSpot Fields**:
- `activo` - PQL key event flag (string 'true')
- `fecha_activo` - PQL key event date (date string 'YYYY-MM-DD')
- `hs_v2_date_entered_opportunity` - SQL qualification date (if sales engages)
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer conversion date

**Product Events** (Mixpanel):
- Invoice Created
- Payment Processed
- Report Generated
- User Login
- Feature Used

**Cohort Definition**:
- Contact must be created AND perform critical events (PQL) in the same period
- Both `createdate` and `fecha_activo` must be in target period
- `activo` must equal 'true'

**Critical Note**:
- `fecha_activo` is date-only (not datetime)
- Must append `T00:00:00+00:00` when parsing for timezone-aware comparisons

---

### 2.3 SQL-PQL Overlap Funnel (Hybrid Conversion)

**Definition**: Contacts that achieve both SQL and PQL (ideal PLG flow)

**Funnel Stages**:
```
Contact Created
    ↓
├─► PQL First (fecha_activo < hs_v2_date_entered_opportunity)
│   └─► Product-Led Growth Pattern
│       └─► SQL (hs_v2_date_entered_opportunity)
│           └─► Deal Created
│               └─► Customer (lifecyclestage = 'customer')
│
└─► SQL First (hs_v2_date_entered_opportunity < fecha_activo)
    └─► Sales-Led Adoption Pattern
        └─► PQL (fecha_activo)
            └─► Deal Created
                └─► Customer (lifecyclestage = 'customer')
```

**Key Metrics**:
- **Overlap Rate (from SQL)**: `(both SQL+PQL / total SQLs) × 100`
- **Overlap Rate (from PQL)**: `(both SQL+PQL / total PQLs) × 100`
- **Correlation Ratio**: `P(SQL ∩ PQL) / [P(SQL) × P(PQL)]`
  - < 0.5: Negative correlation
  - 0.5-1.5: Near independence
  - > 1.5: Positive correlation
- **Timing Pattern**: % PQL→SQL vs % SQL→PQL
  - **Critical**: Chronological order matters - identify which comes first (fecha_activo vs hs_v2_date_entered_opportunity)
  - **PQL → SQL**: fecha_activo < hs_v2_date_entered_opportunity (product-led growth pattern)
  - **SQL → PQL**: hs_v2_date_entered_opportunity < fecha_activo (sales-led adoption pattern)
- **Time Between Events**: Hours between first and second event (only calculate when order is established)

**HubSpot Fields**:
- `hs_v2_date_entered_opportunity` - SQL qualification date
- `activo` - PQL key event flag
- `fecha_activo` - PQL key event date
- `createdate` - Contact creation date

**Typical Patterns**:
- **Low Overlap (< 10%)**: Independent customer journeys, broken handoff
- **PQL → SQL**: Product-led growth (ideal PLG flow)
- **SQL → PQL**: Sales-led adoption (traditional model)
- **High Independence**: Separate customer segments, optimization opportunity

**Use Cases**:
- Measuring PLG program effectiveness
- Identifying team coordination gaps
- Optimizing product-to-sales handoff
- Understanding customer journey paths

---

## 📊 METHOD 3: FUNNELS BY LIFECYCLE STAGE

Organizes funnels based on HubSpot lifecycle stage progression.

### 3.1 Subscriber → Lead Funnel

**Entry Stage**: `lifecyclestage = 'subscriber'`

**Funnel Stages**:
```
Subscriber (lifecyclestage = 'subscriber')
    ↓
Lead (lifecyclestage = 'lead', hs_v2_date_entered_lead)
```

**Key Metrics**:
- **Subscriber Count**: Contacts with `lifecyclestage = 'subscriber'`
- **Lead Conversion Rate**: `(leads / subscribers) × 100`
- **Time to Lead**: `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")

**HubSpot Fields**:
- `lifecyclestage` (UI: "Lifecycle Stage") - Current lifecycle stage
- `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") - Lead qualification date

**Note**: In Colppy, a "Lead" requires an associated Lead object, NOT just `lifecyclestage = 'lead'`. Lead objects can be created automatically by workflow (for Colppy integration contacts) or manually by salesperson (for Intercom contacts). The workflow sets `lifecyclestage = 'lead'` and `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") = `createdate` (UI: "Create Date") automatically, but Lead object creation is separate. For Intercom contacts, Lead objects are created manually by salesperson.

---

### 3.2 Lead → Opportunity Funnel

**Entry Stage**: `lifecyclestage = 'lead'`

**Funnel Stages**:
```
Lead (lifecyclestage = 'lead')
    ↓
Opportunity (lifecyclestage = 'opportunity', hs_v2_date_entered_opportunity)
    ↓
Deal Created
```

**Key Metrics**:
- **Lead Count**: Contacts with `lifecyclestage = 'lead'`
- **Opportunity Conversion Rate**: `(opportunities / leads) × 100`
- **Time to Opportunity**: `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"")
- **Deal Creation Rate**: `(deals / opportunities) × 100`

**HubSpot Fields**:
- `lifecyclestage` (UI: "Lifecycle Stage") - Current lifecycle stage
- `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") - Lead qualification date
- `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"") - Opportunity qualification date
- `num_associated_deals` - Number of associated deals

---

### 3.3 Opportunity → Customer Funnel

**Entry Stage**: `lifecyclestage = 'opportunity'`

**Funnel Stages**:
```
Opportunity (lifecyclestage = 'opportunity')
    ↓
Deal Created
    ↓
Deal Stages:
    ├─► Pendiente de Demo (qualifiedtobuy)
    ├─► Análisis (presentationscheduled)
    ├─► Negociación (decisionmakerboughtin)
    └─► Cerrado Ganado (closedwon)
        └─► Customer (lifecyclestage = 'customer', hs_v2_date_entered_customer)
```

**Key Metrics**:
- **Opportunity Count**: Contacts with `lifecyclestage = 'opportunity'`
- **Customer Conversion Rate**: `(customers / opportunities) × 100`
- **Time to Customer**: `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - `hs_v2_date_entered_opportunity` (UI: "Date entered \"Oportunidad (Pipeline de etapa del ciclo de vida)\"")
- **Win Rate**: `(won deals / total deals) × 100`

**HubSpot Fields**:
- `lifecyclestage` - Current lifecycle stage
- `hs_v2_date_entered_opportunity` - Opportunity qualification date
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer conversion date
- `dealstage` - Current deal stage
- `dealstage_cerrado_ganado_entered_at` - Won stage entry

---

## 📊 METHOD 4: FUNNELS BY CHANNEL

Organizes funnels based on acquisition channel or team.

### 4.1 Marketing Channel Funnel

**Channel**: Marketing-generated leads (UTM tracking)

**Funnel Stages**:
```
Marketing Touch (utm_source, utm_campaign, utm_medium)
    ↓
Contact Created
    ↓
Lead (lifecyclestage = 'lead')
    ↓
MQL (hs_v2_date_entered_lead)
    ↓
SQL (hs_v2_date_entered_opportunity)
    ↓
Customer (lifecyclestage = 'customer')
```

**Key Metrics**:
- **Marketing Contacts**: Contacts with UTM parameters
- **MQL Conversion Rate**: `(MQLs from marketing / marketing contacts) × 100`
- **SQL Conversion Rate**: `(SQLs from marketing / marketing contacts) × 100`
- **Customer Conversion Rate**: `(customers from marketing / marketing contacts) × 100`
- **CAC by Channel**: Marketing spend / customers acquired

**HubSpot Fields**:
- `utm_source` - Traffic source
- `utm_campaign` - Campaign name
- `utm_medium` - Marketing medium
- `hs_v2_date_entered_lead` - MQL qualification date
- `hs_v2_date_entered_opportunity` - SQL qualification date

**Lead Sources**:
- `lead_source = 'Orgánico'` - Organic traffic
- `lead_source = 'Pago'` - Paid marketing

---

### 4.2 Product Channel Funnel (PLG)

**Channel**: Product-led growth (self-service)

**Funnel Stages**:
```
Trial Signup
    ↓
Critical Events (key events)
    ↓
PQL (activo = 'true', fecha_activo)
    ↓
Customer (lifecyclestage = 'customer')
```

**Key Metrics**:
- **Trial Signups**: Users who start 7-day free trial
- **Key Event Rate**: Users with key events / trial signups
- **PQL Conversion Rate**: `(PQLs / trial signups) × 100`
- **Customer Conversion Rate**: `(customers from PQL / total PQLs) × 100`

**HubSpot Fields**:
- `createdate` - Trial signup date
- `activo` - PQL key event flag
- `fecha_activo` - PQL key event date
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer conversion date

**Product Events** (Mixpanel):
- Invoice Created
- Payment Processed
- Report Generated
- User Login
- Feature Used

---

### 4.3 Sales Channel Funnel

**Channel**: Sales-generated leads (outbound, referrals)

**Funnel Stages**:
```
Sales Touch (hs_first_outreach_date, hs_sa_first_engagement_date)
    ↓
Contact Created
    ↓
Lead (lifecyclestage = 'lead')
    ↓
SQL (hs_v2_date_entered_opportunity)
    ↓
Deal Created
    ↓
Customer (lifecyclestage = 'customer')
```

**Key Metrics**:
- **Sales Contacts**: Contacts with sales engagement
- **Time to First Touch**: `hs_first_outreach_date - createdate`
- **SQL Conversion Rate**: `(SQLs from sales / sales contacts) × 100`
- **Deal Win Rate**: `(won deals / total deals) × 100`

**HubSpot Fields**:
- `hs_first_outreach_date` - First outreach date
- `hs_sa_first_engagement_date` - First engagement with current owner
- `hs_v2_date_entered_opportunity` - SQL qualification date
- `num_contacted_notes` - Number of contacted notes
- `notes_last_contacted` - Last contact date

**Engagement Types**:
- CALL - Completed calls, no-answer calls
- EMAIL - Emails sent, email replies
- MEETING_EVENT - Scheduled meetings, completed meetings

---

### 4.4 Intercom Support Channel Funnel (Sales-Led, No Trial)

**Channel**: Intercom chat/support contacts (sales-led, no trial signup)

**Critical Characteristics**:
- **NO Trial Signup**: User contacts sales but does NOT sign up for trial at this point
- **Contact Creation**: Contact created by Intercom integration when user starts chatting
- **Lead Source Attribution**: `lead_source` is set to "Orgánico" (Label: "Orgánico / Directo") by workflow
  - Attribution is Intercom, but we don't know how they got to Intercom
  - Set by AUTOMATION_PLATFORM (workflow) to indicate unknown attribution
  - "Orgánico" includes both organic and direct traffic
  - NOT "Referencia Intercom" (that's only for form submissions, not integration-created contacts)
- **Lifecycle Stage**: Integration may set `lifecyclestage = 'lead'` directly (source: `INTEGRATION`)
- **Lead Object Creation**: Lead object is created MANUALLY by salesperson (not automatic)
  - At this point, you only have a contact (not a Lead yet)
  - Salesperson manually creates Lead object and associates it with contact
  - Source: `CRM_UI` (in Lead object `hs_created_by_user_id` property history)
- **NOT an MQL**: This is NOT an MQL because there's no event in the product - it's just a question/lead from Intercom
- **Cannot Become MQL Retroactively**: Intercom contacts cannot retroactively become MQLs. If the user later signs up for trial, that creates a NEW contact with the standard MQL process.
- **Existing Customer Contacts**: If the Intercom contact is from an existing paying company (customer), that's NOT an MQL
- **Delayed Product Activity**: Product events only if user later signs up for trial (creates NEW contact)

**Funnel Stages**:
```
User Visits Website → Starts Chatting in Intercom → Talks with Sales Team
    ↓
Contact Created in HubSpot (lead_source = 'Orgánico' - set by workflow)
    ↓
Lifecycle Stage Set (lifecyclestage = 'lead') - Set by Intercom integration directly
    ↓
Lead Object Created - MANUALLY by salesperson (associates Lead object with contact)
    ↓
Sales Engagement in HubSpot:
    ├─► First Outreach (hs_first_outreach_date)
    ├─► First Engagement (hs_sa_first_engagement_date)
    └─► Lead Status Changes (last_lead_status_date)
    ↓
[NOT an MQL - No product events, just Intercom conversation]
    ↓
[Optional] User Later Signs Up for Trial
    └─► NEW Contact Created (standard MQL process)
        └─► User Signs Up for Trial (7-day free trial)
            └─► Email Validation ("Validó email" event)
                └─► MQL (hs_v2_date_entered_lead) - NEW contact, not the Intercom contact
                    └─► Product Events Start in Mixpanel
                        └─► PQL (activo = 'true', fecha_activo) - If critical events performed
```

**Key Metrics**:
- **Intercom Contact Rate**: Contacts from Intercom / total Intercom conversations
- **HubSpot Lead Creation Rate**: HubSpot Lead objects created / Intercom contacts
  - **Note**: In Colppy, a "Lead" requires an associated Lead object, NOT just `lifecyclestage = 'lead'`
  - Lead objects for Intercom contacts are created manually by salesperson
- **Qualification Rate**: Qualified leads / Intercom contacts
- **Time to Qualification**: `hs_v2_date_entered_opportunity - createdate`
- **Trial Signup Rate (Later)**: Users who later sign up / Intercom contacts (creates NEW contact)
- **PQL Conversion Rate (Later)**: PQLs from Intercom / Intercom contacts

**HubSpot Fields**:
- `lead_source = 'Orgánico'` (Label: "Orgánico / Directo") - Source tracking
  - Attribution is Intercom, but we don't know how they got to Intercom
  - Set by AUTOMATION_PLATFORM (workflow) to indicate unknown attribution
  - Includes both organic and direct traffic
  - NOT "Referencia Intercom" (that's only for form submissions)
- `createdate` - Contact creation date
- `lifecyclestage = 'lead'` - Lead lifecycle stage (set by Intercom integration)
- `hs_first_outreach_date` - First sales outreach
- `hs_sa_first_engagement_date` - First engagement with owner
- `hs_v2_date_entered_lead` - MQL qualification date (set if user later signs up for trial and validates email)
- `hs_v2_date_entered_opportunity` - SQL qualification date

**Mixpanel Events**:
- **"Qualification"** - Fired when HubSpot qualification happens (ONLY event initially)
- **No other events** until user logs into Colppy and signs up for trial
- **Product events** only appear if user later performs critical events

**HubSpot → Mixpanel Integration**:
- **Workflow Trigger**: When contact qualifies in HubSpot (MQL/SQL)
- **Mixpanel Event**: "Qualification" event is sent
- **Event Properties**: Contact email, qualification date, qualification type
- **Gap**: No other Mixpanel events until user signs up for trial

**Critical Differences from PLG Channel**:
1. **No Trial at Entry**: Unlike PLG, user does NOT start with trial
2. **Bidirectional Conversation Flow**: Conversations happen in both Intercom and HubSpot, with all interactions integrated into HubSpot (not just HubSpot-only)
3. **Manual Process**: Lead creation is manual (sales), not automated
4. **Delayed Product Activity**: Product events only if user later logs in
5. **Mixpanel Gap**: Only "Qualification" event initially, nothing else

**Use Cases**:
- Measuring sales-led conversion effectiveness
- Tracking Intercom → HubSpot → Mixpanel integration
- Identifying qualified leads who never sign up for trial
- Measuring time between qualification and trial signup

**Data Quality Considerations**:
- Contacts have HubSpot activity but no Mixpanel activity (until trial)
- Qualification event is the ONLY Mixpanel event until trial signup
- Need to track HubSpot and Mixpanel separately
- Gap analysis: Qualified leads that never sign up for trial

---

### 4.5 Accountant Channel Funnel

**Channel**: Accountant partner referrals

**Funnel Stages**:
```
Accountant Referral
    ↓
Contact Created (lead_source = 'Referencia Externa Pyme' or Accountant Channel team)
    ↓
Lead (lifecyclestage = 'lead')
    ↓
SQL (hs_v2_date_entered_opportunity) - Higher conversion rate
    ↓
Deal Created (association type 8: Estudio Contable)
    ↓
Customer (lifecyclestage = 'customer')
```

**Key Metrics**:
- **Accountant Referrals**: Contacts from accountant channel
- **SQL Conversion Rate**: `(SQLs from accountant / accountant referrals) × 100`
- **Deal Win Rate**: `(won deals from accountant / total accountant deals) × 100`
- **Average Deal Size**: Average deal amount from accountant channel

**HubSpot Fields**:
- `lead_source` - Source tracking
- `hubspot_owner_id` - Owner from Accountant Channel team
- `hs_v2_date_entered_opportunity` - SQL qualification date
- Deal association type `8` - Estudio Contable relationship

**Team Detection**:
- Owner must be in "Accountant Channel" team
- Use Owners API (`/crm/v3/owners/{ownerId}`) to check teams array

---

## 📊 METHOD 5: FUNNELS BY OUTCOME

Organizes funnels based on final outcome or conversion goal.

### 5.1 Contact → Customer Funnel (Revenue Attribution)

**Outcome**: Paying customer

**Funnel Stages**:
```
Contact Created
    ↓
├─► SQL Path
│   └─► Deal Created
│       └─► Cerrado Ganado (closedwon)
│           └─► Customer (lifecyclestage = 'customer')
│
└─► PQL Path
    └─► Customer (lifecyclestage = 'customer')
```

**Key Metrics**:
- **Total Contacts**: All contacts created
- **Customer Conversion Rate**: `(customers / total contacts) × 100`
- **Time to Customer**: `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - `createdate` (UI: "Create Date")
- **Revenue per Customer**: Total revenue / customers

**HubSpot Fields**:
- `createdate` - Contact creation date
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer conversion date
- `lifecyclestage` - Current lifecycle stage
- Deal `amount` - Deal value (for SQL path)

---

### 5.2 Contact → Deal Funnel (Pipeline Generation)

**Outcome**: Deal created (regardless of outcome)

**Funnel Stages**:
```
Contact Created
    ↓
Lead (lifecyclestage = 'lead')
    ↓
SQL (hs_v2_date_entered_opportunity + validated deal)
    ↓
Deal Created
```

**Key Metrics**:
- **Total Contacts**: All contacts created
- **Deal Creation Rate**: `(contacts with deals / total contacts) × 100`
- **Time to Deal**: `deal createdate - createdate`
- **Average Deal Size**: Average deal amount

**HubSpot Fields**:
- `createdate` - Contact creation date
- `num_associated_deals` - Number of associated deals
- `hs_v2_date_entered_opportunity` - SQL qualification date (with deal validation)
- Deal `createdate` - Deal creation date (used for SQL validation)
- Deal `amount` - Deal value

**Note**: SQL now requires deal validation. A contact is SQL only if they have a deal created between `createdate` and `hs_v2_date_entered_opportunity` (within the analysis period). This ensures SQL conversion is validated by actual deal creation.

---

### 5.3 Deal → Won Funnel (Sales Effectiveness)

**Outcome**: Won deal (revenue generated)

**Funnel Stages**:
```
Deal Created
    ↓
Pendiente de Demo (qualifiedtobuy) - 30% probability
    ↓
Análisis (presentationscheduled) - 50% probability
    ↓
Negociación (decisionmakerboughtin) - 90% probability
    ↓
Cerrado Ganado (closedwon) - 100% probability
```

**Key Metrics**:
- **Total Deals**: All deals created
- **Win Rate**: `(won deals / total deals) × 100`
- **Average Sales Cycle**: `dealstage_cerrado_ganado_entered_at - dealstage_pendiente_de_demo_entered_at`
- **Revenue**: Sum of won deal amounts
- **Stage Conversion Rates**: Conversion rate at each stage

**HubSpot Fields**:
- `dealstage` - Current deal stage
- `dealstage_pendiente_de_demo_entered_at` - First stage entry
- `dealstage_análisis_entered_at` - Analysis stage entry
- `dealstage_negociación_entered_at` - Negotiation stage entry
- `dealstage_cerrado_ganado_entered_at` - Won stage entry
- `amount` - Deal value
- `closedate` - Deal close date

**Won Stages**:
- `closedwon` - Cerrado Ganado
- `34692158` - Cerrado Ganado Recupero (recovery)

**Lost Stages**:
- `closedlost` - Cerrado Perdido
- `31849274` - Cerrado Churn

---

## 📊 METHOD 6: FUNNELS BY TIME PERIOD

Organizes funnels for cohort and trend analysis.

### 6.1 Cohort Funnel

**Time Period**: Configurable analysis period

**Funnel Stages**:
```
Contacts Created in Analysis Period
    ↓
├─► SQL Conversions in Analysis Period
│   └─► Customers in Analysis Period or Later
│
└─► PQL Conversions in Analysis Period
    └─► Customers in Analysis Period or Later
```

**Key Metrics**:
- **Base Cohort**: All contacts created in the analysis period
- **SQL Conversion Rate**: `(SQLs in period / contacts created in period) × 100`
- **PQL Conversion Rate**: `(PQLs in period / contacts created in period) × 100`
- **Customer Conversion Rate**: `(customers from period cohort / contacts created in period) × 100`

**Cohort Definition**:
- Contact must be created AND convert in the same analysis period
- Both `createdate` and conversion date must be in target period

**HubSpot Fields**:
- `createdate` - Contact creation date (must be in analysis period)
- `hs_v2_date_entered_opportunity` - SQL date (must be in analysis period)
- `fecha_activo` - PQL date (must be in analysis period)
- `hs_v2_date_entered_customer` (UI: "Date entered \"Cliente (Pipeline de etapa del ciclo de vida)\"") - Customer date (can be in analysis period or later)

---

### 6.2 Time-to-Contact Funnel

**Time Period**: Time from lead creation to first contact

**Funnel Stages**:
```
Lead Created (hs_v2_date_entered_lead)
    ↓
First Contact (priority order):
    ├─► First Outreach (hs_first_outreach_date)
    ├─► First Engagement (hs_sa_first_engagement_date)
    └─► Lead Status Change (last_lead_status_date, if status changed from 'Nuevo Lead')
```

**Key Metrics**:
- **Total MQLs**: Contacts with `hs_v2_date_entered_lead` in period
- **Contacted MQLs**: MQLs with any contact method
- **Contact Rate**: `(contacted MQLs / total MQLs) × 100`
- **Average Time-to-Contact**: Average days from lead date to contact date
- **Median Time-to-Contact**: Median days from lead date to contact date
- **Distribution by Time Range**: Configurable time ranges for analysis
  - 7+ days

**HubSpot Fields**:
- `hs_v2_date_entered_lead` - Lead qualification date
- `hs_first_outreach_date` - First outreach date
- `hs_sa_first_engagement_date` - First engagement date
- `last_lead_status_date` - Last lead status change date
- `hs_lead_status` - Current lead status

**Contact Method Priority**:
1. `hs_first_outreach_date` - First outreach (email, call, meeting)
2. `hs_sa_first_engagement_date` - First engagement with current owner
3. `last_lead_status_date` - Only if status changed from 'Nuevo Lead' (938333957)

---

## 📝 FUNNEL DEFINITIONS GLOSSARY

### Qualification Stages

- **Lead**: Contact showing interest (`lifecyclestage = 'lead'`)
  - **Automatic**: Set automatically when contact is created via HubSpot workflow
  - **Date Field**: `hs_v2_date_entered_lead` (UI: "Date entered \"Lead (Pipeline de etapa del ciclo de vida)\"") (same as `createdate` (UI: "Create Date"))
  - **Time to Lead**: 0 seconds (same timestamp as contact creation)
  
- **MQL (Marketing Qualified Lead)**: Lead automatically qualified by HubSpot system (`hs_v2_date_entered_lead`)
  - **Definition**: Lead that meets automatic qualification criteria AND has validated their email in Colppy
  - **Note**: "Marketing Qualified" is HubSpot terminology, but qualification happens automatically via HubSpot workflows - no marketing person is involved
  - **MQL Requirements** (ALL must be met):
    1. **Lead Status**: `lifecyclestage = 'lead'` (created automatically by HubSpot workflow)
    2. **MQL Qualification Date**: `hs_v2_date_entered_lead` must be populated
    3. **Email Validated**: Contact must have "Validó email" event in Mixpanel
      - **What it means**: User signed up on the signup page, received validation email with code, and entered the code to validate their email
      - **If event does NOT exist**: User signed up on the signup page, platform sent them an email with a code, but the user never entered the code to validate the email
    4. **Original Marketing Attribution**: `initial_utm_source` must be populated (indicates original marketing source)
      - **Why**: `initial_utm_source` preserves the original marketing attribution and cannot be changed
      - **Distinction**: `lead_source` can be changed by sales/forms/workflows, so it may not reflect the original source
      - **Use Case**: Identifies true MQLs even when `lead_source` has been reclassified (e.g., MQL reclassified as "Referencia Externa Pyme")
  - **Critical Rule**: If contact is created WITHOUT Lead status, it CANNOT be an MQL (Lead is a prerequisite)
  - **Date Field**: `hs_v2_date_entered_lead` (timestamp when automatic qualification occurred)
  - **Qualification Method**: 
    - **Automatic Only**: HubSpot lead scoring workflow automatically qualifies leads based on score thresholds (triggered after email validation). This is a system process - no marketing person is involved. Qualification is based on email validation ("Validó email" event), form submissions, email engagement, website visits, etc.
  - **Time to MQL**: `hs_v2_date_entered_lead - createdate`
    - **Pattern**: Qualification happens very quickly (minutes, not days) for contacts that become MQLs, or never (many contacts skip MQL)
    - **Method**: Automatic qualification via HubSpot lead scoring workflow after email validation
  - **Important**: Not all leads become MQLs. Many skip MQL and go directly to SQL or remain unqualified. For contacts that DO become MQLs, they must have validated their email in Colppy ("Validó email" event in Mixpanel) and qualification happens automatically via HubSpot workflow.
  - **MQL Identification**: Use `initial_utm_source` to identify original MQLs, as `lead_source` can be changed by sales/forms and may not reflect the original marketing source.
  - **MQL Identification**: Use `initial_utm_source` to identify original MQLs, as `lead_source` can be changed by sales/forms and may not reflect the original marketing source.
  
- **PQL (Product Qualified Lead)**: User performed critical events in product (`activo = 'true'`, `fecha_activo`)
  - **Definition**: User who performed critical events during trial (triggered key product events that demonstrate engagement)
  - **Time to PQL**: `fecha_activo - createdate`
    - **Note**: `fecha_activo` is date-only (no time). If both dates are on the same calendar day, cycle time = 0.0 days.
  
- **SQL (Sales Qualified Lead)**: Lead qualified by sales (`hs_v2_date_entered_opportunity`) **WITH validated deal association**
  - **Definition**: Lead that sales team has qualified as an opportunity AND has a validated deal created between contact creation and SQL date (within the analysis period)
  - **Date Field**: `hs_v2_date_entered_opportunity` (timestamp when entered opportunity stage)
  - **Deal Validation**: Contact must have a deal where `deal.createdate` is between `contact.createdate` and `hs_v2_date_entered_opportunity` (all within the analysis period)
  - **Time to SQL**: `hs_v2_date_entered_opportunity - createdate`
  - **Complete Definition**: SQL = MQL (contact created in period, excluding 'Usuario Invitado') + `hs_v2_date_entered_opportunity` in period + deal created between `createdate` and SQL date (within period)

### Lifecycle Stages

- **Subscriber**: Initial contact with minimal interaction (`lifecyclestage = 'subscriber'`)
- **Lead**: Qualified contact showing interest (`lifecyclestage = 'lead'`)
- **Opportunity**: Lead considered for potential deal (`lifecyclestage = 'opportunity'`)
- **Customer**: Converted to paying customer (`lifecyclestage = 'customer'`)

### Deal Stages

- **Pendiente de Demo**: Initial deal stage (30% probability) - `qualifiedtobuy`
- **Análisis**: Analyzing needs and solutions (50% probability) - `presentationscheduled`
- **Negociación**: Discussing terms (90% probability) - `decisionmakerboughtin`
- **Cerrado Ganado**: Deal successfully closed (100% probability) - `closedwon`
- **Cerrado Ganado Recupero**: Recovered previously lost client - `34692158`
- **Cerrado Perdido**: Deal closed but no revenue - `closedlost`
- **Cerrado Churn**: Customer who left - `31849274`

---

## 🔄 HUBSPOT → MIXPANEL INTEGRATION WORKFLOW

### Overview

Colppy has a HubSpot workflow that integrates with Mixpanel to track qualification events. This integration is critical for understanding the Intercom → HubSpot → Mixpanel funnel.

### Workflow Trigger

**When**: Contact qualifies in HubSpot (MQL or SQL)

**Trigger Conditions**:
- Contact's `hs_v2_date_entered_lead` is set (MQL qualification)
- OR Contact's `hs_v2_date_entered_opportunity` is set (SQL qualification)

### Mixpanel Event Sent

**Event Name**: "Qualification"

**Event Properties** (typical):
- Contact email
- Qualification date
- Qualification type (MQL or SQL)
- HubSpot contact ID
- Other HubSpot properties

### Critical Behavior

**What Happens**:
1. Contact qualifies in HubSpot (MQL/SQL)
2. HubSpot workflow triggers
3. Mixpanel receives "Qualification" event
4. **This is the ONLY Mixpanel event at this point**

**What Does NOT Happen**:
- No product events (Invoice Created, Payment Processed, etc.)
- No trial signup events
- No user login events
- No other Mixpanel activity

**Why This Matters**:
- For Intercom → HubSpot contacts, Mixpanel will show ONLY "Qualification" event
- No product activity appears in Mixpanel until user logs into Colppy
- Creates a gap in Mixpanel data for sales-led contacts
- Need to track HubSpot and Mixpanel separately for complete picture

### When Product Events Appear

**Only After**:
- User logs into Colppy application
- User signs up for 7-day free trial
- User starts using the product

**Then Mixpanel Will Show**:
- Trial signup events
- Critical events (key product events: Invoice Created, Payment Processed, etc.)
- User login events
- Feature usage events
- PQL qualification (if `activo = 'true'` - user performed critical events)

### Data Quality Implications

**For Intercom → HubSpot Contacts**:
- HubSpot: Full activity history (outreach, engagement, qualification)
- Mixpanel: Only "Qualification" event (until trial signup)
- Gap: Weeks/months between qualification and trial signup

**For PLG Contacts**:
- Mixpanel: Full product activity from trial signup
- HubSpot: Contact created, with or without sales engagement

---

## 📚 RELATED DOCUMENTATION

- [HubSpot Configuration](./README_HUBSPOT_CONFIGURATION.md) - Complete HubSpot field mapping
- [SQL-PQL Correlation Analysis](./HUBSPOT_SQL_PQL_CORRELATION_ANALYSIS.md) - Detailed overlap methodology
- [HubSpot Complete Retrieval Quick Reference](./HUBSPOT_COMPLETE_RETRIEVAL_QUICK_REFERENCE.md) - API usage guide
- [HubSpot Pagination Standards](./README_HUBSPOT_PAGINATION_STANDARDS.md) - Pagination requirements

---

## 🔄 VERSION HISTORY

- **v1.1**: Added Intercom → HubSpot → Mixpanel funnel
  - Added Intercom Support Channel funnel (Section 1.4 and 4.4)
  - Documented HubSpot → Mixpanel integration workflow
  - Explained manual lead creation process (no trial signup)
  - Documented Mixpanel "Qualification" event behavior
  - Added data quality considerations for sales-led contacts

- **v1.0**: Initial comprehensive funnel mapping
  - 6 organization methods
  - Complete funnel definitions
  - Key metrics and HubSpot fields
  - Cross-references and workflow recommendations

---

