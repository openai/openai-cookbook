# Zapier Integration for Mixpanel Insight Report Export

## Quick Reference

**Goal:** Extract emails from Mixpanel Insight reports and iterate through them in Zapier

**Zapier Workflow:**
1. **Webhooks by Zapier (GET)** → Fetch Mixpanel report JSON
2. **Code by Zapier (JavaScript)** → Extract emails array
3. **Iterator by Zapier** → Iterate over each email
4. **Your Action** → Process each email (HubSpot, Email, etc.)

**Code Files:**
- JavaScript code for Zapier: `/tools/scripts/mixpanel/zapier_email_extraction.js`
- Test script: `/tools/scripts/mixpanel/test_email_extraction.js`

**Quick Start:**
1. Copy code from `zapier_email_extraction.js`
2. Paste into Zapier "Code by Zapier" (JavaScript)
3. Map `mixpanel_response` input to your Webhook's `data` field
4. Use "Iterator by Zapier" to process each email

---

## Overview

Zapier doesn't have a native "Download Insight Report" action for Mixpanel. However, you can use **"Webhooks by Zapier"** to make direct API calls to Mixpanel's Insight Reports endpoint.

## Zapier Setup: Webhooks by Zapier

### Step 1: Create a New Zap

1. Log into Zapier
2. Click "Create Zap"
3. Set up your trigger (e.g., Schedule, Manual, or another app trigger)

### Step 2: Add "Webhooks by Zapier" Action

1. Search for **"Webhooks by Zapier"**
2. Select **"GET"** as the action event
3. Configure the webhook with the following settings:

#### Configuration Details:

**URL:**
```
https://mixpanel.com/api/query/insights?project_id=2201475&bookmark_id={{bookmark_id}}
```

**OR** (if using dynamic values):
```
https://mixpanel.com/api/query/insights?project_id={{project_id}}&bookmark_id={{bookmark_id}}
```

**⚠️ IMPORTANT:** For GET requests, query parameters must be in the URL, NOT in the `data` field!

**Method:** `GET`

**Query String Parameters (in URL):**
- `project_id`: `2201475` (or `{{project_id}}` for dynamic)
- `bookmark_id`: `{{bookmark_id}}` (dynamic value - the report bookmark ID)

**Data Field:** 
- Leave `data` field **EMPTY** or remove it entirely
- GET requests don't use request body - parameters go in URL

**Headers:**
- `Content-Type`: `application/json`

**Authentication:**
- **Type:** Basic Auth
- **Username:** `{{MIXPANEL_USERNAME}}` or `jql_cursor.d931a5.mp-service-account`
- **Password:** `{{MIXPANEL_PASSWORD}}` or your service account password
- **Format:** In Zapier, you can use the pipe format: `username|password` in the auth field, OR configure separately

### Step 3: Process the Response

After the webhook returns the JSON response, you can:

1. **Use "Code by Zapier"** to process the JSON (convert to CSV, flatten, etc.)
2. **Send to Google Sheets** using Zapier's Google Sheets integration
3. **Store in a database** or send via email

## Reusable Code from Our Implementation

### 1. API Request Structure

**From `mixpanel_api.py` lines 171-187:**

```python
# URL and parameters
url = "https://mixpanel.com/api/query/insights"
params = {
    'project_id': self.project_id,  # 2201475
    'bookmark_id': bookmark_id       # e.g., '72369475'
}

# GET request with Basic Auth
response = requests.get(
    url,
    params=params,
    auth=(username, password),  # HTTP Basic Auth
    headers={'Content-Type': 'application/json'}
)
```

**Zapier Equivalent:**
- URL: `https://mixpanel.com/api/query/insights`
- Method: GET
- Query Params: `project_id` and `bookmark_id`
- Auth: Basic Auth with username/password

### 2. Response Structure

The API returns a JSON object with this structure:

```json
{
  "headers": ["$metric", "$time", "email"],
  "computed_at": "2025-12-09T10:51:02.723593+00:00",
  "date_range": {
    "from_date": "2025-12-02T00:00:00-03:00",
    "to_date": "2025-12-09T07:51:02.544012-03:00"
  },
  "meta": {
    "min_sampling_factor": 1.0,
    "is_segmentation_limit_hit": false,
    "sub_query_count": 1,
    "report_sections": { ... }
  },
  "series": {
    "Metric Name": {
      "$overall": {"all": 4},
      "2025-12-03T15:11:01": {
        "$overall": {"all": 1},
        "email@example.com": {"all": 1}
      }
    }
  }
}
```

### 3. CSV Conversion Logic (for Code by Zapier)

If you want to convert the JSON to CSV in Zapier using "Code by Zapier", you can adapt the flattening logic from `_write_insight_to_csv` method.

**Key functions to reuse:**
- `flatten_dict()` - Recursively flattens nested dictionaries
- `summarize_complex_value()` - Summarizes large nested structures
- `safe_str()` - Safely converts values to strings

**Note:** Zapier's Code by Zapier has execution time limits, so for very large reports (like the 2,058 date keys example), you may need to:
- Process in chunks
- Summarize the series data instead of fully flattening
- Use a separate service/endpoint for processing

