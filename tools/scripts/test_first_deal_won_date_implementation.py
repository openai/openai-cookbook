#!/usr/bin/env python3
"""
HubSpot First Deal Won Date - Implementation Testing Script
===========================================================

This script helps test and validate the implementation of tracking
the first deal won date at company level in HubSpot.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any

def test_first_deal_won_date_implementation():
    """Test the first deal won date implementation"""
    
    print("🧪 TESTING FIRST DEAL WON DATE IMPLEMENTATION")
    print("=" * 55)
    
    print("""
## 🎯 IMPLEMENTATION TESTING CHECKLIST

### Phase 1: Formula Field Testing
□ Create formula field: "First Deal Won Date"
□ Internal name: `first_deal_won_date`
□ Field type: Formula (Date)
□ Test formula with existing companies
□ Verify accuracy against manual calculation

### Phase 2: Workflow Testing
□ Create workflow: "Update First Deal Won Date"
□ Test enrollment trigger: Deal stage → Closed Won
□ Test action: Update company property
□ Test edge cases: Multiple deals, reassignments
□ Test mistake handling: Deal unmarked as won

### Phase 3: Data Validation
□ Compare formula vs workflow results
□ Check for data inconsistencies
□ Validate primary association handling
□ Test with accountant channel companies

## 🔍 TESTING SCENARIOS

### Scenario 1: New Company with First Deal
1. Create test company
2. Create deal, associate as primary
3. Mark deal as closed won
4. Verify first_deal_won_date is set correctly

### Scenario 2: Multiple Deals per Company
1. Company with existing closed won deal
2. Create second deal, mark as closed won
3. Verify first_deal_won_date remains unchanged
4. Test with earlier close date

### Scenario 3: Deal Reassignment
1. Deal marked as closed won for Company A
2. Reassign deal to Company B
3. Verify Company A's date is cleared/updated
4. Verify Company B's date is set correctly

### Scenario 4: Mistakenly Marked Deal
1. Deal marked as closed won by mistake
2. Change deal stage back to open
3. Verify first_deal_won_date is cleared
4. Test recalculation logic

## 📊 VALIDATION QUERIES

### Query 1: Companies with First Deal Won Date
```sql
-- Find companies with first_deal_won_date set
SELECT 
    company_id,
    company_name,
    first_deal_won_date,
    num_associated_deals
FROM companies 
WHERE first_deal_won_date IS NOT NULL
ORDER BY first_deal_won_date DESC
```

### Query 2: Data Quality Check
```sql
-- Find inconsistencies
SELECT 
    c.company_id,
    c.company_name,
    c.first_deal_won_date,
    COUNT(d.deal_id) as closed_won_deals,
    MIN(d.closedate) as earliest_closed_won_date
FROM companies c
LEFT JOIN deals d ON c.company_id = d.company_id 
    AND d.dealstage IN ('closedwon', '34692158')
    AND d.association_type = 'primary'
GROUP BY c.company_id, c.company_name, c.first_deal_won_date
HAVING c.first_deal_won_date != MIN(d.closedate)
```

### Query 3: Accountant Channel Companies
```sql
-- Test with accountant channel companies
SELECT 
    c.company_id,
    c.company_name,
    c.type,
    c.first_deal_won_date,
    COUNT(d.deal_id) as accountant_deals
FROM companies c
LEFT JOIN deal_company_associations dca ON c.company_id = dca.company_id
LEFT JOIN deals d ON dca.deal_id = d.deal_id
WHERE c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
    AND dca.association_type_id = 8  -- Estudio Contable
GROUP BY c.company_id, c.company_name, c.type, c.first_deal_won_date
```

## 🚨 COMMON ISSUES & SOLUTIONS

### Issue 1: Formula Not Calculating
**Symptoms**: Field shows empty or incorrect values
**Solutions**:
- Check formula syntax
- Verify deal stage values ('closedwon', '34692158')
- Test with simple formula first
- Check HubSpot formula limitations

