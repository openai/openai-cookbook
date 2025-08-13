#!/usr/bin/env python3
"""
Identify Dormant Companies
Finds companies that were active in week before last but inactive last week.
This helps identify potential churn risks for proactive retention efforts.
"""

import os
import sys
import json
from datetime import datetime, timedelta
import time

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, project_root)

try:
    from mcp import create_session, StdioServerParameters
    MCP_AVAILABLE = True
except ImportError:
    print("⚠️  MCP not available. Please activate the mcp_env environment:")
    print("   source mcp_env/bin/activate")
    MCP_AVAILABLE = False

def get_company_activity_for_period(session, start_date, end_date, period_name):
    """Get company activity for a specific period."""
    print(f"\n📊 Getting company activity for {period_name} ({start_date} to {end_date})...")
    
    try:
        # Try with company property first
        result = session.call_tool(
            "mcp_mixpanel_query_segmentation_report",
            {
                "event": "$mp_session_record",
                "from_date": start_date,
                "to_date": end_date,
                "on": 'properties["company"]',
                "type": "unique",
                "limit": 500,
                "where": 'properties["company"] != ""'
            }
        )
        
        if result and hasattr(result, 'content'):
            content = result.content[0].text if result.content else "No content"
            
            # Check for rate limit errors
            if "rate limit" in content.lower() or "limit exceeded" in content.lower():
                print(f"❌ Rate limit hit for {period_name}")
                return None
            
            try:
                data = json.loads(content)
                print(f"✅ Retrieved data for {period_name}")
                return data
            except json.JSONDecodeError:
                print(f"❌ Invalid JSON response for {period_name}")
                return None
    except Exception as e:
        error_msg = str(e)
        if "rate limit" in error_msg.lower():
            print(f"❌ Rate limit hit for {period_name}: {error_msg}")
            return None
        print(f"❌ Error getting {period_name} data: {error_msg}")
        return None

def extract_companies_from_data(data, period_name):
    """Extract company names and their activity counts from Mixpanel data."""
    if not data:
        return {}
    
    companies = {}
    
    try:
        # Handle different possible data structures
        if 'data' in data:
            if isinstance(data['data'], dict):
                # Structure: {"data": {"Company Name": count}}
                companies = data['data']
            elif isinstance(data['data'], list):
                # Structure: {"data": [{"key": "Company Name", "value": count}]}
                for item in data['data']:
                    if isinstance(item, dict) and 'key' in item and 'value' in item:
                        companies[item['key']] = item['value']
        
        print(f"📈 Found {len(companies)} companies in {period_name}")
        return companies
        
    except Exception as e:
        print(f"❌ Error parsing {period_name} data: {e}")
        return {}

def identify_dormant_companies(previous_week_companies, last_week_companies):
    """Identify companies that were active before but not last week."""
    
    # Find companies that were active in previous week but not in last week
    dormant_companies = []
    
    for company, prev_activity in previous_week_companies.items():
        if company not in last_week_companies:
            dormant_companies.append({
                'company': company,
                'previous_week_activity': prev_activity,
                'last_week_activity': 0,
                'risk_level': 'HIGH' if prev_activity > 100 else 'MEDIUM' if prev_activity > 20 else 'LOW'
            })
    
    # Sort by previous week activity (highest risk first)
    dormant_companies.sort(key=lambda x: x['previous_week_activity'], reverse=True)
    
    return dormant_companies

