from dotenv import load_dotenv
load_dotenv()
import requests
import base64
import json
import logging
import os
from typing import Any, Dict, Optional, List
import csv
from datetime import datetime

logging.basicConfig(level=logging.INFO)

class MixpanelAPI:
    """
    Simple Python wrapper for Mixpanel Query API with JQL support, focused on company (Group) analytics.
    """
    BASE_URL = "https://mixpanel.com/api"

    def __init__(self, service_account_username: Optional[str] = None, service_account_password: Optional[str] = None, project_id: Optional[str] = None):
        # Allow credentials from environment variables for security
        self.auth = (
            service_account_username or os.getenv("MIXPANEL_USERNAME"),
            service_account_password or os.getenv("MIXPANEL_PASSWORD")
        )
        self.project_id = project_id or os.getenv("MIXPANEL_PROJECT_ID")

    def run_jql(self, script: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Run a JQL query against Mixpanel.
        :param script: JQL script as a string
        :param params: Optional parameters for the JQL script
        :return: Query result as Python object
        """
        url = f"{self.BASE_URL}/query/jql"
        payload = {'script': script}
        if params:
            payload['params'] = params
        # Add project_id if available
        if self.project_id:
            payload['project_id'] = self.project_id
        print("\n--- Mixpanel JQL Request Debug ---")
        print("URL:", url)
        print("Auth Username:", self.auth[0])
        print("Payload:", json.dumps(payload, indent=2))
        print("-------------------------------\n")
        try:
            response = requests.post(
                url, 
                json=payload,  # Send as JSON, not form data
                auth=self.auth,
                headers={'Content-Type': 'application/json'}
            )
            print("Response status code:", response.status_code)
            print("Response text:", response.text)
            response.raise_for_status()
            logging.info("JQL query executed successfully.")
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Mixpanel JQL query failed: {e}")
            print("Error details:", e)
            raise

    def get_active_companies(self, from_date: str, to_date: str, event: str = "Login") -> List[Dict[str, Any]]:
        """
        Returns a list of companies (company_id) that had the specified event in the given date range.
        """
        script = f'''
        function main() {{
            return Events({{from_date: "{from_date}", to_date: "{to_date}", event_selectors: [{{event: "{event}"}}]}})
                .groupBy(["properties.company_id"], mixpanel.reducer.count());
        }}
        '''
        return self.run_jql(script)

    def get_company_plan_segmentation(self, from_date: str, to_date: str, event: str = "Login") -> List[Dict[str, Any]]:
        """
        Returns a breakdown of companies by plan type for the specified event and date range.
        """
        script = f'''
        function main() {{
            return Events({{from_date: "{from_date}", to_date: "{to_date}", event_selectors: [{{event: "{event}"}}]}})
                .groupBy(["properties.company_id", "properties.Tipo Plan Empresa"], mixpanel.reducer.count());
        }}
        '''
        return self.run_jql(script)

    def get_user_events(self, user_id: str, from_date: str, to_date: str) -> Any:
        """
        Returns all events performed by a specific user (by user_id/email) during a given date range.
        """
        script = f'''
        function main() {{
            return Events({{
                from_date: "{from_date}",
                to_date: "{to_date}"
            }})
            .filter(function(event) {{
                return event.properties["$user_id"] === "{user_id}" ||
                       event.properties["Email"] === "{user_id}" ||
                       event.properties["idUsuario"] === "{user_id}";
            }})
            .groupBy(["name"], mixpanel.reducer.count());
        }}
        '''
        return self.run_jql(script)

    def get_user_companies(self, user_email: str, from_date: str = "2024-01-01", to_date: str = "2025-12-31") -> list:
        """
        Returns a list of company IDs (Group IDs) that the user (by email) belongs to.
        Uses the events-based approach which is more reliable than profile search.
        """
        script = f'''
        function main() {{
            return Events({{
                from_date: "{from_date}",
                to_date: "{to_date}"
            }})
            .filter(function(event) {{
                return (
                    event.properties["$email"] === "{user_email}" ||
                    event.properties["Email"] === "{user_email}" ||
                    event.properties["email"] === "{user_email}" ||
                    event.properties["distinct_id"] === "{user_email}" ||
                    (typeof event.properties["$user_id"] === "string" && 
                     event.properties["$user_id"].toLowerCase() === "{user_email}".toLowerCase()) ||
                    event.properties["idUsuario"] === "{user_email}" ||
                    event.properties["usuario"] === "{user_email}"
                );
            }})
            .map(function(event) {{
                return {{
                    event_name: event.name,
                    company_id: event.properties["idEmpresa"] || 
                             event.properties["company_id"] || 
                             (event.properties["$groups"] ? event.properties["$groups"]["Company"] : null) ||
                             (event.properties["company"] && Array.isArray(event.properties["company"]) ? 
                             event.properties["company"][0] : event.properties["company"]),
                    time: event.time
                }};
            }})
            .filter(function(result) {{
                return result.company_id !== null && result.company_id !== undefined;
            }})
            .groupBy(["company_id"], mixpanel.reducer.count())
            .map(function(result) {{
                return {{
                    company_id: result.key[0],
                    event_count: result.value
                }};
            }});
        }}
        '''
        return self.run_jql(script)

    def export_insight_report(self, bookmark_id: str, workspace_id: Optional[str] = None, output_file: Optional[str] = None, return_raw_json: bool = False) -> Any:
        """
        Export a Mixpanel Insight report to CSV.
        
        Args:
            bookmark_id: The bookmark ID of the saved Insights report
            workspace_id: Workspace ID (defaults to MIXPANEL_WORKSPACE_ID env var or project default)
            output_file: Optional filename to save the CSV to
            return_raw_json: If True, returns the raw JSON instead of CSV file path
            
        Returns:
            Path to the created CSV file, or raw JSON dict if return_raw_json=True
        """
        workspace_id = workspace_id or os.getenv("MIXPANEL_WORKSPACE_ID")
        
        # Use GET method with /api/query/insights endpoint
        url = f"{self.BASE_URL}/query/insights"
        params = {
            'project_id': self.project_id,
            'bookmark_id': bookmark_id
        }
        if workspace_id:
            params['workspace_id'] = workspace_id
        
        try:
            # Use GET request with query parameters
            response = requests.get(
                url,
                params=params,
                auth=self.auth,
                headers={'Content-Type': 'application/json'}
            )
            
            # Log response for debugging
            print(f"Response status: {response.status_code}")
            if response.status_code != 200:
                print(f"Response text: {response.text[:500]}")
            
            response.raise_for_status()
            result = response.json()
            
            # Always save raw JSON to file
            raw_json_file = f"insight_report_{bookmark_id}_raw.json"
            with open(raw_json_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"💾 Raw JSON saved to: {raw_json_file}")
            
            # If user wants raw JSON, return it now
            if return_raw_json:
                return result
            
            # Process the insight data
            if output_file is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = f"mixpanel_insight_{bookmark_id}_{timestamp}.csv"
            
            # Convert result to CSV
            self._write_insight_to_csv(result, output_file)
            
            logging.info(f"Insight report exported to {output_file}")
            return output_file
            
        except requests.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg = f"{error_msg}\nDetails: {json.dumps(error_detail, indent=2)}"
                except:
                    error_msg = f"{error_msg}\nResponse: {e.response.text[:500]}"
            logging.error(f"Failed to export insight report: {error_msg}")
            raise
    
    def _write_insight_to_csv(self, data: Any, output_file: str):
        """
        Helper method to write insight data to CSV.
        Ensures proper comma-separated format for spreadsheet compatibility.
        Limits cell values to 49,000 characters to avoid Google Sheets 50k limit.
        Summarizes complex nested structures to keep column count manageable.
        """
        MAX_CELL_LENGTH = 49000  # Google Sheets limit is 50,000, leave buffer
        MAX_COLUMNS = 500  # Limit columns for spreadsheet compatibility
        
        def truncate_value(value: str) -> str:
            """Truncate string values that exceed cell limit."""
            if isinstance(value, str) and len(value) > MAX_CELL_LENGTH:
                return value[:MAX_CELL_LENGTH] + "... [truncated]"
            return value
        
        def safe_str(value: Any) -> str:
            """Safely convert value to string, handling special characters."""
            if value is None:
                return ''
            str_val = str(value)
            # Replace newlines and carriage returns with spaces
            str_val = str_val.replace('\n', ' ').replace('\r', ' ')
            # Truncate if too long
            return truncate_value(str_val)
        
        def summarize_complex_value(v: Any, max_items: int = 5, max_length: int = 1000) -> str:
            """Summarize complex nested structures as JSON string, with length limits."""
            if isinstance(v, dict):
                # For series data with many date keys, provide summary stats instead
                if len(v) > 20:
                    # Extract key statistics
                    total_keys = len(v)
                    # Try to find overall/total value
                    overall_val = None
                    if '$overall' in v:
                        overall_val = v.get('$overall', {})
                    elif 'all' in v:
                        overall_val = v.get('all')
                    
                    # Create a very concise summary
                    if overall_val:
                        summary = f"Total: {overall_val} | {total_keys} data points"
                    else:
                        # Sample first few keys
                        sample_keys = list(v.keys())[:2]
                        sample = {k: v[k] for k in sample_keys}
                        json_str = json.dumps(sample, ensure_ascii=False)
                        if len(json_str) > max_length - 100:
                            json_str = json_str[:max_length - 100]
                        summary = json_str + f" ... [{total_keys} total keys]"
                    
                    if len(summary) > max_length:
                        return summary[:max_length] + " ... [truncated]"
                    return summary
                elif len(v) > max_items:
                    # For medium dicts, summarize with key count
                    keys = list(v.keys())[:max_items]
                    summary = {k: v[k] for k in keys}
                    json_str = json.dumps(summary, ensure_ascii=False)
                    # Truncate if still too long
                    if len(json_str) > max_length - 50:
                        json_str = json_str[:max_length - 50]
                    return json_str + f" ... [{len(v)} total keys]"
                else:
                    json_str = json.dumps(v, ensure_ascii=False)
                    if len(json_str) > max_length:
                        return json_str[:max_length] + " ... [truncated]"
                    return json_str
            elif isinstance(v, list):
                if len(v) > max_items:
                    json_str = json.dumps(v[:max_items], ensure_ascii=False)
                    if len(json_str) > max_length - 50:
                        json_str = json_str[:max_length - 50]
                    return json_str + f" ... [{len(v)} total items]"
                else:
                    json_str = json.dumps(v, ensure_ascii=False)
                    if len(json_str) > max_length:
                        return json_str[:max_length] + " ... [truncated]"
                    return json_str
            else:
                return safe_str(v)
        
        def flatten_dict(d: Dict, parent_key: str = '', sep: str = '_', max_depth: int = 3, current_depth: int = 0, column_count: list = None) -> Dict:
            """
            Recursively flatten nested dictionary for CSV export.
            Limits depth and column count to prevent excessive columns.
            """
            if column_count is None:
                column_count = [0]
            
            if current_depth >= max_depth or column_count[0] >= MAX_COLUMNS:
                # If too deep or too many columns, summarize as JSON string
                max_len = 500 if 'series' in (parent_key or '').lower() else 1000
                summary = summarize_complex_value(d, max_items=3, max_length=max_len)
                key = parent_key if parent_key else 'nested_data'
                if column_count[0] < MAX_COLUMNS:
                    column_count[0] += 1
                    return {key: safe_str(summary)}
                else:
                    return {}  # Skip if we've hit column limit
            
            items = []
            for k, v in d.items():
                if column_count[0] >= MAX_COLUMNS:
                    break  # Stop adding columns
                
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                # Clean key name (remove special chars that might break CSV)
                new_key = new_key.replace(' ', '_').replace('.', '_').replace('-', '_').replace('$', 'dollar')
                
                if isinstance(v, dict):
                    if len(v) == 0:
                        items.append((new_key, ''))
                        column_count[0] += 1
                    elif current_depth >= max_depth - 1 or column_count[0] + len(v) > MAX_COLUMNS:
                        # Summarize instead of flattening, with stricter length limit for series data
                        max_len = 500 if 'series' in new_key.lower() else 1000
                        items.append((new_key, safe_str(summarize_complex_value(v, max_items=3, max_length=max_len))))
                        column_count[0] += 1
                    else:
                        nested = flatten_dict(v, new_key, sep=sep, max_depth=max_depth, current_depth=current_depth+1, column_count=column_count)
                        items.extend(nested.items())
                elif isinstance(v, list):
                    if len(v) == 0:
                        items.append((new_key, ''))
                        column_count[0] += 1
                    elif len(v) <= 5 and column_count[0] + len(v) <= MAX_COLUMNS:
                        # For small lists, create indexed columns (limit to 5 items)
                        for idx, item in enumerate(v[:5]):
                            if column_count[0] >= MAX_COLUMNS:
                                break
                            list_key = f"{new_key}_{idx}"
                            if isinstance(item, (dict, list)) and current_depth < max_depth - 1:
                                nested = flatten_dict({f"item": item}, list_key, sep=sep, max_depth=max_depth, current_depth=current_depth+1, column_count=column_count)
                                items.extend(nested.items())
                            else:
                                max_len = 500 if 'series' in new_key.lower() else 1000
                                items.append((list_key, safe_str(summarize_complex_value(item, max_items=3, max_length=max_len))))
                                column_count[0] += 1
                    else:
                        # For large lists, summarize with stricter length limit
                        max_len = 500 if 'series' in new_key.lower() else 1000
                        items.append((new_key, safe_str(summarize_complex_value(v, max_items=3, max_length=max_len))))
                        column_count[0] += 1
                else:
                    # Primitive value
                    items.append((new_key, safe_str(v)))
                    column_count[0] += 1
            return dict(items)
        
        with open(output_file, "w", newline="", encoding='utf-8') as csvfile:
            # Handle different data structures
            if isinstance(data, list):
                if len(data) > 0:
                    # Flatten all rows
                    flattened_rows = [flatten_dict(row) for row in data]
                    # Get all unique keys
                    all_keys = set()
                    for row in flattened_rows:
                        all_keys.update(row.keys())
                    fieldnames = sorted(all_keys)
                    
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    for row in flattened_rows:
                        # Convert all values to strings, handle None, and ensure truncation
                        clean_row = {}
                        for k, v in row.items():
                            if v is None:
                                clean_row[k] = ''
                            else:
                                str_value = str(v)
                                # Double-check truncation (safety measure)
                                if len(str_value) > MAX_CELL_LENGTH:
                                    clean_row[k] = truncate_value(str_value)
                                else:
                                    clean_row[k] = str_value
                        writer.writerow(clean_row)
            elif isinstance(data, dict):
                # Flatten dictionary structure
                if 'data' in data:
                    rows = data['data'] if isinstance(data['data'], list) else [data['data']]
                    if rows and len(rows) > 0:
                        # Flatten all rows
                        flattened_rows = [flatten_dict(row) for row in rows]
                        # Get all unique keys
                        all_keys = set()
                        for row in flattened_rows:
                            all_keys.update(row.keys())
                        fieldnames = sorted(all_keys)
                        
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                        writer.writeheader()
                        for row in flattened_rows:
                            # Convert all values to strings, handle None, and ensure truncation
                            clean_row = {}
                            for k, v in row.items():
                                if v is None:
                                    clean_row[k] = ''
                                else:
                                    str_value = str(v)
                                    # Double-check truncation (safety measure)
                                    if len(str_value) > MAX_CELL_LENGTH:
                                        clean_row[k] = truncate_value(str_value)
                                    else:
                                        clean_row[k] = str_value
                            writer.writerow(clean_row)
                else:
                    # Single row - flatten it
                    flattened = flatten_dict(data)
                    fieldnames = sorted(flattened.keys())
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    # Convert all values to strings, handle None, and ensure truncation
                    clean_row = {}
                    for k, v in flattened.items():
                        if v is None:
                            clean_row[k] = ''
                        else:
                            str_value = str(v)
                            # Double-check truncation (safety measure)
                            if len(str_value) > MAX_CELL_LENGTH:
                                clean_row[k] = truncate_value(str_value)
                            else:
                                clean_row[k] = str_value
                    writer.writerow(clean_row)

    def export_user_companies_to_csv(self, user_email: str, output_file: Optional[str] = None, from_date: str = "2024-01-01", to_date: str = "2025-12-31") -> str:
        """
        Exports all companies a user belongs to into a CSV file
        
        Args:
            user_email: Email of the user to find companies for
            output_file: Optional filename to save the CSV to
            from_date: Start date for events search in YYYY-MM-DD format
            to_date: End date for events search in YYYY-MM-DD format
            
        Returns:
            Path to the created CSV file
        """
        companies = self.get_user_companies(user_email, from_date, to_date)
        
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"companies_{user_email.replace('@', '_at_')}_{timestamp}.csv"
        
        with open(output_file, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["company_id", "event_count"])
            
            for company in companies:
                writer.writerow([company["company_id"], company["event_count"]])
        
        print(f"Exported {len(companies)} companies for {user_email} to {output_file}")
        return output_file

# Example/test usage
if __name__ == "__main__":
    # Credentials can be set via environment variables
    username = os.getenv("MIXPANEL_USERNAME")
    password = os.getenv("MIXPANEL_PASSWORD")
    project_id = os.getenv("MIXPANEL_PROJECT_ID")
    
    print("MIXPANEL_USERNAME:", username)
    print("MIXPANEL_PASSWORD:", "***" if password else None)
    print("MIXPANEL_PROJECT_ID:", project_id)
    
    mixpanel = MixpanelAPI(username, password, project_id)
    
    print("\n--- Testing User-Company Associations ---")
    user_email = "jonetto@colppy.com"
    user_companies = mixpanel.get_user_companies(user_email)
    print(f"Companies for user {user_email}:")
    if user_companies:
        for company in user_companies:
            print(f"  Company ID: {company['company_id']}, Event Count: {company['event_count']}")
        
        # Export to CSV
        csv_file = mixpanel.export_user_companies_to_csv(user_email)
        print(f"Exported to {csv_file}")
    else:
        print("  No companies found for this user")
    
    # Uncomment to test other methods
    # print("\n--- Testing Active Companies ---")
    # active_companies = mixpanel.get_active_companies("2025-01-01", "2025-05-01")
    # print(f"Found {len(active_companies)} active companies")
    # for i, company in enumerate(active_companies[:5]):
    #     print(f"  {i+1}. Company ID: {company['key'][0]}, Login Count: {company['value']}")
    # if len(active_companies) > 5:
    #     print(f"  ... and {len(active_companies) - 5} more")
    # 
    # print("\n--- Testing Company Plan Segmentation ---")
    # plan_data = mixpanel.get_company_plan_segmentation()
    # if plan_data:
    #     for segment in plan_data:
    #         print(f"  Plan: {segment['key'][0]}, Count: {segment['value']}")
    # else:
    #     print("  No plan segmentation data available")
    # 
    # print("\n--- Testing User Events ---")
    # user_events = mixpanel.get_user_events(user_email, "2025-01-01", "2025-05-31")
    # if user_events:
    #     print(f"Found {len(user_events)} event types for user {user_email}")
    #     for event in user_events:
    #         print(f"  Event: {event['key'][0]}, Count: {event['value']}")
    # else:
    #     print(f"  No events found for user {user_email}")

# Example usage (to be removed or moved to tests):
# mixpanel = MixpanelAPI('username', 'password')
# script = '''function main() { return Events({from_date: "2025-05-01", to_date: "2025-05-31"}).groupBy(["properties.company_id"], mixpanel.reducer.count()); }'''
# result = mixpanel.run_jql(script)
# print(result) 