# HubSpot Pagination Standards & Best Practices

## 🚨 CRITICAL REQUIREMENT: Complete Data Retrieval

**⚠️ ALL HubSpot data retrieval MUST use complete pagination to ensure no data is missed**

This document establishes the standard methodology for retrieving ALL records from HubSpot APIs, regardless of dataset size.

---

## 📋 Pagination Standards

### ✅ CORRECT: Complete Pagination Implementation

**HubSpot API Pagination Rules:**
- **Maximum per page**: 100 records (API limit)
- **Pagination method**: `after` cursor-based pagination
- **Complete retrieval**: Continue until no more pages available
- **No arbitrary limits**: Never cap at 100 records unless explicitly requested

### ❌ INCORRECT: Limited Retrieval (What NOT to do)

```python
# ❌ WRONG: This only gets first 100 records
response = mcp_hubspot_search_objects(
    objectType="contacts",
    limit=100,
    # Missing pagination logic
)
contacts = response.results  # Only first 100!
```

---

## 🔧 Standard Pagination Implementation

### Method 1: Using MCP HubSpot Tools

```python
def fetch_all_hubspot_records_mcp(object_type, filters=None, properties=None):
    """Fetch ALL records using MCP HubSpot tools with complete pagination"""
    
    all_records = []
    after_cursor = None
    page = 1
    
    print(f"🔍 Starting {object_type} retrieval...")
    
    while True:
        # Prepare search parameters
        search_params = {
            "objectType": object_type,
            "limit": 100,  # Maximum allowed by API
            "properties": properties or []
        }
        
        if filters:
            search_params["filterGroups"] = filters
            
        if after_cursor:
            search_params["after"] = after_cursor
            
        print(f"📄 Fetching page {page}...")
        
        try:
            # Use MCP tool
            response = mcp_hubspot_search_objects(**search_params)
            
            records = response.get("results", [])
            
            if not records:
                print(f"✅ No more records found. Total retrieved: {len(all_records)}")
                break
                
            all_records.extend(records)
            print(f"   📊 Retrieved {len(records)} records (Total: {len(all_records)})")
            
            # Check for pagination
            paging = response.get("paging", {})
            after_cursor = paging.get("next", {}).get("after")
            
            if not after_cursor:
                print(f"✅ All records retrieved. Total: {len(all_records)}")
                break
                
            page += 1
            
        except Exception as e:
            print(f"❌ Error fetching records: {e}")
            break
    
    return all_records
```

### Method 2: Using Direct HubSpot API

```python
import requests
import time

def fetch_all_hubspot_records_api(object_type, access_token, filters=None, properties=None):
    """Fetch ALL records using direct HubSpot API with complete pagination"""
    
    url = f"https://api.hubapi.com/crm/v3/objects/{object_type}/search"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    all_records = []
    after_cursor = None
    page = 1
    
    print(f"🔍 Starting {object_type} retrieval...")
    
    while True:
        # Prepare search payload
        search_payload = {
            "limit": 100,  # Maximum allowed by API
            "properties": properties or []
        }
        
        if filters:
            search_payload["filterGroups"] = filters
            
        if after_cursor:
            search_payload["after"] = after_cursor
            
        print(f"📄 Fetching page {page}...")
        
        try:
            response = requests.post(url, headers=headers, json=search_payload)
            response.raise_for_status()
            
            data = response.json()
            records = data.get("results", [])
            
            if not records:
                print(f"✅ No more records found. Total retrieved: {len(all_records)}")
                break
                
            all_records.extend(records)
            print(f"   📊 Retrieved {len(records)} records (Total: {len(all_records)})")
            
            # Check for pagination
            paging = data.get("paging", {})
            after_cursor = paging.get("next", {}).get("after")
            
            if not after_cursor:
                print(f"✅ All records retrieved. Total: {len(all_records)}")
                break
                
            page += 1
            time.sleep(0.1)  # Rate limiting
            
        except requests.RequestException as e:
            print(f"❌ Error fetching records: {e}")
            break
    
    return all_records
```

---

## 📊 Standard Analysis Scripts

### Complete Contacts Analysis

