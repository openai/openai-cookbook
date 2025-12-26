# Mixpanel Insight Report - Raw JSON Structure

This document describes the raw, unprocessed JSON structure returned by the Mixpanel Insight Report API endpoint.

## API Endpoint

```
GET https://mixpanel.com/api/query/insights?project_id={project_id}&bookmark_id={bookmark_id}
```

## Response Structure

The raw JSON response from Mixpanel Insight reports typically has the following structure:

```json
{
  "computed_at": "2025-12-08T22:48:12.977017+00:00",
  "date_range": {
    "from_date": "2020-06-17T00:00:00-03:00",
    "to_date": "2025-12-08T19:48:12.587528-03:00"
  },
  "headers": [
    "$metric",
    "$time",
    "email"
  ],
  "meta": {
    "is_segmentation_limit_hit": false,
    "min_sampling_factor": 1.0,
    "report_sections": {
      "group": [
        {
          "bookmark": {
            "dataset": "$mixpanel",
            "value": "$time",
            "resourceType": "events",
            "search": "",
            "propertyType": "datetime"
          }
        },
        {
          "bookmark": {
            "dataset": "$mixpanel",
            "value": "email",
            "resourceType": "events",
            "search": "",
            "propertyType": "string"
          }
        }
      ],
      "show": [
        {
          "metric_key": "Uniques of Invitó usuario"
        }
      ]
    },
    "sub_query_count": 1
  },
  "series": {
    "Uniques of Invitó usuario": {
      "$overall": {
        "all": 1121
      },
      "2021-07-20T15:29:31": {
        "$overall": {
          "all": 1
        },
        "MartinaLizarribar@gmail.com": {
          "all": 1
        }
      },
      "2024-05-07T13:57:58": {
        "$overall": {
          "all": 1
        },
        "hernanb@estudio-torres.com": {
          "all": 1
        }
      }
      // ... many more date keys with nested email breakdowns
    }
  }
}
```

## Key Fields

### Top-Level Fields

- **`computed_at`**: ISO 8601 timestamp when the report was computed
- **`date_range`**: Object with `from_date` and `to_date` ISO 8601 timestamps
- **`headers`**: Array of dimension names used in the report
- **`meta`**: Metadata about the report configuration
- **`series`**: The actual data series, organized by metric name

### `meta` Object

- **`is_segmentation_limit_hit`**: Boolean indicating if segmentation limits were reached
- **`min_sampling_factor`**: Sampling factor used (1.0 = no sampling)
- **`report_sections`**: Configuration of how the report is structured
  - **`group`**: Array of grouping dimensions (properties used to group data)
  - **`show`**: Array of metrics being displayed
- **`sub_query_count`**: Number of sub-queries executed

### `series` Object

The `series` object contains the actual data, organized hierarchically:

- **Top level**: Metric names (e.g., "Uniques of Invitó usuario")
- **Second level**: Time periods or grouping values (dates, property values)
- **Third level**: Breakdown values (e.g., email addresses, user properties)
- **Leaf level**: Count values (usually `{"all": <number>}`)

### Example Series Structure

For a report grouped by `$time` and `email`, showing "Uniques of Invitó usuario":

```
series["Uniques of Invitó usuario"][date_string][email_string]["all"] = count
```

## Viewing Raw Output

To view the raw, unprocessed JSON output:

1. **Using the script**:
   ```bash
   python show_raw_insight.py <bookmark_id>
   ```
   This will display the JSON and save it to `insight_report_{bookmark_id}_raw.json`

2. **Using the API wrapper with environment variable**:
   ```bash
   export MIXPANEL_SAVE_RAW_JSON=true
   python download_insight.py --bookmark-id <bookmark_id>
   ```
   This will save the raw JSON alongside the CSV file.

3. **Direct API call**:
   ```bash
   curl -u "$MIXPANEL_USERNAME:$MIXPANEL_PASSWORD" \
     "https://mixpanel.com/api/query/insights?project_id=$MIXPANEL_PROJECT_ID&bookmark_id=<bookmark_id>" \
     | jq '.' > raw_output.json
   ```

## Notes

- The `series` data can be **very large** for reports with many time periods and breakdowns
- Date keys in series are ISO 8601 timestamps
- The structure is deeply nested, which is why CSV export flattens it
- Some reports may have additional fields depending on report type (funnel, retention, etc.)






