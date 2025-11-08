# HubSpot Blank Field Validator - Quick Start Guide

## 🎯 What This Does

Automatically validates company records for blank required fields and sends Slack notifications when data is missing.

## ⚡ Quick Setup (5 Minutes)

### 1. Create Custom Properties

Go to **Settings** → **Properties** → **Company** and create:

| Property Label | Internal Name | Field Type |
|---------------|---------------|-----------|
| Data Validation Status | `data_validation_status` | Single-line text |
| Data Validation Missing Fields | `data_validation_missing_fields` | Multi-line text |

### 2. Configure Fields to Validate

Edit the code at line 33-42 to specify which fields to check:

```javascript
const REQUIRED_FIELDS = [
  { name: 'name', label: 'Company Name' },
  { name: 'industria_colppy', label: 'Industria (colppy)' },
  { name: 'phone', label: 'Phone Number' },
  // Add your required fields here
];
```

### 3. Create Workflow

1. **Automation** → **Workflows** → **Create workflow**
2. **Company-based** workflow
3. Trigger: **Company is created or updated**
4. Add action: **Custom code** (Node.js 18.x)
5. Add secrets:
   - `ColppyCRMAutomations` (HubSpot API token)
   - `SlackWebhookUrl` (Slack webhook URL)
6. Copy/paste code from: `/Users/virulana/openai-cookbook/tools/scripts/hubspot_company_blank_field_validator.js`
7. **Save** and **Activate**

### 4. Test

1. Edit a company record
2. Leave some required fields blank
3. Save the record
4. Check:
   - ✅ Slack notification received
   - ✅ Company properties updated
   - ✅ Workflow logs show validation details

## 📊 What You'll Get

### Slack Notifications

```
⚠️ Company Record Has Blank Required Fields

🏢 Company: [Link to Company]
👤 Owner: [Owner Name]
❌ Blank Fields:
   • Phone Number (phone)
   • City (city)
📊 3 of 5 required fields are blank
```

### Company Properties

- **data_validation_status**: `incomplete` or `complete`
- **data_validation_missing_fields**: List of blank fields

### Filter Companies with Issues

Create a saved view:
- Filter: `Data Validation Status` = `incomplete`
- Shows all companies with missing required fields

## 🔧 Common Customizations

### Add More Fields

```javascript
{ name: 'website', label: 'Website' },
{ name: 'hubspot_owner_id', label: 'Company Owner' },
{ name: 'numberofemployees', label: 'Number of Employees' },
```

### Disable Success Notifications

Comment out lines 278-289 (the `else` block that sends success notifications)

### Custom Validation Logic

Edit the `isBlank` function at line 56 to add custom rules

## 📚 Full Documentation

See [HUBSPOT_BLANK_FIELD_VALIDATOR_SETUP.md](HUBSPOT_BLANK_FIELD_VALIDATOR_SETUP.md) for complete documentation.

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| No Slack notifications | Check `SlackWebhookUrl` secret configuration |
| Properties not updating | Verify custom properties exist with correct internal names |
| Workflow not triggering | Check enrollment criteria and workflow activation status |
| Wrong fields validated | Verify property internal names in `REQUIRED_FIELDS` |

## ✅ Pre-Deployment Checklist

- [ ] Created `data_validation_status` property
- [ ] Created `data_validation_missing_fields` property
- [ ] Configured `REQUIRED_FIELDS` array
- [ ] Added `ColppyCRMAutomations` secret
- [ ] Added `SlackWebhookUrl` secret
- [ ] Tested with sample company
- [ ] Verified Slack notifications work
- [ ] Activated workflow

---

**File Location**: `/Users/virulana/openai-cookbook/tools/scripts/hubspot_company_blank_field_validator.js`  
**Version**: 1.0.0  
**Last Updated**: 2025-11-08