## Recommended Zapier Workflow

### Option 1: Simple JSON Storage

1. **Trigger:** Schedule (daily/weekly) or Manual
2. **Action:** Webhooks by Zapier (GET) - Fetch insight report
3. **Action:** Google Sheets - Create row with JSON data
   - Store the raw JSON in a cell
   - Or flatten key fields (computed_at, date_range, overall values)

### Option 2: Processed CSV Export

1. **Trigger:** Schedule or Manual
2. **Action:** Webhooks by Zapier (GET) - Fetch insight report
3. **Action:** Code by Zapier (Python) - Process JSON to CSV
   - Use simplified flattening logic
   - Focus on key metrics, not full series breakdown
4. **Action:** Google Sheets - Append rows from CSV
   - Or send CSV via email
   - Or store in Google Drive

### Option 3: Webhook to Your Server

1. **Trigger:** Schedule or Manual
2. **Action:** Webhooks by Zapier (POST) - Call your server endpoint
   - Your server runs the full `export_insight_report` function
   - Returns CSV or processed data
3. **Action:** Process the response (store, email, etc.)

## Common Zapier Configuration Issues

### Issue: "project_id is a required parameter" Error

**Problem:** You're putting `project_id` and `bookmark_id` in the `data` field, but GET requests need them in the URL query string.

**Solution:**
1. **Remove from `data` field** - Don't put parameters in the `data` section
2. **Add to URL** - Include them as query parameters in the URL:
   ```
   https://mixpanel.com/api/query/insights?project_id=2201475&bookmark_id=72369475
   ```

**Correct Zapier Configuration:**
- **URL:** `https://mixpanel.com/api/query/insights?project_id=2201475&bookmark_id={{bookmark_id}}`
- **Method:** GET
- **Data:** Leave empty or remove
- **Auth:** Basic Auth with username/password
- **Headers:** `Content-Type: application/json`

### Issue: Authentication Format

Zapier's Basic Auth can be configured in two ways:

**Option 1: Separate fields (recommended)**
- Username: `jql_cursor.d931a5.mp-service-account`
- Password: `tuMQH6S7YufrX1vbhbkd1M8l6ce5E5TP`

**Option 2: Pipe format**
- Auth: `jql_cursor.d931a5.mp-service-account|tuMQH6S7YufrX1vbhbkd1M8l6ce5E5TP`

## Code by Zapier: Extract Emails for Iteration

### JavaScript Code for "Code by Zapier" (JavaScript)

Use this code to extract a list of unique emails from the Mixpanel Insight report JSON. The output is an array that Zapier can iterate over using the "Iterator by Zapier" action.

**Input Variable:** `mixpanel_response` (the JSON response from the Webhooks by Zapier step)

```javascript
// Extract emails from Mixpanel Insight report JSON
// Input: mixpanel_response (from Webhooks by Zapier output)

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
return uniqueEmails.map((item, index) => ({
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
```

**Alternative: Simple Email List (Just Emails)**

If you only need the email addresses without metadata:

```javascript
// Simple version: Just return array of email strings
const response = inputData.mixpanel_response || inputData.data || inputData;
const emails = [];
const series = response.series || {};

Object.keys(series).forEach(metricName => {
  const metricData = series[metricName];
  Object.keys(metricData).forEach(dateKey => {
    if (dateKey !== '$overall' && dateKey.match(/^\d{4}-\d{2}-\d{2}/)) {
      const dateData = metricData[dateKey];
      Object.keys(dateData).forEach(key => {
        if (key.includes('@') && key !== '$overall') {
          if (!emails.includes(key)) {
            emails.push(key);
          }
        }
      });
    }
  });
});

// Return as array of objects for Zapier iteration
return emails.map((email, index) => ({
  email: email,
  index: index + 1
}));
```

### How to Use in Zapier - Complete Workflow

#### Step-by-Step Setup:

**Step 1: Webhooks by Zapier (GET) - Fetch Mixpanel Report**
- **App:** Webhooks by Zapier
- **Event:** GET
- **URL:** `https://mixpanel.com/api/query/insights?project_id=2201475&bookmark_id={{bookmark_id}}`
- **Method:** GET
- **Data:** Leave empty
- **Authentication:** Basic Auth
  - Username: `jql_cursor.d931a5.mp-service-account`
  - Password: `{{MIXPANEL_PASSWORD}}` (store as Zapier variable)
- **Headers:** `Content-Type: application/json`
- **Output:** This step will return a `data` field containing the JSON response

**Step 2: Code by Zapier (JavaScript) - Extract Emails**
- **App:** Code by Zapier
- **Language:** JavaScript
- **Input Data:**
  - Variable name: `mixpanel_response`
  - Value: Map to `data` from Step 1 (or use `{{1.data}}` in Zapier)
- **Code:** Copy the JavaScript code from the section above (or use `/tools/scripts/mixpanel/zapier_email_extraction.js`)
- **Output:** Returns an array of email objects

