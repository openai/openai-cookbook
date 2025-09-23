#!/usr/bin/env python3
"""
HubSpot Custom Code - Real Mixpanel Webhook Integration
Version: 2.0.0
Last Updated: 2025-01-09T18:00:00Z

This HubSpot custom code processes real Mixpanel data from the webhook
that's now receiving actual user data with UTM parameters and Mixpanel IDs.

WEBHOOK ENDPOINT: https://api-na1.hubapi.com/automation/v4/webhook-triggers/19877595/fXMW5p0

REAL DATA STRUCTURE FROM TEST EVENT:
{
  "action": "members",
  "parameters": {
    "mixpanel_cohort_id": "5167408",
    "mixpanel_project_id": "2201475", 
    "mixpanel_session_id": "37163825-ae24-4bc8-b8f8-a8b034d1d678",
    "mixpanel_cohort_name": "Registros Ultimas 24 horas",
    "mixpanel_integration_id": "0"
  },
  "members": [
    {
      "utm_term": "",
      "utm_medium": "ppc",
      "utm_source": "google", 
      "utm_content": "",
      "$distinct_id": "zoem7960@gmail.com",
      "utm_campaign": "Sales-Performance Max-V2",
      "mixpanel_distinct_id": "zoem7960@gmail.com"
    }
  ]
}
"""

