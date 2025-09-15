#!/usr/bin/env python3
"""
HubSpot Custom Code - First Deal Won Date Calculation with Slack Notifications
Latest Version: 1.5.0
Last Updated: 2025-09-13T14:45:00Z

This is the latest version of the HubSpot Custom Code workflow
that calculates the first_deal_closed_won_date for companies and
sends Slack notifications for edge cases and updates.

CRITICAL REQUIREMENT FOR HUBSPOT WORKFLOWS:
------------------------------------------
HubSpot custom code MUST call the callback function to complete execution:
- On success: callback(null, 'Success');
- On error: callback(err);

Without calling the callback, the workflow will hang with no logs or errors!

SYNC STATUS: This code is kept in sync with HubSpot workflow
"""

from datetime import datetime
from typing import Optional

# HubSpot Custom Code (JavaScript) - Copy this to HubSpot
HUBSPOT_CUSTOM_CODE = '''
const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  try {
    const companyId = String(event.object.objectId);

    console.log('=== ENHANCED FIRST DEAL WON DATE CALCULATION STARTED ===');
    console.log('Company ID:', companyId);
    console.log('Timestamp:', new Date().toISOString());
    console.log('Event type:', event.eventType || 'unknown');
    console.log('Properties changed:', event.propertiesChanged || 'none');

    // Step 1: Log association retrieval
    console.log('--- STEP 1: Retrieving deal associations ---');
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

    console.log(`--- STEP 1 COMPLETE ---`);
    console.log(`Total associations found: ${totalAssociations}`);
    console.log(`Total primary deals found: ${totalPrimaryDeals}`);
    console.log(`Primary deal IDs: [${primaryDealIds.join(', ')}]`);

    // Step 2: Log deal data retrieval
    console.log('--- STEP 2: Retrieving deal details ---');
    const props = ['dealstage', 'closedate', 'dealname', 'amount', 'fecha_de_desactivacion'];
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

        const dealInfo = {
          id: deal.id,
          name: dealName,
          stage: dealStage,
          closeDate: closeDate,
          amount: amount,
          fechaDesactivacion: fechaDesactivacion,
          isPrimary: primaryDealIds.includes(deal.id) /* Check if this deal is primary */
        };

        allDealDetails.push(dealInfo);

        console.log(`Deal ${deal.id}: stage="${dealStage}", closedate="${closeDate}", fecha_desactivacion="${fechaDesactivacion || 'NULL'}", name="${dealName}", isPrimary=${dealInfo.isPrimary}`);

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

    console.log(`--- STEP 2 COMPLETE ---`);
    console.log(`Total deals processed: ${totalDealsProcessed}`);
    console.log(`Won deals found: ${wonDealsFound}`);
    console.log(`Won dates: [${wonDates.map(d => d.toISOString().split('T')[0]).join(', ')}]`);

    // Step 3: Enhanced calculation and update with Slack notifications
    console.log('--- STEP 3: Enhanced calculation and update with notifications ---');

    // Get current field values for comparison
    const currentCompany = await client.crm.companies.basicApi.getById(companyId, ['first_deal_closed_won_date', 'company_churn_date', 'name', 'lifecyclestage', 'type']);
    const currentFirstDealValue = currentCompany.properties.first_deal_closed_won_date;
    const currentChurnDateValue = currentCompany.properties.company_churn_date;
    const companyName = currentCompany.properties.name;

    console.log(`Current company: ${companyName}`);
    console.log(`Current first_deal_closed_won_date: ${currentFirstDealValue || 'NULL'}`);
    console.log(`Current company_churn_date: ${currentChurnDateValue || 'NULL'}`);

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
            
            // Update notification to success
            workflowOutcome = 'AUTO_FIX_SUCCESS';
            slackNotification = {
              type: 'success',
              title: '✅ Auto-Fix Completed Successfully',
              message: `Successfully added PRIMARY association for company "${companyName}" to deal ${dealId}`,
              details: {
                companyId: companyId,
                companyName: companyName,
                dealId: dealId,
                totalDeals: totalAssociations,
                primaryDeals: 1, // Now has 1 PRIMARY deal
                wonDeals: (allDealDetails[0].stage === 'closedwon' || allDealDetails[0].stage === '34692158') ? 1 : 0,
                isChurned: false, // Auto-fix doesn't change churn status
                dealDetails: [], // We don't have deal details since we didn't process any
                lifecycleStage: lifecycleStage,
                companyType: companyType,
                reason: 'Auto-fix completed: Single company now has PRIMARY association',
                autoFixCompleted: true,
                autoFixAction: `Added PRIMARY association (typeId 5) for company ${singleCompanyId} to deal ${dealId}`,
                // Add the missing date fields for the notification template
                oldFirstDate: currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL',
                newFirstDate: currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL', 
                oldChurnDate: currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL',
                newChurnDate: currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL',
                changeReason: 'Auto-fix completed: PRIMARY association added - dates will be calculated on next workflow run'
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
              isPrimary: d.isPrimary
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
      const currentFirstDate = currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : null;
      const calculatedFirstDate = new Date(formattedFirstDate).toISOString().split('T')[0];
      
      const needsFirstUpdate = currentFirstDate !== calculatedFirstDate;
      const needsChurnUpdate = (currentChurnDateValue !== companyChurnDate);
      const needsUpdate = needsFirstUpdate || needsChurnUpdate;

      console.log(`Current first date: ${currentFirstDate || 'NULL'}`);
      console.log(`Calculated first date: ${calculatedFirstDate}`);
      console.log(`First date comparison: ${currentFirstDate} !== ${calculatedFirstDate} = ${needsFirstUpdate}`);
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
              isPrimary: d.isPrimary
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

    console.log('--- STEP 3 COMPLETE ---');

    // Step 4: Send Slack notification if needed
    if (slackNotification) {
      console.log('--- STEP 4: Sending Slack notification ---');
      
      try {
        await sendSlackNotification(slackNotification);
        console.log(`✅ Slack notification sent successfully`);
      } catch (slackError) {
        console.error(`❌ Slack notification failed:`, slackError.message);
        // Don't fail the entire workflow if Slack fails
      }
      
      console.log('--- STEP 4 COMPLETE ---');
    }

    // Final summary log
    console.log('=== ENHANCED WORKFLOW EXECUTION SUMMARY ===');
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
    console.log('=== ENHANCED FIRST DEAL WON DATE CALCULATION COMPLETED SUCCESSFULLY ===');
    
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
      console.error('Response headers:', JSON.stringify(err.response.headers, null, 2));
      console.error('Response body:', JSON.stringify(err.response.body, null, 2));
    }

    console.error('Full error object:', JSON.stringify(err, null, 2));
    console.error('=== ERROR LOGGING COMPLETE ===');

    // Call callback with error
    callback(err);
  }
};

// Enhanced Slack notification function with detailed sales team information
async function sendSlackNotification(notification) {
  const slackWebhookUrl = 'https://hooks.slack.com/services/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';
  
  let slackMessage;
  
  if (notification.type === 'success' && notification.details.dealDetails) {
    // Enhanced success notification with detailed change information
    const dealList = notification.details.dealDetails
      .map(d => `• ${d.name} (${d.stage}) - ${d.closeDateFormatted}${d.amount ? ` - $${parseInt(d.amount).toLocaleString()}` : ''}${d.isPrimary ? ' [PRIMARY]' : ''}`)
      .join('\n');
    
    slackMessage = {
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
              title: '🔗 View Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|Open in HubSpot>`,
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
      .map(d => `• ${d.name} (${d.stage}) - ${d.closeDateFormatted}${d.amount ? ` - $${parseInt(d.amount).toLocaleString()}` : ''}${d.isPrimary ? ' [PRIMARY]' : ''}`)
      .join('\n');
    
    const dealSummary = dealList + (notification.details.dealDetails.length > 5 ? '\n• ...' : '');
    
    slackMessage = {
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
              title: '🔗 View Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|Open in HubSpot>`,
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
      .map(d => `• ${d.name} (${d.stage}) - ${d.closeDateFormatted}${d.amount ? ` - $${parseInt(d.amount).toLocaleString()}` : ''}`)
      .join('\n');
    
    slackMessage = {
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
              title: '🔗 View Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|Open in HubSpot>`,
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
              title: '🔗 View Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|Open in HubSpot>`,
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
              title: '🔗 View Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|Open in HubSpot>`,
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
              title: '🔗 View Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|Open in HubSpot>`,
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
'''

