#!/usr/bin/env python3
"""
HubSpot Custom Code - UTM FIELDS ONLY (NO CUSTOM FIELDS)
Version: 5.0.0 - PRODUCTION READY - UTM FIELDS ONLY
Last Updated: 2025-01-09T22:00:00Z

This HubSpot custom code uses ONLY verified UTM fields that exist in HubSpot.
NO custom Mixpanel fields will be created or used.

VERIFICATION STATUS:
✅ utm_campaign - VERIFIED in HubSpot Contact Properties
✅ utm_source - VERIFIED in HubSpot Contact Properties  
✅ utm_medium - VERIFIED in HubSpot Contact Properties
✅ utm_term - VERIFIED in HubSpot Contact Properties
✅ utm_content - VERIFIED in HubSpot Contact Properties
✅ initial_utm_campaign - VERIFIED in HubSpot Contact Properties
✅ initial_utm_source - VERIFIED in HubSpot Contact Properties
✅ initial_utm_medium - VERIFIED in HubSpot Contact Properties

WEBHOOK ENDPOINT: https://api-na1.hubapi.com/automation/v4/webhook-triggers/19877595/fXMW5p0
"""

# PRODUCTION-READY HUBSPOT CUSTOM CODE (JavaScript) - UTM FIELDS ONLY
HUBSPOT_CUSTOM_CODE_UTM_ONLY = '''
const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  try {
    console.log('🚀 MIXPANEL WEBHOOK PROCESSING - UTM FIELDS ONLY');
    console.log('📋 Event Data:', JSON.stringify(event, null, 2));
    
    const webhookData = event.inputFields || event.object || event;
    
    console.log('📊 WEBHOOK DATA RECEIVED:', JSON.stringify(webhookData, null, 2));
    
    const contactUpdates = processMixpanelCohortData(webhookData);
    
    if (contactUpdates.length === 0) {
      console.log('❌ NO CONTACT UPDATES TO PROCESS');
      callback(null, 'No contact updates to process');
      return;
    }
    
    console.log(`📊 PROCESSING ${contactUpdates.length} CONTACT UPDATE(S)`);
    
    let successCount = 0;
    let errorCount = 0;
    const results = [];
    
    for (const update of contactUpdates) {
      try {
        console.log(`\\n🔄 PROCESSING CONTACT: ${update.email}`);
        
        const contact = await findContactByEmail(update.email);
        
        if (contact) {
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
    
    callback(error, {
      success: false,
      error: error.message,
      message: 'Failed to process Mixpanel webhook data'
    });
  }
  
  function processMixpanelCohortData(data) {
    console.log('🔄 PROCESSING MIXPANEL COHORT DATA - UTM FIELDS ONLY');
    console.log('📊 RAW DATA:', JSON.stringify(data, null, 2));
    
    const contactUpdates = [];
    
    if (data && data.action === 'members' && data.members && Array.isArray(data.members)) {
      console.log(`📋 PROCESSING COHORT: ${data.parameters?.mixpanel_cohort_name || 'Unknown'}`);
      console.log(`📊 COHORT ID: ${data.parameters?.mixpanel_cohort_id || 'Unknown'}`);
      console.log(`📊 PROJECT ID: ${data.parameters?.mixpanel_project_id || 'Unknown'}`);
      console.log(`📊 MEMBERS COUNT: ${data.members.length}`);
      
      data.members.forEach((member, index) => {
        console.log(`📋 PROCESSING MEMBER ${index + 1}:`, JSON.stringify(member, null, 2));
        
        const email = member.$distinct_id || member.mixpanel_distinct_id;
        
        if (email) {
          const properties = extractUTMProperties(member, data.parameters);
          contactUpdates.push({
            email: email,
            properties: properties
          });
          console.log(`✅ EXTRACTED: ${email} -> ${Object.keys(properties).length} UTM properties`);
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
  
  function extractUTMProperties(member, parameters) {
    const properties = {};
    
    // ✅ VERIFIED UTM FIELDS ONLY - NO CUSTOM FIELDS
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
    
    // ✅ VERIFIED INITIAL UTM FIELDS ONLY
    if (member.initial_utm_source) {
      properties.initial_utm_source = member.initial_utm_source;
    }
    if (member.initial_utm_medium) {
      properties.initial_utm_medium = member.initial_utm_medium;
    }
    if (member.initial_utm_campaign) {
      properties.initial_utm_campaign = member.initial_utm_campaign;
    }
    
    console.log(`📊 EXTRACTED ${Object.keys(properties).length} UTM PROPERTIES:`, Object.keys(properties));
    return properties;
  }
  
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
  
  async function updateContactProperties(contactId, properties) {
    console.log(`🔄 UPDATING CONTACT ID: ${contactId}`);
    console.log('📝 UTM PROPERTIES TO UPDATE:', JSON.stringify(properties, null, 2));
    
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
    """Display the production-ready HubSpot custom code"""
    
    print("🚀 HUBSPOT CUSTOM CODE - UTM FIELDS ONLY")
    print("=" * 80)
    print()
    print("📋 PRODUCTION-READY CODE:")
    print("✅ Uses ONLY verified UTM fields that exist in HubSpot")
    print("❌ NO custom Mixpanel fields will be created")
    print("🎯 Focus: UTM marketing attribution only")
    print()
    print("📊 VERIFIED FIELDS:")
    print("✅ utm_campaign, utm_source, utm_medium, utm_term, utm_content")
    print("✅ initial_utm_campaign, initial_utm_source, initial_utm_medium")
    print()
    print("🔗 WEBHOOK ENDPOINT:")
    print("https://api-na1.hubapi.com/automation/v4/webhook-triggers/19877595/fXMW5p0")
    print()
    print("=" * 80)
    print("📝 COPY THIS CODE TO HUBSPOT CUSTOM CODE ACTION:")
    print("=" * 80)
    print()
    print(HUBSPOT_CUSTOM_CODE_UTM_ONLY)
    print()
    print("=" * 80)
    print("✅ READY FOR DEPLOYMENT")
    print("🎯 NO CUSTOM FIELDS REQUIRED")
    print("📊 UTM ATTRIBUTION ONLY")

if __name__ == "__main__":
    main()



