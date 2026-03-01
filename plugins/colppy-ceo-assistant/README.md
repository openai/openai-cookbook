# Colppy CEO Assistant Plugin

CEO analytics assistant for **Colppy.com** — SaaS B2B accounting software for the Argentina market.

## Skills (Automatic Context)

| Skill | What It Provides |
|-------|-----------------|
| **business-context** | Company overview, glossary, platform integrations, metrics |
| **icp-classification** | ICP Operador vs PYME rules, company types, deal associations |
| **hubspot-configuration** | CRM field mappings, Lead definitions, API rules, associations |
| **funnel-analysis** | MQL→Deal→Won funnel stages, PQL analysis, scoring |
| **hubspot-api-patterns** | API package usage, query builder, pagination, common operations |
| **mixpanel-analytics** | Product analytics, PQL signals, engagement, session replays |
| **billing-reconciliation** | Cross-reference HubSpot ICP classifications against billing data |
| **funnel-definitions** | MQL/PQL/SQL stage definitions, HubSpot field mappings |
| **mrr-analysis** | MRR waterfall workflow, revenue trends, Net New MRR |
| **building-blocks-budget** | Fetch, query, dashboard from Building Blocks budget (Budget vs Actual MRR, ASP). Uses Google Sheets registry — no URL needed. |
| **cohort-retention** | Retention tables, heatmaps, survival curves |
| **saas-metrics-conventions** | Metric definitions, Argentina formatting, data sources |
| **docs-reference** | Index of all bundled docs — when to read which file from `docs/` |
| **colppy-hubspot-reconciliation** | Reconcile Colppy first payments vs HubSpot deals by id_empresa. 4-group structure (Match, Wrong Stage incl. Cerrado Churn, HubSpot only). Uses bundled JSON snapshot (no VPN/MySQL). |
| **colppy-first-payments** | Query first payments count by month from Colppy. Uses bundled colppy_first_payments_snapshot.json (no VPN/MySQL). |
| **facturacion-csv-colppy** | Reconcile facturacion.csv vs Colppy billing. Uses bundled colppy_facturacion_snapshot.json. User attaches facturacion.csv. |
| **intercom-customer-research** | Search and analyze Intercom conversations for customer feedback on any feature or topic. Two-step workflow: scan (quick preview) then deep dive (full conversation content). Requires Claude Desktop's built-in Intercom integration (Settings → Integrations → Intercom). |
| **intercom-developer-api-research** | Find Colppy API integration conversations (developers, integrators, e‑commerce, ERP). Uses editable `keywords.json` for learning. Negative filter for false positives. |

## Commands (Slash Commands)

### SaaS Metrics
| Command | Description |
|---------|-------------|
| `/colppy-ceo-assistant:mrr-report` | Generate MRR waterfall report |
| `/colppy-ceo-assistant:budget-dashboard` | Refresh, query, or generate Building Blocks Budget vs Actual dashboard |
| `/colppy-ceo-assistant:dashboard-refresh` | Refresh MRR, ICP, and Building Blocks dashboards (outputs commands to run locally) |
| `/colppy-ceo-assistant:churn-analysis` | Analyze logo and revenue churn |
| `/colppy-ceo-assistant:growth-kpis` | CEO-level growth KPI summary |

### Funnel & HubSpot
| Command | Description |
|---------|-------------|
| `/colppy-ceo-assistant:funnel-report` | Full funnel analysis for accountant/SMB channels |
| `/colppy-ceo-assistant:icp-check` | Classify deals as ICP Operador or PYME |
| `/colppy-ceo-assistant:scoring-review` | Review scoring and contactability metrics |
| `/colppy-ceo-assistant:sql-conversion` | MQL→SQL conversion rates, cycle times |
| `/colppy-ceo-assistant:monthly-pql` | PQL rate per month with trends |
| `/colppy-ceo-assistant:pql-sql-analysis` | PQL→SQL timing (product-led vs sales-led) |
| `/colppy-ceo-assistant:deal-reconciliation` | Verify SQL contacts and deal associations |
| `/colppy-ceo-assistant:colppy-hubspot-reconciliation` | Reconcile Colppy first payments vs HubSpot closed won by id_empresa (e.g. `2026-02`) |
| `/colppy-ceo-assistant:facturacion-csv-colppy` | Reconcile facturacion.csv vs Colppy billing (attach CSV first) |
| `/colppy-ceo-assistant:icp-analysis` | Closed-won ICP Operador breakdown |
| `/colppy-ceo-assistant:lead-scoring` | High-score lead handling analysis |
| `/colppy-ceo-assistant:smb-mql-funnel` | Full SMB MQL funnel |
| `/colppy-ceo-assistant:smb-accountant-comparison` | Compare SMB funnel WITH vs WITHOUT accountant (pass dates) |
| `/colppy-ceo-assistant:referral-funnel` | Accountant referral pipeline |
| `/colppy-ceo-assistant:sales-ramp` | Sales rep ramp cohort analysis |

