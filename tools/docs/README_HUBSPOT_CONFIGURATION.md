# Colppy HubSpot Configuration Documentation

This document serves as the official reference for Colppy's HubSpot configuration, mapping the customer journey from lead to deal.

## 🔍 LIVE CRM FIELD VERIFICATION STATUS
**✅ Last Verified**: August 1, 2025 via Live HubSpot API  
**📊 Verification Coverage**: Products, Line Items, Companies, Deals, Contacts  
**📝 Documentation Status**: All field mappings verified through direct API calls

**What Was Verified:**
- ✅ All subscription fields in Line Items object (MRR, ARR, billing dates)
- ✅ Product Family classification system (Colppy vs Sueldos)  
- ✅ Company CUIT fields (tax identification) and 12 company types
- ✅ Deal custom fields (plan names, accountant associations)
- ✅ Association mappings for accountant channel tracking
- ✅ Contact fields for key events and lifecycle tracking

## CRITICAL INSTRUCTION: Field Name Mapping

**⚠️ ALWAYS map UI field names to internal property names when working with HubSpot data**

When referencing HubSpot fields, you MUST:
1. **Identify the internal property name** used in API calls (e.g., `fecha_activo`)
2. **Document both the UI label and internal name** for clarity
3. **Use the internal property name** in all API requests and scripts
4. **Verify field names exist** before running analysis scripts

**Field Name Format:**
- UI Name: "Fecha de Hizo Evento Clave en Trial" 
- Internal Name: `fecha_activo` (this is what you use in API calls)

This prevents field mapping errors that invalidate entire analyses.

---

## 🎯 HUBSPOT OBJECT FIELD MAPPING - LIVE VERIFIED

**✅ VERIFIED VIA LIVE HUBSPOT API - August 1, 2025**

This section documents the exact field mappings for each HubSpot object, verified through direct API calls to ensure 100% accuracy for integrations and analysis.

### 📦 **PRODUCTS OBJECT**
**Access**: Settings → Objects → Products → Properties

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Product Family** | `product_family` | Select/Enumeration | ✅ **CONFIGURED** | Colppy vs Sueldos classification |
| Name | `name` | String | ✅ Native | Product identification |
| Price | `price` | Number | ✅ Native | Product pricing |

**Product Family Options (Live Verified)**:
- `Colppy (Financial Management)` → **19 products classified**
- `Sueldos (Payroll Processing)` → **32 products classified**

---

### 📊 **LINE ITEMS OBJECT**
**Access**: Settings → Objects → Line Items → Properties  
**Relationship**: Line Items belong to Deals (Deal → Line Items)

#### **🔵 Subscription Revenue Fields (Native HubSpot)**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Monthly recurring revenue** | `hs_mrr` | Number | ✅ **LIVE VERIFIED** | Monthly recurring revenue tracking |
| **Annual recurring revenue** | `hs_arr` | Number | ✅ **LIVE VERIFIED** | Annual recurring revenue tracking |
| **Billing start date** | `hs_recurring_billing_start_date` | Date | ✅ **LIVE VERIFIED** | Subscription start date |
| **Billing end date** | `hs_recurring_billing_end_date` | Date | ✅ **LIVE VERIFIED** | Subscription end date |
| **Discount percentage** | `hs_discount_percentage` | Number | ✅ **LIVE VERIFIED** | Applied discount rate |
| **Product** | `hs_product_id` | String | ✅ **LIVE VERIFIED** | Reference to Products object |
| Quantity | `quantity` | Number | ✅ Native | Line item quantity |
| Amount | `amount` | Number | ✅ Native | Line item total amount |

#### **🟢 Additional Discovered Fields**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Subscription status** | `hs_recurring_billing_status` | Select | ✅ **DISCOVERED** | Active/Inactive subscription status |
| **Next renewal date** | `hs_recurring_billing_next_payment_date` | Date | ✅ **DISCOVERED** | Next payment due date |

---

### 🏢 **COMPANIES OBJECT** 
**Access**: Settings → Objects → Companies → Properties  
**Relationship**: Companies are associated with Deals (Company ↔ Deals)

#### **🎯 Company Identification Fields**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **CUIT** | `cuit` | String | ✅ **LIVE VERIFIED** | Unique company tax identifier (Argentina) |
| **Colppy ID** | `colppy_id` | String | ✅ **LIVE VERIFIED** | Internal system integration ID |
| **ID Empresa** | `id_empresa` | String | ✅ **LIVE VERIFIED** | Company identifier for Mixpanel integration |

#### **🔵 Company Classification Fields**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Type** | `type` | Select | ✅ **LIVE VERIFIED** | Company type classification |
| **Lifecycle Stage** | `lifecyclestage` | Select | ✅ **LIVE VERIFIED** | Customer lifecycle tracking |
| **Industry** | `industry` | Select | ✅ Native | Business sector classification |

**Company Type Options (Live Verified - 12 total)**:
1. `Alianza` - Strategic partnerships
2. `Cuenta Pyme` - Standard SMB accounts  
3. **`Cuenta Contador`** - **Accountant channel companies**
4. **`Cuenta Contador y Reseller`** - **Accountant + reseller**
5. `Integración Comercial` - Business integrations
6. `Integración Tecnológica` - Technical integrations  
7. `Medio de Comunicación` - Media companies
8. `Reseller / Consultor` - Reseller/consultant
9. `VENDOR` - Vendor/supplier
10. `OTHER` - Other/unclassified
11. **`Contador Robado`** - **Reverse discovery accountants**
12. `Empresa Administrada` - Managed companies

---

### 💼 **DEALS OBJECT**
**Access**: Settings → Objects → Deals → Properties

#### **🔵 Core Deal Fields**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Deal Name** | `dealname` | String | ✅ Native | Deal identification |
| **Amount** | `amount` | Number | ✅ Native | Deal value |
| **Close Date** | `closedate` | Date | ✅ Native | Expected/actual close date |
| **Deal Stage** | `dealstage` | Select | ✅ Native | Pipeline stage |
| **Pipeline** | `pipeline` | Select | ✅ Native | Sales pipeline |

#### **🟢 Custom Colppy Fields (Live Verified)**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Nombre del Plan del Negocio** | `nombre_del_plan_del_negocio` | Select | ✅ **LIVE VERIFIED** | Subscription plan name |
| **Cantidad de cuentas contador asociadas** | `tiene_cuenta_contador` | Number | ✅ **LIVE VERIFIED** | Count of associated accountants |
| **_colppy_es_referido_del_contador** | `colppy_es_referido_del_contador` | Select | ✅ **LIVE VERIFIED** | Accountant referral tracking |
| **_colppy_quien_lo_refirió** | `colppy_quien_lo_refirio` | String | ✅ **LIVE VERIFIED** | Referrer identification |

---

### 👤 **CONTACTS OBJECT**
**Access**: Settings → Objects → Contacts → Properties  
**Relationship**: Contacts are associated with Deals and Companies

#### **🔵 Core Contact Fields**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| First Name | `firstname` | String | ✅ Native | Contact first name |
| Last Name | `lastname` | String | ✅ Native | Contact last name |
| Email | `email` | String | ✅ Native | Primary email address |
| Create Date | `createdate` | Date | ✅ Native | Contact creation timestamp |
| Lifecycle Stage | `lifecyclestage` | Select | ✅ Native | Lead/opportunity/customer stage |

#### **🟢 Key Event & Trial Fields (Live Verified)**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Fecha de Hizo Evento Clave en Trial** | `fecha_activo` | Date | ✅ **LIVE VERIFIED** | Date when key activation event occurred |
| **Hizo evento clave en trial** | `activo` | Boolean | ✅ **LIVE VERIFIED** | Boolean flag for key event activation |

#### **🔵 Accountant Channel Fields (Live Verified)**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Es Contador** | `es_contador` | Boolean | ✅ **LIVE VERIFIED** | Identifies if contact is an accountant |
| **Perfil** | `perfil` | Select | ✅ **LIVE VERIFIED** | Contact profile/role classification |
| **Es Administrador** | `es_administrador` | Boolean | ✅ **LIVE VERIFIED** | Identifies if contact is company administrator |
| **Cuántos clientes tiene** | `cuantos_clientes_tiene` | String | ✅ **LIVE VERIFIED** | Number of clients (for accountants) |

#### **🔵 Lifecycle Tracking Fields**

| **UI Field Name** | **Internal Property** | **Type** | **Status** | **Purpose** |
|------------------|---------------------|-----------|------------|-------------|
| **Number of Associated Deals** | `num_associated_deals` | Number | ✅ Native | Count of deals associated with contact |
| **Became a Lead Date** | `hs_lifecyclestage_lead_date` | Date | ✅ Native | When contact became a lead |
| **Became an Opportunity Date** | `hs_lifecyclestage_opportunity_date` | Date | ✅ Native | When contact became an opportunity |
| **Became a Customer Date** | `hs_lifecyclestage_customer_date` | Date | ✅ Native | When contact became a customer |

