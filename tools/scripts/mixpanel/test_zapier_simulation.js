/**
 * Simulate Zapier "Code by Zapier" environment
 * Tests the email extraction code as it would run in Zapier
 */

const fs = require('fs');
const path = require('path');

// Read the raw JSON file (simulating what Zapier receives from Webhooks)
const jsonPath = path.join(__dirname, 'insight_report_72369475_raw.json');
const mixpanelResponse = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));

// Simulate Zapier's inputData structure
const inputData = {
  mixpanel_response: mixpanelResponse
};

// ============================================
// ZAPIER CODE STARTS HERE (copy from zapier_email_extraction.js)
// ============================================

// Get the Mixpanel response (adjust variable name based on your Zapier setup)
const response = inputData.mixpanel_response || inputData.data || inputData;

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
const series = response.series || {};

// Iterate through each metric in series
Object.keys(series).forEach(metricName => {
  const metricData = series[metricName];
  
  // Iterate through each date key in the metric
  Object.keys(metricData).forEach(dateKey => {
    // Skip $overall - we want the date keys
    if (isDateKey(dateKey) && dateKey !== '$overall') {
      const dateData = metricData[dateKey];
      
      // Extract emails from this date's data
      Object.keys(dateData).forEach(key => {
        if (isEmail(key)) {
          const emailData = dateData[key];
          const count = emailData?.all || emailData?.value || 0;
          
          emails.push({
            email: key,
            metric: metricName,
            date: dateKey,
            count: count,
            computed_at: response.computed_at || '',
            date_range_from: response.date_range?.from_date || '',
            date_range_to: response.date_range?.to_date || ''
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

// Output: Array of email objects for Zapier iteration
// Zapier expects an array returned directly
const output = uniqueEmails.map((item, index) => ({
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

// ============================================
// ZAPIER CODE ENDS HERE
// ============================================

// Display results
console.log('🔧 Zapier Simulation Test');
console.log('='.repeat(70));
console.log('\n📥 Input (from Webhooks by Zapier):');
console.log(`   - Response structure: ${Object.keys(response).join(', ')}`);
console.log(`   - Metrics found: ${Object.keys(series).length}`);
console.log(`   - Date range: ${response.date_range?.from_date} to ${response.date_range?.to_date}`);

console.log('\n📤 Output (for Iterator by Zapier):');
console.log(`   - Total unique emails: ${output.length}`);
console.log(`   - Array structure: Array of ${output.length} objects\n`);

console.log('📋 Extracted Emails:');
console.log('-'.repeat(70));
output.forEach((item, idx) => {
  console.log(`\n${idx + 1}. ${item.email}`);
  console.log(`   Metric: ${item.metric}`);
  console.log(`   First Seen: ${item.first_seen_date}`);
  console.log(`   Count: ${item.count}`);
  console.log(`   Index: ${item.index}/${item.total_emails}`);
});

console.log('\n' + '='.repeat(70));
console.log('✅ Zapier Simulation Complete!');
console.log('\n📊 Summary:');
console.log(`   - Input JSON keys: ${Object.keys(response).join(', ')}`);
console.log(`   - Emails extracted: ${output.length}`);
console.log(`   - Output format: Array ready for Iterator by Zapier`);
console.log('\n💡 In Zapier, this array will be passed to "Iterator by Zapier"');
console.log('   Each iteration will have access to: email, metric, first_seen_date, count, etc.\n');

// Also output as JSON for easy copy-paste
console.log('📄 JSON Output (for reference):');
console.log(JSON.stringify(output, null, 2));

