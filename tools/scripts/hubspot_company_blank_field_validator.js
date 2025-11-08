// =============================================================================
// HubSpot Custom Code - Company Blank Field Validator with Slack Notifications
// =============================================================================
// VERSION: 1.0.0
// CREATED: 2025-11-08
// FILE: hubspot_company_blank_field_validator.js
//
// PURPOSE: 
// Validates company records for blank required fields and sends Slack notifications
// when fields are found to be blank. Flags records with validation status.
//
// FEATURES:
// ✅ FIELD VALIDATION: Checks specified company properties for blank values
// ✅ SLACK NOTIFICATIONS: Sends detailed notifications for records with blank fields
// ✅ VALIDATION FLAGS: Sets company properties to track validation status
// ✅ COMPREHENSIVE LOGGING: Detailed console logs for debugging
// ✅ ERROR HANDLING: Graceful error handling with fallback notifications
//
// ENVIRONMENT VARIABLES REQUIRED:
// - ColppyCRMAutomations: HubSpot API token
// - SlackWebhookUrl: Slack webhook URL for notifications
//
// CONFIGURATION:
// Edit the REQUIRED_FIELDS array below to specify which fields to validate
//
// =============================================================================
// ⚡ READY TO COPY/PASTE - Select all (Ctrl/Cmd+A) and copy to HubSpot
// =============================================================================

const hubspot = require('@hubspot/api-client');