---

### 🔗 **ASSOCIATION MAPPINGS (Live Verified)**

#### **Deal ↔ Company Associations**

| **UI Association Label** | **ID** | **Category** | **Purpose** |
|-------------------------|--------|--------------|-------------|
| Primary | `5` | HUBSPOT_DEFINED | Default primary company |
| **Estudio Contable / Asesor / Consultor Externo del negocio** | **`8`** | **USER_DEFINED** | **🎯 ACCOUNTANT CHANNEL TRACKING** |
| Compañía que refiere al negocio | `2` | USER_DEFINED | Referral tracking |
| Compañía Integrador del Negocio | `39` | USER_DEFINED | Integration partner |

#### **Contact ↔ Deal Associations**

| **UI Association Label** | **ID** | **Category** | **Purpose** |
|-------------------------|--------|--------------|-------------|
| Primary Contact | `4` | HUBSPOT_DEFINED | Default relationship |
| Contacto Inicial | `14` | USER_DEFINED | Deal originator |
| Decide | `5` | USER_DEFINED | Decision maker |
| **Influenciador Contador** | **`54`** | **USER_DEFINED** | **🎯 ACCOUNTANT INFLUENCE** |
| Refiere | `4` | USER_DEFINED | Referrer contact |

---

## API Connection Methods

**⚠️ CONNECTION-AGNOSTIC DEVELOPMENT**

This documentation supports both MCP connectors and direct HubSpot API calls. Choose the method that best fits your development environment:

### Common HubSpot Operations

#### 1. Search Contacts with Filters

**MCP Connector Method:**
```python
# Using MCP HubSpot connector
response = mcp_hubspot_search_objects(
    objectType="contacts",
    limit=100,
    properties=["email", "firstname", "lastname", "createdate", "lifecyclestage"],
    filterGroups=[{
        "filters": [
            {"propertyName": "createdate", "operator": "GTE", "value": "2025-01-01"},
            {"propertyName": "lifecyclestage", "operator": "EQ", "value": "lead"}
        ]
    }],
    after=after_cursor
)
contacts = response.results
```

**Direct API Method:**
```python
# Using direct HubSpot REST API
import requests

headers = {
    'Authorization': f'Bearer {access_token}',
    'Content-Type': 'application/json'
}

url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
payload = {
    "limit": 100,
    "properties": ["email", "firstname", "lastname", "createdate", "lifecyclestage"],
    "filterGroups": [{
        "filters": [
            {"propertyName": "createdate", "operator": "GTE", "value": "2025-01-01T00:00:00.000Z"},
            {"propertyName": "lifecyclestage", "operator": "EQ", "value": "lead"}
        ]
    }],
    "after": after_cursor
}

response = requests.post(url, headers=headers, json=payload)
data = response.json()
contacts = data['results']
```

#### 2. Search Deals with Associations

**MCP Connector Method:**
```python
# Search deals with company and contact associations
response = mcp_hubspot_search_objects(
    objectType="deals",
    limit=100,
    properties=["dealname", "amount", "dealstage", "closedate", "createdate"],
    associations=["companies", "contacts"],
    filterGroups=[{
        "filters": [
            {"propertyName": "dealstage", "operator": "IN", "values": ["closedwon", "34692158"]}
        ]
    }],
    after=after_cursor
)
deals = response.results
```

**Direct API Method:**
```python
# Search deals with associations using direct API
url = "https://api.hubapi.com/crm/v3/objects/deals/search"
payload = {
    "limit": 100,
    "properties": ["dealname", "amount", "dealstage", "closedate", "createdate"],
    "associations": ["companies", "contacts"],
    "filterGroups": [{
        "filters": [
            {"propertyName": "dealstage", "operator": "IN", "values": ["closedwon", "34692158"]}
        ]
    }],
    "after": after_cursor
}

response = requests.post(url, headers=headers, json=payload)
data = response.json()
deals = data['results']

# Get association details if needed
for deal in deals:
    deal_id = deal['id']
    assoc_url = f"https://api.hubapi.com/crm/v4/objects/deals/{deal_id}/associations/companies"
    assoc_response = requests.get(assoc_url, headers=headers)
    deal['company_associations'] = assoc_response.json()
```

#### 3. Get Contact-Deal Associations

**MCP Connector Method:**
```python
# Get contact-deal associations
associations = mcp_hubspot_get_associations(
    fromObjectType="contacts",
    toObjectType="deals",
    fromObjectId=contact_id
)
```

**Direct API Method:**
```python
# Get contact-deal associations using direct API
contact_id = "12345"
url = f"https://api.hubapi.com/crm/v4/objects/contacts/{contact_id}/associations/deals"
response = requests.get(url, headers=headers)
associations = response.json()
```

### Key Differences Between Methods

| Aspect | MCP Connector | Direct HubSpot API |
|--------|---------------|-------------------|
| **Date Format** | `"2025-01-01"` | `"2025-01-01T00:00:00.000Z"` |
| **Authentication** | Handled by MCP | Requires Bearer token |
| **Error Handling** | MCP wrapper handles | Manual HTTP status checks |
| **Rate Limiting** | MCP manages | Manual implementation needed |
| **Response Format** | Normalized by MCP | Raw HubSpot API response |
| **Pagination** | `response.results`, `response.paging` | `data['results']`, `data['paging']` |

### Error Handling Examples

**MCP Connector:**
```python
try:
    response = mcp_hubspot_search_objects(objectType="contacts", limit=100)
    if response.results:
        contacts = response.results
except Exception as e:
    print(f"MCP Error: {e}")
```

**Direct API:**
```python
try:
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # Raises exception for HTTP errors
    data = response.json()
    contacts = data['results']
except requests.RequestException as e:
    print(f"API Error: {e}")
except KeyError as e:
    print(f"Response format error: {e}")
```

### Best Practices for Connection-Agnostic Code

1. **Create wrapper functions** that abstract the connection method:
```python
def search_hubspot_objects(object_type, filters=None, properties=None, method="mcp"):
    """Connection-agnostic HubSpot search function"""
    if method == "mcp":
        return search_via_mcp(object_type, filters, properties)
    elif method == "api":
        return search_via_direct_api(object_type, filters, properties)
    else:
        raise ValueError("Method must be 'mcp' or 'api'")
```

2. **Use configuration files** to specify connection method:
```python
# config.py
HUBSPOT_CONNECTION_METHOD = "mcp"  # or "api"
HUBSPOT_ACCESS_TOKEN = "your_token_here"  # only needed for direct API
```

3. **Document both methods** in analysis scripts and maintain compatibility

## CRITICAL INSTRUCTION: Real HubSpot Data Integrity

**⚠️ ALL analysis must use actual HubSpot CRM data via MCP tools or direct API calls**

### Data Collection Requirements:

1. **Complete Pagination**: Always fetch ALL pages of results

**Option A: Using MCP Connector**
```python
# ✅ CORRECT: Complete pagination with MCP
all_contacts = []
after_cursor = None
while True:
    response = mcp_hubspot_search_objects(
        objectType="contacts",
        limit=100,
        after=after_cursor,
        ...
    )
    all_contacts.extend(response.results)
    if not response.paging or not response.paging.next:
        break
    after_cursor = response.paging.next.after
```

**Option B: Using Direct HubSpot API**
```python
# ✅ CORRECT: Complete pagination with direct API
import requests

all_contacts = []
after_cursor = None
headers = {
    'Authorization': f'Bearer {access_token}',
    'Content-Type': 'application/json'
}

while True:
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    payload = {
        "limit": 100,
        "after": after_cursor,
        "properties": ["email", "firstname", "lastname", "createdate"],
        "filterGroups": []  # Add filters as needed
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    all_contacts.extend(data['results'])
    
    if not data.get('paging') or not data['paging'].get('next'):
        break
    after_cursor = data['paging']['next']['after']
```

2. **Real Data Verification**:
   - Always report actual record counts from API responses
   - Verify field data exists before analysis
   - Document any missing or null data
   - Cross-reference with HubSpot UI when needed

3. **No Simulation Policy**:
   - NEVER generate sample or mock HubSpot data
   - NEVER simulate additional records for "comprehensive analysis"
   - NEVER use placeholder data for missing API responses
   - Use only actual CRM data returned by MCP tools or direct API calls

4. **Data Quality Checks**:
   - Validate contact-deal associations from actual API responses
   - Verify date ranges match actual HubSpot record timestamps
   - Confirm field mappings with real data samples
   - Report data anomalies rather than correcting with simulated data

### Audit Trail Requirements:

Every analysis must include:
- Exact API endpoints used (MCP functions or REST endpoints)
- Total records processed from real sources
- Date range of actual data collection
- Any data limitations from real sources

### Pre-Analysis Data Integrity Checklist

Before starting any business analysis, verify:

