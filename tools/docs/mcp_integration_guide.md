# 🔧 MCP Tools Integration Guide for CEO Assistant

## 🎯 Overview

You already have powerful MCP (Model Context Protocol) tools for HubSpot, Mixpanel, and Intercom data. This guide shows you how to integrate them with your CEO assistant for real business insights.

## 🛠 Your Existing MCP Tools

Based on the available tools, you have access to:

### **HubSpot MCP Tools** 🏢
- `mcp_hubspot_hubspot-get-user-details` - Get your HubSpot account info
- `mcp_hubspot_hubspot-list-objects` - List contacts, deals, companies, etc.
- `mcp_hubspot_hubspot-search-objects` - Advanced filtering and search
- `mcp_hubspot_hubspot-batch-read-objects` - Bulk data retrieval
- `mcp_hubspot_hubspot-create-engagement` - Add notes and tasks
- `mcp_hubspot_hubspot-list-associations` - Relationship mapping

### **Mixpanel MCP Tools** 📊
- `mcp_mixpanel_get_top_events` - Most common user actions
- `mcp_mixpanel_aggregate_event_counts` - Event trends over time
- `mcp_mixpanel_query_retention_report` - User retention analysis
- `mcp_mixpanel_query_funnel_report` - Conversion funnel data
- `mcp_mixpanel_query_segmentation_report` - User behavior segments
- `mcp_mixpanel_profile_event_activity` - Individual user journeys

### **Intercom Data** 💬
- Your `intercom-export` folder (456.9 MB, 722 items)
- Customer conversations and support data
- User satisfaction and resolution metrics

## 🚀 Step-by-Step Integration

### Step 1: Replace Mock Data with Real MCP Calls

Let me show you how to replace the placeholder methods in `MCPDataConnector`:

