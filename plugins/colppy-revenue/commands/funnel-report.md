---
name: funnel-report
description: Generate a funnel analysis report for accountant and/or SMB channels. Analyzes MQL → Deal Created → Won conversion rates with ICP segmentation.
---

# Funnel Report

Generate a comprehensive funnel analysis for Colppy's sales channels.

## Steps

1. **Ask which channel(s)** to analyze:
   - Accountant channel (MQL Contador → Deal → Won)
   - SMB channel (MQL PYME → Deal → Won)
   - Both channels comparison

2. **Ask for time period**:
   - Specific month (e.g., 2025-12)
   - Multiple months for comparison
   - Custom date range

3. **Pull funnel data** from HubSpot:
   - MQL contacts created in period (filtered by `rol_wizard` for channel)
   - Deals created in period associated with those MQLs
   - Deals closed won in period (both createdate and closedate in range)
   - SQL metrics as informational (contacts entering Opportunity with deals)

4. **Classify by ICP**:
   - ICP Operador: PRIMARY company type in `['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']`
   - ICP PYME: All other primary company types

5. **Present results** in markdown tables:
   - Stage counts and conversion rates
   - MQL→Deal, Deal→Won, MQL→Won rates
   - ICP breakdown
   - Month-over-month comparison if multiple periods

6. **Flag data quality issues**:
   - Deals without primary company
   - Contacts without owners
   - Edge cases (deals created before contacts, etc.)