☐ **Real Data Sources Confirmed**
  - All data will come from actual data sources (MCP tools, direct HubSpot API, Mixpanel API, etc.)
  - No simulation or mock data will be used
  - Complete pagination strategy planned

☐ **Data Scope Verified**  
  - Date ranges match user requirements
  - Field mappings confirmed with real API responses
  - Expected record counts estimated from real sources

☐ **Analysis Boundaries Set**
  - What to do if real data is insufficient
  - How to handle API limitations
  - When to ask user for guidance vs. proceeding

☐ **Reporting Standards**
  - Real data source documentation planned
  - Actual record counts will be reported
  - Data quality limitations will be disclosed

**Business Impact Warning:**
- Simulated data invalidates all business insights
- Creates false confidence in analysis results  
- Misleads strategic decision-making
- Violates data integrity principles

## CRITICAL INSTRUCTION: Date References and Time Context

**⚠️ ALWAYS use current date context when running analysis scripts**

Before running any HubSpot analysis script, you MUST:
1. **Check today's date** using `datetime.now()` to understand current time context
2. **Set appropriate date ranges** based on the current year (2025)
3. **Ask the user for date range confirmation** if not explicitly specified
4. **Use relative date references** (e.g., "last 30 days", "current quarter") when possible

**Critical Rules:**
- Never hardcode years from previous periods without user confirmation
- Always verify that date filters align with current business context
- When analyzing "recent" data, use current year as reference point
- For historical analysis, explicitly state which time periods are being analyzed

**Example:**
```python
# ✅ CORRECT: Check current date context
from datetime import datetime
today = datetime.now()
current_year = today.year  # 2025
current_month = today.month

# ✅ CORRECT: Set date ranges based on current context
start_date = datetime(current_year, 1, 1)  # Beginning of current year
```

This ensures all analysis reflects current business reality and prevents outdated insights.

## CRITICAL INSTRUCTION: Month-to-Date (MTD) Analysis Methodology

**⚠️ ALWAYS use actual current date for MTD calculations**

When conducting month-to-date analysis, you MUST:

### 1. Dynamic Date Calculation
```python
from datetime import datetime

# Get current date context
today = datetime.now()
current_day = today.day
current_month = today.month  
current_year = today.year

print(f"Running MTD analysis for: {today.strftime('%B %d, %Y')}")
print(f"Comparing first {current_day} days across months")
```

### 2. MTD Comparison Rules
- **MTD = Month-to-Date**: Compare equivalent time periods (e.g., first 14 days of each month)
- **Dynamic Period**: Always use `today.day` to determine comparison period
- **Fair Comparison**: Only compare completed days across months
- **Documentation**: Always state the specific date range being analyzed

### 3. Date Range Construction for HubSpot API
```python
# For current month MTD
start_current = datetime(current_year, current_month, 1)
end_current = datetime(current_year, current_month, current_day, 23, 59, 59)

# For comparison months MTD 
start_comparison = datetime(current_year, comparison_month, 1)
end_comparison = datetime(current_year, comparison_month, current_day, 23, 59, 59)
```

### 4. MTD Reporting Standards
- **Always include current date** in report titles and metadata
- **State comparison period** explicitly (e.g., "First 14 days comparison")
- **Use relative rankings** when comparing MTD performance across months
- **Flag incomplete months** when relevant

### 5. MTD Field Filtering for HubSpot

**Option A: Using MCP Connector**
```python
# HubSpot MTD filter example using MCP tools
filterGroups = [{
    "filters": [
        {"propertyName": "createdate", "operator": "GTE", "value": f"{current_year}-{current_month:02d}-01"},
        {"propertyName": "createdate", "operator": "LTE", "value": f"{current_year}-{current_month:02d}-{current_day:02d}"}
    ]
}]

# Example MCP call with MTD filtering
response = mcp_hubspot_search_objects(
    objectType="contacts",
    limit=100,
    filterGroups=filterGroups,
    properties=["email", "createdate", "lifecyclestage"],
    after=after_cursor
)
```

**Option B: Using Direct HubSpot API**
```python
# Direct API MTD filter example
import requests
from datetime import datetime

# Current date context
today = datetime.now()
current_year = today.year
current_month = today.month
current_day = today.day

headers = {
    'Authorization': f'Bearer {access_token}',
    'Content-Type': 'application/json'
}

url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
payload = {
    "limit": 100,
    "properties": ["email", "createdate", "lifecyclestage"],
    "filterGroups": [{
        "filters": [
            {
                "propertyName": "createdate", 
                "operator": "GTE", 
                "value": f"{current_year}-{current_month:02d}-01T00:00:00.000Z"
            },
            {
                "propertyName": "createdate", 
                "operator": "LTE", 
                "value": f"{current_year}-{current_month:02d}-{current_day:02d}T23:59:59.999Z"
            }
        ]
    }],
    "after": after_cursor
}

response = requests.post(url, headers=headers, json=payload)
data = response.json()
```

**Critical Notes:**
- MTD analysis provides fair month comparisons by using equivalent time periods
- Results change daily as more data becomes available for the current month
- Always document the specific date when MTD analysis was run
- Use MTD for trending analysis and performance tracking
- When using any HubSpot connection method, ensure date formatting matches API requirements
- **MCP Tools**: Use simplified date format (YYYY-MM-DD)
- **Direct API**: Use ISO 8601 format with timezone (YYYY-MM-DDTHH:mm:ss.sssZ)

This methodology ensures accurate, comparable month-to-date analysis that reflects real business performance.

## CRITICAL INSTRUCTION: Key Event Timing Analysis

**⚠️ TIMEZONE AND DATA QUALITY CONSIDERATIONS**

When analyzing key events (`fecha_activo`) and their relationship to deal closing dates, be aware of critical data quality issues:

### Timezone Handling Issues
- **Registration timestamps**: Stored in UTC with full time precision
- **Key event timestamps**: Stored as Argentina local time truncated to midnight (00:00)
- **3-hour offset**: Can create appearance of events occurring "before" registration
- **Impact**: ~45% of timing sequences appear invalid but represent same-day activations

### Data Quality Assessment Requirements
Before making strategic decisions based on timing analysis, you MUST:
1. **Check for negative timing**: Events appearing before registration dates
2. **Identify same-day events**: Events on same calendar day as registration
3. **Calculate timezone-corrected timing**: Account for UTC to Argentina conversion
4. **Report data quality metrics**: Percentage of "invalid" vs correctable timing

### Causation Analysis Guidelines
- **Valid timing sequence**: Key event after registration date
- **Same-day activation**: Key event on same day as registration (likely valid)
- **Invalid timing**: Key event before registration (timezone artifact)
- **Recommendation**: Fix backend timezone handling before making PLG strategy decisions

### Business Intelligence Priority
Focus on same-day activation patterns:
- **76.5%** of customers activate on registration day
- **100%** of conversions occur within 7 days
- Same-day engagement is critical for conversion success

**Example Timezone-Aware Analysis:**
```python
# ✅ CORRECT: Account for timezone issues
contacts_df['registration_date'] = pd.to_datetime(contacts_df['createdate']).dt.date
contacts_df['key_event_date'] = pd.to_datetime(contacts_df['fecha_activo']).dt.date
contacts_df['same_day_activation'] = contacts_df['registration_date'] == contacts_df['key_event_date']
contacts_df['timing_valid'] = contacts_df['key_event_date'] >= contacts_df['registration_date']
```

## Key Event Fields Documentation

### Key Event Timestamp Field
- **UI Name:** "Fecha de Hizo Evento Clave en Trial"
- **Internal Property Name:** `fecha_activo` ✅ **VERIFIED**
- **Data Type:** Date (YYYY-MM-DD format)
- **Data Availability:** ~20% of contacts have timestamps
- **Description:** Records the exact date when a contact triggered a key activation event during trial

### Key Event Boolean Field  
- **UI Name:** "Hizo evento clave en trial"
- **Internal Property Name:** `activo` ✅ **VERIFIED**
- **Data Type:** Boolean (true/false)
- **Data Availability:** ~20% of contacts have true values
- **Description:** Boolean flag indicating whether contact has triggered any key activation event

### Important Notes:
- Both fields work together: `activo` = true indicates key event occurred, `fecha_activo` shows when
- Data quality verified as of July 1, 2025
- Previous analysis incorrectly used `fecha_de_hizo_evento_clave_en_trial` (which exists but has no data)

## Deal Pipeline Configuration

### CRITICAL DEFINITION: Closed vs Won vs Lost Deals

**⚠️ FUNDAMENTAL DISTINCTION FOR ALL ANALYSIS**

When analyzing deal performance, it is CRITICAL to understand these definitions:

1. **CLOSED DEALS** = All deals that have reached a final outcome (both won AND lost)
   - Includes: `closedwon` + `closedlost` + `31849274` (churn)
   - This is the total universe of completed deals

2. **WON DEALS** = Only deals that were successfully closed and revenue was generated
   - Includes ONLY: `closedwon` + `34692158` (recovery)
   - These are deals that generated revenue and customers

