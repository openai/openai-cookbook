# Company-Centric Model: Tracking Customer Transitions in HubSpot

## 🎯 THE SOLUTION: `hs_date_entered_customer` Field

To answer **"How many customers do I have during a month?"** in a company-centric model, HubSpot provides the perfect field:

### ✅ **KEY FIELD DISCOVERED**
- **API Property Name**: `hs_date_entered_customer`
- **UI Label**: "Date entered 'Cliente (Lifecycle Stage Pipeline)'"
- **Type**: datetime
- **Purpose**: Tracks the exact timestamp when a company transitions to "Cliente" (Customer) lifecycle stage

## 📊 JULY 2025 ANALYSIS RESULTS

Using this field, we found:
- **125 companies** became customers in July 2025
- **829 total new customers** from January-July 2025

### Monthly Breakdown (2025):
```
January:    68 new customers
February:  205 new customers (peak month)
March:      61 new customers
April:      83 new customers
May:        96 new customers
June:      191 new customers
July:      125 new customers
```

## 🔍 CRITICAL INSIGHTS FROM ANALYSIS

### 1. **Data Quality Issues Found**
- **59.2%** of companies becoming customers have NO TYPE classification
- Only **22.4%** are properly classified as "Contador Robado"
- Only **12.8%** are classified as "Cuenta Contador"
- **2.4%** are classified as "Cuenta Pyme"

**Impact**: Cannot properly segment customer acquisition by channel without fixing Type field

### 2. **Customer Journey Metrics**
- **Average Lead → Customer**: 240 days
- **Average Opportunity → Customer**: 37 days
- Most companies skip traditional lifecycle stages and jump directly to customer

### 3. **Accountant Channel Dominance**
From the companies with proper Type classification:
- **35.2%** are accountant-related (Contador Robado + Cuenta Contador)
- This aligns with your accountant channel strategy

## 📋 HOW TO IMPLEMENT COMPANY-CENTRIC REPORTING

### 1. **Monthly New Customer Report**
```sql
-- Pseudo-query for monthly customers
SELECT COUNT(*) as new_customers
FROM companies
WHERE hs_date_entered_customer >= '2025-07-01'
  AND hs_date_entered_customer < '2025-08-01'
  AND lifecyclestage = 'customer'
```

### 2. **Customer Cohort Analysis**
Track cohorts by the month they became customers:
- July 2025 Cohort: 125 companies
- June 2025 Cohort: 191 companies
- etc.

### 3. **Churn Tracking**
Use `hs_date_exited_customer` to track when companies stop being customers

### 4. **Channel Performance**
Once Type field is fixed, segment by:
- Accountant channel (Cuenta Contador, Contador Robado)
- Direct sales (Cuenta Pyme)
- Administered accounts (Empresa Administrada)

## 🚨 IMMEDIATE ACTION ITEMS

### PRIORITY 1: Fix Company Type Classification
- **74 companies** (59.2%) that became customers in July have no Type
- These need classification to properly track channel performance

### PRIORITY 2: Create Company-Centric Dashboards
Build reports using `hs_date_entered_customer` to show:
1. Monthly new customer acquisition
2. Customer acquisition by channel (once Types are fixed)
3. Cohort retention analysis
4. Velocity metrics (time to convert)

### PRIORITY 3: Automate Type Assignment
Create workflows to automatically set Company Type based on:
- Association labels (e.g., Type 8 = Accountant)
- Deal properties
- Company name patterns

## 🎯 BENEFITS OF THIS APPROACH

1. **Accurate Customer Counting**: Know exactly when each company becomes a customer
2. **Cohort Analysis**: Track customer behavior by acquisition month
3. **Channel Attribution**: Understand which channels drive customer acquisition
4. **Velocity Tracking**: Measure how fast companies move through the funnel
5. **Churn Prevention**: Identify when customers are at risk

## 📊 ADDITIONAL FIELDS FOR COMPREHENSIVE TRACKING

| Field | Purpose |
|-------|---------|
| `hs_date_entered_customer` | When became customer |
| `hs_date_exited_customer` | When stopped being customer |
| `hs_time_in_customer` | Duration as customer |
| `hs_date_entered_opportunity` | When became opportunity |
| `hs_date_entered_lead` | When became lead |

## 💡 RECOMMENDATION

Implement a **Company Health Score** that combines:
- Time as customer (`hs_time_in_customer`)
- Number of associated deals
- Revenue generated
- Product adoption (Colppy vs Sueldos)

This will enable proactive customer success and reduce churn.

---

**✅ CONCLUSION**: HubSpot's `hs_date_entered_customer` field provides everything needed for company-centric customer tracking. The main challenge is improving data quality (Type classification) to enable proper channel analysis.