# HubSpot Custom Code (JavaScript) - Copy this to HubSpot
HUBSPOT_CUSTOM_CODE = '''
const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  try {
    console.log('🚀 REAL MIXPANEL WEBHOOK PROCESSING STARTED');
    console.log('📋 Event Data:', JSON.stringify(event, null, 2));
    
    // Extract the webhook data from the event
    const webhookData = event.inputFields || event.object || event;
    
    console.log('📊 WEBHOOK DATA RECEIVED:', JSON.stringify(webhookData, null, 2));
    
    // Process the Mixpanel cohort data
    const contactUpdates = processMixpanelCohortData(webhookData);
    
    if (contactUpdates.length === 0) {
      console.log('❌ NO CONTACT UPDATES TO PROCESS');
      callback(null, 'No contact updates to process');
      return;
    }
    
    console.log(`📊 PROCESSING ${contactUpdates.length} CONTACT UPDATE(S)`);
    
    // Update contacts in HubSpot
    let successCount = 0;
    let errorCount = 0;
    const results = [];
    
    for (const update of contactUpdates) {
      try {
        console.log(`\\n🔄 PROCESSING CONTACT: ${update.email}`);
        
        // Find the contact in HubSpot
        const contact = await findContactByEmail(update.email);
        
        if (contact) {
          // Update the contact properties
          await updateContactProperties(contact.id, update.properties);
          successCount++;
          results.push({
            email: update.email,
            contactId: contact.id,
            status: 'success',
            updatedProperties: Object.keys(update.properties)
          });
          console.log(`✅ CONTACT UPDATED: ${update.email} (ID: ${contact.id})`);
        } else {
          console.log(`⚠️ CONTACT NOT FOUND: ${update.email}`);
          errorCount++;
          results.push({
            email: update.email,
            contactId: null,
            status: 'not_found',
            error: 'Contact not found in HubSpot'
          });
        }
      } catch (error) {
        console.error(`💥 ERROR PROCESSING ${update.email}:`, error.message);
        errorCount++;
        results.push({
          email: update.email,
          contactId: null,
          status: 'error',
          error: error.message
        });
      }
    }
    
    // Log final results
    console.log('\\n' + '='.repeat(80));
    console.log('📊 FINAL RESULTS SUMMARY');
    console.log('='.repeat(80));
    console.log(`✅ Successfully updated: ${successCount} contact(s)`);
    console.log(`❌ Errors/Not found: ${errorCount} contact(s)`);
    console.log(`📋 Total processed: ${contactUpdates.length} record(s)`);
    console.log('\\n📊 DETAILED RESULTS:');
    results.forEach((result, index) => {
      console.log(`   ${index + 1}. ${result.email} - ${result.status}`);
      if (result.status === 'success') {
        console.log(`      Contact ID: ${result.contactId}`);
        console.log(`      Updated Properties: ${result.updatedProperties.join(', ')}`);
      } else if (result.error) {
        console.log(`      Error: ${result.error}`);
      }
    });
    console.log('='.repeat(80));
    
    // Return success
    callback(null, {
      success: true,
      message: `Processed ${contactUpdates.length} records: ${successCount} updated, ${errorCount} errors`,
      results: results,
      summary: {
        total: contactUpdates.length,
        success: successCount,
        errors: errorCount
      }
    });
    
  } catch (error) {
    console.error('💥 FATAL ERROR IN MIXPANEL PROCESSING:', error.message);
    console.error('🔍 ERROR STACK:', error.stack);
    
    // Return error
    callback(error, {
      success: false,
      error: error.message,
      message: 'Failed to process Mixpanel webhook data'
    });
  }
  
  // Helper function to process Mixpanel cohort data
  function processMixpanelCohortData(data) {
    console.log('🔄 PROCESSING MIXPANEL COHORT DATA');
    console.log('📊 RAW DATA:', JSON.stringify(data, null, 2));
    
    const contactUpdates = [];
    
    // Check if this is the expected Mixpanel cohort structure
    if (data && data.action === 'members' && data.members && Array.isArray(data.members)) {
      console.log(`📋 PROCESSING COHORT: ${data.parameters?.mixpanel_cohort_name || 'Unknown'}`);
      console.log(`📊 COHORT ID: ${data.parameters?.mixpanel_cohort_id || 'Unknown'}`);
      console.log(`📊 PROJECT ID: ${data.parameters?.mixpanel_project_id || 'Unknown'}`);
      console.log(`📊 MEMBERS COUNT: ${data.members.length}`);
      
      // Process each member in the cohort
      data.members.forEach((member, index) => {
        console.log(`📋 PROCESSING MEMBER ${index + 1}:`, JSON.stringify(member, null, 2));
        
        // Extract email from distinct_id
        const email = member.$distinct_id || member.mixpanel_distinct_id;
        
        if (email) {
          const properties = extractMemberProperties(member, data.parameters);
          contactUpdates.push({
            email: email,
            properties: properties
          });
          console.log(`✅ EXTRACTED: ${email} -> ${Object.keys(properties).length} properties`);
        } else {
          console.log(`⚠️ SKIPPED: No email found in member ${index + 1}`);
        }
      });
    } else {
      console.log('❌ UNEXPECTED DATA STRUCTURE');
      console.log('📊 Expected: { action: "members", members: [...] }');
      console.log('📊 Received:', Object.keys(data || {}));
    }
    
    console.log(`📊 PROCESSED ${contactUpdates.length} CONTACT UPDATE(S)`);
    return contactUpdates;
  }
  
  // Helper function to extract properties from a cohort member
  function extractMemberProperties(member, parameters) {
    const properties = {};
    
    // Mixpanel identification
    if (member.$distinct_id) {
      properties.mixpanel_distinct_id = member.$distinct_id;
    }
    if (member.mixpanel_distinct_id) {
      properties.mixpanel_distinct_id = member.mixpanel_distinct_id;
    }
    
    // UTM Parameters (Marketing Attribution)
    if (member.utm_source) {
      properties.utm_source = member.utm_source;
    }
    if (member.utm_medium) {
      properties.utm_medium = member.utm_medium;
    }
    if (member.utm_campaign) {
      properties.utm_campaign = member.utm_campaign;
    }
    if (member.utm_term) {
      properties.utm_term = member.utm_term;
    }
    if (member.utm_content) {
      properties.utm_content = member.utm_content;
    }
    
    // Cohort information
    if (parameters) {
      if (parameters.mixpanel_cohort_name) {
        properties.mixpanel_cohort_name = parameters.mixpanel_cohort_name;
      }
      if (parameters.mixpanel_cohort_id) {
        properties.mixpanel_cohort_id = parameters.mixpanel_cohort_id;
      }
      if (parameters.mixpanel_project_id) {
        properties.mixpanel_project_id = parameters.mixpanel_project_id;
      }
      if (parameters.mixpanel_session_id) {
        properties.mixpanel_session_id = parameters.mixpanel_session_id;
      }
    }
    
    // Additional member properties (if any)
    Object.keys(member).forEach(key => {
      if (!key.startsWith('$') && !key.startsWith('utm_') && !key.startsWith('mixpanel_')) {
        // Map other properties
        const propertyName = `mixpanel_${key}`;
        properties[propertyName] = member[key];
      }
    });
    
    // Set sync metadata
    properties.last_mixpanel_sync = new Date().toISOString();
    properties.mixpanel_sync_source = 'cohort_export';
    
    return properties;
  }
  
  // Helper function to find contact by email
  async function findContactByEmail(email) {
    console.log(`🔍 SEARCHING FOR CONTACT: ${email}`);
    
    try {
      const searchRequest = {
        filterGroups: [{
          filters: [{
            propertyName: 'email',
            operator: 'EQ',
            value: email
          }]
        }],
        properties: ['email', 'firstname', 'lastname', 'company'],
        limit: 1
      };
      
      const searchResponse = await client.crm.contacts.searchApi.doSearch(searchRequest);
      
      console.log(`📋 SEARCH RESULTS: Found ${searchResponse.total} contact(s)`);
      
      if (searchResponse.total > 0) {
        const contact = searchResponse.results[0];
        console.log(`✅ CONTACT FOUND: ID ${contact.id} - ${contact.properties.email}`);
        return contact;
      } else {
        console.log(`❌ NO CONTACT FOUND for email: ${email}`);
        return null;
      }
    } catch (error) {
      console.error(`💥 CONTACT SEARCH ERROR for ${email}:`, error.message);
      throw error;
    }
  }
  
  // Helper function to update contact properties
  async function updateContactProperties(contactId, properties) {
    console.log(`🔄 UPDATING CONTACT ID: ${contactId}`);
    console.log('📝 PROPERTIES TO UPDATE:', JSON.stringify(properties, null, 2));
    
    try {
      const updateRequest = {
        properties: properties
      };
      
      const updateResponse = await client.crm.contacts.basicApi.update(contactId, updateRequest);
      
      console.log(`✅ CONTACT UPDATED SUCCESSFULLY: ID ${contactId}`);
      console.log('📊 UPDATE RESPONSE:', JSON.stringify(updateResponse, null, 2));
      
      return updateResponse;
    } catch (error) {
      console.error(`💥 CONTACT UPDATE ERROR for ID ${contactId}:`, error.message);
      throw error;
    }
  }
};
'''

