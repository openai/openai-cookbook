# Atlassian MCP Server

This MCP (Model Context Protocol) server provides integration with Atlassian products (Jira and Confluence) through a standardized interface that can be used by AI assistants and automation tools.

## 🚀 Quick Start

### Prerequisites

1. **Atlassian Account**: You need an Atlassian account with access to Jira and/or Confluence
2. **API Token**: Generate an API token from your Atlassian account settings
3. **Node.js**: Version 18 or higher

### Installation

```bash
# Navigate to the atlassian directory
cd tools/scripts/atlassian

# Install dependencies
npm install
```

### Configuration

1. Create or update your `.env` file in the project root (or `tools/.env`):

```env
# Atlassian Configuration
ATLASSIAN_DOMAIN=your-domain    # e.g., "colppy" for colppy.atlassian.net
ATLASSIAN_EMAIL=your-email@company.com
ATLASSIAN_API_TOKEN=your-api-token-here
```

2. Generate an API token:
   - Go to https://id.atlassian.com/manage-profile/security/api-tokens
   - Click "Create API token"
   - Give it a label (e.g., "MCP Server")
   - Copy the token and add it to your `.env` file

### Running the Server

```bash
# Start the MCP server
npm start

# Or directly with node
node mcp-atlassian-server.js
```

## 📋 Available Tools

### Jira Tools

#### 1. `jira_search_issues`
Search for Jira issues using JQL (Jira Query Language).

**Parameters:**
- `jql` (required): JQL query string
- `max_results`: Maximum results to return (default: 50, max: 100)
- `fields`: Array of fields to include
- `expand`: Array of data to expand

**Example:**
```json
{
  "tool": "jira_search_issues",
  "arguments": {
    "jql": "project = COLP AND status = 'In Progress' AND assignee = currentUser()",
    "max_results": 20,
    "fields": ["summary", "status", "priority", "assignee"]
  }
}
```

#### 2. `jira_get_issue`
Get detailed information about a specific Jira issue.

**Parameters:**
- `issue_key` (required): Issue key (e.g., "COLP-123")
- `fields`: Specific fields to include
- `expand`: Additional data to expand

**Example:**
```json
{
  "tool": "jira_get_issue",
  "arguments": {
    "issue_key": "COLP-123",
    "expand": ["changelog", "renderedFields"]
  }
}
```

#### 3. `jira_create_issue`
Create a new Jira issue.

**Parameters:**
- `project_key` (required): Project key
- `issue_type` (required): Issue type (e.g., "Task", "Bug", "Story")
- `summary` (required): Issue title
- `description`: Issue description (supports Jira markdown)
- `assignee`: Assignee account ID or email
- `priority`: Priority name
- `labels`: Array of labels
- `components`: Array of component names
- `custom_fields`: Object with custom field values

**Example:**
```json
{
  "tool": "jira_create_issue",
  "arguments": {
    "project_key": "COLP",
    "issue_type": "Task",
    "summary": "Implement new authentication flow",
    "description": "As a user, I want to authenticate using SSO...",
    "assignee": "user@colppy.com",
    "priority": "High",
    "labels": ["authentication", "security"],
    "components": ["Backend"]
  }
}
```

#### 4. `jira_update_issue`
Update an existing Jira issue.

**Parameters:**
- `issue_key` (required): Issue key to update
- `fields` (required): Object with fields to update
- `notify_users`: Whether to send notifications (default: true)

**Example:**
```json
{
  "tool": "jira_update_issue",
  "arguments": {
    "issue_key": "COLP-123",
    "fields": {
      "summary": "Updated summary",
      "priority": {"name": "Critical"},
      "labels": ["urgent", "backend"]
    }
  }
}
```

#### 5. `jira_add_comment`
Add a comment to a Jira issue.

**Parameters:**
- `issue_key` (required): Issue key
- `comment` (required): Comment text
- `visibility`: Object with visibility restrictions

**Example:**
```json
{
  "tool": "jira_add_comment",
  "arguments": {
    "issue_key": "COLP-123",
    "comment": "I've reviewed the PR and it looks good. Ready for QA testing.",
    "visibility": {
      "type": "group",
      "value": "developers"
    }
  }
}
```

#### 6. `jira_transition_issue`
Move an issue to a different status.

**Parameters:**
- `issue_key` (required): Issue key
- `transition_name` (required): Name of the transition
- `comment`: Optional comment
- `fields`: Fields to update during transition

**Example:**
```json
{
  "tool": "jira_transition_issue",
  "arguments": {
    "issue_key": "COLP-123",
    "transition_name": "Done",
    "comment": "Feature completed and tested"
  }
}
```

#### 7. `jira_list_projects`
List all accessible Jira projects.

**Parameters:**
- `expand`: Additional project data to include

**Example:**
```json
{
  "tool": "jira_list_projects",
  "arguments": {
    "expand": ["lead", "description"]
  }
}
```

### Confluence Tools

#### 1. `confluence_search_content`
Search for Confluence pages and content.

**Parameters:**
- `cql` (required): CQL query string
- `space_key`: Limit to specific space
- `type`: Content type ("page", "blogpost", "attachment", "comment")
- `limit`: Maximum results (default: 25)

**Example:**
```json
{
  "tool": "confluence_search_content",
  "arguments": {
    "cql": "text ~ 'api documentation'",
    "space_key": "DEV",
    "type": "page"
  }
}
```

#### 2. `confluence_get_page`
Get a specific Confluence page.

