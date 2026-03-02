#!/usr/bin/env python3
"""
HubSpot First Deal Won Date Implementation Guide
===============================================

This document provides a comprehensive solution for tracking the date and time
of the first deal WON associated with a company as the primary deal, with automatic
refresh capabilities when deals are updated or reassigned.

Based on HubSpot best practices and Colppy's CRM configuration.
"""

def create_implementation_guide():
    """Create comprehensive implementation guide"""
    
    print("🎯 HUBSPOT FIRST DEAL WON DATE IMPLEMENTATION GUIDE")
    print("=" * 60)
    
    print("""
## 📋 SOLUTION OVERVIEW

**Objective**: Track the date and time of the first deal WON associated with a company
as the primary deal, with automatic refresh capabilities.

**Requirements**:
- Track first deal won date at company level
- Handle primary deal associations correctly
- Refresh when deals are reassigned or updated
- Handle mistakes (deals marked won incorrectly)

## 🏗️ RECOMMENDED IMPLEMENTATION APPROACH

### Option 1: HubSpot Formula Field (RECOMMENDED)
**Best for**: Automatic calculation, always up-to-date, handles reassignments

### Option 2: HubSpot Workflow + Custom Property
**Best for**: More control, custom logic, audit trail

### Option 3: Hybrid Approach
**Best for**: Maximum reliability with fallback mechanisms

## 🎯 OPTION 1: FORMULA FIELD IMPLEMENTATION (RECOMMENDED)

### Step 1: Create Formula Field
1. Go to Settings → Properties → Company Properties
2. Create new property:
   - **Name**: "First Deal Won Date"
   - **Internal Name**: `first_deal_won_date`
   - **Field Type**: Formula
   - **Formula Type**: Date

### Step 2: Formula Logic
```javascript
// Formula to find earliest closed won deal date for primary company
MIN(
  FILTER(
    ASSOCIATED_DEALS.closedate,
    AND(
      ASSOCIATED_DEALS.dealstage = "closedwon",
      ASSOCIATED_DEALS.association_type = "primary"
    )
  )
)
```

### Step 3: Alternative Formula (if association filtering not available)
```javascript
// Fallback formula using deal stage only
MIN(
  FILTER(
    ASSOCIATED_DEALS.closedate,
    ASSOCIATED_DEALS.dealstage = "closedwon"
  )
)
```

**Advantages**:
- ✅ Always up-to-date automatically
- ✅ Handles reassignments without manual intervention
- ✅ No workflow maintenance required
- ✅ Handles mistakes automatically (recalculates)

**Limitations**:
- ❌ May not filter by primary association (HubSpot limitation)
- ❌ Formula complexity limitations

## 🔄 OPTION 2: WORKFLOW + CUSTOM PROPERTY IMPLEMENTATION

### Step 1: Create Custom Property
1. Go to Settings → Properties → Company Properties
2. Create new property:
   - **Name**: "First Deal Won Date"
   - **Internal Name**: `first_deal_won_date`
   - **Field Type**: Date picker
   - **Description**: "Date of first deal won as primary company"

### Step 2: Create Workflow
**Workflow Name**: "Update First Deal Won Date"

**Trigger**: Deal-based workflow
- **Enrollment Trigger**: Deal stage changes to "Closed Won"
- **Additional Conditions**: 
  - Deal is associated with a company
  - Company has PRIMARY association (typeId 5)

**Actions**:
1. **Check if First Deal Won Date is empty**
   - If empty: Set First Deal Won Date = Deal Close Date
   - If not empty: Compare dates and update if earlier

**Workflow Logic**:
```
IF company.first_deal_won_date IS EMPTY:
  SET company.first_deal_won_date = deal.closedate
ELSE IF deal.closedate < company.first_deal_won_date:
  SET company.first_deal_won_date = deal.closedate
```

### Step 3: Handle Deal Updates
**Additional Workflow**: "Refresh First Deal Won Date"

**Trigger**: Deal stage changes FROM "Closed Won"
- **Actions**: Recalculate first deal won date for company

**Logic**:
1. Find all closed won deals for the company
2. Find the earliest close date
3. Update company.first_deal_won_date

## 🔧 OPTION 3: HYBRID APPROACH (MAXIMUM RELIABILITY)

### Implementation Strategy:
1. **Primary**: Formula field for automatic updates
2. **Backup**: Workflow for complex scenarios
3. **Validation**: Regular data quality checks

### Components:
1. **Formula Field**: `first_deal_won_date_formula`
2. **Custom Property**: `first_deal_won_date_manual`
3. **Workflow**: Updates manual field when needed
4. **Validation Script**: Ensures data consistency

## 📊 IMPLEMENTATION STEPS FOR COLLPY

### Phase 1: Setup (Week 1)
1. **Create Formula Field**
   - Name: "First Deal Won Date"
   - Internal: `first_deal_won_date`
   - Type: Formula (Date)

2. **Test Formula**
   - Verify with existing companies
   - Check data accuracy
   - Document any limitations

### Phase 2: Workflow Implementation (Week 2)
1. **Create Primary Workflow**
   - Trigger: Deal stage → Closed Won
   - Action: Update company property
   - Conditions: Primary association check

2. **Create Refresh Workflow**
   - Trigger: Deal stage changes FROM Closed Won
   - Action: Recalculate company property

### Phase 3: Validation & Testing (Week 3)
1. **Data Quality Check**
   - Compare formula vs workflow results
   - Identify discrepancies
   - Fix data inconsistencies

2. **Edge Case Testing**
   - Multiple deals per company
   - Deal reassignments
   - Mistakenly marked deals

## 🎯 SPECIFIC FORMULA FOR COLLPY'S CRM

Based on your HubSpot configuration, here's the recommended formula:

```javascript
// Primary formula - finds earliest closed won deal date
MIN(
  FILTER(
    ASSOCIATED_DEALS.closedate,
    AND(
      ASSOCIATED_DEALS.dealstage = "closedwon",
      ASSOCIATED_DEALS.pipeline = "default"
    )
  )
)
```

**Alternative for Recovery Deals**:
```javascript
// Include recovery deals (stage 34692158)
MIN(
  FILTER(
    ASSOCIATED_DEALS.closedate,
    ASSOCIATED_DEALS.dealstage IN ("closedwon", "34692158")
  )
)
```

## 🔍 WORKFLOW CONFIGURATION DETAILS

### Workflow 1: "Set First Deal Won Date"
**Enrollment Trigger**:
- Deal stage = "Closed Won" OR "34692158" (Recovery)
- Deal pipeline = "default"

**Actions**:
1. **Check Company Association**
   - Verify company has PRIMARY association (typeId 5)
   - If not, skip or log for manual review

2. **Update Property**
   - If `first_deal_won_date` is empty: Set to deal close date
   - If `first_deal_won_date` exists: Compare and update if earlier

### Workflow 2: "Refresh First Deal Won Date"
**Enrollment Trigger**:
- Deal stage changes FROM "Closed Won" to any other stage
- Deal was previously closed won

**Actions**:
1. **Recalculate Property**
   - Find all remaining closed won deals for company
   - Set `first_deal_won_date` to earliest remaining date
   - If no closed won deals remain: Clear the property

## 📋 TESTING SCENARIOS

### Test Case 1: New Company with First Deal
- Create company
- Create deal, associate as primary
- Mark deal as closed won
- Verify `first_deal_won_date` is set

### Test Case 2: Multiple Deals
- Company with existing closed won deal
- Create second deal, mark as closed won
- Verify `first_deal_won_date` remains unchanged (first deal date)

### Test Case 3: Deal Reassignment
- Deal marked as closed won
- Reassign deal to different company
- Verify both companies have correct dates

### Test Case 4: Mistakenly Marked Deal
- Deal marked as closed won by mistake
- Change deal stage back to open
- Verify `first_deal_won_date` is cleared or recalculated

## 🚨 TROUBLESHOOTING GUIDE

### Issue: Formula Not Updating
**Cause**: HubSpot formula limitations
**Solution**: Use workflow as backup

### Issue: Wrong Date Set
**Cause**: Non-primary deal association
**Solution**: Add association type check to workflow

### Issue: Multiple Dates for Same Company
**Cause**: Workflow running multiple times
**Solution**: Add condition to prevent overwriting earlier dates

## 📊 MONITORING & MAINTENANCE

### Weekly Checks:
1. **Data Quality Report**
   - Companies with `first_deal_won_date` but no closed won deals
   - Companies with closed won deals but no `first_deal_won_date`

2. **Workflow Performance**
   - Check workflow enrollment counts
   - Monitor for errors or failures

### Monthly Reviews:
1. **Formula Accuracy**
   - Compare formula results with manual verification
   - Update formula if needed

2. **Process Optimization**
   - Review workflow efficiency
   - Optimize conditions and actions

## 🎯 RECOMMENDED IMPLEMENTATION FOR COLLPY

**Primary Recommendation**: Formula Field Approach

**Reasons**:
1. **Automatic Updates**: Always current without maintenance
2. **Handles Reassignments**: Recalculates when deals move between companies
3. **Handles Mistakes**: Automatically corrects when deals are unmarked
4. **Low Maintenance**: No workflow management required
5. **Performance**: Calculated on-demand, no storage overhead

**Implementation Steps**:
1. Create formula field with recommended formula
2. Test with existing data
3. Monitor for accuracy
4. Add workflow as backup if needed

**Fallback Plan**: If formula has limitations, implement workflow approach as primary method.

## 📞 NEXT STEPS

1. **Review and Approve**: This implementation approach
2. **Create Formula Field**: Using recommended formula
3. **Test Implementation**: With existing Colppy data
4. **Monitor Results**: For accuracy and performance
5. **Document Process**: For team reference

This solution provides a robust, maintainable approach to tracking first deal won dates while handling all the edge cases you mentioned.
""")

if __name__ == "__main__":
    create_implementation_guide()
