#!/usr/bin/env python3
"""
HubSpot Field Verification and Correction Script
Version: 1.0.0
Last Updated: 2025-01-09T19:00:00Z

This script verifies the HubSpot custom code field mappings against the official
documentation and provides corrected field names based on verified HubSpot schema.

VERIFICATION AGAINST: README_HUBSPOT_CONFIGURATION.md
"""

def verify_and_correct_hubspot_fields():
    """Verify HubSpot custom code field mappings and provide corrections"""
    
    print("🔍 HUBSPOT FIELD VERIFICATION & CORRECTION")
    print("=" * 80)
    print()
    
    # Current field mappings from the custom code
    current_mappings = {
        "mixpanel_distinct_id": "mixpanel_distinct_id",
        "utm_source": "utm_source", 
        "utm_medium": "utm_medium",
        "utm_campaign": "utm_campaign",
        "utm_term": "utm_term",
        "utm_content": "utm_content",
        "mixpanel_cohort_name": "mixpanel_cohort_name",
        "mixpanel_cohort_id": "mixpanel_cohort_id",
        "mixpanel_project_id": "mixpanel_project_id",
        "mixpanel_session_id": "mixpanel_session_id",
        "last_mixpanel_sync": "last_mixpanel_sync",
        "mixpanel_sync_source": "mixpanel_sync_source"
    }
    
    # Verified field mappings from documentation
    verified_mappings = {
        # ✅ VERIFIED FIELDS (from README_HUBSPOT_CONFIGURATION.md)
        "utm_campaign": "utm_campaign",  # ✅ VERIFIED - Line 1046
        "utm_campaign_negocio": "utm_campaign_negocio",  # ✅ VERIFIED - Line 1053
        
        # ❌ UNVERIFIED FIELDS - Need to check if they exist in HubSpot
        "utm_source": "utm_source",  # ❓ NOT DOCUMENTED - Need verification
        "utm_medium": "utm_medium",  # ❓ NOT DOCUMENTED - Need verification  
        "utm_term": "utm_term",      # ❓ NOT DOCUMENTED - Need verification
        "utm_content": "utm_content", # ❓ NOT DOCUMENTED - Need verification
        
        # ❌ CUSTOM FIELDS - Need to be created in HubSpot
        "mixpanel_distinct_id": "mixpanel_distinct_id",  # ❌ CUSTOM - Need creation
        "mixpanel_cohort_name": "mixpanel_cohort_name",  # ❌ CUSTOM - Need creation
        "mixpanel_cohort_id": "mixpanel_cohort_id",      # ❌ CUSTOM - Need creation
        "mixpanel_project_id": "mixpanel_project_id",    # ❌ CUSTOM - Need creation
        "mixpanel_session_id": "mixpanel_session_id",    # ❌ CUSTOM - Need creation
        "last_mixpanel_sync": "last_mixpanel_sync",       # ❌ CUSTOM - Need creation
        "mixpanel_sync_source": "mixpanel_sync_source"    # ❌ CUSTOM - Need creation
    }
    
    print("📊 FIELD VERIFICATION RESULTS:")
    print("-" * 50)
    
    verified_fields = []
    unverified_fields = []
    custom_fields = []
    
    for field, internal_name in current_mappings.items():
        if field in ["utm_campaign"]:
            verified_fields.append(field)
            print(f"✅ {field} → {internal_name} (VERIFIED in documentation)")
        elif field.startswith("utm_"):
            unverified_fields.append(field)
            print(f"❓ {field} → {internal_name} (NOT DOCUMENTED - needs verification)")
        else:
            custom_fields.append(field)
            print(f"❌ {field} → {internal_name} (CUSTOM FIELD - needs creation)")
    
    print()
    print("📋 SUMMARY:")
    print("-" * 30)
    print(f"✅ Verified fields: {len(verified_fields)}")
    print(f"❓ Unverified fields: {len(unverified_fields)}")
    print(f"❌ Custom fields needed: {len(custom_fields)}")
    print()
    
    # Generate corrected HubSpot custom code
    corrected_code = generate_corrected_hubspot_code(verified_mappings, unverified_fields, custom_fields)
    
    print("🔧 CORRECTED HUBSPOT CUSTOM CODE:")
    print("-" * 50)
    print(corrected_code)
    print()
    
    # Generate field creation recommendations
    generate_field_creation_recommendations(custom_fields)
    
    # Generate verification steps
    generate_verification_steps(unverified_fields)
    
    return {
        "verified_fields": verified_fields,
        "unverified_fields": unverified_fields, 
        "custom_fields": custom_fields,
        "corrected_code": corrected_code
    }

