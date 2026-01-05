// =============================================================================
// HubSpot Custom Code - Contact Creation to First Engagement Business Hours Calculation
// =============================================================================
// URL in HubSpot automation: <insert-workflow-url>
// VERSION: 2.0.0
// LAST UPDATED: 2026-01-04
// FILE: hubspot_contact_creation_business_hours.js
//
// PURPOSE:
// Calculates the business hours from contact creation to first engagement (first contact by salesperson EVER, regardless of owner).
// Only updates the field when it's blank (first time engagement).
// This helps measure sales team responsiveness in business hours (excluding weekends, holidays, and non-business hours).
// NOTE: Uses property history to find the FIRST engagement date ever, even if contact owner changed (hs_sa_first_engagement_date resets on owner change).
//
// FEATURES:
// ✅ BUSINESS HOURS CALCULATION: Calculates business hours between createdate and hs_sa_first_engagement_date
// ✅ WEEKDAY VALIDATION: Only Monday-Friday are considered business days
// ✅ HOLIDAY EXCLUSION: Excludes Argentina national holidays from business hours
// ✅ TIMEZONE HANDLING: Converts HubSpot UTC timestamps to Argentina timezone (America/Argentina/Buenos_Aires)
// ✅ FIRST ENGAGEMENT ONLY: Only updates field when blank (prevents overwriting on subsequent engagements)
// ✅ COMPREHENSIVE LOGGING: Detailed logs for debugging and audit trails
//
// FIELD REQUIREMENTS:
// - Create a custom number field: `cycle_time_lead_to_first_touch_business_hours` (business hours as decimal number)
//
// BUSINESS HOURS RULES:
// - Days: Monday to Friday (weekdays only)
// - Hours: 9:00 AM to 6:00 PM (Argentina timezone: America/Argentina/Buenos_Aires, UTC-3)
// - Excludes: Weekends (Saturday, Sunday), holidays, and hours outside 9 AM - 6 PM
//
// WORKFLOW SETUP (Use BOTH workflows):
//
// Workflow 1 - Real-Time Trigger:
// - Trigger: Property value changes
// - Property: `hs_sa_first_engagement_date`
// - Condition: Property is not blank
// - Action: Run this custom code
//
// Workflow 2 - Daily Scheduled (Recommended):
// - Trigger: Scheduled (daily)
// - Filter contacts where:
//   - `hs_sa_first_engagement_date` IS NOT NULL (has engagement)
//   - AND `cycle_time_lead_to_first_touch_business_hours` IS NULL (field not calculated yet)
// - Action: Run this custom code
// - Purpose: Catches contacts that had engagement but field wasn't calculated (backfill)
//
// RATE LIMIT HANDLING:
// - If rate limit errors (429) occur, HubSpot will automatically retry the workflow
// - The script handles rate limit errors gracefully and returns success so HubSpot can retry
// - To reduce rate limits: Process fewer contacts per run by adding date filters (e.g., created in last 7 days)
//
// FIELD UPDATE LOGIC:
// - Only updates field if: `cycle_time_lead_to_first_touch_business_hours` is blank/null (prevents overwriting)
// - For contacts WITHOUT engagement: Field stays blank (correct - no engagement = no calculation)
//
// FILTERING CONTACTED vs NOT CONTACTED in HubSpot:
// Option 1 - Use engagement date field (Recommended):
//   - CONTACTED: `hs_sa_first_engagement_date` IS NOT NULL
//   - NOT CONTACTED: `hs_sa_first_engagement_date` IS NULL
//
// Option 2 - Use calculated field:
//   - CONTACTED: `cycle_time_lead_to_first_touch_business_hours` IS NOT NULL
//   - NOT CONTACTED: `cycle_time_lead_to_first_touch_business_hours` IS NULL
//   - Note: Both filters give same result, but using engagement date is more direct
//
// ENVIRONMENT VARIABLES REQUIRED:
// - ColppyCRMAutomations: HubSpot Private App token with CRM scopes
//
// =============================================================================
// ⚡ READY TO COPY/PASTE - Select all (Ctrl/Cmd+A) and copy to HubSpot
// =============================================================================

