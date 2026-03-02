# Colppy Revenue — Instructions

## Tool Usage Hierarchy

### Always prefer commands over raw API calls

This plugin provides **slash commands** that encapsulate complex workflows. Use them instead of building queries from scratch:

| Instead of... | Use... |
|---------------|--------|
| Manually querying HubSpot deals API | `/colppy-revenue:funnel-report` or `/colppy-revenue:smb-mql-funnel` |
| Building MRR calculations from raw deal data | `/colppy-revenue:mrr-report` |
| Fetching and grouping deals by ICP manually | `/colppy-revenue:icp-check` or `/colppy-revenue:icp-analysis` |
| Querying HubSpot scoring properties one by one | `/colppy-revenue:lead-scoring` or `/colppy-revenue:scoring-review` |
| Pulling Mixpanel events and computing PQL rates | `/colppy-revenue:monthly-pql` |

### Do NOT do manual multi-step HubSpot queries

When the user asks for funnel metrics, conversion rates, or deal pipeline analysis, **use the corresponding command** — it already knows the correct HubSpot properties, date filters, ICP logic, and formatting conventions. Do not:

- Fetch deals with `search_crm_objects` and manually compute funnel stages
- Query contacts and deals separately to build conversion funnels
- Manually look up HubSpot property definitions

### Skills provide context, not workflows

Skills are loaded as context for understanding terminology and data structures. They tell you *what* fields mean and *how* the data model works — but the **commands** are what you execute. Read skills to understand, execute commands to produce output.

## MCP Tools

This plugin has **no bundled MCP server**. It relies on external connectors (HubSpot, Mixpanel) configured in the user's environment. The MCP tools from these connectors are building blocks — prefer using the commands that wrap them.

Exception: The **hubspot-analysis** MCP (if available) provides pre-built analysis tools like `run_smb_mql_funnel` and `run_high_score_analysis` — these are already high-level and can be used directly.

## Data Conventions

- **Currency**: Always format in ARS (Argentine pesos) with Argentine number format (. for thousands, , for decimal)
- **ICP types**: "Cuenta Contador" (accountant firms) and "Cuenta Pyme" (direct SMBs) — use the icp-classification skill for the rules
- **Date ranges**: When the user says "this month" or "last month", use calendar months. MTD = month-to-date.
- **HubSpot pagination**: Always paginate through all results — never assume a single page is complete. See hubspot-api-patterns skill.

## Output Rules

- Present results in the chat with markdown tables — do not create files unless explicitly asked
- Include the date range and filters used in every output
- When showing funnel metrics, always include both absolute numbers and conversion percentages
