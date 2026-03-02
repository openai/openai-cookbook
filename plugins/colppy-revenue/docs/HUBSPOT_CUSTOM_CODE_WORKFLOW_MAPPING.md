# HubSpot Custom Code Workflow Mapping

**Document Purpose:** Complete documentation of all HubSpot custom code workflows, their features, notification types, and workflow URLs for the new Head of Revenue.

**Last Updated:** 2025-12-30  
**Maintained By:** CEO Assistant

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Custom Code Workflows](#custom-code-workflows)
   - [First Deal Won Date Calculation](#1-first-deal-won-date-calculation)
   - [Accountant Channel Deal Workflow](#2-accountant-channel-deal-workflow)
   - [Additional Product Association Workflow](#3-additional-product-association-workflow)
   - [Company Blank Field Validator](#4-company-blank-field-validator)
   - [Deal Stage Update Workflow](#5-deal-stage-update-workflow)
3. [Notification Channels](#notification-channels)
4. [Environment Variables](#environment-variables)
5. [Quick Reference](#quick-reference)

---

## Overview

This document provides a complete mapping of all HubSpot custom code workflows in the Colppy CRM system. Each workflow is designed to automate specific business processes and send Slack notifications to the `#intercom_mixpanel_notification` channel (ID: `C07RY5760TZ`) for visibility and action tracking.

### Common Features Across All Workflows

- ✅ **Slack Notifications:** All workflows send detailed notifications to `#intercom_mixpanel_notification`
- ✅ **Comprehensive Logging:** Detailed console logs for debugging and audit trails
- ✅ **Error Handling:** Graceful error handling with fallback notifications
- ✅ **HubSpot API Integration:** Uses HubSpot Private App token (`ColppyCRMAutomations`)

---

## Custom Code Workflows

### 1. First Deal Won Date Calculation

**File:** `tools/scripts/hubspot/custom_code/hubspot_first_deal_won_calculations.js`  
**Workflow URL:** https://app.hubspot.com/workflows/19877595/platform/flow/1693911922/edit/actions/1/custom-code  
**Version:** 1.8.0  
**Last Updated:** 2025-12-30

#### Purpose
Calculates `first_deal_closed_won_date` and `company_churn_date` (fecha de baja) for companies based on their PRIMARY deal associations. Includes auto-fix capabilities for missing PRIMARY associations, data consistency fixes, and intelligent churn detection.

#### Key Features
- ✅ **Auto-Fix:** Automatically adds PRIMARY associations when safe to do so
- ✅ **Churn Detection:** Tracks company churn dates based on deal stages (only stage 31849274 counts as churn)
- ✅ **Churn Date Clearing:** Automatically clears churn date when company has won deals (even non-primary)
- ✅ **Data Consistency Fix:** Calculates `first_deal_closed_won_date` for churned companies when missing OR incorrect
- ✅ **Historical CloseDate:** Fetches historical `closeDate` from property history when deal's current `closeDate` is incorrect (after churn date or equals churn date)
- ✅ **Churn Date Fallback:** Uses `fecha_de_desactivacion` as fallback when `fecha_pedido_baja` is null (older field that was used as fecha de baja)
- ✅ **Date Normalization:** Uses date-only comparison (YYYY-MM-DD) to prevent false updates from format differences
- ✅ **Empty String Clearing:** Uses `""` (not `null`) to properly clear date fields in HubSpot
- ✅ **Owner Resolution:** Shows deal and company owner names in Slack notifications
- ✅ **Edge Case Handling:** Handles trial companies, accountants, referrers, data quality issues, incorrect dates
- ✅ **Slack Notifications:** Detailed notifications for all state changes including data fixes

#### Trigger
- **When:** Company record is created or updated
- **Event Type:** Company property change or creation

#### Fields Updated
- `first_deal_closed_won_date` - Date of first PRIMARY closed-won deal (or earliest PRIMARY deal closeDate if churned)
- `company_churn_date` (fecha de baja) - Date when company churned (if applicable), cleared when company has won deals

#### Notification Types
1. **`success`** - Field updated successfully with deal details
2. **`warning`** - No PRIMARY deals found (requires manual review)
3. **`info`** - No won deals found (primary deals exist but none are closed-won)
4. **`accountant_verification`** - Accountant company with deals but no PRIMARY associations (verification needed)
5. **`auto_fix_available`** - Auto-fix available for missing PRIMARY associations
6. **`error`** - Workflow execution failed

**Special Notification Titles:**
- **`🔴 Churn + First Date Fixed`** - Company is churned and `first_deal_closed_won_date` was calculated from PRIMARY deals
- **`✅ Auto-Fix: Churn Date Cleared`** - Churn date cleared because company has won deals
- **`🔴 Company Churn Detected`** - Company marked as churned with churn date set

#### Slack Channel
- **Channel ID:** `C07RY5760TZ`
- **Channel Name:** `#intercom_mixpanel_notification`

#### Business Logic

**Step 1: Deal Association Retrieval**
1. Retrieves all deal associations for the company (paginated)
2. Identifies PRIMARY associations (type ID 5 or 6, or label contains "primary")
3. Separates deals into `primaryDealIds[]` and `allDealIds[]`

**Step 2: Deal Details Retrieval**
1. Fetches deal properties: `dealstage`, `closedate`, `dealname`, `amount`, `fecha_de_desactivacion`, `fecha_pedido_baja`, `hubspot_owner_id`
2. Processes ALL deals (not just primary) to find true first won date
3. **Historical CloseDate Detection:** For churned deals (stage 31849274), checks if `closeDate` has data quality issues:
   - If `closeDate` equals `fecha_pedido_baja` OR `closeDate` is after `fecha_de_desactivacion` (churn date)
   - Fetches historical `closeDate` from property history (when deal was FIRST set to closed won)
   - Uses historical date instead of current incorrect `closeDate`
4. Identifies won deals: `dealstage === 'closedwon'` or `'34692158'`
5. Builds `wonDates[]` array with all won deal dates (using historical dates when available)

**Step 3: Calculation and Update Logic**

**Path A: No Won Deals (`wonDates.length === 0`)**
1. Checks for auto-fix: won deals without PRIMARY associations
   - If found: adds PRIMARY to oldest won deal
   - If successful: immediately clears churn date
2. Counts ALL won deals (primary + non-primary) to determine if company is active
3. Determines churn status:
   - Company is churned ONLY if:
     - Has primary deals (was a customer)
     - Has NO won deals at all (primary OR non-primary)
     - Has deals in ACTUAL CHURN STAGE (31849274), not just `closedlost`
4. **Data Consistency Fix:** If company is churned but `first_deal_closed_won_date` is blank OR incorrect (after churn date):
   - Finds earliest `closeDate` from PRIMARY deals (closed won OR churned)
   - Uses historical `closeDate` if available (from property history)
   - Sets `first_deal_closed_won_date` to that date
5. Sets churn date from (with fallback logic):
   - Priority 1: `fecha_pedido_baja` from most recent churned deal (primary churn date field)
   - Priority 2: `fecha_de_desactivacion` from most recent churned deal (fallback - older field that was used as fecha de baja)
   - Priority 3: `closeDate` from most recent churned deal (last resort)
6. Clears churn date if company has ANY won deals (even non-primary)

**Path B: Has Won Deals (`wonDates.length > 0`)**
1. Calculates first won date: `Math.min(...wonDates)`
2. Checks for auto-fix: won deals without PRIMARY associations
   - If found: adds PRIMARY to oldest won deal
3. Counts ALL won deals (primary + non-primary)
4. **Always clears churn date** if ANY won deals exist (company is active)
5. Updates `first_deal_closed_won_date` if different from current value

**Date Comparison:**
- Uses date-only format (YYYY-MM-DD) for comparison, ignoring time/milliseconds
- Prevents false updates from format differences (e.g., `2025-06-01T00:00:00Z` vs `2025-06-01T00:00:00.000Z`)

**Field Clearing:**
- Uses empty string `""` (not `null`) to clear date fields in HubSpot
- HubSpot API requires `""` to clear date fields, `null` is ignored

**Edge Cases Handled:**
- Trial companies (lifecycle stage = 'lead') - skipped
- Accountant companies - sends verification notification
- Missing PRIMARY associations - attempts auto-fix when safe
- Companies with won deals but not marked as PRIMARY (data quality issue) - auto-fixes and clears churn date
- Churned companies with missing `first_deal_closed_won_date` - calculates from PRIMARY deals (closed won OR churned)
- Churned companies with incorrect `first_deal_closed_won_date` (after churn date) - recalculates using historical `closeDate`
- Deals with incorrect `closeDate` (after churn date or equals churn date) - fetches historical `closeDate` from property history
- Companies with `fecha_pedido_baja` = null - falls back to `fecha_de_desactivacion` for churn date
- Companies with `churn_date` but no PRIMARY deals - clears `churn_date` (not a customer, just a channel partner/accountant)

#### Special Cases

- **Trial Companies:** Skipped (no notification sent) - Companies in 'lead' lifecycle stage
- **Accountant Companies:** Sends verification notification (may not have PRIMARY deals)
- **Auto-Fix PRIMARY:** Only for single-company deals, non-accountant, missing PRIMARY
- **Active Companies with Churn Date:** Automatically clears churn date when won deals are detected
- **Churned Companies Missing First Date:** Automatically calculates `first_deal_closed_won_date` from PRIMARY deals (closed won OR churned)
- **Churned Companies with Incorrect First Date:** Automatically recalculates `first_deal_closed_won_date` if it's after churn date
- **Data Quality Issues:** Handles companies with won deals not marked as PRIMARY - auto-fixes and clears churn date
- **Historical CloseDate:** For churned deals with incorrect `closeDate`, fetches historical value from property history
- **Churn Date Fallback:** Uses `fecha_de_desactivacion` when `fecha_pedido_baja` is null (backward compatibility)
- **Non-Customer Churn Dates:** Clears `churn_date` for companies without PRIMARY deals (not customers, just channel partners)

#### Workflow Outcomes

- **`UPDATE_MADE`** - Fields updated successfully
- **`CHURN_DETECTED`** - Company marked as churned
- **`FIRST_DATE_FIXED_FOR_CHURNED`** - Fixed data inconsistency: set `first_deal_closed_won_date` for churned company
- **`CHURN_AND_FIRST_DATE_FIXED`** - Both churn date and first date updated
- **`AUTO_FIX_CHURN_CLEARED`** - Auto-fixed PRIMARY and cleared churn date
- **`AUTO_FIX_SUCCESS`** - Successfully added PRIMARY association
- **`NO_CHANGE_NEEDED`** - Fields already correct
- **`TRIAL_COMPANY_SKIPPED`** - Trial company, no action needed

---

### 2. Accountant Channel Deal Workflow

**File:** `tools/scripts/hubspot/workflows/hubspot_accountant_channel_deal_workflow.js`  
**Workflow URL:** https://app.hubspot.com/workflows/19877595/platform/flow/1611949700/edit/actions/10/custom-code  
**Version:** 1.1.0  
**Last Updated:** 2025-11-08

#### Purpose
Evaluates a HubSpot deal to determine whether the Accountant Channel team participated in the sale and updates the custom property `accountant_channel_involucrado_en_la_venta` accordingly.

#### Key Features
- ✅ **Owner Team Inspection:** Resolves the deal owner's team and flags Accountant Channel members
- ✅ **Collaborator Analysis:** Retrieves collaborator owners from `hs_all_collaborator_owner_ids`
- ✅ **Property Enforcement:** Sets `accountant_channel_involucrado_en_la_venta` to "true" or "false"
- ✅ **Slack Visibility:** Sends success/info/error notifications with reasoning and context
- ✅ **Robust Logging:** Provides granular logs for diagnostics and workflow validation

#### Trigger
- **When:** Deal record is created or updated
- **Event Type:** Deal property change or creation

#### Fields Updated
- `accountant_channel_involucrado_en_la_venta` - Boolean field indicating Accountant Channel involvement

#### Notification Types
1. **`success`** - Field updated successfully (from false to true or vice versa)
2. **`info`** - Field already set to correct value (no update needed)
3. **`error`** - Deal not found, field update failed, or workflow error

#### Slack Channel
- **Channel ID:** `C07RY5760TZ`
- **Channel Name:** `#intercom_mixpanel_notification`

#### Business Logic
1. Retrieves deal details including owner and collaborators
2. Checks if deal owner belongs to "Accountant Channel" team
3. Checks all deal collaborators for Accountant Channel team membership
4. Sets field to `true` if owner OR any collaborator is from Accountant Channel
5. Sets field to `false` if no Accountant Channel involvement
6. Updates field only if value changed

#### Team Detection
- Uses HubSpot Owners API to fetch team information
- Checks for team name: "Accountant Channel" or "accountant_channel"
- Validates active status of owners

---

### 3. Additional Product Association Workflow

**File:** `tools/scripts/hubspot/workflows/hubspot_additional_product_created.js`  
**Workflow URL:** https://app.hubspot.com/workflows/19877595/platform/flow/1699053467/edit/actions/6/custom-code  
**Version:** 1.0.27  
**Last Updated:** 2025-11-08

#### Purpose
Automates the association of an Additional Product company with the correct customer deal. Validates the secondary company, traces the originating contact, resolves the primary customer company, finds the newest additional-product deal, applies proper labels, and ensures correct associations.

#### Key Features
- ✅ **Company Validation:** Confirms `empresa_adicional` field and captures owner metadata
- ✅ **Contact Discovery:** Pulls the first associated contact and resolves ownership
- ✅ **Primary Customer Resolution:** Finds the contact's primary company (association typeId 1)
- ✅ **Deal Identification:** Locates the latest deal in stage "Negociación Producto Adicional" with `empresa_adicional = true`
- ✅ **Label Enforcement:** Adds "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol" label on contact ↔ deal link
- ✅ **Association Clean-Up:** Uses v4 batch archive to strip unwanted labels from additional-company association while preserving STANDARD (typeId 342)
- ✅ **Customer Linkage:** Adds STANDARD (typeId 341) association between deal and primary customer company if missing
- ✅ **Slack Visibility:** Sends detailed success/error notifications with links to company, contact, and deal

#### Trigger
- **When:** Company record is created or updated
- **Event Type:** Company property change (specifically when `empresa_adicional = true`)

#### Fields Updated
- **Deal Associations:** Adds STANDARD (341) association between deal and primary customer company
- **Contact-Deal Labels:** Adds "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol" label
- **Company-Deal Associations:** Removes unwanted labels, preserves STANDARD (342) association

#### Notification Types
1. **`success`** - Additional product deal associations configured successfully
2. **`error`** - Validation failed, contact not found, primary company not found, deal not found, or association update failed

#### Slack Channel
- **Channel ID:** `C07RY5760TZ`
- **Channel Name:** `#intercom_mixpanel_notification`

#### Business Logic
1. Validates company has `empresa_adicional = true`
2. Finds first associated contact
3. Resolves contact's primary company (association type 1)
4. Searches for newest deal in "Negociación Producto Adicional" stage with `empresa_adicional = true`
5. Adds contact-deal label: "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol"
6. Cleans up unwanted deal-company association labels (preserves STANDARD 342)
7. Adds STANDARD (341) association between deal and primary customer company

#### Association Types Used
- **Type 341 (STANDARD):** Primary customer company ↔ deal (billing relationship)
- **Type 342 (STANDARD):** Additional company ↔ deal (tracking relationship)
- **Type 279:** "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol" label

---

### 4. Company Blank Field Validator

**File:** `tools/scripts/hubspot/workflows/hubspot_company_blank_field_validator.js`  
**Workflow URL:** *[To be added - workflow URL not found in codebase]*  
**Version:** 2.0.0  
**Last Updated:** 2025-01-27

#### Purpose
Validates company records for blank required fields, flags the record, and sends Slack notifications that tag the company owner. Flags include validation status properties for filtering.

#### Key Features
- ✅ **Field Validation:** Checks specified company properties for blank values
- ✅ **Slack Notifications:** Sends detailed notifications, mentioning company owner
- ✅ **Validation Flags:** Sets company properties to track validation status
- ✅ **Comprehensive Logging:** Detailed console logs for debugging
- ✅ **Error Handling:** Graceful error handling with fallback notifications

#### Trigger
- **When:** Company record is created or updated
- **Event Type:** Company property change or creation

#### Fields Validated
- `name` - Company Name
- `industria` - Industria (colppy)
- `hubspot_owner_id` - Company Owner
- `type` - Company Type

#### Fields Updated
- `validation_status` - Set to "failed" or "passed"
- `blank_fields_count` - Number of blank required fields
- `last_validation_date` - Timestamp of last validation

#### Notification Types
1. **`validation_failed`** - One or more required fields are blank
2. **`validation_passed`** - All required fields are filled
3. **`error`** - Validation process failed

#### Slack Channel
- **Channel ID:** `C07STQJV2A0` (Different channel - intentionally separate)
- **Channel Name:** *[To be confirmed]*

#### Business Logic
1. Retrieves company record with all required fields
2. Checks each field in `REQUIRED_FIELDS` array for blank values
3. Counts blank fields
4. Sets validation status properties
5. Sends Slack notification with owner mention (if configured)
6. Includes list of blank fields in notification

#### Owner Mentions
- Uses `SlackUserMentionMap` environment variable to map HubSpot owner IDs to Slack user IDs
- Mentions owner in Slack notification for visibility
- Falls back to owner name if mention mapping not available

---

### 5. Deal Stage Update Workflow

**File:** `tools/scripts/hubspot/workflows/hubspot_deal_stage_update_workflow.js`  
**Workflow URL:** https://app.hubspot.com/workflows/19877595/platform/flow/1611949700/edit/triggers/event  
**Version:** 1.0.0  
**Last Updated:** 2025-11-08

#### Purpose
Actualizar automáticamente cuando detecta un cambio de etapa en el negocio para indicar si es un negocio influenciado por el canal o no. (Automatically updates when it detects a deal stage change to indicate if it's a channel-influenced deal or not.)

#### Key Features
- ✅ **Deal Stage Update:** Updates the deal stage for a deal when the deal stage is changed
- ✅ **Additional Product Detection:** Finds and processes additional product deals immediately
- ✅ **Primary Association Prevention:** Prevents PRIMARY labels on additional product deals

#### Trigger
- **When:** Deal stage is updated
- **Event Type:** Deal property change (specifically `dealstage`)

#### Fields Updated
- Deal associations (removes PRIMARY labels from additional product deals)

#### Notification Types
- *[No Slack notifications configured in this workflow]*

#### Business Logic
1. Validates company has `empresa_adicional = true`
2. Finds all deals in "Negociación Producto Adicional" stage with `empresa_adicional = true`
3. Checks for PRIMARY associations (type ID 5)
4. Removes PRIMARY labels from additional product deals
5. Preserves STANDARD associations

#### Notes
- This workflow appears to be focused on preventing PRIMARY associations on additional product deals
- No Slack notifications are currently configured
- May need to be updated to include notifications for visibility

---

## Notification Channels

### Primary Notification Channel

**Channel ID:** `C07RY5760TZ`  
**Channel Name:** `#intercom_mixpanel_notification`  
**Used By:**
- ✅ First Deal Won Date Calculation
- ✅ Accountant Channel Deal Workflow
- ✅ Additional Product Association Workflow

### Secondary Notification Channel

**Channel ID:** `C07STQJV2A0`  
**Channel Name:** *[To be confirmed]*  
**Used By:**
- ✅ Company Blank Field Validator

---

## Environment Variables

All workflows require the following environment variables configured in HubSpot:

### Required Variables

1. **`ColppyCRMAutomations`**
   - **Type:** HubSpot Private App Token
   - **Purpose:** API authentication for HubSpot CRM operations
   - **Required By:** All workflows
   - **Scopes Needed:** CRM read/write permissions

2. **`SlackWebhookUrl`**
   - **Type:** Slack Incoming Webhook URL
   - **Purpose:** Sends notifications to Slack channels
   - **Required By:** All workflows except Deal Stage Update
   - **Format:** `https://hooks.slack.com/services/...`

### Optional Variables

3. **`SlackUserMentionMap`**
   - **Type:** JSON string mapping HubSpot owner IDs to Slack user IDs
   - **Purpose:** Enables @mentions in Slack notifications
   - **Required By:** Company Blank Field Validator
   - **Format:** `{"hubspot_owner_id": "slack_user_id", ...}`

---

## Quick Reference

### Workflow Summary Table

| Workflow | File | Workflow URL | Notification Channel | Status |
|----------|------|--------------|---------------------|--------|
| First Deal Won Date | `hubspot_first_deal_won_calculations.js` | [Link](https://app.hubspot.com/workflows/19877595/platform/flow/1693911922/edit/actions/1/custom-code) | `C07RY5760TZ` | ✅ Active |
| Accountant Channel | `hubspot_accountant_channel_deal_workflow.js` | [Link](https://app.hubspot.com/workflows/19877595/platform/flow/1611949700/edit/actions/10/custom-code) | `C07RY5760TZ` | ✅ Active |
| Additional Product | `hubspot_additional_product_created.js` | [Link](https://app.hubspot.com/workflows/19877595/platform/flow/1699053467/edit/actions/6/custom-code) | `C07RY5760TZ` | ✅ Active |
| Blank Field Validator | `hubspot_company_blank_field_validator.js` | *[URL needed]* | `C07STQJV2A0` | ✅ Active |
| Deal Stage Update | `hubspot_deal_stage_update_workflow.js` | [Link](https://app.hubspot.com/workflows/19877595/platform/flow/1611949700/edit/triggers/event) | None | ✅ Active |

### Notification Types Summary

| Notification Type | Workflow(s) | Purpose |
|------------------|-------------|---------|
| `success` | All | Field updated successfully |
| `error` | All | Workflow execution failed |
| `warning` | First Deal Won | No PRIMARY deals found |
| `info` | First Deal Won, Accountant Channel | No change needed or informational |
| `accountant_verification` | First Deal Won | Accountant company verification needed |
| `auto_fix_available` | First Deal Won | Auto-fix available for PRIMARY associations |
| `validation_failed` | Blank Field Validator | Required fields are blank |
| `validation_passed` | Blank Field Validator | All required fields filled |

### Key Fields Updated by Workflows

| Field | Workflow | Update Frequency |
|-------|----------|------------------|
| `first_deal_closed_won_date` | First Deal Won | On company/deal changes |
| `company_churn_date` | First Deal Won | On deal stage changes |
| `accountant_channel_involucrado_en_la_venta` | Accountant Channel | On deal owner/collaborator changes |
| `validation_status` | Blank Field Validator | On company property changes |
| Deal Associations | Additional Product | On company creation/update |
| Deal Associations | Deal Stage Update | On deal stage changes |

---

## Recent Updates (Version 1.8.0 - 2025-12-30)

### Enhanced Data Quality Detection and Fixes

**Historical CloseDate Detection:**
- ✅ Script now detects when a deal's `closeDate` is incorrect (after churn date or equals churn date)
- ✅ Automatically fetches historical `closeDate` from property history (when deal was FIRST set to closed won)
- ✅ Uses historical date instead of current incorrect value for accurate `first_deal_closed_won_date` calculation

**Churn Date Fallback Logic:**
- ✅ Enhanced churn date determination with fallback hierarchy:
  1. `fecha_pedido_baja` (primary churn date field)
  2. `fecha_de_desactivacion` (fallback - older field that was used as fecha de baja)
  3. `closeDate` (last resort)
- ✅ Ensures backward compatibility with older deals that only have `fecha_de_desactivacion`

**Enhanced First Deal Date Calculation:**
- ✅ Now includes PRIMARY churned deals (not just closed won deals) when calculating `first_deal_closed_won_date`
- ✅ Detects and corrects incorrect `first_deal_closed_won_date` values (e.g., after churn date)
- ✅ Uses historical `closeDate` when available for accurate date calculation

**Critical Validation:**
- ✅ Clears `churn_date` for companies without PRIMARY deals (not customers, just channel partners/accountants)
- ✅ Ensures data consistency: companies with `churn_date` must have PRIMARY deals

**Logging Improvements:**
- ✅ Fixed misleading log messages that incorrectly reported field clearing
- ✅ Added accurate tracking of field changes during workflow execution
- ✅ Enhanced log messages to clearly indicate when historical dates are used

### Edge Cases Now Handled

1. **Companies with incorrect `first_deal_closed_won_date`** (e.g., after churn date) - automatically recalculated
2. **Deals with incorrect `closeDate`** (after churn date) - uses historical value from property history
3. **Companies with `fecha_pedido_baja` = null** - falls back to `fecha_de_desactivacion`
4. **Companies with `churn_date` but no PRIMARY deals** - clears `churn_date` (not a customer)

### Testing Recommendations

Test with companies that have:
- `churn_date` set but `first_deal_closed_won_date` missing or incorrect
- Deals with `closeDate` after `fecha_de_desactivacion` or `fecha_pedido_baja`
- `fecha_pedido_baja` = null but `fecha_de_desactivacion` set
- `churn_date` set but no PRIMARY deals

---

## Maintenance Notes

### Adding New Workflows

When adding a new custom code workflow:

1. ✅ Add `channel: 'C07RY5760TZ'` to all Slack message objects
2. ✅ Include workflow URL in file header comments
3. ✅ Update this documentation with workflow details
4. ✅ Test notifications in `#intercom_mixpanel_notification` channel
5. ✅ Document all notification types
6. ✅ List all fields updated by the workflow

### Updating Existing Workflows

When updating existing workflows:

1. ✅ Update version number in file header
2. ✅ Update "Last Updated" date
3. ✅ Document changes in this file
4. ✅ Test all notification types
5. ✅ Verify Slack channel configuration

### Troubleshooting

**Notifications not appearing in Slack:**
- Check `SlackWebhookUrl` environment variable is set
- Verify webhook URL is valid and active
- Check Slack channel ID is correct (`C07RY5760TZ`)
- Review HubSpot workflow execution logs

**Workflow not triggering:**
- Verify workflow is active in HubSpot
- Check trigger conditions are met
- Review workflow enrollment criteria
- Check HubSpot API token permissions

**Field updates not working:**
- Verify field names are correct (case-sensitive)
- Check field permissions in HubSpot
- Review API token scopes
- Check for field-level restrictions

---

## Contact Information

**For Questions or Updates:**
- **Documentation Maintainer:** CEO Assistant
- **Last Review Date:** 2025-01-27
- **Next Review:** Quarterly or when workflows are updated

---

**End of Document**