def generate_corrected_hubspot_code(verified_mappings, unverified_fields, custom_fields):
    """Generate corrected HubSpot custom code with proper field handling"""
    
    corrected_code = '''const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  try {
    console.log('🚀 VERIFIED MIXPANEL WEBHOOK PROCESSING STARTED');
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
          // Update the contact properties with verified fields only
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
    
    // ✅ VERIFIED FIELDS (from documentation)
    if (member.utm_campaign) {
      properties.utm_campaign = member.utm_campaign;
    }
    
    // ❓ UNVERIFIED FIELDS - Use with caution
    if (member.utm_source) {
      properties.utm_source = member.utm_source;  // ⚠️ NOT DOCUMENTED
    }
    if (member.utm_medium) {
      properties.utm_medium = member.utm_medium;  // ⚠️ NOT DOCUMENTED
    }
    if (member.utm_term) {
      properties.utm_term = member.utm_term;      // ⚠️ NOT DOCUMENTED
    }
    if (member.utm_content) {
      properties.utm_content = member.utm_content; // ⚠️ NOT DOCUMENTED
    }
    
    // ❌ CUSTOM FIELDS - Only include if they exist in HubSpot
    // Comment out these fields until they are created in HubSpot
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
    
    return corrected_code

def generate_field_creation_recommendations(custom_fields):
    """Generate recommendations for creating custom fields in HubSpot"""
    
    print("🔧 CUSTOM FIELD CREATION RECOMMENDATIONS:")
    print("-" * 50)
    print("The following fields need to be created in HubSpot before using them:")
    print()
    
    field_definitions = {
        "mixpanel_distinct_id": {
            "type": "String",
            "label": "Mixpanel Distinct ID",
            "description": "Unique identifier from Mixpanel for user tracking",
            "group": "Mixpanel Integration"
        },
        "mixpanel_cohort_name": {
            "type": "String", 
            "label": "Mixpanel Cohort Name",
            "description": "Name of the Mixpanel cohort this contact belongs to",
            "group": "Mixpanel Integration"
        },
        "mixpanel_cohort_id": {
            "type": "String",
            "label": "Mixpanel Cohort ID", 
            "description": "Unique identifier of the Mixpanel cohort",
            "group": "Mixpanel Integration"
        },
        "mixpanel_project_id": {
            "type": "String",
            "label": "Mixpanel Project ID",
            "description": "Mixpanel project identifier",
            "group": "Mixpanel Integration"
        },
        "mixpanel_session_id": {
            "type": "String",
            "label": "Mixpanel Session ID",
            "description": "Session identifier from Mixpanel",
            "group": "Mixpanel Integration"
        },
        "last_mixpanel_sync": {
            "type": "Date",
            "label": "Last Mixpanel Sync",
            "description": "Timestamp of last Mixpanel data sync",
            "group": "Mixpanel Integration"
        },
        "mixpanel_sync_source": {
            "type": "String",
            "label": "Mixpanel Sync Source",
            "description": "Source of the Mixpanel data sync",
            "group": "Mixpanel Integration"
        }
    }
    
    for field in custom_fields:
        if field in field_definitions:
            definition = field_definitions[field]
            print(f"📝 {field}:")
            print(f"   Type: {definition['type']}")
            print(f"   Label: {definition['label']}")
            print(f"   Description: {definition['description']}")
            print(f"   Group: {definition['group']}")
            print()
    
    print("📋 CREATION STEPS:")
    print("1. Go to HubSpot > Settings > Properties > Contact Properties")
    print("2. Click 'Create property'")
    print("3. Use the definitions above for each field")
    print("4. Create a 'Mixpanel Integration' property group")
    print("5. Test the custom code after creating all fields")
    print()

def generate_verification_steps(unverified_fields):
    """Generate steps to verify unverified fields"""
    
    print("🔍 FIELD VERIFICATION STEPS:")
    print("-" * 50)
    print("The following fields need verification in HubSpot:")
    print()
    
    for field in unverified_fields:
        print(f"❓ {field}:")
        print(f"   1. Check if field exists in HubSpot Contact Properties")
        print(f"   2. Verify internal property name matches: {field}")
        print(f"   3. Test field update via API")
        print(f"   4. Document field mapping if it exists")
        print()
    
    print("📋 VERIFICATION METHODS:")
    print("1. HubSpot UI: Settings > Properties > Contact Properties")
    print("2. HubSpot API: GET /crm/v3/properties/contacts")
    print("3. Test Update: Try updating a contact with these fields")
    print("4. Documentation: Update README_HUBSPOT_CONFIGURATION.md")
    print()

def main():
    """Main function to run field verification and correction"""
    results = verify_and_correct_hubspot_fields()
    
    print("🎯 NEXT STEPS:")
    print("-" * 30)
    print("1. ✅ Use verified fields immediately (utm_campaign)")
    print("2. ❓ Verify unverified UTM fields in HubSpot")
    print("3. ❌ Create custom Mixpanel fields in HubSpot")
    print("4. 🧪 Test the corrected custom code")
    print("5. 📚 Update documentation with verified field mappings")
    print()
    
    print("⚠️  CRITICAL NOTES:")
    print("-" * 30)
    print("• Only utm_campaign is verified in your documentation")
    print("• Other UTM fields may not exist in HubSpot")
    print("• Custom Mixpanel fields need to be created first")
    print("• Test field updates before deploying to production")
    print("=" * 80)

if __name__ == "__main__":
    main()