**Parameters:**
- `page_id`: Page ID
- `space_key`: Space key (if using title)
- `title`: Page title (requires space_key)
- `expand`: Additional data to expand

**Example:**
```json
{
  "tool": "confluence_get_page",
  "arguments": {
    "space_key": "DEV",
    "title": "API Documentation",
    "expand": ["body.storage", "version"]
  }
}
```

#### 3. `confluence_create_page`
Create a new Confluence page.

**Parameters:**
- `space_key` (required): Space key
- `title` (required): Page title
- `content` (required): Page content
- `parent_id`: Parent page ID
- `format`: Content format ("storage" or "markdown", default: "markdown")

**Example:**
```json
{
  "tool": "confluence_create_page",
  "arguments": {
    "space_key": "DEV",
    "title": "Sprint 23 Retrospective",
    "content": "# Sprint 23 Retrospective\n\n## What went well\n- Feature X shipped on time\n\n## What could be improved\n- Better estimation needed",
    "format": "markdown"
  }
}
```

#### 4. `confluence_update_page`
Update an existing Confluence page.

**Parameters:**
- `page_id` (required): Page ID
- `content` (required): New content
- `title`: New title (optional)
- `version_comment`: Comment explaining changes
- `format`: Content format

**Example:**
```json
{
  "tool": "confluence_update_page",
  "arguments": {
    "page_id": "12345678",
    "content": "Updated content here...",
    "version_comment": "Added Q4 objectives",
    "format": "markdown"
  }
}
```

#### 5. `confluence_list_spaces`
List all accessible Confluence spaces.

**Parameters:**
- `type`: Space type filter ("global" or "personal")
- `limit`: Maximum results

**Example:**
```json
{
  "tool": "confluence_list_spaces",
  "arguments": {
    "type": "global",
    "limit": 50
  }
}
```

## 🔍 Common Use Cases

### 1. Daily Standup Automation
```javascript
// Search for your assigned issues
const myIssues = await jira_search_issues({
  jql: "assignee = currentUser() AND status != Done",
  fields: ["summary", "status", "priority"]
});
```

### 2. Sprint Planning
```javascript
// Get all issues in backlog
const backlog = await jira_search_issues({
  jql: "project = COLP AND status = Backlog ORDER BY priority DESC",
  max_results: 30
});
```

### 3. Documentation Updates
```javascript
// Update API documentation
await confluence_update_page({
  page_id: "98765432",
  content: "# API v2.0\n\n## New Endpoints\n...",
  version_comment: "Added v2.0 endpoints"
});
```

### 4. Issue Triage
```javascript
// Find unassigned critical bugs
const criticalBugs = await jira_search_issues({
  jql: "project = COLP AND issuetype = Bug AND priority = Critical AND assignee is EMPTY"
});
```

## 🛠 Advanced Configuration

### Custom Fields
To work with custom fields in Jira:

1. First, identify your custom field IDs:
```javascript
const issue = await jira_get_issue({
  issue_key: "COLP-1",
  expand: ["names"]
});
// Look for custom field IDs in the response
```

2. Use custom fields when creating/updating issues:
```javascript
await jira_create_issue({
  project_key: "COLP",
  issue_type: "Story",
  summary: "New feature",
  custom_fields: {
    "customfield_10001": "Value for custom field",
    "customfield_10002": ["multiple", "values"]
  }
});
```

### JQL Examples

Common JQL queries for different scenarios:

```sql
-- My open issues
assignee = currentUser() AND resolution = Unresolved

-- Issues updated in last week
updated >= -1w

-- High priority bugs in current sprint
project = COLP AND issuetype = Bug AND priority in (High, Critical) AND sprint in openSprints()

-- Issues with specific label
labels = "customer-reported"

-- Issues in epic
"Epic Link" = COLP-100

-- Overdue issues
duedate < now() AND resolution = Unresolved
```

### CQL Examples

Common CQL queries for Confluence:

```sql
-- Pages modified in last month
lastmodified > now("-4w")

-- Pages in specific space with label
space = DEV and label = "api-docs"

-- Pages created by specific user
creator = "john.doe@company.com"

-- Search in page titles only
title ~ "meeting notes"
```

## 🔒 Security Best Practices

1. **API Token Storage**: Never commit API tokens to version control
2. **Permissions**: Ensure your Atlassian user has appropriate permissions
3. **Rate Limiting**: Be mindful of Atlassian's API rate limits
4. **Data Sensitivity**: Be careful when handling sensitive issue data

## 🐛 Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Verify your API token is correct
   - Check that your email matches the account that created the token
   - Ensure your domain is correct (without .atlassian.net)

2. **Permission Denied**
   - Verify you have access to the project/space
   - Check issue/page permissions
   - Ensure your account has necessary Jira/Confluence permissions

3. **Invalid JQL/CQL**
   - Test your queries in Jira/Confluence UI first
   - Check field names are correct
   - Verify custom field IDs

### Debug Mode

Set environment variable for verbose logging:
```bash
DEBUG=mcp:* node mcp-atlassian-server.js
```

## 📚 Resources

- [Jira REST API Documentation](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [Confluence REST API Documentation](https://developer.atlassian.com/cloud/confluence/rest/)
- [JQL Reference](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-fields/)
- [CQL Reference](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/)

## 🤝 Contributing

To add new tools or improve existing ones:

1. Add tool definition in `setupToolHandlers()`
2. Implement the corresponding method
3. Update this README with the new tool documentation
4. Test thoroughly with your Atlassian instance

## 📄 License

MIT License - See LICENSE file for details






