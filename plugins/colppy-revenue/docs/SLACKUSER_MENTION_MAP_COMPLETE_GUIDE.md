# SlackUserMentionMap - Complete Setup and Usage Guide

## 🎯 What is SlackUserMentionMap?

**SlackUserMentionMap** is an environment variable in HubSpot workflows that maps HubSpot owner IDs to Slack user IDs. This allows HubSpot custom code workflows to **mention the company owner in Slack notifications**, so they get notified when their company records have validation issues.

## 🔍 Why Do We Need It?

### The Problem:
- HubSpot stores owner IDs (like `216511812`)
- Slack uses different user IDs (like `U01234567`)
- When a workflow sends a Slack notification, it needs to know how to mention the HubSpot owner in Slack
- Without this mapping, notifications just show "Owner ID: 216511812" instead of mentioning the user

### The Solution:
- **SlackUserMentionMap** bridges the gap between HubSpot owner IDs and Slack IDs
- When a workflow detects company owner `216511812`, it looks up their Slack ID
- Then it formats it as `<@U01234567>` which Slack recognizes as a mention
- The owner gets **notified** in Slack!

## 📋 How It Works

### Step-by-Step Flow:

1. **Workflow Triggers** → Company record is updated
2. **Code Detects Owner** → Gets `hubspot_owner_id` = `216511812`
3. **Looks Up Slack ID** → Checks `SlackUserMentionMap` for `"216511812"`
4. **Finds Mapping** → `"216511812": "U01234567"`
5. **Formats Mention** → Creates `<@U01234567>`
6. **Sends Notification** → Slack notification includes the mention
7. **Owner Gets Notified** → Slack pings the owner!

### Example Notification:
```
⚠️ Company Record Has Blank Required Fields • Owner: <@U01234567>
```

Instead of:
```
⚠️ Company Record Has Blank Required Fields • Owner: Owner ID: 216511812
```

## 🛠️ Complete Setup Steps

### Step 1: Find Your Slack User ID

**Method 1: From Your Profile**
1. Open Slack
2. Click on your **profile picture/name** (top left)
3. Click **"View profile"**
4. Click the **three dots (⋯)** menu
5. Click **"Copy member ID"**
6. Your Slack User ID looks like: `U01234567` or `U1234567890`

**Method 2: From a Message**
1. In Slack, **right-click** on your name in any message
2. Select **"Copy link"**
3. The URL contains your user ID (the part after `/team/` and before `/`)
4. Example: `https://workspace.slack.com/team/U01234567` → Your ID is `U01234567`

**Method 3: Using Slack API (Advanced)**
```bash
curl -H "Authorization: Bearer YOUR_SLACK_TOKEN" \
  https://slack.com/api/users.list | jq '.members[] | select(.name=="your_username") | .id'
```

### Step 2: Find HubSpot Owner IDs

**From Workflow Logs:**
- When the workflow runs, check the logs
- Look for messages like:
  - `⚠️ COMPANY OWNER SLACK MENTION NOT FOUND: No mapping for owner 216511812`
- These numbers are the HubSpot owner IDs you need to map

**From HubSpot UI:**
1. Go to **Settings** → **Users & Teams**
2. Click on a user/owner
3. The URL contains their ID: `.../users/OWNER_ID`
4. Or check the company record's `hubspot_owner_id` property

**From Company Records:**
- `hubspot_owner_id` = Owner ID (works with Owners API)
- This is the ID you need to map to Slack

### Step 3: Create the JSON Mapping

The `SlackUserMentionMap` is a **JSON object** that maps HubSpot owner IDs to Slack IDs:

```json
{
  "216511812": "U01234567",
  "46063063": "U09876543"
}
```

**Format Rules:**
- **Keys** = HubSpot Owner IDs (as strings)
- **Values** = Slack User IDs (as strings, starting with `U`)
- Use **double quotes** for both keys and values
- **No trailing commas**
- Valid JSON format

**Two Value Formats Supported:**

1. **Plain Slack ID** (recommended):
   ```json
   {
     "630465": "U01234567"
   }
   ```
   → Code wraps it as `<@U01234567>`

2. **Full Mention Format**:
   ```json
   {
     "630465": "<@U01234567>"
   }
   ```
   → Code uses it as-is

### Step 4: Access HubSpot Workflow Environment Variables

1. Go to **HubSpot** → **Settings** (⚙️ icon, top right)
2. Navigate to **Integrations** → **Custom Code**
3. Find your workflow: **"Company Blank Field Validator"**
4. Click on the workflow to edit it
5. Look for **"Environment Variables"** or **"Secrets"** section
   - This might be in:
     - Workflow settings
     - Custom code action settings
     - Workflow configuration

### Step 5: Add or Update SlackUserMentionMap

1. **If it doesn't exist:**
   - Click **"Add Environment Variable"** or **"Add Secret"**
   - Name: `SlackUserMentionMap`
   - Value: Paste your JSON (from Step 3)
   - Click **Save**

