#!/usr/bin/env python3
"""
HubSpot Custom Code - Enhanced Mixpanel Webhook Integration
Version: 1.1.0
Last Updated: 2025-01-09T16:00:00Z

This enhanced HubSpot custom code fetches data from a Mixpanel webhook via Zapier
and updates contact fields in HubSpot. It handles both current status responses
and actual Mixpanel event data.

WEBHOOK ENDPOINT: https://hooks.zapier.com/hooks/catch/24538/2f03rbk/

CURRENT WEBHOOK RESPONSE FORMAT:
{
  "attempt": "01995fb7-8092-ccc1-e89d-0a64f79e0d77",
  "id": "01995fb7-8092-ccc1-e89d-0a64f79e0d77", 
  "request_id": "01995fb7-8092-ccc1-e89d-0a64f79e0d77",
  "status": "success"
}

EXPECTED MIXPANEL DATA FORMAT (when active):
- Single event: { "event": "event_name", "properties": {...}, "distinct_id": "user@email.com" }
- Multiple events: [{ "event": "event_name", "properties": {...}, "distinct_id": "user@email.com" }, ...]
"""

# HubSpot Custom Code (JavaScript) - Copy this to HubSpot
HUBSPOT_CUSTOM_CODE = '''
const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  // Configuration
  const MIXPANEL_WEBHOOK_URL = 'https://hooks.zapier.com/hooks/catch/24538/2f03rbk/';
  
  // Helper function to fetch data from Mixpanel webhook
  async function fetchMixpanelData() {
    console.log('🔗 FETCHING MIXPANEL DATA FROM WEBHOOK');
    console.log(`📡 Webhook URL: ${MIXPANEL_WEBHOOK_URL}`);
    
    try {
      const response = await fetch(MIXPANEL_WEBHOOK_URL, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'User-Agent': 'HubSpot-CustomCode/1.1.0'
        }
      });
      
      console.log(`📊 WEBHOOK RESPONSE STATUS: ${response.status}`);
      console.log(`📋 RESPONSE HEADERS:`, Object.fromEntries(response.headers.entries()));
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('✅ WEBHOOK DATA RECEIVED:', JSON.stringify(data, null, 2));
      
      return data;
    } catch (error) {
      console.error('❌ WEBHOOK FETCH ERROR:', error.message);
      throw error;
    }
  }

  // Helper function to check if response contains actual Mixpanel data
  function isMixpanelData(data) {
    // Check if it's a status response (current format)
    if (data && typeof data === 'object') {
      const statusKeys = ['attempt', 'id', 'request_id', 'status'];
      if (statusKeys.every(key => key in data)) {
        return false; // This is a status response, not Mixpanel data
      }
    }
    
    // Check for Mixpanel event structure
    if (Array.isArray(data)) {
      return data.some(item => 
        item && typeof item === 'object' && 
        (item.event || item.event_name || item.distinct_id || item.email)
      );
    }
    
    if (data && typeof data === 'object') {
      return !!(data.event || data.event_name || data.distinct_id || data.email);
    }
    
    return false;
  }

  // Helper function to search for contact by email
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

  // Helper function to process Mixpanel data and map to HubSpot properties
  function processMixpanelData(mixpanelData) {
    console.log('🔄 PROCESSING MIXPANEL DATA');
    console.log('📊 RAW DATA:', JSON.stringify(mixpanelData, null, 2));
    
    const contactUpdates = [];
    
    // Handle array of events
    if (Array.isArray(mixpanelData)) {
      mixpanelData.forEach((record, index) => {
        console.log(`📋 PROCESSING RECORD ${index + 1}:`, JSON.stringify(record, null, 2));
        
        const email = record.distinct_id || record.email || record.user_email || record.properties?.email;
        if (email) {
          const properties = {};
          
          // Map Mixpanel event data to HubSpot properties
          if (record.event || record.event_name) {
            properties.last_mixpanel_event = record.event || record.event_name;
          }
          
          if (record.time || record.event_time || record.timestamp) {
            const eventTime = new Date((record.time || record.event_time || record.timestamp) * 1000);
            properties.last_mixpanel_event_date = eventTime.toISOString();
          }
          
          // Map properties from Mixpanel event
          if (record.properties) {
            // Company information
            if (record.properties.company_name || record.properties.company) {
              properties.company = record.properties.company_name || record.properties.company;
            }
            
            // User type and role
            if (record.properties.user_type) {
              properties.user_type = record.properties.user_type;
            }
            if (record.properties.role) {
              properties.role = record.properties.role;
            }
            
            // Subscription and billing
            if (record.properties.subscription_plan || record.properties.plan) {
              properties.subscription_plan = record.properties.subscription_plan || record.properties.plan;
            }
            if (record.properties.subscription_status) {
              properties.subscription_status = record.properties.subscription_status;
            }
            
            // Feature usage
            if (record.properties.feature_usage) {
              properties.feature_usage = record.properties.feature_usage;
            }
            if (record.properties.feature_name) {
              properties.last_feature_used = record.properties.feature_name;
            }
            
            // Platform and version info
            if (record.properties.platform || record.properties.$os) {
              properties.platform = record.properties.platform || record.properties.$os;
            }
            if (record.properties.app_version || record.properties.$app_version) {
              properties.app_version = record.properties.app_version || record.properties.$app_version;
            }
            
            // Geographic data
            if (record.properties.country || record.properties.$country_code) {
              properties.country = record.properties.country || record.properties.$country_code;
            }
            if (record.properties.city || record.properties.$city) {
              properties.city = record.properties.city || record.properties.$city;
            }
            
            // Custom properties (add more as needed)
            if (record.properties.invoice_count) {
              properties.invoice_count = record.properties.invoice_count;
            }
            if (record.properties.accountant_name) {
              properties.accountant_name = record.properties.accountant_name;
            }
            if (record.properties.business_type) {
              properties.business_type = record.properties.business_type;
            }
          }
          
          // Set last webhook sync timestamp
          properties.last_mixpanel_sync = new Date().toISOString();
          
          contactUpdates.push({
            email: email,
            properties: properties
          });
        }
      });
    } 
    // Handle single event
    else if (mixpanelData && typeof mixpanelData === 'object') {
      const email = mixpanelData.distinct_id || mixpanelData.email || mixpanelData.user_email || mixpanelData.properties?.email;
      
      if (email) {
        const properties = {};
        
        // Same mapping logic as above for single event
        if (mixpanelData.event || mixpanelData.event_name) {
          properties.last_mixpanel_event = mixpanelData.event || mixpanelData.event_name;
        }
        
        if (mixpanelData.time || mixpanelData.event_time || mixpanelData.timestamp) {
          const eventTime = new Date((mixpanelData.time || mixpanelData.event_time || mixpanelData.timestamp) * 1000);
          properties.last_mixpanel_event_date = eventTime.toISOString();
        }
        
        if (mixpanelData.properties) {
          // Apply same property mapping logic
          if (mixpanelData.properties.company_name || mixpanelData.properties.company) {
            properties.company = mixpanelData.properties.company_name || mixpanelData.properties.company;
          }
          if (mixpanelData.properties.user_type) {
            properties.user_type = mixpanelData.properties.user_type;
          }
          if (mixpanelData.properties.subscription_plan || mixpanelData.properties.plan) {
            properties.subscription_plan = mixpanelData.properties.subscription_plan || mixpanelData.properties.plan;
          }
          if (mixpanelData.properties.platform || mixpanelData.properties.$os) {
            properties.platform = mixpanelData.properties.platform || mixpanelData.properties.$os;
          }
          if (mixpanelData.properties.app_version || mixpanelData.properties.$app_version) {
            properties.app_version = mixpanelData.properties.app_version || mixpanelData.properties.$app_version;
          }
          if (mixpanelData.properties.country || mixpanelData.properties.$country_code) {
            properties.country = mixpanelData.properties.country || mixpanelData.properties.$country_code;
          }
          if (mixpanelData.properties.invoice_count) {
            properties.invoice_count = mixpanelData.properties.invoice_count;
          }
          if (mixpanelData.properties.accountant_name) {
            properties.accountant_name = mixpanelData.properties.accountant_name;
          }
          if (mixpanelData.properties.business_type) {
            properties.business_type = mixpanelData.properties.business_type;
          }
        }
        
        properties.last_mixpanel_sync = new Date().toISOString();
        
        contactUpdates.push({
          email: email,
          properties: properties
        });
      }
    }
    
    console.log(`📊 PROCESSED ${contactUpdates.length} CONTACT UPDATE(S)`);
    return contactUpdates;
  }

  // Main execution logic
  try {
    console.log('='.repeat(80));
    console.log('🚀 ENHANCED MIXPANEL WEBHOOK INTEGRATION STARTED');
    console.log('='.repeat(80));
    console.log('📋 WORKFLOW INFO:');
    console.log(`   Timestamp: ${new Date().toISOString()}`);
    console.log(`   Webhook URL: ${MIXPANEL_WEBHOOK_URL}`);
    console.log('='.repeat(80));

    // Step 1: Fetch data from Mixpanel webhook
    const webhookData = await fetchMixpanelData();
    
    if (!webhookData) {
      console.log('❌ NO DATA RECEIVED FROM WEBHOOK');
      callback(null, 'No data received from webhook');
      return;
    }

    // Step 2: Check if this is actual Mixpanel data or just a status response
    if (!isMixpanelData(webhookData)) {
      console.log('ℹ️ WEBHOOK RETURNED STATUS RESPONSE, NOT MIXPANEL DATA');
      console.log('📊 This indicates the webhook is active but no Mixpanel events have been received yet');
      console.log('📋 Status Response:', JSON.stringify(webhookData, null, 2));
      
      // Update a test contact to verify the webhook integration is working
      // You can remove this section once Mixpanel data starts flowing
      try {
        const testEmail = 'test@colppy.com'; // Replace with a test contact email
        const testContact = await findContactByEmail(testEmail);
        
        if (testContact) {
          await updateContactProperties(testContact.id, {
            last_webhook_test: new Date().toISOString(),
            webhook_status: 'active_no_data'
          });
          console.log(`✅ TEST CONTACT UPDATED: ${testEmail}`);
        } else {
          console.log(`⚠️ TEST CONTACT NOT FOUND: ${testEmail}`);
        }
      } catch (testError) {
        console.log('⚠️ TEST UPDATE FAILED:', testError.message);
      }
      
      callback(null, {
        success: true,
        message: 'Webhook active but no Mixpanel data received yet',
        status: webhookData,
        dataType: 'status_response'
      });
      return;
    }

    // Step 3: Process the Mixpanel data
    const contactUpdates = processMixpanelData(webhookData);
    
    if (contactUpdates.length === 0) {
      console.log('❌ NO CONTACT UPDATES TO PROCESS');
      callback(null, 'No contact updates to process');
      return;
    }

    // Step 4: Update contacts in HubSpot
    let successCount = 0;
    let errorCount = 0;
    const results = [];

    for (const update of contactUpdates) {
      try {
        console.log(`\\n🔄 PROCESSING CONTACT UPDATE: ${update.email}`);
        
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
        } else {
          console.log(`⚠️ SKIPPING UPDATE: Contact not found for ${update.email}`);
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

    // Step 5: Log final results
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
      },
      dataType: 'mixpanel_data'
    });

  } catch (error) {
    console.error('💥 FATAL ERROR IN MIXPANEL INTEGRATION:', error.message);
    console.error('🔍 ERROR STACK:', error.stack);
    
    // Return error
    callback(error, {
      success: false,
      error: error.message,
      message: 'Failed to process Mixpanel webhook data'
    });
  }
};
'''