```python
class RealMCPConnector:
    """Real connector using your actual MCP tools"""
    
    def __init__(self):
        # Initialize MCP connections
        self.hubspot_available = True
        self.mixpanel_available = True
        self.intercom_available = True
    
    def get_hubspot_user_details(self) -> Dict:
        """Get real HubSpot user details"""
        try:
            # Call your actual MCP tool
            result = mcp_hubspot_hubspot_get_user_details(random_string="init")
            return result
        except Exception as e:
            logger.error(f"HubSpot user details error: {e}")
            return {"error": str(e)}
    
    def get_hubspot_deals_data(self, limit: int = 100) -> Dict:
        """Get real deals data from HubSpot"""
        try:
            # Call your MCP tool to list deals
            result = mcp_hubspot_hubspot_list_objects(
                objectType="deals",
                limit=limit,
                properties=["dealname", "amount", "dealstage", "closedate", "createdate"]
            )
            return result
        except Exception as e:
            logger.error(f"HubSpot deals error: {e}")
            return {"error": str(e)}
    
    def get_hubspot_contacts_metrics(self) -> Dict:
        """Get contact metrics using HubSpot search"""
        try:
            # Get total contacts
            all_contacts = mcp_hubspot_hubspot_list_objects(
                objectType="contacts",
                limit=100
            )
            
            # Get new contacts this month
            from datetime import datetime, timedelta
            month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
            
            new_contacts = mcp_hubspot_hubspot_search_objects(
                objectType="contacts",
                filterGroups=[{
                    "filters": [{
                        "propertyName": "createdate",
                        "operator": "GTE",
                        "value": month_start
                    }]
                }]
            )
            
            return {
                "total_contacts": len(all_contacts.get("results", [])),
                "new_contacts_this_month": len(new_contacts.get("results", [])),
                "qualified_leads": 0,  # Calculate based on your lead scoring
                "customers": 0  # Calculate based on your customer definition
            }
        except Exception as e:
            logger.error(f"HubSpot contacts metrics error: {e}")
            return {"error": str(e)}
    
    def get_mixpanel_top_events(self, limit: int = 10) -> Dict:
        """Get real top events from Mixpanel"""
        try:
            result = mcp_mixpanel_get_top_events(
                limit=limit,
                type="general"
            )
            return result
        except Exception as e:
            logger.error(f"Mixpanel top events error: {e}")
            return {"error": str(e)}
    
    def get_mixpanel_user_engagement(self, from_date: str, to_date: str) -> Dict:
        """Get real user engagement from Mixpanel"""
        try:
            # Get DAU/WAU/MAU data
            engagement = mcp_mixpanel_aggregate_event_counts(
                event='["User Login"]',  # Adjust to your actual login event
                from_date=from_date,
                to_date=to_date,
                unit="day"
            )
            
            # Get retention data
            retention = mcp_mixpanel_query_retention_report(
                from_date=from_date,
                to_date=to_date,
                born_event="User Signup",  # Adjust to your signup event
                unit="day"
            )
            
            return {
                "daily_active_users": engagement.get("data", {}).get("values", {}).get("User Login", [0])[-1],
                "weekly_active_users": 0,  # Calculate from daily data
                "monthly_active_users": 0,  # Calculate from daily data
                "retention_d7": retention.get("data", {}).get("7", 0),
                "retention_d30": retention.get("data", {}).get("30", 0)
            }
        except Exception as e:
            logger.error(f"Mixpanel engagement error: {e}")
            return {"error": str(e)}
    
    def get_mixpanel_conversion_funnel(self, funnel_id: str = None) -> Dict:
        """Get real conversion funnel from Mixpanel"""
        try:
            if funnel_id:
                # Use saved funnel
                result = mcp_mixpanel_query_funnel_report(
                    funnel_id=funnel_id,
                    from_date="2024-11-01",
                    to_date="2024-11-30"
                )
            else:
                # Get list of available funnels first
                funnels = mcp_mixpanel_list_saved_funnels()
                if funnels.get("results"):
                    funnel_id = funnels["results"][0]["id"]
                    result = mcp_mixpanel_query_funnel_report(
                        funnel_id=funnel_id,
                        from_date="2024-11-01", 
                        to_date="2024-11-30"
                    )
                else:
                    result = {"error": "No funnels found"}
            
            return result
        except Exception as e:
            logger.error(f"Mixpanel funnel error: {e}")
            return {"error": str(e)}
    
    def load_intercom_data(self, data_type: str = "conversations") -> pd.DataFrame:
        """Load real Intercom export data"""
        try:
            # Path to your intercom-export folder
            import os
            intercom_path = "/Users/virulana/Downloads/intercom-export"
            
            if data_type == "conversations":
                # Look for conversation files
                conv_files = [f for f in os.listdir(intercom_path) if "conversation" in f.lower()]
                if conv_files:
                    # Load the first conversation file (adjust as needed)
                    file_path = os.path.join(intercom_path, conv_files[0])
                    if file_path.endswith('.csv'):
                        return pd.read_csv(file_path)
                    elif file_path.endswith('.json'):
                        return pd.read_json(file_path)
            
            elif data_type == "customers":
                # Look for customer/user files
                user_files = [f for f in os.listdir(intercom_path) if any(term in f.lower() for term in ["user", "customer", "contact"])]
                if user_files:
                    file_path = os.path.join(intercom_path, user_files[0])
                    if file_path.endswith('.csv'):
                        return pd.read_csv(file_path)
                    elif file_path.endswith('.json'):
                        return pd.read_json(file_path)
            
            return pd.DataFrame()  # Return empty if no data found
            
        except Exception as e:
            logger.error(f"Error loading Intercom data: {e}")
            return pd.DataFrame()
```

### Step 2: Update Your CEO Assistant

Replace the `MCPDataConnector` in `ceo_assistant_enhanced.py` with the `RealMCPConnector` above.

### Step 3: Configure Your Specific Events and Properties

#### For Mixpanel:
1. **Identify your key events** (replace the examples):
   ```python
   # Common Colppy events might be:
   - "Invoice Created"
   - "Payment Processed" 
   - "Report Generated"
   - "User Login"
   - "Feature Used"
   - "Trial Started"
   - "Subscription Upgraded"
   ```

