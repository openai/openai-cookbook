// Simple script to set contact-deal association label
// Label: "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol"
require('dotenv').config();

const hubspot = require('@hubspot/api-client');

// Configuration
const CONTACT_ID = "158555135291";
const DEAL_ID = "96744 - MAB Beauty Center"; // This looks like a deal name, we need the deal ID
const HUBSPOT_API_KEY = process.env.COLPPY_CRM_AUTOMATIONS;

async function setContactDealLabel() {
  const client = new hubspot.Client({
    accessToken: HUBSPOT_API_KEY
  });

  console.log('🔧 SETTING CONTACT-DEAL ASSOCIATION LABEL');
  console.log('='.repeat(60));
  console.log(`Contact ID: ${CONTACT_ID}`);
  console.log(`Deal: ${DEAL_ID}`);
  console.log(`API Key: ${HUBSPOT_API_KEY ? 'Present' : 'Missing'}`);
  console.log('='.repeat(60));

  try {
    // First, let's find the deal ID from the deal name
    console.log('🔍 Searching for deal by name...');
    const dealSearchResults = await client.crm.deals.searchApi.doSearch({
      filterGroups: [{
        filters: [{
          propertyName: 'dealname',
          operator: 'CONTAINS_TOKEN',
          value: 'MAB Beauty Center'
        }]
      }],
      properties: ['dealname', 'hs_object_id'],
      limit: 10
    });

    const deals = dealSearchResults.results || [];
    console.log(`Found ${deals.length} deals matching "MAB Beauty Center"`);

    if (deals.length === 0) {
      console.log('❌ No deals found with that name');
      return;
    }

    // Use the first matching deal
    const targetDeal = deals[0];
    const dealId = targetDeal.id;
    const dealName = targetDeal.properties.dealname;

    console.log(`✅ Found deal: ${dealName} (ID: ${dealId})`);

    // Check if association already exists
    console.log('🔍 Checking existing contact-deal associations...');
    const existingAssociations = await client.crm.associations.v4.basicApi.getPage(
      'contacts',
      CONTACT_ID,
      'deals',
      undefined,
      100
    );

    let targetAssociation = null;
    if (existingAssociations.results) {
      for (const assoc of existingAssociations.results) {
        if (String(assoc.toObjectId) === String(dealId)) {
          targetAssociation = assoc;
          break;
        }
      }
    }

    if (!targetAssociation) {
      console.log(`❌ No association found between Contact ${CONTACT_ID} and Deal ${dealId}`);
      console.log('Available associations:');
      if (existingAssociations.results) {
        for (const assoc of existingAssociations.results) {
          console.log(`  - Deal ID: ${assoc.toObjectId}`);
        }
      }
      return;
    }

    console.log(`✅ Association found between Contact ${CONTACT_ID} and Deal ${dealId}`);
    
    // Check existing labels
    const existingTypes = targetAssociation.associationTypes || [];
    console.log(`📊 Current labels (${existingTypes.length}):`);
    for (const assocType of existingTypes) {
      const typeId = assocType.typeId;
      const label = assocType.label || 'None';
      const category = assocType.category;
      console.log(`   - Type ID: ${typeId}, Label: '${label}', Category: ${category}`);
    }

    // Check if the target label already exists
    const targetLabel = 'Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol';
    const hasTargetLabel = existingTypes.some(type => 
      type.label && type.label.includes('Contacto Inicial que da el Alta del Negocio')
    );
    
    if (hasTargetLabel) {
      const targetType = existingTypes.find(type => 
        type.label && type.label.includes('Contacto Inicial que da el Alta del Negocio')
      );
      console.log(`✅ Label already exists: Type ID ${targetType.typeId} - "${targetType.label}"`);
      console.log('🎉 No action needed - the association already has the correct label!');
      return;
    }

    // If we reach here, the label doesn't exist and we need to add it
    console.log('🔧 The target label "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol" was not found in existing labels');
    console.log('🔧 Adding the label using Type ID 14 (USER_DEFINED)...');
    
    try {
      await client.crm.associations.v4.basicApi.create(
        'contacts',
        CONTACT_ID,
        'deals',
        dealId,
        [{
          associationCategory: 'USER_DEFINED',
          associationTypeId: 14  // Type ID for "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol"
        }]
      );

      console.log(`✅ SUCCESS: Added label "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol" to Contact ${CONTACT_ID} → Deal ${dealId}`);
    } catch (createError) {
      console.log(`❌ ERROR adding label: ${createError.message}`);
      if (createError.response) {
        console.log(`Response status: ${createError.response.status}`);
        console.log(`Response body: ${JSON.stringify(createError.response.body, null, 2)}`);
      }
      return;
    }

    // Verify the change
    console.log('🔍 Verifying the change...');
    const updatedAssociations = await client.crm.associations.v4.basicApi.getPage(
      'contacts',
      CONTACT_ID,
      'deals',
      undefined,
      100
    );

    let updatedAssociation = null;
    if (updatedAssociations.results) {
      for (const assoc of updatedAssociations.results) {
        if (String(assoc.toObjectId) === String(dealId)) {
          updatedAssociation = assoc;
          break;
        }
      }
    }

    if (updatedAssociation) {
      const updatedTypes = updatedAssociation.associationTypes || [];
      console.log(`📊 Updated labels (${updatedTypes.length}):`);
      for (const assocType of updatedTypes) {
        const typeId = assocType.typeId;
        const label = assocType.label || 'None';
        console.log(`   - Type ID: ${typeId}, Label: '${label}'`);
      }
    }

  } catch (error) {
    console.error('❌ Error:', error.message);
    if (error.response) {
      console.error('Response status:', error.response.status);
      console.error('Response body:', error.response.body);
    }
  }
}

// Run the script
setContactDealLabel().then(() => {
  console.log('🏁 Script completed');
  process.exit(0);
}).catch(error => {
  console.error('💥 Script failed:', error);
  process.exit(1);
});
