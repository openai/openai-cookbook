# Google Tag Manager Conversion Tracking Analysis
## Deep Analysis for PMAX Campaign Configuration

**Date:** November 22, 2024  
**Analyst:** AI Assistant  
**Scope:** Complete GTM setup, conversion tracking, and PMAX campaign linkage

> 📋 **For complete configuration mapping and architecture overview, see:** [GTM_PMAX_CONVERSION_TRACKING_COMPLETE_MAP.md](./GTM_PMAX_CONVERSION_TRACKING_COMPLETE_MAP.md)

---

## ⚠️ **IMPORTANT NOTE ABOUT MOCK FILES**

**All files in `/lib/mocks/` directories are MOCK/TEST files and should NOT be used for actual production campaigns.** This analysis focuses ONLY on production code and actual GTM container configurations.

---

## 📋 Executive Summary

This analysis examines the complete Google Tag Manager (GTM) setup for Colppy's conversion tracking, specifically focusing on how PMAX (Performance Max) campaigns are configured and tracked. The analysis covers:

1. **GTM Container Structure** - Multiple containers found in GTM account
2. **Conversion Tags Configuration** - Google Ads conversion tracking setup in GTM
3. **UTM Parameter Flow** - How campaigns are captured and passed through production code
4. **Code Implementation** - Where tracking is implemented in PRODUCTION codebase (excluding mocks)
5. **PMAX Campaign Linkage** - How PMAX campaigns connect to conversion tracking

**🔴 CRITICAL FINDINGS:**

1. **PMAX IS tracking conversions (318 in last 7 days)** ✅
   - BUT: Conversions are imported from GA4, not direct Google Ads conversion tracking
   - Conversion action: "Web Colppy integral 2024 (web) Lead_Registro_Success" (GA4 import)
   - **Unknown source:** How is GA4 receiving "Lead_Registro_Success" events if no GTM/GA4 found in production registration code?

2. **Production code has NO GTM implementation**
   - GTM containers exist in your account (`GTM-TRBKKZ2P`, `GTM-KQV2QTWJ`, etc.)
   - BUT: Production registration pages do NOT load any GTM container
   - Result: GTM cannot track conversions from actual user registrations (but GA4 might be)

3. **Production registration does NOT track directly to Google Ads**
   - Registration completes successfully
   - Tracks to Mixpanel and Intercom ✅
   - Does NOT track directly to Google Ads conversion pixels ❌
   - **BUT:** PMAX is receiving conversions through GA4 import ⚠️

