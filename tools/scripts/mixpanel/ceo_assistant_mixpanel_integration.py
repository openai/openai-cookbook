"""
🎯 CEO ASSISTANT MIXPANEL INTEGRATION
Advanced integration between CEO Assistant and Mixpanel schema/analytics

This module provides:
1. Schema-aware Mixpanel queries for the CEO Assistant
2. Business intelligence functions using real schema data
3. Automated insights and recommendations
4. Integration with existing MCP Mixpanel tools

Features:
- Real-time business metrics
- Schema-driven data analysis
- Executive dashboard capabilities
- Automated reporting and alerts
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

# Import our Mixpanel components
try:
    from .mixpanel_schema_fetcher import MixpanelSchemaFetcher
    from .mixpanel_mcp_integration import MixpanelMCPIntegration
except ImportError:
    # Fallback for direct execution
    from mixpanel_schema_fetcher import MixpanelSchemaFetcher
    from mixpanel_mcp_integration import MixpanelMCPIntegration

# Load environment variables
load_dotenv()

class CEOAssistantMixpanelIntegration:
    """
    Advanced Mixpanel integration for CEO Assistant
    
    Provides schema-aware business intelligence capabilities:
    - Executive dashboard metrics
    - Automated insights and recommendations
    - Schema-driven data analysis
    - Real-time business monitoring
    """
    
    def __init__(self, project_id: Optional[str] = None, workspace_id: Optional[str] = None):
        """Initialize the CEO Assistant Mixpanel integration"""
        
        self.project_id = project_id or os.getenv("MIXPANEL_PROJECT_ID", "2201475")
        self.workspace_id = workspace_id or os.getenv("MIXPANEL_WORKSPACE_ID")
        
        # Initialize components
        self.schema_fetcher = MixpanelSchemaFetcher(self.project_id, self.workspace_id)
        self.mcp_integration = MixpanelMCPIntegration(self.project_id, self.workspace_id)
        
        # Load latest schema if available
        self.current_schema = self._load_latest_schema()
        
        print(f"🎯 CEO Assistant Mixpanel Integration initialized")
        print(f"📊 Project ID: {self.project_id}")
        if self.workspace_id:
            print(f"🏢 Workspace ID: {self.workspace_id}")
    
    def _load_latest_schema(self) -> Optional[Dict[str, Any]]:
        """Load the most recent schema data"""
        
        try:
            schema_base_dir = Path("tools/outputs/csv_data/mixpanel/schemas")
            if not schema_base_dir.exists():
                return None
            
            # Find the most recent schema directory
            schema_dirs = [d for d in schema_base_dir.iterdir() if d.is_dir() and d.name.startswith("schema_fetch_")]
            if not schema_dirs:
                return None
            
            # Sort by timestamp and get the most recent
            latest_dir = sorted(schema_dirs, key=lambda x: x.name)[-1]
            schema_file = latest_dir / "complete_schema.json"
            
            if schema_file.exists():
                with open(schema_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            return None
            
        except Exception as e:
            print(f"⚠️ Could not load latest schema: {e}")
            return None
    
    def get_executive_dashboard(self, date_range_days: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive executive dashboard
        
        Returns key business metrics, insights, and recommendations
        """
        
        print(f"📊 Generating executive dashboard for last {date_range_days} days...")
        
        # Get business intelligence summary
        bi_summary = self.mcp_integration.get_business_intelligence_summary(date_range_days)
        
        # Enhance with schema information
        dashboard = {
            "executive_summary": {
                "period": bi_summary["period"],
                "key_metrics": bi_summary["key_metrics"],
                "top_events": bi_summary["top_events"],
                "event_categories": bi_summary["event_categories"]
            },
            "business_insights": {
                "insights": bi_summary["business_insights"],
                "recommendations": bi_summary["recommendations"],
                "schema_insights": self._generate_schema_insights()
            },
            "operational_metrics": self._calculate_operational_metrics(bi_summary),
            "growth_metrics": self._calculate_growth_metrics(bi_summary),
            "risk_indicators": self._identify_risk_indicators(bi_summary),
            "action_items": self._generate_action_items(bi_summary),
            "generated_at": datetime.now().isoformat()
        }
        
        return dashboard
    
    def _generate_schema_insights(self) -> List[str]:
        """Generate insights based on schema analysis"""
        
        insights = []
        
        if not self.current_schema:
            insights.append("Schema data not available - consider running schema fetch")
            return insights
        
        # Analyze schema completeness
        events_count = self.current_schema.get("metadata", {}).get("total_events", 0)
        properties_count = self.current_schema.get("metadata", {}).get("total_properties", 0)
        custom_events_count = self.current_schema.get("metadata", {}).get("total_custom_events", 0)
        
        insights.append(f"Data governance: {events_count} events, {properties_count} properties, {custom_events_count} custom metrics tracked")
        
        # Analyze property types
        event_properties = self.current_schema.get("event_properties", [])
        custom_properties = [p for p in event_properties if p.get("is_custom")]
        default_properties = [p for p in event_properties if not p.get("is_custom")]
        
        if custom_properties:
            insights.append(f"Custom tracking: {len(custom_properties)} business-specific properties defined")
        
        # Analyze custom events
        custom_events = self.current_schema.get("custom_events", [])
        if custom_events:
            categories = set(event.get("category", "other") for event in custom_events)
            insights.append(f"Advanced analytics: {len(custom_events)} custom metrics across {len(categories)} categories")
        
        return insights
    
    def _calculate_operational_metrics(self, bi_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate operational efficiency metrics"""
        
        top_events = bi_summary.get("top_events", [])
        
        # Find key operational events
        invoice_events = [e for e in top_events if "Invoice" in e["event"]]
        login_events = [e for e in top_events if "Login" in e["event"]]
        payment_events = [e for e in top_events if "Payment" in e["event"]]
        
        metrics = {
            "invoice_processing": {
                "total_invoices": invoice_events[0]["count"] if invoice_events else 0,
                "daily_average": (invoice_events[0]["count"] / 30) if invoice_events else 0
            },
            "user_engagement": {
                "total_logins": login_events[0]["count"] if login_events else 0,
                "daily_average": (login_events[0]["count"] / 30) if login_events else 0
            },
            "payment_processing": {
                "total_payments": payment_events[0]["count"] if payment_events else 0,
                "daily_average": (payment_events[0]["count"] / 30) if payment_events else 0
            }
        }
        
        # Calculate efficiency ratios
        if metrics["invoice_processing"]["total_invoices"] > 0 and metrics["payment_processing"]["total_payments"] > 0:
            metrics["payment_efficiency"] = {
                "payment_to_invoice_ratio": metrics["payment_processing"]["total_payments"] / metrics["invoice_processing"]["total_invoices"],
                "status": "healthy" if metrics["payment_processing"]["total_payments"] / metrics["invoice_processing"]["total_invoices"] > 0.5 else "needs_attention"
            }
        
        return metrics
    
    def _calculate_growth_metrics(self, bi_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate growth and acquisition metrics"""
        
        top_events = bi_summary.get("top_events", [])
        
        # Find growth-related events
        trial_events = [e for e in top_events if "Trial" in e["event"]]
        subscription_events = [e for e in top_events if "Subscription" in e["event"]]
        customer_events = [e for e in top_events if "Customer" in e["event"]]
        
        metrics = {
            "acquisition": {
                "new_trials": trial_events[0]["count"] if trial_events else 0,
                "new_subscriptions": subscription_events[0]["count"] if subscription_events else 0,
                "new_customers": customer_events[0]["count"] if customer_events else 0
            }
        }
        
        # Calculate conversion rates
        if metrics["acquisition"]["new_trials"] > 0 and metrics["acquisition"]["new_subscriptions"] > 0:
            conversion_rate = (metrics["acquisition"]["new_subscriptions"] / metrics["acquisition"]["new_trials"]) * 100
            metrics["conversion"] = {
                "trial_to_paid_rate": conversion_rate,
                "status": "excellent" if conversion_rate > 25 else "good" if conversion_rate > 15 else "needs_improvement"
            }
        
        return metrics
    
    def _identify_risk_indicators(self, bi_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify potential business risks from the data"""
        
        risks = []
        top_events = bi_summary.get("top_events", [])
        
        # Check for support ticket volume
        support_events = [e for e in top_events if "Support" in e["event"] or "Ticket" in e["event"]]
        if support_events:
            support_count = support_events[0]["count"]
            if support_count > 500:  # Threshold for concern
                risks.append({
                    "type": "customer_support",
                    "severity": "high" if support_count > 1000 else "medium",
                    "description": f"High support ticket volume: {support_count:,} tickets",
                    "recommendation": "Investigate common issues and improve product stability"
                })
        
        # Check trial conversion
        trial_events = [e for e in top_events if "Trial" in e["event"]]
        subscription_events = [e for e in top_events if "Subscription" in e["event"]]
        
        if trial_events and subscription_events:
            conversion_rate = (subscription_events[0]["count"] / trial_events[0]["count"]) * 100
            if conversion_rate < 15:
                risks.append({
                    "type": "conversion",
                    "severity": "high",
                    "description": f"Low trial conversion rate: {conversion_rate:.1f}%",
                    "recommendation": "Review onboarding process and trial experience"
                })
        
        # Check user engagement
        login_events = [e for e in top_events if "Login" in e["event"]]
        feature_events = [e for e in top_events if "Feature" in e["event"]]
        
        if login_events and feature_events:
            engagement_ratio = feature_events[0]["count"] / login_events[0]["count"]
            if engagement_ratio < 0.2:
                risks.append({
                    "type": "engagement",
                    "severity": "medium",
                    "description": f"Low feature usage per login: {engagement_ratio:.2f}",
                    "recommendation": "Improve feature discoverability and user education"
                })
        
        return risks
    
    def _generate_action_items(self, bi_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate specific action items for the CEO"""
        
        action_items = []
        top_events = bi_summary.get("top_events", [])
        
        # Revenue optimization actions
        invoice_events = [e for e in top_events if "Invoice" in e["event"]]
        if invoice_events:
            action_items.append({
                "category": "revenue_optimization",
                "priority": "high",
                "title": "Optimize Invoice Processing",
                "description": f"With {invoice_events[0]['count']:,} invoices created, focus on automation and efficiency",
                "timeline": "This quarter",
                "owner": "Product Team"
            })
        
        # Growth acceleration actions
        trial_events = [e for e in top_events if "Trial" in e["event"]]
        if trial_events:
            action_items.append({
                "category": "growth",
                "priority": "high",
                "title": "Improve Trial Conversion",
                "description": f"Optimize onboarding for {trial_events[0]['count']:,} trial users",
                "timeline": "Next 30 days",
                "owner": "Growth Team"
            })
        
        # Product development actions
        feature_events = [e for e in top_events if "Feature" in e["event"]]
        if feature_events:
            action_items.append({
                "category": "product",
                "priority": "medium",
                "title": "Analyze Feature Usage Patterns",
                "description": "Deep dive into feature adoption to guide roadmap",
                "timeline": "Next sprint",
                "owner": "Product Team"
            })
        
        # Data governance actions
        if self.current_schema:
            action_items.append({
                "category": "data_governance",
                "priority": "medium",
                "title": "Regular Schema Monitoring",
                "description": "Set up automated schema change tracking",
                "timeline": "This month",
                "owner": "Engineering Team"
            })
        
        return action_items
    
    def get_schema_summary(self) -> Dict[str, Any]:
        """Get a summary of the current Mixpanel schema"""
        
        if not self.current_schema:
            return {
                "status": "no_schema",
                "message": "No schema data available. Run schema fetch first.",
                "recommendation": "Execute: python run_schema_fetch.py"
            }
        
        metadata = self.current_schema.get("metadata", {})
        
        return {
            "status": "available",
            "fetch_timestamp": metadata.get("fetch_timestamp"),
            "statistics": {
                "total_events": metadata.get("total_events", 0),
                "total_properties": metadata.get("total_properties", 0),
                "total_custom_events": metadata.get("total_custom_events", 0),
                "profile_properties": len(self.current_schema.get("profile_properties", [])),
                "lookup_tables": len(self.current_schema.get("lookup_tables", []))
            },
            "data_quality": self._assess_data_quality(),
            "recommendations": self._get_schema_recommendations()
        }
    
    def _assess_data_quality(self) -> Dict[str, Any]:
        """Assess the quality of the current schema"""
        
        if not self.current_schema:
            return {"score": 0, "status": "no_data"}
        
        score = 0
        max_score = 100
        
        # Check event coverage
        events_count = self.current_schema.get("metadata", {}).get("total_events", 0)
        if events_count > 10:
            score += 25
        elif events_count > 5:
            score += 15
        elif events_count > 0:
            score += 10
        
        # Check property coverage
        properties_count = self.current_schema.get("metadata", {}).get("total_properties", 0)
        if properties_count > 15:
            score += 25
        elif properties_count > 10:
            score += 20
        elif properties_count > 5:
            score += 15
        
        # Check custom events
        custom_events_count = self.current_schema.get("metadata", {}).get("total_custom_events", 0)
        if custom_events_count > 5:
            score += 25
        elif custom_events_count > 3:
            score += 20
        elif custom_events_count > 0:
            score += 15
        
        # Check documentation completeness
        event_properties = self.current_schema.get("event_properties", [])
        documented_properties = [p for p in event_properties if p.get("description")]
        if event_properties and len(documented_properties) / len(event_properties) > 0.8:
            score += 25
        elif event_properties and len(documented_properties) / len(event_properties) > 0.5:
            score += 15
        
        status = "excellent" if score >= 80 else "good" if score >= 60 else "needs_improvement" if score >= 40 else "poor"
        
        return {
            "score": score,
            "max_score": max_score,
            "percentage": (score / max_score) * 100,
            "status": status
        }
    
    def _get_schema_recommendations(self) -> List[str]:
        """Get recommendations for improving the schema"""
        
        recommendations = []
        
        if not self.current_schema:
            recommendations.append("Run initial schema fetch to establish baseline")
            return recommendations
        
        # Check for missing custom events
        custom_events_count = self.current_schema.get("metadata", {}).get("total_custom_events", 0)
        if custom_events_count < 5:
            recommendations.append("Define more custom events for business KPIs (MAU, conversion rates, etc.)")
        
        # Check for business-specific properties
        event_properties = self.current_schema.get("event_properties", [])
        business_properties = [p for p in event_properties if p.get("is_custom")]
        if len(business_properties) < 5:
            recommendations.append("Add more business-specific properties (company_id, plan_type, etc.)")
        
        # Check documentation
        documented_properties = [p for p in event_properties if p.get("description")]
        if event_properties and len(documented_properties) / len(event_properties) < 0.8:
            recommendations.append("Improve property documentation for better data governance")
        
        # Check for lookup tables
        lookup_tables = self.current_schema.get("lookup_tables", [])
        if len(lookup_tables) < 3:
            recommendations.append("Create lookup tables for enriched analysis (company segments, plan features)")
        
        return recommendations
    
    def refresh_schema(self) -> Dict[str, Any]:
        """Refresh the schema data by fetching latest from Mixpanel"""
        
        print("🔄 Refreshing Mixpanel schema...")
        
        try:
            # Fetch new schema
            new_schema = self.schema_fetcher.fetch_all_schemas()
            
            # Save to files
            file_paths = self.schema_fetcher.save_schemas_to_files(new_schema)
            
            # Compare with previous if available
            comparison = self.schema_fetcher.compare_with_previous_schema()
            
            # Update current schema
            self.current_schema = new_schema
            
            return {
                "status": "success",
                "schema_updated": True,
                "files_generated": len(file_paths),
                "changes_detected": len(comparison.get("changes", {}).get("new_events", [])) if comparison else 0,
                "output_directory": str(self.schema_fetcher.output_dir),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "schema_updated": False,
                "timestamp": datetime.now().isoformat()
            }

def main():
    """Demonstrate the CEO Assistant Mixpanel integration"""
    
    print("🎯 CEO ASSISTANT MIXPANEL INTEGRATION DEMO")
    print("=" * 60)
    
    try:
        # Initialize integration
        integration = CEOAssistantMixpanelIntegration()
        
        # Get executive dashboard
        print("\n📊 EXECUTIVE DASHBOARD")
        print("=" * 30)
        
        dashboard = integration.get_executive_dashboard()
        
        # Display key metrics
        print(f"📅 Period: {dashboard['executive_summary']['period']['start_date']} to {dashboard['executive_summary']['period']['end_date']}")
        print(f"📈 Total Events: {dashboard['executive_summary']['key_metrics']['total_events']:,}")
        print(f"⚡ Daily Average: {dashboard['executive_summary']['key_metrics']['avg_events_per_day']:.0f}")
        
        # Display top events
        print("\n🔥 TOP BUSINESS EVENTS:")
        for i, event in enumerate(dashboard['executive_summary']['top_events'], 1):
            print(f"  {i}. {event['event']}: {event['count']:,}")
        
        # Display insights
        print("\n💡 BUSINESS INSIGHTS:")
        for insight in dashboard['business_insights']['insights']:
            print(f"  • {insight}")
        
        # Display schema insights
        print("\n🔍 SCHEMA INSIGHTS:")
        for insight in dashboard['business_insights']['schema_insights']:
            print(f"  • {insight}")
        
        # Display recommendations
        print("\n🎯 RECOMMENDATIONS:")
        for rec in dashboard['business_insights']['recommendations']:
            print(f"  → {rec}")
        
        # Display risk indicators
        if dashboard['risk_indicators']:
            print("\n⚠️ RISK INDICATORS:")
            for risk in dashboard['risk_indicators']:
                print(f"  🚨 {risk['type'].upper()}: {risk['description']}")
                print(f"     → {risk['recommendation']}")
        
        # Display action items
        print("\n📋 ACTION ITEMS:")
        for action in dashboard['action_items']:
            priority_emoji = "🔴" if action['priority'] == 'high' else "🟡" if action['priority'] == 'medium' else "🟢"
            print(f"  {priority_emoji} {action['title']} ({action['owner']})")
            print(f"     {action['description']}")
            print(f"     Timeline: {action['timeline']}")
        
        # Get schema summary
        print("\n🔍 SCHEMA SUMMARY")
        print("=" * 25)
        
        schema_summary = integration.get_schema_summary()
        
        if schema_summary['status'] == 'available':
            stats = schema_summary['statistics']
            quality = schema_summary['data_quality']
            
            print(f"📊 Events: {stats['total_events']}")
            print(f"📊 Properties: {stats['total_properties']}")
            print(f"📊 Custom Events: {stats['total_custom_events']}")
            print(f"📊 Data Quality: {quality['percentage']:.1f}% ({quality['status']})")
            
            if schema_summary['recommendations']:
                print("\n📝 SCHEMA RECOMMENDATIONS:")
                for rec in schema_summary['recommendations']:
                    print(f"  → {rec}")
        else:
            print(f"⚠️ {schema_summary['message']}")
            print(f"💡 {schema_summary['recommendation']}")
        
        print("\n🎉 INTEGRATION DEMO COMPLETE!")
        print("=" * 60)
        print("Your CEO Assistant now has advanced Mixpanel capabilities!")
        
    except Exception as e:
        print(f"❌ Error in integration demo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 