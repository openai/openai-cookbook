---
name: business-context
description: Colppy business context including company overview, market position, key metrics, terminology glossary, and platform integrations. Always apply as foundational context for any Colppy-related analysis or question. For detailed definitions and API patterns, read the docs/ folder (see docs-reference skill).
---

# Business Context — Colppy

Foundational context for Colppy.com. This skill provides the business background for all analysis and recommendations.

---

## Company Overview

| Field | Value |
|-------|-------|
| **Company** | Colppy.com |
| **Product** | SaaS B2B accounting software |
| **Market** | Argentina (SMBs and accountants) |
| **Holding** | Part of SUMA SaaS holding |
| **Investor** | Riverwood Capital |
| **Products** | Colppy (accounting) + Sueldos (payroll) |

---

## Business Model

### Two ICP Segments
1. **ICP Operador** (Accountant billing): We bill the accountant who operates Colppy for their clients
2. **ICP PYME** (SMB billing): We bill the SMB directly

### Key Channel: Canal Contador
- Accountants refer SMBs to Colppy
- Accountants can also operate Colppy on behalf of their clients
- Channel tracked via HubSpot association type 8 and owner team assignments
- Separate funnel analysis for accountant vs SMB channels

---

## Key Metrics

| Metric | Description |
|--------|-------------|
| **MRR/ARR** | Monthly/Annual Recurring Revenue |
| **Conversion Rate** | MQL → Deal → Won (strict funnel path) |
| **PQL Rate** | Product Qualified Lead rate from Mixpanel signals |
| **Contactability** | Time to first contact for scored leads |
| **Deal Cycle Time** | Time from deal creation to close |
| **Score Distribution** | HubSpot contact scores across ranges |

---

## Glossary

| Term | Definition |
|------|-----------|
| **Operador** | Accountant who operates Colppy on behalf of clients |
| **Canal Contador** | Accountant channel — accountants who refer or operate for SMBs |
| **CUIT** | Argentine tax identification number (mapped to companies in HubSpot) |
| **Primary Company** | Company with association type 5 on a deal — source of truth for billing |
| **PQL** | Product Qualified Lead — determined by product usage signals in Mixpanel |
| **MQL** | Marketing Qualified Lead — determined by signup wizard role |
| **SQL** | Sales Qualified Lead — enters Opportunity stage with deal associated |
| **Cuenta Contador** | HubSpot company type for accountant firms |
| **Cuenta Pyme** | HubSpot company type for SMBs |
| **Contador Robado** | Accountant discovered through an SMB client |
| **Estudio Contable** | Accounting firm (association type 8 label) |
| **id_empresa** | Colppy database company ID, links HubSpot to Colppy DB |
| **rol_wizard** | Signup wizard role — determines MQL channel (accountant vs SMB) |
| **Sueldos** | Colppy's payroll product (separate product family) |

---

## Platform Integrations

| Platform | Purpose | Integration |
|----------|---------|-------------|
| **HubSpot** | CRM — deals, contacts, companies, workflows | MCP + API scripts |
| **Mixpanel** | Product analytics — events, funnels, retention, PQL | MCP + API scripts |
| **Intercom** | Customer support — conversations, NPS | API scripts |
| **Google Ads** | Advertising — campaigns, conversions | MCP |
| **Meta Ads** | Advertising — campaigns | Scripts |
| **Slack** | Team communication | MCP |
| **Jira/Confluence** | Project management, documentation | MCP |
| **Fellow** | Meeting notes and recordings | MCP |
| **Colppy Database** | MySQL production DB — billing, empresa data | ORM package |

---

## Analysis Scripts Location

```
tools/scripts/
├── hubspot/     # 39 scripts — funnel, scoring, PQL, ICP, deals
├── mixpanel/    # 77 scripts — events, companies, users, engagement
├── intercom/    # 32 scripts — NPS, conversations, taxonomy
├── atlassian/   # Jira/Confluence scripts
├── fellow/      # Meeting integration
└── meta_ads/    # Meta Ads scripts
```

---

## Documentation Location

All detailed docs in `tools/docs/` (42 markdown files covering HubSpot, Mixpanel, Intercom, Google Ads, GTM, funnels, ICP, scoring, PQL, and more).
