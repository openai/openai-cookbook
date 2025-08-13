#!/usr/bin/env python3
"""
🚀 MIXPANEL SCHEMA FETCH RUNNER
Simple script to run the complete Mixpanel schema fetching process

Usage:
    python run_schema_fetch.py
    
Features:
- Fetches complete Mixpanel schema using Lexicon concepts
- Integrates with MCP Mixpanel tools
- Generates comprehensive documentation
- Saves organized data files
- Provides business intelligence insights
"""

import os
import sys
from pathlib import Path

# Add the tools directory to Python path
tools_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(tools_dir))

from scripts.mixpanel.mixpanel_schema_fetcher import MixpanelSchemaFetcher
from scripts.mixpanel.mixpanel_mcp_integration import MixpanelMCPIntegration

def main():
    """Run the complete Mixpanel schema fetching process"""
    
    print("🚀 MIXPANEL SCHEMA FETCH & ANALYSIS")
    print("=" * 60)
    print("Comprehensive Mixpanel data governance and business intelligence")
    print("=" * 60)
    
    try:
        # Step 1: Initialize components
        print("\n📋 STEP 1: INITIALIZATION")
        print("-" * 30)
        
        # Check environment variables
        project_id = os.getenv("MIXPANEL_PROJECT_ID")
        workspace_id = os.getenv("MIXPANEL_WORKSPACE_ID")
        
        if not project_id:
            print("⚠️  MIXPANEL_PROJECT_ID not found in environment variables")
            print("   Using default project configuration for demo")
            project_id = "demo_project"
        
        print(f"🎯 Project ID: {project_id}")
        if workspace_id:
            print(f"🏢 Workspace ID: {workspace_id}")
        
        # Initialize components
        schema_fetcher = MixpanelSchemaFetcher(project_id=project_id, workspace_id=workspace_id)
        mcp_integration = MixpanelMCPIntegration(project_id=project_id, workspace_id=workspace_id)
        
        # Step 2: Fetch business intelligence summary
        print("\n📊 STEP 2: BUSINESS INTELLIGENCE ANALYSIS")
        print("-" * 45)
        
        bi_summary = mcp_integration.get_business_intelligence_summary(date_range_days=30)
        
        print(f"📅 Analysis Period: {bi_summary['period']['start_date']} to {bi_summary['period']['end_date']}")
        print(f"📈 Total Events: {bi_summary['key_metrics']['total_events']:,}")
        print(f"📊 Unique Event Types: {bi_summary['key_metrics']['unique_events']}")
        print(f"⚡ Avg Events/Day: {bi_summary['key_metrics']['avg_events_per_day']:.0f}")
        
        print("\n🔥 TOP 5 EVENTS:")
        for i, event in enumerate(bi_summary['top_events'], 1):
            category = mcp_integration._categorize_event(event['event'])
            print(f"  {i}. {event['event']} ({category}): {event['count']:,}")
        
        print("\n📈 KEY INSIGHTS:")
        for insight in bi_summary['business_insights']:
            print(f"  • {insight}")
        
        print("\n💡 RECOMMENDATIONS:")
        for rec in bi_summary['recommendations']:
            print(f"  → {rec}")
        
        # Step 3: Fetch complete schema
        print("\n🔍 STEP 3: SCHEMA FETCHING")
        print("-" * 30)
        
        schemas = schema_fetcher.fetch_all_schemas()
        
        # Step 4: Save schemas to files
        print("\n💾 STEP 4: SAVING SCHEMA FILES")
        print("-" * 35)
        
        file_paths = schema_fetcher.save_schemas_to_files(schemas)
        
        print("✅ Files generated:")
        for file_type, path in file_paths.items():
            file_size = Path(path).stat().st_size / 1024  # KB
            print(f"   📄 {file_type}: {Path(path).name} ({file_size:.1f} KB)")
        
        # Step 5: Schema comparison (if previous exists)
        print("\n🔄 STEP 5: SCHEMA COMPARISON")
        print("-" * 32)
        
        comparison = schema_fetcher.compare_with_previous_schema()
        
        if comparison:
            print(f"📊 Changes detected: {comparison['summary']['total_changes']}")
            print(f"   ➕ Events added: {comparison['summary']['events_added']}")
            print(f"   ➖ Events removed: {comparison['summary']['events_removed']}")
        else:
            print("ℹ️  No previous schema found for comparison")
        
        # Step 6: Generate summary report
        print("\n📋 STEP 6: SUMMARY REPORT")
        print("-" * 28)
        
        print(f"📁 Output Directory: {schema_fetcher.output_dir}")
        print(f"📊 Schema Statistics:")
        print(f"   • Events: {schemas['metadata']['total_events']}")
        print(f"   • Event Properties: {schemas['metadata']['total_properties']}")
        print(f"   • Profile Properties: {len(schemas.get('profile_properties', []))}")
        print(f"   • Custom Events: {schemas['metadata']['total_custom_events']}")
        print(f"   • Lookup Tables: {len(schemas.get('lookup_tables', []))}")
        
        # Step 7: Integration recommendations
        print("\n🎯 STEP 7: NEXT STEPS & INTEGRATION")
        print("-" * 40)
        
        print("✅ COMPLETED TASKS:")
        print("   • Fetched comprehensive Mixpanel schema")
        print("   • Generated business intelligence insights")
        print("   • Created structured documentation")
        print("   • Saved data in multiple formats (JSON, CSV, Markdown)")
        print("   • Analyzed schema changes (if applicable)")
        
        print("\n🚀 RECOMMENDED NEXT STEPS:")
        print("   1. Review the generated schema documentation")
        print("   2. Integrate schema data with your CEO Assistant")
        print("   3. Set up automated schema monitoring")
        print("   4. Use insights for product and business decisions")
        print("   5. Connect with real Mixpanel API for live data")
        
        print("\n🔗 INTEGRATION OPTIONS:")
        print("   • CEO Assistant: Add schema-aware Mixpanel queries")
        print("   • Business Intelligence: Use for executive dashboards")
        print("   • Data Governance: Track schema evolution over time")
        print("   • Product Analytics: Guide feature development")
        
        print("\n📚 GENERATED FILES:")
        print(f"   📁 Base Directory: {schema_fetcher.output_dir}")
        print("   📄 complete_schema.json - Full schema data")
        print("   📄 events_schema.csv - Events and properties")
        print("   📄 event_properties_schema.csv - Property definitions")
        print("   📄 profile_properties_schema.csv - User profile schema")
        print("   📄 custom_events_schema.csv - Custom events and formulas")
        print("   📄 schema_documentation.md - Human-readable documentation")
        print("   📄 schema_summary.json - Quick analysis summary")
        if comparison:
            print("   📄 schema_comparison.json - Change analysis")
        
        print("\n🎉 SCHEMA FETCH COMPLETE!")
        print("=" * 60)
        print("Your Mixpanel schema has been successfully fetched and organized.")
        print("Check the generated files for comprehensive data governance insights.")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR DURING SCHEMA FETCH:")
        print(f"   {str(e)}")
        print("\n🔧 TROUBLESHOOTING:")
        print("   1. Check your .env file for MIXPANEL_PROJECT_ID")
        print("   2. Verify your Mixpanel API credentials")
        print("   3. Ensure you have write permissions to the output directory")
        print("   4. Check your internet connection")
        
        import traceback
        print(f"\n🐛 DETAILED ERROR:")
        traceback.print_exc()
        
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 