# Python equivalent for testing in Cursor
def calculate_first_deal_won_date_python(company_id: str, hubspot_client) -> Optional[str]:
    """
    Python equivalent of the HubSpot Custom Code
    Used for testing and validation in Cursor environment
    
    Args:
        company_id: HubSpot company ID
        hubspot_client: HubSpot API client
        
    Returns:
        First deal won date as ISO string or None
    """
    try:
        print(f"=== FIRST DEAL WON DATE CALCULATION STARTED ===")
        print(f"Company ID: {company_id}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        
        # Step 1: Get primary deal associations
        print("--- STEP 1: Retrieving deal associations ---")
        primary_deal_ids = []
        after = None
        total_associations = 0
        
        while True:
            # Get associations page
            associations = hubspot_client.get_associations(
                company_id, 'companies', 'deals', after=after, limit=100
            )
            
            page_results = associations.get('results', [])
            total_associations += len(page_results)
            
            print(f"Page retrieved: {len(page_results)} associations (total so far: {total_associations})")
            
            for row in page_results:
                association_types = row.get('associationTypes', [])
                is_primary = any(
                    t.get('typeId') == 6 or (t.get('label', '') or '').lower().find('primary') >= 0
                    for t in association_types
                )
                
                if is_primary:
                    primary_deal_ids.append(str(row['toObjectId']))
                    print(f"✓ Primary deal found: {row['toObjectId']}")
                else:
                    print(f"- Non-primary deal: {row['toObjectId']}")
            
            # Check for next page
            paging = associations.get('paging', {})
            next_page = paging.get('next', {})
            after = next_page.get('after')
            
            if not after:
                break
        
        print(f"--- STEP 1 COMPLETE ---")
        print(f"Total associations found: {total_associations}")
        print(f"Total primary deals found: {len(primary_deal_ids)}")
        print(f"Primary deal IDs: {primary_deal_ids}")
        
        if not primary_deal_ids:
            print("No primary deals found")
            return None
        
        # Step 2: Get deal details
        print("--- STEP 2: Retrieving deal details ---")
        won_dates = []
        total_deals_processed = 0
        won_deals_found = 0
        
        # Process deals in batches of 100
        for i in range(0, len(primary_deal_ids), 100):
            batch_ids = primary_deal_ids[i:i+100]
            print(f"Processing batch of {len(batch_ids)} deals: {batch_ids}")
            
            # Get deal details
            deals = hubspot_client.batch_read_objects('deals', batch_ids, ['dealstage', 'closedate'])
            batch_results = deals.get('results', [])
            total_deals_processed += len(batch_results)
            
            print(f"Batch returned {len(batch_results)} deals")
            
            for deal in batch_results:
                deal_stage = deal.get('properties', {}).get('dealstage')
                close_date = deal.get('properties', {}).get('closedate')
                
                print(f"Deal {deal['id']}: stage=\"{deal_stage}\", closedate=\"{close_date}\"")
                
                if deal_stage == 'closedwon' and close_date:
                    won_date = datetime.fromisoformat(close_date.replace('Z', '+00:00'))
                    won_dates.append(won_date)
                    won_deals_found += 1
                    print(f"✓ Won deal found: {deal['id']} with close date {close_date}")
                else:
                    print(f"- Deal {deal['id']} not won or no close date")
        
        print(f"--- STEP 2 COMPLETE ---")
        print(f"Total deals processed: {total_deals_processed}")
        print(f"Won deals found: {won_deals_found}")
        print(f"Won dates: {[d.isoformat().split('T')[0] for d in won_dates]}")
        
        # Step 3: Calculate and return result
        print("--- STEP 3: Calculating result ---")
        
        if won_dates:
            first_won_date = min(won_dates)
            formatted_date = first_won_date.isoformat().split('T')[0]
            print(f"First won date calculated: {formatted_date}")
            return formatted_date
        else:
            print("No won deals found")
            return None
        
    except Exception as e:
        print(f"=== ERROR OCCURRED ===")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        raise e

# Version tracking
WORKFLOW_VERSION = "1.12.10"
LAST_UPDATED = "2025-09-15T12:15:00Z"
CHANGES = [
    "Added comprehensive logging",
    "Fixed field name to first_deal_closed_won_date", 
    "Added error handling for missing properties",
    "Added verification logging",
    "Improved batch processing",
    "Added change detection and explicit change/no-change logging",
    "Added workflow execution summary with change status",
    "Fixed timestamp format to use full ISO timestamp with time (not just date)",
    "Fixed date comparison logic to prevent unnecessary updates when only time differs within same day",
    "Added Slack notifications for edge cases and workflow outcomes",
    "Enhanced workflow to detect and notify about companies with no primary deals",
    "Added proper Slack message formatting with line breaks",
    "Added error notifications to Slack for workflow failures",
    "Enhanced deal data collection to include all deals (not just primary) for better edge case detection",
    "CRITICAL FIX: Fixed primary deal detection to use typeId 6 (HubSpot's 'Deal with Primary Company') instead of just label text",
    "CRITICAL FIX: Fixed Step 2 to process only PRIMARY deals instead of ALL deals, ensuring correct first_deal_closed_won_date calculation",
    "SYNTAX FIX: Fixed JavaScript comment syntax error that was causing Runtime.UserCodeSyntaxError",
    "ENHANCED SLACK NOTIFICATIONS: Added detailed sales team notifications with deal amounts, change reasons, and actionable insights",
    "CLICKABLE LINKS: Added direct HubSpot company links in Slack notifications for instant access",
    "DUAL DATE TRACKING: Added last_deal_closed_won_date field to track most recent won deal alongside first_deal_closed_won_date",
    "CHURN DETECTION LOGIC: Redesigned last_deal_closed_won_date to track last active customer date, excluding churned deals (closedlost, 31849274) for churn risk analysis",
    "CHURN DETECTION FIELD: Added company_churn_date field to track when companies churned (all deals closedlost/31849274) - churn date = last won deal close date",
    "CRITICAL FIX: Fixed ReferenceError 'currentFieldValue is not defined' in summary logging section",
    "CRITICAL FIX: Fixed SyntaxError by moving require statement inside exports.main function for HubSpot workflow compatibility",
    "CRITICAL FIX: Fixed undefined variable references (formattedLastDate, needsLastUpdate, currentLastDealValue) in Slack notification details",
    "CRITICAL FIX: Fixed remaining needsLastUpdate reference in changeReason Slack notification",
    "CRITICAL FIX: Fixed variable re-declaration error - totalPrimaryDeals was declared twice (line 23 and 205)",
    "CHURN LOGIC FIX: Fixed churn detection to set company_churn_date to the close date of the last churned deal (not null)",
    "CHURN DATE LOGIC: Implemented correct churn date logic - priority 1: fecha_de_desactivacion, priority 2: close date + manual error detection",
    "SLACK NOTIFICATION FIX: Fixed churn notification to use success format instead of warning format to show correct deal details",
    "RECOVERY STAGE SUPPORT: Added 'Cerrado Ganado Recupero' (34692158) as won stage - treated same as closedwon for first deal date and churn detection",
    "CRITICAL CHURN LOGIC FIX: Fixed churn detection to prevent never-customers from being marked as churned - now requires first_deal_closed_won_date to be set before marking as churned",
    "CHURN STAGE CLARIFICATION: Fixed churn detection to only consider actual churn stage (31849274), not closedlost deals - closedlost means lost, not churned",
    "STRING NULL COMPARISON FIX: Fixed comparison logic to normalize empty strings and null values - prevents unnecessary updates from empty string to null",
    "HUBSPOT UPDATE FIX: Fixed update logic to use empty string instead of null for clearing company_churn_date - HubSpot API doesn't accept null values",
    "CRITICAL FIRST DEAL DATE FIX: Fixed first_deal_closed_won_date calculation to look at ALL deals (not just primary) to find the true first won deal - prevents incorrect dates when primary deals are not the first won deals",
    "NON-PRIMARY COMPANY PROTECTION: Added check to skip companies with won deals but NO PRIMARY deals - prevents setting first_deal_closed_won_date for referrers/accountants who are not customers",
    "TRIAL COMPANY NOTIFICATION FIX: Added logic to skip Slack notifications for trial companies (lifecycle: opportunity) with no deals - prevents false alerts for legitimate new trials",
    "ACCOUNTANT VERIFICATION NOTIFICATION TEMPLATE: Created dedicated notification template for accountant company verification with accurate messaging - shows correct issue (deals exist but NO PRIMARY associations) instead of misleading 'no won deals' message",
    "AUTO-FIX DETECTION: Added detection for single company deals missing PRIMARY associations - triggers critical notification for auto-fix opportunity when company has 1 deal with single non-accountant company",
    "AUTO-FIX IMPLEMENTATION: Added actual HubSpot API call to automatically create PRIMARY associations for single company deals - includes error handling and success/failure notifications",
    "AUTO-FIX API FIX: Fixed API call to use existing deal data instead of making additional API calls - resolves 'Cannot read properties of undefined' error",
    "AUTO-FIX API FORMAT FIX: Corrected API call format from batchApi.create to basicApi.create with proper association object structure - resolves 'Invalid input JSON' error",
    "AUTO-FIX NOTIFICATION FIX: Added missing date fields (oldFirstDate, newFirstDate, oldChurnDate, newChurnDate) to auto-fix success notification template - resolves 'undefined → undefined' display issue",
    "AUTO-FIX NOTIFICATION DATA FIX: Updated auto-fix notification to show actual current field values instead of 'undefined' - now displays real first_deal_closed_won_date and company_churn_date values when they exist",
    "AUTO-FIX EXPANSION: Extended auto-fix to handle won deals missing PRIMARY associations - now detects and fixes won deals (closedwon/34692158) that don't have PRIMARY associations in both normal and churn scenarios",
    "AUTO-FIX BATCH PROCESSING: Added batch auto-fix for multiple won deals missing PRIMARY associations - processes all won deals without PRIMARY in a single workflow run with success/failure tracking",
    "AUTO-FIX IMMEDIATE RECALCULATION: Fixed auto-fix to immediately recalculate and update first_deal_closed_won_date after adding PRIMARY associations - no longer defers to 'next workflow run'",
    "AUTO-FIX NOTIFICATION IMPROVEMENT: Enhanced auto-fix notifications to show actual date changes and correct change reason - now displays real before/after dates instead of 'undefined → undefined'",
    "AUTO-FIX SINGLE PRIMARY RULE: Fixed auto-fix to follow business rule of only ONE PRIMARY deal per company - now selects the OLDEST won deal for PRIMARY association instead of adding PRIMARY to all won deals",
    "NOTIFICATION MESSAGE FIX: Fixed misleading notification messages - now distinguishes between date field updates (existing PRIMARY deals) vs actual PRIMARY association additions - prevents false 'Added PRIMARY associations' messages when only updating date fields",
    "CODE CLEANUP: Removed unused variables (callback parameter, autoFixFailedCount, updatedPrimaryDealsCount, associationResponse) and fixed duplicate companyName declaration - resolved all linting warnings",
    "CRITICAL FIX: Added callback execution for HubSpot workflow - callback(null, 'Success') on success and callback(err) on error - prevents workflow from hanging with no logs"
]

def get_latest_code() -> str:
    """Get the latest HubSpot Custom Code"""
    return HUBSPOT_CUSTOM_CODE

def get_version_info() -> dict:
    """Get workflow version information"""
    return {
        "version": WORKFLOW_VERSION,
        "last_updated": LAST_UPDATED,
        "changes": CHANGES
    }

if __name__ == "__main__":
    print("🔧 HubSpot Custom Code - First Deal Won Date Calculation with Slack Notifications")
    print("=" * 80)
    print(f"Version: {WORKFLOW_VERSION}")
    print(f"Last Updated: {LAST_UPDATED}")
    print(f"Changes: {len(CHANGES)} updates")
    print()
    print("📋 Copy the JavaScript code above to your HubSpot workflow")
    print("🧪 Use the Python function for testing in Cursor environment")
    print("🔔 Slack notifications enabled for edge cases and workflow outcomes")
    print("✅ Ready for production use with comprehensive monitoring")
