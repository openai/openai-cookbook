# MCP (Model Context Protocol) Servers

This folder consolidates MCP-related configuration and source code. Virtual environments remain at the repo root for compatibility.

## Layout

```
mcp/
├── meta-ads/          # Meta Ads API MCP (config, scripts, src/mcp_meta_ads.py)
├── google-ads/        # Google Ads API MCP (config, setup scripts)
└── README.md          # This file
```

## Venvs (at repo root)

- `meta_ads_mcp_env/` — Python venv for Meta Ads MCP
- `google_ads_mcp_env/` — Python venv for Google Ads MCP

## Other MCP servers (unchanged)

- `tools/scripts/intercom/` — Intercom MCP server
- `tools/scripts/fellow/` — Fellow MCP server
- `tools/scripts/atlassian/` — Atlassian MCP server
- `tools/scripts/reconciliation/` — Colppy–HubSpot reconciliation MCP
- `arca-prototype/backend/mcp_server.py` — ARCA MCP (self-contained)

## Meta Ads MCP (mcp/meta-ads)

The MCP server (`mcp_meta_ads`) lives in `mcp/meta-ads/src/`. The Cursor config sample sets `PYTHONPATH` and `cwd` so the module is found. If you run scripts manually, activate the venv and set:

```bash
export PYTHONPATH="<repo-root>/mcp/meta-ads/src"
```

## Setup

See each subfolder for setup instructions:

- **Meta Ads:** [mcp/meta-ads/SETUP_GUIDE.md](meta-ads/SETUP_GUIDE.md)
- **Google Ads:** [mcp/google-ads/SETUP_GUIDE.md](google-ads/SETUP_GUIDE.md)

Cursor MCP config samples are in each folder (`cursor_config_sample.json`). Merge into `~/.cursor/mcp.json` or Cursor MCP settings.