3. **LOST DEALS** = Deals that were closed but no revenue was generated
   - Includes: `closedlost` + `31849274` (churn)
   - These are deals where no sale occurred

**CRITICAL FOR ANALYSIS:**
- **Win Rate** = Won Deals ÷ Closed Deals (NOT total deals in pipeline)
- **Revenue** = Sum of amounts from Won Deals only
- **Pipeline Conversion** = Won Deals ÷ All Created Deals (including open)

**Example:**
- 15 Closed Deals = 8 Won + 7 Lost
- Win Rate = 8 ÷ 15 = 53.3%
- Revenue = Sum of 8 Won Deals only

### Main Sales Pipeline ("Pipeline de ventas")

| Stage Name | Probability | Technical ID | Outcome Type | Notes |
|------------|------------|--------------|--------------|-------|
| Pendiente de Demo | 30% | qualifiedtobuy | Open | Initial deal stage |
| Análisis | 50% | presentationscheduled | Open | Analyzing needs and solutions |
| Negociación | 90% | decisionmakerboughtin | Open | Discussing terms |
| Negociación Empresa Adicional | 90% | 948806400 | Open | Negotiating with additional entities |
| **Cerrado Ganado** | **100%** | **closedwon** | **WON** | **Deal successfully closed + revenue generated** |
| **Cerrado Ganado Recupero** | **100%** | **34692158** | **WON** | **Recovered previously lost client + revenue** |
| **Cerrado Perdido** | **0%** | **closedlost** | **LOST** | **Deal closed but no revenue generated** |
| **Cerrado Churn** | **0%** | **31849274** | **LOST** | **Customer who left (churned) - no new revenue** |

## Deal Owner IDs

### HubSpot Owner Structure
Generic pattern for HubSpot owners configuration:

| **Campo** | **Formato** | **Ejemplo** | **Descripción** |
|-----------|-------------|-------------|----------------|
| **Owner ID** | `{owner_id}` | 8854527xxx | ID único del propietario en HubSpot |
| **Full Name** | `{first_name} {last_name}` | "Juan Rodriguez" | Nombre completo del empleado |
| **Team** | `{team_name}` | "Equipo Customer" / "Marketing" / "Closers" | Equipo al que pertenece |
| **Status** | `Active/Archived` | "Active" | Estado actual del usuario |

### **Equipos Principales:**
- **Equipo Customer**: Customer Success y soporte
- **Equipo Revenue**: Sales y revenue operations  
- **Equipo Producto**: Product management y desarrollo
- **Marketing**: Marketing y growth
- **Closers**: Sales representatives
- **Accountant Channel**: Canal de contadores
- **HubSpot**: Administración de HubSpot
- **Unknown**: Sin equipo asignado

### **Obtener Owner ID Actual:**
```python
# Via HubSpot API
GET https://api.hubspot.com/crm/v3/owners
# Returns: list of all owners with IDs, names, teams
```

## Lead Status Progression

| Status | Technical Value | Description |
|--------|----------------|-------------|
| Nuevo Suscriptor | `{new_subscriber_id}` | New subscriber to content/newsletter |
| Nuevo Lead | `{new_lead_id}` (ej: 938333xxx) | New lead in the system |
| Nuevo Lead de Customer (CQL) | `{cql_lead_id}` (ej: 1002818xxx) | Lead generated from Customer Success team |
| Intentando contactar | `{attempting_id}` | Attempting to contact |
| Conectado | `{connected_id}` | Successfully reached |
| Calificado | `{qualified_id}` | Qualified as sales-ready |
| Descalificado | `{unqualified_id}` | Determined not to be a good fit |

## Lifecycle Stages

| Stage | Technical Value | Description |
|-------|----------------|-------------|
| Suscriptor | subscriber | Initial contact with minimal interaction |
| Lead | lead | Qualified contact showing interest |
| Oportunidad | opportunity | Lead considered for potential deal |
| Cliente | customer | Converted to paying customer |

## Lead Sources

The following values are used in the `lead_source` field to track the origin of leads:

| Source Value | Description |
|--------------|-------------|
| Orgánico | Organic traffic (SEO, direct visits) |
| Pago | Paid marketing channels (ads, sponsored content) |
| Referencia de Integrador | Partner/integrator referrals |
| Referencia Interna | Internal referrals from Colppy employees |
| Referencia Externa Pyme | External referrals from SMB customers or Accountant channel |
| CS | Customer Success team initiated leads |
| Referencia Intercom | Leads from Intercom chat/support |
| Usuario Invitado | Invited users (trials, demos) |

## Contact-Deal Associations

| Relationship Type | Technical ID | Description |
|-------------------|-------------|-------------|
| Primary Contact | 4 (HUBSPOT_DEFINED) | Default HubSpot relationship |
| Contacto Inicial | 14 (USER_DEFINED) | Initial contact creating the deal |
| Decide | 5 (USER_DEFINED) | Decision maker |
| Refiere | 4 (USER_DEFINED) | Referrer |
| Influenciador | 48 (USER_DEFINED) | Influencer in the decision process |
| Influenciador Contador | 54 (USER_DEFINED) | Accounting influencer |

## Deal-Company Associations

| Relationship Type | Technical ID | Description | Usage |
|-------------------|-------------|-------------|-------|
| Primary | 5 (HUBSPOT_DEFINED) | Default primary company relationship | Main client company |
| Default | 341 (HUBSPOT_DEFINED) | Basic company association (no label) | General connection |
| Estudio Contable / Asesor / Consultor Externo del negocio | 8 (USER_DEFINED) | Accounting firm/external consultant | Used to track deals from accountant channel |
| Compañía que refiere al negocio | 2 (USER_DEFINED) | Company that referred the deal | Referral tracking |
| Compañía Integrador del Negocio | 39 (USER_DEFINED) | Integration partner company | Partner attribution |
| Compañía con Múltiples Negocios | 11 (USER_DEFINED) | Company with multiple business relationships | Multi-entity customer |

## Cycle Time Tracking Fields

This section documents the key fields used for calculating important cycle times in the sales process. These fields help measure the efficiency of the sales pipeline and identify opportunities for improvement.

### Lead Lifecycle Cycle Time

> **Note:** In Colppy's workflow, leads are typically created at the same time as contacts, with very few exceptions. The most important cycle times are from lead creation to deal conversion.

**Start Time Fields:**
| Field Name | Object Type | Description |
|------------|-------------|-------------|
| createdate | Contact | Timestamp when the contact/lead record was created |
| hs_lifecyclestage_lead_date | Contact | Timestamp when the contact became a lead (usually same as createdate) |

**End Time Fields:**
| Field Name | Object Type | Description |
|------------|-------------|-------------|
| hs_lifecyclestage_opportunity_date | Contact | Timestamp when the contact was associated with a deal opportunity |
| hs_lifecyclestage_customer_date | Contact | Timestamp when the contact became a customer |

**Cycle Time Calculations:**
- **Lead to Opportunity Time**: `hs_lifecyclestage_opportunity_date - createdate`
- **Lead to Customer Time**: `hs_lifecyclestage_customer_date - createdate`

### Deal Creation to Close Cycle Time

**Start Time Fields:**
| Field Name | Object Type | Description |
|------------|-------------|-------------|
| createdate | Deal | Timestamp when the deal was created |
| hs_createdate | Deal | Alternative creation timestamp |
| dealstage_pendiente_de_demo_entered_at | Deal | Timestamp when the deal entered the first stage |

**End Time Fields:**
| Field Name | Object Type | Description |
|------------|-------------|-------------|
| closedate | Deal | Timestamp when the deal was closed (won or lost) |
| hs_closed_won_date | Deal | Timestamp when the deal was marked as won |
| hs_closed_lost_date | Deal | Timestamp when the deal was marked as lost |
| dealstage_cerrado_ganado_entered_at | Deal | Timestamp when the deal entered the won stage |
| dealstage_cerrado_perdido_entered_at | Deal | Timestamp when the deal entered the lost stage |

**Cycle Time Calculations:**
- **Deal Creation to Close Time**: `closedate - createdate`
- **Deal Creation to Won Time**: `hs_closed_won_date - createdate`
- **Deal Creation to Lost Time**: `hs_closed_lost_date - createdate`
- **First Stage to Won Time**: `dealstage_cerrado_ganado_entered_at - dealstage_pendiente_de_demo_entered_at`

### Stage Duration Tracking

HubSpot automatically tracks the time a deal spends in each stage with fields following this pattern:
- `dealstage_[stage_id]_entered_at` - When the deal entered the stage
- `time_in_[stage_id]` - Duration the deal spent in the stage

These fields can be used to identify bottlenecks in the sales process.

## Historical Notes

