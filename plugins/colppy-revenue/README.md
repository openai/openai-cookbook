# Colppy Revenue Plugin

Revenue analytics for **Colppy.com** — demand generation, marketing funnels, ICP scoring, MRR dashboards, churn analysis, cohort retention, growth KPIs, and multi-platform analytics.

## Skills (Automatic Context)

| Skill | What It Provides |
|-------|-----------------|
| **business-context** | Company overview, glossary, platform integrations, metrics |
| **icp-classification** | ICP Operador vs PYME rules, company types, deal associations |
| **hubspot-configuration** | CRM field mappings, Lead definitions, API rules, associations |
| **funnel-analysis** | MQL→Deal→Won funnel stages, PQL analysis, scoring |
| **hubspot-api-patterns** | API package usage, query builder, pagination, common operations |
| **mixpanel-analytics** | Product analytics, PQL signals, engagement, session replays |
| **funnel-definitions** | MQL/PQL/SQL stage definitions, HubSpot field mappings |
| **mrr-analysis** | MRR waterfall workflow, revenue trends, Net New MRR |
| **building-blocks-budget** | Fetch, query, dashboard from Building Blocks budget (Budget vs Actual MRR, ASP). Uses Google Sheets registry — no URL needed. |
| **cohort-retention** | Retention tables, heatmaps, survival curves |
| **saas-metrics-conventions** | Metric definitions, Argentina formatting, data sources |
| **docs-reference** | Index of all bundled docs — when to read which file from `docs/` |

## Commands (Slash Commands)

### SaaS Metrics
| Command | Description |
|---------|-------------|
| `/colppy-revenue:mrr-report` | Generate MRR waterfall report |
| `/colppy-revenue:budget-dashboard` | Refresh, query, or generate Building Blocks Budget vs Actual dashboard |
| `/colppy-revenue:dashboard-refresh` | Refresh MRR, ICP, and Building Blocks dashboards (outputs commands to run locally) |
| `/colppy-revenue:churn-analysis` | Analyze logo and revenue churn |
| `/colppy-revenue:growth-kpis` | CEO-level growth KPI summary |

### Funnel & HubSpot
| Command | Description |
|---------|-------------|
| `/colppy-revenue:funnel-report` | Full funnel analysis for accountant/SMB channels |
| `/colppy-revenue:icp-check` | Classify deals as ICP Operador or PYME |
| `/colppy-revenue:scoring-review` | Review scoring and contactability metrics |
| `/colppy-revenue:sql-conversion` | MQL→SQL conversion rates, cycle times |
| `/colppy-revenue:monthly-pql` | PQL rate per month with trends |
| `/colppy-revenue:pql-sql-analysis` | PQL→SQL timing (product-led vs sales-led) |
| `/colppy-revenue:icp-analysis` | Closed-won ICP Operador breakdown |
| `/colppy-revenue:lead-scoring` | High-score lead handling analysis |
| `/colppy-revenue:smb-mql-funnel` | Full SMB MQL funnel |
| `/colppy-revenue:smb-accountant-comparison` | Compare SMB funnel WITH vs WITHOUT accountant (pass dates) |
| `/colppy-revenue:referral-funnel` | Accountant referral pipeline |
| `/colppy-revenue:sales-ramp` | Sales rep ramp cohort analysis |

## Agents

| Agent | Description |
|-------|-------------|
| **saas-metrics-analyst** | Specialized agent for MRR, churn, cohort retention, growth KPIs |

## Connectors

- **HubSpot** — CRM data (deals, contacts, companies, workflows)
- **Mixpanel** — Product analytics, PQL signals
- **Slack** — Team communication
- **Atlassian** — Jira/Confluence

## Connector Setup

### HubSpot, Mixpanel, Slack, Atlassian

These connectors are configured via their respective MCP servers in `~/.cursor/mcp.json`. See each skill's SKILL.md for specific setup instructions.

## Related Plugins

| Plugin                       | Focus                                                        |
|------------------------------|--------------------------------------------------------------|
| **colppy-customer-success**  | Intercom research, onboarding analysis, LLM classification   |
| **colppy-revops**            | Billing reconciliation, Colppy-HubSpot matching, deal ops    |
| **colppy-arca**              | ARCA/AFIP tax operations, CUIT enrichment, Libro IVA         |

---

## Installation

### Zip File (Upload to Claude Cowork / Cloud AI)

**Generated zip location:** `tools/outputs/colppy-revenue-plugin-full.zip`

After any plugin change, run `./publish.sh` from this directory to regenerate the zip. Upload this zip in Cowork → Plugins → Upload plugin (or your Cloud AI platform).

### Claude (Cowork)
1. Run `./publish.sh` from this directory to build the zip
2. Upload `tools/outputs/colppy-revenue-plugin-full.zip` in Cowork → Plugins → Upload plugin

### Cursor
Add this plugin directory to your Cursor workspace. Cursor will discover the plugin from `plugins/colppy-revenue/` when the workspace root includes this path.
