# Mixpanel API Python Wrapper

## Overview
This project provides a simple, extensible Python wrapper for the Mixpanel Query API, with a focus on company (Group) analytics for Colppy.com. It enables you to run JQL queries, segment events by company, and analyze user and company activity for Product-Led Growth (PLG) initiatives.

## Key Findings

- **People Profiles vs Events**: We discovered that in Colppy's Mixpanel implementation, user-company associations are stored in event properties rather than in user profiles. The People() JQL queries returned empty results, while Events() queries with proper filtering worked.

- **Company Identifiers**: Companies can be identified through multiple event properties:
  - `company_id`
  - `idEmpresa`
  - `$groups.Company`
  - `company` (as string or array)

- **User Identifiers**: Users can be identified through multiple properties:
  - `$user_id`
  - `Email` or `$email` or `email`
  - `idUsuario`
  - `usuario`

- **Rate Limiting**: Mixpanel imposes strict rate limits (60 queries per hour). Complex JQL queries or chained transformations may hit these limits quickly.

## Features
- Authenticate securely using a Mixpanel service account
- Run custom JQL queries
- Export Insight Reports to CSV
- Helper methods for:
  - Active companies in a date range
  - Company plan segmentation
  - User-level event history
- Extensible for additional Mixpanel analytics needs

## Environment Setup
Create a `.env` file in your project root with the following variables:
```
MIXPANEL_USERNAME=your_service_account_username
MIXPANEL_PASSWORD=your_service_account_password
MIXPANEL_PROJECT_ID=your_project_id
```
**Note:** Never commit your `.env` file to version control.

## Installation
1. Clone the repository.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Ensure your `.env` file is present and filled out as above.

## CSV Export Format

All CSV exports use **comma (`,`) as the field separator** and are formatted for direct import into spreadsheets:
- ✅ Compatible with Google Sheets, Excel, and other spreadsheet applications
- ✅ Properly escaped fields containing commas or quotes
- ✅ Nested JSON structures are flattened with underscore separators (e.g., `meta_min_sampling_factor`)
- ✅ Lists are converted to JSON strings for preservation

## Usage Examples

### Find Companies for a User

This is the successful JQL query pattern to find companies associated with a user:

```javascript
function main() {
  return Events({
    from_date: "2024-01-01",
    to_date: "2025-12-31"
  })
  .filter(function(event) {
    return (
      event.properties["$email"] === "user@example.com" ||
      event.properties["Email"] === "user@example.com" ||
      event.properties["email"] === "user@example.com" ||
      event.properties["distinct_id"] === "user@example.com" ||
      (typeof event.properties["$user_id"] === "string" && 
       event.properties["$user_id"].toLowerCase() === "user@example.com".toLowerCase())
    );
  })
  .map(function(event) {
    return {
      event_name: event.name,
      company: event.properties["idEmpresa"] || 
               event.properties["company_id"] || 
               (event.properties["$groups"] ? event.properties["$groups"]["Company"] : null),
      time: event.time,
      properties: event.properties
    };
  })
  .filter(function(result) {
    return result.company !== null && result.company !== undefined;
  });
}
```

### Get Company Statistics

For analyzing events for a specific company:

```javascript
function main() {
  return Events({
    from_date: "2024-01-01", 
    to_date: "2025-12-31"
  })
  .filter(function(event) {
    return (
      (event.properties["$groups"] && 
       event.properties["$groups"]["Company"] === "COMPANY_ID") ||
      event.properties["idEmpresa"] === "COMPANY_ID" ||
      event.properties["company_id"] === "COMPANY_ID" ||
      (event.properties["company"] && 
       (event.properties["company"] === "COMPANY_ID" || 
        (Array.isArray(event.properties["company"]) && 
         event.properties["company"].indexOf("COMPANY_ID") >= 0)))
    );
  })
  .groupBy(["name"], mixpanel.reducer.count())
  .map(function(result) {
    return {
      event_name: result.key[0],
      count: result.value
    };
  });
}
```

## Additional JQL Query Examples

### Find User Profile by Email