HubSpot retains properties for historical stages that may not be currently active in the pipeline. These include:
- `hs_date_entered_appointmentscheduled` - "Pendiente de Iniciar Proceso" (not currently active)
- `hs_date_entered_contractsent` - "SUSCRIPCIÓN 90%" (not currently active)
- `hs_date_entered_948509722` - "Confirmación de Compra" (not currently active)

These properties appear in API responses but do not represent current pipeline stages.

## Company-Centric Customer Definition  
**Purpose:** unify reporting across Product, RevOps, and Data teams when the CRM is analysed at *company* level instead of *deal* level.

### When is a company counted as a **new customer** for a given month?
A company belongs to the cohort *M* **iff all three conditions are met**:

| # | Condition | HubSpot property / source | Rationale |
|---|-----------|---------------------------|-----------|
| 1 | The company record already exists | `createdate ≤ {month_end}` | Filters out brand-new data-entry mistakes inside the month |
| 2 | Lifecycle stage changed to *Cliente* inside the month | `hs_date_entered_customer ∈ [{month_start},{month_end})` | This is the moment HubSpot flags the company as paying customer |
| 3 | Company is **Primary** on ≥1 *closed-won* deal | Association type `5` on any deal where `dealstage = closedwon` | Ensures we count the actual paying legal entity, not the accountant (type `8`) |

**⚠️  Exclude accountants:** association type `8` (“Estudio Contable / Asesor / Consultor Externo”) must *not* be counted as customers – they are channel partners.

### Sample API filter (SQL style)
```sql
WHERE createdate < '2025-08-01'
  AND hs_date_entered_customer >= '2025-07-01'
  AND hs_date_entered_customer <  '2025-08-01'
  AND EXISTS (
        SELECT 1
        FROM   deal_associations da
        WHERE  da.company_id = companies.id
          AND  da.typeId      = 5      -- Primary company
          AND  da.dealstage   = 'closedwon')
```

### Recommended dashboards
1. **Monthly new customers** – count of companies passing the 3-point test.
2. **Channel attribution** – split by `type` (Cuenta Contador, Contador Robado, Cuenta Pyme, Empresa Administrada, …).
3. **Velocity** – `hs_date_entered_customer − hs_date_entered_lead` and `…opportunity`.
4. **Retention / churn** – use `hs_date_exited_customer` alongside the entry date.

---

## Usage Guidelines

When integrating with HubSpot or analyzing data:
1. Always reference this document for the current pipeline configuration
2. Use the technical IDs for programmatic access
3. Be aware of both active and historical properties
4. When in doubt, verify current configuration in HubSpot UI

## Deal Analysis Rule

- For every output, report, or analysis involving HubSpot deals, **always include**:
  - Whether the deal is associated with an accountant (using the association type `Estudio Contable / Asesor / Consultor Externo del negocio`, ID: 8 USER_DEFINED, in the deal-company associations table below).
  - Whether the deal was referred (using the referral/association fields as specified in HubSpot).
  - **ID Empresa (Company ID) is the unique identifier for the company associated with the deal. This is the key used to join HubSpot deals to Mixpanel company data.**
- This information must be present in all summaries, insights, exports, and responses, regardless of whether the deal is won, lost, or open.
- If the association is not available, explicitly state that the information is missing or not set for the deal.

### How to check for accountant channel
- Always check the deal-company association for the type:
  - **Estudio Contable / Asesor / Consultor Externo del negocio** (`8 (USER_DEFINED)`)
- If present, report the company name and that the deal is from the accountant channel.
- If not present, state that the deal is not associated with an accountant via this relationship.

## Example Output

- Deal ID: 12345
- Deal Name: Example Deal
- **Accountant Channel:** Yes (Estudio Contable: "Estudio Perez & Asociados")
- Referred: False
- ...other deal fields...

## Best Practice
- Always check the latest HubSpot schema for the correct field names and update the analysis scripts and documentation accordingly.



---

## 📋 CONFIGURACIÓN CRM - CANAL DE CONTADOR

Esta sección documenta la configuración específica para identificar y rastrear el canal de contador en el CRM de Colppy.

### 🎯 OBJETO: CONTACTOS

| **Campo Interno** | **Nombre en HubSpot UI** | **Tipo** | **Descripción** | **Uso para Canal Contador** |
|-------------------|-------------------------|----------|-----------------|----------------------------|
| `es_contador` | "Es Contador" | Boolean | Identifica si el contacto es contador | **CAMPO PRINCIPAL**: Marca directa de contador |
| `perfil` | "Perfil" | Enumeration | Perfil del contacto | Puede incluir "Contador" como opción |
| `es_administrador` | "Es Administrador" | Boolean | Si es administrador de empresa | Diferencia contador vs. administrador |
| `cuantos_clientes_tiene` | "Cuántos clientes tiene" | String | Cantidad de clientes del contador | Tamaño del estudio contable |
| `utm_campaign` | "UTM Campaign" | String | Campaña UTM original | **DETECCIÓN AUTOMÁTICA**: Campañas con "conta" = intención contador |

### 🎯 OBJETO: NEGOCIOS (DEALS)

| **Campo Interno** | **Nombre en HubSpot UI** | **Tipo** | **Descripción** | **Uso para Canal Contador** |
|-------------------|-------------------------|----------|-----------------|----------------------------|
| `tiene_cuenta_contador` | "Cantidad de cuentas contador asociadas" | Number | Cuenta etiquetas de contador relacionado | **FÓRMULA**: Cantidad de contadores asociados |
| `utm_campaign_negocio` | "UTM Campaign del Negocio" | String | Campaña UTM del negocio | **DETECCIÓN AUTOMÁTICA**: Campañas con "conta" = intención contador |
| `colppy_es_referido_del_contador` | "_colppy_es_referido_del_contador" | Enumeration | Si es referido por contador | **CANAL DIRECTO**: Referencia de contador |
| `colppy_quien_lo_refirio` | "_colppy_quien_lo_refirió" | String | Quien refirió el negocio | Identificación del contador referente |

### 🎯 OBJETO: COMPAÑÍAS

| **Campo Interno** | **Nombre en HubSpot UI** | **Tipo** | **Descripción** | **Uso para Canal Contador** |
|-------------------|-------------------------|----------|-----------------|----------------------------|
| `domain` | "Dominio del sitio web de la empresa" | String | Dominio web de la compañía | Identificación de estudios contables |
| `industry` | "Sector" | Enumeration | Sector de la compañía | Incluye "Servicios Contables" |
| `name` | "Nombre de empresa" | String | Nombre de la compañía | Identificación del estudio contable |
| `type` | "Type" | Enumeration | Tipo/clasificación de la compañía | **CLASIFICACIÓN CLAVE**: Identifica categoría de canal |

#### **🎯 VALORES DE TIPO DE EMPRESA (Company Type Field)**

| **Orden** | **Etiqueta** | **Nombre Interno** | **Descripción** | **Uso en Canal Management** |
|-----------|--------------|-------------------|----------------|---------------------------|
| 1 | Alianza | Alianza | Compañía en alianza estratégica | Partnerships y colaboraciones |
| 2 | Cuenta Pyme | Cuenta Pyme | Cuenta PyME estándar | Segmento SMB principal |
| 3 | **Cuenta Contador** | **Cuenta Contador** | **Cuenta de contador/estudio contable** | **CANAL CONTADOR PRINCIPAL** |
| 4 | **Cuenta Contador y Resell** | **Cuenta Contador y Reseller** | **Contador que también revende** | **CANAL CONTADOR + RESELLER** |
| 5 | Integración Comercial | Integración Comercial | Integración comercial/business | Partnerships comerciales |
| 6 | Integración Tecnológica | Integración Tecnológica | Integración tech/desarrollo | Partnerships técnicos |
| 7 | Medio de Comunicación | Medio de Comunicación | Medios y comunicación | Marketing y prensa |
| 8 | Reseller / Consultor | Reseller / Consultor | Revendedor o consultor | Canal indirecto |
| 9 | Proveedor | VENDOR | Proveedor de servicios | Supply chain |
| 10 | Otra | OTHER | Otros tipos no clasificados | Clasificación genérica |
| 11 | **Contador Robado** | **Contador Robado** | **Contador descubierto a través de cliente SMB** | **CANAL CONTADOR - REVERSE DISCOVERY** |
| 12 | Empresa Administrada | Empresa Administrada | Empresa con administración externa | Gestión delegada |

> **📋 CAMPOS CLAVE PARA CANAL CONTADOR:**
> - `Cuenta Contador`: Contadores tradicionales directos
> - `Cuenta Contador y Resell`: Contadores que también revenden soluciones
> - `Contador Robado`: **Estrategia de descubrimiento reverso** - Contadores identificados a través de clientes SMB existentes, que luego se cultivan como socios de canal

#### **🎯 ESTRATEGIA "CONTADOR ROBADO" - REVERSE DISCOVERY**

La estrategia **"Contador Robado"** es un método inteligente de desarrollo de canal que funciona de la siguiente manera:

