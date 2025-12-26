// =============================================================================
// HubSpot Custom Code - Company Blank Field Validator with Slack Notifications
// =============================================================================
// VERSION: 2.0.0
// LAST UPDATED: 2025-01-27
// FILE: hubspot_company_blank_field_validator.js
//
// PURPOSE: 
// Validates company records for blank required fields, flags the record, and
// sends Slack notifications that tag the company owner. Flags include validation
// status properties for filtering.
//
// FEATURES:
// ✅ FIELD VALIDATION: Checks specified company properties for blank values
// ✅ SLACK NOTIFICATIONS: Sends detailed notifications, mentioning company owner
// ✅ VALIDATION FLAGS: Sets company properties to track validation status
// ✅ COMPREHENSIVE LOGGING: Detailed console logs for debugging
// ✅ ERROR HANDLING: Graceful error handling with fallback notifications
//
// ENVIRONMENT VARIABLES REQUIRED:
// - ColppyCRMAutomations: HubSpot API token
// - SlackWebhookUrl: Slack webhook URL for notifications
// - SlackUserMentionMap: JSON map of HubSpot owner IDs to Slack user IDs/mentions
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
  { name: 'industria', label: 'Industria (colppy)' },
  { name: 'hubspot_owner_id', label: 'Company Owner' },
  { name: 'type', label: 'Company Type' }
];

// Initialize Slack user mention map from environment variable
let slackMentionMap = {};
const slackMentionMapRaw = process.env.SlackUserMentionMap;
if (slackMentionMapRaw) {
  try {
    slackMentionMap = JSON.parse(slackMentionMapRaw);
    console.log(`✅ Slack mention map loaded with ${Object.keys(slackMentionMap).length} entries`);
  } catch (error) {
    console.log(`❌ Failed to parse SlackUserMentionMap env var: ${error.message}`);
    slackMentionMap = {};
  }
} else {
  console.log('⚠️  SlackUserMentionMap env var not set - Slack mentions will use fallback text');
}

