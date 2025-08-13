#!/usr/bin/env node

/**
 * Atlassian MCP Server
 * 
 * Provides Model Context Protocol (MCP) tools for Atlassian (Jira & Confluence) integration.
 * Enables querying, creating, and managing Jira issues and Confluence pages.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from '@modelcontextprotocol/sdk/types.js';

import axios from 'axios';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import dotenv from 'dotenv';

// Load environment variables
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
dotenv.config({ path: join(__dirname, '../../.env') });

class AtlassianMCPServer {
  constructor() {
    this.server = new Server(
      {
        name: 'atlassian-mcp-server',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupErrorHandling();
    this.setupToolHandlers();

    // Validate required environment variables
    if (!process.env.ATLASSIAN_DOMAIN || !process.env.ATLASSIAN_EMAIL || !process.env.ATLASSIAN_API_TOKEN) {
      console.error('Missing required environment variables: ATLASSIAN_DOMAIN, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN');
      process.exit(1);
    }

    // Initialize Atlassian API client
    const auth = Buffer.from(`${process.env.ATLASSIAN_EMAIL}:${process.env.ATLASSIAN_API_TOKEN}`).toString('base64');
    
    this.atlassianApi = axios.create({
      baseURL: `https://${process.env.ATLASSIAN_DOMAIN}.atlassian.net`,
      headers: {
        'Authorization': `Basic ${auth}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    });
  }

  setupErrorHandling() {
    this.server.onerror = (error) => console.error('[MCP Error]', error);
    process.on('SIGINT', async () => {
      await this.server.close();
      process.exit(0);
    });
  }

  setupToolHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: [
        // Jira Tools
        {
          name: 'jira_search_issues',
          description: 'Search for Jira issues using JQL (Jira Query Language)',
          inputSchema: {
            type: 'object',
            properties: {
              jql: {
                type: 'string',
                description: 'JQL query string (e.g., "project = PROJ AND status = Open")'
              },
              max_results: {
                type: 'number',
                description: 'Maximum number of results to return (default: 50)',
                default: 50,
                minimum: 1,
                maximum: 100
              },
              fields: {
                type: 'array',
                description: 'Fields to include in the response (default: key, summary, status, assignee, reporter)',
                items: { type: 'string' }
              },
              expand: {
                type: 'array',
                description: 'Additional data to expand (e.g., "changelog", "renderedFields")',
                items: { type: 'string' }
              }
            },
            required: ['jql']
          }
        },
        {
          name: 'jira_get_issue',
          description: 'Get detailed information about a specific Jira issue',
          inputSchema: {
            type: 'object',
            properties: {
              issue_key: {
                type: 'string',
                description: 'The issue key (e.g., "PROJ-123")',
                pattern: '^[A-Z]+-\\d+$'
              },
              fields: {
                type: 'array',
                description: 'Specific fields to include',
                items: { type: 'string' }
              },
              expand: {
                type: 'array',
                description: 'Additional data to expand',
                items: { type: 'string' }
              }
            },
            required: ['issue_key']
          }
        },
        {
          name: 'jira_create_issue',
          description: 'Create a new Jira issue',
          inputSchema: {
            type: 'object',
            properties: {
              project_key: {
                type: 'string',
                description: 'Project key where the issue will be created'
              },
              issue_type: {
                type: 'string',
                description: 'Issue type (e.g., "Task", "Bug", "Story")'
              },
              summary: {
                type: 'string',
                description: 'Issue summary/title'
              },
              description: {
                type: 'string',
                description: 'Issue description (supports Jira markdown)'
              },
              assignee: {
                type: 'string',
                description: 'Assignee account ID or email'
              },
              priority: {
                type: 'string',
                description: 'Priority name (e.g., "High", "Medium", "Low")'
              },
              labels: {
                type: 'array',
                description: 'Labels to add to the issue',
                items: { type: 'string' }
              },
              components: {
                type: 'array',
                description: 'Component names to add to the issue',
                items: { type: 'string' }
              },
              custom_fields: {
                type: 'object',
                description: 'Custom field values as key-value pairs'
              }
            },
            required: ['project_key', 'issue_type', 'summary']
          }
        },
        {
          name: 'jira_update_issue',
          description: 'Update an existing Jira issue',
          inputSchema: {
            type: 'object',
            properties: {
              issue_key: {
                type: 'string',
                description: 'The issue key to update',
                pattern: '^[A-Z]+-\\d+$'
              },
              fields: {
                type: 'object',
                description: 'Fields to update with their new values'
              },
              notify_users: {
                type: 'boolean',
                description: 'Whether to send email notifications (default: true)',
                default: true
              }
            },
            required: ['issue_key', 'fields']
          }
        },
        {
          name: 'jira_add_comment',
          description: 'Add a comment to a Jira issue',
          inputSchema: {
            type: 'object',
            properties: {
              issue_key: {
                type: 'string',
                description: 'The issue key',
                pattern: '^[A-Z]+-\\d+$'
              },
              comment: {
                type: 'string',
                description: 'Comment text (supports Jira markdown)'
              },
              visibility: {
                type: 'object',
                description: 'Comment visibility restrictions',
                properties: {
                  type: {
                    type: 'string',
                    enum: ['group', 'role'],
                    description: 'Visibility type'
                  },
                  value: {
                    type: 'string',
                    description: 'Group name or role name'
                  }
                }
              }
            },
            required: ['issue_key', 'comment']
          }
        },
        {
          name: 'jira_transition_issue',
          description: 'Transition a Jira issue to a different status',
          inputSchema: {
            type: 'object',
            properties: {
              issue_key: {
                type: 'string',
                description: 'The issue key',
                pattern: '^[A-Z]+-\\d+$'
              },
              transition_name: {
                type: 'string',
                description: 'Name of the transition (e.g., "Done", "In Progress")'
              },
              comment: {
                type: 'string',
                description: 'Optional comment to add with the transition'
              },
              fields: {
                type: 'object',
                description: 'Fields to update during transition'
              }
            },
            required: ['issue_key', 'transition_name']
          }
        },
        // Confluence Tools
        {
          name: 'confluence_search_content',
          description: 'Search for Confluence pages and content',
          inputSchema: {
            type: 'object',
            properties: {
              cql: {
                type: 'string',
                description: 'CQL (Confluence Query Language) query string'
              },
              space_key: {
                type: 'string',
                description: 'Limit search to specific space'
              },
              type: {
                type: 'string',
                description: 'Content type to search',
                enum: ['page', 'blogpost', 'attachment', 'comment']
              },
              limit: {
                type: 'number',
                description: 'Maximum results (default: 25)',
                default: 25,
                minimum: 1,
                maximum: 100
              }
            },
            required: ['cql']
          }
        },
        {
          name: 'confluence_get_page',
          description: 'Get a specific Confluence page by ID or space/title',
          inputSchema: {
            type: 'object',
            properties: {
              page_id: {
                type: 'string',
                description: 'Page ID'
              },
              space_key: {
                type: 'string',
                description: 'Space key (required if using title)'
              },
              title: {
                type: 'string',
                description: 'Page title (requires space_key)'
              },
              expand: {
                type: 'array',
                description: 'Additional data to expand (e.g., "body.storage", "version", "ancestors")',
                items: { type: 'string' }
              }
            }
          }
        },
        {
          name: 'confluence_create_page',
          description: 'Create a new Confluence page',
          inputSchema: {
            type: 'object',
            properties: {
              space_key: {
                type: 'string',
                description: 'Space key where page will be created'
              },
              title: {
                type: 'string',
                description: 'Page title'
              },
              content: {
                type: 'string',
                description: 'Page content (supports Confluence storage format or markdown)'
              },
              parent_id: {
                type: 'string',
                description: 'Parent page ID (optional)'
              },
              format: {
                type: 'string',
                description: 'Content format',
                enum: ['storage', 'markdown'],
                default: 'markdown'
              }
            },
            required: ['space_key', 'title', 'content']
          }
        },
        {
          name: 'confluence_update_page',
          description: 'Update an existing Confluence page',
          inputSchema: {
            type: 'object',
            properties: {
              page_id: {
                type: 'string',
                description: 'Page ID to update'
              },
              title: {
                type: 'string',
                description: 'New page title (optional)'
              },
              content: {
                type: 'string',
                description: 'New page content'
              },
              version_comment: {
                type: 'string',
                description: 'Version comment explaining the changes'
              },
              format: {
                type: 'string',
                description: 'Content format',
                enum: ['storage', 'markdown'],
                default: 'markdown'
              }
            },
            required: ['page_id', 'content']
          }
        },
        // Project and Space Management
        {
          name: 'jira_list_projects',
          description: 'List all accessible Jira projects',
          inputSchema: {
            type: 'object',
            properties: {
              expand: {
                type: 'array',
                description: 'Additional project data to include',
                items: { type: 'string' }
              }
            }
          }
        },
        {
          name: 'confluence_list_spaces',
          description: 'List all accessible Confluence spaces',
          inputSchema: {
            type: 'object',
            properties: {
              type: {
                type: 'string',
                description: 'Space type filter',
                enum: ['global', 'personal']
              },
              limit: {
                type: 'number',
                description: 'Maximum results',
                default: 25
              }
            }
          }
        }
      ],
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          // Jira Tools Implementation
          case 'jira_search_issues':
            return await this.searchJiraIssues(args);
          case 'jira_get_issue':
            return await this.getJiraIssue(args);
          case 'jira_create_issue':
            return await this.createJiraIssue(args);
          case 'jira_update_issue':
            return await this.updateJiraIssue(args);
          case 'jira_add_comment':
            return await this.addJiraComment(args);
          case 'jira_transition_issue':
            return await this.transitionJiraIssue(args);
          case 'jira_list_projects':
            return await this.listJiraProjects(args);
          
          // Confluence Tools Implementation
          case 'confluence_search_content':
            return await this.searchConfluence(args);
          case 'confluence_get_page':
            return await this.getConfluencePage(args);
          case 'confluence_create_page':
            return await this.createConfluencePage(args);
          case 'confluence_update_page':
            return await this.updateConfluencePage(args);
          case 'confluence_list_spaces':
            return await this.listConfluenceSpaces(args);
            
          default:
            throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
        }
      } catch (error) {
        if (error instanceof McpError) throw error;
        
        console.error(`Error in ${name}:`, error);
        throw new McpError(
          ErrorCode.InternalError,
          `Error executing ${name}: ${error.message}`
        );
      }
    });
  }

  // Jira Methods
  async searchJiraIssues({ jql, max_results = 50, fields, expand }) {
    try {
      const params = {
        jql,
        maxResults: max_results,
        fields: fields || ['key', 'summary', 'status', 'assignee', 'reporter', 'created', 'updated'],
        expand: expand || []
      };

      const response = await this.atlassianApi.get('/rest/api/3/search', { params });
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              total: response.data.total,
              issues: response.data.issues.map(issue => ({
                key: issue.key,
                id: issue.id,
                self: issue.self,
                fields: issue.fields
              }))
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to search Jira issues: ${error.message}`);
    }
  }

  async getJiraIssue({ issue_key, fields, expand }) {
    try {
      const params = {};
      if (fields) params.fields = fields.join(',');
      if (expand) params.expand = expand.join(',');

      const response = await this.atlassianApi.get(`/rest/api/3/issue/${issue_key}`, { params });
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(response.data, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to get issue ${issue_key}: ${error.message}`);
    }
  }

  async createJiraIssue({ project_key, issue_type, summary, description, assignee, priority, labels, components, custom_fields }) {
    try {
      const fields = {
        project: { key: project_key },
        issuetype: { name: issue_type },
        summary
      };

      if (description) fields.description = {
        type: 'doc',
        version: 1,
        content: [{
          type: 'paragraph',
          content: [{
            type: 'text',
            text: description
          }]
        }]
      };

      if (assignee) fields.assignee = { accountId: assignee };
      if (priority) fields.priority = { name: priority };
      if (labels) fields.labels = labels;
      if (components) fields.components = components.map(name => ({ name }));
      
      // Add custom fields
      if (custom_fields) {
        Object.assign(fields, custom_fields);
      }

      const response = await this.atlassianApi.post('/rest/api/3/issue', { fields });
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              key: response.data.key,
              id: response.data.id,
              self: response.data.self,
              message: `Issue ${response.data.key} created successfully`
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to create issue: ${error.message}`);
    }
  }

  async updateJiraIssue({ issue_key, fields, notify_users = true }) {
    try {
      const params = { notifyUsers: notify_users };
      
      await this.atlassianApi.put(
        `/rest/api/3/issue/${issue_key}`,
        { fields },
        { params }
      );
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              success: true,
              message: `Issue ${issue_key} updated successfully`
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to update issue ${issue_key}: ${error.message}`);
    }
  }

  async addJiraComment({ issue_key, comment, visibility }) {
    try {
      const body = {
        body: {
          type: 'doc',
          version: 1,
          content: [{
            type: 'paragraph',
            content: [{
              type: 'text',
              text: comment
            }]
          }]
        }
      };

      if (visibility) {
        body.visibility = visibility;
      }

      const response = await this.atlassianApi.post(
        `/rest/api/3/issue/${issue_key}/comment`,
        body
      );
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              id: response.data.id,
              created: response.data.created,
              message: `Comment added to ${issue_key}`
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to add comment to ${issue_key}: ${error.message}`);
    }
  }

  async transitionJiraIssue({ issue_key, transition_name, comment, fields }) {
    try {
      // First, get available transitions
      const transitionsResponse = await this.atlassianApi.get(
        `/rest/api/3/issue/${issue_key}/transitions`
      );
      
      const transition = transitionsResponse.data.transitions.find(
        t => t.name.toLowerCase() === transition_name.toLowerCase()
      );
      
      if (!transition) {
        throw new Error(`Transition "${transition_name}" not found`);
      }

      const body = {
        transition: { id: transition.id }
      };

      if (comment) {
        body.update = {
          comment: [{
            add: {
              body: {
                type: 'doc',
                version: 1,
                content: [{
                  type: 'paragraph',
                  content: [{
                    type: 'text',
                    text: comment
                  }]
                }]
              }
            }
          }]
        };
      }

      if (fields) {
        body.fields = fields;
      }

      await this.atlassianApi.post(
        `/rest/api/3/issue/${issue_key}/transitions`,
        body
      );
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              success: true,
              message: `Issue ${issue_key} transitioned to ${transition_name}`
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to transition issue ${issue_key}: ${error.message}`);
    }
  }

  async listJiraProjects({ expand }) {
    try {
      const params = {};
      if (expand) params.expand = expand.join(',');

      const response = await this.atlassianApi.get('/rest/api/3/project', { params });
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(
              response.data.map(project => ({
                id: project.id,
                key: project.key,
                name: project.name,
                projectTypeKey: project.projectTypeKey,
                lead: project.lead,
                ...project
              })),
              null,
              2
            )
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to list projects: ${error.message}`);
    }
  }

  // Confluence Methods
  async searchConfluence({ cql, space_key, type, limit = 25 }) {
    try {
      let finalCql = cql;
      if (space_key) {
        finalCql += ` AND space = "${space_key}"`;
      }
      if (type) {
        finalCql += ` AND type = "${type}"`;
      }

      const params = {
        cql: finalCql,
        limit
      };

      const response = await this.atlassianApi.get('/wiki/rest/api/content/search', { params });
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              size: response.data.size,
              results: response.data.results.map(content => ({
                id: content.id,
                type: content.type,
                title: content.title,
                space: content.space,
                lastModified: content.version?.when,
                _links: content._links
              }))
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to search Confluence: ${error.message}`);
    }
  }

  async getConfluencePage({ page_id, space_key, title, expand }) {
    try {
      let url;
      const params = {};
      
      if (page_id) {
        url = `/wiki/rest/api/content/${page_id}`;
      } else if (space_key && title) {
        url = '/wiki/rest/api/content';
        params.spaceKey = space_key;
        params.title = title;
      } else {
        throw new Error('Either page_id or both space_key and title are required');
      }

      if (expand) {
        params.expand = expand.join(',');
      }

      const response = await this.atlassianApi.get(url, { params });
      
      let pageData = response.data;
      if (Array.isArray(pageData.results)) {
        pageData = pageData.results[0];
      }

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(pageData, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to get Confluence page: ${error.message}`);
    }
  }

  async createConfluencePage({ space_key, title, content, parent_id, format = 'markdown' }) {
    try {
      let storageContent = content;
      
      // Convert markdown to storage format if needed
      if (format === 'markdown') {
        storageContent = this.markdownToStorage(content);
      }

      const body = {
        type: 'page',
        title,
        space: { key: space_key },
        body: {
          storage: {
            value: storageContent,
            representation: 'storage'
          }
        }
      };

      if (parent_id) {
        body.ancestors = [{ id: parent_id }];
      }

      const response = await this.atlassianApi.post('/wiki/rest/api/content', body);
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              id: response.data.id,
              title: response.data.title,
              version: response.data.version?.number,
              webUrl: `https://${process.env.ATLASSIAN_DOMAIN}.atlassian.net/wiki${response.data._links.webui}`,
              message: `Page "${title}" created successfully`
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to create Confluence page: ${error.message}`);
    }
  }

  async updateConfluencePage({ page_id, title, content, version_comment, format = 'markdown' }) {
    try {
      // Get current page to get version
      const currentPage = await this.atlassianApi.get(`/wiki/rest/api/content/${page_id}`);
      
      let storageContent = content;
      if (format === 'markdown') {
        storageContent = this.markdownToStorage(content);
      }

      const body = {
        type: 'page',
        title: title || currentPage.data.title,
        version: {
          number: currentPage.data.version.number + 1,
          message: version_comment
        },
        body: {
          storage: {
            value: storageContent,
            representation: 'storage'
          }
        }
      };

      const response = await this.atlassianApi.put(`/wiki/rest/api/content/${page_id}`, body);
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              id: response.data.id,
              title: response.data.title,
              version: response.data.version?.number,
              message: `Page updated to version ${response.data.version?.number}`
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to update Confluence page: ${error.message}`);
    }
  }

  async listConfluenceSpaces({ type, limit = 25 }) {
    try {
      const params = { limit };
      if (type) params.type = type;

      const response = await this.atlassianApi.get('/wiki/rest/api/space', { params });
      
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(
              response.data.results.map(space => ({
                id: space.id,
                key: space.key,
                name: space.name,
                type: space.type,
                status: space.status,
                _links: space._links
              })),
              null,
              2
            )
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to list Confluence spaces: ${error.message}`);
    }
  }

  // Helper method to convert markdown to Confluence storage format (basic implementation)
  markdownToStorage(markdown) {
    // This is a simplified conversion - you might want to use a proper markdown-to-confluence library
    let storage = markdown;
    
    // Convert headers
    storage = storage.replace(/^### (.*)/gm, '<h3>$1</h3>');
    storage = storage.replace(/^## (.*)/gm, '<h2>$1</h2>');
    storage = storage.replace(/^# (.*)/gm, '<h1>$1</h1>');
    
    // Convert bold and italic
    storage = storage.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    storage = storage.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    
    // Convert code blocks
    storage = storage.replace(/```(\w+)?\n([\s\S]*?)```/g, '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">$1</ac:parameter><ac:plain-text-body><![CDATA[$2]]></ac:plain-text-body></ac:structured-macro>');
    
    // Convert inline code
    storage = storage.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Convert line breaks
    storage = storage.replace(/\n\n/g, '</p><p>');
    storage = '<p>' + storage + '</p>';
    
    return storage;
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Atlassian MCP server running on stdio');
  }
}

// Start the server
const server = new AtlassianMCPServer();
server.run().catch(console.error);






