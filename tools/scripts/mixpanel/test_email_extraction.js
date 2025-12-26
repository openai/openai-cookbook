/**
 * Test script for email extraction from Mixpanel Insight report JSON
 * This simulates what the Zapier "Code by Zapier" JavaScript code will do
 */

const fs = require('fs');
const path = require('path');

// Read the raw JSON file
const jsonPath = path.join(__dirname, 'insight_report_72369475_raw.json');
const rawJson = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));

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
const series = rawJson.series || {};

// Iterate through each metric in series
Object.keys(series).forEach(metricName => {
  const metricData = series[metricName];
  
  // Iterate through each date key in the metric
  Object.keys(metricData).forEach(dateKey => {
    // Skip $overall and date keys - we want the email keys
    if (isDateKey(dateKey)) {
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
            computed_at: rawJson.computed_at || '',
            date_range_from: rawJson.date_range?.from_date || '',
            date_range_to: rawJson.date_range?.to_date || ''
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

console.log('📧 Extracted Emails:');
console.log('='.repeat(60));
console.log(JSON.stringify(output, null, 2));
console.log('='.repeat(60));
console.log(`\n✅ Total unique emails: ${uniqueEmails.length}`);
console.log(`📊 Total email occurrences: ${emails.length}`);





