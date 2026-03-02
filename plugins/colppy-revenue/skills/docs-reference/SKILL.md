---
name: docs-reference
description: ALWAYS consult for Colppy-specific questions. Source of truth for definitions, API patterns, configuration, and methodology. Read the relevant doc from docs/ before answering any question about HubSpot, MRR, churn, Mixpanel, ICP, funnel, or billing. Do not rely on general knowledge — the docs are authoritative.
---

# Documentation Reference — Colppy Revenue

**Rule:** For any Colppy-specific question (HubSpot, MRR, churn, Mixpanel, ICP, funnel, pagination, deal stages), **read the relevant doc from `docs/` first**. The docs are the source of truth — do not rely on general knowledge.

All documentation is bundled in the **`docs/`** folder (relative to the plugin root). **Default to reading** the relevant file before implementing or answering.

## When to Use Which Doc

| Need | Read |
|------|------|
| HubSpot CRM config, Lead definition, API setup | `docs/README_HUBSPOT_CONFIGURATION.md` |
| Deal–company associations, CUIT, PRIMARY, fix workflow | `docs/HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md` |
| HubSpot API retrieval patterns, search, pagination | `docs/HUBSPOT_COMPLETE_RETRIEVAL_QUICK_REFERENCE.md` |
| Pagination standards for HubSpot scripts | `docs/README_HUBSPOT_PAGINATION_STANDARDS.md` |
| MRR dashboard formulas, churn, portfolio, CAGR | `docs/MRR_DASHBOARD_DEFINITIONS.md` |
| ICP types (Operador, PYME, Contador), company definitions | `docs/ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md` |
| Mixpanel events, properties, lexicon | `docs/MIXPANEL_LEXICON_CONFIG.md`, `docs/MIXPANEL_EVENTS_CONFIG.md`, `docs/MIXPANEL_USER_PROPERTIES_CONFIG.md` |
| Mixpanel API usage | `docs/README_MIXPANEL_API.md` |
| Funnel stages, MQL/PQL/SQL mapping | `docs/COLPPY_FUNNEL_MAPPING_COMPLETE.md` |
| Contactability, scoring analysis | `docs/CONTACTABILITY_ANALYSIS.md`, `docs/HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md` |
| PQL analysis, SQL–PQL correlation | `docs/HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md`, `docs/HUBSPOT_SQL_PQL_CORRELATION_ANALYSIS.md` |
| Sales ramp cohort methodology | `docs/HUBSPOT_SALES_RAMP_COHORT_ANALYSIS.md` |
| HubSpot scripts (build, populate, fix, reconcile) | `docs/HUBSPOT_SCRIPTS_DOCUMENTATION.md` |
| first_deal_won_date, custom properties | `docs/HUBSPOT_FIRST_DEAL_WON_DATE_IMPLEMENTATION.md` |
| Google Ads MCP | `docs/README_GOOGLE_ADS_MCP.md` |
| Building Blocks budget, fetch, deviation, dashboard | `docs/BUILDING_BLOCKS_BUDGET_GUIDE.md`, `docs/GOOGLE_SHEETS_REGISTRY.json` |
| Dashboard refresh (MRR, ICP, Building Blocks) | `docs/DASHBOARD_REFRESH_GUIDE.md` |
| Numeric company names, CUIT inference | `docs/HUBSPOT_NUMERIC_COMPANY_NAME_INFERENCE.md` |
| Monthly analysis guide | `docs/HUBSPOT_MONTHLY_ANALYSIS_GUIDE.md` |

## Full Doc List (docs/)

- ACCOUNTANT_STUDIOS_IDENTIFICATION_TERMS.md
- COLPPY_2030_PROSPERITY_CALCULATION.md
- COLPPY_ENGAGEMENT_SCORE_PROPOSAL.md
- COLPPY_FUNNEL_MAPPING_COMPLETE.md
- CONTACTABILITY_ANALYSIS.md
- BUILDING_BLOCKS_BUDGET_GUIDE.md
- DASHBOARD_REFRESH_GUIDE.md
- CUIT_CREATION_DATE_LOOKUP.md
- GOOGLE_ADS_CAMPAIGN_STATUS_DOCUMENTATION.md
- GTM_CONVERSION_TRACKING_ANALYSIS.md
- GTM_PMAX_CONVERSION_TRACKING_COMPLETE_MAP.md
- HUBSPOT_COMPLETE_RETRIEVAL_QUICK_REFERENCE.md
- HUBSPOT_CUSTOM_CODE_WORKFLOW_MAPPING.md
- HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md
- HUBSPOT_FIRST_DEAL_WON_DATE_IMPLEMENTATION.md
- HUBSPOT_FUNNEL_CONTACT_TO_DEAL_METHODOLOGY.md
- HUBSPOT_LISTS_API_SUMMARY.md
- HUBSPOT_MONTHLY_ANALYSIS_GUIDE.md
- HUBSPOT_NUMERIC_COMPANY_NAME_INFERENCE.md
- HUBSPOT_PQL_ANALYSIS_DOCUMENTATION.md
- HUBSPOT_SALES_RAMP_COHORT_ANALYSIS.md
- HUBSPOT_SCORING_CONTACTABILITY_ANALYSIS.md
- HUBSPOT_SCRIPTS_DOCUMENTATION.md
- HUBSPOT_SQL_PQL_CORRELATION_ANALYSIS.md
- HUBSPOT_UTM_CAMPAIGN_SCORING_ANALYSIS.md
- ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md
- MIXPANEL_EVENTS_CONFIG.md
- MIXPANEL_LEXICON_CONFIG.md
- MIXPANEL_SESSION_RECORDING_ANALYSIS.md
- MIXPANEL_USER_PROPERTIES_CONFIG.md
- MRR_DASHBOARD_DEFINITIONS.md
- NPS_TO_ICP_DATA_FLOW.md
- GOOGLE_SHEETS_REGISTRY.json
- README_GOOGLE_ADS_MCP.md
- README_HUBSPOT_CONFIGURATION.md
- README_HUBSPOT_PAGINATION_STANDARDS.md
- README_MIXPANEL_API.md
- SQL_PQL_ANALYSIS_README.md

## How to Use

1. **Before implementing** HubSpot, Mixpanel, or billing logic → read the relevant doc from `docs/`.
2. **Path**: Always use `docs/FILENAME.md` relative to the plugin root.
3. **When in doubt**: Check `docs/README_HUBSPOT_CONFIGURATION.md` or `docs/MRR_DASHBOARD_DEFINITIONS.md` for core definitions.
