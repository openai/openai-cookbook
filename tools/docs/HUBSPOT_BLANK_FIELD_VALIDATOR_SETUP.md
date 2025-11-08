# HubSpot Company Blank Field Validator - Setup Guide

## 📋 Overview

This custom code workflow validates company records for blank required fields and sends Slack notifications when validation fails. It automatically flags records with validation status properties for easy filtering and follow-up.

## 🎯 Features

- ✅ **Automated Validation**: Checks specified company properties for blank values
- ✅ **Slack Notifications**: Sends detailed alerts for records with missing data
- ✅ **Validation Flags**: Sets company properties (`data_validation_status`, `data_validation_missing_fields`)
- ✅ **Comprehensive Logging**: Detailed console logs for debugging
- ✅ **Error Handling**: Graceful error handling with fallback notifications

## 📍 File Location

**Source Code**: `/Users/virulana/openai-cookbook/tools/scripts/hubspot_company_blank_field_validator.js`

## 🚀 Setup Instructions

### Step 1: Create Required Custom Properties

Before deploying the workflow, create these custom properties in HubSpot:

1. Go to **Settings** → **Properties** → **Company properties**
2. Create the following properties:

#### Property 1: Data Validation Status
- **Label**: Data Validation Status
- **Internal name**: `data_validation_status`
- **Field type**: Single-line text
- **Description**: Tracks whether company record has all required fields filled

#### Property 2: Data Validation Missing Fields
- **Label**: Data Validation Missing Fields
- **Internal name**: `data_validation_missing_fields`
- **Field type**: Multi-line text
- **Description**: Lists which required fields are blank (semicolon-separated)

### Step 2: Configure Required Fields

Edit the `REQUIRED_FIELDS` array in the custom code (lines 33-42):

```javascript
const REQUIRED_FIELDS = [
  { name: 'name', label: 'Company Name' },
  { name: 'industria_colppy', label: 'Industria (colppy)' },
  { name: 'domain', label: 'Company Domain' },
  { name: 'phone', label: 'Phone Number' },
  { name: 'city', label: 'City' },
  // Add or remove fields as needed
];
```

**To add fields:**
- Add new objects to the array with `name` (internal property name) and `label` (display name)
- Example: `{ name: 'website', label: 'Website' }`

**To remove fields:**
- Delete or comment out the field objects you don't want to validate

### Step 3: Set Up Environment Variables

The workflow requires these secrets in HubSpot:

1. **ColppyCRMAutomations**: HubSpot API token
   - Go to **Settings** → **Integrations** → **Private Apps**
   - Use existing "ColppyCRMAutomations" app or create new one
   - Required scopes: `crm.objects.companies.read`, `crm.objects.companies.write`

2. **SlackWebhookUrl**: Slack webhook URL
   - Go to Slack → **Apps** → **Incoming Webhooks**
   - Create new webhook or use existing one
   - Copy the webhook URL

### Step 4: Create the Workflow

1. Go to **Automation** → **Workflows**
2. Click **Create workflow** → **From scratch**
3. Choose **Company-based** workflow
4. Set enrollment trigger:
   - **Trigger**: Company is created or updated
   - **Filters** (optional): 
     - Lifecycle stage is any of: Lead, Customer, etc.
     - Owner is known

5. Add **Custom code** action:
   - Click **+** → **Custom code**
   - Select **Node.js 18.x**
   - **Manage secrets**: Add `ColppyCRMAutomations` and `SlackWebhookUrl`
   - Copy the entire code from `hubspot_company_blank_field_validator.js`
   - Paste into the code editor
   - **Code properties**: No properties needed (uses `event.object.objectId`)

6. **Save** and **Review** the workflow
7. **Activate** when ready

### Step 5: Test the Workflow

#### Test with a Company Missing Required Fields

1. Create or edit a test company
2. Leave some required fields blank (e.g., phone, city)
3. Save the company
4. Check workflow execution logs:
   - Go to **Automation** → **Workflows** → [Your workflow]
   - Click **Actions** tab
   - View recent executions
5. Verify:
   - ✅ Console logs show validation failure
   - ✅ Company properties updated (`data_validation_status` = "incomplete")
   - ✅ Slack notification received with list of blank fields

#### Test with Complete Company Record

1. Edit the same company
2. Fill in all required fields
3. Save the company
4. Verify:
   - ✅ Console logs show validation passed
   - ✅ Company properties updated (`data_validation_status` = "complete")
   - ✅ Slack notification received (optional)

## 📊 Validation Status Properties

### data_validation_status

| Value | Meaning |
|-------|---------|
| `complete` | All required fields are filled |
| `incomplete` | One or more required fields are blank |

### data_validation_missing_fields

Contains semicolon-separated list of blank field labels:
- Example: `"Phone Number; City; Company Domain"`
- Empty string when all fields are filled

