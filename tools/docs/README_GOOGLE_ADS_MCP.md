### Google Ads MCP Setup and Usage (Cursor/Claude)

This guide documents how to run the Google Ads MCP server and pull metrics using environment-driven configuration. It mirrors the HubSpot README structure and avoids hard-coded values. Provide all required parameters via environment variables or CLI flags.

#### Requirements
- Python 3.11+
- Virtual environment with `mcp-google-ads` and `google-ads`
- A valid Google Ads Developer Token and OAuth credentials with the `https://www.googleapis.com/auth/adwords` scope

#### Environment variables
Set these in your IDE MCP config or shell. Do not commit secrets.
- `GOOGLE_ADS_DEVELOPER_TOKEN`: Developer token
- `GOOGLE_ADS_AUTH_TYPE`: `oauth` or `service_account`
- `GOOGLE_ADS_CLIENT_ID`: OAuth client ID (ends with `.apps.googleusercontent.com`) when using `oauth`
- `GOOGLE_ADS_CLIENT_SECRET`: OAuth client secret (when using `oauth`)
- `GOOGLE_ADS_REFRESH_TOKEN`: OAuth refresh token (when using `oauth`)
- `GOOGLE_ADS_CREDENTIALS_PATH`: Absolute path to service account JSON (when using `service_account`)
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID`: Manager account ID used for the login header (no dashes)
- `GOOGLE_ADS_CUSTOMER_ID`: Target client account ID (no dashes)

Optional (used by helper scripts/tools):
- `GA_START_DATE`, `GA_END_DATE` formatted as `YYYY-MM-DD`
- `GA_OUTPUT_PATH` absolute path for exports

#### Cursor MCP configuration (global)
Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "/ABS/PATH/TO/venv/bin/python",
      "args": ["-m", "mcp_google_ads.server"],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "${GOOGLE_ADS_DEVELOPER_TOKEN}",
        "GOOGLE_ADS_AUTH_TYPE": "${GOOGLE_ADS_AUTH_TYPE}",
        "GOOGLE_ADS_CLIENT_ID": "${GOOGLE_ADS_CLIENT_ID}",
        "GOOGLE_ADS_CLIENT_SECRET": "${GOOGLE_ADS_CLIENT_SECRET}",
        "GOOGLE_ADS_REFRESH_TOKEN": "${GOOGLE_ADS_REFRESH_TOKEN}",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "${GOOGLE_ADS_LOGIN_CUSTOMER_ID}",
        "GOOGLE_ADS_CUSTOMER_ID": "${GOOGLE_ADS_CUSTOMER_ID}"
      }
    }
  }
}
```

Notes:
- Always use absolute paths.
- IDs must not contain dashes.
- The server entrypoint is the module `mcp_google_ads.server`.

#### Quick validation steps
1) Restart Cursor and refresh MCP tools.
2) Run `list_accounts` and `list_clients` to confirm visibility.
3) Query metrics against the client account (not the manager). Ensure the login header is set via `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.

#### Reporting helper (script)
Use `tools/scripts/google_ads_report.py` to export ICP-, campaign-, and keyword-level metrics. It does not hard-code dates; pass them via env or flags.

Examples (dates are placeholders):
```bash
source /ABS/PATH/TO/venv/bin/activate
python tools/scripts/google_ads_report.py \
  --start_date ${GA_START_DATE} \
  --end_date ${GA_END_DATE} \
  --customer_id ${GOOGLE_ADS_CUSTOMER_ID} \
  --login_customer_id ${GOOGLE_ADS_LOGIN_CUSTOMER_ID} \
  --output_path ${GA_OUTPUT_PATH}
```

Outputs
- Console: concise Markdown summary
- Optional CSV at `--output_path` with Argentina formatting and metadata (date range, source, record count, filters)

#### Troubleshooting
- INVALID_CLIENT: Client ID must end with `.apps.googleusercontent.com` and match the refresh token.
- REQUESTED_METRICS_FOR_MANAGER: Query the client account; set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` to the manager.
- BAD_VALUE for dates: Use `YYYY-MM-DD` and wrap in single quotes in GAQL when building raw queries.

#### Security
- Never commit secrets.
- Rotate exposed credentials immediately.
- Keep `client_secret.json` and any token files with `0600` permissions.