const hubspot = require('@hubspot/api-client');

exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  // Argentina timezone offset (UTC-3)
  const ARGENTINA_UTC_OFFSET = -3; // UTC-3 hours

  // Argentina holidays 2026 (as date strings in YYYY-MM-DD format for comparison)
  // Official Argentina National Holidays 2026
  const ARGENTINA_HOLIDAYS_2026 = [
    '2026-01-01', // New Year's Day
    '2026-02-16', // Carnival Monday
    '2026-02-17', // Carnival Tuesday
    '2026-03-24', // Day of Remembrance for Truth and Justice
    '2026-04-02', // Malvinas Day (Veteran's Day) / Maundy Thursday (same date in 2026)
    '2026-04-03', // Good Friday
    '2026-05-01', // Labour Day
    '2026-05-25', // May Revolution Day
    '2026-06-15', // Martín Miguel de Güemes' Day (Monday - moved from June 17)
    '2026-06-20', // National Flag Day
    '2026-07-09', // Independence Day
    '2026-08-17', // San Martín's Day (Death of San Martin)
    '2026-10-12', // Day of Respect for Cultural Diversity
    '2026-11-20', // National Sovereignty Day
    '2026-12-08', // Immaculate Conception Day
    '2026-12-25', // Christmas Day
  ];

  /**
   * Convert UTC timestamp to Argentina timezone date object
   * @param {number|string} timestamp - Unix timestamp in milliseconds or ISO string
   * @returns {Object} Object with Argentina timezone components
   */
  function convertToArgentinaTimezone(timestamp) {
    let date;
    
    if (typeof timestamp === 'string') {
      date = new Date(timestamp);
    } else {
      date = new Date(parseInt(timestamp));
    }
    
    const utcHours = date.getUTCHours();
    const utcMinutes = date.getUTCMinutes();
    const utcSeconds = date.getUTCSeconds();
    const utcMs = date.getUTCMilliseconds();
    const utcDate = date.getUTCDate();
    const utcMonth = date.getUTCMonth();
    const utcYear = date.getUTCFullYear();
    
    // Calculate Argentina time (UTC-3)
    let arHours = utcHours + ARGENTINA_UTC_OFFSET;
    let arDate = utcDate;
    let arMonth = utcMonth;
    let arYear = utcYear;
    
    // Handle day rollover
    if (arHours < 0) {
      arHours += 24;
      arDate -= 1;
      if (arDate < 1) {
        arMonth -= 1;
        if (arMonth < 0) {
          arMonth = 11;
          arYear -= 1;
        }
        arDate = new Date(Date.UTC(arYear, arMonth + 1, 0)).getUTCDate();
      }
    } else if (arHours >= 24) {
      arHours -= 24;
      arDate += 1;
      const daysInMonth = new Date(Date.UTC(arYear, arMonth + 1, 0)).getUTCDate();
      if (arDate > daysInMonth) {
        arDate = 1;
        arMonth += 1;
        if (arMonth > 11) {
          arMonth = 0;
          arYear += 1;
        }
      }
    }
    
    // Create Date object for day of week calculation
    const arDateObj = new Date(Date.UTC(arYear, arMonth, arDate, arHours, utcMinutes, utcSeconds, utcMs));
    const dayOfWeek = arDateObj.getUTCDay();
    
    return {
      year: arYear,
      month: arMonth,
      date: arDate,
      hours: arHours,
      minutes: utcMinutes,
      seconds: utcSeconds,
      milliseconds: utcMs,
      dayOfWeek: dayOfWeek,
      // Store as Date object for calculations
      dateObj: arDateObj,
      // Helper methods
      toDateString: function() {
        const monthStr = String(this.month + 1).padStart(2, '0');
        const dateStr = String(this.date).padStart(2, '0');
        return `${this.year}-${monthStr}-${dateStr}`;
      },
      toTimeString: function() {
        const hoursStr = String(this.hours).padStart(2, '0');
        const minutesStr = String(this.minutes).padStart(2, '0');
        const secondsStr = String(this.seconds).padStart(2, '0');
        return `${hoursStr}:${minutesStr}:${secondsStr}`;
      },
      // Get timestamp in milliseconds (UTC representation of Argentina time)
      getTime: function() {
        return this.dateObj.getTime();
      }
    };
  }

  /**
   * Check if date is a holiday
   * @param {Object} arDate - Argentina timezone date object
   * @returns {boolean} True if date is a holiday
   */
  function isHoliday(arDate) {
    const dateString = arDate.toDateString();
    return ARGENTINA_HOLIDAYS_2026.includes(dateString);
  }

  /**
   * Check if date is a weekday (Monday-Friday)
   * @param {Object} arDate - Argentina timezone date object
   * @returns {boolean} True if date is Monday-Friday
   */
  function isWeekday(arDate) {
    return arDate.dayOfWeek >= 1 && arDate.dayOfWeek <= 5;
  }

  /**
   * Check if datetime is within business hours (9 AM - 6 PM)
   * @param {Object} arDate - Argentina timezone date object
   * @returns {boolean} True if hour is between 9 and 17 (9 AM - 5:59 PM)
   */
  function isWithinBusinessHours(arDate) {
    return arDate.hours >= 9 && arDate.hours < 18;
  }

  /**
   * Check if datetime is business hours (weekday, 9 AM - 6 PM, not holiday)
   * @param {Object} arDate - Argentina timezone date object
   * @returns {boolean} True if datetime is business hours
   */
  function isBusinessHour(arDate) {
    if (!isWeekday(arDate)) {
      return false;
    }
    if (isHoliday(arDate)) {
      return false;
    }
    if (!isWithinBusinessHours(arDate)) {
      return false;
    }
    return true;
  }

  /**
   * Get earliest engagement date from property history (first engagement ever, regardless of owner)
   * @param {string} contactId - Contact ID
   * @returns {string|null} Earliest engagement date as ISO string, or null if not found
   */
  async function getEarliestEngagementDateFromHistory(contactId) {
    console.log(`🔍 ENGAGEMENT HISTORY: Fetching property history for contact ${contactId}`);
    
    try {
      const response = await fetch(`https://api.hubspot.com/crm/v3/objects/contacts/${contactId}?propertiesWithHistory=hs_sa_first_engagement_date`, {
        headers: {
          'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        if (response.status === 429) {
          console.log(`⚠️ ENGAGEMENT HISTORY: Rate limit error (429) for contact ${contactId} - HubSpot will retry`);
          throw new Error('Rate limit exceeded - HubSpot will retry this workflow');
        }
        console.log(`⚠️ ENGAGEMENT HISTORY: API error ${response.status} for contact ${contactId}`);
        return null;
      }
      
      const data = await response.json();
      const propertiesWithHistory = data.propertiesWithHistory || {};
      const engagementHistory = propertiesWithHistory.hs_sa_first_engagement_date;
      
      if (!engagementHistory) {
        console.log(`⚠️ ENGAGEMENT HISTORY: No history found for contact ${contactId}`);
        return null;
      }
      
      // Property history format: can be a list of versions directly, or a dict with "versions" key
      let history = [];
      if (Array.isArray(engagementHistory)) {
        history = engagementHistory;
      } else if (engagementHistory && typeof engagementHistory === 'object' && engagementHistory.versions) {
        history = engagementHistory.versions;
      }
      
      if (history.length === 0) {
        console.log(`⚠️ ENGAGEMENT HISTORY: Empty history for contact ${contactId}`);
        return null;
      }
      
      // Find the earliest engagement date (first time it was set, regardless of owner changes)
      let earliestDate = null;
      let earliestTimestamp = null;
      
      for (const entry of history) {
        const value = entry.value;
        const timestamp = entry.timestamp;
        
        if (value && value.trim() && value.trim().toLowerCase() !== 'null') {
          try {
            const dateObj = new Date(value);
            if (!isNaN(dateObj.getTime())) {
              const timestampDate = new Date(timestamp);
              if (!earliestTimestamp || timestampDate.getTime() < earliestTimestamp.getTime()) {
                earliestDate = value;
                earliestTimestamp = timestampDate;
              }
            }
          } catch (e) {
            // Skip invalid dates
            continue;
          }
        }
      }
      
      if (earliestDate) {
        console.log(`✅ ENGAGEMENT HISTORY: Earliest engagement date found: ${earliestDate} (set on ${earliestTimestamp.toISOString()})`);
        return earliestDate;
      }
      
      console.log(`⚠️ ENGAGEMENT HISTORY: No valid engagement dates found in history for contact ${contactId}`);
      return null;
      
    } catch (error) {
      // Check if this is a rate limit error - if so, re-throw so main handler can deal with it
      if (error.message && error.message.includes('Rate limit')) {
        throw error;
      }
      console.error(`❌ ENGAGEMENT HISTORY ERROR: Contact ${contactId} - ${error.message}`);
      return null;
    }
  }

  /**
   * Calculate business hours between two timestamps
   * @param {number|string} startTimestamp - Start timestamp
   * @param {number|string} endTimestamp - End timestamp
   * @returns {number} Business hours as decimal number
   */
  function calculateBusinessHours(startTimestamp, endTimestamp) {
    // Convert to Date objects
    const startDate = typeof startTimestamp === 'string' ? new Date(startTimestamp) : new Date(parseInt(startTimestamp));
    const endDate = typeof endTimestamp === 'string' ? new Date(endTimestamp) : new Date(parseInt(endTimestamp));
    
    // Validate dates
    if (endDate.getTime() <= startDate.getTime()) {
      return 0.0;
    }
    
    let businessHours = 0.0;
    const startTime = startDate.getTime();
    const endTime = endDate.getTime();
    
    // Start from the beginning of the hour containing startTime
    let current = new Date(startTime);
    // Round down to the hour
    current.setUTCMinutes(0, 0, 0);
    
    // Iterate hour by hour
    while (current.getTime() < endTime) {
      const currentAr = convertToArgentinaTimezone(current.getTime());
      
      if (isBusinessHour(currentAr)) {
        // Calculate the segment of this hour that is within our range
        const hourStart = current.getTime();
        const hourEnd = hourStart + (60 * 60 * 1000); // Add 1 hour in milliseconds
        const segmentStart = Math.max(hourStart, startTime);
        const segmentEnd = Math.min(hourEnd, endTime);
        
        const segmentHours = (segmentEnd - segmentStart) / (60 * 60 * 1000);
        businessHours += segmentHours;
      }
      
      // Move to next hour
      current = new Date(current.getTime() + (60 * 60 * 1000));
      
      // Safety check to prevent infinite loops (shouldn't happen, but just in case)
      if (current.getTime() > endTime + (24 * 60 * 60 * 1000)) {
        console.error('⚠️  Safety break: Loop exceeded end time by more than 24 hours');
        break;
      }
    }
    
    return Math.round(businessHours * 100) / 100; // Round to 2 decimal places
  }

  try {
    const contactId = String(event.object.objectId);

    console.log('='.repeat(80));
    console.log('🚀 CONTACT CREATION TO FIRST ENGAGEMENT BUSINESS HOURS CALCULATION STARTED');
    console.log('='.repeat(80));
    console.log('📋 WORKFLOW INFO:');
    console.log(`   Contact ID: ${contactId}`);
    console.log(`   Timestamp: ${new Date().toISOString()}`);
    console.log(`   Event Type: ${event.eventType || 'unknown'}`);
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 1: GET CONTACT DETAILS
    // ========================================================================
    console.log('📊 STEP 1: GETTING CONTACT DETAILS');
    console.log('-'.repeat(50));

    let contact;
    try {
      contact = await client.crm.contacts.basicApi.getById(contactId, [
        'createdate',
        'hs_sa_first_engagement_date',
        'firstname',
        'lastname',
        'email',
        'cycle_time_lead_to_first_touch_business_hours' // Custom field to store result
      ]);
      
      console.log(`✅ CONTACT FOUND: Successfully retrieved contact ${contactId}`);
      console.log(`🔍 Contact Properties:`, JSON.stringify(contact.properties, null, 2));
    } catch (contactError) {
      console.error(`❌ CONTACT NOT FOUND: Contact ${contactId} could not be retrieved`);
      console.error(`Error details:`, contactError.message);
      callback(new Error(`Contact ${contactId} not found: ${contactError.message}`));
      return;
    }

    const contactName = `${contact.properties.firstname || ''} ${contact.properties.lastname || ''}`.trim() || 'Unknown';
    const contactEmail = contact.properties.email || 'No email';
    const createdate = contact.properties.createdate;
    const currentEngagementDate = contact.properties.hs_sa_first_engagement_date;
    const currentBusinessHoursValue = contact.properties.cycle_time_lead_to_first_touch_business_hours;

    console.log(`Contact Name: ${contactName}`);
    console.log(`Contact Email: ${contactEmail}`);
    console.log(`Created Date: ${createdate}`);
    console.log(`Current Engagement Date (may be owner-specific): ${currentEngagementDate || 'Not set'}`);
    console.log(`Current Business Hours Value: ${currentBusinessHoursValue || 'Not set (blank)'}`);

    // ========================================================================
    // STEP 2: GET EARLIEST ENGAGEMENT DATE FROM HISTORY (FIRST EVER, REGARDLESS OF OWNER)
    // ========================================================================
    console.log('🔍 STEP 2: GETTING EARLIEST ENGAGEMENT DATE FROM HISTORY');
    console.log('-'.repeat(50));

    if (!createdate) {
      console.error(`❌ NO CREATED DATE: Contact ${contactId} has no createdate property`);
      callback(new Error(`Contact ${contactId} has no createdate property`));
      return;
    }

    // Get the earliest engagement date ever (first engagement regardless of owner)
    let firstEngagementDate = await getEarliestEngagementDateFromHistory(contactId);
    
    if (!firstEngagementDate) {
      // Fallback to current value if history is not available
      if (!currentEngagementDate) {
        console.log(`ℹ️  NO FIRST ENGAGEMENT DATE: Contact ${contactId} has no engagement date - workflow should not have triggered`);
        callback(null, 'Success'); // Not an error, just no engagement yet
        return;
      } else {
        console.log(`⚠️  PROPERTY HISTORY NOT AVAILABLE: Using current engagement date as fallback: ${currentEngagementDate}`);
        firstEngagementDate = currentEngagementDate;
      }
    } else {
      console.log(`✅ EARLIEST ENGAGEMENT DATE FOUND: ${firstEngagementDate} (first engagement ever, regardless of owner)`);
      if (currentEngagementDate && currentEngagementDate !== firstEngagementDate) {
        console.log(`ℹ️  NOTE: Current engagement date (${currentEngagementDate}) differs from earliest (${firstEngagementDate}) - owner may have changed`);
      }
    }

    console.log('✅ STEP 2 COMPLETE - Earliest engagement date retrieved');
    console.log('='.repeat(80));

    // Check if field is already populated
    if (currentBusinessHoursValue !== null && currentBusinessHoursValue !== undefined && currentBusinessHoursValue !== '') {
      console.log(`✅ FIELD ALREADY POPULATED: cycle_time_lead_to_first_touch_business_hours = ${currentBusinessHoursValue}`);
      console.log(`ℹ️  Skipping calculation - field already has value (first engagement already calculated)`);
      callback(null, 'Success');
      return;
    }

    // ========================================================================
    // STEP 3: CALCULATE BUSINESS HOURS
    // ========================================================================
    console.log('🕐 STEP 3: CALCULATING BUSINESS HOURS');
    console.log('-'.repeat(50));

    const businessHours = calculateBusinessHours(createdate, firstEngagementDate);
    
    const createdAr = convertToArgentinaTimezone(createdate);
    const engagementAr = convertToArgentinaTimezone(firstEngagementDate);
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    console.log(`Created Date (UTC): ${createdate}`);
    console.log(`Created Date (Argentina): ${createdAr.toDateString()} ${createdAr.toTimeString()}`);
    console.log(`Created Day: ${dayNames[createdAr.dayOfWeek]}`);
    console.log(`First Engagement (UTC): ${firstEngagementDate}`);
    console.log(`First Engagement (Argentina): ${engagementAr.toDateString()} ${engagementAr.toTimeString()}`);
    console.log(`Engagement Day: ${dayNames[engagementAr.dayOfWeek]}`);
    console.log(`Business Hours Calculated: ${businessHours} hours`);

    console.log('✅ STEP 3 COMPLETE');
    console.log('='.repeat(80));

    // ========================================================================
    // STEP 4: UPDATE CONTACT PROPERTY
    // ========================================================================
    console.log('💾 STEP 4: UPDATING CONTACT PROPERTY');
    console.log('-'.repeat(50));

    try {
      await client.crm.contacts.basicApi.update(contactId, {
        properties: {
          cycle_time_lead_to_first_touch_business_hours: String(businessHours)
        }
      });

      console.log(`✅ PROPERTY UPDATED: Successfully updated contact ${contactId}`);
      console.log(`   cycle_time_lead_to_first_touch_business_hours = ${businessHours} hours`);
    } catch (updateError) {
      console.error(`❌ UPDATE FAILED: ${updateError.message}`);
      console.error(`Error details:`, updateError);
      callback(new Error(`Failed to update contact property: ${updateError.message}`));
      return;
    }

    console.log('✅ STEP 4 COMPLETE');
    console.log('='.repeat(80));

    // ========================================================================
    // FINAL SUMMARY
    // ========================================================================
    console.log('📊 FINAL WORKFLOW EXECUTION SUMMARY');
    console.log('-'.repeat(50));
    console.log(`Contact: ${contactName} (${contactEmail}) - ID: ${contactId}`);
    console.log(`Created Date (Argentina): ${createdAr.toDateString()} ${createdAr.toTimeString()}`);
    console.log(`First Engagement (Argentina): ${engagementAr.toDateString()} ${engagementAr.toTimeString()}`);
    console.log(`Business Hours: ${businessHours} hours`);
    console.log(`Field Updated: cycle_time_lead_to_first_touch_business_hours = ${businessHours}`);
    console.log('='.repeat(80));
    console.log('🎉 BUSINESS HOURS CALCULATION COMPLETED SUCCESSFULLY');
    console.log('='.repeat(80));

    callback(null, 'Success');

  } catch (err) {
    console.error('=== ERROR OCCURRED ===');
    console.error('Error type:', err.constructor.name);
    console.error('Error message:', err.message);
    console.error('Error stack:', err.stack);

    // Check if this is a rate limit error (429)
    const isRateLimit = err.code === 429 || 
                       (err.response && err.response.status === 429) ||
                       (err.body && err.body.errorType === 'RATE_LIMIT');

    if (isRateLimit) {
      console.error('⚠️ RATE LIMIT ERROR DETECTED (429)');
      console.error('HubSpot workflows will automatically retry this contact');
      console.error('This is expected when processing many contacts - HubSpot will retry with backoff');
      // Let the error propagate so HubSpot knows to retry this contact
      // HubSpot workflows automatically retry failed actions with exponential backoff
      callback(err);
      return;
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

    callback(err);
  }
};