```python
#!/usr/bin/env python3
"""
Complete HubSpot Contacts Analysis with Full Pagination
Retrieves ALL contacts for specified date range
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any

def analyze_contacts_by_date_range(start_date: str, end_date: str):
    """Analyze ALL contacts created in date range"""
    
    # Date filters
    filters = [{
        "filters": [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00.000Z"},
            {"propertyName": "createdate", "operator": "LTE", "value": f"{end_date}T23:59:59.999Z"}
        ]
    }]
    
    # Properties to retrieve
    properties = [
        "email", "firstname", "lastname", "company", "lifecyclestage", 
        "createdate", "utm_campaign", "utm_source", "utm_medium", 
        "utm_term", "utm_content", "activo", "fecha_activo", 
        "num_associated_deals", "hs_lead_status", "hs_analytics_source"
    ]
    
    # Fetch ALL contacts with pagination
    contacts = fetch_all_hubspot_records_mcp(
        object_type="contacts",
        filters=filters,
        properties=properties
    )
    
    print(f"\n📊 ANALYSIS RESULTS")
    print(f"Total Contacts Retrieved: {len(contacts):,}")
    print(f"Date Range: {start_date} to {end_date}")
    
    # Perform analysis...
    return contacts

# Usage
if __name__ == "__main__":
    contacts = analyze_contacts_by_date_range("2025-08-01", "2025-08-31")
```

### Complete Deals Analysis

```python
#!/usr/bin/env python3
"""
Complete HubSpot Deals Analysis with Full Pagination
Retrieves ALL deals for specified date range
"""

def analyze_deals_by_date_range(start_date: str, end_date: str):
    """Analyze ALL deals created in date range"""
    
    # Date filters
    filters = [{
        "filters": [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00.000Z"},
            {"propertyName": "createdate", "operator": "LTE", "value": f"{end_date}T23:59:59.999Z"}
        ]
    }]
    
    # Properties to retrieve
    properties = [
        "dealname", "dealstage", "amount", "closedate", "createdate",
        "pipeline", "dealtype", "hs_analytics_source", "description",
        "hubspot_owner_id", "hs_deal_stage_probability"
    ]
    
    # Fetch ALL deals with pagination
    deals = fetch_all_hubspot_records_mcp(
        object_type="deals",
        filters=filters,
        properties=properties
    )
    
    print(f"\n📊 ANALYSIS RESULTS")
    print(f"Total Deals Retrieved: {len(deals):,}")
    print(f"Date Range: {start_date} to {end_date}")
    
    # Perform analysis...
    return deals
```

### Complete Companies Analysis

```python
#!/usr/bin/env python3
"""
Complete HubSpot Companies Analysis with Full Pagination
Retrieves ALL companies for specified date range
"""

def analyze_companies_by_date_range(start_date: str, end_date: str):
    """Analyze ALL companies created in date range"""
    
    # Date filters
    filters = [{
        "filters": [
            {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00.000Z"},
            {"propertyName": "createdate", "operator": "LTE", "value": f"{end_date}T23:59:59.999Z"}
        ]
    }]
    
    # Properties to retrieve
    properties = [
        "name", "domain", "industry", "createdate", "lifecyclestage",
        "num_associated_deals", "hs_analytics_source", "city", "state",
        "country", "phone", "website", "description", "annualrevenue",
        "numberofemployees", "type"
    ]
    
    # Fetch ALL companies with pagination
    companies = fetch_all_hubspot_records_mcp(
        object_type="companies",
        filters=filters,
        properties=properties
    )
    
    print(f"\n📊 ANALYSIS RESULTS")
    print(f"Total Companies Retrieved: {len(companies):,}")
    print(f"Date Range: {start_date} to {end_date}")
    
    # Perform analysis...
    return companies
```

---

## 🎯 Usage Guidelines

### For Any Time Period Analysis

**Always use this pattern:**

1. **Define date range** (start_date, end_date)
2. **Set up filters** with proper date formatting
3. **Use complete pagination** (never limit to 100)
4. **Report total records** retrieved
5. **Save raw data** for future reference

### Example: Monthly Analysis