```javascript
function main() {
  return People()
    .filter(function(user) {
      return (
        (user["$email"] && user["$email"].toLowerCase() === "jonetto@colppy.com".toLowerCase()) ||
        (user["Email"] && user["Email"].toLowerCase() === "jonetto@colppy.com".toLowerCase()) ||
        (user["email"] && user["email"].toLowerCase() === "jonetto@colppy.com".toLowerCase()) ||
        (user["$distinct_id"] && user["$distinct_id"].toLowerCase() === "jonetto@colppy.com".toLowerCase())
      );
    });
}
```

### Find Companies by User Events

```javascript
function main() {
  return Events({
    from_date: "2024-01-01",
    to_date: "2025-12-31"
  })
  .filter(function(event) {
    return (
      event.properties["$email"] === "jonetto@colppy.com" ||
      event.properties["Email"] === "jonetto@colppy.com" ||
      event.properties["email"] === "jonetto@colppy.com" ||
      event.properties["distinct_id"] === "jonetto@colppy.com" ||
      (typeof event.properties["$user_id"] === "string" && 
       event.properties["$user_id"].toLowerCase() === "jonetto@colppy.com".toLowerCase())
    );
  })
  .map(function(event) {
    return {
      event: event.name,
      company: event.properties["idEmpresa"] || 
               event.properties["company_id"] || 
               (event.properties["$groups"] ? event.properties["$groups"]["Company"] : null),
      time: event.time,
      properties: event.properties
    };
  })
  .filter(function(result) {
    return result.company !== null && result.company !== undefined;
  });
}
```

### Lookup User's Distinct ID First

```javascript
function main() {
  // First, get the distinct_id for this user
  var users = People()
    .filter(function(user) {
      return (
        (user["$email"] && user["$email"].toLowerCase() === "jonetto@colppy.com".toLowerCase()) ||
        (user["Email"] && user["Email"].toLowerCase() === "jonetto@colppy.com".toLowerCase()) ||
        (user["email"] && user["email"].toLowerCase() === "jonetto@colppy.com".toLowerCase())
      );
    })
    .map(function(user) {
      return user["$distinct_id"];
    });

  // If no distinct_id found, try to find events by other identifiers
  if (!users || users.length === 0) {
    return Events({
      from_date: "2024-01-01",
      to_date: "2025-12-31"
    })
    .filter(function(event) {
      return (
        event.properties["$email"] === "jonetto@colppy.com" ||
        event.properties["Email"] === "jonetto@colppy.com" ||
        event.properties["email"] === "jonetto@colppy.com"
      );
    })
    .map(function(event) {
      return {
        distinct_id: event.distinct_id,
        event: event.name,
        company: event.properties["idEmpresa"] || 
                 event.properties["company_id"] || 
                 (event.properties["$groups"] ? event.properties["$groups"]["Company"] : null)
      };
    });
  }
  
  // Use the distinct_id to find company associations
  var distinct_id = users[0];
  
  return Events({
    from_date: "2024-01-01",
    to_date: "2025-12-31"
  })
  .filter(function(event) {
    return event.distinct_id === distinct_id;
  })
  .map(function(event) {
    return {
      distinct_id: event.distinct_id,
      event: event.name,
      company: event.properties["idEmpresa"] || 
               event.properties["company_id"] || 
               (event.properties["$groups"] ? event.properties["$groups"]["Company"] : null),
      properties: event.properties
    };
  });
}
```

### Search by Event Property "idUsuario"

```javascript
function main() {
  return Events({
    from_date: "2024-01-01",
    to_date: "2025-12-31"
  })
  .filter(function(event) {
    // Try to match on multiple potential user identifiers
    return (
      event.properties["idUsuario"] === "jonetto@colppy.com" ||
      event.properties["idUsuario"] === "jonetto" ||
      event.properties["usuario"] === "jonetto@colppy.com" ||
      event.properties["usuario"] === "jonetto"
    );
  })
  .map(function(event) {
    return {
      event: event.name,
      company: event.properties["idEmpresa"] || 
               event.properties["company_id"] || 
               (event.properties["$groups"] ? event.properties["$groups"]["Company"] : null),
      time: event.time,
      user_id: event.properties["idUsuario"] || event.properties["usuario"],
      properties: event.properties
    };
  })
  .filter(function(result) {
    return result.company !== null && result.company !== undefined;
  });
}
```

