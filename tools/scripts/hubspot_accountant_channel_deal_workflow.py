#!/usr/bin/env python3
"""
HubSpot Custom Code - Accountant Channel Deal Workflow
Latest Version: 1.0.0
Last Updated: 2025-01-15T20:00:00Z

This HubSpot Custom Code workflow automatically detects when deals involve
accountant channel team members (either as deal owners or collaborators)
and updates the accountant_channel_involucrado_en_la_venta field accordingly.

CRITICAL REQUIREMENT FOR HUBSPOT WORKFLOWS:
------------------------------------------
HubSpot custom code MUST call the callback function to complete execution:
- On success: callback(null, 'Success');
- On error: callback(err);

Without calling the callback, the workflow will hang with no logs or errors!

SYNC STATUS: This code is kept in sync with HubSpot workflow
"""

from datetime import datetime
from typing import Optional

# HubSpot Custom Code (JavaScript) - Copy this to HubSpot
HUBSPOT_CUSTOM_CODE = '''
const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

      // Helper function to get owner details with team information
      async function getOwnerDetails(ownerId) {
        console.log(`🔍 OWNER DETAILS START - Owner ID: ${ownerId}`);
        
        if (!ownerId) {
          console.log(`❌ OWNER DETAILS: No owner ID provided`);
          return { name: 'No Owner', team: 'Unknown', isAccountantChannel: false };
        }
        
        try {
          console.log(`📡 OWNERS API CALL: Fetching owner details for ID ${ownerId}`);
          
          const response = await fetch(`https://api.hubspot.com/crm/v3/owners/${ownerId}`, {
            headers: {
              'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
              'Content-Type': 'application/json'
            }
          });
          
          console.log(`📊 OWNERS API RESPONSE: Status ${response.status} for ID ${ownerId}`);
          
          if (response.ok) {
            const data = await response.json();
            console.log(`✅ OWNERS API SUCCESS: Raw data for ID ${ownerId}:`, JSON.stringify(data, null, 2));
            
            const firstName = data.firstName || '';
            const lastName = data.lastName || '';
            const fullName = `${firstName} ${lastName}`.trim();
            const isActive = data.archived === false;
            
            console.log(`👤 OWNER DETAILS: ID ${ownerId}`);
            console.log(`   - Full Name: "${fullName}"`);
            console.log(`   - Active Status: ${isActive ? 'ACTIVE' : 'INACTIVE'}`);
            
            // Check teams array for Accountant Channel team
            let teamName = 'Unknown';
            let isAccountantChannel = false;
            
            if (data.teams && Array.isArray(data.teams) && data.teams.length > 0) {
              console.log(`🏢 TEAMS FOUND: ${data.teams.length} teams assigned`);
              
              for (const team of data.teams) {
                const currentTeamName = team.name || 'Unknown';
                const isPrimary = team.primary || false;
                
                console.log(`🏢 TEAM: "${currentTeamName}" (Primary: ${isPrimary})`);
                
                // Check if this is the Accountant Channel team
                if (currentTeamName === 'Accountant Channel' || currentTeamName === 'accountant_channel') {
                  teamName = currentTeamName;
                  isAccountantChannel = true;
                  console.log(`🎯 ACCOUNTANT CHANNEL TEAM FOUND: "${currentTeamName}"`);
                  break;
                }
              }
              
              // If no Accountant Channel team found, use the first team name
              if (!isAccountantChannel && data.teams.length > 0) {
                teamName = data.teams[0].name || 'Unknown';
                console.log(`🏢 USING FIRST TEAM: "${teamName}"`);
              }
            } else {
              console.log(`❌ NO TEAMS: Owner ${ownerId} has no teams assigned`);
            }
            
            console.log(`👤 FINAL OWNER DETAILS: ID ${ownerId}`);
            console.log(`   - Full Name: "${fullName}"`);
            console.log(`   - Team: "${teamName}"`);
            console.log(`   - Is Accountant Channel: ${isAccountantChannel}`);
            console.log(`   - Active Status: ${isActive ? 'ACTIVE' : 'INACTIVE'}`);
            console.log(`🔍 DEBUG: Team lookup result - teamName: ${teamName}, isAccountantChannel: ${isAccountantChannel}`);
            console.log(`🔍 DEBUG: Team name comparison - "${teamName}" === "Accountant Channel": ${teamName === 'Accountant Channel'}`);
            console.log(`🔍 DEBUG: Team name comparison - "${teamName}" === "accountant_channel": ${teamName === 'accountant_channel'}`);
            
            return {
              name: fullName || `Owner ID: ${ownerId}`,
              team: teamName,
              isAccountantChannel: isAccountantChannel,
              isActive: isActive
            };
            
          } else {
            console.log(`⚠️ OWNERS API ERROR: Status ${response.status} for ID ${ownerId}`);
            const errorText = await response.text();
            console.log(`📄 Error Response Body: ${errorText}`);
            return { name: `Owner ID: ${ownerId}`, team: 'Unknown', isAccountantChannel: false };
          }
        } catch (error) {
          console.log(`💥 OWNERS API EXCEPTION: ID ${ownerId} - ${error.message}`);
          console.log(`🔍 Error Stack: ${error.stack}`);
          return { name: `Owner ID: ${ownerId}`, team: 'Unknown', isAccountantChannel: false };
        }
      }

  // Helper function to get deal collaborators using the correct property
  async function getDealCollaborators(dealId) {
    console.log(`🔍 COLLABORATORS START - Deal ID: ${dealId}`);
    
    try {
      console.log(`📡 COLLABORATORS API CALL: Fetching deal with hs_all_collaborator_owner_ids property`);
      
      const response = await fetch(`https://api.hubspot.com/crm/v3/objects/deals/${dealId}?properties=hs_all_collaborator_owner_ids`, {
        headers: {
          'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
          'Content-Type': 'application/json'
        }
      });
      
      console.log(`📊 COLLABORATORS API RESPONSE: Status ${response.status} for deal ${dealId}`);
      
      if (response.ok) {
        const data = await response.json();
        const collaboratorIdsString = data.properties?.hs_all_collaborator_owner_ids;
        
        console.log(`🔍 COLLABORATOR IDS STRING: "${collaboratorIdsString}"`);
        
        if (!collaboratorIdsString) {
          console.log(`❌ NO COLLABORATORS: Deal ${dealId} has no collaborators`);
          return [];
        }
        
        // Parse the semicolon-separated string of user IDs
        const collaboratorIds = collaboratorIdsString.split(';').filter(id => id.trim() !== '');
        console.log(`✅ COLLABORATORS FOUND: ${collaboratorIds.length} collaborator IDs: [${collaboratorIds.join(', ')}]`);
        
        const collaborators = [];
        for (const ownerId of collaboratorIds) {
          console.log(`👤 COLLABORATOR: Processing owner ID ${ownerId}`);
          
          try {
            const ownerDetails = await getOwnerDetails(ownerId);
            collaborators.push({
              ownerId: ownerId,
              ownerName: ownerDetails.name,
              team: ownerDetails.team,
              isAccountantChannel: ownerDetails.isAccountantChannel
            });
          } catch (ownerError) {
            console.log(`💥 COLLABORATOR OWNER ERROR: ${ownerError.message}`);
          }
        }
        
        console.log(`✅ COLLABORATORS COMPLETE: Found ${collaborators.length} collaborators with owner info`);
        return collaborators;
        
      } else {
        console.log(`⚠️ COLLABORATORS API ERROR: Status ${response.status} for deal ${dealId}`);
        return [];
      }
    } catch (error) {
      console.log(`💥 COLLABORATORS API EXCEPTION: Deal ${dealId} - ${error.message}`);
      return [];
    }
  }

  try {
    const dealId = String(event.object.objectId);

    console.log('='.repeat(80));
    console.log('🚀 ACCOUNTANT CHANNEL DEAL WORKFLOW STARTED');
    console.log('='.repeat(80));
    console.log('📋 WORKFLOW INFO:');
    console.log(`   Deal ID: ${dealId}`);
    console.log(`   Timestamp: ${new Date().toISOString()}`);
    console.log(`   Event Type: ${event.eventType || 'unknown'}`);
    console.log(`   Properties Changed: ${event.propertiesChanged || 'none'}`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 0: VALIDATE DEAL ID AND DIAGNOSTIC INFO
    // ========================================================================
    console.log('🔍 STEP 0: VALIDATING DEAL ID AND DIAGNOSTIC INFO');
    console.log('-'.repeat(50));
    
    if (!dealId || dealId === 'undefined' || dealId === 'null') {
      console.error(`❌ INVALID DEAL ID: Deal ID is missing or invalid: ${dealId}`);
      callback(new Error(`Invalid deal ID: ${dealId}`));
      return;
    }
    
    console.log(`✅ DEAL ID VALID: ${dealId}`);
    console.log(`🔍 DEAL ID TYPE: ${typeof dealId}`);
    console.log(`🔍 DEAL ID LENGTH: ${dealId.length}`);
    console.log(`🔍 DEAL ID IS NUMERIC: ${!isNaN(dealId)}`);
    console.log(`🔍 EVENT OBJECT: ${JSON.stringify(event, null, 2)}`);
    console.log(`🔍 EVENT OBJECT ID: ${event.object?.objectId}`);
    console.log(`🔍 EVENT OBJECT TYPE: ${event.object?.objectType}`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 1: GET DEAL DETAILS
    // ========================================================================
    console.log('📊 STEP 1: GETTING DEAL DETAILS');
    console.log('-'.repeat(50));
    
    let deal;
    try {
      console.log(`🔍 FETCHING DEAL: Attempting to get deal ${dealId}`);
      console.log(`🔍 API ENDPOINT: /crm/v3/objects/deals/${dealId}`);
      console.log(`🔍 REQUESTED PROPERTIES: dealname, hubspot_owner_id, accountant_channel_involucrado_en_la_venta, amount, dealstage, hs_all_collaborator_owner_ids`);
      
      deal = await client.crm.deals.basicApi.getById(dealId, [
        'dealname', 
        'hubspot_owner_id', 
        'accountant_channel_involucrado_en_la_venta',
        'amount',
        'dealstage',
        'hs_all_collaborator_owner_ids'
      ]);
      console.log(`✅ DEAL FOUND: Successfully retrieved deal ${dealId}`);
      console.log(`🔍 DEAL PROPERTIES: ${JSON.stringify(deal.properties, null, 2)}`);
    } catch (dealError) {
      console.error(`❌ DEAL NOT FOUND: Deal ${dealId} could not be retrieved`);
      console.error(`Error details:`, dealError.message);
      console.error(`Error code:`, dealError.code);
      console.error(`Error status:`, dealError.status);
      console.error(`Full error object:`, JSON.stringify(dealError, null, 2));
      
      // Try to get more diagnostic information
      try {
        console.log(`🔍 DIAGNOSTIC: Attempting to get deal with minimal properties`);
        const diagnosticDeal = await client.crm.deals.basicApi.getById(dealId, ['dealname']);
        console.log(`🔍 DIAGNOSTIC SUCCESS: Deal exists but may have property access issues`);
        console.log(`🔍 DIAGNOSTIC DEAL: ${JSON.stringify(diagnosticDeal, null, 2)}`);
      } catch (diagnosticError) {
        console.error(`🔍 DIAGNOSTIC FAILED: Deal ${dealId} does not exist at all`);
        console.error(`🔍 DIAGNOSTIC ERROR: ${diagnosticError.message}`);
      }
      
      // Send error notification to Slack
      try {
        await sendSlackNotification({
          type: 'error',
          title: '❌ Deal Not Found',
          message: `Deal ${dealId} could not be found or accessed. This may be due to the deal being deleted, archived, or insufficient permissions.`,
          details: {
            dealId: dealId,
            errorMessage: dealError.message,
            errorCode: dealError.code || 'UNKNOWN',
            errorStatus: dealError.status || 'UNKNOWN',
            reason: 'Deal not found or inaccessible - may be deleted, archived, or permission issue'
          }
        });
      } catch (slackError) {
        console.error(`❌ Slack error notification failed:`, slackError.message);
      }
      
      // Call callback with error
      callback(new Error(`Deal ${dealId} not found: ${dealError.message}`));
      return;
    }
    
    const dealName = deal.properties.dealname;
    const dealOwnerId = deal.properties.hubspot_owner_id;
    const currentAccountantChannelValue = deal.properties.accountant_channel_involucrado_en_la_venta;
    const dealAmount = deal.properties.amount;
    const dealStage = deal.properties.dealstage;
    
    console.log(`Deal Name: ${dealName}`);
    console.log(`Deal Owner ID: ${dealOwnerId}`);
    console.log(`Current Accountant Channel Value: ${currentAccountantChannelValue}`);
    console.log(`Deal Amount: ${dealAmount}`);
    console.log(`Deal Stage: ${dealStage}`);
    
    console.log('✅ STEP 1 COMPLETE');
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 2: CHECK DEAL OWNER
    // ========================================================================
    console.log('👤 STEP 2: CHECKING DEAL OWNER');
    console.log('-'.repeat(50));
    
    let dealOwnerDetails = null;
    let ownerIsAccountantChannel = false;
    
    if (dealOwnerId) {
      dealOwnerDetails = await getOwnerDetails(dealOwnerId);
      ownerIsAccountantChannel = dealOwnerDetails.isAccountantChannel;
      
      console.log(`Deal Owner: ${dealOwnerDetails.name}`);
      console.log(`Owner Team: ${dealOwnerDetails.team}`);
      console.log(`Owner is Accountant Channel: ${ownerIsAccountantChannel}`);
    } else {
      console.log(`❌ No deal owner found`);
    }
    
    console.log('✅ STEP 2 COMPLETE');
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 3: CHECK DEAL COLLABORATORS
    // ========================================================================
    console.log('👥 STEP 3: CHECKING DEAL COLLABORATORS');
    console.log('-'.repeat(50));
    
    // Get collaborators from the deal properties we already fetched
    const collaboratorIdsString = deal.properties.hs_all_collaborator_owner_ids;
    console.log(`🔍 COLLABORATOR IDS FROM DEAL: "${collaboratorIdsString}"`);
    
    let collaborators = [];
    let accountantChannelCollaborators = [];
    
    if (collaboratorIdsString) {
      // Parse the semicolon-separated string of user IDs
      const collaboratorIds = collaboratorIdsString.split(';').filter(id => id.trim() !== '');
      console.log(`✅ COLLABORATORS FOUND: ${collaboratorIds.length} collaborator IDs: [${collaboratorIds.join(', ')}]`);
      
      for (const ownerId of collaboratorIds) {
        console.log(`👤 COLLABORATOR: Processing owner ID ${ownerId}`);
        
        try {
          console.log(`🔍 COLLABORATOR PROCESSING: Starting owner details lookup for ${ownerId}`);
          const ownerDetails = await getOwnerDetails(ownerId);
          console.log(`🔍 COLLABORATOR PROCESSING: Owner details received for ${ownerId}:`, JSON.stringify(ownerDetails, null, 2));
          
          const collaborator = {
            ownerId: ownerId,
            ownerName: ownerDetails.name,
            team: ownerDetails.team,
            isAccountantChannel: ownerDetails.isAccountantChannel
          };
          
          collaborators.push(collaborator);
          
          if (ownerDetails.isAccountantChannel) {
            accountantChannelCollaborators.push(collaborator);
            console.log(`🎯 ACCOUNTANT CHANNEL COLLABORATOR FOUND: ${ownerDetails.name} (Team: ${ownerDetails.team})`);
          }
          
          console.log(`👤 COLLABORATOR DETAILS: ${ownerDetails.name} (Team: ${ownerDetails.team}) - Accountant Channel: ${ownerDetails.isAccountantChannel}`);
          console.log(`🔍 DEBUG: Collaborator ${ownerId} - name: ${ownerDetails.name}, team: ${ownerDetails.team}, isAccountantChannel: ${ownerDetails.isAccountantChannel}`);
        } catch (ownerError) {
          console.log(`💥 COLLABORATOR OWNER ERROR: ${ownerError.message}`);
          console.log(`🔍 COLLABORATOR OWNER ERROR STACK: ${ownerError.stack}`);
        }
      }
    } else {
      console.log(`❌ NO COLLABORATORS: Deal ${dealId} has no collaborators`);
    }
    
    console.log(`Total Collaborators: ${collaborators.length}`);
    console.log(`Accountant Channel Collaborators: ${accountantChannelCollaborators.length}`);
    
    if (collaborators.length > 0) {
      console.log('All Collaborators:');
      collaborators.forEach((collab, index) => {
        console.log(`  ${index + 1}. ${collab.ownerName} (Team: ${collab.team}) - Accountant Channel: ${collab.isAccountantChannel}`);
      });
    }
    
    console.log('✅ STEP 3 COMPLETE');
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 4: DETERMINE ACCOUNTANT CHANNEL INVOLVEMENT
    // ========================================================================
    console.log('⚙️ STEP 4: DETERMINING ACCOUNTANT CHANNEL INVOLVEMENT');
    console.log('-'.repeat(50));
    
    const hasAccountantChannelInvolvement = ownerIsAccountantChannel || accountantChannelCollaborators.length > 0;
    const newAccountantChannelValue = hasAccountantChannelInvolvement ? 'true' : 'false';
    
    console.log(`Owner is Accountant Channel: ${ownerIsAccountantChannel}`);
    console.log(`Has Accountant Channel Collaborators: ${accountantChannelCollaborators.length > 0}`);
    console.log(`Has Accountant Channel Involvement: ${hasAccountantChannelInvolvement}`);
    console.log(`Current Field Value: ${currentAccountantChannelValue}`);
    console.log(`New Field Value: ${newAccountantChannelValue}`);
    
    // Check if update is needed
    const needsUpdate = currentAccountantChannelValue !== newAccountantChannelValue;
    console.log(`Needs Update: ${needsUpdate}`);
    
    let workflowOutcome = '';
    let slackNotification = null;
    
    if (needsUpdate) {
      console.log(`🔄 UPDATE NEEDED: Changing accountant_channel_involucrado_en_la_venta from "${currentAccountantChannelValue}" to "${newAccountantChannelValue}"`);
      
      try {
        await client.crm.deals.basicApi.update(dealId, {
          properties: {
            accountant_channel_involucrado_en_la_venta: newAccountantChannelValue
          }
        });
        
        console.log(`✅ FIELD UPDATED: accountant_channel_involucrado_en_la_venta set to "${newAccountantChannelValue}"`);
        workflowOutcome = 'FIELD_UPDATED';
        
        // Prepare Slack notification
        const involvementReason = [];
        if (ownerIsAccountantChannel) {
          involvementReason.push(`Deal Owner: ${dealOwnerDetails.name} (${dealOwnerDetails.team})`);
        }
        if (accountantChannelCollaborators.length > 0) {
          const collaboratorNames = accountantChannelCollaborators.map(c => `${c.ownerName} (${c.team})`).join(', ');
          involvementReason.push(`Collaborators: ${collaboratorNames}`);
        }
        
        slackNotification = {
          type: 'success',
          title: '✅ Accountant Channel Field Updated',
          message: `Deal "${dealName}" - accountant_channel_involucrado_en_la_venta updated from "${currentAccountantChannelValue}" to "${newAccountantChannelValue}"`,
          details: {
            dealId: dealId,
            dealName: dealName,
            dealAmount: dealAmount,
            dealStage: dealStage,
            oldValue: currentAccountantChannelValue,
            newValue: newAccountantChannelValue,
            hasAccountantChannelInvolvement: hasAccountantChannelInvolvement,
            involvementReason: involvementReason.join(' | '),
            dealOwner: dealOwnerDetails ? dealOwnerDetails.name : 'No Owner',
            dealOwnerTeam: dealOwnerDetails ? dealOwnerDetails.team : 'Unknown',
            totalCollaborators: collaborators.length,
            accountantChannelCollaborators: accountantChannelCollaborators.length,
            changeReason: `Field updated because ${hasAccountantChannelInvolvement ? 'deal involves Accountant Channel team members' : 'no Accountant Channel team members involved'}`
          }
        };
        
      } catch (updateError) {
        console.error(`❌ FIELD UPDATE FAILED: ${updateError.message}`);
        workflowOutcome = 'UPDATE_FAILED';
        
        slackNotification = {
          type: 'error',
          title: '❌ Accountant Channel Field Update Failed',
          message: `Failed to update accountant_channel_involucrado_en_la_venta for deal "${dealName}" - ${updateError.message}`,
          details: {
            dealId: dealId,
            dealName: dealName,
            errorMessage: updateError.message,
            hasAccountantChannelInvolvement: hasAccountantChannelInvolvement,
            intendedValue: newAccountantChannelValue
          }
        };
      }
    } else {
      console.log(`✅ NO UPDATE NEEDED: Field already set to correct value`);
      workflowOutcome = 'NO_CHANGE_NEEDED';
      
      // Still send notification for visibility
      slackNotification = {
        type: 'info',
        title: 'ℹ️ Accountant Channel Field Already Correct',
        message: `Deal "${dealName}" - accountant_channel_involucrado_en_la_venta already set to "${currentAccountantChannelValue}"`,
        details: {
          dealId: dealId,
          dealName: dealName,
          dealAmount: dealAmount,
          dealStage: dealStage,
          currentValue: currentAccountantChannelValue,
          hasAccountantChannelInvolvement: hasAccountantChannelInvolvement,
          dealOwner: dealOwnerDetails ? dealOwnerDetails.name : 'No Owner',
          dealOwnerTeam: dealOwnerDetails ? dealOwnerDetails.team : 'Unknown',
          totalCollaborators: collaborators.length,
          accountantChannelCollaborators: accountantChannelCollaborators.length,
          reason: 'Field already set to correct value - no update needed'
        }
      };
    }
    
    console.log('✅ STEP 4 COMPLETE');
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 5: SENDING SLACK NOTIFICATION
    // ========================================================================
    if (slackNotification) {
      console.log('📢 STEP 5: SENDING SLACK NOTIFICATION');
      console.log('-'.repeat(50));
      
      try {
        console.log(`📤 Sending notification: ${slackNotification.type} - ${slackNotification.title}`);
        await sendSlackNotification(slackNotification);
        console.log(`✅ Slack notification sent successfully`);
      } catch (slackError) {
        console.error(`❌ Slack notification failed:`, slackError.message);
        console.error(`🔍 Slack error details:`, slackError);
        // Don't fail the entire workflow if Slack fails
      }
      
      console.log('✅ STEP 5 COMPLETE');
    } else {
      console.log('📢 STEP 5: SKIPPED (No notification needed)');
    }
    console.log('='.repeat(80));

    // ========================================================================
    // FINAL WORKFLOW EXECUTION SUMMARY
    // ========================================================================
    console.log('📊 FINAL WORKFLOW EXECUTION SUMMARY');
    console.log('-'.repeat(50));
    console.log(`Deal: ${dealName} (ID: ${dealId})`);
    console.log(`Deal Owner: ${dealOwnerDetails ? dealOwnerDetails.name : 'No Owner'}`);
    console.log(`Owner Team: ${dealOwnerDetails ? dealOwnerDetails.team : 'Unknown'}`);
    console.log(`Total Collaborators: ${collaborators.length}`);
    console.log(`Accountant Channel Collaborators: ${accountantChannelCollaborators.length}`);
    console.log(`Has Accountant Channel Involvement: ${hasAccountantChannelInvolvement}`);
    console.log(`Field Value: ${currentAccountantChannelValue} → ${newAccountantChannelValue}`);
    console.log(`Workflow Outcome: ${workflowOutcome}`);
    console.log(`Slack Notification: ${slackNotification ? 'SENT' : 'NONE'}`);
    console.log('='.repeat(80));
    console.log('🎉 ACCOUNTANT CHANNEL DEAL WORKFLOW COMPLETED SUCCESSFULLY');
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
        title: '❌ Accountant Channel Workflow Error',
        message: `Error in accountant channel workflow for deal ${event.object.objectId}`,
        details: {
          dealId: event.object.objectId,
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
      const headersString = JSON.stringify(err.response.headers, null, 2);
      const bodyString = JSON.stringify(err.response.body, null, 2);
      console.error('Response headers:', headersString);
      console.error('Response body:', bodyString);
    }

    const errorString = JSON.stringify(err, null, 2);
    console.error('Full error object:', errorString);
    console.error('=== ERROR LOGGING COMPLETE ===');

    // Call callback with error
    callback(err);
  }
};

// Slack notification function
async function sendSlackNotification(notification) {
  const slackWebhookUrl = process.env.SlackWebhookUrl;
  
  // Check if webhook URL is configured
  if (!slackWebhookUrl) {
    console.error('❌ SLACK WEBHOOK MISSING: SlackWebhookUrl environment variable not set');
    throw new Error('Slack webhook URL not configured. Please set SlackWebhookUrl environment variable.');
  }
  
  console.log(`📤 SLACK NOTIFICATION: Sending ${notification.type} notification to Slack`);
  
  let slackMessage;
  
  if (notification.type === 'success') {
    // Success notification with field update details
    slackMessage = {
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '💼 Deal',
              value: `<https://app.hubspot.com/contacts/19877595/deal/${notification.details.dealId}|${notification.details.dealName}>`,
              short: true
            },
            {
              title: '💰 Amount',
              value: notification.details.dealAmount ? `$${parseInt(notification.details.dealAmount).toLocaleString()}` : 'Not set',
              short: true
            },
            {
              title: '📊 Stage',
              value: notification.details.dealStage || 'Unknown',
              short: true
            },
            {
              title: '👤 Deal Owner',
              value: `${notification.details.dealOwner} (${notification.details.dealOwnerTeam})`,
              short: true
            },
            {
              title: '🔄 Field Change',
              value: `${notification.details.oldValue} → ${notification.details.newValue}`,
              short: true
            },
            {
              title: '👥 Collaborators',
              value: `${notification.details.totalCollaborators} total, ${notification.details.accountantChannelCollaborators} from Accountant Channel`,
              short: true
            },
            {
              title: '💡 Reason for Change',
              value: notification.details.involvementReason || notification.details.changeReason,
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Accountant Channel Workflow',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  } else if (notification.type === 'info') {
    // Info notification for no change needed
    slackMessage = {
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '💼 Deal',
              value: `<https://app.hubspot.com/contacts/19877595/deal/${notification.details.dealId}|${notification.details.dealName}>`,
              short: true
            },
            {
              title: '💰 Amount',
              value: notification.details.dealAmount ? `$${parseInt(notification.details.dealAmount).toLocaleString()}` : 'Not set',
              short: true
            },
            {
              title: '📊 Stage',
              value: notification.details.dealStage || 'Unknown',
              short: true
            },
            {
              title: '👤 Deal Owner',
              value: `${notification.details.dealOwner} (${notification.details.dealOwnerTeam})`,
              short: true
            },
            {
              title: '✅ Current Value',
              value: notification.details.currentValue,
              short: true
            },
            {
              title: '👥 Collaborators',
              value: `${notification.details.totalCollaborators} total, ${notification.details.accountantChannelCollaborators} from Accountant Channel`,
              short: true
            },
            {
              title: '💡 Status',
              value: notification.details.reason,
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Accountant Channel Workflow',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  } else {
    // Error notification
    slackMessage = {
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '💼 Deal',
              value: `<https://app.hubspot.com/contacts/19877595/deal/${notification.details.dealId}|${notification.details.dealName}>`,
              short: true
            },
            {
              title: '❌ Error',
              value: notification.details.errorMessage || notification.details.errorMessage,
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Accountant Channel Workflow',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  }

  const response = await fetch(slackWebhookUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(slackMessage)
  });

  if (!response.ok) {
    throw new Error(`Slack API error: ${response.status} ${response.statusText}`);
  }
}

function getSlackColor(type) {
  switch (type) {
    case 'success': return 'good';
    case 'info': return '#36a64f';
    case 'error': return 'danger';
    default: return '#36a64f';
  }
}
'''


