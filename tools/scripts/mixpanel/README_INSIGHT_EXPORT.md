# Mixpanel Insight Report Export

## How to Export Insight Reports to CSV

### Step 1: Get the Bookmark ID

The share link (`https://mixpanel.com/s/1XEB5C`) contains a **share token**, not a bookmark_id. To get the actual bookmark_id:

1. **Open the report in Mixpanel** using the share link
2. **Look at the URL** in your browser - it will look like:
   ```
   https://mixpanel.com/project/2201475/view/142035/app/boards#id=12345&editor-card-id="report-123456"
   ```
3. **Extract the bookmark_id** - it's the number after `report-` (e.g., `123456`)

### Step 2: Export Using Command Line

**Recommended script:** `download_insight.py` (uses GET method, avoids rate limits)

```bash
cd /Users/virulana/openai-cookbook/tools/scripts/mixpanel

# Export by bookmark ID
python download_insight.py --bookmark-id 123456

# Export with custom output file
python download_insight.py --bookmark-id 123456 --output my_report.csv

# With workspace ID (if needed)
python download_insight.py --bookmark-id 123456 --workspace-id 142035 --output report.csv
```

**Alternative script:** `export_insight_report.py` (legacy, uses POST method)

```bash
# Export by bookmark ID
python export_insight_report.py --bookmark-id 123456

# Export with custom output file
python export_insight_report.py --bookmark-id 123456 --output my_report.csv
```

### CSV Output Format

All exported CSV files use **comma (`,`) as the field separator** and are formatted for direct import into spreadsheets:
- ✅ Compatible with Google Sheets
- ✅ Compatible with Excel
- ✅ Properly escaped fields with commas
- ✅ Nested structures flattened with underscores

### Step 3: Set Up Zapier Webhook

For automated exports via Zapier:

1. **Run the webhook server:**
   ```bash
   python mixpanel_webhook_server.py
   ```

2. **Use ngrok for local testing:**
   ```bash
   ngrok http 5000
   ```

3. **Configure Zapier webhook** to POST to:
   ```
   http://your-ngrok-url.ngrok.io/webhook/mixpanel-query/predefined
   ```

4. **Send JSON payload:**
   ```json
   {
     "query_type": "12_users_2025",
     "format": "csv"
   }
   ```

   Or for custom JQL queries:
   ```json
   {
     "jql_query": "function main() { return Events({from_date: '2025-01-01', to_date: '2025-12-08'}).groupBy(['name'], mixpanel.reducer.count()); }",
     "format": "csv"
   }
   ```

## Alternative: Use JQL Query Instead

If you can't get the bookmark_id, you can recreate the insight report as a JQL query:

1. **Open the report in Mixpanel** and note what it shows
2. **Recreate it as a JQL query** using `run_jql.py`
3. **Export to CSV** using the webhook or command line

Example:
```bash
# Export JQL query to CSV
python run_jql.py --file example_query.jql --format csv --output report.csv
```

## CSV Format Details

All CSV exports are formatted with **comma (`,`) as the field separator** for spreadsheet compatibility:

- **Field Separator**: Comma (`,`)
- **Text Qualifier**: Double quotes (`"`) for fields containing commas or special characters
- **Encoding**: UTF-8
- **Line Endings**: Unix-style (`\n`)
- **Nested Data**: Flattened with underscore separators (e.g., `date_range_from_date`, `meta_min_sampling_factor`)
- **Lists/Arrays**: Converted to JSON strings for preservation

**Example CSV structure:**
```csv
computed_at,date_range_from_date,date_range_to_date,headers,meta_min_sampling_factor
2025-12-08T22:40:39.376019+00:00,2025-12-01T00:00:00-03:00,2025-12-08T19:40:38.768592-03:00,"['$funnel', '$os']",1.0
```

The CSV files can be directly imported into:
- ✅ Google Sheets
- ✅ Microsoft Excel
- ✅ Numbers (macOS)
- ✅ Any spreadsheet application that supports CSV

## Troubleshooting

- **"Invalid insights_id"**: The bookmark_id is incorrect. Make sure you're using the number from the report URL, not the share token.
- **"Unable to authenticate"**: Check your `.env` file has correct `MIXPANEL_USERNAME` and `MIXPANEL_PASSWORD`.
- **Rate limit errors**: Wait a few minutes between requests (Mixpanel allows 60 queries/hour).