1. **📈 Cliente SMB existente**: Colppy ya tiene un cliente SMB activo
2. **🔍 Descubrimiento del contador**: A través del cliente SMB, se identifica el contador/estudio contable que trabaja con esa empresa
3. **🤝 Cultivo del canal**: El contador descubierto se convierte en un prospecto para el canal de contadores
4. **📊 Clasificación CRM**: Se marca como "Contador Robado" para trackear este método de adquisición de canal
5. **🌱 Desarrollo del partner**: El contador se cultiva para generar nuevos referidos y expandir el canal

> **💡 VENTAJA ESTRATÉGICA**: Este método aprovecha relaciones existentes para identificar contadores que ya conocen y confían en el perfil de cliente ideal de Colppy.

### 🔗 ETIQUETAS DE ASOCIACIÓN CONTADOR

#### **Negocios ↔ Compañías (Deal-Company Associations)**

| **Etiqueta** | **ID Técnico** | **Significado** | **Uso** |
|--------------|-------------|-----------------|---------|
| "Estudio Contable / Asesor / Consultor Externo del negocio" | `8 (USER_DEFINED)` | Contador asociado como asesor externo | **PRINCIPAL**: Identifica canal contador |
| "Compañía que refiere al negocio" | `2 (USER_DEFINED)` | Compañía que refiere el negocio | Rastreo de referencias |

#### **Contactos ↔ Negocios (Contact-Deal Associations)**

| **Etiqueta** | **ID Técnico** | **Significado** | **Uso** |
|--------------|-------------|-----------------|---------|
| "Influenciador Contador" | `54 (USER_DEFINED)` | Contador que influye en la decisión | **ESPECÍFICO**: Influencia contable |
| "Refiere" | `4 (USER_DEFINED)` | Contacto que refiere el negocio | Rastreo de referencias |

### 🔍 MÉTODOS DE IDENTIFICACIÓN DEL CANAL CONTADOR

#### **1. Identificación Automática por UTM Campaign**
- **Campo**: `utm_campaign` (Contactos) / `utm_campaign_negocio` (Negocios)
- **Criterio**: Contiene la palabra "conta" en cualquier parte del nombre
- **Ejemplo**: "fb_conta_trial", "google_contador_demo"
- **Propósito**: Detectar intención de atraer contadores desde generación de demanda

#### **2. Identificación Directa por Campo Booleano**
- **Campo**: `es_contador` (Contactos)
- **Criterio**: `true`
- **Propósito**: Marca explícita de contador

#### **3. Identificación por Asociación de Compañías**
- **Método**: Etiqueta "Estudio Contable / Asesor / Consultor Externo del negocio"
- **ID**: `8 (USER_DEFINED)`
- **Propósito**: Rastrear negocios vinculados a estudios contables

#### **4. Identificación por Referencia Directa**
- **Campo**: `colppy_es_referido_del_contador` (Negocios)
- **Propósito**: Negocios referidos específicamente por contadores

#### **5. Conteo Automático de Contadores**
- **Campo**: `tiene_cuenta_contador` (Negocios)
- **Tipo**: Fórmula calculada
- **Propósito**: Cuenta automáticamente las etiquetas de contador relacionado

### 📊 REGLAS DE ANÁLISIS CANAL CONTADOR

Para cualquier análisis, reporte o salida que involucre negocios de HubSpot:

1. **Siempre incluir**:
   - Si tiene contador asociado (usando etiqueta ID 8)
   - Si fue referido por contador (`colppy_es_referido_del_contador`)
   - Cantidad de contadores relacionados (`tiene_cuenta_contador`)
   - Origen de campaña UTM con "conta"

2. **Ejemplos de estructura de datos**:

> **📝 Nota sobre URLs de HubSpot:**  
> `{portal_id}` = ID de la cuenta de HubSpot de Colppy (usar el valor actual de producción)
   
   **Ejemplo 1 - Negocio con contador asociado:**
   ```
   - Deal ID: {deal_id} (ej: 9354650xxx)
   - Deal Name: "{deal_number} - {company_name}"
   - **Canal Contador**: Sí (Cantidad: {count})
   - **Referido por Contador**: {true/false}
   - **Amount**: ${amount}
   - **Stage**: {deal_stage}
   - **HubSpot URL**: https://app.hubspot.com/contacts/{portal_id}/deal/{deal_id}/
   ```
   
   **Ejemplo 2 - Contacto contador:**
   ```
   - Contact ID: {contact_id} (ej: 110651628xxx)
   - Name: "{first_name} {last_name}"
   - Email: "{name}@{studio_domain}.com.ar"
   - **Es Contador**: {true/false}
   - **UTM Campaign**: "{campaign_name}"
   - **HubSpot URL**: https://app.hubspot.com/contacts/{portal_id}/contact/{contact_id}/
   ```
   
   **Ejemplo 3 - Estudio contable:**
   ```
   - Company ID: {company_id} (ej: 9018573xxx)
   - Name: "{studio_name} Estudio Contable | {partner_name}"
   - **Tipo**: {type_field_value}
   - **Asociación**: {association_label}
   - **HubSpot URL**: https://app.hubspot.com/contacts/{portal_id}/record/0-2/{company_id}/
   ```

3. **Si no hay información disponible**:
   - Declarar explícitamente que la información falta o no está configurada

### 📋 ESTRUCTURA DE DATOS - CONTADORES EN EL CRM

#### **Contadores Identificados (es_contador = true)**

| **Campo** | **Formato** | **Ejemplo** | **Descripción** |
|-----------|-------------|-------------|----------------|
| **Nombre** | `{first_name} {last_name}` | "Juan Rodriguez" | Nombre completo del contador |
| **Email** | `{name}@{studio}.com.ar` | "juan@rodriguezconta.com.ar" | Email profesional del estudio |
| **UTM Campaign** | `{campaign_type}_{target}` | "Acuerdo_Beneficiocontadorpyme" | Campaña de origen |
| **ID** | `{contact_id}` | 110651628xxx | ID único de contacto |
| **HubSpot URL** | - | `https://app.hubspot.com/contacts/{portal_id}/contact/{contact_id}/` | Link directo |

#### **Estudios Contables Registrados**

| **Campo** | **Formato** | **Ejemplo** | **Descripción** |
|-----------|-------------|-------------|----------------|
| **Nombre del Estudio** | `{name} Estudio Contable \| {partner}` | "Rodriguez & Asoc. Estudio Contable \| Juan Rodriguez" | Razón social completa |
| **ID Compañía** | `{company_id}` | 9018573xxx | ID único de compañía |
| **Tipo** | `type` field | "Cuenta Contador" / "Contador Robado" | Clasificación de canal |
| **HubSpot URL** | - | `https://app.hubspot.com/contacts/{portal_id}/record/0-2/{company_id}/` | Link directo |

#### **Negocios con Contadores Asociados**

| **Campo** | **Formato** | **Ejemplo** | **Descripción** |
|-----------|-------------|-------------|----------------|
| **Deal Name** | `{number} - {company_name}` | "150 - Empresa PyME SRL" | Nombre del deal |
| **Amount** | `${amount}` | "$100.315,50" | Monto en pesos argentinos |
| **Cantidad Contadores** | `{count}` | 1-3 | Número de contadores asociados |
| **Stage** | `dealstage` | "Cerrado Ganado" / "En Proceso" | Estado del deal |
| **ID** | `{deal_id}` | 9354650xxx | ID único del deal |
| **HubSpot URL** | - | `https://app.hubspot.com/contacts/{portal_id}/deal/{deal_id}/` | Link directo |

#### **Campañas UTM con Intención Contador**

| **Campaña** | **Descripción** |
|-------------|-----------------|
| Acuerdo_Beneficiocontadorpyme | Acuerdo específico para beneficios de contadores PyME |
| Base_Frio | Campaña de base fría que incluye contadores |

### 🎯 MEJORES PRÁCTICAS

1. **Verificación Regular**: Revisar la configuración actual en HubSpot UI
2. **Campos Obligatorios**: Incluir `id_empresa` para integración con Mixpanel
3. **Actualización**: Mantener este documento actualizado con cambios de configuración
4. **Consistencia**: Usar siempre los nombres de campos tanto internos como de UI

---

## 📈 CONVERSION MEASUREMENT METHODOLOGIES

This section defines the standard methodologies for measuring different types of conversions in Colppy's HubSpot CRM. These methodologies must be used consistently across all analyses and reports.

### 🎯 Contact-to-Deal Conversion

**Definition**: Measures how many contacts generate associated deals (opportunities), regardless of deal outcome.

**Primary Method**: Deal Association Field
- **Field Used**: `num_associated_deals` (Contact object)
- **Formula**: `contacts_df['has_deals'] = contacts_df['num_associated_deals'] > 0`
- **Conversion Rate**: `(contacts with deals / total contacts) × 100`

**Use Cases**:
- Lead generation effectiveness
- Campaign performance analysis
- Source quality assessment
- Marketing ROI calculations

