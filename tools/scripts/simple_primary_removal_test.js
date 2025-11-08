// Simple HubSpot Custom Code - Test PRIMARY Removal
// Copy this to HubSpot Custom Code for easy debugging

const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  const DEAL_ID = "44653784974";
  const CUSTOMER_COMPANY_ID = "38965107090";

  console.log('🧪 SIMPLE PRIMARY REMOVAL TEST');
  console.log(`Deal: ${DEAL_ID}, Company: ${CUSTOMER_COMPANY_ID}`);

  try {
    // Step 1: Check current state
    console.log('\n📊 CURRENT STATE:');
    const currentAssociations = await client.crm.associations.v4.basicApi.getPage(
      'deals', DEAL_ID, 'companies', undefined, 100
    );
    
    const customerAssoc = currentAssociations.results?.find(a => a.toObjectId === CUSTOMER_COMPANY_ID);
    if (customerAssoc) {
      console.log('Found customer association:');
      customerAssoc.associationTypes?.forEach(t => {
        console.log(`  - Type ${t.typeId}: ${t.label || 'No label'}`);
      });
    } else {
      console.log('No customer association found');
    }

    // Step 2: Try to remove PRIMARY only
    console.log('\n🔧 REMOVING PRIMARY:');
    
    // Method 1: Try v4 batch archive
    try {
      const batchInput = [{
        from: { id: DEAL_ID },
        to: { id: CUSTOMER_COMPANY_ID },
        types: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 5 }]
      }];
      
      const response = await fetch(`https://api.hubspot.com/crm/v4/objects/deals/${DEAL_ID}/associations/companies/batch/archive`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ inputs: batchInput })
      });
      
      console.log(`V4 Batch Archive: ${response.status} - ${response.ok ? 'SUCCESS' : 'FAILED'}`);
      if (!response.ok) {
        console.log(`Error: ${await response.text()}`);
      }
    } catch (e) {
      console.log(`V4 Batch Archive Error: ${e.message}`);
    }

    // Method 2: Try v3 batch archive
    try {
      const batchInput = [{
        from: { id: DEAL_ID },
        to: { id: CUSTOMER_COMPANY_ID },
        types: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 5 }]
      }];
      
      const response = await fetch(`https://api.hubspot.com/crm/v3/objects/deals/${DEAL_ID}/associations/companies/batch/archive`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ inputs: batchInput })
      });
      
      console.log(`V3 Batch Archive: ${response.status} - ${response.ok ? 'SUCCESS' : 'FAILED'}`);
      if (!response.ok) {
        console.log(`Error: ${await response.text()}`);
      }
    } catch (e) {
      console.log(`V3 Batch Archive Error: ${e.message}`);
    }

    // Step 3: Check final state
    console.log('\n📊 FINAL STATE:');
    const finalAssociations = await client.crm.associations.v4.basicApi.getPage(
      'deals', DEAL_ID, 'companies', undefined, 100
    );
    
    const finalCustomerAssoc = finalAssociations.results?.find(a => a.toObjectId === CUSTOMER_COMPANY_ID);
    if (finalCustomerAssoc) {
      console.log('Final customer association:');
      finalCustomerAssoc.associationTypes?.forEach(t => {
        console.log(`  - Type ${t.typeId}: ${t.label || 'No label'}`);
      });
      
      const hasPrimary = finalCustomerAssoc.associationTypes?.some(t => t.typeId === 5);
      console.log(`PRIMARY still exists: ${hasPrimary ? 'YES' : 'NO'}`);
    } else {
      console.log('No customer association found (removed entirely)');
    }

    console.log('\n✅ TEST COMPLETE');
    callback(null, 'Success');

  } catch (error) {
    console.error('❌ ERROR:', error.message);
    callback(error);
  }
};