def main():
    """
    Main function to display the HubSpot custom code and provide usage instructions
    """
    print("HubSpot Enhanced Mixpanel Webhook Integration")
    print("=" * 60)
    print()
    print("📋 HUBSPOT CUSTOM CODE (JavaScript):")
    print("-" * 60)
    print(HUBSPOT_CUSTOM_CODE)
    print()
    print("📖 IMPLEMENTATION INSTRUCTIONS:")
    print("-" * 60)
    print("1. Copy the JavaScript code above")
    print("2. Go to HubSpot > Automation > Workflows")
    print("3. Create a new workflow or edit existing one")
    print("4. Add a 'Custom Code' action")
    print("5. Paste the code and save")
    print()
    print("🔧 CONFIGURATION:")
    print("-" * 60)
    print("- Webhook URL: https://hooks.zapier.com/hooks/catch/24538/2f03rbk/")
    print("- Access Token: Use 'ColppyCRMAutomations' environment variable")
    print("- Test Email: Update 'test@colppy.com' with your test contact email")
    print()
    print("📊 CURRENT STATUS:")
    print("-" * 60)
    print("- Webhook is active and responding")
    print("- Currently receiving status responses (no Mixpanel data yet)")
    print("- Code handles both status responses and actual Mixpanel data")
    print("- Will update contacts when Mixpanel events start flowing")
    print()
    print("🎯 FEATURES:")
    print("-" * 60)
    print("✅ Fetches data from Mixpanel webhook via Zapier")
    print("✅ Handles both single events and arrays of events")
    print("✅ Maps Mixpanel properties to HubSpot contact fields")
    print("✅ Comprehensive error handling and logging")
    print("✅ Test mode for when no Mixpanel data is available")
    print("✅ Automatic timestamp tracking")
    print()

if __name__ == "__main__":
    main()