# Version tracking
WORKFLOW_VERSION = "1.0.0"
LAST_UPDATED = "2025-01-15T20:00:00Z"
CHANGES = [
    "INITIAL VERSION: Created accountant channel deal workflow that automatically detects when deals involve Accountant Channel team members (either as deal owners or collaborators) and updates the accountant_channel_involucrado_en_la_venta field accordingly",
    "DEAL OWNER CHECKING: Added functionality to check if the deal owner belongs to the 'Accountant Channel' team and update the field to 'true' if they do",
    "COLLABORATOR CHECKING: Added functionality to check all deal collaborators and see if any of their owners belong to the 'Accountant Channel' team",
    "FIELD UPDATES: Automatically updates the accountant_channel_involucrado_en_la_venta field with 'true' or 'false' based on Accountant Channel team involvement",
    "SLACK NOTIFICATIONS: Sends detailed Slack notifications for field updates, no changes needed, and errors with deal information and involvement details",
    "COMPREHENSIVE LOGGING: Added detailed logging throughout the workflow for debugging and monitoring purposes",
    "ERROR HANDLING: Includes proper error handling with Slack notifications for workflow failures"
]

def get_latest_code() -> str:
    """Get the latest HubSpot Custom Code"""
    return HUBSPOT_CUSTOM_CODE

def get_version_info() -> dict:
    """Get workflow version information"""
    return {
        "version": WORKFLOW_VERSION,
        "last_updated": LAST_UPDATED,
        "changes": CHANGES
    }

if __name__ == "__main__":
    print("🔧 HubSpot Custom Code - Accountant Channel Deal Workflow")
    print("=" * 80)
    print(f"Version: {WORKFLOW_VERSION}")
    print(f"Last Updated: {LAST_UPDATED}")
    print(f"Changes: {len(CHANGES)} updates")
    print()
    print("📋 Copy the JavaScript code above to your HubSpot workflow")
    print("🔔 Slack notifications enabled for field updates and workflow outcomes")
    print("✅ Ready for production use with comprehensive monitoring")
