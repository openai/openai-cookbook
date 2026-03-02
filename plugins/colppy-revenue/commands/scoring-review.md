---
name: scoring-review
description: Review contact scoring and sales contactability metrics. Analyzes score 40+ contacts, contact rates, owner performance, and uncontacted leads.
---

# Scoring Review

Analyze contact scoring and sales team contactability.

## MCP Tools (Preferred When Available)

If **hubspot-analysis** MCP is configured, use these tools directly:
- **Single month**: `run_high_score_analysis(month="YYYY-MM")` — e.g. `run_high_score_analysis(month="2026-02")`
- **Current MTD**: `run_high_score_analysis(current_mtd=True)`
- **Compare two months**: `run_mtd_scoring(month1="2026-01", month2="2026-02")`
- **Visualization**: `run_visualization_report(month="2026-02")` — run high_score first

Skip to "Present in markdown tables" with the MCP output. Otherwise follow the manual steps below.

## Steps

1. **Ask for time period**: Current MTD, specific month, or custom range

2. **Pull scored contacts** from HubSpot:
   - Contacts with `hubspot_score >= 40` created in period
   - Exclude inactive owners and "Usuario Invitado" contacts
   - Include `hs_lead_status`, owner, score, lifecycle stage

3. **Analyze contactability**:
   - Contact rate: % of scored contacts that were contacted
   - Time to first contact
   - Uncontacted contacts list

4. **Owner performance**:
   - Contacts per owner
   - Contact rate by owner
   - SQL/PQL conversion rates by owner
   - Average time to contact by owner

5. **Score distribution**:
   - Breakdown by score ranges (40-49, 50-59, 60-69, 70+)
   - Conversion rates by score range

6. **Present in markdown tables** with actionable insights
