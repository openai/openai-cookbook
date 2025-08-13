import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from mixpanel_api import MixpanelAPI
import json

def get_user_companies_by_events(mixpanel, user_email, from_date="2024-01-01", to_date="2025-12-31"):
    """
    Find companies by looking at events performed by the user and extracting company info
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
                 event.properties["$user_id"].toLowerCase() === "{user_email}".toLowerCase())
            );
        }})
        .groupByUser(["$group_key"], mixpanel.reducer.any());
    }}
    '''
    return mixpanel.run_jql(script)

def get_user_info(mixpanel, user_email):
    """
    Get all available info about a user to understand what properties exist
    """
    script = f'''
    function main() {{
        return People()
        .filter(function(user) {{
            return (
                (user["$email"] && user["$email"].toLowerCase() === "{user_email}".toLowerCase()) ||
                (user["Email"] && user["Email"].toLowerCase() === "{user_email}".toLowerCase()) ||
                (user["email"] && user["email"].toLowerCase() === "{user_email}".toLowerCase()) ||
                (user["$distinct_id"] && user["$distinct_id"].toLowerCase() === "{user_email}".toLowerCase())
            );
        }})
        .map(function(user) {{
            return user;
        }});
    }}
    '''
    return mixpanel.run_jql(script)

def search_by_company_users(mixpanel, user_email):
    """
    Go through all companies and check if the user is a member
    """
    script = f'''
    function main() {{
        return GroupsOverview("Company")
        .filter(function(group) {{
            var members = group.members || [];
            for (var i = 0; i < members.length; i++) {{
                var member = members[i];
                if (member && 
                    (member === "{user_email}" || 
                     member.toLowerCase() === "{user_email}".toLowerCase())) {{
                    return true;
                }}
            }}
            return false;
        }})
        .map(function(group) {{
            return {{
                company_id: group.key,
                company_name: group.properties["name"] || group.key
            }};
        }});
    }}
    '''
    return mixpanel.run_jql(script)

def find_events_with_company_property(mixpanel, user_email, from_date="2024-01-01", to_date="2025-12-31"):
    """
    Find events with company properties for this user
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
                event.properties["distinct_id"] === "{user_email}"
            );
        }})
        .map(function(event) {{
            return {{
                event: event.name,
                company: event.properties["idEmpresa"] || 
                         event.properties["company_id"] || 
                         (event.properties["$groups"] ? event.properties["$groups"]["Company"] : null)
            }};
        }})
        .filter(function(result) {{
            return result.company !== null && result.company !== undefined;
        }});
    }}
    '''
    return mixpanel.run_jql(script)

if __name__ == "__main__":
    user_email = sys.argv[1] if len(sys.argv) > 1 else "jonetto@colppy.com"
    
    print(f"Searching for companies associated with user: {user_email}")
    print("-" * 60)
    
    mixpanel = MixpanelAPI()
    
    print("1. Finding companies through user profile...")
    user_info = get_user_info(mixpanel, user_email)
    print(json.dumps(user_info, indent=2))
    print("-" * 60)
    
    print("2. Finding companies through user events...")
    events_companies = get_user_companies_by_events(mixpanel, user_email)
    print(json.dumps(events_companies, indent=2))
    print("-" * 60)
    
    print("3. Finding companies that have this user as a member...")
    company_users = search_by_company_users(mixpanel, user_email)
    print(json.dumps(company_users, indent=2))
    print("-" * 60)
    
    print("4. Finding events with company properties...")
    events_with_company = find_events_with_company_property(mixpanel, user_email)
    print(json.dumps(events_with_company, indent=2))
    print("-" * 60) 