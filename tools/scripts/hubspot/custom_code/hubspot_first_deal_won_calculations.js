// =============================================================================
// HubSpot Custom Code - First Deal Won Date Calculation with Slack Notifications
// =============================================================================
// source: hubspot_first_deal_won_calculations.js
// URL in hubspot automation: https://app.hubspot.com/workflows/19877595/platform/flow/1693911922/edit/actions/1/custom-code
// VERSION: 1.8.0
// LAST UPDATED: 2025-12-30
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

  // Helper function to get when dealstage was first set to closedwon
  // This is used when closedate is missing, future date, or equals deal creation date
  async function getDealStageClosedWonTimestamp(dealId) {
    console.log(`🔍 DEALSTAGE HISTORY: Fetching dealstage history for deal ${dealId}`);
    
    try {
      const response = await fetch(`https://api.hubspot.com/crm/v3/objects/deals/${dealId}?propertiesWithHistory=dealstage`, {
        headers: {
          'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        console.log(`⚠️ DEALSTAGE HISTORY: API error ${response.status} for deal ${dealId}`);
        return null;
      }
      
      const data = await response.json();
      const propertiesWithHistory = data.propertiesWithHistory || {};
      const dealstageHistory = propertiesWithHistory.dealstage;
      
      if (!dealstageHistory) {
        console.log(`⚠️ DEALSTAGE HISTORY: No history found for deal ${dealId}`);
        return null;
      }
      
      // Property history format: can be a list of versions directly, or a dict with "versions" key
      let history = [];
      if (Array.isArray(dealstageHistory)) {
        history = dealstageHistory;
      } else if (dealstageHistory && typeof dealstageHistory === 'object' && dealstageHistory.versions) {
        history = dealstageHistory.versions;
      }
      
      if (history.length === 0) {
        console.log(`⚠️ DEALSTAGE HISTORY: Empty history for deal ${dealId}`);
        return null;
      }
      
      // Find when dealstage was first set to closedwon or recovery (34692158)
      const closedWonStages = ['closedwon', '34692158'];
      for (const entry of history) {
        const value = entry.value;
        if (value && closedWonStages.includes(value)) {
          const timestamp = entry.timestamp;
          // HubSpot returns timestamp as ISO string, not Unix timestamp
          // Use it directly with Date constructor
          const timestampDate = new Date(timestamp);
          if (isNaN(timestampDate.getTime())) {
            console.log(`⚠️ DEALSTAGE HISTORY: Invalid timestamp format '${timestamp}' for deal ${dealId}`);
            continue;
          }
          console.log(`✅ DEALSTAGE HISTORY: Deal ${dealId} was first set to ${value} on ${timestampDate.toISOString()}`);
          return {
            timestamp: timestamp,
            timestampDate: timestampDate.toISOString(),
            timestampDateOnly: timestampDate.toISOString().split('T')[0],
            stage: value
          };
        }
      }
      
      console.log(`⚠️ DEALSTAGE HISTORY: No closedwon stage found in history for deal ${dealId}`);
      return null;
      
    } catch (error) {
      console.error(`❌ DEALSTAGE HISTORY ERROR: Deal ${dealId} - ${error.message}`);
      return null;
    }
  }

  // Helper function to get earliest close date from deal property history
  // This finds when the deal was FIRST set to closed won, not the current closedate value
  async function getEarliestCloseDateFromHistory(dealId) {
    console.log(`🔍 CLOSE DATE HISTORY: Fetching property history for deal ${dealId}`);
    
    try {
      const response = await fetch(`https://api.hubspot.com/crm/v3/objects/deals/${dealId}?propertiesWithHistory=closedate`, {
        headers: {
          'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        console.log(`⚠️ CLOSE DATE HISTORY: API error ${response.status} for deal ${dealId}`);
        return null;
      }
      
      const data = await response.json();
      const propertiesWithHistory = data.propertiesWithHistory || {};
      const closedateHistory = propertiesWithHistory.closedate;
      
      if (!closedateHistory) {
        console.log(`⚠️ CLOSE DATE HISTORY: No history found for deal ${dealId}`);
        return null;
      }
      
      // Property history format: can be a list of versions directly, or a dict with "versions" key
      let history = [];
      if (Array.isArray(closedateHistory)) {
        history = closedateHistory;
      } else if (closedateHistory && typeof closedateHistory === 'object' && closedateHistory.versions) {
        history = closedateHistory.versions;
      }
      
      if (history.length === 0) {
        console.log(`⚠️ CLOSE DATE HISTORY: Empty history for deal ${dealId}`);
        return null;
      }
      
      // Collect all valid close dates from history
      const validDates = [];
      for (const entry of history) {
        const value = entry.value;
        if (value && value.trim() && value.trim().toLowerCase() !== 'null') {
          try {
            const dateObj = new Date(value);
            if (!isNaN(dateObj.getTime())) {
              validDates.push({
                date: dateObj,
                dateIso: dateObj.toISOString(),
                dateOnly: dateObj.toISOString().split('T')[0],
                timestamp: entry.timestamp,
                sourceType: entry.sourceType,
                sourceId: entry.sourceId,
                value: value
              });
            }
          } catch (e) {
            console.log(`   ⚠️ Could not parse date '${value}' for deal ${dealId}: ${e.message}`);
            continue;
          }
        }
      }
      
      if (validDates.length === 0) {
        console.log(`⚠️ CLOSE DATE HISTORY: No valid dates found in history for deal ${dealId}`);
        return null;
      }
      
      // Sort by date (earliest first) - this is the FIRST time the deal was closed
      validDates.sort((a, b) => a.date - b.date);
      const earliest = validDates[0];
      
      console.log(`✅ CLOSE DATE HISTORY: Earliest close date for deal ${dealId} is ${earliest.dateOnly} (from history)`);
      console.log(`   Total history entries: ${history.length}, Valid dates: ${validDates.length}`);
      
      return {
        date: earliest.dateIso,
        dateOnly: earliest.dateOnly,
        timestamp: earliest.timestamp,
        sourceType: earliest.sourceType,
        sourceId: earliest.sourceId
      };
      
    } catch (error) {
      console.error(`❌ CLOSE DATE HISTORY ERROR: Deal ${dealId} - ${error.message}`);
      return null;
    }
  }

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
    // Handle both test mode and production mode event structures
    const companyId = event.object?.objectId || event.inputFields?.objectId || event.objectId;
    
    if (!companyId) {
      const errorMsg = 'Company ID not found in event object. Event structure: ' + JSON.stringify(event, null, 2);
      console.error('❌ MISSING COMPANY ID:', errorMsg);
      callback(new Error(errorMsg));
      return;
    }
    
    const companyIdString = String(companyId);

    console.log('='.repeat(80));
    console.log('🚀 ENHANCED FIRST DEAL WON DATE CALCULATION STARTED');
    console.log('='.repeat(80));
    console.log('📋 WORKFLOW INFO:');
    console.log(`   Company ID: ${companyIdString}`);
    console.log(`   Timestamp: ${new Date().toISOString()}`);
    console.log(`   Event Type: ${event.eventType || 'unknown'}`);
    console.log(`   Properties Changed: ${event.propertiesChanged || 'none'}`);
    console.log(`   Event Object Keys: ${Object.keys(event).join(', ')}`);
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
        'company', companyIdString, 'deal', after, 100
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
    const props = ['dealstage', 'closedate', 'dealname', 'amount', 'fecha_de_desactivacion', 'fecha_pedido_baja', 'hubspot_owner_id', 'createdate'];
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
        const fechaPedidoBaja = deal.properties.fecha_pedido_baja; // This is the actual churn date field
        const ownerId = deal.properties.hubspot_owner_id;
        const dealCreatedDate = deal.properties.createdate || deal.createdAt;

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

        // CRITICAL: Check if closedate needs to be corrected
        // Sales people should manually update closedate when setting deal to closedwon
        // If closedate is missing, future date, or equals deal creation date, use dealstage timestamp
        let historicalCloseDate = closeDate;
        const isChurned = (dealStage === '31849274');
        const isClosedWon = (dealStage === 'closedwon' || dealStage === '34692158');
        const today = new Date();
        today.setHours(23, 59, 59, 999); // End of today
        let needsCorrection = false;
        
        // Check if closedate needs correction for closed won deals
        if (isClosedWon) {
          let correctionReason = '';
          
          // Check if closedate is missing
          if (!closeDate || closeDate.trim() === '') {
            needsCorrection = true;
            correctionReason = 'closedate is missing';
          } 
          // Check if closedate is a future date
          else {
            const closeDateObj = new Date(closeDate);
            if (closeDateObj > today) {
              needsCorrection = true;
              correctionReason = `closedate is a future date (${closeDate})`;
            }
            // Check if closedate equals deal creation date (default value, not manually updated)
            else if (dealCreatedDate) {
              const createdDateObj = new Date(dealCreatedDate);
              const createdDateOnly = createdDateObj.toISOString().split('T')[0];
              const closeDateOnly = closeDateObj.toISOString().split('T')[0];
              if (createdDateOnly === closeDateOnly) {
                needsCorrection = true;
                correctionReason = `closedate equals deal creation date (${closeDateOnly}) - not manually updated`;
              }
            }
          }
          
          if (needsCorrection) {
            console.log(`⚠️ CLOSEDATE CORRECTION NEEDED: Deal ${deal.id} - ${correctionReason}`);
            console.log(`🔍 DEALSTAGE TIMESTAMP: Fetching timestamp when deal was first set to closedwon`);
            
            const stageTimestamp = await getDealStageClosedWonTimestamp(deal.id);
            if (stageTimestamp && stageTimestamp.timestampDate) {
              historicalCloseDate = stageTimestamp.timestampDate;
              console.log(`✅ CLOSEDATE CORRECTED: Using dealstage timestamp ${stageTimestamp.timestampDateOnly} (when deal was first set to ${stageTimestamp.stage})`);
            } else {
              console.log(`⚠️ CLOSEDATE CORRECTION: Could not get dealstage timestamp for deal ${deal.id}, using current closedate ${closeDate}`);
            }
          }
        }
        
        // CRITICAL: For churned deals, check if closeDate has data quality issues
        // Determine effective churn date: fecha_pedido_baja (primary) or fecha_de_desactivacion (fallback)
        // If closeDate equals effective churn date OR closeDate is after effective churn date,
        // get historical closeDate from when deal was FIRST set to closed won
        // This handles cases where the closeDate was incorrectly updated
        // Skip this check if we already corrected the closedate above
        if (isChurned && closeDate && !needsCorrection) {
          // Determine effective churn date: fecha_pedido_baja (primary) or fecha_de_desactivacion (fallback)
          const effectiveChurnDate = fechaPedidoBaja && fechaPedidoBaja.trim() !== '' 
            ? fechaPedidoBaja 
            : (fechaDesactivacion && fechaDesactivacion.trim() !== '' ? fechaDesactivacion : null);
          
          // Normalize dates for comparison (date-only, ignore time)
          const closeDateOnly = closeDate ? new Date(closeDate).toISOString().split('T')[0] : null;
          const effectiveChurnDateOnly = effectiveChurnDate ? new Date(effectiveChurnDate).toISOString().split('T')[0] : null;
          
          // Check for data quality issues:
          // 1. closeDate equals effective churn date (fecha_pedido_baja or fecha_de_desactivacion)
          // 2. closeDate is after effective churn date - indicates incorrect closeDate
          const equalsChurnDate = effectiveChurnDateOnly && closeDateOnly === effectiveChurnDateOnly;
          const afterChurnDate = effectiveChurnDateOnly && closeDateOnly && new Date(closeDateOnly) > new Date(effectiveChurnDateOnly);
          
          if (equalsChurnDate || afterChurnDate) {
            const churnDateSource = fechaPedidoBaja && fechaPedidoBaja.trim() !== '' ? 'fecha_pedido_baja' : 'fecha_de_desactivacion';
            const issueType = equalsChurnDate 
              ? `closeDate (${closeDateOnly}) equal to ${churnDateSource} (${effectiveChurnDateOnly})`
              : `closeDate (${closeDateOnly}) is AFTER ${churnDateSource}/churn date (${effectiveChurnDateOnly})`;
            
            console.log(`⚠️ DATA QUALITY ISSUE: Deal ${deal.id} has ${issueType}`);
            console.log(`🔍 HISTORICAL CLOSE DATE: Fetching historical closeDate from when deal was FIRST set to closed won`);
            
            const historyResult = await getEarliestCloseDateFromHistory(deal.id);
            if (historyResult && historyResult.date) {
              historicalCloseDate = historyResult.date;
              console.log(`✅ HISTORICAL CLOSE DATE: Using historical date ${historyResult.dateOnly} (when deal was first won) instead of incorrect closeDate ${closeDateOnly}`);
            } else {
              console.log(`⚠️ HISTORICAL CLOSE DATE: Could not get history for deal ${deal.id}, using current closedate ${closeDate}`);
            }
          } else {
            console.log(`✅ CLOSE DATE OK: Deal ${deal.id} closeDate (${closeDateOnly}) appears valid - using current closedate`);
          }
        }

        const dealInfo = {
          id: deal.id,
          name: dealName,
          stage: dealStage,
          closeDate: historicalCloseDate, // Use historical date if available, otherwise current
          amount: amount,
          fechaDesactivacion: fechaDesactivacion,
          fechaPedidoBaja: fechaPedidoBaja, // This is the actual churn date field (Fecha pedido baja)
          ownerId: ownerId,
          ownerName: dealOwnerName,
          isPrimary: primaryDealIds.includes(deal.id) /* Check if this deal is primary */
        };

        allDealDetails.push(dealInfo);

        const fechaDesactivacionDisplay = fechaDesactivacion || 'NULL';
        const closeDateDisplay = historicalCloseDate || 'NULL';
        console.log(`Deal ${deal.id}: stage="${dealStage}", closedate="${closeDateDisplay}"${historicalCloseDate !== closeDate ? ' (from history)' : ''}, fecha_desactivacion="${fechaDesactivacionDisplay}", name="${dealName}", isPrimary=${dealInfo.isPrimary}`);

        if ((dealStage === 'closedwon' || dealStage === '34692158') && historicalCloseDate) {
          const wonDate = new Date(historicalCloseDate);
          wonDates.push(wonDate);
          wonDealsFound++;
          console.log(`✓ Won deal found: ${deal.id} with close date ${historicalCloseDate}${historicalCloseDate !== closeDate ? ' (from history)' : ''}`);
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
    const currentCompany = await client.crm.companies.basicApi.getById(companyIdString, ['first_deal_closed_won_date', 'company_churn_date', 'name', 'lifecyclestage', 'type', 'hubspot_owner_id']);
    let currentFirstDealValue = currentCompany.properties.first_deal_closed_won_date;
    let currentChurnDateValue = currentCompany.properties.company_churn_date;
    const companyName = currentCompany.properties.name;
    
    // Track whether first_deal_closed_won_date was cleared during this workflow execution
    let firstDealDateWasCleared = false;
    
     // Get company owner name using the helper function with detailed logging
     console.log(`🔍 COMPANY OWNER RESOLUTION: Processing company ${companyIdString}`);
     let companyOwnerName = 'No Owner';
     if (currentCompany.properties.hubspot_owner_id) {
       console.log(`👤 COMPANY OWNER: Resolving owner ID ${currentCompany.properties.hubspot_owner_id} for company ${companyIdString}`);
       companyOwnerName = await getOwnerName(currentCompany.properties.hubspot_owner_id);
       console.log(`✅ COMPANY OWNER RESOLVED: "${companyOwnerName}" for company ${companyIdString}`);
     } else {
       console.log(`❌ COMPANY OWNER: No owner ID found for company ${companyIdString}`);
     }

    console.log(`Current company: ${companyName}`);
    const currentFirstDate = currentFirstDealValue || 'NULL';
    const currentChurnDate = currentChurnDateValue || 'NULL';
    console.log(`Current first_deal_closed_won_date: ${currentFirstDate}`);
    console.log(`Current company_churn_date: ${currentChurnDate}`);

    // ========================================================================
    // CRITICAL VALIDATION: If company has churn_date, it MUST have PRIMARY deals
    // ========================================================================
    // Business Rule: A company with churn_date was a customer (had PRIMARY deals)
    // If company has churn_date but NO PRIMARY deals → clear churn_date (not a customer, just a channel partner/accountant)
    const hasChurnDate = currentChurnDateValue && currentChurnDateValue.trim() !== '';
    const hasPrimaryDeals = primaryDealIds.length > 0;
    const missingFirstDealDate = !currentFirstDealValue || currentFirstDealValue.trim() === '';
    
    // Track if churn_date was cleared for notification purposes
    let churnDateWasCleared = false;
    const originalChurnDateValue = currentChurnDateValue;
    
    // CRITICAL: If company has churn_date but NO PRIMARY deals, it's NOT a customer
    // Clear churn_date because company was never a customer (just an accountant/referrer)
    if (hasChurnDate && !hasPrimaryDeals) {
      console.log(`⚠️ DATA INCONSISTENCY DETECTED: Company has churn_date (${currentChurnDateValue}) but NO PRIMARY deals`);
      console.log(`🔧 AUTO-FIX: Clearing churn_date - company is not a customer (no PRIMARY deals), just a channel partner/accountant`);
      console.log(`   Company was never billed - it's an external accountant/referrer, not a customer`);
      
      try {
        await client.crm.companies.basicApi.update(companyIdString, {
          properties: {
            company_churn_date: ""
          }
        });
        
        console.log(`✅ CHURN DATE CLEARED: company_churn_date set to NULL`);
        console.log(`   Company is not a customer (no PRIMARY deals) - churn_date should not exist`);
        
        // Update currentChurnDateValue for subsequent logic
        currentChurnDateValue = null;
        churnDateWasCleared = true;
        
      } catch (updateError) {
        console.error(`❌ CHURN DATE CLEAR FAILED: ${updateError.message}`);
        // Continue with workflow even if update fails
      }
    }
    
    // If company has churn_date AND PRIMARY deals, calculate first_deal_closed_won_date if missing OR incorrect
    if (hasChurnDate && hasPrimaryDeals) {
      // Check if first_deal_closed_won_date is missing or incorrect (e.g., after churn date)
      let needsFirstDealCalculation = missingFirstDealDate;
      
      if (!missingFirstDealDate && currentChurnDateValue) {
        // Check if current first_deal_closed_won_date is after churn date (data quality issue)
        try {
          const currentFirstDateParsed = new Date(currentFirstDealValue);
          const churnDateParsed = new Date(currentChurnDateValue);
          if (currentFirstDateParsed > churnDateParsed) {
            needsFirstDealCalculation = true;
            console.log(`⚠️ DATA QUALITY ISSUE: Company has first_deal_closed_won_date (${currentFirstDealValue}) that is AFTER churn_date (${currentChurnDateValue})`);
            console.log(`🔧 AUTO-FIX: Will recalculate first_deal_closed_won_date from PRIMARY deals`);
          }
        } catch (e) {
          // Date parsing failed, skip this check
        }
      }
      
      if (needsFirstDealCalculation) {
        const issueType = missingFirstDealDate 
          ? 'first_deal_closed_won_date is NULL'
          : 'first_deal_closed_won_date is incorrect (after churn_date)';
        console.log(`⚠️ DATA INCONSISTENCY DETECTED: Company has churn_date (${currentChurnDateValue}) but ${issueType}`);
        console.log(`🔧 AUTO-FIX: Calculating first_deal_closed_won_date from PRIMARY deals (closed won OR churned)`);
        console.log(`📋 Looking through ${allDealDetails.length} associated deals to find PRIMARY closed won/churned deals`);
        
        // Find ALL deals that are closed won (closedwon/34692158) OR churned (31849274) where company is PRIMARY
        // CRITICAL: Company must be PRIMARY to the deal for it to count as first_deal_closed_won_date
        // For churned companies, we also need to consider churned deals (they were customers before churning)
        const primaryClosedWonOrChurnedDeals = allDealDetails.filter(d => {
          const isClosedWon = (d.stage === 'closedwon' || d.stage === '34692158');
          const isChurned = (d.stage === '31849274');
          const isPrimary = primaryDealIds.includes(d.id);
          const hasCloseDate = d.closeDate && d.closeDate.trim() !== '';
          return (isClosedWon || isChurned) && isPrimary && hasCloseDate;
        });
        
        console.log(`📊 Found ${primaryClosedWonOrChurnedDeals.length} PRIMARY closed won/churned deals`);
        
        if (primaryClosedWonOrChurnedDeals.length > 0) {
          // Sort by closeDate and get the earliest
          const sortedPrimaryDeals = primaryClosedWonOrChurnedDeals.sort((a, b) => 
            new Date(a.closeDate) - new Date(b.closeDate)
          );
          const earliestDeal = sortedPrimaryDeals[0];
          
          const calculatedFirstDealDate = new Date(earliestDeal.closeDate).toISOString();
          
          console.log(`✅ CALCULATED: first_deal_closed_won_date = ${calculatedFirstDealDate}`);
          console.log(`   From PRIMARY deal: ${earliestDeal.name} (ID: ${earliestDeal.id})`);
          console.log(`   Stage: ${earliestDeal.stage}, CloseDate: ${earliestDeal.closeDate}`);
          
          // Only update if the calculated date is different from current value
          const needsUpdate = !currentFirstDealValue || 
                             new Date(calculatedFirstDealDate).toISOString().split('T')[0] !== 
                             new Date(currentFirstDealValue).toISOString().split('T')[0];
          
          if (needsUpdate) {
            try {
              await client.crm.companies.basicApi.update(companyIdString, {
                properties: {
                  first_deal_closed_won_date: calculatedFirstDealDate
                }
              });
              
              const updateType = missingFirstDealDate ? 'set' : 'corrected';
              console.log(`✅ FIELD ${updateType.toUpperCase()}: first_deal_closed_won_date ${updateType} to ${calculatedFirstDealDate} for company with churn_date`);
              console.log(`   Company was a customer (had PRIMARY closed won/churned deals)`);
              
              // Update currentFirstDealValue for subsequent logic
              currentFirstDealValue = calculatedFirstDealDate;
              
            } catch (updateError) {
              console.error(`❌ FIELD UPDATE FAILED: ${updateError.message}`);
              // Continue with workflow even if update fails
            }
          } else {
            console.log(`✅ FIELD ALREADY CORRECT: first_deal_closed_won_date is already set to the correct value`);
          }
        } else {
          console.log(`⚠️ WARNING: Company has churn_date and PRIMARY deals, but NO PRIMARY closed won/churned deals found`);
          console.log(`   Total deals checked: ${allDealDetails.length}`);
          console.log(`   PRIMARY deals found: ${primaryDealIds.length}`);
          console.log(`   This might indicate a data quality issue`);
        }
      }
    }

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
        
        // Determine notification title and message based on whether churn_date was cleared
        const notificationTitle = churnDateWasCleared 
          ? '🔍 Accountant Company Verification + Churn Date Cleared'
          : '🔍 Accountant Company Verification Needed';
        
        const notificationMessage = churnDateWasCleared
          ? `Accountant company "${companyName}" had churn_date but NO PRIMARY deals - cleared churn_date (not a customer, just a referrer). Has ${totalAssociations} deals but NO PRIMARY associations.`
          : `Accountant company "${companyName}" has ${totalAssociations} deals but NO PRIMARY associations. Please verify this is a legitimate accountant referral.`;
        
        workflowOutcome = churnDateWasCleared 
          ? 'ACCOUNTANT_CHURN_DATE_CLEARED_NO_PRIMARY_DEALS'
          : 'ACCOUNTANT_COMPANY_VERIFICATION';
        
        // Special notification for accountant companies
        slackNotification = {
          type: churnDateWasCleared ? 'success' : 'accountant_verification',
          title: notificationTitle,
          message: notificationMessage,
          details: {
            companyId: companyIdString,
            companyName: companyName,
            companyOwnerId: currentCompany.properties.hubspot_owner_id,
            companyOwnerName: companyOwnerName,
            totalDeals: totalAssociations,
            primaryDeals: 0,
            dealDetails: [], // We don't have deal details since we didn't process any
            lifecycleStage: lifecycleStage,
            companyType: companyType,
            reason: churnDateWasCleared
              ? 'Accountant company had churn_date but no PRIMARY deals - cleared churn_date (not a customer, just a referrer)'
              : 'Accountant companies refer clients but typically don\'t get PRIMARY deals - verification needed to confirm this is normal',
            // Include churn date change if it was cleared
            oldChurnDate: churnDateWasCleared && originalChurnDateValue 
              ? new Date(originalChurnDateValue).toISOString().split('T')[0] 
              : (currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL'),
            newChurnDate: churnDateWasCleared ? 'NULL' : (currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL'),
            churnDateCleared: churnDateWasCleared,
            changeReason: churnDateWasCleared
              ? 'Company has churn_date but NO PRIMARY deals - cleared churn_date (not a customer, just a channel partner/accountant)'
              : undefined
          }
        };
        
        // CRITICAL: Do NOT clear first_deal_closed_won_date if company has churn_date
        // A company with churn_date was a customer and MUST have first_deal_closed_won_date
        // The validation above should have already set it if it was missing
        if (hasChurnDate && !churnDateWasCleared) {
          console.log(`✅ ACCOUNTANT WITH CHURN DATE: Company has churn_date (${currentChurnDateValue}) - first_deal_closed_won_date should be set (validation above should have handled it)`);
          workflowOutcome = 'ACCOUNTANT_NO_CHANGE_NEEDED_NO_PRIMARY_DEALS';
        } else {
          // Only clear first_deal_closed_won_date if company has NO churn_date (not a customer)
          if (currentFirstDealValue) {
            console.log(`🧹 CLEARING FIELD: No primary deals found for accountant company (no churn_date) - clearing first_deal_closed_won_date from "${currentFirstDealValue}" to NULL`);
            
            try {
              await client.crm.companies.basicApi.update(companyIdString, {
                properties: {
                  first_deal_closed_won_date: ""
                }
              });
              
              console.log(`✅ FIELD CLEARED: first_deal_closed_won_date set to NULL for accountant company`);
              
              // Track that field was cleared
              firstDealDateWasCleared = true;
              
              // Update workflow outcome to reflect the change
              workflowOutcome = 'ACCOUNTANT_FIELD_CLEARED_NO_PRIMARY_DEALS';
              
              // Update notification to reflect the field clearing
              slackNotification.details.changeReason = 'No primary deals found - cleared first_deal_closed_won_date field for accountant company (not a customer)';
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
            const singleCompanyId = companyIdString; // The company we're processing is the single company
            
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
              await client.crm.companies.basicApi.update(companyIdString, {
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
                companyId: companyIdString,
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
                companyId: companyIdString,
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
              companyId: companyIdString,
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
          
          // CRITICAL: Do NOT clear first_deal_closed_won_date if company has churn_date
          // A company with churn_date was a customer and MUST have first_deal_closed_won_date
          // The validation above should have already set it if it was missing
          if (hasChurnDate) {
            console.log(`✅ COMPANY WITH CHURN DATE: Company has churn_date (${currentChurnDateValue}) - first_deal_closed_won_date should be set (validation above should have handled it)`);
            workflowOutcome = 'NO_CHANGE_NEEDED_NO_PRIMARY_DEALS';
          } else {
            // Only clear first_deal_closed_won_date if company has NO churn_date (not a customer)
            if (currentFirstDealValue) {
              console.log(`🧹 CLEARING FIELD: No primary deals found (no churn_date) - clearing first_deal_closed_won_date from "${currentFirstDealValue}" to NULL`);
              
              try {
                await client.crm.companies.basicApi.update(companyIdString, {
                  properties: {
                    first_deal_closed_won_date: ""
                  }
                });
                
                console.log(`✅ FIELD CLEARED: first_deal_closed_won_date set to NULL`);
                
                // Track that field was cleared
                firstDealDateWasCleared = true;
                
                // Update workflow outcome to reflect the change
                workflowOutcome = 'FIELD_CLEARED_NO_PRIMARY_DEALS';
                
                // Update notification to reflect the field clearing
                slackNotification.details.changeReason = 'No primary deals found - cleared first_deal_closed_won_date field (not a customer)';
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
          
          console.log(`🔧 AUTO-FIX: Updated wonDates array with ${wonDates.length} dates - company now has won deals, will clear churn date`);
          
          // CRITICAL: After auto-fix, we have won deals, so company is active
          // Clear churn date immediately here in Path A
          const normalizedCurrentChurnDate = (currentChurnDateValue === '' || currentChurnDateValue === null) ? null : currentChurnDateValue;
          
          if (normalizedCurrentChurnDate !== null) {
            console.log(`🔄 AUTO-FIX: Clearing churn date because company now has won deals`);
            console.log(`Current churn date: ${currentChurnDateValue || 'NULL'} → NULL`);
            
            try {
              await client.crm.companies.basicApi.update(companyIdString, {
                properties: {
                  company_churn_date: "" // Clear churn date
                }
              });
              
              console.log(`✅ AUTO-FIX: Churn date cleared successfully`);
          
              // Send notification about churn date being cleared
              slackNotification = {
                type: 'success',
                title: '✅ Auto-Fix: Churn Date Cleared',
                message: `Company "${companyName}" had won deals without PRIMARY - auto-fixed PRIMARY association and cleared churn date`,
                details: {
                  companyId: companyIdString,
                  companyName: companyName,
                  companyOwnerId: currentCompany.properties.hubspot_owner_id,
                  companyOwnerName: companyOwnerName,
                  oldChurnDate: currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL',
                  newChurnDate: 'NULL',
                  allWonDeals: allDealDetails.filter(d => d.stage === 'closedwon' || d.stage === '34692158').length,
                  changeReason: 'Auto-fix: Added PRIMARY to won deal and cleared churn date (company is active)'
                }
              };
              
              workflowOutcome = 'AUTO_FIX_CHURN_CLEARED';
            } catch (updateError) {
              console.error(`❌ AUTO-FIX: Failed to clear churn date: ${updateError.message}`);
            }
          } else {
            console.log(`✅ AUTO-FIX: Churn date already cleared - no update needed`);
            workflowOutcome = 'AUTO_FIX_NO_CHURN_UPDATE_NEEDED';
          }
          
          // Skip the rest of Path A churn detection since we've handled it
          // Path B will handle first_deal_closed_won_date update
        }
      }
      
      // CRITICAL FIX: Only run churn detection if we don't have won deals after auto-fix
      // If auto-fix succeeded and we have wonDates, skip this entire section
      if (wonDates.length === 0) {
      // Count all deals by stage
        // CRITICAL: Count ALL won deals (primary and non-primary) to determine if company is active
        let allWonDealsCount = 0; // ALL won deals (primary + non-primary)
        let primaryWonDealsCount = 0; // Only PRIMARY won deals
      let lostDealsCount = 0;
      let churnedDealsCount = 0;
      
      for (const deal of allDealDetails) {
        // Count ALL won deals (primary and non-primary)
          if (deal.stage === 'closedwon' || deal.stage === '34692158') {
          allWonDealsCount++;
          if (deal.isPrimary) {
            primaryWonDealsCount++;
          }
        }
        
        // Count PRIMARY deals by stage for churn analysis
        if (deal.isPrimary) {
          if (deal.stage === 'closedlost') {
            lostDealsCount++;
          } else if (deal.stage === '31849274') {
            churnedDealsCount++;
          }
        }
      }
      
      console.log(`All deals breakdown: ${allWonDealsCount} total won (${primaryWonDealsCount} primary), ${lostDealsCount} primary lost, ${churnedDealsCount} primary churned`);
      
      // Determine if company is churned
      const totalPrimaryDealsCount = primaryWonDealsCount + lostDealsCount + churnedDealsCount;
      
      // CRITICAL FIX: A company is churned ONLY if:
      // 1. It has primary deals (was a customer)
      // 2. It currently has NO won deals at all (primary OR non-primary) - company is truly inactive
      // 3. It has deals in ACTUAL CHURN STAGE (31849274), not just closedlost
      // This prevents companies with won deals (even non-primary) from being marked as churned
      const hasActualChurnDeals = churnedDealsCount > 0; // Only 31849274 stage counts as churn
      const isChurned = totalPrimaryDealsCount > 0 && allWonDealsCount === 0 && hasActualChurnDeals;
      
      console.log(`Total primary deals: ${totalPrimaryDealsCount}`);
      console.log(`Total won deals (all): ${allWonDealsCount} (primary: ${primaryWonDealsCount}, non-primary: ${allWonDealsCount - primaryWonDealsCount})`);
      console.log(`Has actual churn deals (31849274): ${hasActualChurnDeals} (churnedDealsCount: ${churnedDealsCount})`);
      console.log(`Is company churned: ${isChurned} (will be false if ANY won deals exist)`);
      
      let companyChurnDate = null;
      let churnDateSource = '';
      let manualErrorDetected = false;
      
      // CRITICAL: If company has ANY won deals (even non-primary), it's NOT churned
      if (allWonDealsCount > 0) {
        console.log(`✅ COMPANY IS ACTIVE: Found ${allWonDealsCount} won deal(s) (${primaryWonDealsCount} primary, ${allWonDealsCount - primaryWonDealsCount} non-primary) - company is NOT churned`);
        companyChurnDate = null; // Clear churn date - company is active
      } else if (isChurned) {
        // Company is churned - find the correct churn date
        // Only look at actual churn deals (31849274), not closedlost deals
        const churnedDeals = allDealDetails.filter(d => 
          d.isPrimary && d.stage === '31849274'
        );
        
        if (churnedDeals.length > 0) {
          // Sort by effective churn date (fecha_pedido_baja, then fecha_de_desactivacion, then closeDate)
          // Get the most recent churned deal (product) - this determines when the company churned
          const sortedChurnedDeals = churnedDeals.sort((a, b) => {
            // Priority: Use fecha_pedido_baja first, then fecha_de_desactivacion, then closeDate
            const getSortDate = (deal) => {
              if (deal.fechaPedidoBaja && deal.fechaPedidoBaja.trim() !== '') {
                return new Date(deal.fechaPedidoBaja);
              } else if (deal.fechaDesactivacion && deal.fechaDesactivacion.trim() !== '') {
                return new Date(deal.fechaDesactivacion);
              } else {
                return new Date(deal.closeDate);
              }
            };
            return getSortDate(b) - getSortDate(a); // Most recent first
          });
          const lastChurnedDeal = sortedChurnedDeals[0];
          
          // Check for manual error: churned deal with blank fecha_pedido_baja AND fecha_de_desactivacion
          if (lastChurnedDeal.stage === '31849274' && 
              (!lastChurnedDeal.fechaPedidoBaja || lastChurnedDeal.fechaPedidoBaja.trim() === '') &&
              (!lastChurnedDeal.fechaDesactivacion || lastChurnedDeal.fechaDesactivacion.trim() === '')) {
            manualErrorDetected = true;
            console.log(`⚠️ MANUAL ERROR DETECTED: Deal ${lastChurnedDeal.id} (${lastChurnedDeal.name}) is churned but both fecha_pedido_baja and fecha_de_desactivacion are blank!`);
          }
          
          // Priority 1: Use fecha_pedido_baja (primary churn date field)
          // Priority 2: Use fecha_de_desactivacion (fallback - older field that was used as fecha de baja)
          // Priority 3: Use closeDate as last resort
          const today = new Date();
          today.setHours(0, 0, 0, 0); // Normalize to start of day for comparison
          let useChurnDate = false;
          
          // Helper function to validate churn date
          const validateChurnDate = (dateValue) => {
            if (!dateValue || dateValue.trim() === '') return { valid: false, reason: 'Empty' };
            
            const churnDate = new Date(dateValue);
            churnDate.setHours(0, 0, 0, 0);
            const churnDateOnly = churnDate.toISOString().split('T')[0];
            const dealCloseDate = new Date(lastChurnedDeal.closeDate);
            dealCloseDate.setHours(0, 0, 0, 0);
            
            // Check for placeholder dates dynamically
            const nextYear = new Date(today);
            nextYear.setFullYear(today.getFullYear() + 1);
            nextYear.setMonth(0, 1);
            nextYear.setHours(0, 0, 0, 0);
            
            const oneYearFromToday = new Date(today);
            oneYearFromToday.setFullYear(today.getFullYear() + 1);
            
            const isNextYearJan1 = churnDate.getFullYear() === nextYear.getFullYear() &&
                                   churnDate.getMonth() === 0 &&
                                   churnDate.getDate() === 1;
            const isMoreThanOneYearFuture = churnDate > oneYearFromToday;
            const isPlaceholderDate = isNextYearJan1 || isMoreThanOneYearFuture;
            
            const isValid = churnDate <= today && !isPlaceholderDate && churnDate >= dealCloseDate;
            
            const reasons = [];
            if (churnDate > today) reasons.push('Future date');
            if (isPlaceholderDate) reasons.push(`Placeholder date (${churnDateOnly})`);
            if (churnDate < dealCloseDate) reasons.push('Before closeDate');
            
            return {
              valid: isValid,
              date: churnDate,
              dateOnly: churnDateOnly,
              reasons: reasons
            };
          };
          
          // Priority 1: Use fecha_pedido_baja (primary churn date field)
          if (lastChurnedDeal.fechaPedidoBaja && lastChurnedDeal.fechaPedidoBaja.trim() !== '') {
            console.log(`🔍 VALIDATING fecha_pedido_baja: ${lastChurnedDeal.fechaPedidoBaja}`);
            const validation = validateChurnDate(lastChurnedDeal.fechaPedidoBaja);
            
            if (validation.valid) {
              useChurnDate = true;
              companyChurnDate = validation.date.toISOString();
              churnDateSource = 'fecha_pedido_baja';
              console.log(`✅ VALID: Company churn date set to: ${companyChurnDate} (from fecha_pedido_baja field of deal: ${lastChurnedDeal.name})`);
            } else {
              console.log(`⚠️ INVALID fecha_pedido_baja: ${lastChurnedDeal.fechaPedidoBaja}`);
              console.log(`   Reasons: ${validation.reasons.join(', ') || 'Unknown'}`);
            }
          }
          
          // Priority 2: Fallback to fecha_de_desactivacion (older field that was used as fecha de baja)
          if (!useChurnDate && lastChurnedDeal.fechaDesactivacion && lastChurnedDeal.fechaDesactivacion.trim() !== '') {
            console.log(`🔍 VALIDATING fecha_de_desactivacion (fallback): ${lastChurnedDeal.fechaDesactivacion}`);
            const validation = validateChurnDate(lastChurnedDeal.fechaDesactivacion);
            
            if (validation.valid) {
              useChurnDate = true;
              companyChurnDate = validation.date.toISOString();
              churnDateSource = 'fecha_de_desactivacion';
              console.log(`✅ VALID: Company churn date set to: ${companyChurnDate} (from fecha_de_desactivacion field of deal: ${lastChurnedDeal.name} - fecha_pedido_baja was missing/invalid)`);
            } else {
              console.log(`⚠️ INVALID fecha_de_desactivacion: ${lastChurnedDeal.fechaDesactivacion}`);
              console.log(`   Reasons: ${validation.reasons.join(', ') || 'Unknown'}`);
            }
          }
          
          // Priority 3: Fallback to closeDate if both fecha_pedido_baja and fecha_de_desactivacion are invalid or missing
          if (!useChurnDate) {
            companyChurnDate = new Date(lastChurnedDeal.closeDate).toISOString();
            churnDateSource = 'close_date';
            console.log(`Company churn date set to: ${companyChurnDate} (from close date of deal: ${lastChurnedDeal.name} - both fecha_pedido_baja and fecha_de_desactivacion were invalid or missing)`);
          }
        } else {
          console.log(`Company is churned but no churned deals found - this shouldn't happen`);
        }
      } else {
        console.log(`Company is not churned - no primary deals or has won deals`);
      }

      // CRITICAL: If company is churned but first_deal_closed_won_date is blank OR incorrect, calculate it
      // A company can't churn if it was never a customer (never had won deals)
      // Also check if first_deal_closed_won_date is incorrect (e.g., after churn date)
      let calculatedFirstDealDate = null;
      let needsFirstDealUpdate = false;
      
      const isFirstDealMissing = (!currentFirstDealValue || currentFirstDealValue === '');
      let isFirstDealIncorrect = false;
      
      if (!isFirstDealMissing && companyChurnDate) {
        // Check if current first_deal_closed_won_date is after churn date (data quality issue)
        try {
          const currentFirstDateParsed = new Date(currentFirstDealValue);
          const churnDateParsed = new Date(companyChurnDate);
          if (currentFirstDateParsed > churnDateParsed) {
            isFirstDealIncorrect = true;
            console.log(`⚠️ DATA QUALITY ISSUE: Company has first_deal_closed_won_date (${currentFirstDealValue}) that is AFTER churn_date (${companyChurnDate})`);
            console.log(`🔧 AUTO-FIX: Will recalculate first_deal_closed_won_date from PRIMARY deals`);
          }
        } catch (e) {
          // Date parsing failed, skip this check
        }
      }
      
      if (isChurned && (isFirstDealMissing || isFirstDealIncorrect)) {
        const issueType = isFirstDealMissing 
          ? 'first_deal_closed_won_date is blank'
          : 'first_deal_closed_won_date is incorrect (after churn_date)';
        console.log(`⚠️ DATA INCONSISTENCY DETECTED: Company is churned but ${issueType}`);
        console.log(`🔧 AUTO-FIX: Calculating first_deal_closed_won_date from PRIMARY deals' closeDate`);
        
        // Find earliest closeDate from PRIMARY deals (this represents when they first became a customer)
        // Use historical closeDate if available (already set in dealInfo.closeDate)
        const primaryDealsWithCloseDate = allDealDetails.filter(d => 
          d.isPrimary && d.closeDate
        );
        
        if (primaryDealsWithCloseDate.length > 0) {
          // Sort by closeDate and get the earliest
          const sortedPrimaryDeals = primaryDealsWithCloseDate.sort((a, b) => 
            new Date(a.closeDate) - new Date(b.closeDate)
          );
          const earliestPrimaryDeal = sortedPrimaryDeals[0];
          
          calculatedFirstDealDate = new Date(earliestPrimaryDeal.closeDate).toISOString();
          needsFirstDealUpdate = true;
          
          console.log(`✅ CALCULATED: first_deal_closed_won_date = ${calculatedFirstDealDate} (from PRIMARY deal: ${earliestPrimaryDeal.name}, closeDate: ${earliestPrimaryDeal.closeDate})`);
          console.log(`   Deal stage: ${earliestPrimaryDeal.stage}, Deal ID: ${earliestPrimaryDeal.id}`);
        } else {
          console.log(`⚠️ WARNING: No PRIMARY deals with closeDate found - cannot calculate first_deal_closed_won_date`);
        }
      }
      
      // Check if changes are needed for churn date
      // Normalize dates to date-only format (YYYY-MM-DD) for proper comparison, ignoring time/milliseconds
      const normalizedCurrentChurnDate = (currentChurnDateValue === '' || currentChurnDateValue === null) 
        ? null 
        : new Date(currentChurnDateValue).toISOString().split('T')[0];
      const normalizedCalculatedChurnDate = (companyChurnDate === '' || companyChurnDate === null) 
        ? null 
        : new Date(companyChurnDate).toISOString().split('T')[0];
      const needsChurnUpdate = (normalizedCurrentChurnDate !== normalizedCalculatedChurnDate);
      
      console.log(`Current churn date: ${currentChurnDateValue || 'NULL'}`);
      console.log(`Calculated churn date: ${companyChurnDate || 'NULL'}`);
      console.log(`Normalized comparison (date-only): "${normalizedCurrentChurnDate}" !== "${normalizedCalculatedChurnDate}" = ${needsChurnUpdate}`);

      if (needsChurnUpdate || needsFirstDealUpdate) {
        workflowOutcome = needsFirstDealUpdate && needsChurnUpdate ? 'CHURN_AND_FIRST_DATE_FIXED' : 
                          needsFirstDealUpdate ? 'FIRST_DATE_FIXED_FOR_CHURNED' : 'CHURN_DETECTED';
        
        // Prepare update properties
        const updateProperties = {};
        
        if (companyChurnDate) {
          updateProperties.company_churn_date = companyChurnDate;
        } else {
          updateProperties.company_churn_date = ""; // Clear churn date with empty string
        }
        
        // Add first_deal_closed_won_date if it needs to be set
        if (needsFirstDealUpdate && calculatedFirstDealDate) {
          updateProperties.first_deal_closed_won_date = calculatedFirstDealDate;
          console.log(`🔧 ADDING: first_deal_closed_won_date = ${calculatedFirstDealDate} (fixing data inconsistency)`);
        }
        
        const changeDescription = [];
        if (needsChurnUpdate) {
          changeDescription.push(`Churn: "${currentChurnDateValue || 'NULL'}" → "${companyChurnDate || 'NULL'}"`);
        }
        if (needsFirstDealUpdate) {
          changeDescription.push(`First: "NULL" → "${calculatedFirstDealDate}"`);
        }
        
        console.log(`🔄 CHANGE DETECTED: ${changeDescription.join(' | ')}`);
        console.log(`Updating company ${companyIdString} with properties:`, updateProperties);

        await client.crm.companies.basicApi.update(companyIdString, {
          properties: updateProperties
        });

        console.log(`✅ CHURN CHANGE MADE: Company updated successfully`);

        const notificationTitle = needsFirstDealUpdate 
          ? (manualErrorDetected ? '🚨 Churn + First Date Fixed + Manual Error' : '🔴 Churn + First Date Fixed')
          : (manualErrorDetected ? '🚨 Company Churn + Manual Error Detected' : '🔴 Company Churn Detected');
        
        const notificationMessage = needsFirstDealUpdate
          ? `Company "${companyName}" is CHURNED - fixed data inconsistency: set first_deal_closed_won_date to ${calculatedFirstDealDate ? new Date(calculatedFirstDealDate).toISOString().split('T')[0] : 'NULL'} (from PRIMARY deals)${needsChurnUpdate ? `, churn date set to ${companyChurnDate ? new Date(companyChurnDate).toISOString().split('T')[0] : 'NULL'}` : ''}${manualErrorDetected ? ' - ⚠️ MANUAL ERROR: fecha_de_desactivacion is blank!' : ''}`
          : `Company "${companyName}" is CHURNED - churn date set to ${companyChurnDate ? new Date(companyChurnDate).toISOString().split('T')[0] : 'NULL'} (source: ${churnDateSource})${manualErrorDetected ? ' - ⚠️ MANUAL ERROR: fecha_de_desactivacion is blank!' : ''}`;
        
        slackNotification = {
          type: manualErrorDetected ? 'error' : 'success',
          title: notificationTitle,
          message: notificationMessage,
          details: {
            companyId: companyIdString,
            companyName: companyName,
            companyOwnerId: currentCompany.properties.hubspot_owner_id,
            companyOwnerName: companyOwnerName,
            oldChurnValue: currentChurnDateValue,
            newChurnValue: companyChurnDate,
            oldChurnDate: currentChurnDateValue ? new Date(currentChurnDateValue).toISOString().split('T')[0] : 'NULL',
            newChurnDate: companyChurnDate ? new Date(companyChurnDate).toISOString().split('T')[0] : 'NULL',
            oldFirstDate: currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL',
            newFirstDate: needsFirstDealUpdate && calculatedFirstDealDate 
              ? new Date(calculatedFirstDealDate).toISOString().split('T')[0] 
              : (currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : 'NULL'),
            primaryDeals: totalDealsProcessed,
            wonDeals: wonDealsFound,
            allWonDeals: allWonDealsCount,
            primaryWonDeals: primaryWonDealsCount,
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
            changeReason: allWonDealsCount > 0 
              ? `Company has ${allWonDealsCount} won deal(s) - clearing churn date (company is active)`
              : needsFirstDealUpdate
                ? `Company churned - fixed data inconsistency: set first_deal_closed_won_date from PRIMARY deals (${lostDealsCount} lost, ${churnedDealsCount} churned)${manualErrorDetected ? ' - MANUAL ERROR: fecha_de_desactivacion is blank!' : ''}`
                : `Company churned - all deals are lost/churned (${lostDealsCount} lost, ${churnedDealsCount} churned)${manualErrorDetected ? ' - MANUAL ERROR: fecha_de_desactivacion is blank!' : ''}`
          }
        };

        // Log the result
        const updatedCompany = await client.crm.companies.basicApi.getById(companyId, ['first_deal_closed_won_date', 'company_churn_date', 'name']);
        console.log(`Verification - Company name: ${updatedCompany.properties.name}`);
        console.log(`Verification - First deal closed won date: ${updatedCompany.properties.first_deal_closed_won_date || 'NULL'}`);
        console.log(`Verification - Company churn date: ${updatedCompany.properties.company_churn_date || 'NULL'}`);

      } else {
        workflowOutcome = 'NO_CHANGE_NEEDED';
        console.log(`✅ NO CHANGE NEEDED: Churn date already set correctly`);
        console.log(`Churn date: ${companyChurnDate || 'NULL'} (unchanged)`);
        console.log(`Skipping update - churn status is already correct`);
      }
      } // End of "if (wonDates.length === 0)" check for churn detection
      
    } else if (wonDates.length > 0) {
      // NORMAL CASE: Calculate first won date
      // CRITICAL: Only use PRIMARY won deals for first_deal_closed_won_date calculation
      // This ensures we only count deals where company was PRIMARY (customer), not channel partner deals
      const primaryWonDates = [];
      for (const deal of allDealDetails) {
        if ((deal.stage === 'closedwon' || deal.stage === '34692158') && 
            deal.closeDate && 
            primaryDealIds.includes(deal.id)) {
          primaryWonDates.push(new Date(deal.closeDate));
        }
      }
      
      if (primaryWonDates.length === 0) {
        console.log(`⚠️ SKIPPING: Company has won deals but NO PRIMARY won deals - this is a referrer/accountant, not a customer`);
        workflowOutcome = 'SKIPPED_NON_PRIMARY';
        slackNotification = {
          type: 'warning',
          title: '⚠️ Non-Primary Company Skipped',
          message: `Company "${companyName}" has won deals but NO PRIMARY won deals - skipping first_deal_closed_won_date calculation`,
          details: {
            companyId: companyIdString,
            companyName: companyName,
            companyOwnerId: currentCompany.properties.hubspot_owner_id,
            companyOwnerName: companyOwnerName,
            totalDeals: totalAssociations,
            primaryDeals: primaryDealIds.length,
            wonDeals: wonDates.length,
            reason: 'Company is referrer/accountant, not a customer'
          }
        };
        return { workflowOutcome, slackNotification };
      }
      
      const firstWonDate = new Date(Math.min(...primaryWonDates));
      const formattedFirstDate = firstWonDate.toISOString();

      console.log(`First won date calculated: ${formattedFirstDate} (from ${primaryWonDates.length} PRIMARY won deals)`);

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
            companyId: companyIdString,
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
      // CRITICAL: Count ALL won deals (primary and non-primary) to determine if company is active
      let allWonDealsCount = 0; // ALL won deals (primary + non-primary)
      let primaryWonDealsCount = 0; // Only PRIMARY won deals
      let lostDealsCount = 0;
      let churnedDealsCount = 0;
      
      for (const deal of allDealDetails) {
        // Count ALL won deals (primary and non-primary)
          if (deal.stage === 'closedwon' || deal.stage === '34692158') {
          allWonDealsCount++;
          if (deal.isPrimary) {
            primaryWonDealsCount++;
          }
        }
        
        // Count PRIMARY deals by stage for churn analysis
        if (deal.isPrimary) {
          if (deal.stage === 'closedlost') {
            lostDealsCount++;
          } else if (deal.stage === '31849274') {
            churnedDealsCount++;
          }
        }
      }
      
      console.log(`All deals breakdown: ${allWonDealsCount} total won (${primaryWonDealsCount} primary), ${lostDealsCount} primary lost, ${churnedDealsCount} primary churned`);
      
      // Determine if company is churned
      const totalPrimaryDealsCount = primaryWonDealsCount + lostDealsCount + churnedDealsCount;
      
      // CRITICAL FIX: A company is churned ONLY if:
      // 1. It has primary deals (was a customer)
      // 2. It currently has NO won deals at all (primary OR non-primary) - company is truly inactive
      // 3. It has deals in ACTUAL CHURN STAGE (31849274), not just closedlost
      // This prevents companies with won deals (even non-primary) from being marked as churned
      const hasActualChurnDeals = churnedDealsCount > 0; // Only 31849274 stage counts as churn
      const isChurned = totalPrimaryDealsCount > 0 && allWonDealsCount === 0 && hasActualChurnDeals;
      
      console.log(`Total primary deals: ${totalPrimaryDealsCount}`);
      console.log(`Total won deals (all): ${allWonDealsCount} (primary: ${primaryWonDealsCount}, non-primary: ${allWonDealsCount - primaryWonDealsCount})`);
      console.log(`Has actual churn deals (31849274): ${hasActualChurnDeals} (churnedDealsCount: ${churnedDealsCount})`);
      console.log(`Is company churned: ${isChurned} (will be false if ANY won deals exist)`);
      
      let companyChurnDate = null;
      let churnDateSource = '';
      
      // CRITICAL: If company has ANY won deals (even non-primary), it's NOT churned - clear churn date
      if (allWonDealsCount > 0) {
        console.log(`✅ COMPANY IS ACTIVE: Found ${allWonDealsCount} won deal(s) (${primaryWonDealsCount} primary, ${allWonDealsCount - primaryWonDealsCount} non-primary) - clearing churn date`);
        companyChurnDate = null; // Clear churn date - company is active
      } else if (isChurned) {
        // Company is churned - find the correct churn date from churned deals
        const churnedDeals = allDealDetails.filter(d => 
          d.isPrimary && d.stage === '31849274'
        );
        
        if (churnedDeals.length > 0) {
          // Sort by effective churn date (fecha_pedido_baja, then fecha_de_desactivacion, then closeDate)
          const sortedChurnedDeals = churnedDeals.sort((a, b) => {
            const getSortDate = (deal) => {
              if (deal.fechaPedidoBaja && deal.fechaPedidoBaja.trim() !== '') {
                return new Date(deal.fechaPedidoBaja);
              } else if (deal.fechaDesactivacion && deal.fechaDesactivacion.trim() !== '') {
                return new Date(deal.fechaDesactivacion);
              } else {
                return new Date(deal.closeDate);
              }
            };
            return getSortDate(b) - getSortDate(a);
          });
          const lastChurnedDeal = sortedChurnedDeals[0];
          
          // Priority 1: Use fecha_pedido_baja (primary churn date field)
          if (lastChurnedDeal.fechaPedidoBaja && lastChurnedDeal.fechaPedidoBaja.trim() !== '') {
            companyChurnDate = new Date(lastChurnedDeal.fechaPedidoBaja).toISOString();
            churnDateSource = 'fecha_pedido_baja';
            console.log(`Company churn date set to: ${companyChurnDate} (from fecha_pedido_baja field of deal: ${lastChurnedDeal.name})`);
          } else if (lastChurnedDeal.fechaDesactivacion && lastChurnedDeal.fechaDesactivacion.trim() !== '') {
            // Priority 2: Fallback to fecha_de_desactivacion (older field that was used as fecha de baja)
            companyChurnDate = new Date(lastChurnedDeal.fechaDesactivacion).toISOString();
            churnDateSource = 'fecha_de_desactivacion';
            console.log(`Company churn date set to: ${companyChurnDate} (from fecha_de_desactivacion field of deal: ${lastChurnedDeal.name} - fecha_pedido_baja was missing)`);
          } else {
            // Priority 3: Use close date as last resort if both fecha_pedido_baja and fecha_de_desactivacion are missing
            companyChurnDate = new Date(lastChurnedDeal.closeDate).toISOString();
            churnDateSource = 'close_date';
            console.log(`Company churn date set to: ${companyChurnDate} (from close date of deal: ${lastChurnedDeal.name} - both fecha_pedido_baja and fecha_de_desactivacion were missing)`);
          }
        } else {
          console.log(`Company is churned but no churned deals found - this shouldn't happen`);
        }
      } else {
        console.log(`Company is still active - no churn date`);
      }

      // Check if changes are needed (date-based comparison, not exact timestamp)
      const normalizedCurrentFirstDate = currentFirstDealValue ? new Date(currentFirstDealValue).toISOString().split('T')[0] : null;
      const calculatedFirstDate = new Date(formattedFirstDate).toISOString().split('T')[0];
      
      // Normalize churn dates to date-only format (YYYY-MM-DD) for proper comparison, ignoring time/milliseconds
      const normalizedCurrentChurnDate = (currentChurnDateValue === '' || currentChurnDateValue === null) 
        ? null 
        : new Date(currentChurnDateValue).toISOString().split('T')[0];
      const normalizedCalculatedChurnDate = (companyChurnDate === '' || companyChurnDate === null) 
        ? null 
        : new Date(companyChurnDate).toISOString().split('T')[0];
      
      const needsFirstUpdate = normalizedCurrentFirstDate !== calculatedFirstDate;
      const needsChurnUpdate = (normalizedCurrentChurnDate !== normalizedCalculatedChurnDate);
      const needsUpdate = needsFirstUpdate || needsChurnUpdate;

      console.log(`Current first date: ${normalizedCurrentFirstDate || 'NULL'}`);
      console.log(`Calculated first date: ${calculatedFirstDate}`);
      console.log(`First date comparison: ${normalizedCurrentFirstDate} !== ${calculatedFirstDate} = ${needsFirstUpdate}`);
      console.log(`Current churn date: ${currentChurnDateValue || 'NULL'}`);
      console.log(`Calculated churn date: ${companyChurnDate || 'NULL'}`);
      console.log(`Churn date comparison (date-only): "${normalizedCurrentChurnDate}" !== "${normalizedCalculatedChurnDate}" = ${needsChurnUpdate}`);
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
            updateProperties.company_churn_date = ""; // Clear churn date with empty string (HubSpot requires "" not null)
          }
          if (changeDescription) changeDescription += ' | ';
          changeDescription += `Churn: "${currentChurnDateValue || 'NULL'}" → "${companyChurnDate || 'NULL'}"`;
        }
        
        console.log(`🔄 CHANGE DETECTED: ${changeDescription}`);
        console.log(`Updating company ${companyIdString} with properties:`, updateProperties);

        await client.crm.companies.basicApi.update(companyIdString, {
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
            companyId: companyIdString,
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
            allWonDeals: allWonDealsCount,
            primaryWonDeals: primaryWonDealsCount,
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
              : allWonDealsCount > 0 && needsChurnUpdate
                ? `Company has ${allWonDealsCount} won deal(s) - clearing churn date (company is active)`
                : `${needsFirstUpdate && needsChurnUpdate 
                    ? 'Recalculated first deal date and churn date from current PRIMARY deals' 
                    : needsFirstUpdate 
                      ? 'Recalculated first deal date from earliest PRIMARY closed-won deal' 
                      : 'Recalculated churn date from current PRIMARY deals'}`,
            churnDateSource: churnDateSource || (needsChurnUpdate && companyChurnDate ? 'fecha_pedido_baja' : ''),
            autoFixCompleted: wasAutoFix
          }
        };

        // Log the result
        const updatedCompany = await client.crm.companies.basicApi.getById(companyIdString, ['first_deal_closed_won_date', 'company_churn_date', 'name']);
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
    console.log(`Company: ${companyName} (ID: ${companyIdString})`);
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
      // Use tracking variable to accurately report if field was cleared during this workflow execution
      if (firstDealDateWasCleared) {
        console.log(`Change made: YES (field was cleared during this workflow execution)`);
      } else {
        // Field was not cleared - check if it should have been cleared but wasn't (e.g., company has churn_date)
        // Use hasChurnDate from upper scope (declared at line 416)
        if (hasChurnDate && currentFirstDealValue) {
          console.log(`Change made: NO (field preserved - company has churn_date, so first_deal_closed_won_date should remain set)`);
        } else if (currentFirstDealValue) {
          console.log(`Change made: NO (field preserved - no changes needed)`);
        } else {
          console.log(`Change made: NO (field already NULL - no changes needed)`);
        }
      }
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

    // Get companyId from event object (companyIdString may not be defined if error occurred early)
    // Get directly from event object to avoid ReferenceError if companyIdString is not in scope
    const errorCompanyId = event.object?.objectId || event.inputFields?.objectId || event.objectId || 'UNKNOWN';

    // Send error notification to Slack
    try {
      await sendSlackNotification({
        type: 'error',
        title: '❌ Workflow Error',
        message: `Error in first_deal_closed_won_date workflow for company ${errorCompanyId}`,
        details: {
          companyId: errorCompanyId,
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
              value: notification.details.changeReason || 'Recalculated first deal date from earliest PRIMARY closed-won deal',
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
  } else if (notification.type === 'accountant_verification' || (notification.type === 'success' && notification.details.churnDateCleared)) {
    // Special notification for accountant company verification
    // Also handle success type when churn_date was cleared for accountant
    const isChurnDateCleared = notification.details.churnDateCleared === true;
    
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(isChurnDateCleared ? 'success' : notification.type),
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
            }
          ]
        }
      ]
    };
    
    // Add churn date change field if it was cleared
    if (isChurnDateCleared && notification.details.oldChurnDate && notification.details.oldChurnDate !== 'NULL') {
      slackMessage.attachments[0].fields.push({
        title: '📅 Churn Date Cleared',
        value: `${notification.details.oldChurnDate} → NULL`,
        short: true
      });
    }
    
    // Add remaining fields
    slackMessage.attachments[0].fields.push(
      {
        title: '💡 Action Needed',
        value: isChurnDateCleared 
          ? 'Churn date cleared - company is not a customer (no PRIMARY deals), just a channel partner/accountant'
          : 'Please verify this is a legitimate accountant referral',
        short: false
      },
      {
        title: '📝 Reason',
        value: notification.details.reason || notification.details.changeReason || 'Verification needed',
        short: false
      }
    );
    
    // Add timestamp and footer
    slackMessage.attachments[0].timestamp = Math.floor(Date.now() / 1000);
    slackMessage.attachments[0].footer = 'HubSpot Workflow Automation';
    slackMessage.attachments[0].footer_icon = 'https://hubspot.com/favicon.ico';
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