```python
# ✅ CORRECT: Complete monthly analysis
def analyze_month(year: int, month: int):
    """Analyze complete month with full pagination"""
    
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-31"
    
    print(f"📅 Analyzing {year}-{month:02d} (Complete Dataset)")
    
    # Get ALL contacts
    contacts = analyze_contacts_by_date_range(start_date, end_date)
    
    # Get ALL deals  
    deals = analyze_deals_by_date_range(start_date, end_date)
    
    # Get ALL companies
    companies = analyze_companies_by_date_range(start_date, end_date)
    
    print(f"\n📊 COMPLETE DATASET SUMMARY")
    print(f"Contacts: {len(contacts):,}")
    print(f"Deals: {len(deals):,}")
    print(f"Companies: {len(companies):,}")
    
    return contacts, deals, companies

# Usage
contacts, deals, companies = analyze_month(2025, 8)
```

---

## 📋 Quality Assurance Checklist

Before running any HubSpot analysis, verify:

☐ **Complete Pagination Implemented**
  - Uses `while True` loop with pagination
  - Continues until `after_cursor` is None
  - Reports total records retrieved

☐ **No Arbitrary Limits**
  - Never caps at 100 records unless explicitly requested
  - Uses API maximum (100) per page, not total limit

☐ **Proper Date Filtering**
  - Uses correct date format for API
  - Includes timezone information (T00:00:00.000Z)
  - Covers complete date range

☐ **Data Verification**
  - Reports actual record counts from API
  - Saves raw data for audit trail
  - Documents any missing or null data

☐ **Error Handling**
  - Handles API rate limits gracefully
  - Includes retry logic for failed requests
  - Reports errors without stopping analysis

---

## 🚨 Common Mistakes to Avoid

### ❌ Mistake 1: Single Page Retrieval
```python
# ❌ WRONG: Only gets first 100 records
contacts = mcp_hubspot_search_objects(objectType="contacts", limit=100)
```

### ❌ Mistake 2: Hard-coded Limits
```python
# ❌ WRONG: Arbitrary limit
contacts = fetch_contacts(limit=500)  # What if there are 1000+?
```

### ❌ Mistake 3: Missing Pagination Logic
```python
# ❌ WRONG: No pagination handling
response = api_call()
all_data = response.results  # Only first page!
```

### ✅ Correct Approach
```python
# ✅ CORRECT: Complete pagination
all_data = fetch_all_records_with_pagination()
print(f"Retrieved {len(all_data):,} total records")
```

---

## 📊 Reporting Standards

### Always Include in Analysis Output:

1. **Total Records Retrieved**: Exact count from API
2. **Date Range**: Start and end dates analyzed
3. **Pagination Status**: "Complete dataset retrieved"
4. **Data Quality**: Any missing or null data noted
5. **Raw Data Location**: Where complete dataset is saved

### Example Output Format:

```
📊 HUBSPOT ANALYSIS RESULTS
============================
Date Range: 2025-08-01 to 2025-08-31
Pagination: Complete dataset retrieved

📈 DATASET SUMMARY:
• Contacts: 1,115 (100% complete)
• Deals: 110 (100% complete)  
• Companies: 1,032 (100% complete)

💾 Raw Data Saved: hubspot_august_2025_complete_20250908_204500.json
```

---

## 🔧 Implementation Requirements

**All HubSpot analysis scripts MUST:**

1. **Use complete pagination** (never limit to 100 records)
2. **Report total records** retrieved from API
3. **Handle pagination errors** gracefully
4. **Save raw data** for audit trail
5. **Document methodology** used
6. **Follow Argentina formatting** standards
7. **Include data quality checks**

**Script Template:**
```python
def analyze_hubspot_data(start_date, end_date):
    """Complete HubSpot analysis with full pagination"""
    
    # 1. Set up filters and properties
    # 2. Use complete pagination function
    # 3. Perform analysis on ALL data
    # 4. Report total records retrieved
    # 5. Save raw data
    # 6. Return results
    
    pass
```

---

## 📚 References

- **HubSpot API Documentation**: [Search API](https://developers.hubspot.com/docs/api/crm/search)
- **Pagination Guide**: [Cursor-based pagination](https://developers.hubspot.com/docs/api/crm/search#cursor-based-pagination)
- **Rate Limits**: [API Rate Limits](https://developers.hubspot.com/docs/api/rate-limits)
- **Colppy HubSpot Config**: `tools/docs/README_HUBSPOT_CONFIGURATION.md`

---

**⚠️ REMEMBER: Complete data retrieval is critical for accurate business analysis. Never compromise on pagination completeness.**
