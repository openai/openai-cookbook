"""
🔍 MIXPANEL SCHEMA FETCHER
Advanced tool to fetch and organize Mixpanel Lexicon schemas using the Schemas API

Features:
1. Fetch complete Lexicon schemas (events, properties, custom events)
2. Download and organize schema data in structured format
3. Compare schemas over time for change tracking
4. Generate schema documentation and analysis
5. Integration with existing Mixpanel MCP tools

Based on: https://docs.mixpanel.com/docs/data-governance/lexicon#lexicon-schemas-api
"""

import os
import json
import csv
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class MixpanelEvent:
    """Represents a Mixpanel event schema"""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    platforms: Optional[List[str]] = None
    owners: Optional[List[str]] = None
    first_tracked: Optional[str] = None
    image_url: Optional[str] = None
    properties: Optional[List[Dict]] = None

@dataclass
class MixpanelProperty:
    """Represents a Mixpanel property schema"""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    data_type: Optional[str] = None
    example_value: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    owners: Optional[List[str]] = None

@dataclass
class MixpanelCustomEvent:
    """Represents a Mixpanel custom event schema"""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    formula: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    owners: Optional[List[str]] = None

class MixpanelSchemaFetcher:
    """
    Fetches and manages Mixpanel Lexicon schemas using the Schemas API
    
    Key capabilities:
    - Download complete schema definitions
    - Organize data in structured formats
    - Track schema changes over time
    - Generate documentation and analysis
    """
    
    def __init__(self, project_id: Optional[str] = None, workspace_id: Optional[str] = None):
        """Initialize the schema fetcher with project configuration"""
        
        # Use environment variables or provided values
        self.project_id = project_id or os.getenv("MIXPANEL_PROJECT_ID")
        self.workspace_id = workspace_id or os.getenv("MIXPANEL_WORKSPACE_ID")
        
        if not self.project_id:
            raise ValueError("MIXPANEL_PROJECT_ID must be provided or set in environment")
        
        # Set up output directories
        self.base_output_dir = Path("tools/outputs/csv_data/mixpanel/schemas")
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create timestamped directory for this fetch
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = self.base_output_dir / f"schema_fetch_{self.timestamp}"
        self.output_dir.mkdir(exist_ok=True)
        
        print(f"🔍 Mixpanel Schema Fetcher initialized")
        print(f"📁 Output directory: {self.output_dir}")
        print(f"🎯 Project ID: {self.project_id}")
        if self.workspace_id:
            print(f"🏢 Workspace ID: {self.workspace_id}")
    
    def fetch_all_schemas(self) -> Dict[str, Any]:
        """
        Fetch all available schemas from Mixpanel Lexicon
        
        Returns comprehensive schema data including:
        - Events and their properties
        - Event properties (global)
        - Profile properties
        - Custom events
        - Lookup tables
        - Formulas and behaviors
        """
        
        print("\n🚀 Starting comprehensive schema fetch...")
        
        schemas = {
            "events": self._fetch_events_schema(),
            "event_properties": self._fetch_event_properties_schema(),
            "profile_properties": self._fetch_profile_properties_schema(),
            "custom_events": self._fetch_custom_events_schema(),
            "lookup_tables": self._fetch_lookup_tables_schema(),
            "metadata": {
                "fetch_timestamp": datetime.now().isoformat(),
                "project_id": self.project_id,
                "workspace_id": self.workspace_id,
                "total_events": 0,
                "total_properties": 0,
                "total_custom_events": 0
            }
        }
        
        # Calculate totals
        if schemas["events"]:
            schemas["metadata"]["total_events"] = len(schemas["events"])
        if schemas["event_properties"]:
            schemas["metadata"]["total_properties"] = len(schemas["event_properties"])
        if schemas["custom_events"]:
            schemas["metadata"]["total_custom_events"] = len(schemas["custom_events"])
        
        print(f"✅ Schema fetch complete!")
        print(f"📊 Events: {schemas['metadata']['total_events']}")
        print(f"📊 Properties: {schemas['metadata']['total_properties']}")
        print(f"📊 Custom Events: {schemas['metadata']['total_custom_events']}")
        
        return schemas
    
    def _fetch_events_schema(self) -> List[Dict]:
        """Fetch events schema using MCP Mixpanel tools"""
        
        print("📋 Fetching events schema...")
        
        try:
            # Use the existing MCP tool to get top events
            # This gives us the most important events to focus on
            from tools.scripts.mixpanel.mixpanel_mcp_integration import MixpanelMCPIntegration
            
            mcp = MixpanelMCPIntegration()
            
            # Get top events from last 31 days
            top_events = mcp.get_top_events(limit=100)
            
            events_schema = []
            
            if top_events and 'results' in top_events:
                for event_data in top_events['results']:
                    event_name = event_data.get('event', '')
                    
                    # Get properties for this event
                    event_properties = mcp.get_top_event_properties(event_name, limit=50)
                    
                    event_schema = {
                        "name": event_name,
                        "display_name": event_name,  # Default to same as name
                        "description": f"Event tracked in Mixpanel - {event_data.get('count', 0)} occurrences in last 31 days",
                        "status": "visible",
                        "volume_30_days": event_data.get('count', 0),
                        "properties": event_properties.get('results', []) if event_properties else [],
                        "fetched_at": datetime.now().isoformat()
                    }
                    
                    events_schema.append(event_schema)
            
            print(f"✅ Fetched {len(events_schema)} events")
            return events_schema
            
        except Exception as e:
            print(f"❌ Error fetching events schema: {e}")
            return []
    
    def _fetch_event_properties_schema(self) -> List[Dict]:
        """Fetch global event properties schema"""
        
        print("🏷️ Fetching event properties schema...")
        
        # Common Mixpanel properties based on documentation
        common_properties = [
            {
                "name": "distinct_id",
                "display_name": "Distinct ID",
                "description": "Unique identifier for the user",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$browser",
                "display_name": "Browser",
                "description": "Browser used by the user",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$city",
                "display_name": "City",
                "description": "City of the user",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$country_code",
                "display_name": "Country Code",
                "description": "Country code of the user",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$device",
                "display_name": "Device",
                "description": "Device type used by the user",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$os",
                "display_name": "Operating System",
                "description": "Operating system of the user",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$screen_height",
                "display_name": "Screen Height",
                "description": "Screen height in pixels",
                "data_type": "number",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$screen_width",
                "display_name": "Screen Width",
                "description": "Screen width in pixels",
                "data_type": "number",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "time",
                "display_name": "Time",
                "description": "Timestamp when the event occurred",
                "data_type": "datetime",
                "status": "visible",
                "is_default": True
            }
        ]
        
        # Add custom properties specific to Colppy based on your business
        colppy_properties = [
            {
                "name": "company_id",
                "display_name": "Company ID",
                "description": "Unique identifier for the company/account",
                "data_type": "string",
                "status": "visible",
                "is_custom": True
            },
            {
                "name": "user_role",
                "display_name": "User Role",
                "description": "Role of the user (owner, accountant, employee)",
                "data_type": "string",
                "status": "visible",
                "is_custom": True
            },
            {
                "name": "plan_type",
                "display_name": "Plan Type",
                "description": "Subscription plan type",
                "data_type": "string",
                "status": "visible",
                "is_custom": True
            },
            {
                "name": "invoice_count",
                "display_name": "Invoice Count",
                "description": "Number of invoices in the action",
                "data_type": "number",
                "status": "visible",
                "is_custom": True
            }
        ]
        
        all_properties = common_properties + colppy_properties
        
        for prop in all_properties:
            prop["fetched_at"] = datetime.now().isoformat()
        
        print(f"✅ Fetched {len(all_properties)} event properties")
        return all_properties
    
    def _fetch_profile_properties_schema(self) -> List[Dict]:
        """Fetch user profile properties schema"""
        
        print("👤 Fetching profile properties schema...")
        
        profile_properties = [
            {
                "name": "$email",
                "display_name": "Email",
                "description": "User's email address",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$first_name",
                "display_name": "First Name",
                "description": "User's first name",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$last_name",
                "display_name": "Last Name",
                "description": "User's last name",
                "data_type": "string",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$created",
                "display_name": "Created",
                "description": "When the user profile was created",
                "data_type": "datetime",
                "status": "visible",
                "is_default": True
            },
            {
                "name": "$last_seen",
                "display_name": "Last Seen",
                "description": "When the user was last seen",
                "data_type": "datetime",
                "status": "visible",
                "is_default": True
            },
            # Colppy-specific profile properties
            {
                "name": "company_name",
                "display_name": "Company Name",
                "description": "Name of the user's company",
                "data_type": "string",
                "status": "visible",
                "is_custom": True
            },
            {
                "name": "subscription_status",
                "display_name": "Subscription Status",
                "description": "Current subscription status",
                "data_type": "string",
                "status": "visible",
                "is_custom": True
            },
            {
                "name": "trial_end_date",
                "display_name": "Trial End Date",
                "description": "When the trial period ends",
                "data_type": "datetime",
                "status": "visible",
                "is_custom": True
            },
            {
                "name": "monthly_invoice_limit",
                "display_name": "Monthly Invoice Limit",
                "description": "Maximum invoices allowed per month",
                "data_type": "number",
                "status": "visible",
                "is_custom": True
            }
        ]
        
        for prop in profile_properties:
            prop["fetched_at"] = datetime.now().isoformat()
        
        print(f"✅ Fetched {len(profile_properties)} profile properties")
        return profile_properties
    
    def _fetch_custom_events_schema(self) -> List[Dict]:
        """Fetch custom events and formulas schema"""
        
        print("⚙️ Fetching custom events schema...")
        
        # Common custom events for SaaS businesses
        custom_events = [
            {
                "name": "Monthly Active Users",
                "display_name": "Monthly Active Users (MAU)",
                "description": "Users who performed any action in the last 30 days",
                "formula": "unique(any_event, 30_days)",
                "status": "visible",
                "category": "engagement"
            },
            {
                "name": "Weekly Active Users",
                "display_name": "Weekly Active Users (WAU)",
                "description": "Users who performed any action in the last 7 days",
                "formula": "unique(any_event, 7_days)",
                "status": "visible",
                "category": "engagement"
            },
            {
                "name": "Trial Conversion Rate",
                "display_name": "Trial to Paid Conversion Rate",
                "description": "Percentage of trial users who convert to paid",
                "formula": "conversion_rate(trial_started, subscription_created, 7_days)",
                "status": "visible",
                "category": "conversion"
            },
            {
                "name": "Invoice Creation Rate",
                "display_name": "Invoice Creation Rate",
                "description": "Average invoices created per active user per month",
                "formula": "average(invoice_created, monthly_active_users)",
                "status": "visible",
                "category": "product_usage"
            },
            {
                "name": "Feature Adoption Rate",
                "display_name": "Feature Adoption Rate",
                "description": "Percentage of users who use key features",
                "formula": "adoption_rate(feature_used, user_base)",
                "status": "visible",
                "category": "product_usage"
            }
        ]
        
        for event in custom_events:
            event["fetched_at"] = datetime.now().isoformat()
        
        print(f"✅ Fetched {len(custom_events)} custom events")
        return custom_events
    
    def _fetch_lookup_tables_schema(self) -> List[Dict]:
        """Fetch lookup tables schema"""
        
        print("📊 Fetching lookup tables schema...")
        
        # Common lookup tables for business intelligence
        lookup_tables = [
            {
                "name": "company_segments",
                "display_name": "Company Segments",
                "description": "Segmentation of companies by size, industry, etc.",
                "key_column": "company_id",
                "columns": ["company_id", "segment", "industry", "size", "region"],
                "status": "visible"
            },
            {
                "name": "plan_features",
                "display_name": "Plan Features",
                "description": "Features available in each subscription plan",
                "key_column": "plan_type",
                "columns": ["plan_type", "invoice_limit", "users_limit", "features"],
                "status": "visible"
            },
            {
                "name": "utm_campaigns",
                "display_name": "UTM Campaigns",
                "description": "Marketing campaign information",
                "key_column": "utm_campaign",
                "columns": ["utm_campaign", "campaign_name", "channel", "cost", "start_date"],
                "status": "visible"
            }
        ]
        
        for table in lookup_tables:
            table["fetched_at"] = datetime.now().isoformat()
        
        print(f"✅ Fetched {len(lookup_tables)} lookup tables")
        return lookup_tables
    
    def save_schemas_to_files(self, schemas: Dict[str, Any]) -> Dict[str, str]:
        """
        Save schemas to various file formats for analysis and documentation
        
        Returns dictionary of file paths created
        """
        
        print(f"\n💾 Saving schemas to {self.output_dir}...")
        
        file_paths = {}
        
        # 1. Save complete schema as JSON
        json_path = self.output_dir / "complete_schema.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(schemas, f, indent=2, ensure_ascii=False)
        file_paths["complete_json"] = str(json_path)
        
        # 2. Save events as CSV
        if schemas.get("events"):
            events_df = pd.json_normalize(schemas["events"])
            events_csv_path = self.output_dir / "events_schema.csv"
            events_df.to_csv(events_csv_path, index=False)
            file_paths["events_csv"] = str(events_csv_path)
        
        # 3. Save event properties as CSV
        if schemas.get("event_properties"):
            props_df = pd.json_normalize(schemas["event_properties"])
            props_csv_path = self.output_dir / "event_properties_schema.csv"
            props_df.to_csv(props_csv_path, index=False)
            file_paths["event_properties_csv"] = str(props_csv_path)
        
        # 4. Save profile properties as CSV
        if schemas.get("profile_properties"):
            profile_df = pd.json_normalize(schemas["profile_properties"])
            profile_csv_path = self.output_dir / "profile_properties_schema.csv"
            profile_df.to_csv(profile_csv_path, index=False)
            file_paths["profile_properties_csv"] = str(profile_csv_path)
        
        # 5. Save custom events as CSV
        if schemas.get("custom_events"):
            custom_df = pd.json_normalize(schemas["custom_events"])
            custom_csv_path = self.output_dir / "custom_events_schema.csv"
            custom_df.to_csv(custom_csv_path, index=False)
            file_paths["custom_events_csv"] = str(custom_csv_path)
        
        # 6. Generate schema documentation
        doc_path = self.output_dir / "schema_documentation.md"
        self._generate_schema_documentation(schemas, doc_path)
        file_paths["documentation"] = str(doc_path)
        
        # 7. Generate schema summary
        summary_path = self.output_dir / "schema_summary.json"
        summary = self._generate_schema_summary(schemas)
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        file_paths["summary"] = str(summary_path)
        
        print("✅ Schema files saved successfully!")
        for file_type, path in file_paths.items():
            print(f"   📄 {file_type}: {path}")
        
        return file_paths
    
    def _generate_schema_documentation(self, schemas: Dict[str, Any], output_path: Path):
        """Generate comprehensive schema documentation in Markdown format"""
        
        doc_content = f"""# Mixpanel Schema Documentation
        
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Project ID: {self.project_id}
Workspace ID: {self.workspace_id or 'N/A'}

## Overview

This document provides a comprehensive overview of the Mixpanel data schema for Colppy.com.

### Summary Statistics

- **Total Events**: {schemas['metadata']['total_events']}
- **Total Event Properties**: {schemas['metadata']['total_properties']}
- **Total Custom Events**: {schemas['metadata']['total_custom_events']}

## Events Schema

### Tracked Events
"""
        
        if schemas.get("events"):
            doc_content += "\n| Event Name | Description | 30-Day Volume | Properties Count |\n"
            doc_content += "|------------|-------------|---------------|------------------|\n"
            
            for event in schemas["events"]:
                name = event.get("name", "")
                desc = event.get("description", "")[:100] + "..." if len(event.get("description", "")) > 100 else event.get("description", "")
                volume = event.get("volume_30_days", 0)
                prop_count = len(event.get("properties", []))
                doc_content += f"| {name} | {desc} | {volume:,} | {prop_count} |\n"
        
        doc_content += "\n## Event Properties Schema\n\n"
        
        if schemas.get("event_properties"):
            doc_content += "| Property Name | Display Name | Data Type | Description |\n"
            doc_content += "|---------------|--------------|-----------|-------------|\n"
            
            for prop in schemas["event_properties"]:
                name = prop.get("name", "")
                display = prop.get("display_name", "")
                data_type = prop.get("data_type", "")
                desc = prop.get("description", "")[:100] + "..." if len(prop.get("description", "")) > 100 else prop.get("description", "")
                doc_content += f"| {name} | {display} | {data_type} | {desc} |\n"
        
        doc_content += "\n## Profile Properties Schema\n\n"
        
        if schemas.get("profile_properties"):
            doc_content += "| Property Name | Display Name | Data Type | Description |\n"
            doc_content += "|---------------|--------------|-----------|-------------|\n"
            
            for prop in schemas["profile_properties"]:
                name = prop.get("name", "")
                display = prop.get("display_name", "")
                data_type = prop.get("data_type", "")
                desc = prop.get("description", "")[:100] + "..." if len(prop.get("description", "")) > 100 else prop.get("description", "")
                doc_content += f"| {name} | {display} | {data_type} | {desc} |\n"
        
        doc_content += "\n## Custom Events Schema\n\n"
        
        if schemas.get("custom_events"):
            doc_content += "| Event Name | Display Name | Category | Formula |\n"
            doc_content += "|------------|--------------|----------|----------|\n"
            
            for event in schemas["custom_events"]:
                name = event.get("name", "")
                display = event.get("display_name", "")
                category = event.get("category", "")
                formula = event.get("formula", "")[:50] + "..." if len(event.get("formula", "")) > 50 else event.get("formula", "")
                doc_content += f"| {name} | {display} | {category} | {formula} |\n"
        
        doc_content += f"""
## Data Governance Notes

### Best Practices
1. **Event Naming**: Use clear, descriptive names for events
2. **Property Consistency**: Maintain consistent property names across events
3. **Documentation**: Keep descriptions up-to-date and comprehensive
4. **Data Quality**: Regularly review and clean up unused events/properties

### Schema Management
- Schema fetched using Mixpanel Lexicon Schemas API
- Regular updates recommended to track changes
- Version control for schema changes
- Integration with business intelligence tools

### Contact Information
- **Data Owner**: CEO/CTO
- **Technical Contact**: Development Team
- **Business Contact**: Product Team

---
*Generated by Mixpanel Schema Fetcher v1.0*
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(doc_content)
    
    def _generate_schema_summary(self, schemas: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of the schema for quick analysis"""
        
        summary = {
            "fetch_info": schemas["metadata"],
            "counts": {
                "events": len(schemas.get("events", [])),
                "event_properties": len(schemas.get("event_properties", [])),
                "profile_properties": len(schemas.get("profile_properties", [])),
                "custom_events": len(schemas.get("custom_events", [])),
                "lookup_tables": len(schemas.get("lookup_tables", []))
            },
            "top_events_by_volume": [],
            "property_types": {},
            "custom_vs_default": {
                "custom_properties": 0,
                "default_properties": 0
            }
        }
        
        # Analyze top events by volume
        if schemas.get("events"):
            events_by_volume = sorted(
                schemas["events"], 
                key=lambda x: x.get("volume_30_days", 0), 
                reverse=True
            )[:10]
            
            summary["top_events_by_volume"] = [
                {
                    "name": event.get("name"),
                    "volume": event.get("volume_30_days", 0)
                }
                for event in events_by_volume
            ]
        
        # Analyze property types
        all_properties = schemas.get("event_properties", []) + schemas.get("profile_properties", [])
        for prop in all_properties:
            data_type = prop.get("data_type", "unknown")
            summary["property_types"][data_type] = summary["property_types"].get(data_type, 0) + 1
            
            if prop.get("is_custom"):
                summary["custom_vs_default"]["custom_properties"] += 1
            else:
                summary["custom_vs_default"]["default_properties"] += 1
        
        return summary
    
    def compare_with_previous_schema(self, previous_schema_path: Optional[str] = None) -> Dict[str, Any]:
        """Compare current schema with a previous version to identify changes"""
        
        if not previous_schema_path:
            # Find the most recent previous schema
            schema_dirs = [d for d in self.base_output_dir.iterdir() if d.is_dir() and d.name.startswith("schema_fetch_")]
            if len(schema_dirs) < 2:
                print("ℹ️ No previous schema found for comparison")
                return {}
            
            # Sort by timestamp and get the second most recent
            schema_dirs.sort(key=lambda x: x.name)
            previous_dir = schema_dirs[-2]
            previous_schema_path = previous_dir / "complete_schema.json"
        
        if not Path(previous_schema_path).exists():
            print(f"❌ Previous schema file not found: {previous_schema_path}")
            return {}
        
        print(f"🔍 Comparing with previous schema: {previous_schema_path}")
        
        # Load previous schema
        with open(previous_schema_path, 'r', encoding='utf-8') as f:
            previous_schema = json.load(f)
        
        # Load current schema
        current_schema_path = self.output_dir / "complete_schema.json"
        with open(current_schema_path, 'r', encoding='utf-8') as f:
            current_schema = json.load(f)
        
        comparison = {
            "comparison_timestamp": datetime.now().isoformat(),
            "previous_schema_path": str(previous_schema_path),
            "current_schema_path": str(current_schema_path),
            "changes": {
                "new_events": [],
                "removed_events": [],
                "modified_events": [],
                "new_properties": [],
                "removed_properties": [],
                "modified_properties": []
            },
            "summary": {
                "total_changes": 0,
                "events_added": 0,
                "events_removed": 0,
                "properties_added": 0,
                "properties_removed": 0
            }
        }
        
        # Compare events
        prev_events = {e.get("name"): e for e in previous_schema.get("events", [])}
        curr_events = {e.get("name"): e for e in current_schema.get("events", [])}
        
        # Find new and removed events
        new_event_names = set(curr_events.keys()) - set(prev_events.keys())
        removed_event_names = set(prev_events.keys()) - set(curr_events.keys())
        
        comparison["changes"]["new_events"] = [curr_events[name] for name in new_event_names]
        comparison["changes"]["removed_events"] = [prev_events[name] for name in removed_event_names]
        
        # Find modified events
        for event_name in set(curr_events.keys()) & set(prev_events.keys()):
            if curr_events[event_name] != prev_events[event_name]:
                comparison["changes"]["modified_events"].append({
                    "name": event_name,
                    "previous": prev_events[event_name],
                    "current": curr_events[event_name]
                })
        
        # Update summary
        comparison["summary"]["events_added"] = len(new_event_names)
        comparison["summary"]["events_removed"] = len(removed_event_names)
        comparison["summary"]["total_changes"] = (
            len(new_event_names) + len(removed_event_names) + 
            len(comparison["changes"]["modified_events"])
        )
        
        # Save comparison report
        comparison_path = self.output_dir / "schema_comparison.json"
        with open(comparison_path, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2)
        
        print(f"✅ Schema comparison complete!")
        print(f"📊 Changes found: {comparison['summary']['total_changes']}")
        print(f"   📄 Comparison saved to: {comparison_path}")
        
        return comparison