// =============================================================================
// CONFIGURATION: Define fields to validate
// =============================================================================
// Add or remove fields from this array based on your requirements
// Format: { name: 'internal_property_name', label: 'Display Name' }
// =============================================================================
const REQUIRED_FIELDS = [
  { name: 'name', label: 'Company Name' },
  { name: 'industria_colppy', label: 'Industria (colppy)' },
  { name: 'domain', label: 'Company Domain' },
  { name: 'phone', label: 'Phone Number' },
  { name: 'city', label: 'City' },
  // Add more fields as needed:
  // { name: 'hubspot_owner_id', label: 'Company Owner' },
  // { name: 'numberofemployees', label: 'Number of Employees' },
];

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  // Helper function to check if a value is blank
  function isBlank(value) {
    if (value === null || value === undefined) {
      return true;
    }
    if (typeof value === 'string' && value.trim() === '') {
      return true;
    }
    return false;
  }

  // Helper function to send Slack notifications
  async function sendSlackNotification(notification) {
    const slackWebhookUrl = process.env.SlackWebhookUrl;
    
    if (!slackWebhookUrl) {
      console.log('⚠️  Slack webhook URL not configured - skipping notification');
      return;
    }

    try {
      let slackMessage;

      if (notification.type === 'validation_failed') {
        // Notification for records with blank fields
        const fieldList = notification.details.blankFields
          .map(f => `• ${f.label} (${f.name})`)
          .join('\n');

        slackMessage = {
          text: notification.title,
          attachments: [
            {
              color: '#FF0000', // Red for validation errors
              fields: [
                {
                  title: '🏢 Company',
                  value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
                  short: true
                },
                {
                  title: '👤 Company Owner',
                  value: notification.details.companyOwner || 'No Owner',
                  short: true
                },
                {
                  title: '❌ Blank Fields',
                  value: fieldList,
                  short: false
                },
                {
                  title: '📊 Total Blank Fields',
                  value: `${notification.details.blankFields.length} of ${notification.details.totalFields} required fields are blank`,
                  short: false
                }
              ],
              footer: 'HubSpot Blank Field Validator',
              footer_icon: 'https://cdn2.hubspot.net/hubfs/53/tools/emailsignature/hubspot-logo.png',
              ts: Math.floor(Date.now() / 1000)
            }
          ]
        };
      } else if (notification.type === 'validation_passed') {
        // Notification for records that passed validation
        slackMessage = {
          text: notification.title,
          attachments: [
            {
              color: '#36a64f', // Green for success
              fields: [
                {
                  title: '🏢 Company',
                  value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
                  short: true
                },
                {
                  title: '👤 Company Owner',
                  value: notification.details.companyOwner || 'No Owner',
                  short: true
                },
                {
                  title: '✅ Status',
                  value: 'All required fields are filled',
                  short: false
                }
              ],
              footer: 'HubSpot Blank Field Validator',
              footer_icon: 'https://cdn2.hubspot.net/hubfs/53/tools/emailsignature/hubspot-logo.png',
              ts: Math.floor(Date.now() / 1000)
            }
          ]
        };
      } else if (notification.type === 'error') {
        // Error notification
        slackMessage = {
          text: notification.title,
          attachments: [
            {
              color: '#FF0000',
              fields: [
                {
                  title: '🏢 Company ID',
                  value: notification.details.companyId || 'Unknown',
                  short: true
                },
                {
                  title: '❌ Error',
                  value: notification.details.errorMessage || 'Unknown error',
                  short: false
                }
              ],
              footer: 'HubSpot Blank Field Validator',
              footer_icon: 'https://cdn2.hubspot.net/hubfs/53/tools/emailsignature/hubspot-logo.png',
              ts: Math.floor(Date.now() / 1000)
            }
          ]
        };
      }

      const response = await fetch(slackWebhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(slackMessage)
      });

      if (response.ok) {
        console.log(`✅ Slack notification sent successfully`);
      } else {
        console.error(`❌ Slack notification failed: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      console.error(`❌ Slack notification error:`, error.message);
    }
  }

  try {
    const companyId = String(event.object.objectId);

    console.log('='.repeat(80));
    console.log('🔍 COMPANY BLANK FIELD VALIDATION STARTED');
    console.log('='.repeat(80));
    console.log('📋 WORKFLOW INFO:');
    console.log(`   Company ID: ${companyId}`);
    console.log(`   Timestamp: ${new Date().toISOString()}`);
    console.log(`   Event Type: ${event.eventType || 'unknown'}`);
    console.log(`   Fields to validate: ${REQUIRED_FIELDS.length}`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 1: RETRIEVE COMPANY DATA
    // ========================================================================
    console.log('📊 STEP 1: RETRIEVING COMPANY DATA');
    console.log('-'.repeat(50));

    // Get list of properties to retrieve
    const propertiesToRetrieve = REQUIRED_FIELDS.map(f => f.name);
    // Add additional properties for reporting
    propertiesToRetrieve.push('name', 'hubspot_owner_id', 'data_validation_status', 'data_validation_missing_fields');

    const company = await client.crm.companies.basicApi.getById(companyId, propertiesToRetrieve);
    const properties = company.properties || {};

    const companyName = properties.name || 'Unknown Company';
    const companyOwner = properties.hubspot_owner_id || 'No Owner';

    console.log(`✅ Company retrieved: ${companyName} (ID: ${companyId})`);
    console.log(`   Owner ID: ${companyOwner}`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 2: VALIDATE REQUIRED FIELDS
    // ========================================================================
    console.log('✅ STEP 2: VALIDATING REQUIRED FIELDS');
    console.log('-'.repeat(50));

    const blankFields = [];
    const filledFields = [];

    for (const field of REQUIRED_FIELDS) {
      const value = properties[field.name];
      const blank = isBlank(value);

      if (blank) {
        blankFields.push(field);
        console.log(`❌ BLANK: ${field.label} (${field.name})`);
      } else {
        filledFields.push(field);
        console.log(`✅ FILLED: ${field.label} (${field.name}) = "${value}"`);
      }
    }

    console.log('-'.repeat(50));
    console.log(`📊 VALIDATION SUMMARY:`);
    console.log(`   Total fields checked: ${REQUIRED_FIELDS.length}`);
    console.log(`   Filled fields: ${filledFields.length}`);
    console.log(`   Blank fields: ${blankFields.length}`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 3: UPDATE VALIDATION STATUS PROPERTIES
    // ========================================================================
    console.log('📝 STEP 3: UPDATING VALIDATION STATUS');
    console.log('-'.repeat(50));

    const updateData = {
      properties: {}
    };

    if (blankFields.length > 0) {
      // Validation failed - update status and list of missing fields
      updateData.properties.data_validation_status = 'incomplete';
      updateData.properties.data_validation_missing_fields = blankFields
        .map(f => f.label)
        .join('; ');

      console.log(`⚠️  Setting validation status to: incomplete`);
      console.log(`⚠️  Missing fields: ${updateData.properties.data_validation_missing_fields}`);
    } else {
      // Validation passed - clear status flags
      updateData.properties.data_validation_status = 'complete';
      updateData.properties.data_validation_missing_fields = '';

      console.log(`✅ Setting validation status to: complete`);
      console.log(`✅ Clearing missing fields list`);
    }

    // Update the company record
    await client.crm.companies.basicApi.update(companyId, updateData);
    console.log(`✅ Company validation status updated successfully`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 4: SEND SLACK NOTIFICATION
    // ========================================================================
    console.log('📢 STEP 4: SENDING SLACK NOTIFICATION');
    console.log('-'.repeat(50));

    let slackNotification;

    if (blankFields.length > 0) {
      // Send notification for validation failure
      slackNotification = {
        type: 'validation_failed',
        title: '⚠️ Company Record Has Blank Required Fields',
        details: {
          companyId: companyId,
          companyName: companyName,
          companyOwner: companyOwner,
          blankFields: blankFields,
          totalFields: REQUIRED_FIELDS.length
        }
      };

      console.log(`📤 Sending validation failure notification for ${blankFields.length} blank fields`);
    } else {
      // Send notification for validation success (optional - can be disabled)
      slackNotification = {
        type: 'validation_passed',
        title: '✅ Company Record Validation Passed',
        details: {
          companyId: companyId,
          companyName: companyName,
          companyOwner: companyOwner
        }
      };

      console.log(`📤 Sending validation success notification`);
    }

    try {
      await sendSlackNotification(slackNotification);
      console.log(`✅ Slack notification sent successfully`);
    } catch (slackError) {
      console.error(`❌ Slack notification failed:`, slackError.message);
      // Don't fail the entire workflow if Slack fails
    }

    console.log('='.repeat(80));

    // ========================================================================
    // FINAL WORKFLOW EXECUTION SUMMARY
    // ========================================================================
    console.log('📊 FINAL WORKFLOW EXECUTION SUMMARY');
    console.log('-'.repeat(50));
    console.log(`Company: ${companyName} (ID: ${companyId})`);
    console.log(`Validation status: ${blankFields.length > 0 ? 'FAILED' : 'PASSED'}`);
    console.log(`Blank fields found: ${blankFields.length}`);
    console.log(`Notification sent: ${slackNotification ? 'YES' : 'NO'}`);
    console.log('='.repeat(80));
    console.log('🎉 COMPANY BLANK FIELD VALIDATION COMPLETED SUCCESSFULLY');
    console.log('='.repeat(80));

    // Call callback to indicate success
    callback(null, 'Success');

  } catch (err) {
    console.error('=== ERROR OCCURRED ===');
    console.error('Error type:', err.constructor.name);
    console.error('Error message:', err.message);
    console.error('Error stack:', err.stack);

    // Send error notification to Slack
    try {
      await sendSlackNotification({
        type: 'error',
        title: '❌ Validation Workflow Error',
        details: {
          companyId: event.object.objectId,
          errorType: err.constructor.name,
          errorMessage: err.message
        }
      });
    } catch (slackError) {
      console.error(`❌ Slack error notification failed:`, slackError.message);
    }

    if (err.response) {
      console.error('HTTP Status:', err.response.status);
      console.error('HTTP Status Text:', err.response.statusText);
      console.error('Response body:', JSON.stringify(err.response.body, null, 2));
    }

    console.error('Full error object:', JSON.stringify(err, null, 2));
    console.error('=== ERROR LOGGING COMPLETE ===');

    // Call callback with error
    callback(err);
  }
};

