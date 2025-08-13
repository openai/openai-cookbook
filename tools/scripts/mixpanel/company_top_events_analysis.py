#!/usr/bin/env python3
"""
Company-level Top Events Analysis for Colppy Mixpanel Data

This script analyzes top events at the company level and lists users per company.
It works around Mixpanel API rate limits by using efficient JQL queries.
"""

import os
import sys
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from mixpanel_api import MixpanelAPI

def get_top_companies_by_activity(mixpanel: MixpanelAPI, 
                                 from_date: str = "2024-01-01", 
                                 to_date: str = "2025-01-15", 
                                 limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get top companies by event activity count
    
    Args:
        mixpanel: Initialized MixpanelAPI instance
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        limit: Number of top companies to return
        
    Returns:
        List of companies with activity counts
    """
    script = f'''
    function main() {{
        return Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
        }})
        .filter(function(event) {{
            return (
                event.properties["company_id"] || 
                event.properties["idEmpresa"] ||
                (event.properties["company"] && Array.isArray(event.properties["company"]) && event.properties["company"].length > 0) ||
                (event.properties["$groups"] && event.properties["$groups"]["Company"])
            );
        }})
        .groupBy([
            function(event) {{
                return event.properties["company_id"] || 
                       event.properties["idEmpresa"] ||
                       (Array.isArray(event.properties["company"]) ? event.properties["company"][0] : event.properties["company"]) ||
                       (event.properties["$groups"] ? event.properties["$groups"]["Company"] : "unknown");
            }}
        ], mixpanel.reducer.count())
        .map(function(result) {{
            return {{
                company_id: result.key[0],
                total_events: result.value
            }};
        }});
    }}
    '''
    
    print(f"🔍 Fetching top {limit} companies by activity...")
    companies = mixpanel.run_jql(script)
    
    if companies:
        # Sort in Python instead of JQL
        companies = sorted(companies, key=lambda x: x.get('total_events', 0), reverse=True)
        if len(companies) > limit:
            companies = companies[:limit]
        
    return companies or []

def get_company_top_events(mixpanel: MixpanelAPI, 
                          company_id: str, 
                          from_date: str = "2024-01-01", 
                          to_date: str = "2025-01-15") -> List[Dict[str, Any]]:
    """
    Get top events for a specific company
    """
    script = f'''
    function main() {{
        return Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
        }})
        .filter(function(event) {{
            return (
                event.properties["company_id"] === "{company_id}" ||
                event.properties["idEmpresa"] === "{company_id}" ||
                (Array.isArray(event.properties["company"]) && event.properties["company"].indexOf("{company_id}") >= 0) ||
                (event.properties["company"] === "{company_id}") ||
                (event.properties["$groups"] && event.properties["$groups"]["Company"] === "{company_id}")
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
    
    events = mixpanel.run_jql(script) or []
    # Sort in Python
    return sorted(events, key=lambda x: x.get('count', 0), reverse=True)

def get_company_users(mixpanel: MixpanelAPI, 
                     company_id: str, 
                     from_date: str = "2024-01-01", 
                     to_date: str = "2025-01-15") -> List[Dict[str, Any]]:
    """
    Get users for a specific company
    """
    script = f'''
    function main() {{
        return Events({{
            from_date: "{from_date}",
            to_date: "{to_date}"
        }})
        .filter(function(event) {{
            return (
                event.properties["company_id"] === "{company_id}" ||
                event.properties["idEmpresa"] === "{company_id}" ||
                (Array.isArray(event.properties["company"]) && event.properties["company"].indexOf("{company_id}") >= 0) ||
                (event.properties["company"] === "{company_id}") ||
                (event.properties["$groups"] && event.properties["$groups"]["Company"] === "{company_id}")
            );
        }})
        .groupBy([
            function(event) {{
                return event.properties["$user_id"] || 
                       event.properties["Email"] || 
                       event.properties["email"] || 
                       event.properties["$email"] ||
                       event.properties["idUsuario"] || 
                       event.properties["usuario"] || 
                       event.distinct_id ||
                       "unknown";
            }}
        ], mixpanel.reducer.count())
        .map(function(result) {{
            return {{
                user_id: result.key[0],
                event_count: result.value
            }};
        }});
    }}
    '''
    
    users = mixpanel.run_jql(script) or []
    # Sort in Python
    return sorted(users, key=lambda x: x.get('event_count', 0), reverse=True)

def analyze_companies_and_events(from_date: str = "2024-01-01", 
                                to_date: str = "2025-01-15",
                                top_companies_limit: int = 10,
                                output_dir: str = "../../outputs/mixpanel") -> Dict[str, Any]:
    """
    Main analysis function that gets company data and top events
    
    Args:
        from_date: Start date for analysis
        to_date: End date for analysis  
        top_companies_limit: Number of top companies to analyze
        output_dir: Directory to save output files
        
    Returns:
        Dictionary with analysis results
    """
    mixpanel = MixpanelAPI()
    
    print("🚀 Starting Company-Level Events Analysis")
    print("=" * 60)
    
    # Get top companies
    top_companies = get_top_companies_by_activity(
        mixpanel, from_date, to_date, top_companies_limit
    )
    
    if not top_companies:
        print("❌ No companies found with activity data")
        return {}
        
    print(f"✅ Found {len(top_companies)} active companies")
    
    # Analyze each company
    analysis_results = {
        "analysis_date": datetime.now().isoformat(),
        "period": {"from": from_date, "to": to_date},
        "companies": []
    }
    
    for i, company in enumerate(top_companies, 1):
        company_id = company["company_id"]
        total_events = company["total_events"]
        
        print(f"\n📊 Analyzing Company {i}/{len(top_companies)}: {company_id}")
        print(f"   Total Events: {total_events:,}")
        
        try:
            # Get top events for this company
            print("   🔍 Fetching top events...")
            top_events = get_company_top_events(mixpanel, company_id, from_date, to_date)
            
            # Get users for this company
            print("   👥 Fetching company users...")
            company_users = get_company_users(mixpanel, company_id, from_date, to_date)
            
            company_analysis = {
                "company_id": company_id,
                "total_events": total_events,
                "total_users": len(company_users),
                "top_events": top_events[:10],  # Top 10 events
                "users": company_users[:20],    # Top 20 users by activity
                "analysis_status": "success"
            }
            
            analysis_results["companies"].append(company_analysis)
            
            print(f"   ✅ Found {len(top_events)} event types, {len(company_users)} users")
            
        except Exception as e:
            print(f"   ❌ Error analyzing company {company_id}: {str(e)}")
            analysis_results["companies"].append({
                "company_id": company_id,
                "total_events": total_events,
                "analysis_status": "error",
                "error": str(e)
            })
    
    # Save results
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save JSON results
    json_file = os.path.join(output_dir, f"company_events_analysis_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, indent=2, ensure_ascii=False)
    
    # Save CSV summary
    csv_file = os.path.join(output_dir, f"company_summary_{timestamp}.csv")
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')  # Using ; as separator for Argentina
        
        # Company summary
        writer.writerow(['Company ID', 'Total Events', 'Total Users', 'Top Event', 'Top Event Count', 'Status'])
        
        for company in analysis_results["companies"]:
            if company.get("analysis_status") == "success":
                top_event = company["top_events"][0] if company["top_events"] else {"event_name": "N/A", "count": 0}
                writer.writerow([
                    company["company_id"],
                    f"{company['total_events']:,}".replace(',', '.'),  # Argentina number format
                    company["total_users"],
                    top_event["event_name"],
                    f"{top_event['count']:,}".replace(',', '.'),
                    company["analysis_status"]
                ])
            else:
                writer.writerow([
                    company["company_id"],
                    f"{company['total_events']:,}".replace(',', '.'),
                    "Error",
                    "Error",
                    "Error",
                    f"Error: {company.get('error', 'Unknown')}"
                ])
    
    print(f"\n💾 Results saved:")
    print(f"   📄 JSON: {json_file}")
    print(f"   📊 CSV:  {csv_file}")
    
    return analysis_results

def print_summary(results: Dict[str, Any]) -> None:
    """Print a summary of the analysis results"""
    if not results or not results.get("companies"):
        print("❌ No results to summarize")
        return
        
    print("\n" + "=" * 60)
    print("📈 COMPANY EVENTS ANALYSIS SUMMARY")
    print("=" * 60)
    
    successful_analyses = [c for c in results["companies"] if c.get("analysis_status") == "success"]
    
    print(f"📊 Period: {results['period']['from']} to {results['period']['to']}")
    print(f"🏢 Companies Analyzed: {len(results['companies'])}")
    print(f"✅ Successful Analyses: {len(successful_analyses)}")
    print(f"❌ Failed Analyses: {len(results['companies']) - len(successful_analyses)}")
    
    if successful_analyses:
        print(f"\n🔝 TOP COMPANIES BY ACTIVITY:")
        print("-" * 40)
        
        for i, company in enumerate(successful_analyses[:5], 1):
            print(f"{i}. Company {company['company_id']}")
            print(f"   📊 Total Events: {company['total_events']:,}")
            print(f"   👥 Total Users: {company['total_users']}")
            
            if company['top_events']:
                top_event = company['top_events'][0]
                print(f"   🎯 Top Event: {top_event['event_name']} ({top_event['count']:,} times)")
            
            if company['users']:
                top_user = company['users'][0]
                print(f"   🏆 Most Active User: {top_user['user_id']} ({top_user['event_count']:,} events)")
            print()

if __name__ == "__main__":
    # Configuration
    from_date = "2024-01-01"
    to_date = "2025-01-15" 
    top_companies_limit = 10
    
    print("🎯 COLPPY COMPANY-LEVEL EVENTS ANALYSIS")
    print("=" * 60)
    print(f"📅 Period: {from_date} to {to_date}")
    print(f"🏢 Analyzing top {top_companies_limit} companies")
    print()
    
    try:
        results = analyze_companies_and_events(
            from_date=from_date,
            to_date=to_date, 
            top_companies_limit=top_companies_limit
        )
        
        if results:
            print_summary(results)
        else:
            print("❌ Analysis failed - no results returned")
            
    except KeyboardInterrupt:
        print("\n⏹️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Analysis failed with error: {str(e)}")
        import traceback
        traceback.print_exc() 