### Check for User as Company Owner

```javascript
function main() {
  return GroupsOverview("Company")
    .filter(function(group) {
      // Check owner/admin properties that might contain the user email
      return (
        (group.properties["owner_email"] && 
         group.properties["owner_email"].toLowerCase() === "jonetto@colppy.com".toLowerCase()) ||
        (group.properties["admin_email"] && 
         group.properties["admin_email"].toLowerCase() === "jonetto@colppy.com".toLowerCase()) ||
        (group.properties["contact_email"] && 
         group.properties["contact_email"].toLowerCase() === "jonetto@colppy.com".toLowerCase())
      );
    })
    .map(function(group) {
      return {
        company_id: group.key,
        company_name: group.properties["name"] || group.key,
        properties: group.properties
      };
    });
}
```

### Find Events by idEmpresa First

```javascript
function main() {
  // Get all unique company IDs
  var companies = Events({
    from_date: "2024-01-01",
    to_date: "2025-12-31"
  })
  .map(function(event) {
    return event.properties["idEmpresa"];
  })
  .filter(function(id) {
    return id !== null && id !== undefined;
  })
  .unique();
  
  // Results object to collect companies with the user
  var results = [];
  
  // For each company, check if the user has events for it
  companies.forEach(function(companyId) {
    var userEvents = Events({
      from_date: "2024-01-01",
      to_date: "2025-12-31"
    })
    .filter(function(event) {
      return (
        event.properties["idEmpresa"] === companyId &&
        (
          event.properties["$email"] === "jonetto@colppy.com" ||
          event.properties["Email"] === "jonetto@colppy.com" ||
          event.properties["email"] === "jonetto@colppy.com" ||
          event.properties["idUsuario"] === "jonetto@colppy.com" ||
          event.properties["idUsuario"] === "jonetto" ||
          event.properties["usuario"] === "jonetto@colppy.com" ||
          event.properties["usuario"] === "jonetto"
        )
      );
    })
    .count();
    
    if (userEvents > 0) {
      results.push({
        company_id: companyId,
        event_count: userEvents
      });
    }
  });
  
  return results;
}
```

## API Reference

### MixpanelAPI

The main class for interacting with Mixpanel's API.

```python
mixpanel = MixpanelAPI(
    service_account_username=None,  # If None, read from MIXPANEL_USERNAME env var
    service_account_password=None,  # If None, read from MIXPANEL_PASSWORD env var
    project_id=None                # If None, read from MIXPANEL_PROJECT_ID env var
)
```

### Methods

- **run_jql(script, params=None)**: Run a raw JQL query against Mixpanel
- **export_insight_report(bookmark_id, workspace_id, output_file)**: Export a Mixpanel Insight report to CSV
- **get_user_companies(user_email, from_date, to_date)**: Get all companies a user belongs to
- **get_active_companies(from_date, to_date)**: Get list of active companies in date range
- **get_company_plan_segmentation(from_date, to_date)**: Get company distribution by plan type
- **get_user_events(user_id, from_date, to_date)**: Get events performed by a specific user
- **export_user_companies_to_csv(user_email, output_file)**: Export user's companies to CSV

## JQL Tips

1. **Watch out for chaining transformations**:
   - Certain transformations can't be chained (e.g., `.sort()` on a groupBy result)
   - Break complex queries into separate, simpler queries

2. **Property access patterns**:
   - Use direct property access with fallbacks when properties might be missing:
     ```javascript
     event.properties["idEmpresa"] || event.properties["company_id"] || null
     ```
   - For nested properties, always check parent existence:
     ```javascript
     (event.properties["$groups"] ? event.properties["$groups"]["Company"] : null)
     ```

3. **Handling arrays**:
   - Check if a property is an array before using array methods:
     ```javascript
     (Array.isArray(event.properties["company"]) && 
      event.properties["company"].indexOf("COMPANY_ID") >= 0)
     ```

