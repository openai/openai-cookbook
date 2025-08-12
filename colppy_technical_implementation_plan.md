# 🛠️ **COLPPY CRM TECHNICAL IMPLEMENTATION PLAN**
## **Company-Centric Model Migration**

### 📋 **PHASE 1: IMMEDIATE SETUP (Week 1-2)**

#### **1.1 Product Library Creation**

**Step 1: Create Product Families in HubSpot**
```bash
# Via HubSpot Product Library
Products > Create Product Family

Family 1: "Colppy - Financial Management"
- Description: "Comprehensive financial management solution for SMBs"
- Product Type: "Recurring"
- Family Code: "COLPPY"

Family 2: "Sueldos - Payroll Processing" 
- Description: "Payroll management and compliance solution"
- Product Type: "Recurring"
- Family Code: "SUELDOS"
```

**Step 2: Create Subscription Plans**
```
COLPPY FAMILY:
├── Colppy Starter
│   ├── Billing Frequency: Monthly/Annual
│   ├── Price Tiers: Based on invoice volume
│   └── Features: Basic financial management
├── Colppy Professional
│   ├── Billing Frequency: Monthly/Annual
│   ├── Advanced features
└── Colppy Plus
    ├── Includes accounting advisory
    └── Premium pricing

SUELDOS FAMILY:
├── Sueldos Basic (1-10 employees)
├── Sueldos Professional (11-50 employees)  
└── Sueldos Enterprise (50+ employees)
```

#### **1.2 Company Properties Audit**

**Execute this HubSpot API check:**
```python
# Check CUIT population across all companies
import os
from mcp_hubspot import hubspot_search_objects

def audit_company_cuit():
    """Audit CUIT field population in all companies"""
    
    companies = hubspot_search_objects(
        objectType="companies",
        properties=["name", "cuit", "createdate", "colppy_id"],
        limit=1000
    )
    
    missing_cuit = []
    for company in companies.results:
        if not company.get('properties', {}).get('cuit'):
            missing_cuit.append({
                'id': company['id'],
                'name': company.get('properties', {}).get('name'),
                'colppy_id': company.get('properties', {}).get('colppy_id')
            })
    
    print(f"Companies missing CUIT: {len(missing_cuit)}")
    return missing_cuit

# Run the audit
missing_cuit_companies = audit_company_cuit()
```

**Manual Actions Required:**
1. **Populate CUIT** for companies missing this field
2. **Verify Type field** has all 12 values from transition document
3. **Set up lifecycle automation** (see workflow below)

#### **1.3 Company Lifecycle Automation**

**Create HubSpot Workflow:**
```yaml
Workflow Name: "Company Lifecycle - Deal Won Trigger"
Object Type: Deals
Enrollment Trigger: 
  - Deal Stage = "Closed Won"
  
Actions:
  1. Update Associated Company Properties:
     - lifecyclestage = "customer"
     - hs_date_entered_customer = Deal.closedate
     - hubspot_owner_id = Deal.hubspot_owner_id
     
  2. Create Company Note:
     - "Company became customer via Deal: {Deal.dealname}"
     - Associate note with Company and Deal
```

---

### 📋 **PHASE 2: DEAL STRUCTURE CHANGES (Week 3-4)**

#### **2.1 New Deal Creation Process**

**Updated Deal Creation Workflow:**
```yaml
Step 1: Create/Associate Company (Required)
  - Verify CUIT exists and is unique
  - Set Company Type (Cuenta Pyme, Cuenta Contador, etc.)
  - Associate Deal with Company using "Primary" relationship

Step 2: Create Deal with Line Items (Required)  
  - Deal Name: "{auto_number} - {company_name}"
  - Add Line Items for products:
    * Select from Product Library (Colppy/Sueldos)
    * Set subscription terms and pricing
    * Configure MRR/ARR automatically

Step 3: Set Deal Properties
  - id_empresa = Company.colppy_id  
  - utm_*_negocio = from associated Contact
  - Product families = derived from Line Items
```

