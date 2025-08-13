import os
import sys
import json
import csv
from datetime import datetime
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from mixpanel_api import MixpanelAPI

def get_company_statistics(mixpanel: MixpanelAPI, company_id: str, 
                          from_date: str = "2024-01-01", 
                          to_date: str = "2025-12-31") -> Dict[str, Any]:
    """
    Get comprehensive statistics about company activities in Mixpanel
    
    Args:
        mixpanel: Initialized MixpanelAPI instance
        company_id: Company ID to analyze
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        
    Returns:
        Dictionary with statistics
    """
    # First, get event counts and user data - simpler query
    event_counts_script = f'''
    function main() {{
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
    
    # Get users script
    users_script = f'''
    function main() {{
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
        .groupBy([
            function(event) {{
                return event.properties["$user_id"] || 
                       event.properties["Email"] || 
                       event.properties["email"] || 
                       event.properties["idUsuario"] || 
                       event.properties["usuario"] || 
                       "unknown";
            }}
        ], mixpanel.reducer.count())
        .map(function(user) {{
            return {{
                user_id: user.key[0],
                event_count: user.value
            }};
        }});
    }}
    '''
    
    # Events by day script
    events_by_day_script = f'''
    function main() {{
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
        .groupBy([
            function(event) {{
                var date = new Date(event.time);
                return date.toISOString().split('T')[0];
            }}
        ], mixpanel.reducer.count())
        .map(function(result) {{
            return {{
                date: result.key[0],
                event_count: result.value
            }};
        }});
    }}
    '''
    
    # User activities script
    user_activities_script = f'''
    function main() {{
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
        .groupBy([
            function(event) {{
                return event.properties["$user_id"] || 
                       event.properties["Email"] || 
                       event.properties["email"] || 
                       event.properties["idUsuario"] || 
                       event.properties["usuario"] || 
                       "unknown";
            }},
            "name"
        ], mixpanel.reducer.count())
        .map(function(result) {{
            return {{
                user: result.key[0],
                event_name: result.key[1],
                count: result.value
            }};
        }});
    }}
    '''
    
    # Execute each query separately
    print("Fetching event counts...")
    event_counts = mixpanel.run_jql(event_counts_script)
    
    print("Fetching user data...")
    users = mixpanel.run_jql(users_script)
    
    print("Fetching daily events...")
    events_by_day = mixpanel.run_jql(events_by_day_script)
    
    print("Fetching user activities...")
    top_user_activities = mixpanel.run_jql(user_activities_script)
    
    # Calculate total events
    total_events = sum(item.get('count', 0) for item in event_counts) if event_counts else 0
    
    # Get user count
    user_count = len(users) if users else 0
    
    # Sort top user activities in Python and get top 20
    if top_user_activities:
        top_user_activities = sorted(
            top_user_activities, 
            key=lambda x: x.get('count', 0),
            reverse=True
        )[:20]  # Get top 20
    
    # Compile all results
    result = {
        "company_id": company_id,
        "total_events": total_events,
        "event_counts": event_counts,
        "user_count": user_count,
        "users": users,
        "events_by_day": events_by_day,
        "top_user_activities": top_user_activities
    }
    
    return result

def export_company_stats(stats: Dict[str, Any], output_dir: Optional[str] = None) -> Dict[str, str]:
    """
    Export company statistics to CSV and JSON files
    
    Args:
        stats: Statistics dictionary returned by get_company_statistics
        output_dir: Directory to save output files
        
    Returns:
        Dictionary with paths to created files
    """
    company_id = stats.get("company_id", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create output directory if specified and doesn't exist
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = "."
    
    # Base filename for all exports
    base_filename = f"{output_dir}/company_{company_id}_{timestamp}"
    
    output_files = {}
    
    # Save event counts to CSV
    if stats.get("event_counts"):
        events_file = f"{base_filename}_events.csv"
        with open(events_file, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["event_name", "count"])
            for event in stats["event_counts"]:
                writer.writerow([event["event_name"], event["count"]])
            print(f"Event counts exported to {events_file}")
        output_files["events"] = events_file
    
    # Save users to CSV
    if stats.get("users"):
        users_file = f"{base_filename}_users.csv"
        with open(users_file, "w", newline="") as csvfile:
            # Get all possible fields
            fields = set()
            for user in stats["users"]:
                for field in user:
                    fields.add(field)
            
            writer = csv.writer(csvfile)
            writer.writerow(list(fields))
            
            for user in stats["users"]:
                row = []
                for field in fields:
                    row.append(user.get(field, ""))
                writer.writerow(row)
            
            print(f"Users exported to {users_file}")
        output_files["users"] = users_file
    
    # Save events by day to CSV
    if stats.get("events_by_day"):
        timeline_file = f"{base_filename}_timeline.csv"
        with open(timeline_file, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["date", "event_count"])
            
            # Sort by date
            sorted_days = sorted(stats["events_by_day"], key=lambda x: x["date"])
            
            for day in sorted_days:
                writer.writerow([day["date"], day["event_count"]])
            
            print(f"Daily event counts exported to {timeline_file}")
        output_files["timeline"] = timeline_file
    
    # Save top user activities to CSV
    if stats.get("top_user_activities"):
        activities_file = f"{base_filename}_top_activities.csv"
        with open(activities_file, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["user", "event_name", "count"])
            
            for activity in stats["top_user_activities"]:
                writer.writerow([activity["user"], activity["event_name"], activity["count"]])
            
            print(f"Top user activities exported to {activities_file}")
        output_files["activities"] = activities_file
    
    # Save all stats as one JSON file
    all_stats_file = f"{base_filename}_all_stats.json"
    with open(all_stats_file, "w") as f:
        json.dump(stats, f, indent=2)
        print(f"All statistics exported to {all_stats_file}")
    output_files["all_stats"] = all_stats_file
    
    return output_files

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_company_stats.py <company_id> [from_date] [to_date]")
        sys.exit(1)
    
    company_id = sys.argv[1]
    from_date = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    to_date = sys.argv[3] if len(sys.argv) > 3 else "2025-12-31"
    
    print(f"Analyzing statistics for company {company_id} from {from_date} to {to_date}")
    
    # Credentials can be set via environment variables
    username = os.getenv("MIXPANEL_USERNAME")
    password = os.getenv("MIXPANEL_PASSWORD")
    project_id = os.getenv("MIXPANEL_PROJECT_ID")
    
    print("MIXPANEL_USERNAME:", username)
    print("MIXPANEL_PASSWORD:", "***" if password else None)
    print("MIXPANEL_PROJECT_ID:", project_id)
    
    mixpanel = MixpanelAPI(username, password, project_id)
    
    try:
        print(f"\nFetching company statistics... (this may take a minute)")
        stats = get_company_statistics(mixpanel, company_id, from_date, to_date)
        
        print(f"\nCompany: {company_id}")
        print(f"Total events: {stats.get('total_events', 0)}")
        print(f"Unique users: {stats.get('user_count', 0)}")
        print(f"Event types: {len(stats.get('event_counts', []))}")
        
        # Export all statistics to files
        export_company_stats(stats)
        
    except Exception as e:
        print(f"Error analyzing company statistics: {e}")
        sys.exit(1) 