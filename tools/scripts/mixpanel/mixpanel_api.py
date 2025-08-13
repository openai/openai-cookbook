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
        data = {'script': script}
        if params:
            data['params'] = json.dumps(params)
        # Add project_id if available
        if self.project_id:
            data['project_id'] = self.project_id
        print("\n--- Mixpanel JQL Request Debug ---")
        print("URL:", url)
        print("Auth Username:", self.auth[0])
        print("Payload:", json.dumps(data, indent=2))
        print("-------------------------------\n")
        try:
            response = requests.post(url, data=data, auth=self.auth)
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