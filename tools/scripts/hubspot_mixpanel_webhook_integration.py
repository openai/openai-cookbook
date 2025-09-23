#!/usr/bin/env python3
"""
HubSpot Custom Code - Mixpanel Webhook Integration
Version: 1.0.0
Last Updated: 2025-01-09T15:30:00Z

This HubSpot custom code fetches data from a Mixpanel webhook via Zapier
and updates contact fields in HubSpot based on the received data.

CRITICAL REQUIREMENT FOR HUBSPOT WORKFLOWS:
------------------------------------------
HubSpot custom code MUST call the callback function to complete execution:
- On success: callback(null, 'Success');
- On error: callback(err);

Without calling the callback, the workflow will hang with no logs or errors!

WEBHOOK ENDPOINT: https://hooks.zapier.com/hooks/catch/24538/2f03rbk/
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
          'User-Agent': 'HubSpot-CustomCode/1.0'
        }
      });
      
      console.log(`📊 WEBHOOK RESPONSE STATUS: ${response.status}`);
      
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
    
    // This function maps Mixpanel data to HubSpot contact properties
    // Adjust the mapping based on your actual Mixpanel data structure
    
    const contactUpdates = [];
    
    // Example data processing - adjust based on your actual webhook data structure
    if (Array.isArray(mixpanelData)) {
      // If webhook returns an array of records
      mixpanelData.forEach((record, index) => {
        console.log(`📋 PROCESSING RECORD ${index + 1}:`, JSON.stringify(record, null, 2));
        
        if (record.email || record.user_email || record.distinct_id) {
          const email = record.email || record.user_email || record.distinct_id;
          const properties = {};
          
          // Map common Mixpanel properties to HubSpot contact properties
          // Adjust these mappings based on your actual data structure
          
          if (record.event_name) {
            properties.last_mixpanel_event = record.event_name;
          }
          
          if (record.event_time || record.timestamp) {
            const eventTime = new Date(record.event_time || record.timestamp);
            properties.last_mixpanel_event_date = eventTime.toISOString();
          }
          
          if (record.properties) {
            // Map nested properties
            if (record.properties.company_name) {
              properties.company = record.properties.company_name;
            }
            if (record.properties.user_type) {
              properties.user_type = record.properties.user_type;
            }
            if (record.properties.subscription_plan) {
              properties.subscription_plan = record.properties.subscription_plan;
            }
            if (record.properties.feature_usage) {
              properties.feature_usage = record.properties.feature_usage;
            }
          }
          
          // Add custom properties based on your Mixpanel data
          if (record.platform) {
            properties.platform = record.platform;
          }
          if (record.app_version) {
            properties.app_version = record.app_version;
          }
          
          contactUpdates.push({
            email: email,
            properties: properties
          });
        }
      });
    } else if (mixpanelData.email || mixpanelData.user_email || mixpanelData.distinct_id) {
      // If webhook returns a single record
      const email = mixpanelData.email || mixpanelData.user_email || mixpanelData.distinct_id;
      const properties = {};
      
      // Map properties for single record (same logic as above)
      if (mixpanelData.event_name) {
        properties.last_mixpanel_event = mixpanelData.event_name;
      }
      
      if (mixpanelData.event_time || mixpanelData.timestamp) {
        const eventTime = new Date(mixpanelData.event_time || mixpanelData.timestamp);
        properties.last_mixpanel_event_date = eventTime.toISOString();
      }
      
      if (mixpanelData.properties) {
        if (mixpanelData.properties.company_name) {
          properties.company = mixpanelData.properties.company_name;
        }
        if (mixpanelData.properties.user_type) {
          properties.user_type = mixpanelData.properties.user_type;
        }
        if (mixpanelData.properties.subscription_plan) {
          properties.subscription_plan = mixpanelData.properties.subscription_plan;
        }
        if (mixpanelData.properties.feature_usage) {
          properties.feature_usage = mixpanelData.properties.feature_usage;
        }
      }
      
      if (mixpanelData.platform) {
        properties.platform = mixpanelData.platform;
      }
      if (mixpanelData.app_version) {
        properties.app_version = mixpanelData.app_version;
      }
      
      contactUpdates.push({
        email: email,
        properties: properties
      });
    }
    
    console.log(`📊 PROCESSED ${contactUpdates.length} CONTACT UPDATE(S)`);
    return contactUpdates;
  }

  // Main execution logic
  try {
    console.log('='.repeat(80));
    console.log('🚀 MIXPANEL WEBHOOK INTEGRATION STARTED');
    console.log('='.repeat(80));
    console.log('📋 WORKFLOW INFO:');
    console.log(`   Timestamp: ${new Date().toISOString()}`);
    console.log(`   Webhook URL: ${MIXPANEL_WEBHOOK_URL}`);
    console.log('='.repeat(80));

    // Step 1: Fetch data from Mixpanel webhook
    const mixpanelData = await fetchMixpanelData();
    
    if (!mixpanelData) {
      console.log('❌ NO DATA RECEIVED FROM WEBHOOK');
      callback(null, 'No data received from webhook');
      return;
    }

    // Step 2: Process the data and extract contact information
    const contactUpdates = processMixpanelData(mixpanelData);
    
    if (contactUpdates.length === 0) {
      console.log('❌ NO CONTACT UPDATES TO PROCESS');
      callback(null, 'No contact updates to process');
      return;
    }

    // Step 3: Update contacts in HubSpot
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

    // Step 4: Log final results
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

# Test function to validate the webhook endpoint
def test_webhook_endpoint():
    """
    Test function to validate the webhook endpoint and understand data structure
    """
    import requests
    import json
    from datetime import datetime
    
    webhook_url = "https://hooks.zapier.com/hooks/catch/24538/2f03rbk/"
    
    print("🔗 Testing Mixpanel Webhook Endpoint")
    print("=" * 50)
    print(f"URL: {webhook_url}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    try:
        response = requests.get(webhook_url, timeout=30)
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📋 Response Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ JSON Response Received:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                
                # Analyze data structure
                print("\n🔍 Data Structure Analysis:")
                if isinstance(data, list):
                    print(f"   - Type: Array with {len(data)} items")
                    if len(data) > 0:
                        print(f"   - First item keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'Not a dict'}")
                elif isinstance(data, dict):
                    print(f"   - Type: Object with keys: {list(data.keys())}")
                else:
                    print(f"   - Type: {type(data).__name__}")
                    
            except json.JSONDecodeError:
                print("❌ Response is not valid JSON:")
                print(response.text[:500])
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(response.text[:500])
            
    except requests.exceptions.RequestException as e:
        print(f"💥 Request Error: {e}")

if __name__ == "__main__":
    print("HubSpot Mixpanel Webhook Integration")
    print("=" * 50)
    print()
    print("📋 HubSpot Custom Code (JavaScript):")
    print("-" * 50)
    print(HUBSPOT_CUSTOM_CODE)
    print()
    print("🧪 Testing Webhook Endpoint:")
    print("-" * 50)
    test_webhook_endpoint()



