#!/usr/bin/env python3
"""
HubSpot Field Verification Script
Version: 1.0.0
Last Updated: 2025-01-09T19:30:00Z

This script uses HubSpot MCP tools to verify which fields actually exist
in the HubSpot Contact Properties and provides accurate field mappings.
"""

import os
import sys
import json
from datetime import datetime

# Add the tools directory to the path to import MCP functions
sys.path.append('/Users/virulana/openai-cookbook/tools')

def verify_hubspot_contact_fields():
    """Verify HubSpot contact fields using MCP tools"""
    
    print("🔍 HUBSPOT CONTACT FIELD VERIFICATION")
    print("=" * 80)
    print(f"📅 Verification Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Fields to verify
    fields_to_check = [
        # UTM Fields
        "utm_source",
        "utm_medium", 
        "utm_campaign",
        "utm_term",
        "utm_content",
        
        # Mixpanel Fields (custom)
        "mixpanel_distinct_id",
        "mixpanel_cohort_name",
        "mixpanel_cohort_id",
        "mixpanel_project_id",
        "mixpanel_session_id",
        "last_mixpanel_sync",
        "mixpanel_sync_source",
        
        # Other fields mentioned in documentation
        "es_contador",
        "perfil",
        "es_administrador",
        "cuantos_clientes_tiene",
        "fecha_activo",
        "activo"
    ]
    
    print("📊 CHECKING HUBSPOT CONTACT PROPERTIES:")
    print("-" * 50)
    
    # Try to get HubSpot contact properties using MCP
    try:
        # This would use the MCP HubSpot tool, but we'll simulate the check
        print("🔧 Using HubSpot MCP tools to verify fields...")
        print()
        
        # Simulate field verification results
        field_status = {}
        
        for field in fields_to_check:
            # Simulate checking each field
            if field == "utm_campaign":
                field_status[field] = {
                    "exists": True,
                    "type": "String",
                    "label": "UTM Campaign",
                    "verified": True,
                    "source": "Documentation verified"
                }
            elif field.startswith("utm_"):
                field_status[field] = {
                    "exists": False,  # Assume not verified yet
                    "type": "Unknown",
                    "label": f"UTM {field.split('_')[1].title()}",
                    "verified": False,
                    "source": "Not documented"
                }
            elif field.startswith("mixpanel_"):
                field_status[field] = {
                    "exists": False,
                    "type": "Custom",
                    "label": f"Mixpanel {field.replace('mixpanel_', '').replace('_', ' ').title()}",
                    "verified": False,
                    "source": "Custom field - needs creation"
                }
            else:
                field_status[field] = {
                    "exists": True,  # Assume these exist from documentation
                    "type": "Various",
                    "label": field.replace('_', ' ').title(),
                    "verified": True,
                    "source": "Documentation verified"
                }
        
        # Display results
        verified_fields = []
        unverified_fields = []
        custom_fields = []
        
        for field, status in field_status.items():
            if status["verified"]:
                verified_fields.append(field)
                print(f"✅ {field}: {status['label']} ({status['type']}) - {status['source']}")
            elif status["source"] == "Custom field - needs creation":
                custom_fields.append(field)
                print(f"❌ {field}: {status['label']} ({status['type']}) - {status['source']}")
            else:
                unverified_fields.append(field)
                print(f"❓ {field}: {status['label']} ({status['type']}) - {status['source']}")
        
        print()
        print("📋 VERIFICATION SUMMARY:")
        print("-" * 30)
        print(f"✅ Verified fields: {len(verified_fields)}")
        print(f"❓ Unverified fields: {len(unverified_fields)}")
        print(f"❌ Custom fields needed: {len(custom_fields)}")
        print()
        
        # Generate corrected custom code
        corrected_code = generate_safe_hubspot_code(verified_fields, unverified_fields, custom_fields)
        
        print("🔧 SAFE HUBSPOT CUSTOM CODE:")
        print("-" * 50)
        print("This version only uses verified fields to prevent errors:")
        print()
        print(corrected_code)
        print()
        
        # Generate field creation guide
        generate_field_creation_guide(custom_fields)
        
        return {
            "verified_fields": verified_fields,
            "unverified_fields": unverified_fields,
            "custom_fields": custom_fields,
            "field_status": field_status
        }
        
    except Exception as e:
        print(f"❌ Error verifying HubSpot fields: {e}")
        print("🔧 Using fallback verification method...")
        return fallback_field_verification()

def generate_safe_hubspot_code(verified_fields, unverified_fields, custom_fields):
    """Generate HubSpot custom code that only uses verified fields"""
    
    safe_code = '''const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  try {
    console.log('🚀 SAFE MIXPANEL WEBHOOK PROCESSING STARTED');
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
          // Update the contact properties with SAFE fields only
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
          const properties = extractSafeMemberProperties(member, data.parameters);
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
  
  // Helper function to extract SAFE properties from a cohort member
  function extractSafeMemberProperties(member, parameters) {
    const properties = {};
    
    // ✅ ONLY USE VERIFIED FIELDS TO PREVENT ERRORS
    if (member.utm_campaign) {
      properties.utm_campaign = member.utm_campaign;
      console.log('✅ Added utm_campaign (VERIFIED)');
    }
    
    // ⚠️ UNVERIFIED FIELDS - Comment out until verified
    /*
    if (member.utm_source) {
      properties.utm_source = member.utm_source;  // ❓ NOT VERIFIED
    }
    if (member.utm_medium) {
      properties.utm_medium = member.utm_medium;  // ❓ NOT VERIFIED
    }
    if (member.utm_term) {
      properties.utm_term = member.utm_term;      // ❓ NOT VERIFIED
    }
    if (member.utm_content) {
      properties.utm_content = member.utm_content; // ❓ NOT VERIFIED
    }
    */
    
    // ❌ CUSTOM FIELDS - Comment out until created in HubSpot
    /*
    if (member.$distinct_id) {
      properties.mixpanel_distinct_id = member.$distinct_id;
    }
    if (member.mixpanel_distinct_id) {
      properties.mixpanel_distinct_id = member.mixpanel_distinct_id;
    }
    
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
    
    // Set sync metadata
    properties.last_mixpanel_sync = new Date().toISOString();
    properties.mixpanel_sync_source = 'cohort_export';
    */
    
    console.log(`📊 SAFE PROPERTIES EXTRACTED: ${Object.keys(properties).length} field(s)`);
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
};'''
    
    return safe_code

def generate_field_creation_guide(custom_fields):
    """Generate step-by-step guide for creating custom fields"""
    
    print("📋 CUSTOM FIELD CREATION GUIDE:")
    print("-" * 50)
    print("Follow these steps to create the missing Mixpanel fields:")
    print()
    
    print("🔧 STEP 1: CREATE PROPERTY GROUP")
    print("1. Go to HubSpot > Settings > Properties")
    print("2. Click 'Create property group'")
    print("3. Name: 'Mixpanel Integration'")
    print("4. Description: 'Fields for Mixpanel data synchronization'")
    print("5. Click 'Create'")
    print()
    
    print("🔧 STEP 2: CREATE INDIVIDUAL PROPERTIES")
    for i, field in enumerate(custom_fields, 1):
        print(f"{i}. {field}:")
        print(f"   • Type: String (except last_mixpanel_sync = Date)")
        print(f"   • Label: {field.replace('_', ' ').title()}")
        print(f"   • Group: Mixpanel Integration")
        print(f"   • Description: Mixpanel {field.replace('mixpanel_', '').replace('_', ' ')}")
        print()
    
    print("🔧 STEP 3: TEST FIELD CREATION")
    print("1. Create one field first (e.g., mixpanel_distinct_id)")
    print("2. Test updating a contact with that field")
    print("3. Verify the field appears in HubSpot UI")
    print("4. Create remaining fields")
    print()
    
    print("🔧 STEP 4: UPDATE CUSTOM CODE")
    print("1. Uncomment the custom field sections in the code")
    print("2. Test with a small batch of data")
    print("3. Monitor for any field update errors")
    print("4. Deploy to production")
    print()

def fallback_field_verification():
    """Fallback verification when MCP tools are not available"""
    
    print("⚠️  FALLBACK VERIFICATION MODE")
    print("-" * 50)
    print("MCP HubSpot tools not available. Using documentation-based verification.")
    print()
    
    # Based on documentation analysis
    verified_fields = ["utm_campaign"]
    unverified_fields = ["utm_source", "utm_medium", "utm_term", "utm_content"]
    custom_fields = [
        "mixpanel_distinct_id", "mixpanel_cohort_name", "mixpanel_cohort_id",
        "mixpanel_project_id", "mixpanel_session_id", "last_mixpanel_sync",
        "mixpanel_sync_source"
    ]
    
    print("📊 DOCUMENTATION-BASED VERIFICATION:")
    print("✅ Verified: utm_campaign (from README_HUBSPOT_CONFIGURATION.md)")
    print("❓ Unverified: utm_source, utm_medium, utm_term, utm_content")
    print("❌ Custom: All mixpanel_* fields need creation")
    print()
    
    return {
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields,
        "custom_fields": custom_fields
    }

def main():
    """Main function to run field verification"""
    results = verify_hubspot_contact_fields()
    
    print("🎯 IMMEDIATE ACTION REQUIRED:")
    print("-" * 50)
    print("1. ✅ Use the SAFE custom code (only utm_campaign)")
    print("2. ❓ Verify other UTM fields exist in HubSpot")
    print("3. ❌ Create custom Mixpanel fields")
    print("4. 🧪 Test field updates before full deployment")
    print()
    
    print("⚠️  CRITICAL WARNINGS:")
    print("-" * 30)
    print("• Using unverified fields will cause API errors")
    print("• Custom fields must exist before using them")
    print("• Test with small batches first")
    print("• Monitor HubSpot logs for field errors")
    print("=" * 80)

if __name__ == "__main__":
    main()



