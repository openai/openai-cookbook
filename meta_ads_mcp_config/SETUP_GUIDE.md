# Meta Ads MCP Setup Guide

## 1. Prerequisites

Before configuring the Meta Ads MCP, you need to:

1. **Get Meta Business Manager Access**:
   - Go to [Facebook Business Manager](https://business.facebook.com/)
   - Ensure you have admin access to the Business Manager account
   - Note your Business Manager ID

2. **Create Facebook App**:
   - Go to [Facebook Developers](https://developers.facebook.com/)
   - Create a new app or use existing one
   - Add "Marketing API" product to your app
   - Get your App ID and App Secret

3. **Get Ad Account Access**:
   - Ensure your Facebook app has access to the Ad Account
   - Note your Ad Account ID (starts with `act_`)

## 2. Authentication Setup

### Option A: User Access Token (Recommended for personal use)

1. Generate a User Access Token with required permissions:
   - `ads_read` - Read ads data
   - `ads_management` - Manage ads (if needed)
   - `business_management` - Access business data

2. Use Facebook's Access Token Tool:
   - Go to [Facebook Access Token Tool](https://developers.facebook.com/tools/explorer/)
   - Select your app
   - Generate token with required permissions
   - Copy the access token

### Option B: System User Token (For server applications)

1. In Business Manager, create a System User
2. Assign the System User to your Ad Account
3. Generate a System User Access Token
4. This provides more stable, long-term access

## 3. Environment Configuration

Create a `.env` file in this directory with the following content:

```bash
# Meta Ads API Credentials
META_ADS_APP_ID=your_app_id_here
META_ADS_APP_SECRET=your_app_secret_here
META_ADS_ACCESS_TOKEN=your_access_token_here

# Optional: Default Ad Account ID (starts with 'act_')
META_ADS_ACCOUNT_ID=act_123456789

# Optional: Business Manager ID
META_ADS_BUSINESS_ID=123456789

# Optional: Default timezone (for reporting)
META_ADS_TIMEZONE=America/Argentina/Buenos_Aires
```

## 4. Generate Access Token

If you need to generate a new access token, you can use the Facebook Graph API Explorer:

1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Select your app
3. Add required permissions:
   - `ads_read`
   - `ads_management` (if needed)
   - `business_management`
4. Generate token
5. Copy the token to your `.env` file

## 5. Test Your Setup

Run the test script to verify your configuration:

```bash
python test_setup.py
```

This will:
- Validate your environment variables
- Test API connection
- List available ad accounts
- Display basic account information

## 6. Required Permissions

Your access token needs these permissions:

### Minimum Required:
- `ads_read` - Read ads, campaigns, and performance data

### Optional (for full functionality):
- `ads_management` - Create and modify ads
- `business_management` - Access business-level data
- `read_insights` - Read detailed insights and reports

## 7. Rate Limits

Meta Ads API has rate limits:
- **User Access Token**: 200 calls per hour per user
- **App Access Token**: 200 calls per hour per app
- **System User Token**: Higher limits, varies by business

## 8. Troubleshooting

### Common Issues:

1. **Invalid Access Token**:
   - Check if token has expired
   - Verify required permissions are granted
   - Regenerate token if needed

2. **Ad Account Access Denied**:
   - Ensure your app has access to the ad account
   - Check Business Manager permissions
   - Verify ad account ID format (`act_123456789`)

3. **Rate Limit Exceeded**:
   - Implement exponential backoff
   - Use batch requests when possible
   - Consider upgrading to System User token

### Debug Mode:
Set `META_ADS_DEBUG=true` in your `.env` file to enable detailed logging.

## 9. Security Best Practices

1. **Never commit access tokens** to version control
2. **Use environment variables** for all credentials
3. **Rotate tokens regularly** for security
4. **Use System User tokens** for production applications
5. **Implement proper error handling** and retry logic

## 10. Next Steps

Once setup is complete:
1. Run the test script to verify connection
2. Explore available ad accounts and campaigns
3. Use the MCP server for integration with Cursor/Claude
4. Run analysis scripts for campaign performance

For more information, see the [Meta Marketing API Documentation](https://developers.facebook.com/docs/marketing-api/).
