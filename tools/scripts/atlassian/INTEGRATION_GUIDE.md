# Atlassian MCP Server Integration Guide

This guide explains how to integrate the Atlassian MCP server with your AI assistant (Claude, Cursor, or other MCP-compatible tools).

## 🚀 Quick Integration

### For Cursor IDE

1. **Add to Cursor Settings**
   
   Open your Cursor settings and add the Atlassian MCP server configuration:

   ```json
   {
     "mcpServers": {
       "atlassian": {
         "command": "node",
         "args": ["/path/to/openai-cookbook/tools/scripts/atlassian/mcp-atlassian-server.js"],
         "env": {
           "ATLASSIAN_DOMAIN": "your-domain",
           "ATLASSIAN_EMAIL": "your-email@company.com",
           "ATLASSIAN_API_TOKEN": "your-api-token"
         }
       }
     }
   }
   ```

2. **Restart Cursor** to load the new MCP server

3. **Use in your prompts**:
   ```
   "Search for all open bugs in project COLP"
   "Create a new task for implementing the login feature"
   "Update issue COLP-123 to Done status"
   ```

### For Claude Desktop

1. **Configure Claude Desktop** (when MCP support is available):
   ```json
   {
     "mcpServers": {
       "atlassian": {
         "command": "node",
         "args": ["mcp-atlassian-server.js"],
         "cwd": "/path/to/tools/scripts/atlassian"
       }
     }
   }
   ```

## 📋 Common Workflows

### 1. Daily Standup Assistant

Ask your AI: "What are my open Jira tasks and what did I complete yesterday?"

The AI will use:
- `jira_search_issues` to find your assigned tasks
- `jira_search_issues` with date filters to find recently completed work

### 2. Sprint Planning Helper

Ask: "Show me all unassigned high-priority bugs in the backlog"

The AI will:
- Use `jira_search_issues` with JQL to find matching issues
- Format and present them for planning

### 3. Documentation Manager

Ask: "Create a new Confluence page for the API documentation in the DEV space"

The AI will:
- Use `confluence_create_page` to create the page
- Return the URL for easy access

### 4. Issue Triage

Ask: "Find all customer-reported bugs that haven't been assigned yet"

The AI will:
- Search using labels and assignment status
- Present issues with priority and creation date

## 🔧 Advanced Integration Examples

### Custom AI Commands

Create custom commands in your AI assistant:

```javascript
// Sprint health check
async function checkSprintHealth(sprintName) {
  // Get all issues in sprint
  const sprintIssues = await mcp.call('jira_search_issues', {
    jql: `sprint = "${sprintName}"`,
    fields: ['status', 'assignee', 'priority', 'created']
  });
  
  // Analyze and report
  return analyzeSprintMetrics(sprintIssues);
}

// Auto-documentation
async function documentFeature(issueKey) {
  // Get issue details
  const issue = await mcp.call('jira_get_issue', {
    issue_key: issueKey
  });
  
  // Create documentation page
  const page = await mcp.call('confluence_create_page', {
    space_key: 'DOCS',
    title: `Feature: ${issue.fields.summary}`,
    content: generateDocumentation(issue)
  });
  
  // Link back to Jira
  await mcp.call('jira_add_comment', {
    issue_key: issueKey,
    comment: `Documentation created: ${page.url}`
  });
}
```

### Automation Recipes

#### Recipe 1: Weekly Report Generator
```javascript
// Generate weekly report of completed work
const weeklyReport = async () => {
  const completed = await mcp.call('jira_search_issues', {
    jql: 'status changed to Done during (-1w, now()) AND assignee = currentUser()',
    fields: ['summary', 'issuetype', 'resolutiondate']
  });
  
  const report = formatWeeklyReport(completed);
  
  await mcp.call('confluence_create_page', {
    space_key: 'REPORTS',
    title: `Weekly Report - ${new Date().toISOString().split('T')[0]}`,
    content: report
  });
};
```

#### Recipe 2: Bug Escalation
```javascript
// Escalate old high-priority bugs
const escalateBugs = async () => {
  const oldBugs = await mcp.call('jira_search_issues', {
    jql: 'issuetype = Bug AND priority = High AND created < -2w AND status != Done',
    fields: ['key', 'summary', 'reporter']
  });
  
  for (const bug of oldBugs.issues) {
    await mcp.call('jira_update_issue', {
      issue_key: bug.key,
      fields: {
        priority: { name: 'Critical' }
      }
    });
    
    await mcp.call('jira_add_comment', {
      issue_key: bug.key,
      comment: 'Auto-escalated: High priority bug open for more than 2 weeks'
    });
  }
};
```

## 🎯 Best Practices

### 1. JQL Query Optimization

Instead of:
```sql
project = COLP  -- This gets ALL issues
```

Use:
```sql
project = COLP AND updated >= -7d  -- Only recent updates
```

### 2. Batch Operations

When updating multiple issues, consider:
- Rate limiting (Atlassian has API limits)
- Using bulk operations where available
- Adding delays between operations

### 3. Error Handling

Always handle potential errors:
```javascript
try {
  const result = await mcp.call('jira_create_issue', {...});
} catch (error) {
  if (error.message.includes('permissions')) {
    // Handle permission errors
  } else if (error.message.includes('validation')) {
    // Handle validation errors
  }
}
```

## 🔐 Security Considerations

1. **API Token Management**
   - Never share API tokens in prompts
   - Use environment variables
   - Rotate tokens regularly

2. **Permission Scoping**
   - Create tokens with minimal required permissions
   - Use read-only tokens when possible

3. **Data Privacy**
   - Be mindful of sensitive issue content
   - Don't expose internal issues publicly

## 📊 Monitoring and Logging

### Enable Debug Logging

Set environment variable:
```bash
DEBUG=mcp:atlassian:* node mcp-atlassian-server.js
```

### Track API Usage

Monitor your Atlassian API usage at:
- Jira: `https://your-domain.atlassian.net/secure/ViewProfile.jspa`
- Check "API tokens" section for usage

## 🚨 Troubleshooting

### Common Issues

1. **"Tool not found" errors**
   - Ensure MCP server is running
   - Check tool name spelling
   - Verify server configuration

2. **Authentication failures**
   - Regenerate API token
   - Verify email matches token owner
   - Check domain configuration

3. **Permission errors**
   - Verify project/space access
   - Check issue-level permissions
   - Ensure API token has required scopes

### Debug Commands

Test connection:
```
Ask AI: "List all available Jira projects"
```

Test permissions:
```
Ask AI: "Show me my profile information from Jira"
```

## 📚 Additional Resources

- [MCP Protocol Documentation](https://github.com/modelcontextprotocol/mcp)
- [Atlassian API Documentation](https://developer.atlassian.com/cloud/)
- [JQL Tutorial](https://www.atlassian.com/software/jira/guides/expand-jira/jql)
- [CQL Tutorial](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/)

## 🤝 Getting Help

- Check the README-MCP.md for detailed tool documentation
- Review error messages carefully - they often indicate the solution
- Test queries in Jira/Confluence UI first
- Use the test script: `node test-mcp.js`






