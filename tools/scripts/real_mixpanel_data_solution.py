#!/usr/bin/env python3
"""
Real Mixpanel Data Access Solution
Version: 1.0.0
Last Updated: 2025-01-09T17:30:00Z

This script demonstrates how to access real Mixpanel data by working
with the actual data flow: Mixpanel → Zapier → HubSpot Custom Code
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

class RealMixpanelDataSolution:
    def __init__(self):
        self.webhook_url = "https://hooks.zapier.com/hooks/catch/24538/2f03rbk/"
        
    def demonstrate_data_flow(self):
        """Demonstrate the actual data flow and how to access real data"""
        print("🎯 REAL MIXPANEL DATA ACCESS SOLUTION")
        print("=" * 80)
        print()
        
        print("📊 CURRENT DATA FLOW ANALYSIS:")
        print("-" * 50)
        print("1. ✅ Mixpanel exports 'Registros Ultimas 24 horas' cohort")
        print("2. ✅ 197 users exported every 24 hours")
        print("3. ✅ Data sent to Zapier webhook")
        print("4. ✅ Zapier processes the data")
        print("5. ✅ Webhook returns status confirmation")
        print("6. ❌ Raw data not accessible via webhook endpoint")
        print()
        
        print("🔍 WHY WEBHOOK ONLY SHOWS STATUS:")
        print("-" * 50)
        print("• Zapier webhooks are designed to 'catch' data, not 'store' it")
        print("• The webhook confirms data was received and processed")
        print("• Actual user data is processed by Zapier and sent to configured destinations")
        print("• This is the correct behavior for webhook integrations")
        print()
        
        print("💡 HOW TO ACCESS REAL MIXPANEL DATA:")
        print("-" * 50)
        print("Option 1: Configure Zapier to send data to HubSpot workflow")
        print("Option 2: Use HubSpot custom code to process incoming data")
        print("Option 3: Access Mixpanel data directly via their API")
        print("Option 4: Configure Zapier to send data to a database/webhook")
        print()
        
        return self.create_hubspot_solution()
    
    def create_hubspot_solution(self):
        """Create the complete HubSpot custom code solution"""
        print("🚀 HUBSPOT CUSTOM CODE SOLUTION")
        print("=" * 80)
        print()
        
        hubspot_code = '''
const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  try {
    console.log('🚀 MIXPANEL DATA PROCESSING STARTED');
    console.log('📋 Event Data:', JSON.stringify(event, null, 2));
    
    // Extract data from the event (this comes from Zapier)
    const mixpanelData = event.inputFields || event.object || event;
    
    console.log('📊 MIXPANEL DATA RECEIVED:', JSON.stringify(mixpanelData, null, 2));
    
    // Process the data based on its structure
    const contactUpdates = processMixpanelData(mixpanelData);
    
    if (contactUpdates.length === 0) {
      console.log('❌ NO CONTACT UPDATES TO PROCESS');
      callback(null, 'No contact updates to process');
      return;
    }
    
    // Update contacts in HubSpot
    let successCount = 0;
    let errorCount = 0;
    const results = [];
    
    for (const update of contactUpdates) {
      try {
        console.log(`🔄 PROCESSING CONTACT: ${update.email}`);
        
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
    
    console.log(`✅ SUCCESS: ${successCount} contacts updated`);
    console.log(`❌ ERRORS: ${errorCount} contacts failed`);
    
    callback(null, {
      success: true,
      message: `Processed ${contactUpdates.length} records: ${successCount} updated, ${errorCount} errors`,
      results: results
    });
    
  } catch (error) {
    console.error('💥 FATAL ERROR:', error.message);
    callback(error, {
      success: false,
      error: error.message
    });
  }
  
  // Helper function to process Mixpanel data
  function processMixpanelData(data) {
    const contactUpdates = [];
    
    // Handle different data structures from Zapier
    if (Array.isArray(data)) {
      // Array of user records
      data.forEach(record => {
        const email = record.email || record.distinct_id || record.properties?.email;
        if (email) {
          contactUpdates.push({
            email: email,
            properties: extractProperties(record)
          });
        }
      });
    } else if (data && typeof data === 'object') {
      // Single user record or nested structure
      if (data.email || data.distinct_id) {
        contactUpdates.push({
          email: data.email || data.distinct_id,
          properties: extractProperties(data)
        });
      } else if (data.users && Array.isArray(data.users)) {
        // Nested users array
        data.users.forEach(user => {
          const email = user.email || user.distinct_id || user.properties?.email;
          if (email) {
            contactUpdates.push({
              email: email,
              properties: extractProperties(user)
            });
          }
        });
      }
    }
    
    return contactUpdates;
  }
  
  // Helper function to extract properties
  function extractProperties(record) {
    const properties = {};
    
    // Event information
    if (record.event || record.event_name) {
      properties.last_mixpanel_event = record.event || record.event_name;
    }
    
    if (record.time || record.event_time || record.timestamp) {
      const timestamp = record.time || record.event_time || record.timestamp;
      const eventTime = new Date(timestamp * 1000);
      properties.last_mixpanel_event_date = eventTime.toISOString();
    }
    
    // User properties
    if (record.properties) {
      const props = record.properties;
      
      // Company information
      if (props.company_name || props.company) {
        properties.company = props.company_name || props.company;
      }
      
      // User type and role
      if (props.user_type) properties.user_type = props.user_type;
      if (props.role) properties.role = props.role;
      
      // Subscription and billing
      if (props.subscription_plan || props.plan) {
        properties.subscription_plan = props.subscription_plan || props.plan;
      }
      if (props.subscription_status) {
        properties.subscription_status = props.subscription_status;
      }
      
      // Feature usage
      if (props.feature_usage) properties.feature_usage = props.feature_usage;
      if (props.feature_name) properties.last_feature_used = props.feature_name;
      
      // Platform and version
      if (props.platform || props.$os) {
        properties.platform = props.platform || props.$os;
      }
      if (props.app_version || props.$app_version) {
        properties.app_version = props.app_version || props.$app_version;
      }
      
      // Geographic data
      if (props.country || props.$country_code) {
        properties.country = props.country || props.$country_code;
      }
      if (props.city || props.$city) {
        properties.city = props.city || props.$city;
      }
      
      // Colppy-specific properties
      if (props.invoice_count) properties.invoice_count = props.invoice_count;
      if (props.accountant_name) properties.accountant_name = props.accountant_name;
      if (props.business_type) properties.business_type = props.business_type;
      
      // Additional Mixpanel properties
      if (props.$browser) properties.browser = props.$browser;
      if (props.$referrer) properties.referrer = props.$referrer;
    }
    
    // Set sync timestamp
    properties.last_mixpanel_sync = new Date().toISOString();
    
    return properties;
  }
  
  // Helper function to find contact by email
  async function findContactByEmail(email) {
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
      
      if (searchResponse.total > 0) {
        return searchResponse.results[0];
      }
      
      return null;
    } catch (error) {
      console.error(`Contact search error for ${email}:`, error.message);
      throw error;
    }
  }
  
  // Helper function to update contact properties
  async function updateContactProperties(contactId, properties) {
    try {
      const updateRequest = { properties: properties };
      const updateResponse = await client.crm.contacts.basicApi.update(contactId, updateRequest);
      return updateResponse;
    } catch (error) {
      console.error(`Contact update error for ID ${contactId}:`, error.message);
      throw error;
    }
  }
};
'''
        
        print("📋 HUBSPOT CUSTOM CODE (JavaScript):")
        print("-" * 50)
        print(hubspot_code)
        print()
        
        return self.create_zapier_configuration()
    
    def create_zapier_configuration(self):
        """Create Zapier configuration instructions"""
        print("🔧 ZAPIER CONFIGURATION INSTRUCTIONS")
        print("=" * 80)
        print()
        
        print("📋 STEP-BY-STEP ZAPIER SETUP:")
        print("-" * 50)
        print("1. Go to Zapier.com and open your 'Colppy Zapier Demand Gen' Zap")
        print("2. Edit the Zap to add a new action:")
        print("   • Action: 'HubSpot'")
        print("   • Event: 'Create or Update Contact'")
        print("   • Or: 'Trigger HubSpot Workflow'")
        print()
        print("3. Configure the HubSpot action:")
        print("   • Connect your HubSpot account")
        print("   • Select the workflow with the custom code")
        print("   • Map Mixpanel data fields to HubSpot properties")
        print()
        print("4. Test the Zap to ensure data flows correctly")
        print("5. Turn on the Zap to start processing real data")
        print()
        
        print("📊 EXPECTED DATA STRUCTURE FROM MIXPANEL:")
        print("-" * 50)
        print("The Zapier webhook will receive data in this format:")
        print()
        sample_data = {
            "users": [
                {
                    "distinct_id": "user@example.com",
                    "properties": {
                        "company_name": "Example Company",
                        "user_type": "accountant",
                        "subscription_plan": "premium",
                        "platform": "web",
                        "app_version": "2.1.0",
                        "country": "AR",
                        "invoice_count": 150,
                        "accountant_name": "Juan Ignacio Onetto",
                        "business_type": "SMB"
                    }
                }
            ]
        }
        print(json.dumps(sample_data, indent=2, ensure_ascii=False))
        print()
        
        print("🎯 PROPERTY MAPPING:")
        print("-" * 50)
        mappings = [
            "distinct_id → email (contact identifier)",
            "properties.company_name → company",
            "properties.user_type → user_type", 
            "properties.subscription_plan → subscription_plan",
            "properties.platform → platform",
            "properties.app_version → app_version",
            "properties.country → country",
            "properties.invoice_count → invoice_count",
            "properties.accountant_name → accountant_name",
            "properties.business_type → business_type"
        ]
        for mapping in mappings:
            print(f"• {mapping}")
        print()
        
        return self.create_testing_instructions()
    
    def create_testing_instructions(self):
        """Create testing and monitoring instructions"""
        print("🧪 TESTING AND MONITORING INSTRUCTIONS")
        print("=" * 80)
        print()
        
        print("📋 TESTING STEPS:")
        print("-" * 50)
        print("1. Deploy the HubSpot custom code in a workflow")
        print("2. Configure Zapier to send data to the workflow")
        print("3. Trigger a test export from Mixpanel")
        print("4. Monitor HubSpot workflow logs for processing")
        print("5. Check contact properties for updates")
        print()
        
        print("📊 MONITORING CHECKLIST:")
        print("-" * 50)
        print("✅ Mixpanel cohort export runs every 24 hours")
        print("✅ Zapier processes the data successfully")
        print("✅ HubSpot workflow receives and processes data")
        print("✅ Contact properties are updated correctly")
        print("✅ Error handling works for missing contacts")
        print()
        
        print("🔍 TROUBLESHOOTING:")
        print("-" * 50)
        print("• Check Zapier Zap logs for data flow issues")
        print("• Monitor HubSpot workflow execution logs")
        print("• Verify contact email addresses match Mixpanel data")
        print("• Ensure HubSpot custom properties exist")
        print("• Test with a small subset of data first")
        print()
        
        return {
            'status': 'solution_complete',
            'message': 'Complete solution provided for accessing real Mixpanel data',
            'components': [
                'HubSpot Custom Code',
                'Zapier Configuration',
                'Testing Instructions',
                'Monitoring Guidelines'
            ]
        }

def main():
    """Main function to demonstrate the complete solution"""
    print("🎯 REAL MIXPANEL DATA ACCESS SOLUTION")
    print("=" * 80)
    print()
    
    solution = RealMixpanelDataSolution()
    result = solution.demonstrate_data_flow()
    
    print("=" * 80)
    print("✅ SOLUTION COMPLETE")
    print("=" * 80)
    print("You now have everything needed to access real Mixpanel data:")
    print("• Complete HubSpot custom code")
    print("• Zapier configuration instructions") 
    print("• Testing and monitoring guidelines")
    print("• Property mapping specifications")
    print()
    print("Next steps:")
    print("1. Deploy the HubSpot custom code")
    print("2. Configure Zapier to send data to HubSpot")
    print("3. Test with real Mixpanel data")
    print("4. Monitor the integration")
    print("=" * 80)

if __name__ == "__main__":
    main()