4. **GA4 Conversion Import Has Limitations**
   - ⚠️ Attribution delay (24-48 hours)
   - ⚠️ Data-driven attribution only (can't optimize with last-click)
   - ⚠️ May not pass gclid as reliably as direct conversion tracking
   - ⚠️ Requires proper GA4 ↔ Google Ads linking

5. **Mock files are irrelevant (as you correctly noted)**
   - Mock files have GTM references, but they're not used in production
   - This is expected behavior - mock files are for testing only
   - **No action needed on mock files** - they don't affect production

---

## 🔍 GTM Container Discovery

### Active Containers Found in GTM Account

| Container Name | Container ID | Type | Purpose |
|---------------|---------------|------|---------|
| **Sitio Web general (colppy.com)** | **GTM-TRBKKZ2P** | Web | ✅ **Main website container** |
| Página de producto (app.colppy.com/registro) + (login.colppy.com) | GTM-KQV2QTWJ | Web | Product/registration pages |
| [Server] Página de registro (app.colppy.com/registro) | GTM-KJLHJKCD | Server | Server-side registration tracking |
| colppy.com | GTM-NQ9TP6C7 | Server | Server-side tracking |
| erver.colppy.com | GTM-WF43K555 | Server | Server-side tracking |
| erver.web.colppy.com | GTM-NCKQ6SG4 | Server | Server-side tracking |
| Staging página de registro | GTM-P79WSXCH | Web | Staging environment |

### ✅ **Container Verification: GTM-M699MG**

**Verification Result:**
- ✅ Searched all GTM accounts accessible to your Google account
- ✅ Checked all 7 active containers listed above
- ❌ **Container `GTM-M699MG` does NOT exist in your GTM account**
- ✅ **Found only in mock files:** `lib/mocks/registro/resources/header.php` (lines 71, 77)

**Why This is NOT a Concern:**
- ✅ **Mock files are NOT used in production** - They are for testing/development only
- ✅ **Production code doesn't reference this container** - Production code has no GTM implementation at all
- ✅ **No impact on live campaigns** - Since mock files aren't used, this doesn't affect PMAX campaigns

**Conclusion:**
- The container ID `GTM-M699MG` in mock files is irrelevant for production
- It's a test/example container ID in test files (as expected)
- **The REAL issue:** Production code doesn't have ANY GTM container (mock or real)
- **For Production Implementation:** Use `GTM-TRBKKZ2P` (main website) or `GTM-KQV2QTWJ` (product/registration pages)

### 🔍 **PRODUCTION CODE ANALYSIS - ALL REPOSITORIES**

**Complete Search Across All Repositories:**

**Repositories Checked:**
1. ✅ `/Users/virulana/colppy-app` - Main application
2. ✅ `/Users/virulana/colppy-vue` - Vue components
3. ✅ `/Users/virulana/svc_backoffice` - Backoffice service
4. ✅ `/Users/virulana/colppy-benjamin` - Benjamin service
5. ✅ `/Users/virulana/colppy-crmintegration-connector` - CRM connector

**Search Results:**
- ❌ **NO GTM container IDs found** (`GTM-TRBKKZ2P`, `GTM-KQV2QTWJ`, etc.) in any repository
- ❌ **NO GTM snippet code found** (`googletagmanager.com`, `gtm.js`, `dataLayer`) in any repository
- ✅ Only found in mock files (`lib/mocks/`) which are test-only

**Key Findings:**
- **Mock files excluded:** All files in `/lib/mocks/` are test/mock files and ignored
- **Production registration flow:** Uses React/TypeScript in `mfe_authentication/`
- **Production main app:** Uses `index.php` as entry point (ExtJS application)
- **GTM Implementation Status:** ❌ **NOT FOUND in ANY production repository**

**Container Purposes (from GTM account):**
- `GTM-TRBKKZ2P` - "Sitio Web general (colppy.com)" → **Likely for WordPress marketing site**
- `GTM-KQV2QTWJ` - "Página de producto (app.colppy.com/registro) + (login.colppy.com)" → **Should be for registration pages**
- `GTM-KJLHJKCD` - "[Server] Página de registro" → **Server-side tracking**

**Complete Findings Across ALL Repositories:**

**Repositories Searched:**
1. ✅ `/Users/virulana/colppy-app` - Main application
2. ✅ `/Users/virulana/colppy-vue` - Vue components  
3. ✅ `/Users/virulana/svc_backoffice` - Backoffice service
4. ✅ `/Users/virulana/colppy-benjamin` - Benjamin service
5. ✅ `/Users/virulana/colppy-crmintegration-connector` - CRM connector

**Search Results:**
- ❌ **NO GTM container IDs found** in any repository
- ❌ **NO GTM snippet code found** (`googletagmanager.com`, `gtm.js`, `dataLayer`) in any repository
- ✅ Only found in mock files (test-only, not used in production)

**GTM Container Status:**
- `GTM-KQV2QTWJ` (for registration pages) - ❌ **EMPTY** (no tags configured)
- `GTM-TRBKKZ2P` (for general website) - ✅ Has tags configured

**Conclusion:**
- The public marketing website (www.colppy.com) is likely **WordPress-based** (evidence: `www.colppy.com/wp-content/` in README) - separate from these repositories
- GTM containers exist in your account but are **NOT implemented in any code repository**
- The registration flow in `app.colppy.com/registro` should use `GTM-KQV2QTWJ` but:
  1. ❌ **GTM container is NOT loaded in the code** (missing GTM snippet)
  2. ❌ **GTM container is EMPTY** (no tags configured even if it were loaded)
- **Conversion tracking is completely missing** from the actual registration flow

---

## 🏷️ Tags Configuration Analysis

### Container Status Summary

| Container ID | Purpose | Tags Configured? | Status |
|--------------|---------|------------------|--------|
| `GTM-TRBKKZ2P` | Sitio Web general (colppy.com) | ✅ Yes | Has tags (see below) |
| `GTM-KQV2QTWJ` | Página de producto (app.colppy.com/registro) | ❌ **EMPTY** | **No tags configured** |
| `GTM-KJLHJKCD` | [Server] Página de registro | Unknown | Server-side container |
| `GTM-P79WSXCH` | Staging página de registro | Unknown | Staging environment |

**⚠️ CRITICAL FINDING:**
- **`GTM-KQV2QTWJ`** (the container for registration pages) is **EMPTY** - no tags are configured
- This means even if GTM is loaded in the code, **no conversion tracking will fire** because there are no tags

### Tags Found in GTM-TRBKKZ2P Container (General Website)

#### 1. **Google Ads Conversion Tracking Tag**
- **Tag Name:** "A WAP Flotante"
- **Tag Type:** Google Ads Conversion Tracking
- **Trigger:** "Click ID what app_button"
- **Status:** ⚠️ **Triggered only on WhatsApp button click** (NOT on registration)
- **Last Edited:** 3 months ago

**Analysis:**
- This tag is configured for WhatsApp button clicks, NOT for registration conversions
- **This is a problem** - PMAX campaigns need conversion tracking on registration completion, not just WhatsApp clicks

#### 2. **Google Tag Tags**
- **Tag 1:** "Etiqueta de Google G-FXK524TXDM"
  - Type: Google Tag
  - Trigger: Initialization - All Page
  - Last Edited: 6 months ago

- **Tag 2:** "Google Tag G-TDL4R0Q5MX"
  - Type: Google Tag
  - Trigger: Initialization - All Page
  - Last Edited: 3 months ago

**Analysis:**
- These are Google Analytics 4 (GA4) tags
- They fire on all pages for general tracking
- **Not specifically configured for conversion tracking**

#### 3. **Conversion Linker Tag**
- **Tag Name:** "Vinculación de conversiones Google Ad"
- **Tag Type:** Conversion Linker
- **Triggers:** All Page + History Change (pushState)
- **Purpose:** Maintains conversion tracking across domains/pages

**Analysis:**
- ✅ This is correctly configured
- Helps maintain gclid (Google Click ID) across the user journey
- Essential for PMAX conversion tracking

#### 4. **Mixpanel Tags**
- **Tag 1:** "Mixpanel - UTM Meta register"
  - Type: Custom HTML
  - Trigger: All Page
  - Purpose: Captures UTM parameters for Mixpanel

- **Tag 2:** "Mixpanel - Visita"
  - Type: Mixpanel
  - Trigger: All Page
  - Purpose: Tracks page visits

**Analysis:**
- These capture UTM parameters for analytics
- **However, they don't fire conversion events to Google Ads**

---

## 🔄 Conversion Tracking Flow Analysis

### Current Implementation (What We Found)

#### **Step 1: User Clicks PMAX Ad**
```
User clicks PMAX ad → Google adds gclid to URL
URL: https://colppy.com/registro?utm_source=google&utm_medium=cpc&utm_campaign=PMax_PyMEs_lead_gen&gclid=ABC123
```

#### **Step 2: Registration Page Loads**
**❌ PROBLEM:** Production registration pages do NOT load any GTM container.

**Current State:**
- ✅ GTM containers exist in your account (`GTM-TRBKKZ2P`, `GTM-KQV2QTWJ`, etc.)
- ❌ Production registration pages (`mfe_authentication/src/`) have NO GTM snippet
- ❌ Production main app (`index.php`) has NO GTM snippet
- ⚠️ **Mock files have GTM-M699MG, but those aren't used in production** (so not a concern)

**Impact:**
- GTM cannot initialize on registration pages
- dataLayer is not available
- Conversion tags cannot fire

#### **Step 3: UTM Parameters Captured**
The new React registration flow captures UTM parameters:
```95:106:mfe_authentication/src/views/screens/register/register.tsx
    const paramsObj: QueryParams = {}
    queryParams.forEach((value, key) => {
      paramsObj[key] = value
    })
    postEmailValidate({
      codigo: CryptoJS.AES.encrypt(code, import.meta.env.VITE_SECRET_KEY).toString(),
      idUsuario: parameters.idUsuario,
      nombreUsuario: parameters.nombreUsuario,
      telefono: parameters.telefono,
      landingOrigen: 'Orgánico',
      ...paramsObj
    })
```

**Analysis:**
- ✅ UTM parameters are captured from URL
- ✅ Passed to backend registration endpoint
- ✅ Stored in database and HubSpot

#### **Step 4: Backend Registration Processing**
```58:63:resources/Provisiones/Usuario/1_0_0_0/delegates/AltaDelegate.php
            $empresaParams->datos_generales->utmSource = isset($parametros->utm_source) ? $parametros->utm_source : '';
            $empresaParams->datos_generales->utmMedium = isset($parametros->utm_medium) ? $parametros->utm_medium : '';
            $empresaParams->datos_generales->utmCampaign = isset($parametros->utm_campaign) ? $parametros->utm_campaign : '';
            $empresaParams->datos_generales->utmTerm = isset($parametros->utm_term) ? $parametros->utm_term : '';
            $empresaParams->datos_generales->utmContent = isset($parametros->utm_content) ? $parametros->utm_content : '';
            $empresaParams->datos_generales->gclid = isset($parametros->gclid) ? $parametros->gclid : '';
```

**Analysis:**
- ✅ gclid is captured and stored
- ✅ UTM parameters are stored
- ✅ Data flows to HubSpot CRM

#### **Step 5: Conversion Tracking (Production State)**

**Production Registration Flow (React - ACTUAL CODE):**
- ✅ Uses Mixpanel for analytics (`email-validation.tsx` line 62-81)
- ✅ Uses Intercom for tracking (`email-validation.tsx` line 64-71)
- ❌ **Missing:** Google Ads conversion tracking
- ❌ **Missing:** GTM dataLayer push for conversion event
- ❌ **Missing:** gclid passed to conversion tracking

**Note:** The old PHP conversion pixel code is in mock files only - it's not used in production, so it's not relevant here.

---

## 🎯 PMAX Campaign Configuration Analysis

### How PMAX Campaigns Should Work with Conversion Tracking

#### **What PMAX Needs:**
1. **Conversion Action** - A specific action (like "Registration") that Google can optimize for
2. **Conversion Tracking** - Properly configured tags that fire when registration completes
3. **gclid Preservation** - The Google Click ID must be maintained through the conversion
4. **Value Tracking** (Optional) - If you want to optimize for revenue/value

#### **Current PMAX Campaign Setup:**
From our Google Ads analysis:
- **Campaign:** "PMax_PyMEs_lead_gen" (ID: 23061668821)
- **Status:** ENABLED
- **Budget:** $40.000 ARS daily
- **Budget:** 40,000,000 micros (40,000 ARS)
- **Bidding Strategy:** Performance Max (auto-optimization)

#### **🔍 CRITICAL FINDING: How PMAX is Actually Tracking Conversions**

**✅ ACTUAL CONVERSION DATA:**
- **PMAX Campaign:** "PMax_PyMEs_lead_gen" (ID: 23061668821)
- **Conversions (Last 7 days):** **318 conversions** ✅
- **Conversion Value:** 318 (1 per conversion)

**✅ CONVERSION ACTION USED:**
- **Name:** "Web Colppy integral 2024 (web) Lead_Registro_Success"
- **ID:** 6984840895
- **Type:** `GOOGLE_ANALYTICS_4_CUSTOM` ⚠️
- **Status:** ENABLED
- **Category:** DEFAULT
- **Attribution Model:** Data-driven (Google Search Attribution)
- **Counting:** ONE_PER_CLICK

**This means:**
- ✅ **PMAX IS tracking conversions** - 318 in last 7 days
- ⚠️ **Conversions are imported from Google Analytics 4 (GA4)**, not direct Google Ads conversion tracking
- The conversion action "Lead_Registro_Success" is a GA4 custom event imported to Google Ads
- PMAX optimizes when GA4 receives the "Lead_Registro_Success" event

**🔍 Key Questions:**

1. **How is GA4 receiving "Lead_Registro_Success" events?**
   - Production code (`email-validation.tsx`) doesn't show GA4 event tracking
   - No GTM found in production registration pages
   - **Possible sources:**
     - GA4 tags in GTM-TRBKKZ2P (marketing site) might be tracking this
     - Server-side tracking (GTM-KJLHJKCD) might be sending events
     - GA4 might be loaded directly (not through GTM) on registration pages
     - Events might be tracked from a different page/flow (post-registration redirect)

2. **Is this optimal for PMAX?**
   - ⚠️ **GA4 imports have limitations** compared to direct Google Ads conversion tracking:
     - Attribution delay (can take 24-48 hours)
     - Data-driven attribution only (can't use last-click)
     - May not pass gclid as reliably
     - Requires GA4 and Google Ads to be linked properly

**Other Enabled Conversion Actions:**
- "TEST PQL" (ID: 7301473088) - WEBPAGE, SIGNUP, ENABLED
- "TEST PQL -Click iD" (ID: 7307624054) - WEBPAGE, SIGNUP, ENABLED  
- "TEST PQL-Element" (ID: 7307846625) - WEBPAGE, SIGNUP, ENABLED
- "Wap Flotante" (ID: 7270554419) - WEBPAGE, CONTACT, ENABLED (WhatsApp button)

#### **What's Missing:**

1. **❌ No GTM-based conversion tag for registration**
   - The only Google Ads conversion tag fires on WhatsApp button click
   - Registration completion doesn't trigger a conversion tag

2. **❌ Hardcoded conversion pixel doesn't pass gclid**
   - The old conversion code doesn't include gclid
   - This breaks attribution for PMAX campaigns

3. **❌ No dataLayer.push() for conversion events**
   - Modern GTM setup should use dataLayer events
   - No evidence of conversion events being pushed to dataLayer

---

## 🔧 Production Code Implementation Details

### **Production Registration Flow Analysis**

**Key Files (Production Only):**
- `mfe_authentication/src/views/screens/register/register.tsx` - Registration form
- `mfe_authentication/src/views/screens/email-validation/email-validation.tsx` - Email verification
- `resources/Provisiones/Usuario/1_0_0_0/delegates/AltaDelegate.php` - Backend registration handler

#### **Registration Success Flow (Production)**

**Step 1: Registration Form Submits**
```95:106:mfe_authentication/src/views/screens/register/register.tsx
    const paramsObj: QueryParams = {}
    queryParams.forEach((value, key) => {
      paramsObj[key] = value
    })
    postEmailValidate({
      codigo: CryptoJS.AES.encrypt(code, import.meta.env.VITE_SECRET_KEY).toString(),
      idUsuario: parameters.idUsuario,
      nombreUsuario: parameters.nombreUsuario,
      telefono: parameters.telefono,
      landingOrigen: 'Orgánico',
      ...paramsObj
    })
```

**Analysis:**
- ✅ UTM parameters captured from URL (`queryParams`)
- ✅ All params spread to API call
- ✅ gclid would be included if present in URL

**Step 2: Email Validation Completes Registration**
```60:87:mfe_authentication/src/views/screens/email-validation/email-validation.tsx
  useEffect(() => {
    if (isSuccess && data?.response.success) {
      trackEmailValidation()
      setIdentify(userData.idUsuario)
      setPropertyEmailValidation(true)
      tracking.setPropertyRoles(
        {
          mail: userData.idUsuario,
          name: userData.nombreUsuario
        },
        userData.roles
      )
      trackLogin(
        userData.idUsuario,
        userData.idUsuario,
        null,
        'pendiente_pago',
        '12',
        '1',
        new Date().toString(),
        data?.response.data!.idEmpresa
      )
      postLogin({
        idUsuario: userData.idUsuario,
        passwordAuth: userData.password
      })
    }
  }, [isSuccess])
```

**Current Implementation:**
- ✅ Tracks to Mixpanel (`trackEmailValidation()`, `trackLogin()`)
- ✅ Tracks to Intercom (`tracking.setPropertyRoles()`)
- ❌ **MISSING:** Google Ads conversion tracking
- ❌ **MISSING:** GTM dataLayer push
- ❌ **MISSING:** gclid retrieval and passing

**Step 3: Backend Captures gclid**
```58:63:resources/Provisiones/Usuario/1_0_0_0/delegates/AltaDelegate.php
            $empresaParams->datos_generales->utmSource = isset($parametros->utm_source) ? $parametros->utm_source : '';
            $empresaParams->datos_generales->utmMedium = isset($parametros->utm_medium) ? $parametros->utm_medium : '';
            $empresaParams->datos_generales->utmCampaign = isset($parametros->utm_campaign) ? $parametros->utm_campaign : '';
            $empresaParams->datos_generales->utmTerm = isset($parametros->utm_term) ? $parametros->utm_term : '';
            $empresaParams->datos_generales->utmContent = isset($parametros->utm_content) ? $parametros->utm_content : '';
            $empresaParams->datos_generales->gclid = isset($parametros->gclid) ? $parametros->gclid : '';
```

**Analysis:**
- ✅ gclid captured and stored in backend
- ✅ UTM parameters stored
- ✅ Data sent to HubSpot CRM
- ❌ **Problem:** gclid not available in frontend for conversion tracking

---

## 📊 Production UTM Parameter Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER CLICKS PMAX AD                                          │
│    URL: colppy.com/registro?utm_campaign=PMax_PyMEs_lead_gen   │
│         &utm_source=google&utm_medium=cpc&gclid=ABC123         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. REGISTRATION PAGE LOADS (Production React App)               │
│    ❌ GTM Container NOT loaded (not implemented in code)        │
│    ✅ React registration component loads                        │
│    ✅ gclid should be stored in localStorage                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. UTM PARAMETERS CAPTURED (Production)                         │
│    ✅ React: URLSearchParams captures all params                │
│       Location: register.tsx line 40, 95-98                    │
│    ✅ All params spread to API call                             │
│    ✅ gclid included if present in URL                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. BACKEND PROCESSING (Production)                              │
│    ✅ AltaDelegate.php captures:                               │
│       - utm_campaign, utm_source, utm_medium                   │
│       - gclid (Google Click ID)                                │
│       Location: resources/Provisiones/Usuario/1_0_0_0/         │
│                 delegates/AltaDelegate.php line 58-63          │
│    ✅ Stored in database                                        │
│    ✅ Sent to HubSpot CRM                                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. EMAIL VALIDATION COMPLETES (Production)                      │
│    ✅ Mixpanel tracking works                                   │
│       Location: email-validation.tsx line 62-81                │
│    ✅ Intercom tracking works                                   │
│    ❌ Google Ads conversion tracking MISSING                    │
│    ❌ GTM dataLayer.push() MISSING                              │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. CONVERSION ATTRIBUTION (❌ NOT WORKING)                      │
│    ❌ No conversion event fired                                  │
│    ❌ gclid not passed to Google Ads                            │
│    ❌ PMAX can't attribute conversion to campaign               │
│    ❌ PMAX can't optimize effectively                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚠️ Critical Issues Found (Production Code Only)

### **Issue #1: No GTM Implementation in Production Code**
**Severity:** 🔴 **CRITICAL**

- **Production Registration:** Uses React/TypeScript in `mfe_authentication/src/`
- **Problem:** GTM container snippet is NOT implemented in production registration pages
- **Current State:** No GTM found in `index.php` or React registration components
- **Impact:** 
  - GTM cannot track conversions from the actual user registration flow
  - PMAX campaigns can't attribute registrations to ad clicks
  - Conversion tracking is completely missing in production
- **Fix Required:** Add GTM container snippet to production registration pages

**Note:** The mock file with `GTM-M699MG` is irrelevant - mock files aren't used in production, so that's not the problem. The problem is that production code has NO GTM at all.

### **Issue #2: No Google Ads Conversion Tracking in Production**
**Severity:** 🔴 **CRITICAL**

- **Production Code Location:** `mfe_authentication/src/views/screens/email-validation/email-validation.tsx`
- **Current Implementation:** Only tracks to Mixpanel and Intercom (lines 62-81)
- **Problem:** No Google Ads conversion tracking when registration completes
- **Impact:** PMAX campaigns cannot track or optimize for actual registrations
- **Fix Required:** Add conversion tracking when registration succeeds

### **Issue #3: GTM Container Exists But Not Connected**
**Severity:** 🟠 **HIGH**

- **GTM Container:** `GTM-TRBKKZ2P` exists in your GTM account
- **Problem:** This container is not loaded in production registration flow
- **Impact:** Even if tags are configured in GTM, they won't fire because GTM isn't loaded
- **Fix Required:** Add GTM container snippet to registration pages

### **Issue #4: No dataLayer Push for Conversions**
**Severity:** 🟠 **HIGH**

- **Problem:** Production registration flow doesn't push conversion events to dataLayer
- **Location:** `mfe_authentication/src/views/screens/email-validation/email-validation.tsx`
- **Impact:** GTM can't trigger conversion tags based on events
- **Fix Required:** Add `dataLayer.push()` when registration completes successfully

### **Issue #5: gclid Not Used in Conversion Tracking**
**Severity:** 🟠 **HIGH**

- **Current:** gclid is captured in backend (line 63 in `AltaDelegate.php`) and stored in HubSpot
- **Problem:** gclid is NOT passed to Google Ads conversion tracking
- **Impact:** PMAX can't attribute conversions to specific ad clicks
- **Fix Required:** Pass gclid to conversion tracking when registration completes

---

## ✅ What's Working Correctly (Production Code)

1. **UTM Parameter Capture** ✅
   - Production React registration captures all UTM parameters from URL
   - Location: `register.tsx` line 40, 95-98
   - Backend stores them correctly in `AltaDelegate.php`
   - HubSpot receives UTM data

2. **gclid Capture (Backend)** ✅
   - Backend captures gclid from URL parameters
   - Location: `AltaDelegate.php` line 63
   - Stored in database and HubSpot
   - ⚠️ **But:** Not retrieved in frontend for conversion tracking

3. **Mixpanel Tracking** ✅
   - Production registration tracks to Mixpanel
   - Location: `email-validation.tsx` line 62, 72-81
   - UTM parameters tracked
   - Registration events tracked

4. **Intercom Tracking** ✅
   - Production registration tracks to Intercom
   - Location: `email-validation.tsx` line 64-71

5. **GTM Container Exists** ✅
   - `GTM-TRBKKZ2P` exists in your GTM account
   - Conversion Linker tag configured
   - ⚠️ **But:** Not loaded in production registration pages

---

## 🛠️ Recommended Fixes (Production Code Only)

### **Fix #1: Add GTM Container to Production Registration Pages**

**GTM Container ID:** `GTM-KQV2QTWJ` ⚠️ **Use this one for registration pages!**

**Why `GTM-KQV2QTWJ` and not `GTM-TRBKKZ2P`:**
- `GTM-TRBKKZ2P` = "Sitio Web general (colppy.com)" → For WordPress marketing site
- `GTM-KQV2QTWJ` = "Página de producto (app.colppy.com/registro) + (login.colppy.com)" → **For registration pages**

**Where to Add:**
1. **Registration MFE Root Component** - Add GTM snippet in the HTML head of the registration MFE
   - Location: Wherever `mfe_authentication` is embedded/loaded
   - This is the `app.colppy.com/registro` pages
2. **OR in main app entry** - If registration is part of main app, add to `index.php`

**GTM Snippet Code:**
```html
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'//www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','GTM-KQV2QTWJ');</script>
<!-- End Google Tag Manager -->

<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="//www.googletagmanager.com/ns.html?id=GTM-KQV2QTWJ"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
```

**⚠️ Important:** Use `GTM-KQV2QTWJ` (the container specifically for registration pages), NOT `GTM-TRBKKZ2P` (which is for the general marketing website).

**Action Required:**
1. Determine where registration pages are served (MFE or main app)
2. Add GTM snippet to HTML head
3. Test that GTM loads correctly (check browser console for `dataLayer`)
4. Verify dataLayer is available

---

### **Fix #2: Create Registration Conversion Tag in GTM**

**Steps:**
1. Go to GTM container `GTM-KQV2QTWJ` (the one for app.colppy.com/registro pages)
2. Create new tag: "Google Ads - Registration Conversion"
3. Tag Type: **Google Ads Conversion Tracking**
4. Conversion ID: `1014054320` (verify this in your Google Ads account)
5. Conversion Label: `jMUjCKDUpQQQsPvE4wM` (verify this in your Google Ads account)
6. **Trigger:** Create new trigger "Registration Complete"
   - Trigger Type: Custom Event
   - Event Name: `registration_complete`
   - This trigger fires when `dataLayer.push({event: 'registration_complete'})` is called

**Alternative (Better):** Use Google Tag (gtag) instead:
- Tag Type: **Google Tag**
- Configuration Tag: Use existing Google Tag (G-TDL4R0Q5MX or G-FXK524TXDM)
- Event: `conversion`
- Conversion ID and Label as parameters

**Note:** Verify conversion ID and label in Google Ads:
1. Go to Google Ads → Tools & Settings → Conversions
2. Find your "Registration" conversion action
3. Check the Conversion ID and Label

---

### **Fix #3: Add dataLayer Push on Registration Success**

**File:** `mfe_authentication/src/views/screens/email-validation/email-validation.tsx`

**Add after line 61 (after registration succeeds):**

```typescript
// Push conversion event to GTM dataLayer for Google Ads tracking
if (typeof window !== 'undefined' && window.dataLayer) {
  // Get gclid from URL parameters or localStorage (set when user first lands)
  const urlParams = new URLSearchParams(window.location.search);
  const gclid = urlParams.get('gclid') || localStorage.getItem('gclid') || '';
  
  window.dataLayer.push({
    'event': 'registration_complete',
    'conversion_id': '1014054320', // Verify this in Google Ads
    'conversion_label': 'jMUjCKDUpQQQsPvE4wM', // Verify this in Google Ads
    'value': 0,
    'currency': 'ARS',
    'gclid': gclid,
    'user_id': userData.idUsuario,
    'company_id': data?.response.data?.idEmpresa || ''
  });
}
```

**Add helper to store gclid on initial page load:**

**File:** `mfe_authentication/src/views/screens/register/register.tsx`

**Add useEffect to capture gclid when user first lands:**

```typescript
useEffect(() => {
  // Store gclid from URL if present (for conversion attribution)
  const urlParams = new URLSearchParams(window.location.search);
  const gclid = urlParams.get('gclid');
  if (gclid && typeof window !== 'undefined') {
    localStorage.setItem('gclid', gclid);
    // Also set cookie for GTM Conversion Linker
    document.cookie = `gclid=${gclid}; path=/; max-age=2592000`; // 30 days
  }
}, []);
```
            'conversion_label': 'jMUjCKDUpQQQsPvE4wM',
            'value': 0,
            'currency': 'ARS',
            'gclid': gclid
        });
    }

    // Fallback: hardcoded pixel (keep for now, remove after GTM is verified)
    var pixelUrl = '//www.googleadservices.com/pagead/conversion/1014054320/?value=0&label=jMUjCKDUpQQQsPvE4wM&guid=ON&script=0';
    if (gclid) {
        pixelUrl += '&gclid=' + encodeURIComponent(gclid);
    }
    $("#registro").append('<div style="display:inline;"><img height="1" width="1" style="border-style:none;" alt="" src="' + pixelUrl + '"/></div>');
}