#### **2.2 Line Items Integration**

**For New Deals - Mandatory Line Items:**
```json
{
  "deal_creation_requirements": {
    "line_items": "REQUIRED",
    "product_families": ["Colppy", "Sueldos"],
    "subscription_terms": {
      "billing_frequency": ["monthly", "annual"],
      "start_date": "deal_close_date",
      "mrr_calculation": "automatic"
    }
  }
}
```

**Line Item Properties to Track:**
- `hs_product_id` → Links to Product Library
- `hs_mrr` → Monthly recurring revenue
- `hs_recurring_billing_start_date` → Subscription start
- `hs_recurring_billing_end_date` → Churn/end date
- `quantity` → Number of licenses/seats

#### **2.3 Sales Process Training**

**New Sales Team Process:**
1. **Company First**: Always create/find company by CUIT
2. **Product Selection**: Use Product Library, not free text
3. **Line Items Mandatory**: Every deal must have structured line items
4. **Association Required**: Deal must be associated with Company

---

### 📋 **PHASE 3: DATA MIGRATION (Week 5-8)**

#### **3.1 Historical Deal Analysis**

**Run this analysis script:**
```python
def analyze_existing_deals():
    """Analyze current deals for migration requirements"""
    
    # Get all deals from 2024-2025
    deals = hubspot_search_objects(
        objectType="deals",
        properties=["dealname", "amount", "closedate", "id_empresa", "plan"],
        filterGroups=[{
            "filters": [
                {"propertyName": "createdate", "operator": "GTE", "value": "2024-01-01"}
            ]
        }]
    )
    
    migration_needs = {
        "missing_company_association": [],
        "missing_line_items": [], 
        "unclear_product_family": [],
        "missing_mrr_data": []
    }
    
    for deal in deals.results:
        # Check company association
        associations = get_deal_associations(deal['id'], 'companies')
        if not associations:
            migration_needs["missing_company_association"].append(deal)
            
        # Check line items
        line_items = get_deal_line_items(deal['id'])
        if not line_items:
            migration_needs["missing_line_items"].append(deal)
            
    return migration_needs

# Execute analysis
migration_analysis = analyze_existing_deals()
```

#### **3.2 Company Consolidation Script**

**CUIT-based company deduplication:**
```python
def consolidate_companies_by_cuit():
    """Find and merge duplicate companies with same CUIT"""
    
    companies = hubspot_search_objects(
        objectType="companies",
        properties=["name", "cuit", "createdate"],
        limit=1000
    )
    
    cuit_groups = {}
    for company in companies.results:
        cuit = company.get('properties', {}).get('cuit')
        if cuit:
            if cuit not in cuit_groups:
                cuit_groups[cuit] = []
            cuit_groups[cuit].append(company)
    
    duplicates = {cuit: companies for cuit, companies in cuit_groups.items() if len(companies) > 1}
    
    print(f"Found {len(duplicates)} CUITs with duplicate companies")
    
    # Manual review required before merging
    return duplicates

# Run analysis first, then manual merge in HubSpot UI
duplicate_companies = consolidate_companies_by_cuit()
```

#### **3.3 Product Family Classification**

**Classify existing deals by product family:**
```python
def classify_deals_by_product_family():
    """Classify historical deals into Colppy/Sueldos families"""
    
    classification_rules = {
        "Sueldos": ["sueldo", "payroll", "liquidación", "legajo"],
        "Colppy": ["colppy", "financ", "contab", "factur", "invoice"]
    }
    
    deals = get_all_deals_without_line_items()
    
    for deal in deals:
        deal_name = deal.get('properties', {}).get('dealname', '').lower()
        plan = deal.get('properties', {}).get('plan', '').lower()
        
        product_family = "Colppy"  # Default
        
        # Check for Sueldos indicators
        for keyword in classification_rules["Sueldos"]:
            if keyword in deal_name or keyword in plan:
                product_family = "Sueldos"
                break
                
        # Create line item for this deal
        create_line_item_from_deal(deal, product_family)

# Execute classification
classify_deals_by_product_family()
```

