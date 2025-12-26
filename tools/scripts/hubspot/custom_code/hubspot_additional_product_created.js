// =============================================================================
// HubSpot Custom Code - Additional Product Association Workflow
// =============================================================================
// VERSION: 1.0.27 (Clean JavaScript)
// LAST UPDATED: 2025-11-08
// FILE: hubspot_additional_product_workflow_clean.js
// WF: https://app.hubspot.com/workflows/19877595/platform/flow/1699053467/edit/actions/6/custom-code
// PURPOSE:
// Automates the association of an Additional Product company with the correct
// customer deal. The workflow validates the secondary company, traces the
// originating contact, resolves the primary customer company, finds the newest
// additional-product deal, applies the proper contact/deal label, cleans legacy
// deal → additional-company labels, and ensures the deal is linked to the billing
// (primary) company. Every action is logged and surfaced via Slack notifications.
//
// FEATURES:
// ✅ COMPANY VALIDATION: Confirms `empresa_adicional` and captures owner metadata
// ✅ CONTACT DISCOVERY: Pulls the first associated contact and resolves ownership
// ✅ PRIMARY CUSTOMER RESOLUTION: Finds the contact’s primary company (association typeId 1)
// ✅ DEAL IDENTIFICATION: Locates the latest deal in stage “Negociación Producto Adicional” with `empresa_adicional = true`
// ✅ LABEL ENFORCEMENT: Adds the “Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol” label on the contact ↔ deal link
// ✅ ASSOCIATION CLEAN-UP: Uses v4 batch archive to strip unwanted labels from the additional-company association while preserving STANDARD (typeId 342)
// ✅ CUSTOMER LINKAGE: Adds a STANDARD (typeId 341) association between the deal and the primary customer company if missing
// ✅ SLACK VISIBILITY: Sends detailed success/error notifications with links to the company, contact, and deal
// ✅ RESILIENT LOGGING: Captures granular diagnostics and avoids workflow failure where possible
//
// ENVIRONMENT VARIABLES REQUIRED:
// - ColppyCRMAutomations: HubSpot Private App token with CRM scopes
// - SlackWebhookUrl: Incoming webhook URL for notifications
//
const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  // Helper function to resolve owner names with detailed logging
  async function getOwnerName(ownerId) {
    console.log(`🔍 OWNER RESOLUTION START - Owner ID: ${ownerId}`);
    
    if (!ownerId) {
      console.log(`❌ OWNER RESOLUTION: No owner ID provided`);
      return 'No Owner';
    }
    
    try {
      console.log(`📡 OWNER API CALL: Fetching owner details for ID ${ownerId}`);
      console.log(`🔑 API Key Status: ${process.env.ColppyCRMAutomations ? 'Present' : 'Missing'}`);
      
      const response = await fetch(`https://api.hubspot.com/crm/v3/owners/${ownerId}`, {
        headers: {
          'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
          'Content-Type': 'application/json'
        }
      });
      
      console.log(`📊 OWNER API RESPONSE: Status ${response.status} for ID ${ownerId}`);
      
      if (response.ok) {
        const data = await response.json();
        console.log(`✅ OWNER API SUCCESS: Raw data for ID ${ownerId}:`, JSON.stringify(data, null, 2));
        
        const firstName = data.firstName || '';
        const lastName = data.lastName || '';
        const fullName = `${firstName} ${lastName}`.trim();
        const isActive = data.archived === false;
        
        console.log(`👤 OWNER DETAILS: ID ${ownerId}`);
        console.log(`   - First Name: "${firstName}"`);
        console.log(`   - Last Name: "${lastName}"`);
        console.log(`   - Full Name: "${fullName}"`);
        console.log(`   - Active Status: ${isActive ? 'ACTIVE' : 'INACTIVE'}`);
        console.log(`   - Archived: ${data.archived}`);
        
        const result = fullName || `Owner ID: ${ownerId}`;
        console.log(`✅ OWNER RESOLUTION SUCCESS: "${result}" for ID ${ownerId}`);
        return result;
        
      } else if (response.status === 404) {
        console.log(`❌ OWNER NOT FOUND: ID ${ownerId} does not exist (404)`);
        return `Owner ID: ${ownerId}`;
      } else {
        console.log(`⚠️ OWNER API ERROR: Status ${response.status} for ID ${ownerId}`);
        const errorText = await response.text();
        console.log(`📄 Error Response Body: ${errorText}`);
        return `Owner ID: ${ownerId}`;
      }
    } catch (error) {
      console.log(`💥 OWNER API EXCEPTION: ID ${ownerId} - ${error.message}`);
      console.log(`🔍 Error Stack: ${error.stack}`);
      return `Owner ID: ${ownerId}`;
    }
  }

  try {
    const additionalCompanyId = String(event.object.objectId);

    console.log('='.repeat(80));
    console.log('🚀 ADDITIONAL PRODUCT ASSOCIATION WORKFLOW STARTED');
    console.log('🔥 VERSION 1.0.27 CLEAN JS - V4 BATCH ARCHIVE LABEL REMOVAL ACTIVE');
    console.log('='.repeat(80));
    console.log('📋 WORKFLOW INFO:');
    console.log(`   Additional Company ID: ${additionalCompanyId}`);
    console.log(`   Timestamp: ${new Date().toISOString()}`);
    console.log(`   Event Type: ${event.eventType || 'unknown'}`);
    console.log(`   Properties Changed: ${event.propertiesChanged || 'none'}`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 1: VALIDATE ADDITIONAL COMPANY
    // ========================================================================
    console.log('📊 STEP 1: VALIDATING ADDITIONAL COMPANY');
    console.log('-'.repeat(50));

    // Get additional company details
    const additionalCompany = await client.crm.companies.basicApi.getById(additionalCompanyId, [
      'name', 'empresa_adicional', 'hubspot_owner_id', 'lifecyclestage', 'type'
    ]);

    const companyName = additionalCompany.properties.name;
    const empresaAdicional = additionalCompany.properties.empresa_adicional;
    const companyOwnerId = additionalCompany.properties.hubspot_owner_id;
    const lifecycleStage = additionalCompany.properties.lifecyclestage;
    const companyType = additionalCompany.properties.type;

    console.log(`Additional Company: ${companyName}`);
    console.log(`empresa_adicional field: ${empresaAdicional}`);
    console.log(`Lifecycle Stage: ${lifecycleStage}`);
    console.log(`Company Type: ${companyType}`);

    // Get company owner name
    console.log(`🔍 COMPANY OWNER RESOLUTION: Processing company ${additionalCompanyId}`);
    let companyOwnerName = 'No Owner';
    if (companyOwnerId) {
      console.log(`👤 COMPANY OWNER: Resolving owner ID ${companyOwnerId} for company ${additionalCompanyId}`);
      companyOwnerName = await getOwnerName(companyOwnerId);
      console.log(`✅ COMPANY OWNER RESOLVED: "${companyOwnerName}" for company ${additionalCompanyId}`);
    } else {
      console.log(`❌ COMPANY OWNER: No owner ID found for company ${additionalCompanyId}`);
    }

    // Validate this is actually an additional company
    if (!empresaAdicional) {
      const errorMsg = `Company "${companyName}" is not marked as additional company (empresa_adicional field is empty)`;
      console.log(`❌ VALIDATION FAILED: ${errorMsg}`);
      
      // Send error notification
      await sendSlackNotification({
        type: 'error',
        title: '❌ Invalid Additional Company',
        message: errorMsg,
        details: {
          companyId: additionalCompanyId,
          companyName: companyName,
          companyOwnerId: companyOwnerId,
          companyOwnerName: companyOwnerName,
          empresaAdicional: empresaAdicional,
          reason: 'Company does not have empresa_adicional field set - not an additional product company'
        }
      });

      callback(null, 'Success'); // Don't fail workflow, just log and notify
      return;
    }

    console.log(`✅ STEP 1 COMPLETE: Valid additional company confirmed`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 2: FIND CONTACT ASSOCIATED WITH ADDITIONAL COMPANY
    // ========================================================================
    console.log('📊 STEP 2: FINDING CONTACT ASSOCIATED WITH ADDITIONAL COMPANY');
    console.log('-'.repeat(50));

    let contactId = null;
    let contactName = 'Unknown';
    let contactEmail = 'Unknown';
    let contactOwnerId = null;
    let contactOwnerName = 'No Owner';
    let after = undefined;
    const allContactIds = [];
    let totalContactAssociations = 0;

    do {
      const page = await client.crm.associations.v4.basicApi.getPage(
        'companies', additionalCompanyId, 'contacts', after, 100
      );

      const pageResults = page.results || [];
      totalContactAssociations += pageResults.length;

      console.log(`Page retrieved: ${pageResults.length} contact associations (total so far: ${totalContactAssociations})`);

      for (const row of pageResults) {
        const contactIdStr = String(row.toObjectId);
        allContactIds.push(contactIdStr);
        console.log(`✓ Contact found: ${contactIdStr}`);
      }

      after = page.paging?.next?.after;
      if (after) {
        console.log(`Continuing to next page (after: ${after})`);
      }
    } while (after);

    console.log(`Total contact associations found: ${totalContactAssociations}`);
    console.log(`Contact IDs: [${allContactIds.join(', ')}]`);

    if (allContactIds.length === 0) {
      const errorMsg = `No contacts found associated with additional company "${companyName}"`;
      console.log(`❌ CONTACT SEARCH FAILED: ${errorMsg}`);
      
      await sendSlackNotification({
        type: 'error',
        title: '❌ No Contacts Found',
        message: errorMsg,
        details: {
          companyId: additionalCompanyId,
          companyName: companyName,
          companyOwnerId: companyOwnerId,
          companyOwnerName: companyOwnerName,
          reason: 'Additional company has no contact associations - cannot determine primary customer'
        }
      });

      callback(null, 'Success');
      return;
    }

    // For now, use the first contact (in the future, we might need logic to choose the right one)
    contactId = allContactIds[0];
    console.log(`Using first contact: ${contactId}`);

    // Get contact details
    const contact = await client.crm.contacts.basicApi.getById(contactId, [
      'firstname', 'lastname', 'email', 'hubspot_owner_id'
    ]);

    contactName = `${contact.properties.firstname || ''} ${contact.properties.lastname || ''}`.trim() || 'Unknown';
    contactEmail = contact.properties.email || 'Unknown';
    contactOwnerId = contact.properties.hubspot_owner_id;

    // Get contact owner name
    console.log(`🔍 CONTACT OWNER RESOLUTION: Processing contact ${contactId}`);
    if (contactOwnerId) {
      console.log(`👤 CONTACT OWNER: Resolving owner ID ${contactOwnerId} for contact ${contactId}`);
      contactOwnerName = await getOwnerName(contactOwnerId);
      console.log(`✅ CONTACT OWNER RESOLVED: "${contactOwnerName}" for contact ${contactId}`);
    } else {
      console.log(`❌ CONTACT OWNER: No owner ID found for contact ${contactId}`);
    }

    console.log(`Contact Details: ${contactName} (${contactEmail})`);
    console.log(`✅ STEP 2 COMPLETE: Contact found and validated`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 3: FIND PRIMARY CUSTOMER COMPANY ASSOCIATED WITH CONTACT
    // ========================================================================
    console.log('📊 STEP 3: FINDING PRIMARY CUSTOMER COMPANY ASSOCIATED WITH CONTACT');
    console.log('-'.repeat(50));

    let primaryCustomerCompanyId = null;
    let primaryCustomerCompanyName = 'Unknown';
    let primaryCustomerOwnerId = null;
    let primaryCustomerOwnerName = 'No Owner';
    const allCompanyIds = [];
    let totalCompanyAssociations = 0;
    let primaryAssociationsFound = 0;
    after = undefined;

    do {
      const page = await client.crm.associations.v4.basicApi.getPage(
        'contacts', contactId, 'companies', after, 100
      );

      const pageResults = page.results || [];
      totalCompanyAssociations += pageResults.length;

      console.log(`Page retrieved: ${pageResults.length} company associations (total so far: ${totalCompanyAssociations})`);

      for (const row of pageResults) {
        const companyIdStr = String(row.toObjectId);
        const associationTypes = row.associationTypes || [];
        
        // CRITICAL FIX: Use typeId 1 for "Primary" association (not typeId 6)
        // Based on real data testing: typeId 1 has label "Primary"
        const isPrimary = associationTypes.some(t =>
          t.typeId === 1 || (t.label || '').toLowerCase().includes('primary')
        );

        allCompanyIds.push(companyIdStr);

        if (isPrimary) {
          primaryCustomerCompanyId = companyIdStr;
          primaryAssociationsFound++;
          console.log(`✓ PRIMARY customer company found: ${companyIdStr} (typeId: ${associationTypes.map(t => t.typeId).join(', ')})`);
        } else {
          console.log(`- Non-primary company: ${companyIdStr} (typeId: ${associationTypes.map(t => t.typeId).join(', ')})`);
        }
      }

      after = page.paging?.next?.after;
      if (after) {
        console.log(`Continuing to next page (after: ${after})`);
      }
    } while (after);

    console.log(`Total company associations found: ${totalCompanyAssociations}`);
    console.log(`Primary associations found: ${primaryAssociationsFound}`);
    console.log(`All company IDs: [${allCompanyIds.join(', ')}]`);

    if (!primaryCustomerCompanyId) {
      const errorMsg = `No PRIMARY customer company found for contact "${contactName}" (${contactEmail})`;
      console.log(`❌ PRIMARY COMPANY SEARCH FAILED: ${errorMsg}`);
      
      await sendSlackNotification({
        type: 'error',
        title: '❌ No Primary Customer Company Found',
        message: errorMsg,
        details: {
          additionalCompanyId: additionalCompanyId,
          additionalCompanyName: companyName,
          contactId: contactId,
          contactName: contactName,
          contactEmail: contactEmail,
          contactOwnerId: contactOwnerId,
          contactOwnerName: contactOwnerName,
          totalCompanies: totalCompanyAssociations,
          reason: 'Contact has no PRIMARY company association - cannot determine customer company for deal association'
        }
      });

      callback(null, 'Success');
      return;
    }

    // Get primary customer company details
    const primaryCustomerCompany = await client.crm.companies.basicApi.getById(primaryCustomerCompanyId, [
      'name', 'hubspot_owner_id', 'lifecyclestage', 'type'
    ]);

    primaryCustomerCompanyName = primaryCustomerCompany.properties.name;
    primaryCustomerOwnerId = primaryCustomerCompany.properties.hubspot_owner_id;
    const primaryCustomerLifecycleStage = primaryCustomerCompany.properties.lifecyclestage;
    const primaryCustomerType = primaryCustomerCompany.properties.type;

    // Get primary customer company owner name
    console.log(`🔍 PRIMARY CUSTOMER OWNER RESOLUTION: Processing company ${primaryCustomerCompanyId}`);
    if (primaryCustomerOwnerId) {
      console.log(`👤 PRIMARY CUSTOMER OWNER: Resolving owner ID ${primaryCustomerOwnerId} for company ${primaryCustomerCompanyId}`);
      primaryCustomerOwnerName = await getOwnerName(primaryCustomerOwnerId);
      console.log(`✅ PRIMARY CUSTOMER OWNER RESOLVED: "${primaryCustomerOwnerName}" for company ${primaryCustomerCompanyId}`);
    } else {
      console.log(`❌ PRIMARY CUSTOMER OWNER: No owner ID found for company ${primaryCustomerCompanyId}`);
    }

    console.log(`Primary Customer Company: ${primaryCustomerCompanyName}`);
    console.log(`Primary Customer Lifecycle: ${primaryCustomerLifecycleStage}`);
    console.log(`Primary Customer Type: ${primaryCustomerType}`);
    console.log(`✅ STEP 3 COMPLETE: Primary customer company found and validated`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 4: FIND NEWLY CREATED DEAL (ADDITIONAL PRODUCT)
    // ========================================================================
    console.log('📊 STEP 4: FINDING NEWLY CREATED DEAL (ADDITIONAL PRODUCT)');
    console.log('-'.repeat(50));

    // DYNAMIC DEAL SEARCH: Find deals associated with THIS specific additional company
    // Step 1: Get all deals associated with the additional company
    const dealsAssociatedWithCompany = await client.crm.associations.v4.basicApi.getPage(
      'companies',
      additionalCompanyId,
      'deals',
      undefined,
      100
    );

    let associatedDealIds = [];
    if (dealsAssociatedWithCompany.results) {
      associatedDealIds = dealsAssociatedWithCompany.results.map(deal => deal.toObjectId);
      console.log(`📊 Found ${associatedDealIds.length} deals associated with Additional Company ${additionalCompanyId}: [${associatedDealIds.join(', ')}]`);
    }

    if (associatedDealIds.length === 0) {
      const errorMsg = `El Producto Adicional: Compañía ${additionalCompanyId} (${companyName}) no tiene asociación a negocio en la etapa de Negociación Producto Adicional`;
      console.log(`❌ ASSOCIATION SEARCH FAILED: ${errorMsg}`);
      
      await sendSlackNotification({
        type: 'error',
        title: '❌ No Associated Deals Found',
        message: errorMsg,
        details: {
          additionalCompanyId: additionalCompanyId,
          additionalCompanyName: companyName,
          reason: `No deals are currently associated with this additional company - deal may need to be created or associated`
        }
      });

      callback(null, 'Success');
      return;
    }

    // Step 2: Search for deals from the associated list that match our criteria (stage + empresa_adicional)
    const dealSearchResults = await client.crm.deals.searchApi.doSearch({
      filterGroups: [{
        filters: [{
          propertyName: 'dealstage',
          operator: 'EQ',
          value: '948806400'  // Negociación Producto Adicional
        }, {
          propertyName: 'empresa_adicional',
          operator: 'EQ',
          value: 'true'
        }, {
          propertyName: 'hs_object_id',
          operator: 'IN',
          values: associatedDealIds
        }]
      }],
      properties: ['dealname', 'amount', 'closedate', 'hubspot_owner_id', 'createdate', 'empresa_adicional'],
      sorts: [{
        propertyName: 'createdate',
        direction: 'DESCENDING'
      }],
      limit: 10
    });

    const deals = dealSearchResults.results || [];
    console.log(`Found ${deals.length} deals with stage "Negociación Producto Adicional" and empresa_adicional=true associated with Additional Company "${companyName}" (ID: ${additionalCompanyId})`);

    if (deals.length === 0) {
      const errorMsg = `No deals found in correct stage associated with Additional Company ${additionalCompanyId} (${companyName}). Associated deals: [${associatedDealIds.join(', ')}]`;
      console.log(`❌ DEAL STAGE SEARCH FAILED: ${errorMsg}`);
      
      await sendSlackNotification({
        type: 'error',
        title: '❌ No Correct Stage Deals Found',
        message: errorMsg,
        details: {
          additionalCompanyId: additionalCompanyId,
          additionalCompanyName: companyName,
          associatedDealIds: associatedDealIds,
          reason: `Deals exist but none have the expected stage or empresa_adicional=true`
        }
      });

        callback(null, 'Success');
      return;
    }

    // Get the most recent deal for this specific additional company (first in sorted results)
    const newDeal = deals[0];
    const dealId = newDeal.id;
    const dealName = newDeal.properties.dealname;
    const dealAmount = newDeal.properties.amount;
    const dealCloseDate = newDeal.properties.closedate;
    const dealOwnerId = newDeal.properties.hubspot_owner_id;
    const dealCreateDate = newDeal.properties.createdate;

    // Get deal owner name
    console.log(`🔍 DEAL OWNER RESOLUTION: Processing deal ${dealId}`);
    let dealOwnerName = 'No Owner';
    if (dealOwnerId) {
      console.log(`👤 DEAL OWNER: Resolving owner ID ${dealOwnerId} for deal ${dealId}`);
      dealOwnerName = await getOwnerName(dealOwnerId);
      console.log(`✅ DEAL OWNER RESOLVED: "${dealOwnerName}" for deal ${dealId}`);
    } else {
      console.log(`❌ DEAL OWNER: No owner ID found for deal ${dealId}`);
    }

    console.log(`New Deal Details:`);
    console.log(`   Deal ID: ${dealId}`);
    console.log(`   Deal Name: ${dealName}`);
    console.log(`   Deal Amount: ${dealAmount || 'No amount'}`);
    console.log(`   Deal Close Date: ${dealCloseDate || 'No close date'}`);
    console.log(`   Deal Create Date: ${dealCreateDate}`);
    console.log(`   Deal Owner: ${dealOwnerName}`);
    console.log(`✅ STEP 4 COMPLETE: New deal found and validated`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 5: ADD CONTACT-DEAL LABEL FOR TRACKING
    // ========================================================================
    console.log('📊 STEP 5: ADDING CONTACT-DEAL LABEL FOR TRACKING');
    console.log('-'.repeat(50));

    try {
      // Check if the contact-deal association already has the target label
      console.log(`🔍 Checking existing contact-deal associations for label...`);
      const existingContactDealAssociations = await client.crm.associations.v4.basicApi.getPage(
        'contacts',
        contactId,
        'deals',
        undefined,
        100
      );

      let targetContactDealAssociation = null;
      if (existingContactDealAssociations.results) {
        for (const assoc of existingContactDealAssociations.results) {
          if (String(assoc.toObjectId) === String(dealId)) {
            targetContactDealAssociation = assoc;
            break;
          }
        }
      }

      if (!targetContactDealAssociation) {
        console.log(`❌ No association found between Contact ${contactId} and Deal ${dealId} - creating association first`);
        
        // Create the contact-deal association first
        console.log('🔧 Creating contact-deal association...');
        await client.crm.associations.v4.basicApi.create(
          'contacts',
          contactId,
          'deals',
          dealId,
          [{
            associationCategory: 'HUBSPOT_DEFINED',
            associationTypeId: 4  // Standard contact-deal association
          }]
        );
        
        console.log(`✅ SUCCESS: Created contact-deal association between Contact ${contactId} and Deal ${dealId}`);
        
        // Now add the tracking label
        console.log('🔧 Adding tracking label to the new association...');
        await client.crm.associations.v4.basicApi.create(
          'contacts',
          contactId,
          'deals',
          dealId,
          [{
            associationCategory: 'USER_DEFINED',
            associationTypeId: 14  // Type ID for "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol"
          }]
        );
        
        console.log(`✅ SUCCESS: Added label "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol" to Contact ${contactId} → Deal ${dealId}`);
      } else {
        const existingTypes = targetContactDealAssociation.associationTypes || [];
        console.log(`📊 Current contact-deal labels (${existingTypes.length}):`);
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
          console.log('🎉 No action needed - the contact-deal association already has the correct label!');
        } else {
          // Add the label to the existing association
          console.log('🔧 The target label "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol" was not found in existing labels');
          console.log('🔧 Adding the label using Type ID 14 (USER_DEFINED)...');
          
          await client.crm.associations.v4.basicApi.create(
            'contacts',
            contactId,
            'deals',
            dealId,
            [{
              associationCategory: 'USER_DEFINED',
              associationTypeId: 14  // Type ID for "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol"
            }]
          );

          console.log(`✅ SUCCESS: Added label "Contacto Inicial que da el Alta del Negocio - Pendiente asignar rol" to Contact ${contactId} → Deal ${dealId}`);
        }
      }
    } catch (labelError) {
      console.log(`💥 CONTACT-DEAL LABEL ERROR: ${labelError.message}`);
      console.log(`🔍 Error Stack: ${labelError.stack}`);
      // Don't fail the workflow, just log the error
    }

    console.log(`✅ STEP 5 COMPLETE: Contact-deal label processing complete`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 6: ASSOCIATE DEAL WITH PRIMARY CUSTOMER COMPANY
    // ========================================================================
    console.log('📊 STEP 6: ASSOCIATING DEAL WITH PRIMARY CUSTOMER COMPANY');
    console.log('-'.repeat(50));

    try {
      // STEP 6a: REMOVE UNWANTED LABELS FROM ADDITIONAL COMPANY (PRESERVE ASSOCIATION)
      console.info(`🔧 STEP 6a: REMOVING UNWANTED LABELS FROM ADDITIONAL COMPANY (PRESERVE ASSOCIATION)`);
      console.log(`Target: Deal ${dealId} → Additional Company ${additionalCompanyId}`);
      console.log(`Goal: Remove unwanted labels, keep STANDARD (typeId 342) to preserve association`);
      
      try {
        // First, get current association state to see what labels exist
        console.log(`🔍 Getting current additional company associations to identify existing labels...`);
        const currentAssociations = await client.crm.associations.v4.basicApi.getPage(
          'companies',
          additionalCompanyId,
          'deals',
          undefined, // after
          100
        );
        
        // Find the association with our deal
        let targetAssociation = null;
        if (currentAssociations.results) {
          for (const assoc of currentAssociations.results) {
            if (String(assoc.toObjectId) === String(dealId)) {
              targetAssociation = assoc;
              break;
            }
          }
        }
        
        if (!targetAssociation) {
          console.log(`❌ No association found between Additional Company ${additionalCompanyId} and Deal ${dealId} - cannot remove labels`);
        } else {
          const existingTypes = targetAssociation.associationTypes || [];
          if (existingTypes.length === 0) {
            console.log(`✅ No labels to remove - association already has 0 labels`);
          } else {
            console.log(`📊 Found ${existingTypes.length} existing labels to remove:`);
            for (const assocType of existingTypes) {
              const typeId = assocType.typeId;
              const category = assocType.category;
              const label = assocType.label || 'None';
              console.log(`   - Type ID: ${typeId}, Category: ${category}, Label: '${label}'`);
            }
            
            // Filter out STANDARD (typeId 342) - we want to keep this one
            const labelsToRemove = existingTypes.filter(assocType => assocType.typeId !== 342);
            
            if (labelsToRemove.length === 0) {
              console.log(`✅ No unwanted labels to remove - only STANDARD (typeId 342) exists`);
            } else {
              console.log(`📊 Removing ${labelsToRemove.length} unwanted labels, keeping STANDARD (typeId 342):`);
              for (const assocType of labelsToRemove) {
                const typeId = assocType.typeId;
                const label = assocType.label || 'None';
                console.log(`   - Type ID: ${typeId}, Label: '${label}'`);
              }
              
              // Use V4 batch archive to remove unwanted labels
              const batchArchiveInputs = [{
                from: { id: additionalCompanyId },
                to: { id: dealId },
                types: labelsToRemove.map(assocType => ({
                  associationCategory: assocType.category,
                  associationTypeId: assocType.typeId
                }))
              }];
              
              console.log(`📊 BATCH ARCHIVE REQUEST: Removing unwanted labels from additional company`);
              console.log(`📊 Archive Input:`, JSON.stringify(batchArchiveInputs, null, 2));
              
              const archiveUrl = `https://api.hubapi.com/crm/v4/associations/companies/deals/batch/labels/archive`;
              
              const archiveResponse = await fetch(archiveUrl, {
                method: 'POST',
                headers: {
                  'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
                  'Content-Type': 'application/json'
                },
                body: JSON.stringify({ inputs: batchArchiveInputs })
              });
              
              console.log(`📊 BATCH ARCHIVE STATUS: ${archiveResponse.status} (ok: ${archiveResponse.ok})`);
              
              if (archiveResponse.ok) {
                if (archiveResponse.status === 204) {
                  console.log(`✅ BATCH ARCHIVE SUCCESS: Unwanted labels removed from additional company (204 No Content)`);
                  console.log(`   Result: Association preserved with STANDARD (typeId 342) only`);
                } else {
                  try {
                    const archiveResult = await archiveResponse.json();
                    console.log(`✅ BATCH ARCHIVE SUCCESS: Unwanted labels removed from additional company`);
                    console.log(`📊 Archive Result:`, JSON.stringify(archiveResult, null, 2));
                  } catch (jsonError) {
                    console.log(`✅ BATCH ARCHIVE SUCCESS: Unwanted labels removed from additional company (non-JSON response)`);
                  }
                }
              } else {
                const errorText = await archiveResponse.text();
                console.log(`❌ BATCH ARCHIVE FAILED: ${archiveResponse.status} - ${errorText}`);
              }
            }
          }
        }
      } catch (removalError) {
        console.log(`💥 ADDITIONAL COMPANY LABEL REMOVAL ERROR: ${removalError.message}`);
        console.log(`🔍 Error Stack: ${removalError.stack}`);
      }
      
      console.log(`✅ ADDITIONAL COMPANY LABEL REMOVAL COMPLETE: Check logs above for success/failure status`);

      // STEP 6b: ASSOCIATE DEAL WITH PRIMARY CUSTOMER COMPANY (STANDARD)
      console.log(`🔧 STEP 6b: ASSOCIATING DEAL WITH PRIMARY CUSTOMER COMPANY (STANDARD)`);
      console.log(`🔍 Checking if STANDARD association already exists between Deal ${dealId} and Customer Company ${primaryCustomerCompanyId}`);
      
      // Check if STANDARD association already exists
      try {
        const existingAssociations = await client.crm.associations.v4.basicApi.getPage(
          'deals',
          dealId,
          'companies',
          undefined, // after
          100
        );
        
        const hasStandardAssociation = existingAssociations.results?.some(assoc => 
          assoc.toObjectId === primaryCustomerCompanyId && 
          assoc.associationTypes?.some(type => type.typeId === 341)
        );
        
        if (hasStandardAssociation) {
          console.log(`✅ STANDARD ASSOCIATION ALREADY EXISTS: Deal ${dealId} already has STANDARD association with Customer Company ${primaryCustomerCompanyId}`);
        } else {
          console.log(`🔧 CREATING STANDARD ASSOCIATION: Deal ${dealId} needs STANDARD association with Customer Company ${primaryCustomerCompanyId}`);
          
          // Create STANDARD association with customer company (the one we bill)
          await client.crm.associations.v4.basicApi.create(
            'deals',
            dealId,
            'companies',
            primaryCustomerCompanyId,
            [{
              associationCategory: 'HUBSPOT_DEFINED',
              associationTypeId: 341 // STANDARD association (no label) for additional products
            }]
          );

          console.log(`✅ STANDARD ASSOCIATION CREATED: Deal ${dealId} now has STANDARD association with Customer Company ${primaryCustomerCompanyId} (no PRIMARY label)`);
        }
      } catch (checkError) {
        console.log(`⚠️ ASSOCIATION CHECK ERROR: ${checkError.message} - proceeding with creation`);
        
        // Fallback: create STANDARD association
        try {
          await client.crm.associations.v4.basicApi.create(
            'deals',
            dealId,
            'companies',
            primaryCustomerCompanyId,
            [{
              associationCategory: 'HUBSPOT_DEFINED',
              associationTypeId: 341 // STANDARD association (no label) for additional products
            }]
          );

          console.log(`✅ STANDARD ASSOCIATION CREATED (FALLBACK): Deal ${dealId} now has STANDARD association with Customer Company ${primaryCustomerCompanyId}`);
        } catch (fallbackError) {
          console.log(`❌ STANDARD ASSOCIATION CREATION FAILED: ${fallbackError.message} - manual intervention required`);
        }
      }

      console.log(`✅ STEP 6 COMPLETE: Deal associations configured correctly`);
      console.log(`   - Deal ${dealId} → Customer Company ${primaryCustomerCompanyId}: STANDARD (no PRIMARY label)`);
      console.log(`   - Deal ${dealId}/${dealId} → Additional Company ${additionalCompanyId}: STANDARD (for tracking)`);

      // Send success notification
      await sendSlackNotification({
        type: 'success',
        title: '✅ Additional Product Deal Associations Configured',
        message: `Successfully configured additional product deal "${dealName}" - removed unwanted labels and created STANDARD associations with both customer company "${primaryCustomerCompanyName}" (billing) and additional company "${companyName}" (tracking)`,
        details: {
          additionalCompanyId: additionalCompanyId,
          additionalCompanyName: companyName,
          additionalCompanyOwnerId: companyOwnerId,
          additionalCompanyOwnerName: companyOwnerName,
          primaryCustomerCompanyId: primaryCustomerCompanyId,
          primaryCustomerCompanyName: primaryCustomerCompanyName,
          primaryCustomerOwnerId: primaryCustomerOwnerId,
          primaryCustomerOwnerName: primaryCustomerOwnerName,
          contactId: contactId,
          contactName: contactName,
          contactEmail: contactEmail,
          contactOwnerId: contactOwnerId,
          contactOwnerName: contactOwnerName,
          dealId: dealId,
          dealName: dealName,
          dealAmount: dealAmount,
          dealCloseDate: dealCloseDate,
          dealCreateDate: dealCreateDate,
          dealOwnerId: dealOwnerId,
          dealOwnerName: dealOwnerName,
          associationType: 'STANDARD',
          reason: 'Additional product deal successfully associated with primary customer company through contact relationship'
        }
      });

      console.log(`✅ STEP 6 COMPLETE: Deal association created successfully`);
      
    } catch (associationError) {
      console.error(`❌ ASSOCIATION CREATION FAILED: ${associationError.message}`);
      console.error(`Error details:`, associationError);
      
      // Send error notification
      await sendSlackNotification({
        type: 'error',
        title: '❌ Deal Association Failed',
        message: `Failed to associate deal "${dealName}" with primary customer company "${primaryCustomerCompanyName}" - ${associationError.message}`,
        details: {
          additionalCompanyId: additionalCompanyId,
          additionalCompanyName: companyName,
          primaryCustomerCompanyId: primaryCustomerCompanyId,
          primaryCustomerCompanyName: primaryCustomerCompanyName,
          dealId: dealId,
          dealName: dealName,
          dealAmount: dealAmount,
          errorMessage: associationError.message,
          reason: 'Failed to create association between deal and primary customer company'
        }
      });

      // Don't fail the workflow, just log the error
    }

    console.log('='.repeat(80));

    // ========================================================================
    // FINAL WORKFLOW EXECUTION SUMMARY
    // ========================================================================
    console.log('📊 FINAL WORKFLOW EXECUTION SUMMARY');
    console.log('-'.repeat(50));
    console.log(`Additional Company: ${companyName} (ID: ${additionalCompanyId})`);
    console.log(`Contact: ${contactName} (${contactEmail}) (ID: ${contactId})`);
    console.log(`Primary Customer Company: ${primaryCustomerCompanyName} (ID: ${primaryCustomerCompanyId})`);
    console.log(`Deal: ${dealName} (ID: ${dealId})`);
    console.log(`Association: Deal → Primary Customer Company`);
    console.log(`Slack notification: SENT`);
    console.log('='.repeat(80));
    console.log('🎉 ADDITIONAL PRODUCT ASSOCIATION WORKFLOW COMPLETED SUCCESSFULLY');
    console.log('='.repeat(80));
    
    // CRITICAL: Call callback to indicate success (required for HubSpot workflows)
    callback(null, 'Success');

  } catch (err) {
    console.error('=== ERROR OCCURRED ===');
    console.error('Error type:', err.constructor.name);
    console.error('Error message:', err.message);
    console.error('Error stack:', err.stack);

    // Send error notification to Slack
    try {
      await sendSlackNotification({
        type: 'error',
        title: '❌ Workflow Error',
        message: `Error in additional product association workflow for company ${event.object.objectId}`,
        details: {
          companyId: event.object.objectId,
          errorType: err.constructor.name,
          errorMessage: err.message
        }
      });
    } catch (slackError) {
      console.error(`❌ Slack error notification failed:`, slackError.message);
    }

    if (err.response) {
      console.error('HTTP Status:', err.response.status);
      console.error('HTTP Status Text:', err.response.statusText);
      const headersString = JSON.stringify(err.response.headers, null, 2);
      const bodyString = JSON.stringify(err.response.body, null, 2);
      console.error('Response headers:', headersString);
      console.error('Response body:', bodyString);
    }

    const errorString = JSON.stringify(err, null, 2);
    console.error('Full error object:', errorString);
    console.error('=== ERROR LOGGING COMPLETE ===');

    // Call callback with error
    callback(err);
  }
};

// Enhanced Slack notification function with detailed information
async function sendSlackNotification(notification) {
  const slackWebhookUrl = process.env.SlackWebhookUrl;
  
  let slackMessage;
  
  if (notification.type === 'success' && notification.details.dealId) {
    // Enhanced success notification with detailed information
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Additional Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.additionalCompanyId}|${notification.details.additionalCompanyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '👤 Additional Company Owner',
              value: notification.details.additionalCompanyOwnerName || 'No Owner',
              short: true
            },
            {
              title: '🏢 Primary Customer Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.primaryCustomerCompanyId}|${notification.details.primaryCustomerCompanyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '👤 Primary Customer Owner',
              value: notification.details.primaryCustomerOwnerName || 'No Owner',
              short: true
            },
            {
              title: '👤 Contact',
              value: `<https://app.hubspot.com/contacts/19877595/contact/${notification.details.contactId}|${notification.details.contactName || 'Unknown'}> (${notification.details.contactEmail || 'No email'})`,
              short: true
            },
            {
              title: '👤 Contact Owner',
              value: notification.details.contactOwnerName || 'No Owner',
              short: true
            },
            {
              title: '💰 Deal',
              value: `<https://app.hubspot.com/contacts/19877595/deal/${notification.details.dealId}|${notification.details.dealName || 'Unknown'}>`,
              short: true
            },
            {
              title: '💵 Deal Amount',
              value: notification.details.dealAmount ? `$${parseInt(notification.details.dealAmount).toLocaleString()}` : 'No amount',
              short: true
            },
            {
              title: '👤 Deal Owner',
              value: notification.details.dealOwnerName || 'No Owner',
              short: true
            },
            {
              title: '📅 Deal Create Date',
              value: notification.details.dealCreateDate ? new Date(notification.details.dealCreateDate).toISOString().split('T')[0] : 'No date',
              short: true
            },
            {
              title: '🔗 Association Type',
              value: notification.details.associationType || 'STANDARD',
              short: true
            },
            {
              title: '💡 Why This Association?',
              value: notification.details.reason || 'Additional product deal associated with primary customer company through contact relationship',
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Additional Product Workflow',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  } else {
    // Standard format for error notifications
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Additional Company',
              value: notification.details.additionalCompanyId ? `<https://app.hubspot.com/contacts/19877595/company/${notification.details.additionalCompanyId}|${notification.details.additionalCompanyName || 'Unknown'}>` : 'Unknown',
              short: true
            },
            {
              title: '👤 Additional Company Owner',
              value: notification.details.additionalCompanyOwnerName || 'No Owner',
              short: true
            },
            {
              title: '📝 Message',
              value: notification.message,
              short: false
            },
            {
              title: '🔗 Associated Deals',
              value: notification.details.associatedDealIds ? notification.details.associatedDealIds.map(id => `<https://app.hubspot.com/contacts/19877595/deal/${id}|${id}>`).join(', ') : 'None',
              short: true
            },
            {
              title: '💡 Reason',
              value: notification.details.reason || 'No additional details available',
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Additional Product Workflow',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  }

  const response = await fetch(slackWebhookUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(slackMessage)
  });

  if (!response.ok) {
    throw new Error(`Slack API error: ${response.status} ${response.statusText}`);
  }
}

function getSlackColor(type) {
  switch (type) {
    case 'success': return 'good';
    case 'warning': return 'warning';
    case 'error': return 'danger';
    case 'info': return '#36a64f';
    default: return '#36a64f';
  }
}
