import os
import sys
import json
import csv
from datetime import datetime
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from mixpanel_api import MixpanelAPI

# Accept company_id, from_date, to_date as arguments
if len(sys.argv) < 2:
    print("Usage: python get_company_stats_simple.py <company_id> [from_date] [to_date]")
    sys.exit(1)

company_id = sys.argv[1]
from_date = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
to_date = sys.argv[3] if len(sys.argv) > 3 else "2025-12-31"

OUTPUT_DIR = os.path.join("mixpanel_reports", "company_events")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_company_events(mixpanel: MixpanelAPI, company_id: str, 
                     from_date: str = "2024-01-01", 
                     to_date: str = "2025-12-31") -> List[Dict[str, Any]]:
    """
    Get simple event counts for a company
    
    Args:
        mixpanel: Initialized MixpanelAPI instance
        company_id: Company ID to analyze
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        
    Returns:
        List of event dictionaries
    """
    script = f'''
    function main() {{
        // Get events for this company
        return Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
        }})
        .filter(function(event) {{
            return (
                (event.properties["$groups"] && 
                 event.properties["$groups"]["Company"] === "{company_id}") ||
                event.properties["idEmpresa"] === "{company_id}" ||
                event.properties["company_id"] === "{company_id}" ||
                (event.properties["company"] && 
                 (event.properties["company"] === "{company_id}" || 
                  (Array.isArray(event.properties["company"]) && 
                   event.properties["company"].indexOf("{company_id}") >= 0)))
            );
        }})
        .groupBy(["name"], mixpanel.reducer.count())
        .map(function(result) {{
            return {{
                event_name: result.key[0],
                count: result.value
            }};
        }});
    }}
    '''
    events = mixpanel.run_jql(script)
    if isinstance(events, dict):
        events = [events]
    return events

def export_to_csv(events: List[Dict[str, Any]], company_id: str, from_date: str, to_date: str) -> str:
    """
    Export company events to CSV in mixpanel_reports/company_events
    
    Args:
        events: List of event dictionaries
        company_id: Company ID
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        
    Returns:
        Path to the created CSV file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"company_{company_id}_events_{from_date}_to_{to_date}_{timestamp}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Calculate total events
    total_events = sum(event["count"] for event in events)
    
    with open(filepath, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["event_name", "count", "percentage"])
        
        # Sort by count (descending)
        sorted_events = sorted(events, key=lambda x: x["count"], reverse=True)
        
        for event in sorted_events:
            percentage = (event["count"] / total_events * 100) if total_events > 0 else 0
            writer.writerow([
                event["event_name"], 
                event["count"], 
                f"{percentage:.2f}%"
            ])
        
        # Add total row
        writer.writerow(["TOTAL", total_events, "100.00%"])
    
    print(f"Exported {len(events)} event types to {filepath}")
    return filepath

if __name__ == "__main__":
    print(f"Analyzing events for company {company_id} from {from_date} to {to_date}")
    
    # Credentials from environment variables
    username = os.getenv("MIXPANEL_USERNAME")
    password = os.getenv("MIXPANEL_PASSWORD")
    project_id = os.getenv("MIXPANEL_PROJECT_ID")
    
    print("MIXPANEL_USERNAME:", username)
    print("MIXPANEL_PASSWORD:", "***" if password else None)
    print("MIXPANEL_PROJECT_ID:", project_id)
    
    mixpanel = MixpanelAPI(username, password, project_id)
    
    try:
        print(f"\nFetching company events... (this may take a minute)")
        events = get_company_events(mixpanel, company_id, from_date, to_date)
        
        if not events:
            print(f"No events found for company {company_id}")
            sys.exit(0)
        
        total_events = sum(event["count"] for event in events)
        unique_event_types = len(events)
        
        print(f"\nCompany: {company_id}")
        print(f"Total events: {total_events}")
        print(f"Unique event types: {unique_event_types}")
        
        # Show top 5 events
        sorted_events = sorted(events, key=lambda x: x["count"], reverse=True)
        print("\nTop events:")
        for i, event in enumerate(sorted_events[:5]):
            percentage = (event["count"] / total_events * 100) if total_events > 0 else 0
            print(f"  {i+1}. {event['event_name']}: {event['count']} ({percentage:.2f}%)")
        
        # Export to CSV
        export_to_csv(events, company_id, from_date, to_date)
        
    except Exception as e:
        print(f"Error analyzing company events: {e}")
        sys.exit(1) 