2. **If it already exists:**
   - Click on `SlackUserMentionMap`
   - Edit the value
   - Add new mappings or update existing ones
   - Click **Save**

### Step 6: Verify the Setup

1. **Check the JSON is valid:**
   - Use a JSON validator: https://jsonlint.com/
   - Ensure no syntax errors

2. **Test the workflow:**
   - Update a company record
   - Check workflow logs for:
     - `✅ Slack mention map loaded with X entries`
     - `✅ LAST MODIFIED BY SLACK MENTION FOUND: <@U01234567>`
   - Check Slack for the mention notification

3. **Verify mentions work:**
   - You should see `<@U01234567>` in the notification
   - Clicking it should show your Slack profile
   - You should receive a Slack notification

## 📝 Example: Complete Setup for planetaverde.ba

### Current Situation:
- **Company Owner ID:** `216511812` (Juan Ignacio Onetto)
- Needs Slack mention mapping

### Step-by-Step:

1. **Find Slack User ID for owner 216511812:**
   - Ask the owner or check their Slack profile
   - Example: `U1234567890`

2. **Create JSON:**
   ```json
   {
     "216511812": "U1234567890"
   }
   ```

3. **Add to HubSpot:**
   - Go to HubSpot → Settings → Integrations → Custom Code
   - Find "Company Blank Field Validator" workflow
   - Add environment variable: `SlackUserMentionMap`
   - Value: The JSON above
   - Save

4. **Result:**
   - When company owner 216511812's company has blank fields, Slack notification will show:
     - `⚠️ Company Record Has Blank Required Fields • Owner: <@U1234567890>`
   - Owner 216511812 gets notified in Slack!

## 🔧 Troubleshooting

### Issue: "SlackUserMentionMap env var not set"
**Solution:** The environment variable doesn't exist in HubSpot
- Go to HubSpot workflow settings
- Add the `SlackUserMentionMap` environment variable
- Paste your JSON mapping

### Issue: "Failed to parse SlackUserMentionMap env var"
**Solution:** JSON syntax error
- Validate JSON at https://jsonlint.com/
- Check for:
  - Missing quotes around keys/values
  - Trailing commas
  - Missing commas between entries
  - Invalid characters

### Issue: "No Slack mention mapping for HubSpot user XXXX"
**Solution:** Owner ID not in the map
- Add the missing owner ID to your JSON
- Format: `"XXXX": "U_SLACK_ID"`
- Update the environment variable in HubSpot

### Issue: Slack mention not working (shows as text, not mention)
**Solution:** Invalid Slack user ID format
- Slack IDs must start with `U` (not `W` or other letters)
- Format: `U01234567` or `<@U01234567>`
- Verify the Slack user ID is correct

### Issue: User gets notified but name doesn't resolve
**Solution:** This is expected behavior
- Name resolution uses Owners API (for Owner IDs)
- User IDs (`hs_updated_by_user_id`) may not resolve to names
- **Slack mentions will still work** even if name doesn't resolve
- The notification will show: `<@U01234567>` instead of name

## 💡 Best Practices

1. **Keep the map updated:**
   - Add new users as they join
   - Remove archived users
   - Update when users change Slack accounts

2. **Use a helper script:**
   - Use `/tools/scripts/generate_slack_mention_map.js` to generate JSON
   - Easier to maintain and validate

3. **Document your mappings:**
   - Keep a record of which HubSpot IDs map to which Slack IDs
   - Makes troubleshooting easier

4. **Test regularly:**
   - Update a test record
   - Verify mentions work
   - Check logs for any missing mappings

## 🎯 Role and Purpose Summary

**Role:** Bridge between HubSpot owner tracking and Slack notifications

**Purpose:**
- ✅ Enable Slack mentions in workflow notifications
- ✅ Notify company owners when their records are flagged
- ✅ Improve team communication and accountability
- ✅ Make notifications actionable (owners get pinged)

**How It Works:**
1. HubSpot workflow detects company owner (HubSpot owner ID)
2. Code looks up owner ID in `SlackUserMentionMap`
3. Finds corresponding Slack user ID
4. Formats as Slack mention (`<@U123>`)
5. Includes in Slack notification
6. Owner receives notification in Slack

## 📚 Related Files

- **Code:** `/tools/scripts/hubspot_company_blank_field_validator.js`
- **Helper Script:** `/tools/scripts/generate_slack_mention_map.js`
- **Documentation:** `/tools/docs/HUBSPOT_SLACK_MENTION_SETUP.md`

## 🚀 Quick Start Checklist

- [ ] Find your Slack User ID
- [ ] Identify HubSpot Owner IDs that need mapping
- [ ] Create JSON mapping object
- [ ] Validate JSON format
- [ ] Add to HubSpot workflow environment variables
- [ ] Test by updating a company record
- [ ] Verify Slack notification includes mention
- [ ] Confirm owner received the notification

---

**Need Help?** Check the workflow logs for detailed information about which user IDs need to be added to the map.