## Limitations

1. **Rate Limiting**: Mixpanel restricts to 60 queries per hour per project
2. **Query Complexity**: Complex queries may fail with cryptic errors
3. **Data Quality**: Property inconsistencies mean you should check multiple possible locations for the same data
4. **GroupsOverview**: This function is not supported in Colppy's Mixpanel plan
5. **Internal Events**: Any event whose name starts with a `$` (e.g., `$identify`, `$mp_click`) is an internal Mixpanel event and should **not** be considered as valid user activity for analytics or reporting purposes.

## Troubleshooting

- **"Unable to authenticate request"**: Check that your credentials are correct
- **"Query rate limit exceeded"**: Wait before making further requests
- **"Uncaught exception"**: Check your JQL syntax, especially for invalid property access or chaining operations
- **"is not a function"**: Certain operations can't be chained together. Try breaking into separate queries.

## Exporting Insight Reports

Mixpanel Insight Reports can be exported directly to CSV format using the API.

### Getting the Bookmark ID

Share links (e.g., `https://mixpanel.com/s/hmnpw`) contain a **share token**, not a bookmark_id. To get the actual bookmark_id:

1. **Open the report in Mixpanel** using the share link
2. **Look at the URL** in your browser after logging in - it will look like:
   ```
   https://mixpanel.com/project/2201475/view/142035/app/boards#id=12345&editor-card-id="report-123456"
   ```
3. **Extract the bookmark_id** - it's the number after `report-` (e.g., `123456`)

### Exporting via Command Line

Use the `download_insight.py` script:

```bash
cd /Users/virulana/openai-cookbook/tools/scripts/mixpanel

# Export by bookmark ID
python download_insight.py --bookmark-id 123456

# Export with custom output file
python download_insight.py --bookmark-id 123456 --output my_report.csv

# With workspace ID (if needed)
python download_insight.py --bookmark-id 123456 --workspace-id 142035 --output report.csv
```

### Exporting via Python API

```python
from mixpanel_api import MixpanelAPI

mixpanel = MixpanelAPI()

# Export insight report to CSV
output_file = mixpanel.export_insight_report(
    bookmark_id="123456",
    workspace_id=None,  # Optional, defaults to env var or project default
    output_file="insight_report.csv"  # Optional, auto-generated if not provided
)

print(f"Report exported to: {output_file}")
```

### CSV Output Format

The exported CSV files use **comma (`,`) as the field separator** and are formatted for direct import into spreadsheets (Google Sheets, Excel, etc.). Nested JSON structures are flattened with underscore separators (e.g., `meta_min_sampling_factor`).

**Note:** The Insight Reports API uses **GET method** with query parameters, which helps avoid rate limit issues compared to POST requests.

## Running the Example Script
You can run the provided example/test script:
```
python src/mixpanel_api.py
```

## Best Practices
- Store credentials in `.env` and keep them secure.
- Use service accounts for API access, not personal credentials.
- **Exclude internal events**: Always filter out events whose name starts with `$` when analyzing user activity or generating reports.
- **Use GET method for Insight Reports**: The `download_insight.py` script uses GET requests which are more reliable and avoid rate limit issues.
- **CSV Format**: All CSV exports use comma separators and are ready for direct import into spreadsheets.
- Review Mixpanel's [Query API documentation](https://developer.mixpanel.com/reference/query-api) and [JQL reference](https://developer.mixpanel.com/reference/query-jql) for advanced queries.
- Extend the wrapper with new helper methods as your analytics needs grow.
- For production, consider adding more robust error handling and logging.

## References
- [Mixpanel Query API Docs](https://developer.mixpanel.com/reference/query-api)
- [Mixpanel JQL Reference](https://developer.mixpanel.com/reference/query-jql)
- [Colppy Product Insights Framework] (internal)

## Data Model and Integration Notes

- **ID Empresa (Company ID)**: This is the unique identifier for companies in Mixpanel and is used as the join key to match company data with HubSpot deals. Always use this field for cross-platform analytics and reporting.

---
For questions or improvements, contact the Colppy Product/Analytics team. 