**Example Output**:
```
Contact-to-Deal Conversion Analysis:
• Total Contacts: 1,245
• Contacts with Deals: 156
• Conversion Rate: 12.53%
• Method: num_associated_deals > 0
```

### 🎯 Contact-to-Customer Conversion

**Definition**: Measures how many contacts become paying customers.

**Primary Method**: Lifecycle Stage Method
- **Field Used**: `lifecyclestage = 'customer'` (Contact object)
- **Formula**: `contacts_df['is_customer'] = contacts_df['lifecyclestage'] == 'customer'`
- **Conversion Rate**: `(customer contacts / total contacts) × 100`

**Secondary Method**: Customer Date Method
- **Field Used**: `hs_lifecyclestage_customer_date` (populated)
- **Formula**: `contacts_df['is_customer_date'] = contacts_df['hs_lifecyclestage_customer_date'].notna()`
- **Timing**: `hs_lifecyclestage_customer_date - createdate`

**Data Quality Check**:
- Both methods should yield identical results
- If discrepancies exist, investigate data integrity issues
- Report overlap percentage and inconsistencies

**Use Cases**:
- Revenue attribution analysis
- Customer acquisition cost (CAC) calculations
- Lifetime value (LTV) analysis
- True business impact measurement

**Example Output**:
```
Contact-to-Customer Conversion Analysis:
• Total Contacts: 1,245
• Customers (Lifecycle): 89
• Customers (Date Method): 89
• Conversion Rate: 7.15%
• Method Overlap: 100.0%
• Average Time to Customer: 45.2 days
```

### 🎯 Deal-to-Customer Conversion

**Definition**: Measures the win rate of created deals.

**Primary Method**: Deal Stage Analysis
- **Field Used**: `dealstage` (Deal object)
- **Won Stages**: `['closedwon', '34692158']` (Cerrado Ganado, Cerrado Ganado Recupero)
- **Formula**: `deals_df['is_won'] = deals_df['dealstage'].isin(won_stages)`
- **Conversion Rate**: `(won deals / total deals) × 100`

**Timing Calculation**:
- **Field Used**: `closedate - createdate`
- **Alternative**: `hs_closed_won_date - createdate`

**Use Cases**:
- Sales team effectiveness
- Pipeline health analysis
- Deal velocity tracking
- Sales process optimization

**Example Output**:
```
Deal-to-Customer Conversion Analysis:
• Total Deals: 245
• Won Deals: 67
• Win Rate: 27.35%
• Average Deal Cycle: 38.5 days
• Total Revenue: $1,245,600
```

### 🔄 Methodology Comparison Requirements

When conducting any conversion analysis, always:
1. **Report both contact-to-deal AND contact-to-customer rates**
2. **Include timing analysis** (average days to conversion)
3. **Segment by key attributes** (source, campaign, accountant channel)
4. **Check data quality** (missing fields, inconsistencies)
5. **Document methodology used** in all outputs

---

## 📊 KEY EVENT ANALYSIS FINDINGS & RECOMMENDATIONS

### 🎯 Critical Data Quality Issues Identified

**Timezone Handling Problems:**
- **45.1%** of key events appear to occur "before" registration (timezone artifacts)
- **Registration timestamps**: UTC with full precision
- **Key event timestamps**: Argentina local time truncated to midnight
- **3-hour offset** creates false negative timing sequences

### 🔍 Corrected Business Intelligence

**Same-Day Activation Patterns:**
- **76.5%** of customers activate on registration day
- **11.8%** activate on the next day
- **100%** of conversions occur within 7 days
- Same-day engagement is **critical** for conversion success

**Key Event Impact on Conversion:**
- **With key events**: 21.6% conversion rate (236 contacts)
- **Without key events**: 23.1% conversion rate (5,421 contacts)
- **Net impact**: -1.5 percentage points (correlation, not causation)

### 🚨 Immediate Technical Recommendations

1. **Fix Backend Timezone Handling**:
   - Standardize all timestamps to UTC
   - Maintain full timestamp precision
   - Implement proper timezone conversion for Argentina

2. **Data Quality Audit**:
   - Clean existing timestamp data
   - Implement validation rules
   - Monitor for future timezone inconsistencies

3. **PLG Strategy Focus**:
   - Optimize same-day onboarding experience
   - Implement real-time activation triggers
   - Reduce time-to-first-value to hours, not days

### 📈 Strategic Implications

**Product-Led Growth Priority:**
- First few hours after registration are **critical**
- Immediate value delivery drives conversion
- Same-day activation should be primary PLG metric

**Analysis Reliability:**
- Causation analysis compromised by data quality issues
- Focus on timing patterns rather than correlation coefficients
- Use corrected data for strategic decision-making

---

**For every conversion analysis, always include**:

1. **Method Description**: Clearly state which method is being used
2. **Field Documentation**: List the exact HubSpot fields and formulas
3. **Data Quality Check**: Report any inconsistencies between methods
4. **Time Period**: Specify the analysis date range
5. **Sample Size**: Include total count of records analyzed

**Standard Output Format**:
```
CONVERSION METHODOLOGY:
• Analysis Type: [Contact-to-Deal/Contact-to-Customer/Deal-to-Customer]
• Primary Method: [Field name and criteria]
• Formula: [Exact calculation used]
• Data Quality: [Overlap rate, inconsistencies, missing data]
• Time Period: [Start date] to [End date]
• Sample Size: [Total records analyzed]
```

### 📊 Conversion Funnel Analysis

**Complete Customer Journey**:
1. **Contact Creation** → `createdate`
2. **Lead Qualification** → `hs_lifecyclestage_lead_date`
3. **Deal Creation** → `hs_lifecyclestage_opportunity_date`
4. **Customer Conversion** → `hs_lifecyclestage_customer_date`

**Funnel Metrics**:
- Contact → Lead: Usually 100% (created simultaneously)
- Contact → Deal: Use `num_associated_deals > 0`
- Contact → Customer: Use `lifecyclestage = 'customer'`
- Deal → Customer: Use deal `dealstage` analysis

### ⚠️ Critical Methodology Notes

1. **Contact-to-Deal vs Contact-to-Customer**:
   - Contact-to-Deal measures lead generation effectiveness
   - Contact-to-Customer measures actual revenue impact
   - Contact-to-Customer rates are always lower than Contact-to-Deal

2. **Data Integrity Requirements**:
   - Always verify `lifecyclestage` matches `hs_lifecyclestage_customer_date`
   - Report discrepancies as data quality issues
   - Use primary method consistently across analyses

3. **Timing Calculations**:
   - Use UTC timezone for all date calculations
   - Account for business days vs calendar days where relevant
   - Handle null dates appropriately

4. **Reporting Standards**:
   - Include methodology in all reports
   - Use Argentina number formatting (comma for decimals)
   - Provide both count and percentage metrics

### 📋 Script Implementation Requirements

**All HubSpot conversion analysis scripts must**:
1. Include methodology comparison function
2. Document data quality checks
3. Export methodology summary with results
4. Use consistent field naming conventions
5. Follow Argentina formatting standards
6. Generate visualization with methodology labels

**Example Script Structure**:
```python
def analyze_conversion_methods(df):
    """Compare different conversion measurement methods"""
    # Implementation details...
    
def export_methodology_summary(results, output_dir):
    """Export methodology documentation with results"""
    # Implementation details...
    
def main():
    # Analysis implementation with methodology documentation
    pass
```

---



## Key Event Trial Fields

### Trial Activation Tracking

Colppy tracks user activation during trial periods through key product events. These fields help measure product engagement and predict conversion potential.

| Field Display Name | HubSpot Internal Field | Object Type | Description | Data Status |
|-------------------|------------------------|-------------|-------------|-------------|
| Fecha de Hizo Evento Clave en Trial | `fecha_activo` | Contact | Timestamp when the user triggered a key event during their trial period. If blank, the user never triggered the key event. | ✅ **Has data** - PQL date field for activation timing |
| Hizo evento clave en trial | `activo` | Contact | Boolean checkbox indicating whether the user performed a key event during trial. `true` means they activated, `false` or blank means no activation. | ✅ **Has data** - Found in 17.8% of contacts |

### Analysis Findings (July 1, 2025)

**Field Data Availability:**
- `fecha_activo`: PQL timestamp data available (data quality to be verified in current analysis)
- `activo`: 533 out of 3,000 contacts (17.8%) have `true` values
- **Key Event Rate by Source:**
  - ORGANIC_SEARCH: 81.5% activation rate
  - PAID_SEARCH: 68.0% activation rate  
  - DIRECT_TRAFFIC: 64.5% activation rate
  - OFFLINE: 16.4% activation rate
  - OTHER_CAMPAIGNS: 1.4% activation rate

**Data Quality Issues Identified:**
- The timestamp field (`fecha_activo`) data quality needs verification in current analysis
- Potential timezone handling issues between PQL events and deal close dates
- Both fields (`fecha_activo` and `activo`) should be used together for comprehensive PQL analysis

