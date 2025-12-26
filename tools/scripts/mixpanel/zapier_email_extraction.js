/**
 * Zapier "Code by Zapier" (JavaScript) - Extract Emails from Mixpanel Insight Report
 * 
 * INSTRUCTIONS:
 * 1. In Zapier, add a "Code by Zapier" step after your "Webhooks by Zapier" step
 * 2. Select "JavaScript" as the language
 * 3. In "Input Data", add a variable: `mixpanel_response`
 * 4. Map it to one of these from Step 2:
 *    - {{2.data}} (recommended - entire response)
 *    - {{2}} (entire Step 2 output)
 *    - {{2.series}} (if you want to pass only the series object)
 * 5. Paste this entire code into the code editor
 * 6. The output will be an array of email objects that you can iterate with "Iterator by Zapier"
 * 
 * NOTE: With "Unflatten: Yes" in your Webhook step, the data should be nested.
 *       The code will automatically find the `series` object from the response.
 */

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

// Debug: Log the structure (remove in production if needed)
// console.log('Response type:', typeof response);
// console.log('Response keys:', Object.keys(response || {}));

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
  console.log('Warning: series object is empty');
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
console.log('Total emails found:', emails.length);
console.log('Unique emails:', uniqueEmails.length);
if (uniqueEmails.length > 0) {
  console.log('First email:', uniqueEmails[0].email);
  console.log('All emails:', uniqueEmails.map(e => e.email).join(', '));
}

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
output = Array.isArray(emailArray) ? emailArray : [];

// Debug: Verify output structure
console.log('Output is array:', Array.isArray(output));
console.log('Output length:', output.length);
if (output.length > 0) {
  console.log('Output first item keys:', Object.keys(output[0]));
}