### Customer Research
| Command | Description |
|---------|-------------|
| `/colppy-ceo-assistant:intercom-research` | Search Intercom conversations for customer feedback on a specific feature or topic. Scans by keywords/tags, deep-dives relevant conversations, categorizes findings. |
| `/colppy-ceo-assistant:intercom-developer-api-research` | Find developer/API integration conversations in Intercom. Uses curated keywords and negative filters. Editable config for learning. |

## Agents

| Agent | Description |
|-------|-------------|
| **saas-metrics-analyst** | Specialized agent for MRR, churn, cohort retention, growth KPIs |

## Connectors

- **HubSpot** — CRM data (deals, contacts, companies, workflows)
- **Mixpanel** — Product analytics, PQL signals
- **Intercom** — Customer support conversations, feedback research
- **Slack** — Team communication
- **Atlassian** — Jira/Confluence

## Connector Setup

### Intercom (required for customer research)

The **intercom-customer-research** skill uses the **intercom-research** MCP server bundled with this plugin. Tools: `scan_full_text`, `scan_customer_feedback`, `get_conversation_feedback`, `export_intercom_conversations`, `count_intercom_conversations`, `get_intercom_conversation_stats`, `search_intercom_conversations`.

**Quick setup:**

1. **Get the access token** — Ask the team lead or IT for the `INTERCOM_ACCESS_TOKEN`. It's generated in Intercom > Settings > Integrations > Developer Hub > your app > Authentication. The token looks like `dG9rOjxxx...`. This token is a secret; do not commit it to any file.

2. **Set the token** — Add `INTERCOM_ACCESS_TOKEN=your-token` to your workspace `.env` file (at the repo root), or in Cursor: Settings → Tools & MCP → **intercom-research** → env. The plugin loads `.env` from the workspace root as a fallback.

3. **Install dependencies** (first time only) — Run `npm install` in `plugins/colppy-ceo-assistant/mcp/` if the MCP fails to start.

4. **Restart Cursor** — The MCP tools will become available.

> Full setup details are in `skills/intercom-customer-research/SKILL.md`.

#### Intercom MCP: Scan result limits

**`scan_full_text` returns all matches** — no cap. The cost is in fetching conversations; once fetched, all matches are returned. The `limit` parameter is deprecated and no longer used.

**Local only** — Use Cursor or Claude Desktop. Claude Cowork and Cloud Agents do not support this (no remote MCP).

### HubSpot Analysis MCP (funnel, scoring, visualization)

The **hubspot-analysis** MCP exposes funnel and scoring scripts for use in Cursor and Claude Desktop. Tools: `run_smb_mql_funnel`, `run_accountant_mql_funnel`, `run_smb_accountant_involved_funnel`, `run_high_score_analysis`, `run_mtd_scoring`, `run_visualization_report`.

**Setup:** Add to project `.mcp.json` (workspace root) or Claude Desktop config:

```json
"hubspot-analysis": {
  "command": "python",
  "args": ["/path/to/openai-cookbook/tools/scripts/hubspot/mcp_hubspot_analysis_server.py"],
  "cwd": "/path/to/openai-cookbook"
}
```

See `tools/scripts/hubspot/README_MCP_HUBSPOT_ANALYSIS.md` for full documentation.

### HubSpot, Mixpanel, Slack, Atlassian

These connectors are configured via their respective MCP servers in `~/.cursor/mcp.json`. See each skill's SKILL.md for specific setup instructions.

---

## Installation

### Zip File (Upload to Claude Cowork / Cloud AI)

**Generated zip location:** `tools/outputs/colppy-ceo-assistant-plugin-full.zip`

After any plugin change, run `./publish.sh` from this directory to regenerate the zip. Upload this zip in Cowork → Plugins → Upload plugin (or your Cloud AI platform).

### Claude (Cowork)
1. Run `./publish.sh` from this directory to build the zip
2. Upload `tools/outputs/colppy-ceo-assistant-plugin-full.zip` in Cowork → Plugins → Upload plugin

### Cursor
Add this plugin directory to your Cursor workspace. Cursor will discover the plugin from `plugins/colppy-ceo-assistant/` when the workspace root includes this path.