2. **Update funnel steps** for your conversion flow:
   ```python
   # Typical SaaS B2B funnel for Colppy:
   - "Trial Signup" 
   - "First Invoice Created"
   - "Payment Method Added"
   - "Subscription Activated"
   ```

#### For HubSpot:
1. **Map your custom properties**:
   ```python
   # Colppy-specific properties might include:
   - "company_size" 
   - "industry_type"
   - "accountant_partner"
   - "plan_type"
   - "mrr_value"
   ```

2. **Define your lead stages**:
   ```python
   # Your lead lifecycle stages:
   - "subscriber" (trial user)
   - "lead" (engaged trial user)
   - "marketing_qualified_lead"
   - "sales_qualified_lead" 
   - "customer"
   ```

### Step 4: Explore Your Intercom Data

Let's see what's in your intercom-export folder:

```python
import os
import pandas as pd

def explore_intercom_export():
    """Explore your Intercom export data"""
    intercom_path = "/Users/virulana/Downloads/intercom-export"
    
    print("=== Intercom Export Contents ===")
    for file in os.listdir(intercom_path)[:10]:  # Show first 10 files
        file_path = os.path.join(intercom_path, file)
        file_size = os.path.getsize(file_path) / 1024 / 1024  # MB
        print(f"📄 {file} ({file_size:.1f} MB)")
    
    # Try to load and preview a few files
    csv_files = [f for f in os.listdir(intercom_path) if f.endswith('.csv')]
    
    for csv_file in csv_files[:3]:  # Preview first 3 CSV files
        try:
            df = pd.read_csv(os.path.join(intercom_path, csv_file))
            print(f"\n=== {csv_file} Preview ===")
            print(f"Rows: {len(df)}, Columns: {len(df.columns)}")
            print("Columns:", list(df.columns))
            print(df.head(2))
        except Exception as e:
            print(f"Error reading {csv_file}: {e}")

# Run this to understand your data structure
explore_intercom_export()
```

## 🎯 Practical Implementation Steps

### Week 1: Basic Integration
1. **Test MCP connections**:
   ```bash
   python -c "from ceo_assistant_enhanced import RealMCPConnector; conn = RealMCPConnector(); print(conn.get_hubspot_user_details())"
   ```

2. **Verify data access**:
   - Check HubSpot permissions
   - Confirm Mixpanel project access
   - Explore Intercom export structure

### Week 2: Data Mapping
1. **Map your specific events and properties**
2. **Create custom metrics calculations**
3. **Test with real data**

### Week 3: Enhanced Analytics
1. **Build custom dashboards**
2. **Create automated reports**
3. **Set up alerts and notifications**

## 🔍 Key Insights You'll Get

### Strategic Insights:
- **Growth Opportunities**: Based on real conversion funnel data
- **Customer Segments**: Using Mixpanel cohort analysis
- **Pipeline Health**: From HubSpot deal progression
- **Support Efficiency**: From Intercom resolution times

### Operational Insights:
- **Product Usage Patterns**: Top features and user journeys
- **Sales Performance**: Deal velocity and win rates
- **Customer Health**: Satisfaction scores and churn indicators
- **Team Productivity**: Response times and resolution rates

## 🚨 Important Notes

1. **Data Privacy**: Ensure compliance with your data policies
2. **Rate Limits**: Be mindful of API rate limits for HubSpot and Mixpanel
3. **Error Handling**: Implement robust error handling for API failures
4. **Caching**: Consider caching frequently accessed data

## 🎓 Next Steps

1. **Start with one data source** (recommend HubSpot first)
2. **Test with small data sets** before full integration
3. **Gradually add more sophisticated analytics**
4. **Build custom visualizations** for your specific KPIs

This integration will give you a powerful, data-driven CEO assistant that provides real insights from your actual business data! 🚀 