def analyze_dormant_companies():
    """Main analysis function."""
    if not MCP_AVAILABLE:
        return False
    
    print("🔍 Dormant Company Analysis")
    print("=" * 50)
    print(f"🕐 Analysis started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Define date ranges
    today = datetime.now()
    
    # Last week: June 9-15, 2025
    last_week_start = "2025-06-09"
    last_week_end = "2025-06-15"
    
    # Week before last: June 2-8, 2025  
    previous_week_start = "2025-06-02"
    previous_week_end = "2025-06-08"
    
    print(f"📅 Previous week: {previous_week_start} to {previous_week_end}")
    print(f"📅 Last week: {last_week_start} to {last_week_end}")
    
    try:
        with create_session(StdioServerParameters(command="npx", args=["-y", "@mixpanel/mcp-server"])) as session:
            
            # Get company activity for previous week
            previous_week_data = get_company_activity_for_period(
                session, previous_week_start, previous_week_end, "Previous Week"
            )
            
            if previous_week_data is None:
                print("❌ Cannot proceed - rate limit hit or error getting previous week data")
                return False
            
            # Wait a bit to avoid rate limits
            print("⏳ Waiting 5 seconds to avoid rate limits...")
            time.sleep(5)
            
            # Get company activity for last week
            last_week_data = get_company_activity_for_period(
                session, last_week_start, last_week_end, "Last Week"
            )
            
            if last_week_data is None:
                print("❌ Cannot proceed - rate limit hit or error getting last week data")
                return False
            
            # Extract company data
            previous_week_companies = extract_companies_from_data(previous_week_data, "Previous Week")
            last_week_companies = extract_companies_from_data(last_week_data, "Last Week")
            
            if not previous_week_companies:
                print("❌ No previous week company data available")
                return False
            
            # Identify dormant companies
            dormant_companies = identify_dormant_companies(previous_week_companies, last_week_companies)
            
            # Display results
            print("\n" + "=" * 50)
            print("🚨 DORMANT COMPANY ANALYSIS RESULTS")
            print("=" * 50)
            
            if not dormant_companies:
                print("🎉 Great news! No completely dormant companies found.")
                print("All companies that were active in the previous week remained active last week.")
            else:
                print(f"⚠️  Found {len(dormant_companies)} potentially dormant companies")
                print("\nTop Dormant Companies (by previous activity level):")
                print("-" * 70)
                print(f"{'Company':<30} {'Prev Week':<12} {'Last Week':<12} {'Risk':<8}")
                print("-" * 70)
                
                for i, company_data in enumerate(dormant_companies[:20], 1):  # Show top 20
                    print(f"{company_data['company'][:29]:<30} "
                          f"{company_data['previous_week_activity']:<12} "
                          f"{company_data['last_week_activity']:<12} "
                          f"{company_data['risk_level']:<8}")
                
                # Summary by risk level
                risk_summary = {}
                for company in dormant_companies:
                    risk_level = company['risk_level']
                    if risk_level not in risk_summary:
                        risk_summary[risk_level] = 0
                    risk_summary[risk_level] += 1
                
                print("\n📊 Risk Level Summary:")
                for risk_level in ['HIGH', 'MEDIUM', 'LOW']:
                    count = risk_summary.get(risk_level, 0)
                    if count > 0:
                        print(f"  🔴 {risk_level}: {count} companies")
                
                print("\n💡 Recommended Actions:")
                print("  1. High Risk: Immediate outreach and check-in calls")
                print("  2. Medium Risk: Send re-engagement email campaigns") 
                print("  3. Low Risk: Include in general newsletter/updates")
            
            # Activity comparison
            total_prev = len(previous_week_companies)
            total_last = len(last_week_companies)
            retention_rate = (total_last / total_prev * 100) if total_prev > 0 else 0
            
            print(f"\n📈 Company Activity Summary:")
            print(f"  Previous week active companies: {total_prev}")
            print(f"  Last week active companies: {total_last}")
            print(f"  Week-over-week retention: {retention_rate:.1f}%")
            
            return True
            
    except Exception as e:
        error_msg = str(e)
        if "rate limit" in error_msg.lower():
            print(f"❌ Rate limit exceeded: {error_msg}")
            print("\n💡 Try again in about an hour when the rate limit resets.")
            return False
        print(f"❌ Analysis failed: {error_msg}")
        return False

def main():
    """Main function."""
    success = analyze_dormant_companies()
    
    if success:
        print("\n🎯 Analysis completed successfully!")
        sys.exit(0)
    else:
        print("\n⚠️  Analysis could not be completed due to rate limits or errors.")
        print("💡 Please try again later when API limits reset.")
        sys.exit(1)

if __name__ == "__main__":
    main() 