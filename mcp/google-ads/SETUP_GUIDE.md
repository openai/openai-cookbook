# Google Ads MCP Setup Guide

## 1. Prerequisites

Before configuring the Google Ads MCP, you need to:

1. **Get a Google Ads Developer Token**:
   - Go to [Google Ads API Center](https://ads.google.com/home/tools/manager-accounts/)
   - Navigate to Tools & Settings > Setup > API Center
   - Apply for or copy your Developer Token

2. **Create Google Cloud Project & Enable APIs**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable the Google Ads API
   - Create OAuth 2.0 credentials or Service Account

## 2. Authentication Setup

Choose one of the following authentication methods:

### Option A: OAuth (Recommended for personal use)

1. In Google Cloud Console, create OAuth 2.0 credentials:
   - Application type: Desktop app
   - Download the credentials JSON file
   
2. Extract from the downloaded JSON:
   - `client_id`
   - `client_secret`

3. Generate refresh token (you'll need to run the setup script below)

### Option B: Service Account (For server applications)

1. In Google Cloud Console, create a Service Account
2. Download the JSON key file
3. Save it as `credentials/service_account.json` in this directory

## 3. Environment Configuration

Create a `.env` file in this directory with the following content:

```bash
# Google Ads API Credentials
GOOGLE_ADS_DEVELOPER_TOKEN=your_developer_token_here
GOOGLE_ADS_AUTH_TYPE=oauth  # Can be 'oauth' or 'service_account'

# If using OAuth (recommended for personal use)
GOOGLE_ADS_CLIENT_ID=your_client_id_here
GOOGLE_ADS_CLIENT_SECRET=your_client_secret_here
GOOGLE_ADS_REFRESH_TOKEN=your_refresh_token_here

# If using Service Account (for server applications)
GOOGLE_ADS_CREDENTIALS_PATH=/Users/virulana/openai-cookbook/mcp/google-ads/credentials/service_account.json

# Optional: Default Customer ID (remove dashes)
GOOGLE_ADS_CUSTOMER_ID=1234567890
```

## 4. Generate OAuth Refresh Token

If using OAuth, run this script to generate your refresh token:

```bash
cd /Users/virulana/openai-cookbook
source google_ads_mcp_env/bin/activate
python mcp/google-ads/generate_refresh_token.py
```

## 5. Configure Your IDE

### For Cursor:

Add to your Cursor settings (`~/.cursor/settings.json`):

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "/Users/virulana/openai-cookbook/google_ads_mcp_env/bin/python",
      "args": ["-m", "mcp_google_ads"],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your_developer_token_here",
        "GOOGLE_ADS_AUTH_TYPE": "oauth",
        "GOOGLE_ADS_CLIENT_ID": "your_client_id_here",
        "GOOGLE_ADS_CLIENT_SECRET": "your_client_secret_here",
        "GOOGLE_ADS_REFRESH_TOKEN": "your_refresh_token_here"
      }
    }
  }
}
```

### For Claude Desktop:

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "/Users/virulana/openai-cookbook/google_ads_mcp_env/bin/python",
      "args": ["-m", "mcp_google_ads"],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your_developer_token_here",
        "GOOGLE_ADS_AUTH_TYPE": "oauth",
        "GOOGLE_ADS_CLIENT_ID": "your_client_id_here",
        "GOOGLE_ADS_CLIENT_SECRET": "your_client_secret_here",
        "GOOGLE_ADS_REFRESH_TOKEN": "your_refresh_token_here"
      }
    }
  }
}
```

## 6. Test Your Setup

Run the test script:

```bash
cd /Users/virulana/openai-cookbook
source google_ads_mcp_env/bin/activate
python mcp/google-ads/test_setup.py
```

## 7. Restart Your IDE

After configuration, restart Cursor or Claude Desktop for the changes to take effect.

## Troubleshooting

- If you get Python not found errors, create a Python alias:
  ```bash
  sudo ln -s $(which python3) /usr/local/bin/python
  ```

- For permission issues with Google Ads accounts, ensure your developer token has proper access
- Check that your service account (if using) has been granted access to your Google Ads accounts