### Business Logic
- **Key Event Definition**: The key event represents critical product activation actions (e.g., creating first invoice, setting up company data, processing first transaction)
- **Trial Period**: Events tracked during the 7-day free trial period
- **Conversion Impact**: Users who trigger key events typically show higher conversion rates from trial to paid subscription
- **Timing Analysis**: Use `fecha_activo` field for PQL timing correlation with deal conversion

### Usage in Analysis
These fields are commonly used for:
- **Conversion Rate Analysis**: Comparing conversion rates between activated vs non-activated trial users
- **Source Effectiveness**: Understanding which traffic sources generate more activated users
- **Product Led Growth**: Identifying activation patterns by industry and user type
- **Sales Prioritization**: Focusing sales efforts on activated trial users

### Recommendations for Data Improvement
1. **Verify Timestamp Data**: Confirm `fecha_activo` field is properly populated when `activo` is set to true
2. **Data Validation**: Implement checks to ensure both fields align (if `activo` = true, then `fecha_activo` should exist)
3. **PQL Analysis**: Use both `fecha_activo` and `activo` fields for comprehensive Product Qualified Lead analysis

### Technical Notes
- `activo` field mapping confirmed working in scoring analysis (SCORING_ANALYSIS_METHODOLOGY.md)
- `fecha_activo` field provides PQL timestamp for activation timing analysis
- Field shows slight negative conversion lift (-2.8%) in predictive scoring
- Organic and paid search traffic show highest activation rates (65%+)
- OFFLINE traffic shows lower activation rates (16.4%), suggesting different user behavior patterns

---

## 🔗 HubSpot Deal Association Structure Guide

### Overview
This section defines the correct association structure for HubSpot deals when switching primary companies between client companies and accountant firms for revenue attribution purposes.

### ✅ Complete Association Structure for Accountant Primary Deals

When an **accountant firm is the primary company** (revenue attributed to accountant):

#### **Accountant Company (PRIMARY)**
**Example: Maria Florencia Peña - Estudio**
```
Association Type IDs: [5, 341, 8]
- typeId 5 = PRIMARY 
- typeId 8 = "Estudio Contable / Asesor / Consultor Externo del negocio"
- typeId 341 = Default association
```
**Status**: PRIMARY + ESTUDIO CONTABLE + ASSOCIATED  
**Revenue Attribution**: ✅ Revenue attributed to accountant firm

#### **SMB Client Company (ASSOCIATED)**
**Example: 18462 GIO INTERNATIONAL LLC**
```
Association Type IDs: [341, 11]
- typeId 341 = Default association
- typeId 11 = "Deal with Primary Company"
```
**Status**: DEAL WITH PRIMARY COMPANY + ASSOCIATED  
**Revenue Attribution**: ❌ Revenue NOT attributed to client (attributed to primary accountant)

### ✅ Complete Association Structure for Client Primary Deals

When a **client company is the primary company** (standard revenue attribution):

#### **SMB Client Company (PRIMARY)**
**Example: When client should get revenue attribution**
```
Association Type IDs: [5, 341]
- typeId 5 = PRIMARY
- typeId 341 = Default association
```
**Status**: PRIMARY + ASSOCIATED  
**Revenue Attribution**: ✅ Revenue attributed to client company

#### **Accountant Company (ASSOCIATED)**
**Example: Maria Florencia Peña - Estudio when not primary**
```
Association Type IDs: [8, 341]
- typeId 8 = "Estudio Contable / Asesor / Consultor Externo del negocio"  
- typeId 341 = Default association
```
**Status**: ESTUDIO CONTABLE + ASSOCIATED  
**Revenue Attribution**: ❌ Revenue NOT attributed to accountant

### 🔧 API Implementation Guide

#### ✅ What Works via API

1. **Adding/Removing PRIMARY (typeId 5)**
   - ✅ Can add typeId 5 to any company
   - ✅ Can remove typeId 5 from any company
   - ✅ Can switch PRIMARY between companies

2. **Managing Default Associations (typeId 341)**
   - ✅ Can add/remove typeId 341
   - ✅ Usually included automatically

#### ❌ API Limitations

1. **Cannot CREATE typeId 8 via API**
   - ❌ HubSpot API v4 blocks creating "Estudio Contable" (typeId 8) in deal→company direction
   - ❌ Error: "One or more association types in request don't match specified object types & direction"
   - ✅ Can PRESERVE typeId 8 if it already exists
   - ✅ Can add via HubSpot UI manually

2. **Cannot CREATE typeId 11 via API**
   - ❌ HubSpot API v4 blocks creating "Deal with Primary Company" (typeId 11) in deal→company direction
   - ❌ Same error as typeId 8 - API limitation for custom association labels
   - ✅ Can PRESERVE typeId 11 if it already exists
   - ✅ Can add via HubSpot UI manually

3. **UI-Only Association Types**
   - ❌ Both typeId 8 and typeId 11 require HubSpot UI for initial creation
   - ❌ API can only preserve existing associations, not create new ones

### 📋 Best Practices for Switching Primary Companies

#### Scenario: Switch from Client Primary to Accountant Primary

```python
# Step 1: Remove PRIMARY from client company
# Keep their existing non-primary associations + add SMB label
# Result: Client should have [341, 11] (DEFAULT + DEAL WITH PRIMARY COMPANY)

# Step 2: Add PRIMARY to accountant
# IMPORTANT: If accountant already has typeId 8, preserve it!
# Result should be: [5, 341, 8] (PRIMARY + DEFAULT + ESTUDIO CONTABLE)

# Step 3: Verify final state
# Client: [341, 11] (DEFAULT + DEAL WITH PRIMARY COMPANY)
# Accountant: [5, 341, 8] (PRIMARY + DEFAULT + ESTUDIO CONTABLE)
```

#### Scenario: Switch from Accountant Primary to Client Primary

```python
# Step 1: Remove PRIMARY from accountant
# CRITICAL: Preserve typeId 8! Result should be [8, 341]

# Step 2: Add PRIMARY to client + remove SMB label
# Result should be: [5, 341] (PRIMARY + DEFAULT)

# Step 3: Verify final state  
# Client: [5, 341] (PRIMARY + DEFAULT)
# Accountant: [8, 341] (ESTUDIO CONTABLE + DEFAULT)
```

### 🎯 Association Type ID Reference

| Type ID | Label | Description | API Support | When to Use |
|---------|-------|-------------|-------------|-------------|
| 5 | PRIMARY | Primary company association | ✅ Full support | Company that receives revenue attribution |
| 8 | Estudio Contable / Asesor / Consultor Externo del negocio | Accountant firm label | ❌ Cannot create via API | Accountant companies (preserve if exists) |
| 11 | Deal with Primary Company | SMB client label when accountant is primary | ✅ Full support | Non-accountant companies when not primary |
| 341 | Default | Standard association | ✅ Full support | All associated companies |

### 🔍 Reference Examples

#### Deal 18355 (BARLOW LIMITED) - Accountant Primary
```
✅ PRIMARY + ESTUDIO CONTABLE: Maria Florencia Peña - Estudio [5, 341, 8]
📋 DEAL WITH PRIMARY COMPANY: 18355 BARLOW LIMITED [11, 341]
Revenue → Maria Florencia Peña - Estudio
```

#### Deal 18462 (GIO INTERNATIONAL LLC) - Accountant Primary
```
✅ PRIMARY + ESTUDIO CONTABLE: Maria Florencia Peña - Estudio [5, 341, 8]  
📋 DEAL WITH PRIMARY COMPANY: 18462 GIO INTERNATIONAL LLC [11, 341]
Revenue → Maria Florencia Peña - Estudio
```

#### Deal 18463 (NEWMORE HOLDING LTD) - Client Primary (After Restoration)
```
✅ PRIMARY: 18463 NEWMORE HOLDING LTD [5, 341]
📋 ESTUDIO CONTABLE: Maria Florencia Peña - Estudio [8, 341]
Revenue → 18463 NEWMORE HOLDING LTD
```

### ⚠️ Troubleshooting

#### Issue: typeId 8 Missing After API Changes
**Cause**: HubSpot API limitation  
**Solution**: 
1. Add manually via HubSpot UI
2. Go to Deal → Companies section
3. Edit Maria Florencia Peña - Estudio association
4. Add "Estudio Contable / Asesor / Consultor Externo del negocio" label

#### Issue: SMB Company Missing "Deal with Primary Company" Label
**Cause**: HubSpot API limitation - typeId 11 cannot be created via API  
**Solution**: 
1. Accept basic association [341] for API-only changes
2. Add "Deal with Primary Company" label manually via HubSpot UI if needed
3. Core revenue attribution works correctly regardless

#### Issue: Revenue Not Attributed Correctly
**Cause**: Wrong company has PRIMARY association  
**Solution**: Ensure the company that should receive revenue attribution has typeId 5 (PRIMARY)

---