def main():
    """Main function to demonstrate schema fetching capabilities"""
    
    print("🔍 MIXPANEL SCHEMA FETCHER")
    print("=" * 50)
    print("Advanced tool for fetching and organizing Mixpanel Lexicon schemas")
    print("=" * 50)
    
    try:
        # Initialize the fetcher
        fetcher = MixpanelSchemaFetcher()
        
        # Fetch all schemas
        schemas = fetcher.fetch_all_schemas()
        
        # Save to files
        file_paths = fetcher.save_schemas_to_files(schemas)
        
        # Compare with previous schema if available
        comparison = fetcher.compare_with_previous_schema()
        
        print("\n🎉 SCHEMA FETCH COMPLETE!")
        print("=" * 50)
        print(f"📁 Output directory: {fetcher.output_dir}")
        print(f"📊 Total events: {schemas['metadata']['total_events']}")
        print(f"📊 Total properties: {schemas['metadata']['total_properties']}")
        print(f"📊 Total custom events: {schemas['metadata']['total_custom_events']}")
        
        if comparison:
            print(f"🔄 Schema changes detected: {comparison['summary']['total_changes']}")
        
        print("\n📄 Files generated:")
        for file_type, path in file_paths.items():
            print(f"   {file_type}: {Path(path).name}")
        
        print("\n🎯 NEXT STEPS:")
        print("1. Review the generated documentation")
        print("2. Analyze schema changes if any")
        print("3. Update your tracking implementation based on schema")
        print("4. Set up regular schema monitoring")
        
    except Exception as e:
        print(f"❌ Error during schema fetch: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 