## 📢 Slack Notifications

### Validation Failed Notification

```
⚠️ Company Record Has Blank Required Fields

🏢 Company: [Company Name Link]
👤 Company Owner: [Owner Name]
❌ Blank Fields:
   • Phone Number (phone)
   • City (city)
   • Company Domain (domain)
📊 Total: 3 of 5 required fields are blank
```

### Validation Passed Notification (Optional)

```
✅ Company Record Validation Passed

🏢 Company: [Company Name Link]
👤 Company Owner: [Owner Name]
✅ Status: All required fields are filled
```

## 🔍 Filtering Companies with Validation Issues

Create a saved view in HubSpot:

1. Go to **Contacts** → **Companies**
2. Click **+ Add view**
3. Add filters:
   - `Data Validation Status` = `incomplete`
4. Save view as "Companies - Missing Required Fields"

## ⚙️ Configuration Options

### Disable Success Notifications

If you only want to receive notifications for validation failures:

Edit line 277 in the code, change:

```javascript
if (blankFields.length > 0) {
  // Send notification for validation failure
  slackNotification = {
    // ... notification config
  };
} else {
  // Comment out or remove this entire else block
  // to disable success notifications
}
```

### Custom Validation Rules

For more complex validation (e.g., conditional requirements):

Edit the `isBlank` function (lines 56-64):

```javascript
function isBlank(value) {
  if (value === null || value === undefined) {
    return true;
  }
  if (typeof value === 'string' && value.trim() === '') {
    return true;
  }
  // Add custom validation logic here
  // Example: Minimum length requirement
  // if (typeof value === 'string' && value.length < 3) {
  //   return true;
  // }
  return false;
}
```

## 🛠 Troubleshooting

### Workflow Not Triggering

**Problem**: Workflow doesn't run when company is updated

**Solutions**:
1. Check enrollment criteria - ensure company meets trigger conditions
2. Verify workflow is activated
3. Check if company is already enrolled (workflows may skip re-enrollment)

### No Slack Notifications

**Problem**: Validation runs but no Slack messages received

**Solutions**:
1. Verify `SlackWebhookUrl` secret is configured correctly
2. Check webhook URL is valid and active in Slack
3. Review workflow logs for Slack API errors
4. Test webhook URL with curl:
   ```bash
   curl -X POST -H 'Content-Type: application/json' \
   --data '{"text":"Test message"}' \
   YOUR_WEBHOOK_URL
   ```

### Properties Not Updated

**Problem**: Validation runs but properties don't update

**Solutions**:
1. Verify custom properties exist with correct internal names:
   - `data_validation_status`
   - `data_validation_missing_fields`
2. Check HubSpot API token has write permissions
3. Review workflow logs for API errors

### Incorrect Field Validation

**Problem**: Fields showing as blank when they have values

**Solutions**:
1. Verify property internal names in `REQUIRED_FIELDS` match HubSpot property names exactly
2. Check for typos in property names
3. Use workflow logs to see actual property values
4. Some properties may have different data types (e.g., checkboxes, dropdowns)

## 📈 Monitoring & Reporting

### Create Dashboard Widget

1. Go to **Reports** → **Dashboards**
2. Add widget: "Companies by Data Validation Status"
   - Type: Donut chart
   - Object: Companies
   - Breakdown by: Data Validation Status

### Weekly Report

Create a saved filter for companies with incomplete validation:
1. **Contacts** → **Companies** → **All companies**
2. Filter: `Data Validation Status` = `incomplete`
3. Filter: `Last Modified Date` = `Last 7 days`
4. Export to CSV for weekly review

## 🔄 Maintenance

### Adding New Required Fields

1. Add field to `REQUIRED_FIELDS` array
2. Test with sample company
3. Deploy updated code to workflow
4. No need to update existing company records (will validate on next update)

### Removing Required Fields

1. Remove field from `REQUIRED_FIELDS` array
2. Deploy updated code
3. Consider clearing validation flags on existing companies:
   - Create a workflow to reset `data_validation_status` to blank
   - Or manually clear for affected companies

## 📚 Related Documentation

- [HubSpot Custom Code Testing & Validation](README_HUBSPOT_CUSTOM_CODE_TESTING.md)
- [HubSpot Configuration Guide](README_HUBSPOT_CONFIGURATION.md)
- [HubSpot Custom Code Actions Documentation](https://developers.hubspot.com/docs/api-reference/automation-actions-v4-v4/custom-code-actions)

## 🆘 Support

If you encounter issues:
1. Check workflow execution logs for detailed error messages
2. Review console logs for validation details
3. Test with a single company record first
4. Verify all required properties and secrets are configured

---

**Last Updated**: 2025-11-08  
**Version**: 1.0.0

