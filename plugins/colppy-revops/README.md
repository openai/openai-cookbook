# Colppy RevOps Plugin

Revenue Operations toolkit for Colppy — billing reconciliation, first payments analysis, facturacion matching, and deal pipeline verification.

## Skills

| Skill | Purpose |
|-------|---------|
| `billing-reconciliation` | Billing data cross-checks and verification |
| `colppy-hubspot-reconciliation` | Colppy ↔ HubSpot deal matching and reconciliation |
| `colppy-first-payments` | First payments analysis and billing lifecycle |
| `facturacion-csv-colppy` | Facturacion CSV export and matching |

## Commands

| Command | Description |
|---------|-------------|
| `/colppy-hubspot-reconciliation` | Run Colppy-HubSpot reconciliation report |
| `/facturacion-csv-colppy` | Export and analyze facturacion CSV data |
| `/deal-reconciliation` | Reconcile deals across systems |

## MCP Tools

### reconciliation (5 tools)

| Tool | Description |
|------|-------------|
| `refresh_colppy_db` | Refresh SQLite from Colppy MySQL (requires VPN) |
| `refresh_hubspot_deals` | Refresh HubSpot closed-won deals |
| `populate_deal_associations` | Sync deal-company associations |
| `run_reconciliation` | Run Colppy ↔ HubSpot reconciliation |
| `run_full_refresh` | Full pipeline for a month |

### hubspot-analysis (6 tools)

| Tool | Description |
|------|-------------|
| `run_smb_mql_funnel` | SMB MQL funnel analysis |
| `run_accountant_mql_funnel` | Accountant MQL funnel |
| `run_smb_accountant_involved_funnel` | SMB with/without accountant comparison |
| `run_high_score_analysis` | High-score contactability and conversion |
| `run_mtd_scoring` | Month-to-date scoring comparison |
| `run_visualization_report` | HTML visualization report |

## Setup

MCP servers use Python scripts from `tools/scripts/`. Requires:
- Python 3.11+
- HubSpot API key in `.env`
- Colppy MySQL access (VPN) for `refresh_colppy_db`
