const fs = require('fs');
const path = require('path');

// Read the raw JSON file (this is what Zapier receives from Step 2)
const jsonPath = path.join(__dirname, 'insight_report_72369475_raw.json');
const mixpanelResponse = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));

console.log('='.repeat(80));
console.log('SIMULATING ZAPIER ENVIRONMENT');
console.log('='.repeat(80));
console.log('\n📥 Input from Step 2 (Webhooks by Zapier):');
console.log('   - Total keys in response:', Object.keys(mixpanelResponse).length);
console.log('   - Has "series" key:', 'series' in mixpanelResponse);
console.log('   - Series keys:', Object.keys(mixpanelResponse.series || {}));
console.log('\n');

// Simulate Zapier's inputData structure
// This is how Zapier passes data to "Code by Zapier"
const inputData = {
  mixpanel_response: mixpanelResponse  // This is what you map from {{2.data}}
};

console.log('🔧 Simulating Zapier "Code by Zapier" step...\n');

// ============================================
// ZAPIER CODE (from zapier_email_extraction.js)
// ============================================

// Get the Mixpanel response (adjust variable name based on your Zapier setup)
// Try multiple possible input field names
let response = inputData.mixpanel_response || 
               inputData.data || 
               inputData;

// If response is still the whole inputData object, try to find the actual data
if (response === inputData && Object.keys(inputData).length > 0) {
  // Try common Zapier output field names
  response = inputData.data || 
             inputData.body || 
             inputData.content ||
             inputData;
}

// Parse if it's a JSON string
if (typeof response === 'string') {
  try {
    response = JSON.parse(response);
  } catch (e) {
    response = {};
  }
}

// Helper function to check if a string looks like an email
function isEmail(str) {
  return typeof str === 'string' && 
         str.includes('@') && 
         str !== '$overall' &&
         !str.match(/^\d{4}-\d{2}-\d{2}/); // Not a date string
}

// Helper function to check if a string looks like a date/timestamp
function isDateKey(str) {
  return typeof str === 'string' && 
         (str.match(/^\d{4}-\d{2}-\d{2}/) || str === '$overall');
}

// Extract all emails from the series object
const emails = [];

// Access series - try multiple possible paths based on Zapier's unflattening
let series = response.series || 
             response.Series ||
             response['series'] ||
             {};

// If series is still empty, the data structure might be different
// Check if series is nested differently or if we need to access it from the root
if (!series || Object.keys(series).length === 0) {
  // Try accessing from inputData directly (in case response is the whole object)
  series = inputData.series || 
           inputData.Series ||
           inputData['series'] ||
           {};
}

// If still empty, log for debugging
if (!series || Object.keys(series).length === 0) {
  // This will help debug - check Zapier logs
  console.log('⚠️  Warning: series object is empty');
  console.log('Response keys:', Object.keys(response || {}));
  console.log('InputData keys:', Object.keys(inputData || {}));
}

// Iterate through each metric in series
Object.keys(series).forEach(metricName => {
  const metricData = series[metricName];
  
  // Skip if metricData is not an object
  if (typeof metricData !== 'object' || metricData === null) {
    return;
  }
  
  // Iterate through each date key in the metric
  Object.keys(metricData).forEach(dateKey => {
    // Skip $overall - we want the date keys
    if (isDateKey(dateKey) && dateKey !== '$overall') {
      const dateData = metricData[dateKey];
      
      // Skip if dateData is not an object
      if (typeof dateData !== 'object' || dateData === null) {
        return;
      }
      
      // Extract emails from this date's data
      Object.keys(dateData).forEach(key => {
        if (isEmail(key)) {
          const emailData = dateData[key];
          const count = emailData?.all || emailData?.value || emailData || 0;
          
          emails.push({
            email: key,
            metric: metricName,
            date: dateKey,
            count: count,
            computed_at: response.computed_at || response['Computed At'] || '',
            date_range_from: response.date_range?.from_date || 
                            response.date_range?.['Date Range From Date'] || 
                            response['Date Range From Date'] || '',
            date_range_to: response.date_range?.to_date || 
                          response.date_range?.['Date Range To Date'] || 
                          response['Date Range To Date'] || ''
          });
        }
      });
    }
  });
});

// Remove duplicates (same email can appear in multiple dates)
const uniqueEmails = [];
const seenEmails = new Set();

emails.forEach(item => {
  if (!seenEmails.has(item.email)) {
    seenEmails.add(item.email);
    uniqueEmails.push(item);
  }
});

// Debug: Log what we found (check Zapier logs)
console.log('📊 Processing Results:');
console.log('   - Total emails found:', emails.length);
console.log('   - Unique emails:', uniqueEmails.length);
if (uniqueEmails.length > 0) {
  console.log('   - First email:', uniqueEmails[0].email);
  console.log('   - All emails:', uniqueEmails.map(e => e.email).join(', '));
}
console.log('\n');

// Output: Array of email objects for Zapier iteration
// Zapier pre-declares 'output' - assign to it, don't declare it
// This array will be used by "Iterator by Zapier" in the next step
const emailArray = uniqueEmails.map((item, index) => ({
  email: item.email,
  metric: item.metric,
  first_seen_date: item.date,
  count: item.count,
  computed_at: item.computed_at,
  date_range_from: item.date_range_from,
  date_range_to: item.date_range_to,
  index: index + 1,
  total_emails: uniqueEmails.length
}));

// Ensure output is definitely an array
let output = Array.isArray(emailArray) ? emailArray : [];

// Debug: Verify output structure
console.log('✅ Output Verification:');
console.log('   - Output is array:', Array.isArray(output));
console.log('   - Output length:', output.length);
if (output.length > 0) {
  console.log('   - Output first item keys:', Object.keys(output[0]));
}
console.log('\n');

// ============================================
// DISPLAY RESULTS
// ============================================

console.log('='.repeat(80));
console.log('📤 OUTPUT ARRAY (This is what Zapier "Iterator by Zapier" will iterate):');
console.log('='.repeat(80));
console.log(JSON.stringify(output, null, 2));
console.log('\n');

console.log('='.repeat(80));
console.log('📋 SUMMARY - What Zapier will see:');
console.log('='.repeat(80));
console.log(`Total items in array: ${output.length}`);
console.log('\nEach item in the array:\n');

output.forEach((item, idx) => {
  console.log(`  ${idx + 1}. ${item.email}`);
  console.log(`     - Metric: ${item.metric}`);
  console.log(`     - First Seen: ${item.first_seen_date}`);
  console.log(`     - Count: ${item.count}`);
  console.log(`     - Index: ${item.index}/${item.total_emails}`);
  console.log('');
});

console.log('='.repeat(80));
console.log('💡 IMPORTANT: In Zapier, you MUST add "Iterator by Zapier" step');
console.log('   after this "Code by Zapier" step to iterate through each email.');
console.log('   The preview in Zapier only shows the FIRST item, but the array');
console.log('   contains ALL items. The Iterator will process each one separately.');
console.log('='.repeat(80));