// Helper function to get gclid
function getGclid() {
    // Try to get from URL
    var urlParams = new URLSearchParams(window.location.search);
    var gclid = urlParams.get('gclid');
    
    // If not in URL, try cookie (set by Conversion Linker)
    if (!gclid) {
        gclid = getCookie('_gcl_au') || getCookie('gclid');
    }
    
    return gclid;
}
```

---

### **Fix #4: Verify Conversion ID and Label**

**Important:** Before implementing, verify the conversion ID and label in Google Ads:

1. **Go to Google Ads:**
   - Tools & Settings → Conversions
   - Find your "Registration" or "Lead" conversion action
   - Click on it to see details

2. **Check Conversion Details:**
   - Conversion ID: Should be `1014054320` (or different - verify!)
   - Conversion Label: Should match `jMUjCKDUpQQQsPvE4wM` (or different - verify!)
   
3. **Update code with correct values:**
   - Replace hardcoded values in Fix #3 with actual values from Google Ads

**Note:** The conversion ID and label found in mock files may be outdated or incorrect. Always verify against your actual Google Ads account.

---

### **Fix #5: Configure PMAX-Specific Conversion Action**

**In Google Ads:**
1. Go to Tools & Settings → Conversions
2. Verify conversion action "Registration" exists
3. Ensure it's linked to the conversion tag in GTM
4. For PMAX campaigns:
   - Go to campaign settings
   - Select "Registration" as the conversion goal
   - Set conversion value (if applicable)

**In GTM:**
1. Create conversion tag specifically for PMAX
2. Use the same conversion ID/label
3. Ensure gclid is passed correctly
4. Test with GTM Preview mode

---

## 📝 Step-by-Step Implementation Guide

### **Phase 1: Fix Critical Issues (Week 1)**

#### **Day 1-2: Fix GTM Container ID**
1. ✅ Update `header.php` with correct container ID
2. ✅ Test GTM loads on registration page
3. ✅ Verify dataLayer is available in browser console

#### **Day 3-4: Create Conversion Tag in GTM**
1. ✅ Create "Registration Conversion" tag
2. ✅ Configure trigger for `registration_complete` event
3. ✅ Test in GTM Preview mode
4. ✅ Publish GTM container

#### **Day 5: Add dataLayer Push**
1. ✅ Add dataLayer.push() to React registration flow
2. ✅ Add dataLayer.push() to old PHP registration flow
3. ✅ Test conversion fires correctly

### **Phase 2: Enhance Tracking (Week 2)**

#### **Day 1-2: gclid Preservation**
1. ✅ Implement gclid storage/retrieval
2. ✅ Ensure gclid passed to conversion events
3. ✅ Test attribution in Google Ads

#### **Day 3-4: PMAX Optimization**
1. ✅ Verify conversions appear in Google Ads
2. ✅ Check PMAX campaign conversion tracking
3. ✅ Monitor conversion data quality

#### **Day 5: Documentation & Testing**
1. ✅ Document new setup
2. ✅ Create testing checklist
3. ✅ Train team on new tracking

---

## 🧪 Testing Checklist

### **Pre-Deployment Testing**

- [ ] GTM container loads on registration page
- [ ] dataLayer is accessible in browser console
- [ ] UTM parameters captured from URL
- [ ] gclid stored in localStorage/cookie
- [ ] Registration completion fires `registration_complete` event
- [ ] GTM conversion tag fires on registration
- [ ] Conversion appears in Google Ads (within 24-48 hours)
- [ ] PMAX campaign shows conversions
- [ ] Attribution works correctly (conversion linked to ad click)

### **Post-Deployment Verification**

- [ ] Check Google Ads conversion reports
- [ ] Verify PMAX campaign optimization
- [ ] Monitor conversion value (if set)
- [ ] Check for duplicate conversions
- [ ] Verify gclid attribution in reports

---

## 📚 Beginner-Friendly Explanations

### **What is Google Tag Manager (GTM)?**

Think of GTM as a **control center** for all your website tracking. Instead of hardcoding tracking code in multiple places, you:
1. Install GTM once on your website
2. Configure all tracking tags inside GTM
3. GTM automatically fires the right tags at the right time

**Benefits:**
- ✅ No need to edit code for every tracking change
- ✅ Easy to add/remove tracking tags
- ✅ Centralized management
- ✅ Better testing with Preview mode

### **What is a Conversion?**

A **conversion** is when a user completes a valuable action, like:
- Registering for your service
- Making a purchase
- Signing up for a trial

For PMAX campaigns, Google needs to know when conversions happen so it can:
- Learn which ads work best
- Optimize to get more conversions
- Show your ads to people likely to convert

### **What is gclid (Google Click ID)?**

**gclid** is like a **receipt number** that Google gives each ad click:
- When someone clicks your PMAX ad, Google adds `?gclid=ABC123` to the URL
- This ID links the click to the conversion
- Without gclid, Google can't tell which ad led to which conversion

**Why it matters:**
- PMAX needs gclid to attribute conversions to your campaign
- Without it, conversions show up but Google can't optimize properly

### **What is dataLayer?**

**dataLayer** is like a **messenger** between your website and GTM:
- Your code "pushes" events to dataLayer: `dataLayer.push({event: 'registration_complete'})`
- GTM "listens" to dataLayer and fires tags when events happen
- This is the modern way to track conversions

**Example:**
```javascript
// When registration completes, tell GTM:
dataLayer.push({
  'event': 'registration_complete',
  'conversion_id': '1014054320',
  'gclid': 'ABC123'
});

