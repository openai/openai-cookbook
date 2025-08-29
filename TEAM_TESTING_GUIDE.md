# 🚀 Google Ads MCP Integration - Team Testing Guide

**Version:** 1.0  
**Last Updated:** August 28, 2025  
**Repository:** [openai-cookbook](https://github.com/jonetto1978/openai-cookbook)

## 📋 What's Available

The repository now includes a complete Google Ads MCP (Model Context Protocol) integration that enables natural language analysis of Google Ads campaign data directly within Cursor IDE.

### 🔧 New Tools Added:

1. **Google Ads MCP Configuration** (`google_ads_mcp_config/`)
2. **Campaign Analysis Scripts** (`tools/scripts/`)
3. **HubSpot-Google Ads Integration** (UTM tracking and CPA calculation)
4. **Automated PQL Analysis** (Product Qualified Lead tracking)
5. **Team Development Guidelines** (`.cursorrules`)

---

## 🛠️ Quick Setup for Team Members

### Step 1: Clone/Pull Latest Changes
```bash
git clone https://github.com/jonetto1978/openai-cookbook.git
# OR if you already have the repo:
git pull origin main
```

### Step 2: Install Google Ads MCP
```bash
# Create virtual environment for Google Ads MCP
python -m venv google_ads_mcp_env
source google_ads_mcp_env/bin/activate  # On Windows: google_ads_mcp_env\Scripts\activate

# Install required packages
pip install mcp-google-ads google-ads google-auth-oauthlib rich cairosvg
```

### Step 3: Set Up Credentials (IMPORTANT!)
1. **Get Google Ads API access** from project admin
2. **Create your own `.env` file** in the root directory:
   ```bash
   cp .env.example .env  # If example exists
   # OR manually create .env with required variables (see below)
   ```

3. **Required Environment Variables:**
   ```env
   GOOGLE_ADS_DEVELOPER_TOKEN=your_developer_token
   GOOGLE_ADS_CLIENT_ID=your_oauth_client_id
   GOOGLE_ADS_CLIENT_SECRET=your_oauth_client_secret
   GOOGLE_ADS_REFRESH_TOKEN=your_refresh_token
   GOOGLE_ADS_CUSTOMER_ID=4904978003
   GOOGLE_ADS_LOGIN_CUSTOMER_ID=6497883096
   HUBSPOT_ACCESS_TOKEN=your_hubspot_token
   ```

### Step 4: Configure Cursor MCP
1. **Copy the sample configuration:**
   ```bash
   cp google_ads_mcp_config/cursor_config_sample.json ~/.cursor/mcp.json
   ```

2. **Update paths in `~/.cursor/mcp.json`:**
   ```json
   {
     "mcpServers": {
       "google-ads": {
         "command": "/path/to/your/openai-cookbook/google_ads_mcp_env/bin/python",
         "args": ["-m", "mcp_google_ads.server"],
         "env": {
           "GOOGLE_ADS_DEVELOPER_TOKEN": "your_token",
           "GOOGLE_ADS_CLIENT_ID": "your_client_id",
           "GOOGLE_ADS_CLIENT_SECRET": "your_client_secret", 
           "GOOGLE_ADS_REFRESH_TOKEN": "your_refresh_token",
           "GOOGLE_ADS_CUSTOMER_ID": "4904978003",
           "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "6497883096"
         }
       }
     }
   }
   ```

### Step 5: Generate OAuth Tokens (If Needed)
```bash
# Navigate to config directory
cd google_ads_mcp_config/

# Run token generation script
python generate_refresh_token.py

# Follow the OAuth flow in your browser
```

---

## 🧪 Testing the Integration

### Test 1: Verify MCP Connection
1. **Restart Cursor IDE** completely
2. **Open the openai-cookbook project**
3. **In a chat conversation, ask:**
   ```
   List all my Google Ads accounts
   ```
4. **Expected Result:** Should show available Google Ads accounts without errors

### Test 2: Campaign Analysis
Ask the AI assistant:
```
Show me the performance of all active campaigns in August 2025
```
**Expected Result:** Formatted table showing campaign metrics (impressions, clicks, cost, CTR, CPC)

### Test 3: ICP-Specific Analysis
Ask:
```
Compare PyMés vs Contadores campaign performance for August 2025
```
**Expected Result:** Side-by-side comparison of both campaign types with strategic insights

### Test 4: HubSpot Integration
Ask:
```
Calculate CPA by linking Google Ads UTM campaigns to HubSpot contacts for August 2025
```
**Expected Result:** Analysis showing which campaigns generated contacts and their cost per acquisition

### Test 5: Keyword Analysis
Ask:
```
Analyze the keyword strategy for the Contadores_lead_gen campaign
```
**Expected Result:** Detailed breakdown of keywords with ICP targeting assessment

---

## 🔍 What You Can Analyze

### Campaign Performance Metrics
- **Monthly/Weekly/Daily performance** comparisons
- **ICP-based campaign analysis** (PyMEs vs Contadores)
- **Keyword effectiveness** and quality scores
- **Budget utilization** and pacing
- **Geographic performance** breakdowns

### Strategic Analysis
- **Campaign configuration** health checks
- **ICP targeting quality** assessment
- **Keyword overlap** detection between campaigns
- **Landing page alignment** with campaign goals
- **Competitive positioning** analysis

### HubSpot Integration
- **UTM campaign tracking** and attribution
- **Cost per acquisition (CPA)** calculation
- **Lead quality scoring** by campaign source
- **Pipeline conversion** from paid campaigns
- **ROI analysis** by marketing channel

### Automation Capabilities
- **Campaign inventory** snapshots for change tracking
- **Monthly PQL analysis** automation
- **Performance alerts** and anomaly detection
- **Scheduled reporting** for stakeholders

---

## 📊 Available Scripts

### 1. Campaign Inventory Export
```bash
cd tools/scripts/
python google_ads_export_campaign_inventory.py
```
**Purpose:** Creates snapshot of all campaigns for change tracking

### 2. HubSpot-Google Ads UTM Analysis
```bash
python hubspot_utm_google_ads_analysis.py
```
**Purpose:** Links UTM campaigns to HubSpot contacts for CPA calculation

### 3. Monthly PQL Analysis
```bash
python hubspot/monthly_pql_analysis.py --month=2025-08
```
**Purpose:** Analyze product qualified leads by month

### 4. Automated Monthly Reports
```bash
./run_monthly_pql.sh
```
**Purpose:** Full monthly analysis automation

---

## 🚨 Common Troubleshooting

### Issue: "No tools or prompts" in Cursor
**Solution:** 
1. Restart Cursor completely
2. Check that `~/.cursor/mcp.json` has correct paths
3. Verify environment variables are set
4. Check virtual environment is properly installed

### Issue: "Authentication failed"
**Solution:**
1. Regenerate OAuth tokens using `generate_refresh_token.py`
2. Verify Google Ads API access permissions
3. Check that Client ID/Secret are correct format

### Issue: "Customer not found" error
**Solution:**
1. Verify `GOOGLE_ADS_CUSTOMER_ID=4904978003` in `.env`
2. Ensure `GOOGLE_ADS_LOGIN_CUSTOMER_ID=6497883096` is set
3. Check you have access to these accounts

### Issue: Script fails with import errors
**Solution:**
1. Activate virtual environment: `source google_ads_mcp_env/bin/activate`
2. Install missing packages: `pip install missing_package_name`
3. Verify Python path in scripts

---

## 📈 Usage Examples

### Natural Language Queries You Can Ask:

1. **Performance Analysis:**
   - "How did our Google Ads perform last month?"
   - "Which campaigns have the highest CTR?"
   - "Show me cost trends for PyMEs campaigns"

2. **Strategic Assessment:**
   - "Are our keywords properly targeted to SMBs?"
   - "Do we have keyword overlap between campaigns?"
   - "How well does our ad copy match landing pages?"

3. **Optimization Suggestions:**
   - "What should we optimize in our MercadoPago campaign?"
   - "Which keywords are underperforming?"
   - "How can we improve our CPA?"

4. **Competitive Analysis:**
   - "How do our ads compare to competitors?"
   - "What keywords are we missing?"
   - "Which ad positions are most effective?"

5. **ROI and Attribution:**
   - "What's our return on ad spend by campaign?"
   - "Which UTM sources generate the best leads?"
   - "How do Google Ads contacts convert in HubSpot?"

---

## 🎯 Team Best Practices

### 1. Data Security
- **Never commit** `.env` files to git
- **Use separate credentials** for each team member
- **Rotate tokens** regularly for security

### 2. Analysis Workflow
- **Always specify date ranges** in queries
- **Save important reports** in `tools/outputs/`
- **Document insights** for team knowledge sharing
- **Use consistent naming** for campaign analysis

### 3. Development Guidelines
- **Follow `.cursorrules`** for consistent code style
- **Test scripts** before pushing changes
- **Update documentation** when adding new features
- **Use semantic versioning** for script updates

### 4. Collaboration
- **Share significant insights** in team channels
- **Create templates** for recurring analysis
- **Document campaign learnings** for future reference
- **Coordinate** major campaign changes

---

## 📞 Support & Troubleshooting

### Team Resources:
- **Primary Documentation:** `tools/docs/README_GOOGLE_ADS_MCP.md`
- **Setup Guide:** `google_ads_mcp_config/SETUP_GUIDE.md`
- **Script Documentation:** Individual script docstrings
- **Team Chat:** For real-time troubleshooting

### External Resources:
- **Google Ads API Docs:** https://developers.google.com/google-ads/api
- **MCP Google Ads:** https://github.com/cohnen/mcp-google-ads
- **Cursor MCP Guide:** https://docs.cursor.com/mcp

### Getting Help:
1. **Check this guide** first
2. **Review error messages** carefully
3. **Test with simple queries** first
4. **Ask team members** who have it working
5. **Escalate to project admin** for credentials/access issues

---

## 🎉 Ready to Start!

You now have access to powerful Google Ads analysis capabilities directly in your development environment. Start with simple queries and gradually explore more complex analysis as you become comfortable with the tools.

**First Query to Try:**
```
Show me a summary of our Google Ads performance for the current month
```

Happy analyzing! 🚀📊
