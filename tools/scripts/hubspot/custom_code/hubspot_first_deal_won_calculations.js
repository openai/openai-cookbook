// =============================================================================
// HubSpot Custom Code - First Deal Won Date Calculation with Slack Notifications
// =============================================================================
// source: hubspot_first_deal_won_calculations.js
// URL in hubspot automation: https://app.hubspot.com/workflows/19877595/platform/flow/1693911922/edit/actions/1/custom-code
// VERSION: 1.6.0
// LAST UPDATED: 2025-10-19//
// PURPOSE: 
// Calculates first_deal_closed_won_date and company_churn_date for companies
// with auto-fix capabilities for missing PRIMARY associations.
//
// FEATURES:
// ✅ AUTO-FIX: Automatically adds PRIMARY associations when safe to do so
// ✅ CHURN DETECTION: Tracks company churn dates based on deal stages
// ✅ OWNER RESOLUTION: Shows deal and company owner names in Slack notifications
// ✅ EDGE CASE HANDLING: Trial companies, accountants, referrers
// ✅ SLACK NOTIFICATIONS: Detailed notifications for all state changes
//
// ENVIRONMENT VARIABLES REQUIRED:
// - ColppyCRMAutomations: HubSpot API token
// - SlackWebhookUrl: Slack webhook URL for notifications

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
    const companyId = String(event.object.objectId);

    console.log('='.repeat(80));
    console.log('🚀 ENHANCED FIRST DEAL WON DATE CALCULATION STARTED');
    console.log('='.repeat(80));
    console.log('📋 WORKFLOW INFO:');
    console.log(`   Company ID: ${companyId}`);
    console.log(`   Timestamp: ${new Date().toISOString()}`);
    console.log(`   Event Type: ${event.eventType || 'unknown'}`);
    console.log(`   Properties Changed: ${event.propertiesChanged || 'none'}`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 1: RETRIEVING DEAL ASSOCIATIONS
    // ========================================================================
    console.log('📊 STEP 1: RETRIEVING DEAL ASSOCIATIONS');
    console.log('-'.repeat(50));
    let after = undefined;
    const primaryDealIds = [];
    const allDealIds = [];
    let totalAssociations = 0;
    let totalPrimaryDeals = 0;

    do {
      const page = await client.crm.associations.v4.basicApi.getPage(
        'company', companyId, 'deal', after, 100
      );

      const pageResults = page.results || [];
      totalAssociations += pageResults.length;

      console.log(`Page retrieved: ${pageResults.length} associations (total so far: ${totalAssociations})`);

      for (const row of pageResults) {
        const associationTypes = row.associationTypes || [];
        const isPrimary = associationTypes.some(t =>
          t.typeId === 6 || (t.label || '').toLowerCase().includes('primary')
        );

        allDealIds.push(String(row.toObjectId));

        if (isPrimary) {
          primaryDealIds.push(String(row.toObjectId));
          totalPrimaryDeals++;
          console.log(`✓ Primary deal found: ${row.toObjectId} (total primary: ${totalPrimaryDeals})`);
        } else {
          console.log(`- Non-primary deal: ${row.toObjectId}`);
        }
      }

      after = page.paging?.next?.after;
      if (after) {
        console.log(`Continuing to next page (after: ${after})`);
      }
    } while (after);

    console.log('✅ STEP 1 COMPLETE');
    console.log(`   Total associations found: ${totalAssociations}`);
    console.log(`   Total primary deals found: ${totalPrimaryDeals}`);
    console.log(`   Primary deal IDs: [${primaryDealIds.join(', ')}]`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 2: RETRIEVING DEAL DETAILS
    // ========================================================================
    console.log('📋 STEP 2: RETRIEVING DEAL DETAILS');
    console.log('-'.repeat(50));
    const props = ['dealstage', 'closedate', 'dealname', 'amount', 'fecha_de_desactivacion', 'hubspot_owner_id'];
    const wonDates = [];
    const allDealDetails = [];
    let totalDealsProcessed = 0;
    let wonDealsFound = 0;

    // Get details for ALL deals to find true first won date
    for (const ids of chunk(allDealIds, 100)) {
      console.log(`Processing batch of ${ids.length} deals (ALL deals for first won date): [${ids.join(', ')}]`);

      const batch = await client.crm.deals.batchApi.read({
        properties: props,
        inputs: ids.map(id => ({ id })),
      });

      const batchResults = batch.results || [];
      totalDealsProcessed += batchResults.length;

      console.log(`Batch returned ${batchResults.length} deals`);

      for (const deal of batchResults) {
        const dealStage = deal.properties.dealstage;
        const closeDate = deal.properties.closedate;
        const dealName = deal.properties.dealname;
        const amount = deal.properties.amount;
        const fechaDesactivacion = deal.properties.fecha_de_desactivacion;
        const ownerId = deal.properties.hubspot_owner_id;

        // Get deal owner name using the helper function with detailed logging
        console.log(`🔍 DEAL OWNER RESOLUTION: Processing deal ${deal.id}`);
        let dealOwnerName = 'No Owner';
        if (ownerId) {
          console.log(`👤 DEAL OWNER: Resolving owner ID ${ownerId} for deal ${deal.id}`);
          dealOwnerName = await getOwnerName(ownerId);
          console.log(`✅ DEAL OWNER RESOLVED: "${dealOwnerName}" for deal ${deal.id}`);
        } else {
          console.log(`❌ DEAL OWNER: No owner ID found for deal ${deal.id}`);
        }

        const dealInfo = {
          id: deal.id,
          name: dealName,
          stage: dealStage,
          closeDate: closeDate,
          amount: amount,
          fechaDesactivacion: fechaDesactivacion,
          ownerId: ownerId,
          ownerName: dealOwnerName,
          isPrimary: primaryDealIds.includes(deal.id) /* Check if this deal is primary */
        };

        allDealDetails.push(dealInfo);

        const fechaDesactivacionDisplay = fechaDesactivacion || 'NULL';
        console.log(`Deal ${deal.id}: stage="${dealStage}", closedate="${closeDate}", fecha_desactivacion="${fechaDesactivacionDisplay}", name="${dealName}", isPrimary=${dealInfo.isPrimary}`);

        if ((dealStage === 'closedwon' || dealStage === '34692158') && closeDate) {
          const wonDate = new Date(closeDate);
          wonDates.push(wonDate);
          wonDealsFound++;
          console.log(`✓ Won deal found: ${deal.id} with close date ${closeDate}`);
        } else {
          console.log(`- Deal ${deal.id} not won or no close date`);
        }
      }
    }

    console.log('✅ STEP 2 COMPLETE');
    console.log(`   Total deals processed: ${totalDealsProcessed}`);
    console.log(`   Won deals found: ${wonDealsFound}`);
    console.log(`   Won dates: [${wonDates.map(d => d.toISOString().split('T')[0]).join(', ')}]`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 3: ENHANCED CALCULATION AND UPDATE WITH NOTIFICATIONS
    // ========================================================================
    console.log('⚙️ STEP 3: ENHANCED CALCULATION AND UPDATE WITH NOTIFICATIONS');
    console.log('-'.repeat(50));

    // Get current field values for comparison
    const currentCompany = await client.crm.companies.basicApi.getById(companyId, ['first_deal_closed_won_date', 'company_churn_date', 'name', 'lifecyclestage', 'type', 'hubspot_owner_id']);
    const currentFirstDealValue = currentCompany.properties.first_deal_closed_won_date;
    const currentChurnDateValue = currentCompany.properties.company_churn_date;
    const companyName = currentCompany.properties.name;
    
     // Get company owner name using the helper function with detailed logging
     console.log(`🔍 COMPANY OWNER RESOLUTION: Processing company ${companyId}`);
     let companyOwnerName = 'No Owner';
     if (currentCompany.properties.hubspot_owner_id) {
       console.log(`👤 COMPANY OWNER: Resolving owner ID ${currentCompany.properties.hubspot_owner_id} for company ${companyId}`);
       companyOwnerName = await getOwnerName(currentCompany.properties.hubspot_owner_id);
       console.log(`✅ COMPANY OWNER RESOLVED: "${companyOwnerName}" for company ${companyId}`);
     } else {
       console.log(`❌ COMPANY OWNER: No owner ID found for company ${companyId}`);
     }

    console.log(`Current company: ${companyName}`);
    const currentFirstDate = currentFirstDealValue || 'NULL';
    const currentChurnDate = currentChurnDateValue || 'NULL';
    console.log(`Current first_deal_closed_won_date: ${currentFirstDate}`);
    console.log(`Current company_churn_date: ${currentChurnDate}`);

    // Determine workflow outcome for Slack notification
    let workflowOutcome = '';
    let slackNotification = null;

    if (primaryDealIds.length === 0) {
      // EDGE CASE: No primary deals found
      
      // Check if this is a trial company or accountant company
      const lifecycleStage = currentCompany.properties.lifecyclestage;
      const companyType = currentCompany.properties.type;
      
      // Trial company = ANY company in 'lead' lifecycle stage
      // Companies in 'lead' stage don't have deals yet - they become 'opportunity' when deals are created
      const isTrialCompany = lifecycleStage === 'lead';
      
      // Accountant company = Companies that refer clients but don't get PRIMARY deals
      // These are channel partners, not direct customers
      const accountantTypes = ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado'];
      const isAccountantCompany = accountantTypes.includes(companyType);
      
      if (isTrialCompany) {
        // TRIAL COMPANY: Skip notification - this is normal
        console.log(`✅ TRIAL COMPANY: Company "${companyName}" is in 'lead' stage (lifecycle: ${lifecycleStage}) - skipping notification as this is normal for trial companies`);
        workflowOutcome = 'TRIAL_COMPANY_SKIPPED';
        // No Slack notification for trial companies
        slackNotification = null;
      } else if (isAccountantCompany) {
        // ACCOUNTANT COMPANY: Send special notification for verification
        console.log(`🔍 ACCOUNTANT COMPANY: Company "${companyName}" is an accountant (type: ${companyType}) - sending verification notification to confirm this is a legitimate accountant referral`);
        workflowOutcome = 'ACCOUNTANT_COMPANY_VERIFICATION';
        
        // Special notification for accountant companies
        slackNotification = {
          type: 'accountant_verification',
          title: '🔍 Accountant Company Verification Needed',
          message: `Accountant company "${companyName}" has ${totalAssociations} deals but NO PRIMARY associations. Please verify this is a legitimate accountant referral.`,
          details: {
            companyId: companyId,
            companyName: companyName,
            totalDeals: totalAssociations,
            primaryDeals: 0,
            dealDetails: [], // We don't have deal details since we didn't process any
            lifecycleStage: lifecycleStage,
            companyType: companyType,
            reason: 'Accountant companies refer clients but typically don\'t get PRIMARY deals - verification needed to confirm this is normal'
          }
        };
        
        // CLEAR FIRST DEAL DATE: No primary deals means no valid first deal date (even for accountants)
        if (currentFirstDealValue) {
          console.log(`🧹 CLEARING FIELD: No primary deals found for accountant company - clearing first_deal_closed_won_date from "${currentFirstDealValue}" to NULL`);
          
          try {
            await client.crm.companies.basicApi.update(companyId, {
              properties: {
                first_deal_closed_won_date: ""
              }
            });
            
            console.log(`✅ FIELD CLEARED: first_deal_closed_won_date set to NULL for accountant company`);
            
            // Update workflow outcome to reflect the change
            workflowOutcome = 'ACCOUNTANT_FIELD_CLEARED_NO_PRIMARY_DEALS';
            
            // Update notification to reflect the field clearing
            slackNotification.details.changeReason = 'No primary deals found - cleared first_deal_closed_won_date field for accountant company';
            slackNotification.details.oldFirstDate = currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL';
            slackNotification.details.newFirstDate = 'NULL';
            
          } catch (updateError) {
            console.error(`❌ FIELD CLEAR FAILED: ${updateError.message}`);
            // Don't fail the workflow if field clearing fails
          }
        } else {
          console.log(`✅ FIELD ALREADY CLEAR: first_deal_closed_won_date is already NULL for accountant company - no action needed`);
          workflowOutcome = 'ACCOUNTANT_NO_CHANGE_NEEDED_NO_PRIMARY_DEALS';
        }
      } else {
        // CHECK FOR AUTO-FIX OPPORTUNITY: Single company, non-accountant, missing PRIMARY
        const isSingleCompany = totalAssociations === 1;
        const isNotAccountant = !isAccountantCompany;
        const hasNoPrimary = primaryDealIds.length === 0;
        
        if (isSingleCompany && isNotAccountant && hasNoPrimary) {
          // AUTO-FIX CASE: Single company should be PRIMARY
          console.log(`🔧 AUTO-FIX AVAILABLE: Company "${companyName}" has 1 deal with single company (non-accountant) - can auto-fix by setting PRIMARY association`);
          
          try {
            // Get the single company ID from the deal associations
            const singleCompanyId = companyId; // The company we're processing is the single company
            
            // Get the deal ID from the existing associations data
            // We already have allDealDetails from the beginning of the workflow
            const dealId = allDealDetails[0].id; // Get the first (and only) deal
            
            console.log(`🔧 AUTO-FIX: Attempting to add PRIMARY association for company ${singleCompanyId} to deal ${dealId}`);
            
            // Create PRIMARY association via HubSpot API
            await client.crm.associations.v4.basicApi.create(
              'deals',
              dealId,
              'companies',
              singleCompanyId,
              [{
                associationCategory: 'HUBSPOT_DEFINED',
                associationTypeId: 5
              }]
            );
            
            console.log(`✅ AUTO-FIX SUCCESS: Added PRIMARY association for company ${singleCompanyId} to deal ${dealId}`);
            
            // IMMEDIATE RECALCULATION: Now that we have PRIMARY association, recalculate dates
            console.log('🔄 IMMEDIATE RECALCULATION: Recalculating dates after PRIMARY association added');
            
            // Update primaryDealIds to include the newly fixed deal
            // Note: primaryDealIds is const array, so we'll push to it instead of reassigning
            primaryDealIds.push(dealId);
            
            // Recalculate won dates with the new PRIMARY deal
            const dealStage = allDealDetails[0].stage;
            const dealCloseDate = allDealDetails[0].closeDate;
            
            let recalculatedFirstDate = null;
            let recalculatedChurnDate = null;
            
            if (dealStage === 'closedwon' || dealStage === '34692158') {
              // This is a won deal - set first_deal_closed_won_date
              recalculatedFirstDate = dealCloseDate;
              console.log(`✅ RECALCULATED: First deal won date set to ${recalculatedFirstDate}`);
            }
            
            // Update company with recalculated dates
            const updateProperties = {};
            let needsUpdate = false;
            
            if (recalculatedFirstDate && recalculatedFirstDate !== currentFirstDealValue) {
              updateProperties.first_deal_closed_won_date = recalculatedFirstDate;
              needsUpdate = true;
              const oldDate = currentFirstDealValue || 'NULL';
              console.log(`🔄 UPDATE NEEDED: First deal date ${oldDate} → ${recalculatedFirstDate}`);
            }
            
            if (needsUpdate) {
              await client.crm.companies.basicApi.update(companyId, {
                properties: updateProperties
              });
              console.log(`✅ IMMEDIATE UPDATE: Company updated with recalculated dates`);
            }
            
            // Update notification to success with actual calculated dates
            workflowOutcome = 'AUTO_FIX_SUCCESS';
            slackNotification = {
              type: 'success',
              title: '✅ Auto-Fix Completed Successfully',
              message: `Successfully added PRIMARY association and immediately calculated dates for company "${companyName}"`,
              details: {
                companyId: companyId,
                companyName: companyName,
                companyOwnerId: currentCompany.properties.hubspot_owner_id,
                companyOwnerName: companyOwnerName,
                dealId: dealId,
                totalDeals: totalAssociations,
                primaryDeals: 1, // Now has 1 PRIMARY deal
                wonDeals: (dealStage === 'closedwon' || dealStage === '34692158') ? 1 : 0,
                isChurned: false, // Auto-fix doesn't change churn status
                dealDetails: [{
                  name: allDealDetails[0].name,
                  stage: dealStage,
                  closeDateFormatted: dealCloseDate ? new Date(dealCloseDate).toISOString().split('T')[0] : 'NULL',
                  amount: allDealDetails[0].amount,
                  isPrimary: true,
                  ownerId: allDealDetails[0].ownerId,
                  ownerName: allDealDetails[0].ownerName
                }],
                lifecycleStage: lifecycleStage,
                companyType: companyType,
                reason: 'Auto-fix completed: PRIMARY association added and dates immediately calculated',
                autoFixCompleted: true,
                autoFixAction: `Added PRIMARY association (typeId 5) for company ${singleCompanyId} to deal ${dealId}`,
                // Show actual calculated dates
                oldFirstDate: currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL',
                newFirstDate: recalculatedFirstDate ? new Date(recalculatedFirstDate).toISOString().split('T')[0] : 'NULL', 
                oldChurnDate: currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL',
                newChurnDate: recalculatedChurnDate ? new Date(recalculatedChurnDate).toISOString().split('T')[0] : 'NULL',
                changeReason: 'Auto-fix completed: Added PRIMARY association and immediately calculated first_deal_closed_won_date'
              }
            };
            
          } catch (error) {
            console.error(`❌ AUTO-FIX FAILED: ${error.message}`);
            console.error(`Error details:`, error);
            
            // Keep the auto_fix_available notification if fix fails
            workflowOutcome = 'AUTO_FIX_FAILED';
            slackNotification = {
              type: 'error',
              title: '❌ Auto-Fix Failed',
              message: `Failed to add PRIMARY association for company "${companyName}" - ${error.message}`,
              details: {
                companyId: companyId,
                companyName: companyName,
                totalDeals: totalAssociations,
                primaryDeals: 0,
                dealDetails: [],
                lifecycleStage: lifecycleStage,
                companyType: companyType,
                reason: `Auto-fix failed: ${error.message}`,
                autoFixFailed: true,
                errorMessage: error.message
              }
            };
          }
        } else {
          // REAL ISSUE: Company should have primary deals but doesn't
          workflowOutcome = 'NO_PRIMARY_DEALS';
          
          // Different messages based on whether company has any deals
          const hasAnyDeals = totalAssociations > 0;
          const message = hasAnyDeals 
            ? `Company "${companyName}" has ${totalAssociations} total deals but NO PRIMARY associations.`
            : `Company "${companyName}" has no deals and no PRIMARY associations.`;
          
          slackNotification = {
            type: 'warning',
            title: '⚠️ No Primary Deals Found',
            message: message,
            details: {
              companyId: companyId,
              companyName: companyName,
              companyOwnerId: currentCompany.properties.hubspot_owner_id,
              companyOwnerName: companyOwnerName,
              totalDeals: totalAssociations,
              primaryDeals: 0,
              dealDetails: [], // We don't have deal details since we didn't process any
              lifecycleStage: lifecycleStage,
              reason: hasAnyDeals 
                ? 'Company has deals but none are marked as PRIMARY' 
                : 'Company has no deals and no PRIMARY associations'
            }
          };
          console.log(`🚨 EDGE CASE: No primary deals found for company ${companyName} (lifecycle: ${lifecycleStage}, total deals: ${totalAssociations})`);
          
          // CLEAR FIRST DEAL DATE: No primary deals means no valid first deal date
          if (currentFirstDealValue) {
            console.log(`🧹 CLEARING FIELD: No primary deals found - clearing first_deal_closed_won_date from "${currentFirstDealValue}" to NULL`);
            
            try {
              await client.crm.companies.basicApi.update(companyId, {
                properties: {
                  first_deal_closed_won_date: ""
                }
              });
              
              console.log(`✅ FIELD CLEARED: first_deal_closed_won_date set to NULL`);
              
              // Update workflow outcome to reflect the change
              workflowOutcome = 'FIELD_CLEARED_NO_PRIMARY_DEALS';
              
              // Update notification to reflect the field clearing
              slackNotification.details.changeReason = 'No primary deals found - cleared first_deal_closed_won_date field';
              slackNotification.details.oldFirstDate = currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL';
              slackNotification.details.newFirstDate = 'NULL';
              
            } catch (updateError) {
              console.error(`❌ FIELD CLEAR FAILED: ${updateError.message}`);
              // Don't fail the workflow if field clearing fails
            }
          } else {
            console.log(`✅ FIELD ALREADY CLEAR: first_deal_closed_won_date is already NULL - no action needed`);
            workflowOutcome = 'NO_CHANGE_NEEDED_NO_PRIMARY_DEALS';
          }
        }
      }
      
    } else if (wonDates.length === 0) {
      // EDGE CASE: Primary deals exist but none are won - CHECK FOR CHURN AND AUTO-FIX
      console.log('--- CHURN DETECTION ANALYSIS (No Won Deals) ---');
      
      // CHECK FOR AUTO-FIX OPPORTUNITIES: Won deals exist but missing PRIMARY
      const wonDealsWithoutPrimary = allDealDetails.filter(d => 
        (d.stage === 'closedwon' || d.stage === '34692158') && !d.isPrimary
      );
      
      if (wonDealsWithoutPrimary.length > 0) {
        console.log(`🔧 AUTO-FIX AVAILABLE: Found ${wonDealsWithoutPrimary.length} won deals without PRIMARY associations`);
        
        // BUSINESS RULE: Only ONE PRIMARY deal per company - the OLDEST won deal
        // Sort won deals by close date (oldest first)
        const sortedWonDeals = wonDealsWithoutPrimary.sort((a, b) => 
          new Date(a.closeDate) - new Date(b.closeDate)
        );
        
        // Only auto-fix the OLDEST won deal (first in sorted array)
        const oldestWonDeal = sortedWonDeals[0];
        let autoFixSuccessCount = 0;
        const autoFixErrors = [];
        
        if (oldestWonDeal) {
          try {
            console.log(`🔧 AUTO-FIX: Adding PRIMARY association to OLDEST won deal ${oldestWonDeal.id} (${oldestWonDeal.closeDate})`);
            console.log(`🔧 AUTO-FIX: Skipping ${sortedWonDeals.length - 1} newer won deals to maintain single PRIMARY rule`);
            
            // Create PRIMARY association for the OLDEST won deal only
            await client.crm.associations.v4.basicApi.create(
              'deals',
              oldestWonDeal.id,
              'companies',
              companyId,
              [{
                associationCategory: 'HUBSPOT_DEFINED',
                associationTypeId: 5
              }]
            );
            
            console.log(`✅ AUTO-FIX SUCCESS: Added PRIMARY association to OLDEST won deal ${oldestWonDeal.id}`);
            autoFixSuccessCount = 1;
            
          } catch (error) {
            console.error(`❌ AUTO-FIX FAILED for oldest deal ${oldestWonDeal.id}: ${error.message}`);
            autoFixErrors.push(`Oldest deal ${oldestWonDeal.id}: ${error.message}`);
          }
        }
        
        // After auto-fix, continue with normal churn detection logic
        // Update primaryDealIds to include the newly fixed deals
        for (const deal of wonDealsWithoutPrimary) {
          if (autoFixSuccessCount > 0) {
            primaryDealIds.push(deal.id);
          }
        }
        
        // Recalculate won dates with only the OLDEST fixed PRIMARY deal
        const updatedWonDates = [];
        for (const deal of allDealDetails) {
          if ((deal.stage === 'closedwon' || deal.stage === '34692158') && 
              (primaryDealIds.includes(deal.id) || (autoFixSuccessCount > 0 && oldestWonDeal && deal.id === oldestWonDeal.id))) {
            updatedWonDates.push(new Date(deal.closeDate));
          }
        }
        
        console.log(`🔧 AUTO-FIX: Recalculated won dates after adding PRIMARY associations: ${updatedWonDates.length} won deals`);
        
        // Continue with normal processing using updated data
        if (updatedWonDates.length > 0) {
          // Update wonDates array for normal processing
          wonDates.length = 0;
          wonDates.push(...updatedWonDates);
          
          console.log(`🔧 AUTO-FIX: Updated wonDates array with ${wonDates.length} dates - continuing with normal processing`);
          
          // Skip the rest of churn detection and go to normal won deals processing
          // This will be handled by the main won deals logic below
        }
      }
      
      // Count all deals by stage
      let wonDealsCount = 0;
      let lostDealsCount = 0;
      let churnedDealsCount = 0;
      
      for (const deal of allDealDetails) {
        if (deal.isPrimary) {
          if (deal.stage === 'closedwon' || deal.stage === '34692158') {
            wonDealsCount++;
          } else if (deal.stage === 'closedlost') {
            lostDealsCount++;
          } else if (deal.stage === '31849274') {
            churnedDealsCount++;
          }
        }
      }
      
      console.log(`Primary deals breakdown: ${wonDealsCount} won, ${lostDealsCount} lost, ${churnedDealsCount} churned`);
      
      // Determine if company is churned
      const totalPrimaryDealsCount = wonDealsCount + lostDealsCount + churnedDealsCount;
      
      // CRITICAL FIX: A company is churned ONLY if:
      // 1. It has primary deals (was a customer)
      // 2. It currently has no won deals (all deals are lost/churned)
      // 3. It has deals in ACTUAL CHURN STAGE (31849274), not just closedlost
      // This prevents never-customers and lost-but-not-churned customers from being marked as churned
      const hasActualChurnDeals = churnedDealsCount > 0; // Only 31849274 stage counts as churn
      const isChurned = totalPrimaryDealsCount > 0 && wonDealsCount === 0 && hasActualChurnDeals;
      
      console.log(`Total primary deals: ${totalPrimaryDealsCount}`);
      console.log(`Has actual churn deals (31849274): ${hasActualChurnDeals} (churnedDealsCount: ${churnedDealsCount})`);
      console.log(`Is company churned: ${isChurned}`);
      
      let companyChurnDate = null;
      let churnDateSource = '';
      let manualErrorDetected = false;
      
      if (isChurned) {
        // Company is churned - find the correct churn date
        // Only look at actual churn deals (31849274), not closedlost deals
        const churnedDeals = allDealDetails.filter(d => 
          d.isPrimary && d.stage === '31849274'
        );
        
        if (churnedDeals.length > 0) {
          // Sort by close date and get the most recent churned deal
          const sortedChurnedDeals = churnedDeals.sort((a, b) => 
            new Date(b.closeDate) - new Date(a.closeDate)
          );
          const lastChurnedDeal = sortedChurnedDeals[0];
          
          // Check for manual error: churned deal with blank fecha_de_desactivacion
          if (lastChurnedDeal.stage === '31849274' && 
              (!lastChurnedDeal.fechaDesactivacion || lastChurnedDeal.fechaDesactivacion.trim() === '')) {
            manualErrorDetected = true;
            console.log(`⚠️ MANUAL ERROR DETECTED: Deal ${lastChurnedDeal.id} (${lastChurnedDeal.name}) is churned but fecha_de_desactivacion is blank!`);
          }
          
          // Priority 1: Use fecha_de_desactivacion if available
          if (lastChurnedDeal.fechaDesactivacion && lastChurnedDeal.fechaDesactivacion.trim() !== '') {
            companyChurnDate = new Date(lastChurnedDeal.fechaDesactivacion).toISOString();
            churnDateSource = 'fecha_de_desactivacion';
            console.log(`Company churn date set to: ${companyChurnDate} (from fecha_de_desactivacion field of deal: ${lastChurnedDeal.name})`);
          } else {
            // Priority 2: Use close date (date when deal was last closedwon)
            companyChurnDate = new Date(lastChurnedDeal.closeDate).toISOString();
            churnDateSource = 'close_date';
            console.log(`Company churn date set to: ${companyChurnDate} (from close date of deal: ${lastChurnedDeal.name})`);
          }
        } else {
          console.log(`Company is churned but no churned deals found - this shouldn't happen`);
        }
      } else {
        console.log(`Company is not churned - no primary deals or has won deals`);
      }

      // Check if changes are needed for churn date
      // Normalize empty strings to null for proper comparison
      const normalizedCurrentChurnDate = (currentChurnDateValue === '' || currentChurnDateValue === null) ? null : currentChurnDateValue;
      const normalizedCalculatedChurnDate = (companyChurnDate === '' || companyChurnDate === null) ? null : companyChurnDate;
      const needsChurnUpdate = (normalizedCurrentChurnDate !== normalizedCalculatedChurnDate);
      
      console.log(`Current churn date: ${currentChurnDateValue || 'NULL'}`);
      console.log(`Calculated churn date: ${companyChurnDate || 'NULL'}`);
      console.log(`Normalized comparison: "${normalizedCurrentChurnDate}" !== "${normalizedCalculatedChurnDate}" = ${needsChurnUpdate}`);

      if (needsChurnUpdate) {
        workflowOutcome = 'CHURN_DETECTED';
        
        // Prepare update properties
        const updateProperties = {};
        
        if (companyChurnDate) {
          updateProperties.company_churn_date = companyChurnDate;
        } else {
          updateProperties.company_churn_date = ""; // Clear churn date with empty string
        }
        
        console.log(`🔄 CHURN CHANGE DETECTED: Churn date "${currentChurnDateValue || 'NULL'}" → "${companyChurnDate || 'NULL'}"`);
        console.log(`Updating company ${companyId} with properties:`, updateProperties);

        await client.crm.companies.basicApi.update(companyId, {
          properties: updateProperties
        });

        console.log(`✅ CHURN CHANGE MADE: Company updated successfully`);

        slackNotification = {
          type: manualErrorDetected ? 'error' : 'success',
          title: manualErrorDetected ? '🚨 Company Churn + Manual Error Detected' : '🔴 Company Churn Detected',
          message: `Company "${companyName}" is CHURNED - churn date set to ${companyChurnDate ? new Date(companyChurnDate).toISOString().split('T')[0] : 'NULL'} (source: ${churnDateSource})${manualErrorDetected ? ' - ⚠️ MANUAL ERROR: fecha_de_desactivacion is blank!' : ''}`,
          details: {
            companyId: companyId,
            companyName: companyName,
            companyOwnerId: currentCompany.properties.hubspot_owner_id,
            companyOwnerName: companyOwnerName,
            oldChurnValue: currentChurnDateValue,
            newChurnValue: companyChurnDate,
            oldChurnDate: currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL',
            newChurnDate: companyChurnDate ? new Date(companyChurnDate).toISOString().split('T')[0] : 'NULL',
            oldFirstDate: currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL',
            newFirstDate: currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL',
            primaryDeals: totalDealsProcessed,
            wonDeals: wonDealsFound,
            isChurned: isChurned,
            dealDetails: allDealDetails.map(d => ({
              id: d.id,
              name: d.name,
              stage: d.stage,
              closeDate: d.closeDate,
              closeDateFormatted: d.closeDate ? new Date(d.closeDate).toISOString().split('T')[0] : 'No date',
              fechaDesactivacion: d.fechaDesactivacion,
              fechaDesactivacionFormatted: d.fechaDesactivacion ? new Date(d.fechaDesactivacion).toISOString().split('T')[0] : 'NULL',
              amount: d.amount,
              isPrimary: d.isPrimary,
              ownerId: d.ownerId,
              ownerName: d.ownerName
            })),
            churnDateSource: churnDateSource,
            manualErrorDetected: manualErrorDetected,
            changeReason: `Company churned - all primary deals are lost/churned (${lostDealsCount} lost, ${churnedDealsCount} churned)${manualErrorDetected ? ' - MANUAL ERROR: fecha_de_desactivacion is blank!' : ''}`
          }
        };

        // Log the result
        const updatedCompany = await client.crm.companies.basicApi.getById(companyId, ['first_deal_closed_won_date', 'company_churn_date', 'name']);
        console.log(`Verification - Company name: ${updatedCompany.properties.name}`);
        console.log(`Verification - Company churn date: ${updatedCompany.properties.company_churn_date}`);

      } else {
        workflowOutcome = 'NO_CHANGE_NEEDED';
        console.log(`✅ NO CHANGE NEEDED: Churn date already set correctly`);
        console.log(`Churn date: ${companyChurnDate || 'NULL'} (unchanged)`);
        console.log(`Skipping update - churn status is already correct`);
      }
      
    } else if (wonDates.length > 0) {
      // NORMAL CASE: Calculate first won date
      const firstWonDate = new Date(Math.min(...wonDates));
      const formattedFirstDate = firstWonDate.toISOString();

      console.log(`First won date calculated: ${formattedFirstDate}`);

      // CHECK FOR AUTO-FIX OPPORTUNITIES: Won deals exist but missing PRIMARY
      const wonDealsWithoutPrimary = allDealDetails.filter(d => 
        (d.stage === 'closedwon' || d.stage === '34692158') && !d.isPrimary
      );
      
      if (wonDealsWithoutPrimary.length > 0) {
        console.log(`🔧 AUTO-FIX AVAILABLE: Found ${wonDealsWithoutPrimary.length} won deals without PRIMARY associations`);
        
        // BUSINESS RULE: Only ONE PRIMARY deal per company - the OLDEST won deal
        // Sort won deals by close date (oldest first)
        const sortedWonDeals = wonDealsWithoutPrimary.sort((a, b) => 
          new Date(a.closeDate) - new Date(b.closeDate)
        );
        
        // Only auto-fix the OLDEST won deal (first in sorted array)
        const oldestWonDeal = sortedWonDeals[0];
        let autoFixSuccessCount = 0;
        const autoFixErrors = [];
        
        if (oldestWonDeal) {
          try {
            console.log(`🔧 AUTO-FIX: Adding PRIMARY association to OLDEST won deal ${oldestWonDeal.id} (${oldestWonDeal.closeDate})`);
            console.log(`🔧 AUTO-FIX: Skipping ${sortedWonDeals.length - 1} newer won deals to maintain single PRIMARY rule`);
            
            // Create PRIMARY association for the OLDEST won deal only
            await client.crm.associations.v4.basicApi.create(
              'deals',
              oldestWonDeal.id,
              'companies',
              companyId,
              [{
                associationCategory: 'HUBSPOT_DEFINED',
                associationTypeId: 5
              }]
            );
            
            console.log(`✅ AUTO-FIX SUCCESS: Added PRIMARY association to OLDEST won deal ${oldestWonDeal.id}`);
            autoFixSuccessCount = 1;
            
          } catch (error) {
            console.error(`❌ AUTO-FIX FAILED for oldest deal ${oldestWonDeal.id}: ${error.message}`);
            autoFixErrors.push(`Oldest deal ${oldestWonDeal.id}: ${error.message}`);
          }
        }
        
        // Update primaryDealIds count after auto-fix
        // Note: updatedPrimaryDealsCount variable removed as it was not being used
        
        // After auto-fix, continue with normal date calculation logic
        // Update primaryDealIds to include only the OLDEST fixed deal
        if (autoFixSuccessCount > 0 && oldestWonDeal) {
          primaryDealIds.push(oldestWonDeal.id);
        }
        
        // Recalculate won dates with only the OLDEST fixed PRIMARY deal
        const updatedWonDates = [];
        for (const deal of allDealDetails) {
          if ((deal.stage === 'closedwon' || deal.stage === '34692158') && 
              (primaryDealIds.includes(deal.id) || (autoFixSuccessCount > 0 && oldestWonDeal && deal.id === oldestWonDeal.id))) {
            updatedWonDates.push(new Date(deal.closeDate));
          }
        }
        
        console.log(`🔧 AUTO-FIX: Recalculated won dates after adding PRIMARY associations: ${updatedWonDates.length} won deals`);
        
        // Continue with normal processing using updated data
        if (updatedWonDates.length > 0) {
          // Update wonDates array for normal processing
          wonDates.length = 0;
          wonDates.push(...updatedWonDates);
          
          console.log(`🔧 AUTO-FIX: Updated wonDates array with ${wonDates.length} dates`);
        }
      }

      // CRITICAL CHECK: Only process companies with PRIMARY deals
      if (primaryDealIds.length === 0) {
        console.log(`⚠️ SKIPPING: Company has won deals but NO PRIMARY deals - this is a referrer/accountant, not a customer`);
        workflowOutcome = 'SKIPPED_NON_PRIMARY';
        slackNotification = {
          type: 'warning',
          title: '⚠️ Non-Primary Company Skipped',
          message: `Company "${companyName}" has won deals but NO PRIMARY associations - skipping first_deal_closed_won_date calculation`,
          details: {
            companyId: companyId,
            companyName: companyName,
            companyOwnerId: currentCompany.properties.hubspot_owner_id,
            companyOwnerName: companyOwnerName,
            totalDeals: totalAssociations,
            primaryDeals: 0,
            wonDeals: wonDates.length,
            reason: 'Company is referrer/accountant, not a customer'
          }
        };
        return { workflowOutcome, slackNotification };
      }

      // CHURN DETECTION LOGIC
      console.log('--- CHURN DETECTION ANALYSIS ---');
      
      // Count all deals by stage
      let wonDealsCount = 0;
      let lostDealsCount = 0;
      let churnedDealsCount = 0;
      
      for (const deal of allDealDetails) {
        if (deal.isPrimary) {
          if (deal.stage === 'closedwon' || deal.stage === '34692158') {
            wonDealsCount++;
          } else if (deal.stage === 'closedlost') {
            lostDealsCount++;
          } else if (deal.stage === '31849274') {
            churnedDealsCount++;
          }
        }
      }
      
      console.log(`Primary deals breakdown: ${wonDealsCount} won, ${lostDealsCount} lost, ${churnedDealsCount} churned`);
      
      // Determine if company is churned
      const totalPrimaryDealsCount = wonDealsCount + lostDealsCount + churnedDealsCount;
      const isChurned = totalPrimaryDealsCount > 0 && wonDealsCount === 0 && (lostDealsCount > 0 || churnedDealsCount > 0);
      
      console.log(`Total primary deals: ${totalPrimaryDealsCount}`);
      console.log(`Is company churned: ${isChurned}`);
      
      let companyChurnDate = null;
      if (isChurned) {
        // Company is churned - churn date is the close date of the last won deal
        const lastWonDate = new Date(Math.max(...wonDates));
        companyChurnDate = lastWonDate.toISOString();
        console.log(`Company churn date: ${companyChurnDate}`);
      } else {
        console.log(`Company is still active - no churn date`);
      }

      // Check if changes are needed (date-based comparison, not exact timestamp)
      const normalizedCurrentFirstDate = currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : null;
      const calculatedFirstDate = new Date(formattedFirstDate).toISOString().split('T')[0];
      
      const needsFirstUpdate = normalizedCurrentFirstDate !== calculatedFirstDate;
      const needsChurnUpdate = (currentChurnDateValue !== companyChurnDate);
      const needsUpdate = needsFirstUpdate || needsChurnUpdate;

      console.log(`Current first date: ${normalizedCurrentFirstDate || 'NULL'}`);
      console.log(`Calculated first date: ${calculatedFirstDate}`);
      console.log(`First date comparison: ${normalizedCurrentFirstDate} !== ${calculatedFirstDate} = ${needsFirstUpdate}`);
      console.log(`Current churn date: ${currentChurnDateValue || 'NULL'}`);
      console.log(`Calculated churn date: ${companyChurnDate || 'NULL'}`);
      console.log(`Churn date comparison: ${currentChurnDateValue} !== ${companyChurnDate} = ${needsChurnUpdate}`);
      console.log(`Overall needs update: ${needsUpdate}`);

      if (needsUpdate) {
        workflowOutcome = 'UPDATE_MADE';
        
        // Prepare update properties
        const updateProperties = {};
        let changeDescription = '';
        
        if (needsFirstUpdate) {
          updateProperties.first_deal_closed_won_date = formattedFirstDate;
          changeDescription += `First: "${currentFirstDealValue || 'NULL'}" → "${formattedFirstDate}"`;
        }
        
        if (needsChurnUpdate) {
          if (companyChurnDate) {
            updateProperties.company_churn_date = companyChurnDate;
          } else {
            updateProperties.company_churn_date = null; // Clear churn date for active companies
          }
          if (changeDescription) changeDescription += ' | ';
          changeDescription += `Churn: "${currentChurnDateValue || 'NULL'}" → "${companyChurnDate || 'NULL'}"`;
        }
        
        console.log(`🔄 CHANGE DETECTED: ${changeDescription}`);
        console.log(`Updating company ${companyId} with properties:`, updateProperties);

        await client.crm.companies.basicApi.update(companyId, {
          properties: updateProperties
        });

        console.log(`✅ CHANGE MADE: Company updated successfully`);

        // Check if this was an auto-fix case (PRIMARY associations were actually added)
        // Note: This section only runs when date fields are updated, not when PRIMARY associations are added
        // PRIMARY association auto-fix has its own notification above (lines 236-250)
        const wasAutoFix = false; // Date field updates are not PRIMARY association auto-fixes
        
        slackNotification = {
          type: 'success',
          title: wasAutoFix ? '✅ Auto-Fix Completed Successfully' : '✅ Company Data Updated',
          message: `Company "${companyName}" - ${changeDescription}`,
          details: {
            companyId: companyId,
            companyName: companyName,
            companyOwnerId: currentCompany.properties.hubspot_owner_id,
            companyOwnerName: companyOwnerName,
            oldFirstValue: currentFirstDealValue,
            newFirstValue: needsFirstUpdate ? formattedFirstDate : currentFirstDealValue,
            oldChurnValue: currentChurnDateValue,
            newChurnValue: needsChurnUpdate ? companyChurnDate : currentChurnDateValue,
            oldFirstDate: currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL',
            newFirstDate: needsFirstUpdate ? new Date(formattedFirstDate).toISOString().split('T')[0] : (currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL'),
            oldChurnDate: currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL',
            newChurnDate: needsChurnUpdate ? (companyChurnDate ? new Date(companyChurnDate).toISOString().split('T')[0] : 'NULL') : (currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL'),
            primaryDeals: totalDealsProcessed,
            wonDeals: wonDealsFound,
            isChurned: isChurned,
            dealDetails: allDealDetails.map(d => ({
              id: d.id,
              name: d.name,
              stage: d.stage,
              closeDate: d.closeDate,
              closeDateFormatted: d.closeDate ? new Date(d.closeDate).toISOString().split('T')[0] : 'No date',
              amount: d.amount,
              isPrimary: d.isPrimary,
              ownerId: d.ownerId,
              ownerName: d.ownerName
            })),
            changeReason: wasAutoFix 
              ? `Auto-fix completed: Added PRIMARY associations to won deals and immediately calculated first_deal_closed_won_date`
              : `Updated because ${needsFirstUpdate ? 'first deal date' : ''}${needsFirstUpdate && needsChurnUpdate ? ' and ' : ''}${needsChurnUpdate ? 'churn date' : ''} changed based on current PRIMARY deals.`,
            autoFixCompleted: wasAutoFix
          }
        };

        // Log the result
        const updatedCompany = await client.crm.companies.basicApi.getById(companyId, ['first_deal_closed_won_date', 'company_churn_date', 'name']);
        console.log(`Verification - Company name: ${updatedCompany.properties.name}`);
        console.log(`Verification - First deal closed won date: ${updatedCompany.properties.first_deal_closed_won_date}`);
        console.log(`Verification - Company churn date: ${updatedCompany.properties.company_churn_date}`);

      } else {
        workflowOutcome = 'NO_CHANGE_NEEDED';
        console.log(`✅ NO CHANGE NEEDED: Fields already set to correct values`);
        console.log(`First date: ${calculatedFirstDate} (unchanged)`);
        console.log(`Churn date: ${companyChurnDate || 'NULL'} (unchanged)`);
        console.log(`Skipping update - values are already correct`);
      }
    }

    console.log('✅ STEP 3 COMPLETE');
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 4: SENDING SLACK NOTIFICATION
    // ========================================================================
    if (slackNotification) {
      console.log('📢 STEP 4: SENDING SLACK NOTIFICATION');
      console.log('-'.repeat(50));
      
      try {
        console.log(`📤 Sending notification: ${slackNotification.type} - ${slackNotification.title}`);
        await sendSlackNotification(slackNotification);
        console.log(`✅ Slack notification sent successfully`);
      } catch (slackError) {
        console.error(`❌ Slack notification failed:`, slackError.message);
        console.error(`🔍 Slack error details:`, slackError);
        // Don't fail the entire workflow if Slack fails
      }
      
      console.log('✅ STEP 4 COMPLETE');
    } else {
      console.log('📢 STEP 4: SKIPPED (No notification needed)');
    }
    console.log('='.repeat(80));

    // ========================================================================
    // FINAL WORKFLOW EXECUTION SUMMARY
    // ========================================================================
    console.log('📊 FINAL WORKFLOW EXECUTION SUMMARY');
    console.log('-'.repeat(50));
    console.log(`Company: ${companyName} (ID: ${companyId})`);
    console.log(`Primary deals processed: ${primaryDealIds.length}`);
    console.log(`Won deals found: ${wonDates.length}`);
    console.log(`Workflow outcome: ${workflowOutcome}`);
    console.log(`Slack notification: ${slackNotification ? 'SENT' : 'NONE'}`);
    
    if (wonDates.length > 0) {
      const firstWonDate = new Date(Math.min(...wonDates));
      const formattedDate = firstWonDate.toISOString();
      console.log(`Calculated first won date: ${formattedDate}`);
      console.log(`Current field value: ${currentFirstDealValue || 'NULL'}`);
      const currentDateSummary = currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : null;
      const calculatedDateSummary = new Date(formattedDate).toISOString().split('T')[0];
      console.log(`Change made: ${currentDateSummary !== calculatedDateSummary ? 'YES' : 'NO'}`);
    } else {
      console.log(`No won deals found`);
      console.log(`Current field value: ${currentFirstDealValue || 'NULL'}`);
      console.log(`Change made: ${currentFirstDealValue !== null && currentFirstDealValue !== undefined ? 'YES (cleared)' : 'NO'}`);
    }
    
    console.log('='.repeat(80));
    console.log('🎉 ENHANCED FIRST DEAL WON DATE CALCULATION COMPLETED SUCCESSFULLY');
    console.log('='.repeat(80));
    
    // Call callback to indicate success
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
        message: `Error in first_deal_closed_won_date workflow for company ${event.object.objectId}`,
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

// Enhanced Slack notification function with detailed sales team information
async function sendSlackNotification(notification) {
  const slackWebhookUrl = process.env.SlackWebhookUrl;
  
  let slackMessage;
  
  if (notification.type === 'success' && notification.details.dealDetails) {
    // Enhanced success notification with detailed change information
    const dealList = notification.details.dealDetails
      .map(d => `• <https://app.hubspot.com/contacts/19877595/deal/${d.id}|${d.name}> (${d.stage}) - ${d.closeDateFormatted}${d.amount ? ` - $${parseInt(d.amount).toLocaleString()}` : ''}${d.isPrimary ? ' [PRIMARY]' : ''}${d.ownerName && d.ownerName !== 'No Owner' ? ` - Owner: ${d.ownerName}` : ''}`)
      .join('\n');
    
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '👤 Company Owner',
              value: notification.details.companyOwnerName || 'No Owner',
              short: true
            },
                        {
                          title: '📅 First Deal Date',
                          value: `${notification.details.oldFirstDate} → ${notification.details.newFirstDate}`,
                          short: true
                        },
                        {
                          title: '📅 Churn Date',
                          value: `${notification.details.oldChurnDate} → ${notification.details.newChurnDate}`,
                          short: true
                        },
            {
              title: '💰 Deal Summary',
              value: `${notification.details.primaryDeals} primary deals, ${notification.details.wonDeals} won${notification.details.isChurned ? ' (CHURNED)' : ' (ACTIVE)'}`,
              short: true
            },
            {
              title: '📋 All Primary Deals',
              value: dealList,
              short: false
            },
            {
              title: '💡 Why This Change?',
              value: notification.details.changeReason || 'Field updated to reflect earliest primary won deal',
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Workflow Automation',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  } else if (notification.type === 'warning' && notification.details.dealDetails) {
    // Enhanced warning notification for no primary deals
    const dealList = notification.details.dealDetails
      .slice(0, 5)
      .map(d => `• <https://app.hubspot.com/contacts/19877595/deal/${d.id}|${d.name}> (${d.stage}) - ${d.closeDateFormatted}${d.amount ? ` - $${parseInt(d.amount).toLocaleString()}` : ''}${d.isPrimary ? ' [PRIMARY]' : ''}${d.ownerName && d.ownerName !== 'No Owner' ? ` - Owner: ${d.ownerName}` : ''}`)
      .join('\n');
    
    const dealSummary = dealList + (notification.details.dealDetails.length > 5 ? '\n• ...' : '');
    
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '👤 Company Owner',
              value: notification.details.companyOwnerName || 'No Owner',
              short: true
            },
            {
              title: '⚠️ Issue',
              value: `${notification.details.totalDeals} deals found, but NO PRIMARY associations`,
              short: false
            },
            {
              title: '📋 Deal Details',
              value: dealSummary,
              short: false
            },
            {
              title: '🔧 Action Needed',
              value: 'Please check deal associations and ensure at least one deal is marked as PRIMARY',
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Workflow Automation',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  } else if (notification.type === 'info') {
    // Enhanced info notification for no won deals
    const dealList = notification.details.dealDetails
      .map(d => `• <https://app.hubspot.com/contacts/19877595/deal/${d.id}|${d.name}> (${d.stage}) - ${d.closeDateFormatted}${d.amount ? ` - $${parseInt(d.amount).toLocaleString()}` : ''}${d.ownerName && d.ownerName !== 'No Owner' ? ` - Owner: ${d.ownerName}` : ''}`)
      .join('\n');
    
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '👤 Company Owner',
              value: notification.details.companyOwnerName || 'No Owner',
              short: true
            },
            {
              title: 'ℹ️ Status',
              value: `${notification.details.primaryDeals} primary deals found, but none are closed won`,
              short: false
            },
            {
              title: '📋 Primary Deals',
              value: dealList,
              short: false
            },
            {
              title: '💡 Next Steps',
              value: 'When a primary deal is closed won, the first_deal_closed_won_date will be automatically updated',
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Workflow Automation',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  } else if (notification.type === 'accountant_verification') {
    // Special notification for accountant company verification
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '🏢 Company Type',
              value: notification.details.companyType || 'Unknown',
              short: true
            },
            {
              title: '📊 Lifecycle Stage',
              value: notification.details.lifecycleStage || 'Unknown',
              short: true
            },
            {
              title: '⚠️ Issue',
              value: `${notification.details.totalDeals} deals found, but NO PRIMARY associations`,
              short: false
            },
            {
              title: '💡 Action Needed',
              value: 'Please verify this is a legitimate accountant referral',
              short: false
            },
            {
              title: '📝 Reason',
              value: notification.details.reason || 'Verification needed',
              short: false
            }
          ]
        }
      ]
    };
  } else if (notification.type === 'auto_fix_available') {
    // Critical notification for auto-fix availability
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '🏢 Company Type',
              value: notification.details.companyType || 'Unknown',
              short: true
            },
            {
              title: '📊 Lifecycle Stage',
              value: notification.details.lifecycleStage || 'Unknown',
              short: true
            },
            {
              title: '⚠️ Issue',
              value: `${notification.details.totalDeals} deals found, but NO PRIMARY associations`,
              short: false
            },
            {
              title: '🔧 Auto-Fix Available',
              value: notification.details.autoFixAction || 'Set single company as PRIMARY association',
              short: false
            },
            {
              title: '📝 Reason',
              value: notification.details.reason || 'Single company, non-accountant, missing PRIMARY - safe to auto-fix',
              short: false
            }
          ]
        }
      ]
    };
  } else {
    // Standard format for other notifications
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '👤 Company Owner',
              value: notification.details.companyOwnerName || 'No Owner',
              short: true
            },
            {
              title: '📝 Message',
              value: notification.message,
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Workflow Automation',
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
    case 'accountant_verification': return '#ff9500'; // Orange color for verification
    case 'auto_fix_available': return '#ff0000'; // Red color for critical auto-fix
    default: return '#36a64f';
  }
}

// Helper function for batching
function chunk(array, size) {
  const chunks = [];
  for (let i = 0; i < array.length; i += size) {
    chunks.push(array.slice(i, i + size));
  }
  return chunks;
}
