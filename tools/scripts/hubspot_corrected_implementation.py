#!/usr/bin/env python3
"""
HubSpot First Deal Won Date - Corrected Implementation
=====================================================

This script provides the correct implementation approach for HubSpot's
actual formula field limitations and workflow capabilities.
"""

def create_corrected_implementation():
    """Create corrected implementation guide for HubSpot limitations"""
    
    print("🎯 CORRECTED HUBSPOT IMPLEMENTATION APPROACH")
    print("=" * 50)
    
    print("""
## ❌ WHAT DOESN'T WORK IN HUBSPOT

- JavaScript syntax in formula fields
- Complex MIN/FILTER functions with associations
- Direct filtering of associated deals in formulas
- Advanced conditional logic in formulas

## ✅ RECOMMENDED APPROACH: WORKFLOW-BASED SOLUTION

### Step 1: Create Custom Property
1. Go to Settings → Properties → Company Properties
2. Create new property:
   - Name: "First Deal Won Date"
   - Internal Name: first_deal_won_date
   - Field Type: Date picker
   - Description: "Date of first deal won as primary company"

### Step 2: Create Primary Workflow
**Workflow Name**: "Set First Deal Won Date"

**Enrollment Trigger**: Deal-based workflow
- Trigger: Deal stage changes to "Closed Won" OR "34692158"
- Additional Conditions:
  - Deal is associated with a company
  - Company.first_deal_won_date is empty

**Actions**:
1. Set Company.first_deal_won_date = Deal.closedate
2. Send notification (optional)

### Step 3: Create Refresh Workflow
**Workflow Name**: "Refresh First Deal Won Date"

**Enrollment Trigger**: Deal stage changes FROM "Closed Won"
- Actions:
  1. Find all remaining closed won deals for the company
  2. Set first_deal_won_date = earliest remaining date
  3. If no deals exist: Clear first_deal_won_date

## 🔧 ALTERNATIVE: SIMPLE FORMULA FIELD

If you want to try a formula field (with limitations):

### Formula Field Setup
- Name: "First Deal Won Date"
- Internal Name: first_deal_won_date
- Field Type: Formula
- Formula Type: Date

### HubSpot Formula Syntax
```
MIN(ASSOCIATED_DEALS.closedate)
```

**Limitations**:
- Cannot filter by deal stage
- Cannot filter by association type
- Will include ALL associated deals (won and lost)

## 🎯 HYBRID APPROACH (RECOMMENDED)

### Implementation Strategy:
1. Primary: Workflow-based approach for accuracy
2. Backup: Simple formula field for validation
3. Monitoring: Regular data quality checks

### Components:
1. Workflow Property: first_deal_won_date (workflow-managed)
2. Formula Property: first_deal_won_date_formula (validation)
3. Validation Script: Compare both values

## 📋 DETAILED WORKFLOW CONFIGURATION

### Workflow 1: "Set First Deal Won Date"

**Enrollment Trigger**:
```
Deal stage = "Closed Won" OR "34692158"
AND
Company.first_deal_won_date is empty
```

**Actions**:
```
1. Set Company.first_deal_won_date = Deal.closedate
2. Send notification to admin (optional)
```

### Workflow 2: "Refresh First Deal Won Date"

**Enrollment Trigger**:
```
Deal stage changes FROM "Closed Won" to any other stage
```

**Actions**:
```
1. Find all remaining closed won deals for the company
2. If deals exist: Set first_deal_won_date = earliest date
3. If no deals exist: Clear first_deal_won_date
```

## 🚨 WORKFLOW LIMITATIONS & SOLUTIONS

### Limitation 1: Cannot Find Earliest Date Directly
**Problem**: HubSpot workflows can't directly find the earliest date
**Solution**: Use enrollment conditions to only set on first deal

### Limitation 2: Multiple Deals Closing Simultaneously
**Problem**: Race conditions with multiple deals
**Solution**: Add delay and enrollment conditions

### Limitation 3: Deal Reassignment
**Problem**: Workflow doesn't automatically recalculate
**Solution**: Create separate refresh workflow

## 📊 TESTING SCENARIOS

### Test Case 1: New Company with First Deal
1. Create test company
2. Create deal, associate as primary
3. Mark deal as closed won
4. Verify first_deal_won_date is set correctly

### Test Case 2: Multiple Deals per Company
1. Company with existing closed won deal
2. Create second deal, mark as closed won
3. Verify first_deal_won_date remains unchanged
4. Test with earlier close date

### Test Case 3: Deal Reassignment
1. Deal marked as closed won for Company A
2. Reassign deal to Company B
3. Verify Company A's date is cleared/updated
4. Verify Company B's date is set correctly

### Test Case 4: Mistakenly Marked Deal
1. Deal marked as closed won by mistake
2. Change deal stage back to open
3. Verify first_deal_won_date is cleared
4. Test recalculation logic

## 🔍 MONITORING & VALIDATION

### Weekly Data Quality Checks
1. Companies with first_deal_won_date but no closed won deals
2. Companies with closed won deals but no first_deal_won_date
3. Workflow enrollment counts and errors

### Monthly Performance Review
1. Compare workflow vs formula field results
2. Check for data inconsistencies
3. Review workflow performance and optimization

## 📞 IMPLEMENTATION STEPS

### Phase 1: Setup (Week 1)
1. Create custom property: first_deal_won_date
2. Create primary workflow: "Set First Deal Won Date"
3. Test with existing companies

### Phase 2: Advanced Features (Week 2)
1. Create refresh workflow: "Refresh First Deal Won Date"
2. Test edge cases and error scenarios
3. Add monitoring and notifications

### Phase 3: Validation (Week 3)
1. Data quality checks and validation
2. Performance monitoring
3. Documentation and team training

## 🎯 RECOMMENDED IMPLEMENTATION FOR COLLPY

**Primary Recommendation**: Workflow-Based Approach

**Reasons**:
1. Works within HubSpot's actual limitations
2. Handles primary association correctly
3. Can be customized for Colppy's specific needs
4. Provides audit trail and monitoring
5. Handles edge cases through multiple workflows

**Implementation Steps**:
1. Create custom property with workflow management
2. Set up primary workflow for new deals
3. Set up refresh workflow for deal updates
4. Test with existing Colppy data
5. Monitor and optimize performance

This approach works within HubSpot's actual capabilities while providing
the functionality you need for tracking first deal won dates.
""")

if __name__ == "__main__":
    create_corrected_implementation()