### Issue 2: Wrong Date Set
**Symptoms**: Date doesn't match earliest closed won deal
**Solutions**:
- Verify primary association (typeId 5)
- Check deal pipeline filter
- Test with manual calculation
- Review workflow conditions

### Issue 3: Multiple Dates for Same Company
**Symptoms**: Company has multiple first_deal_won_date values
**Solutions**:
- Check workflow enrollment conditions
- Add condition to prevent overwriting
- Review deal association logic
- Test with single deal per company

### Issue 4: Performance Issues
**Symptoms**: Slow formula calculation or workflow execution
**Solutions**:
- Optimize formula complexity
- Review workflow enrollment volume
- Check for circular references
- Monitor HubSpot API limits

## 📋 IMPLEMENTATION CHECKLIST

### Pre-Implementation
□ Review HubSpot formula field limitations
□ Check existing company properties
□ Verify deal stage values in production
□ Test with small dataset first

### Implementation
□ Create formula field with recommended formula
□ Test formula with existing companies
□ Create workflow as backup
□ Test workflow enrollment and actions
□ Validate data accuracy

### Post-Implementation
□ Monitor formula calculation performance
□ Check for data inconsistencies
□ Test edge cases and error scenarios
□ Document any limitations or workarounds
□ Train team on new field usage

## 🎯 RECOMMENDED FORMULA FOR COLLPY

Based on your HubSpot configuration:

```javascript
// Primary formula - includes recovery deals
MIN(
  FILTER(
    ASSOCIATED_DEALS.closedate,
    ASSOCIATED_DEALS.dealstage IN ("closedwon", "34692158")
  )
)
```

**Alternative with pipeline filter**:
```javascript
// Include pipeline filter for accuracy
MIN(
  FILTER(
    ASSOCIATED_DEALS.closedate,
    AND(
      ASSOCIATED_DEALS.dealstage IN ("closedwon", "34692158"),
      ASSOCIATED_DEALS.pipeline = "default"
    )
  )
)
```

## 📊 MONITORING DASHBOARD QUERIES

### Weekly Data Quality Report
```sql
-- Companies with first_deal_won_date but no closed won deals
SELECT 
    company_id,
    company_name,
    first_deal_won_date,
    'No closed won deals' as issue
FROM companies 
WHERE first_deal_won_date IS NOT NULL
    AND company_id NOT IN (
        SELECT DISTINCT company_id 
        FROM deals d
        JOIN deal_company_associations dca ON d.deal_id = dca.deal_id
        WHERE d.dealstage IN ('closedwon', '34692158')
    )
```

### Monthly Performance Review
```sql
-- Companies with closed won deals but no first_deal_won_date
SELECT 
    c.company_id,
    c.company_name,
    COUNT(d.deal_id) as closed_won_deals,
    MIN(d.closedate) as earliest_deal_date
FROM companies c
JOIN deal_company_associations dca ON c.company_id = dca.company_id
JOIN deals d ON dca.deal_id = d.deal_id
WHERE d.dealstage IN ('closedwon', '34692158')
    AND c.first_deal_won_date IS NULL
GROUP BY c.company_id, c.company_name
```

## 🔧 TROUBLESHOOTING COMMANDS

### Test Formula Field
```python
# Test formula field with sample data
def test_formula_field():
    # Implementation for testing formula field
    pass
```

### Validate Workflow
```python
# Test workflow enrollment and actions
def test_workflow():
    # Implementation for testing workflow
    pass
```

### Data Quality Check
```python
# Check for data inconsistencies
def data_quality_check():
    # Implementation for data validation
    pass
```

## 📞 NEXT STEPS

1. **Create Formula Field**: Use recommended formula
2. **Test Implementation**: With existing Colppy data
3. **Create Workflow**: As backup mechanism
4. **Validate Results**: Compare formula vs manual calculation
5. **Monitor Performance**: Check for issues and optimizations
6. **Document Process**: For team reference and maintenance

This testing framework ensures a robust implementation that handles all edge cases
while maintaining data accuracy and performance.
""")

if __name__ == "__main__":
    test_first_deal_won_date_implementation()