function getSlackMentionForUser(userId) {
  if (!userId) {
    return null;
  }

  // Convert to string for consistent lookup (HubSpot might return number or string)
  const userIdStr = String(userId);
  
  // Try both string and number keys (in case JSON parsing created number keys)
  const mapped = slackMentionMap[userIdStr] || slackMentionMap[userId];
  
  if (!mapped) {
    console.log(`⚠️  No Slack mention mapping for HubSpot user ${userId} (tried as string "${userIdStr}" and number ${userId})`);
    console.log(`📋 Available keys in map: ${Object.keys(slackMentionMap).join(', ')}`);
    return null;
  }

  // Allow either direct <@U123> strings or plain IDs that we wrap
  if (mapped.startsWith('<@') && mapped.endsWith('>')) {
    return mapped;
  }

  return `<@${mapped}>`;
}

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  // Helper function to resolve owner names with detailed logging
  async function getOwnerName(ownerId) {
    console.log(`🔍 OWNER RESOLUTION START - Owner ID: ${ownerId}`);
    
    if (!ownerId) {
      console.log(`❌ OWNER RESOLUTION: No owner ID provided`);
      return 'No Owner';
    }
    
    try {
      console.log(`📡 OWNER API CALL: Fetching owner details for ID ${ownerId}`);
      console.log(`🔑 API Key Status: ${process.env.ColppyCRMAutomations ? 'Present' : 'Missing'}`);
      
      const response = await fetch(`https://api.hubspot.com/crm/v3/owners/${ownerId}`, {
        headers: {
          'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
          'Content-Type': 'application/json'
        }
      });
      
      console.log(`📊 OWNER API RESPONSE: Status ${response.status} for ID ${ownerId}`);
      
      if (response.ok) {
        const data = await response.json();
        console.log(`✅ OWNER API SUCCESS: Raw data for ID ${ownerId}:`, JSON.stringify(data, null, 2));
        
        const firstName = data.firstName || '';
        const lastName = data.lastName || '';
        const fullName = `${firstName} ${lastName}`.trim();
        const isActive = data.archived === false;
        
        console.log(`👤 OWNER DETAILS: ID ${ownerId}`);
        console.log(`   - First Name: "${firstName}"`);
        console.log(`   - Last Name: "${lastName}"`);
        console.log(`   - Full Name: "${fullName}"`);
        console.log(`   - Active Status: ${isActive ? 'ACTIVE' : 'INACTIVE'}`);
        console.log(`   - Archived: ${data.archived}`);
        
        const result = fullName || `Owner ID: ${ownerId}`;
        console.log(`✅ OWNER RESOLUTION SUCCESS: "${result}" for ID ${ownerId}`);
        return result;
        
      } else if (response.status === 404) {
        console.log(`❌ OWNER NOT FOUND: ID ${ownerId} does not exist (404)`);
        return `Owner ID: ${ownerId}`;
      } else {
        console.log(`⚠️ OWNER API ERROR: Status ${response.status} for ID ${ownerId}`);
        const errorText = await response.text();
        console.log(`📄 Error Response Body: ${errorText}`);
        return `Owner ID: ${ownerId}`;
      }
    } catch (error) {
      console.log(`💥 OWNER API EXCEPTION: ID ${ownerId} - ${error.message}`);
      console.log(`🔍 Error Stack: ${error.stack}`);
      return `Owner ID: ${ownerId}`;
    }
  }

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

  // Helper function to format user display with name and/or Slack mention
  function formatUserDisplay(name, mention, userId) {
    // CRITICAL: Always prioritize Slack mention if available - this ensures notifications work
    if (mention) {
      // Always include the mention - it's what triggers the Slack notification
      // If we have a valid resolved name, combine name + mention
      if (name && !name.startsWith('Owner ID:') && name !== 'No Owner' && name !== 'Unknown user' && name !== `Owner ID: ${userId}` && !name.startsWith('User ID:')) {
        return `${name} ${mention}`;
      }
      // If name resolution failed but we have a mention, use ONLY the mention (this will notify the user)
      return mention;
    }
    
    // No mention configured - use name if available
    if (name && !name.startsWith('Owner ID:') && name !== 'No Owner' && name !== 'Unknown user' && !name.startsWith('User ID:')) {
      return name;
    }
    
    // Both name resolution and mention failed - show helpful fallback
    if (name && (name.startsWith('Owner ID:') || name.startsWith('User ID:'))) {
      // Name resolution failed - suggest adding to SlackUserMentionMap
      return `${name} (⚠️ Add to SlackUserMentionMap for mentions)`;
    }
    
    // Final fallback
    return userId ? `HubSpot User ${userId}` : 'Unknown user';
  }

  // Helper function to send Slack notifications (matching format from hubspot_first_deal_won_calculations.js)
  async function sendSlackNotification(notification) {
    const slackWebhookUrl = process.env.SlackWebhookUrl;
    
    // Debug logging for environment variables
    console.log('🔍 SLACK CONFIGURATION CHECK:');
    console.log(`   SlackWebhookUrl present: ${slackWebhookUrl ? 'YES' : 'NO'}`);
    console.log(`   SlackWebhookUrl starts with https://hooks.slack.com: ${slackWebhookUrl ? slackWebhookUrl.startsWith('https://hooks.slack.com') : 'N/A'}`);
    console.log(`   SlackUserMentionMap present: ${process.env.SlackUserMentionMap ? 'YES' : 'NO'}`);
    
    if (!slackWebhookUrl) {
      console.log('⚠️  Slack webhook URL not configured - skipping notification');
      console.log('⚠️  Make sure SlackWebhookUrl environment variable is set (not SlackUserMentionMap)');
      return;
    }
    
    // Validate webhook URL format
    if (!slackWebhookUrl.startsWith('https://hooks.slack.com')) {
      console.error(`❌ Invalid Slack webhook URL format: ${slackWebhookUrl.substring(0, 50)}...`);
      console.error(`❌ Webhook URL should start with "https://hooks.slack.com"`);
      console.error(`❌ Check that SlackWebhookUrl env var is set correctly (not SlackUserMentionMap)`);
      return;
    }

    const ownerMention = notification.details?.companyOwnerMention || null;
    const ownerName = notification.details?.companyOwnerName || 'Unknown Owner';
    const ownerDisplay = formatUserDisplay(ownerName, ownerMention, notification.details?.companyOwnerId);
    const baseTitle = notification.title || '';
    // CRITICAL: Always include mention in title if available - this ensures Slack pings the user
    const textWithMention = ownerMention ? `${baseTitle} • Owner: ${ownerMention}` : `${baseTitle} • Owner: ${ownerDisplay}`;

    let slackMessage;

    if (notification.type === 'validation_failed') {
      // Notification for records with blank fields
      const fieldList = notification.details.blankFields
        .map(f => `• ${f.label} (${f.name})`)
        .join('\n');

      slackMessage = {
        channel: 'C07STQJV2A0', // Explicitly set channel for HubSpot notifications
        text: textWithMention,
        attachments: [
          {
            color: getSlackColor(notification.type),
            fields: [
              {
                title: '🏢 Company',
                value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
                short: true
              },
              {
                title: '👤 Company Owner',
                value: ownerDisplay,
                short: true
              },
              {
                title: '❌ Blank Fields',
                value: fieldList,
                short: false
              },
              {
                title: '📊 Validation Summary',
                value: `${notification.details.blankFields.length} of ${notification.details.totalFields} required fields are blank`,
                short: false
              },
              {
                title: '🔧 Action Needed',
                value: 'Please fill in the blank required fields to complete the company record',
                short: false
              }
            ],
            timestamp: Math.floor(Date.now() / 1000),
            footer: 'HubSpot Workflow Automation',
            footer_icon: 'https://hubspot.com/favicon.ico'
          }
        ]
      };
    } else if (notification.type === 'validation_passed') {
      // Notification for records that passed validation
      slackMessage = {
        channel: 'C07STQJV2A0', // Explicitly set channel for HubSpot notifications
        text: textWithMention,
        attachments: [
          {
            color: getSlackColor(notification.type),
            fields: [
              {
                title: '🏢 Company',
                value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
                short: true
              },
              {
                title: '👤 Company Owner',
                value: ownerDisplay,
                short: true
              },
              {
                title: '✅ Status',
                value: 'All required fields are filled',
                short: false
              }
            ],
            timestamp: Math.floor(Date.now() / 1000),
            footer: 'HubSpot Workflow Automation',
            footer_icon: 'https://hubspot.com/favicon.ico'
          }
        ]
      };
    } else if (notification.type === 'error') {
      // Error notification
      slackMessage = {
        channel: 'C07STQJV2A0', // Explicitly set channel for HubSpot notifications
        text: textWithMention,
        attachments: [
          {
            color: getSlackColor(notification.type),
            fields: [
              {
                title: '🏢 Company ID',
                value: notification.details.companyId || 'Unknown',
                short: true
              },
              {
                title: '👤 Company Owner',
                value: ownerDisplay,
                short: true
              },
              {
                title: '❌ Error',
                value: notification.details.errorMessage || 'Unknown error',
                short: false
              }
            ],
            timestamp: Math.floor(Date.now() / 1000),
            footer: 'HubSpot Workflow Automation',
            footer_icon: 'https://hubspot.com/favicon.ico'
          }
        ]
      };
    }

    try {
      console.log(`📤 Sending Slack notification to webhook...`);
      console.log(`📋 Message text: ${textWithMention}`);
      console.log(`📋 Owner mention in message: ${ownerMention || 'NONE'}`);
      
      const response = await fetch(slackWebhookUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(slackMessage)
      });

      if (response.ok) {
        console.log(`✅ Slack notification sent successfully`);
        console.log(`✅ Mention included: ${ownerMention ? 'YES (' + ownerMention + ')' : 'NO'}`);
      } else {
        const errorText = await response.text();
        console.error(`❌ Slack notification failed: ${response.status} ${response.statusText}`);
        console.error(`❌ Error response: ${errorText.substring(0, 200)}`);
      }
    } catch (error) {
      console.error(`❌ Slack notification error:`, error.message);
      console.error(`❌ Error stack:`, error.stack);
      if (error.message.includes('Failed to parse URL')) {
        console.error(`❌ CRITICAL: SlackWebhookUrl env var appears to contain invalid data`);
        console.error(`❌ Make sure SlackWebhookUrl is set to your Slack webhook URL (starts with https://hooks.slack.com)`);
        console.error(`❌ SlackUserMentionMap should be a separate env var with JSON mapping`);
      }
    }
  }

  // Helper function to get Slack color (matching hubspot_first_deal_won_calculations.js)
  function getSlackColor(type) {
    switch (type) {
      case 'success':
      case 'validation_passed':
        return 'good';
      case 'warning':
      case 'validation_failed':
        return 'warning';
      case 'error':
        return 'danger';
      default:
        return '#36a64f';
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
    propertiesToRetrieve.push('name', 'data_validation_status', 'data_validation_missing_fields');

    const company = await client.crm.companies.basicApi.getById(companyId, propertiesToRetrieve);
    const properties = company.properties || {};

    const companyName = properties.name || 'Unknown Company';
    const companyOwnerId = properties.hubspot_owner_id;
    const companyType = properties.type;
    
    // Resolve company owner name using the helper function
    console.log(`🔍 COMPANY OWNER RESOLUTION: Processing company ${companyId}`);
    let companyOwnerName = 'No Owner';
    if (companyOwnerId) {
      console.log(`👤 COMPANY OWNER: Resolving owner ID ${companyOwnerId} for company ${companyId}`);
      companyOwnerName = await getOwnerName(companyOwnerId);
      console.log(`✅ COMPANY OWNER RESOLVED: "${companyOwnerName}" for company ${companyId}`);
    } else {
      console.log(`❌ COMPANY OWNER: No owner ID found for company ${companyId}`);
    }
    
    const companyOwnerMention = getSlackMentionForUser(companyOwnerId);
    
    // Log mention lookup results
    if (companyOwnerId) {
      if (companyOwnerMention) {
        console.log(`✅ COMPANY OWNER SLACK MENTION FOUND: ${companyOwnerMention} for owner ${companyOwnerId}`);
      } else {
        console.log(`⚠️  COMPANY OWNER SLACK MENTION NOT FOUND: No mapping for owner ${companyOwnerId} in SlackUserMentionMap`);
      }
    }

    console.log(`✅ Company retrieved: ${companyName} (ID: ${companyId})`);
    console.log(`   Owner: ${companyOwnerName} (ID: ${companyOwnerId || 'N/A'})`);
    if (companyOwnerMention) {
      console.log(`   Owner Slack Mention: ${companyOwnerMention}`);
    } else if (companyOwnerId) {
      console.log(`   ⚠️  Owner Slack Mention: NOT CONFIGURED - Add owner ${companyOwnerId} to SlackUserMentionMap env var`);
    }
    console.log(`   Company Type: ${companyType || 'Unknown'}`);
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
    try {
      await client.crm.companies.basicApi.update(companyId, updateData);
      console.log(`✅ Company validation status updated successfully`);
    } catch (updateError) {
      console.error(`⚠️  Failed to update validation status properties: ${updateError.message}`);
      console.error(`⚠️  This may happen if properties don't exist or are read-only`);
      console.error(`⚠️  Validation will continue, but status flags won't be set`);
      // Don't fail the workflow - validation still happened, just can't flag it
    }
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 4: SEND SLACK NOTIFICATION (ONLY FOR FAILURES)
    // ========================================================================
    console.log('📢 STEP 4: SENDING SLACK NOTIFICATION');
    console.log('-'.repeat(50));

    let slackNotification = null;

    if (blankFields.length > 0) {
      // Send notification only for validation failure
      slackNotification = {
        type: 'validation_failed',
        title: '⚠️ Company Record Has Blank Required Fields',
        details: {
          companyId: companyId,
          companyName: companyName,
          companyOwnerId: companyOwnerId,
          companyOwnerName: companyOwnerName,
          companyOwnerMention: companyOwnerMention,
          companyType: companyType,
          blankFields: blankFields,
          totalFields: REQUIRED_FIELDS.length
        }
      };

      console.log(`📤 Sending validation failure notification for ${blankFields.length} blank fields`);
      
      try {
        await sendSlackNotification(slackNotification);
        console.log(`✅ Slack notification sent successfully`);
      } catch (slackError) {
        console.error(`❌ Slack notification failed:`, slackError.message);
        // Don't fail the entire workflow if Slack fails
      }
    } else {
      // Validation passed - no notification needed
      console.log(`✅ Validation passed - skipping Slack notification`);
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
    console.log(`Company Owner: ${formatUserDisplay(companyOwnerName, companyOwnerMention, companyOwnerId)}`);
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

    const companyId = event.object?.objectId;
    const companyOwnerId = event.object?.properties?.hubspot_owner_id;
    
    // Resolve company owner name (with error handling to avoid errors in error handler)
    let companyOwnerName = 'Unknown Owner';
    let companyOwnerMention = null;
    try {
      if (companyOwnerId) {
        companyOwnerName = await getOwnerName(companyOwnerId);
        companyOwnerMention = getSlackMentionForUser(companyOwnerId);
      }
    } catch (nameError) {
      console.error(`⚠️ Failed to resolve company owner name: ${nameError.message}`);
      companyOwnerName = `Owner ID: ${companyOwnerId || 'Unknown'}`;
    }

    // Send error notification to Slack
    try {
      await sendSlackNotification({
        type: 'error',
        title: '❌ Validation Workflow Error',
        details: {
          companyId: companyId,
          errorType: err.constructor.name,
          errorMessage: err.message,
          companyOwnerId: companyOwnerId,
          companyOwnerName: companyOwnerName,
          companyOwnerMention: companyOwnerMention
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