def main():
    """Main function to display the updated HubSpot custom code"""
    print("🎉 REAL MIXPANEL DATA - UPDATED HUBSPOT CUSTOM CODE")
    print("=" * 80)
    print()
    print("✅ SUCCESS: Real Mixpanel data is now flowing!")
    print("📊 Webhook: https://api-na1.hubapi.com/automation/v4/webhook-triggers/19877595/fXMW5p0")
    print("📋 Cohort: Registros Ultimas 24 horas")
    print("👥 Members: Multiple users with UTM parameters")
    print()
    
    print("📋 UPDATED HUBSPOT CUSTOM CODE (JavaScript):")
    print("-" * 80)
    print(HUBSPOT_CUSTOM_CODE)
    print()
    
    print("🎯 KEY IMPROVEMENTS:")
    print("-" * 50)
    print("✅ Processes real Mixpanel cohort data structure")
    print("✅ Extracts UTM parameters for marketing attribution")
    print("✅ Maps Mixpanel distinct_id to contact email")
    print("✅ Handles cohort metadata (name, ID, project ID)")
    print("✅ Comprehensive error handling and logging")
    print("✅ Production-ready for your 197 users/24h export")
    print()
    
    print("📊 PROPERTY MAPPING:")
    print("-" * 50)
    mappings = [
        "$distinct_id → mixpanel_distinct_id",
        "utm_source → utm_source", 
        "utm_medium → utm_medium",
        "utm_campaign → utm_campaign",
        "utm_term → utm_term",
        "utm_content → utm_content",
        "mixpanel_cohort_name → mixpanel_cohort_name",
        "mixpanel_cohort_id → mixpanel_cohort_id",
        "mixpanel_project_id → mixpanel_project_id",
        "mixpanel_session_id → mixpanel_session_id"
    ]
    for mapping in mappings:
        print(f"• {mapping}")
    print()
    
    print("🚀 DEPLOYMENT INSTRUCTIONS:")
    print("-" * 50)
    print("1. Copy the JavaScript code above")
    print("2. Go to HubSpot > Automation > Workflows")
    print("3. Create/edit your webhook workflow")
    print("4. Add Custom Code action")
    print("5. Paste the code and save")
    print("6. Test with incoming webhook data")
    print()
    
    print("📊 EXPECTED RESULTS:")
    print("-" * 50)
    print("• Contacts will be updated with UTM parameters")
    print("• Mixpanel distinct_id will be stored")
    print("• Cohort information will be tracked")
    print("• Marketing attribution data will be preserved")
    print("• Sync timestamps will be recorded")
    print("=" * 80)

if __name__ == "__main__":
    main()