**Step 3: Iterator by Zapier - Iterate Over Emails**
- **App:** Iterator by Zapier
- **Input:** The array from Step 2
- **Output:** This creates one Zap run for each email in the array
- Each iteration will have access to:
  - `{{email}}` - The email address
  - `{{metric}}` - The metric name
  - `{{first_seen_date}}` - When this email first appeared
  - `{{count}}` - Count value
  - `{{index}}` - Position in the list (1, 2, 3...)
  - `{{total_emails}}` - Total number of emails found

**Step 4: Your Action - Process Each Email**
- **Examples:**
  - **HubSpot:** Create/Update Contact with `{{email}}`
  - **Email:** Send personalized email to `{{email}}`
  - **Google Sheets:** Add row with email and metadata
  - **Slack:** Send notification about each email
  - **Intercom:** Create user or conversation

**Example: Complete Zap Flow**
```
Trigger (Schedule/Manual)
  ↓
Webhooks by Zapier (GET) → Fetch Mixpanel report
  ↓
Code by Zapier (JavaScript) → Extract emails array
  ↓
Iterator by Zapier → Create one run per email
  ↓
HubSpot → Create Contact with {{email}}
  ↓
Email → Send welcome email to {{email}}
```

### Example Zapier Output Structure

After running the code, Zapier will output an array like:

```json
[
  {
    "email": "estudiomc.recepcion@gmail.com",
    "metric": "Uniques of Invitó usuario",
    "first_seen_date": "2025-12-03T15:11:01",
    "count": 1,
    "computed_at": "2025-12-09T10:51:02.723593+00:00",
    "date_range_from": "2025-12-02T00:00:00-03:00",
    "date_range_to": "2025-12-09T07:51:02.544012-03:00",
    "index": 1,
    "total_emails": 5
  },
  {
    "email": "luciatorres@estudiofay.com",
    "metric": "Uniques of Invitó usuario",
    "first_seen_date": "2025-12-05T14:58:21",
    "count": 1,
    ...
  }
]
```

## Code by Zapier Example (Simplified - Python)

If you want to use "Code by Zapier" (Python) to process the response, here's a simplified version:

```python
# Input: response_data (from Webhooks by Zapier output)
import json

def flatten_simple(data, parent_key='', sep='_'):
    """Simplified flattening for Zapier (limited depth)"""
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            if len(v) <= 10:  # Only flatten small dicts
                items.extend(flatten_simple(v, new_key, sep=sep).items())
            else:
                # Summarize large dicts
                items.append((new_key, f"{len(v)} items"))
        elif isinstance(v, list):
            items.append((new_key, json.dumps(v[:5]) + f" ... {len(v)} total"))
        else:
            items.append((new_key, str(v)))
    return dict(items)

# Get response from webhook
response_data = input_data['response_data']  # Adjust based on Zapier output structure

# Flatten the data
flattened = flatten_simple(response_data)

# Output for next step
output = {
    'computed_at': response_data.get('computed_at', ''),
    'date_range_from': response_data.get('date_range', {}).get('from_date', ''),
    'date_range_to': response_data.get('date_range', {}).get('to_date', ''),
    'overall_value': response_data.get('series', {}).get('Metric Name', {}).get('$overall', {}).get('all', 0),
    'flattened_data': json.dumps(flattened)
}
```

## Important Notes

1. **Rate Limits:** Mixpanel has rate limits (60 queries/hour). Be careful with scheduled Zaps that run frequently.

2. **Authentication:** Store Mixpanel credentials as Zapier secrets/variables for security:
   - Go to Zap Settings → Variables
   - Add `MIXPANEL_USERNAME` and `MIXPANEL_PASSWORD`

3. **Bookmark ID:** You need to extract the bookmark ID from the Mixpanel report URL:
   - Open the report in Mixpanel
   - Look for `report-{BOOKMARK_ID}` in the URL
   - Use that number as the `bookmark_id` parameter

4. **Large Reports:** For reports with thousands of date keys, consider:
   - Processing on your server instead of in Zapier
   - Summarizing the data instead of full export
   - Using a different approach (direct API integration)

## Alternative: Server Endpoint

Instead of processing in Zapier, you can:

1. Create a Flask/FastAPI endpoint that uses your `export_insight_report` function
2. Have Zapier call that endpoint via webhook
3. The server handles the full processing and returns CSV/JSON
4. Zapier receives the processed data

This approach:
- ✅ No execution time limits
- ✅ Can handle large reports
- ✅ Reuses all your existing code
- ✅ Better error handling
- ❌ Requires hosting a server

## Summary

**Zapier Task to Use:**
- **"Webhooks by Zapier"** → **"GET"** action

**Code You Can Reuse:**
- API endpoint URL: `https://mixpanel.com/api/query/insights`
- Request parameters: `project_id`, `bookmark_id`
- Authentication method: HTTP Basic Auth
- Response structure understanding
- CSV flattening logic (simplified for Zapier's limits)

**Best Approach:**
For production use with large reports, consider creating a server endpoint that Zapier calls, which then uses your full `export_insight_report` implementation.