---

### 📋 **PHASE 4: REPORTING & ANALYTICS (Week 9-10)**

#### **4.1 Company-Centric Dashboards**

**Dashboard 1: Customer Health**
```yaml
Name: "Company Health Dashboard"
Widgets:
  - Total Active Customers (lifecycle = customer)
  - New Customers This Month (company-based)
  - Customer MRR Trends
  - Product Family Adoption
  - Channel Attribution (Accountant/Referral/Direct)
  
Filters:
  - Date Range
  - Company Type
  - Product Family
  - Owner Team
```

**Dashboard 2: Product Performance**
```yaml
Name: "Product Family Performance"
Widgets:
  - Colppy vs Sueldos Revenue
  - Cross-sell Rate (customers with both families)
  - Upsell Progression (plan upgrades)
  - Churn by Product Family
  - ARR/MRR by Product Type
```

#### **4.2 Updated KPI Calculations**

**New Customer Metrics:**
```python
def calculate_company_metrics():
    """Calculate company-centric KPIs"""
    
    metrics = {
        # Customer counting
        "active_customers": count_companies_with_lifecycle("customer"),
        "new_customers_mtd": count_companies_became_customer_in_period("month"),
        
        # Revenue metrics  
        "total_mrr": sum_mrr_from_active_line_items(),
        "arr_by_product_family": calculate_arr_by_product_family(),
        
        # Product adoption
        "colppy_only_customers": count_customers_with_only_family("Colppy"),
        "sueldos_only_customers": count_customers_with_only_family("Sueldos"),
        "cross_sell_customers": count_customers_with_both_families(),
        
        # Channel attribution
        "accountant_channel_revenue": calculate_revenue_by_association_type(8),
        "referral_channel_revenue": calculate_revenue_by_association_type(2)
    }
    
    return metrics
```

---

### 📋 **PHASE 5: VALIDATION & ROLLOUT (Week 11-12)**

#### **5.1 Data Validation Checklist**

**Pre-Launch Validation:**
- [ ] All companies have CUIT populated
- [ ] All deals have company associations  
- [ ] All active deals have line items
- [ ] MRR/ARR calculations match previous totals
- [ ] Customer counts align between old/new methods
- [ ] Product families properly classified
- [ ] Reporting dashboards functional

#### **5.2 Team Training Schedule**

**Week 11: Sales Team Training**
- New deal creation process
- Product Library usage
- Company-first approach
- Line items mandatory setup

**Week 12: Customer Success Training**  
- Company health monitoring
- Product family upselling
- Subscription management
- Churn prevention workflows

#### **5.3 Go-Live Checklist**

**Technical Go-Live Steps:**
1. [ ] Backup current HubSpot configuration
2. [ ] Enable new workflows for deal creation
3. [ ] Deactivate old deal-centric reports
4. [ ] Activate new company-centric dashboards
5. [ ] Update integration endpoints (Mixpanel sync)
6. [ ] Monitor for 48 hours post-launch

---

### ⚡ **CRITICAL SUCCESS FACTORS**

#### **Data Quality**
- **100% CUIT coverage** for all companies
- **Complete deal-company associations** 
- **Accurate product family classification**

#### **Process Adoption**
- **Sales team trained** on new process
- **Line items used** for all new deals
- **Company-first mindset** adopted

#### **Technical Stability**
- **Reporting continuity** maintained
- **Integration stability** preserved  
- **Performance impact** minimized

---

### 🚨 **ROLLBACK PLAN**

If issues arise during migration:

**Immediate Actions:**
1. Revert to previous dashboard configurations
2. Re-enable old reporting workflows
3. Document specific failure points
4. Communicate status to stakeholders

**Recovery Steps:**
1. Restore from pre-migration backup
2. Fix identified issues in staging environment
3. Re-test migration process
4. Schedule new migration date

---

*This technical implementation plan provides step-by-step instructions for migrating Colppy's CRM to the new company-centric model while maintaining business continuity and data integrity.*