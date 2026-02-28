# Colppy–HubSpot Reconciliation MCP Server

MCP server that exposes reconciliation tools for use in Cursor, Claude Desktop, or any MCP client.

## Tools

| Tool | Description |
|------|-------------|
| `refresh_colppy_db` | Refresh Colppy data from MySQL (requires VPN). Use `incremental=True` for faster sync. |
| `refresh_hubspot_deals` | Refresh HubSpot closed-won deals. Single month (year, month) or multi-year (`years="2025 2026"`). |
| `populate_deal_associations` | Sync deal–company associations (required before CUIT reconciliation). |
| `run_reconciliation` | Run Colppy ↔ HubSpot 4-group reconciliation report. |
| `run_full_refresh` | Orchestrate: Colppy → HubSpot → associations → reconciliation. Use `skip_colppy=True` when VPN is off. |

## Setup

```bash
pip install -r tools/scripts/reconciliation/requirements.txt
# Or: pip install "mcp[cli]"
```

## Cursor Configuration

Add to `~/.cursor/mcp.json` (merge with existing `mcpServers`). See `cursor_mcp_config_sample.json` for the exact structure.

```json
"reconciliation": {
  "command": "python",
  "args": ["/Users/virulana/openai-cookbook/tools/scripts/reconciliation/mcp_reconciliation_server.py"],
  "cwd": "/Users/virulana/openai-cookbook"
}
```

- **args:** Use the **absolute path** to the script. Cursor may start the process from the home directory, so a relative path fails.
- **cwd:** Must be the absolute path to the openai-cookbook repo root (where `tools/` lives).
- **command:** Use `python` or `python3` depending on your environment. Ensure `mcp[cli]` is installed (`pip install "mcp[cli]"` or via repo `requirements.txt`).
- Restart Cursor after editing.

## Usage in Cursor

Once configured, you can ask in natural language, e.g.:

- "Refresh Colppy and HubSpot for February 2026, then run reconciliation"
- "Run reconciliation for 2026-02"
- "Refresh HubSpot deals for 2025 and 2026"

The AI will call the appropriate MCP tools.

## Timeouts

- Single-month HubSpot refresh: ~2–3 min
- Multi-year (2025–2026): ~1 hour
- Colppy refresh: ~20–60 s (requires VPN)
- Full refresh: ~5–10 min per month

## See Also

- [README_BILLING_RECONCILIATION.md](../../docs/README_BILLING_RECONCILIATION.md) — workflow and terminology
- [RECONCILE_REPORT_GROUPS.md](../../docs/RECONCILE_REPORT_GROUPS.md) — 4-group report structure
