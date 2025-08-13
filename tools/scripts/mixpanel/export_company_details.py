import os
import sys
import csv
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from mixpanel_api import MixpanelAPI

def get_company_details(mixpanel, company_id, from_date="2024-01-01", to_date="2025-12-31"):
    """
    Get detailed information about a company, including:
    - Company properties
    - Events count by type
    - User count
    """
    script = f'''
    function main() {{
        var company_details = {{
            company_id: "{company_id}",
            properties: null,
            event_counts: null,
            users: null
        }};
        
        // Get company properties
        var company_props = GroupsOverview("Company")
            .filter(function(group) {{
                return group.key === "{company_id}";
            }})
            .map(function(group) {{
                return group.properties || {{}};
            }});
            
        if (company_props && company_props.length > 0) {{
            company_details.properties = company_props[0];
        }}
        
        // Get events count by type
        company_details.event_counts = Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
        }})
        .filter(function(event) {{
            return (
                (event.properties["$groups"] && 
                 event.properties["$groups"]["Company"] === "{company_id}") ||
                event.properties["idEmpresa"] === "{company_id}" ||
                event.properties["company_id"] === "{company_id}"
            );
        }})
        .groupBy(["name"], mixpanel.reducer.count());
        
        // Get users who performed events for this company
        company_details.users = Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
        }})
        .filter(function(event) {{
            return (
                (event.properties["$groups"] && 
                 event.properties["$groups"]["Company"] === "{company_id}") ||
                event.properties["idEmpresa"] === "{company_id}" ||
                event.properties["company_id"] === "{company_id}"
            );
        }})
        .groupByUser([
            "$email", 
            "Email",
            "email",
            "idUsuario",
            "usuario"
        ], mixpanel.reducer.any());
        
        return company_details;
    }}
    '''
    return mixpanel.run_jql(script)

def export_company_details_to_csv(company_details, output_dir="company_exports"):
    """Export company details to CSV files"""
    if not company_details:
        print("No company details found")
        return
    
    company_id = company_details.get("company_id", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Base filename for all exports
    base_filename = f"{output_dir}/{company_id}_{timestamp}"
    
    # Export company properties
    if company_details.get("properties"):
        with open(f"{base_filename}_properties.json", "w") as f:
            json.dump(company_details["properties"], f, indent=2)
            print(f"Company properties exported to {base_filename}_properties.json")
    
    # Export event counts
    if company_details.get("event_counts"):
        with open(f"{base_filename}_events.csv", "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["event_name", "count"])
            for event in company_details["event_counts"]:
                writer.writerow([event["key"][0], event["value"]])
            print(f"Company events exported to {base_filename}_events.csv")
    
    # Export users
    if company_details.get("users"):
        with open(f"{base_filename}_users.csv", "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            
            # Get all possible user identifier fields
            fields = set()
            for user in company_details["users"]:
                for field in user["key"]:
                    if field is not None:
                        fields.add(field)
            
            # Write header row
            writer.writerow(list(fields))
            
            # Write user data
            for user in company_details["users"]:
                row = []
                for field in fields:
                    idx = user["key"].index(field) if field in user["key"] else -1
                    value = user["key"][idx] if idx >= 0 else ""
                    row.append(value)
                writer.writerow(row)
            
            print(f"Company users exported to {base_filename}_users.csv")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python export_company_details.py <company_id> [from_date] [to_date]")
        sys.exit(1)
    
    company_id = sys.argv[1]
    from_date = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    to_date = sys.argv[3] if len(sys.argv) > 3 else "2025-12-31"
    
    print(f"Exporting details for company {company_id} from {from_date} to {to_date}")
    
    mixpanel = MixpanelAPI()
    company_details = get_company_details(mixpanel, company_id, from_date, to_date)
    
    export_company_details_to_csv(company_details) 