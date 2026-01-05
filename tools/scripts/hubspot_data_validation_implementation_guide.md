# HubSpot Data Validation Implementation Guide

## Overview
This guide explains how to implement data validation rules in HubSpot to prevent the data quality issues identified in the analysis.

## Issues to Fix

1. **Churn Date must be >= First Deal Date**
2. **Companies with deals must have First Deal Date**

---

## Solution 1: HubSpot Workflows (Recommended)

### For Validation: Churn Date >= First Deal Date

**Approach: Use a Company Workflow with Conditional Logic**

1. **Create a Company Workflow:**
   - Go to **Automation > Workflows**
   - Create a new workflow for Companies
   - Name: "Validate Churn Date vs First Deal Date"

2. **Enrollment Trigger:**
   - **When:** Company property "Fecha de baja de la compañía" is updated
   - **OR:** Company property "First deal closed won date" is updated

3. **Workflow Actions:**
   
   **Step 1: Check if both dates exist**
   - Use conditional logic (IF/THEN)
   - **IF:** "Fecha de baja de la compañía" has a value
   - **AND:** "First deal closed won date" has a value
   
   **Step 2: Compare dates**
   - Use a custom code action (if available) or:
   - Create a calculated property that compares dates
   - **IF:** Churn Date < First Deal Date
   - **THEN:** Send notification/alert
   - **THEN:** Clear the churn date (optional - to prevent bad data)

4. **Alternative: Use Custom Code Action**
   - In Operations Hub, you can use custom code actions
   - Write JavaScript to compare dates:
   ```javascript
   const churnDate = new Date(company.properties.fecha_de_baja_de_la_compania);
   const firstDealDate = new Date(company.properties.first_deal_closed_won_date);
   
   if (churnDate < firstDealDate) {
     // Clear churn date or set error flag
     return {
       properties: {
         fecha_de_baja_de_la_compania: null,
         data_validation_error: "Churn date cannot be before first deal date"
       }
     };
   }
   ```

### For Validation: Companies with Deals Must Have First Deal Date

**Approach: Use a Deal Workflow**

1. **Create a Deal Workflow:**
   - Go to **Automation > Workflows**
   - Create a new workflow for Deals
   - Name: "Ensure First Deal Date on Company"

2. **Enrollment Trigger:**
   - **When:** Deal is created
   - **AND:** Deal is associated with a company

3. **Workflow Actions:**
   
   **Step 1: Check if company has First Deal Date**
   - Use conditional logic
   - **IF:** Associated company's "First deal closed won date" is empty
   - **THEN:** Set company property "First deal closed won date" = Deal's "Close date"
   - **THEN:** Send notification (optional)

4. **Alternative: Use Deal-to-Company Association Workflow**
   - Trigger: When deal is associated with company
   - Action: Update company's "First deal closed won date" if empty

---

## Solution 2: HubSpot Property Validations API

### Using the Property Validations API

**Reference:** [HubSpot Property Validations API](https://developers.hubspot.com/docs/api-reference/crm-property-validations-v3/guide)

### For Custom Properties:

You can set validation rules for **custom properties** using the API:

```bash
PUT /crm/v3/property-validations/{objectTypeId}/{propertyName}/rule-type/{ruleType}
```

**Example: Validate Churn Date >= First Deal Date**

Since this requires comparing two properties, you'll need to:
1. Create a custom calculated property that compares dates
2. Set validation on that calculated property
3. Use workflows to enforce the rule

### Limitations:

- **Default properties** (like "First deal closed won date") cannot have validation rules set via the API
- Property validations work on single properties, not cross-property comparisons
- For complex validations, use workflows instead

---

## Solution 3: Operations Hub Custom Code

### Using Custom Code Actions in Workflows

If you have **Operations Hub**, you can use custom code actions:

1. **Create Custom Code Action:**
   - Go to **Automation > Workflows**
   - Add a "Custom code" action
   - Write validation logic

2. **Example Code for Churn Date Validation:**

```javascript
exports.main = async (event, callback) => {
  const company = event.inputFields;
  
  const churnDate = company.fecha_de_baja_de_la_compania;
  const firstDealDate = company.first_deal_closed_won_date;
  
  if (churnDate && firstDealDate) {
    const churn = new Date(churnDate);
    const firstDeal = new Date(firstDealDate);
    
    if (churn < firstDeal) {
      // Clear invalid churn date
      callback({
        outputFields: {
          fecha_de_baja_de_la_compania: null,
          data_validation_error: "Churn date cannot be before first deal date"
        }
      });
    }
  }
  
  callback({ outputFields: {} });
};
```

---

## Solution 4: Data Quality Monitoring (Operations Hub)

### Using Data Quality Command Center

1. **Set Up Data Quality Rules:**
   - Go to **Settings > Data Quality**
   - Create custom data quality rules
   - Monitor for companies with:
     - Deals but no First Deal Date
     - Churn Date < First Deal Date

2. **Automated Cleanup:**
   - Use workflows triggered by data quality issues
   - Automatically fix or flag problematic records

---

## Recommended Implementation Steps

### Phase 1: Immediate Fixes (Manual)
1. Export the 136 companies with issues
2. Manually fix the 28 CRITICAL issues
3. Review the 107 HIGH priority issues

### Phase 2: Prevention (Automation)
1. **Create Workflow 1:** "Validate Churn Date"
   - Trigger: When churn date is set
   - Action: Clear if < First Deal Date
   - Notification: Alert data team

2. **Create Workflow 2:** "Set First Deal Date"
   - Trigger: When deal is created/associated
   - Action: Set First Deal Date on company if empty

3. **Create Workflow 3:** "Data Quality Check"
   - Trigger: Daily/Scheduled
   - Action: Find companies with issues
   - Action: Create tasks for data team

### Phase 3: Monitoring
1. Set up Data Quality Command Center rules
2. Create reports for data quality metrics
3. Schedule regular data audits

---

## HubSpot Documentation References

1. **Property Validations:** 
   - https://developers.hubspot.com/docs/api-reference/crm-property-validations-v3/guide
   - https://knowledge.hubspot.com/properties/set-validation-rules-for-properties

2. **Workflows:**
   - https://knowledge.hubspot.com/workflows/create-workflows
   - https://knowledge.hubspot.com/workflows/use-conditional-logic-in-workflows

3. **Custom Code Actions:**
   - https://developers.hubspot.com/docs/api-reference/crm-extensions/custom-code-actions

4. **Data Quality:**
   - https://knowledge.hubspot.com/data-quality/use-data-quality-command-center

---

## Notes

- **Default properties** cannot have validation rules set directly
- **Cross-property validation** requires workflows or custom code
- **Operations Hub** provides more advanced validation capabilities
- Consider using **calculated properties** for complex validations
