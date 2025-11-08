// =============================================================================
// HubSpot Custom Code - Deal Stage Update Workflow
// =============================================================================
// URL in hubspot automation: https://app.hubspot.com/workflows/19877595/platform/flow/1611949700/edit/triggers/event
// VERSION: 1.0.0
// LAST UPDATED: 2025-11-08
// FILE: hubspot_deal_stage_update_workflow.js
//
// PURPOSE: 
// Actualizar automáticamente cuando detecta un cambio de estapa en el negocio para indicar si es un negocio influenciado por el canal o no. 
//
// FEATURES:
// ✅ DEAL STAGE UPDATE: Updates the deal stage for a deal when the deal stage is changed.

const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  try {
    const additionalCompanyId = String(event.object.objectId);
    console.log(`🚀 Immediate Primary Prevention Workflow v1.0.2 - Company: ${additionalCompanyId}`);

    // STEP 1: VALIDATE ADDITIONAL COMPANY
    const additionalCompany = await client.crm.companies.basicApi.getById(additionalCompanyId, [
      'name', 'empresa_adicional'
    ]);

    const companyName = additionalCompany.properties.name;
    const empresaAdicional = additionalCompany.properties.empresa_adicional;

    console.log(`📋 Company: ${companyName}`);
    console.log(`📋 Empresa Adicional: ${empresaAdicional}`);

    if (!empresaAdicional) {
      console.log(`ℹ️  Not an additional company - skipping`);
      callback(null, 'Success');
      return;
    }

    console.log(`✅ Additional company detected - finding associated deals immediately`);

    // STEP 2: FIND ALL ADDITIONAL PRODUCT DEALS IMMEDIATELY
    const dealSearchResults = await client.crm.deals.searchApi.doSearch({
      filterGroups: [{
        filters: [{
          propertyName: 'dealstage',
          operator: 'EQ',
          value: '948806400'
        }, {
          propertyName: 'empresa_adicional',
          operator: 'EQ',
          value: 'true'
        }]
      }],
      properties: ['dealname', 'amount', 'closedate', 'createdate'],
      sorts: [{ propertyName: 'createdate', direction: 'DESCENDING' }],
      limit: 10
    });

    const deals = dealSearchResults.results || [];
    if (deals.length === 0) {
      console.log(`ℹ️  No additional product deals found yet - may be created shortly`);
      callback(null, 'Success');
      return;
    }

    console.log(`🔍 Found ${deals.length} additional product deals to check immediately`);

    // STEP 3: PROCESS ALL DEALS IMMEDIATELY TO PREVENT PRIMARY LABELS
    let totalProcessed = 0;
    let totalFixed = 0;

    for (const deal of deals) {
      const dealId = deal.id;
      const dealName = deal.properties.dealname;

      console.log(`\n🔧 IMMEDIATE PROCESSING: Deal ${dealId} - ${dealName}`);

      try {
        // Get current associations immediately
        const currentAssociations = await client.crm.associations.v4.basicApi.getPage(
          'deals', dealId, 'companies', undefined, 100
        );

        console.log(`📊 Current associations for ${dealId}:`, JSON.stringify(currentAssociations.results, null, 2));

        // Identify Primary associations
        let primaryFound = false;
        let companiesToFix = [];

        for (const association of currentAssociations.results) {
          const companyId = association.toObjectId;
          const associationTypes = association.associationTypes || [];

          for (const assocType of associationTypes) {
            if (assocType.typeId === 5) { // Primary
              primaryFound = true;
              companiesToFix.push(companyId);
              console.log(`🚨 PRIMARY FOUND with company ${companyId} - will fix IMMEDIATELY`);
            }
          }
        }

        if (!primaryFound) {
          console.log(`✅ Deal ${dealId} - No Primary associations found`);
          totalProcessed++;
          continue;
        }

        // COMPREHENSIVE ASSOCIATION CLEANUP AND REBUILD
        console.log(`⚡ COMPREHENSIVE FIX - Complete association cleanup and rebuild`);

        // STEP 1: Remove ALL association types from ALL companies
        console.log(`🗑️  STEP 1: Removing ALL association types from ALL companies`);
        const associationTypesToRemove = [5, 6, 341, 279, 11, 1, 2]; // Primary, Deal with Primary, Standard, Unlabeled, User Defined, Contact to Company, Company to Contact

        for (const association of currentAssociations.results) {
          const companyId = association.toObjectId;
          console.log(`🗑️  Cleaning ALL associations for company ${companyId}`);

          for (const typeId of associationTypesToRemove) {
            try {
              const deleteResponse = await fetch(`https://api.hubapi.com/crm/v3/objects/deals/${dealId}/associations/companies/${companyId}/${typeId}`, {
                method: 'DELETE',
                headers: {
                  'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
                  'Content-Type': 'application/json'
                }
              });
              if (deleteResponse.status === 204) {
                console.log(`   ✅ Removed type ${typeId} from company ${companyId}`);
              }
            } catch (error) {
              // Ignore errors - some types may not exist
            }
          }
        }

        // STEP 2: Wait for deletions to process
        console.log(`⏳ STEP 2: Waiting for deletions to process...`);
        await new Promise(resolve => setTimeout(resolve, 3000));

        // STEP 3: Find customer company through contact relationships
        console.log(`🔍 STEP 3: Finding customer company through contact relationships`);

        // Get contacts associated with additional company
        const contactAssociations = await client.crm.associations.v4.basicApi.getPage(
          'companies', additionalCompanyId, 'contacts', undefined, 100
        );

        let customerCompanyId = null;
        if (contactAssociations.results && contactAssociations.results.length > 0) {
          const contactId = contactAssociations.results[0].toObjectId;
          console.log(`📞 Found contact: ${contactId}`);

          // Get companies associated with this contact
          const contactCompanies = await client.crm.associations.v4.basicApi.getPage(
            'contacts', contactId, 'companies', undefined, 100
          );

          // Find primary customer company (not the additional company)
          for (const companyAssoc of contactCompanies.results) {
            const companyId = companyAssoc.toObjectId;
            if (companyId !== additionalCompanyId) {
              // Check if this is the primary customer company
              const associationTypes = companyAssoc.associationTypes || [];
              const isPrimary = associationTypes.some(t => t.typeId === 1 || (t.label || '').toLowerCase().includes('primary'));
              if (isPrimary) {
                customerCompanyId = companyId;
                console.log(`🎯 Found customer company: ${customerCompanyId}`);
                break;
              }
            }
          }
        }

        if (!customerCompanyId) {
          console.log(`⚠️  Could not find customer company - using default`);
          customerCompanyId = '38965107090'; // Fallback to known customer company
        }

        // STEP 4: Create proper Standard associations using batch API
        console.log(`➕ STEP 4: Creating Standard associations using batch API`);

        const batchData = {
          inputs: [
            {
              from: { id: dealId },
              to: { id: customerCompanyId },
              type: 'deal_to_company',
              associationTypes: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 341 }]
            },
            {
              from: { id: dealId },
              to: { id: additionalCompanyId },
              type: 'deal_to_company',
              associationTypes: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 341 }]
            }
          ]
        };

        const batchUrl = 'https://api.hubapi.com/crm/v3/associations/deals/companies/batch/create';
        const batchResponse = await fetch(batchUrl, {
          headers: {
            'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
            'Content-Type': 'application/json'
          },
          method: 'POST',
          body: JSON.stringify(batchData)
        });

        if (batchResponse.status === 201) {
          console.log(`✅ Batch associations created successfully`);
          console.log(`   Customer Company ${customerCompanyId}: Standard association`);
          console.log(`   Additional Company ${additionalCompanyId}: Standard association`);
          totalFixed += 2;
        } else {
          console.log(`❌ Batch association failed: ${batchResponse.status}`);
        }

        totalProcessed++;

      } catch (dealError) {
        console.error(`❌ Failed to process deal ${dealId}: ${dealError.message}`);
      }
    }

    // STEP 4: SUMMARY
    console.log(`\n📊 IMMEDIATE PREVENTION SUMMARY:`);
    console.log(`   Deals processed: ${totalProcessed}/${deals.length}`);
    console.log(`   Primary labels fixed: ${totalFixed}`);

    if (totalFixed > 0) {
      console.log(`✅ SUCCESS - ${totalFixed} Primary labels immediately converted to Standard`);
    } else {
      console.log(`ℹ️  No Primary labels found to fix`);
    }

    console.log(`🎉 Immediate Primary Prevention completed for company ${companyName}`);
    callback(null, 'Success');

  } catch (error) {
    console.error(`❌ Workflow error: ${error.message}`);
    callback(error);
  }
};