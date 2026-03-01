# HubSpot Analysis MCP Server

MCP server that exposes funnel, scoring, and visualization tools for use in Cursor, Claude Desktop, or any MCP client.

## Tools

| Tool | Description |
|------|--------------|
| `run_smb_mql_funnel` | SMB MQL funnel (MQL PYME → Deal Created → Won). Pass months as space-separated YYYY-MM. |
| `run_accountant_mql_funnel` | Accountant MQL funnel. Pass months as space-separated YYYY-MM. |
| `run_smb_accountant_involved_funnel` | SMB funnel WITH vs WITHOUT accountant. Optional minimal, dual_criteria. |
| `run_high_score_analysis` | Score 40+ contactability, owner performance, SQL/PQL. Pass month, start_date+end_date, or current_mtd. |
| `run_mtd_scoring` | Month-to-date scoring comparison (SQL/PQL by score range). Pass month1, month2. |
| `run_visualization_report` | HTML report from high_score CSV. Pass month; run run_high_score_analysis first. |

## Setup

```bash
pip install -r tools/scripts/reconciliation/requirements.txt
# Or: pip install "mcp[cli]"
```

## Cursor Configuration

Add to project `.mcp.json` (workspace root) or merge with existing `mcpServers`:

```json
"hubspot-analysis": {
  "command": "python",
  "args": ["/Users/virulana/openai-cookbook/tools/scripts/hubspot/mcp_hubspot_analysis_server.py"],
  "cwd": "/Users/virulana/openai-cookbook"
}
```

Use absolute paths. Restart Cursor after editing.

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
"mcpServers": {
  "hubspot-analysis": {
    "command": "python",
    "args": ["/path/to/openai-cookbook/tools/scripts/hubspot/mcp_hubspot_analysis_server.py"],
    "cwd": "/path/to/openai-cookbook"
  }
}
```

## Usage

Once configured, you can ask in natural language, e.g.:

- "Run SMB MQL funnel for Dec 2025, Jan 2026, and Feb 2026"
- "Run high score analysis for February 2026"
- "Compare scoring for January vs February 2026"
- "Generate the visualization report for Feb 2026"

## HubSpot Scripts Not Exposed via MCP

The following HubSpot scripts are **not** exposed via this MCP. Run them manually or extend the MCP.

### Conversion & PQL/SQL
- `sql_pql_conversion_analysis.py` — SQL conversion by month
- `pql_sql_deal_relationship_analysis.py` — PQL→SQL→Deal timing
- `complete_sql_conversion_analysis.py` — Full SQL conversion with cycle times
- `monthly_pql_analysis.py` — PQL rate per month
- `deal_focused_pql_analysis.py` — Deal-focused PQL metrics
- `hubspot_conversion_analysis.py` — General conversion analysis

### ICP & Billing
- `analyze_icp_operador_billing.py` — ICP Operador vs PYME from billing
- `analyze_icp_dashboard.py` — ICP dashboard
- `analyze_accountant_mrr_matrix.py` — Accountant MRR matrix

### Referral & Lead Source
- `analyze_accountant_referral_funnel.py` — Accountant referral funnel
- `analyze_customer_referral_funnel.py` — Customer referral funnel
- `analyze_referral_type8_correlation.py` — Type 8 association correlation
- `analyze_direct_deals_lead_source.py` — Deals by lead source
- `analyze_deal_conversion_by_lead_source.py` — Conversion by lead source

### Support & Uncontacted
- `analyze_uncontacted_lead_status.py` — Uncontacted lead status
- `check_owner_status.py` — Owner active/inactive
- `compare_owner_status_months.py` — Owner status month comparison

### Other Analysis
- `analyze_product_led_deals.py` — Product-led deal analysis
- `analyze_touch_sequence_deals.py` — Touch sequence
- `sales_ramp_cohort_analysis.py` — Sales ramp cohorts
- `visualize_sql_cycle_time.py` — SQL cycle time charts
- `fetch_hubspot_deals_with_company.py` — Fetch deals with company
- `find_contacts_without_lead_objects.py` — Contacts without Lead objects

### Data Fix / Maintenance (write operations)
- `fix_deal_associations.py` — Fix deal–company associations
- `merge_duplicate_companies.py` — Merge duplicates
- `populate_accountant_deals.py` — Populate accountant deals
- `reconcile_missing_deals.py` — Reconcile missing deals
- `build_facturacion_hubspot_mapping.py` — Build facturacion mapping (used by reconciliation MCP)
- `populate_deal_associations.py` — Populate associations (used by reconciliation MCP)

### Infrastructure / Build
- `hubspot_build_*.py` — Build/refresh scripts
- `reconcile_*.py` — Various reconciliation scripts