// GTM sees this event and fires the conversion tag
```

### **How PMAX Campaigns Use Conversion Tracking**

1. **User clicks PMAX ad** → Google adds gclid to URL
2. **User visits your site** → GTM loads, stores gclid
3. **User registers** → Your code pushes conversion event to dataLayer
4. **GTM fires conversion tag** → Sends conversion + gclid to Google Ads
5. **Google Ads links conversion to ad click** → PMAX learns and optimizes

**Current Problem:**
- Step 3-4 are broken (no conversion event pushed, no tag fires)
- Step 5 fails (no gclid passed, so Google can't link conversion to click)

---

## 🎯 PMAX-Specific Configuration

### **How to Link PMAX Campaigns to Conversion Tracking**

#### **In Google Ads:**

1. **Create/Verify Conversion Action:**
   - Go to: Tools & Settings → Conversions
   - Look for "Registration" or create new one
   - Note the Conversion ID and Label (you have: `1014054320` / `jMUjCKDUpQQQsPvE4wM`)

2. **Link to GTM:**
   - In conversion action settings, select "Google Tag Manager"
   - Enter your GTM container ID: `GTM-TRBKKZ2P`
   - Google will automatically detect the conversion tag

3. **Assign to PMAX Campaign:**
   - Go to your PMAX campaign: "PMax_PyMEs_lead_gen"
   - Settings → Conversion goals
   - Select "Registration" as primary conversion
   - Save

#### **In GTM:**

1. **Create Conversion Tag:**
   - Tag Type: Google Ads Conversion Tracking
   - Conversion ID: `1014054320`
   - Conversion Label: `jMUjCKDUpQQQsPvE4wM`
   - Conversion Value: `{{Conversion Value}}` (variable, can be 0)
   - Currency Code: ARS

2. **Create Trigger:**
   - Trigger Type: Custom Event
   - Event Name: `registration_complete`
   - This trigger fires when registration succeeds

3. **Link gclid:**
   - In tag configuration, enable "Use Google Tag (gtag) settings"
   - Or manually pass gclid via dataLayer variable

---

## 🔍 Verification Steps

### **How to Verify Conversion Tracking is Working**

#### **Step 1: Check GTM is Loading**
1. Open registration page in browser
2. Open Developer Tools (F12)
3. Go to Console tab
4. Type: `dataLayer`
5. Should see array with GTM data
6. If empty or error → GTM not loading (check container ID)

#### **Step 2: Test Conversion Event**
1. Complete a test registration
2. In Console, check dataLayer:
   ```javascript
   dataLayer.filter(item => item.event === 'registration_complete')
   ```
3. Should see conversion event pushed
4. If not → dataLayer.push() not working

#### **Step 3: Check GTM Tag Fires**
1. Use GTM Preview mode
2. Complete test registration
3. In GTM Preview, check "Tags" section
4. Should see "Google Ads Conversion" tag fired
5. If not → Trigger not configured correctly

#### **Step 4: Verify in Google Ads**
1. Wait 24-48 hours after conversion
2. Go to Google Ads → Tools & Settings → Conversions
3. Check "Registration" conversion action
4. Should see conversions appearing
5. Click on conversion → Check "Attribution" tab
6. Should see gclid and campaign info

---

## 📊 Expected Results After Fixes

### **Before Fixes:**
- ❌ GTM not loading (wrong container ID)
- ❌ No conversion tag fires on registration
- ❌ Conversions not attributed to PMAX campaigns
- ❌ PMAX can't optimize effectively

### **After Fixes:**
- ✅ GTM loads correctly
- ✅ Conversion tag fires on every registration
- ✅ gclid preserved and passed to conversion
- ✅ Conversions properly attributed to PMAX
- ✅ PMAX can optimize and learn
- ✅ Better conversion rates over time

---

## 🚨 Immediate Action Items

### **Priority 1 (Do Today):**
1. ✅ **Update GTM container ID** in `header.php`
   - Change `GTM-M699MG` → `GTM-TRBKKZ2P`
   - Test immediately

2. ✅ **Verify GTM loads** on registration page
   - Check browser console
   - Confirm dataLayer exists

### **Priority 2 (This Week):**
3. ✅ **Create conversion tag in GTM**
   - Use conversion ID: `1014054320`
   - Use conversion label: `jMUjCKDUpQQQsPvE4wM`
   - Create trigger for registration completion

4. ✅ **Add dataLayer.push() to registration flow**
   - Both React and PHP flows
   - Include gclid in the push

### **Priority 3 (Next Week):**
5. ✅ **Test and verify conversions**
   - Use GTM Preview mode
   - Check Google Ads conversion reports
   - Verify PMAX campaign shows conversions

---

## 📖 Additional Resources

### **Google Tag Manager Documentation:**
- [GTM Setup Guide](https://support.google.com/tagmanager/answer/6103696)
- [Conversion Tracking Setup](https://support.google.com/tagmanager/answer/6105160)
- [dataLayer Guide](https://developers.google.com/tag-manager/devguide)

### **Google Ads PMAX Documentation:**
- [PMAX Conversion Tracking](https://support.google.com/google-ads/answer/9322685)
- [Conversion Attribution](https://support.google.com/google-ads/answer/1728595)

### **Testing Tools:**
- GTM Preview Mode (built into GTM)
- Google Tag Assistant (browser extension)
- Google Ads Conversion Tracking Test Tool

---

## 📝 Summary

### **Key Findings:**
1. **GTM container mismatch** - Code uses non-existent container
2. **No registration conversion tag** - Only WhatsApp button tracked
3. **Hardcoded conversion missing gclid** - Breaks attribution
4. **No dataLayer events** - Modern tracking not implemented
5. **UTM capture works** - But not connected to conversion tracking

### **Impact on PMAX:**
- PMAX campaigns are running but can't properly track conversions
- Conversions may be showing but not attributed correctly
- PMAX optimization is likely suboptimal
- Budget may be wasted on non-converting traffic

### **Next Steps:**
1. Fix GTM container ID (30 minutes)
2. Create conversion tag in GTM (1 hour)
3. Add dataLayer.push() to code (2 hours)
4. Test and verify (1 day)
5. Monitor results (ongoing)

---

**Document Version:** 1.0  
**Last Updated:** November 22, 2024  
**Status:** Analysis Complete - Awaiting Implementation

