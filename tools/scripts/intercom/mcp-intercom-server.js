#!/usr/bin/env node

/**
 * Intercom MCP Server
 * 
 * Provides Model Context Protocol (MCP) tools for Intercom data export and analysis.
 * Converts the fast-export-intercom.js functionality into callable MCP tools.
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

class IntercomMCPServer {
  constructor() {
    this.server = new Server(
      {
        name: 'intercom-export-server',
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

    // Initialize Intercom API client
    this.intercomApi = axios.create({
      baseURL: 'https://api.intercom.io',
      headers: {
        'Authorization': `Bearer ${process.env.INTERCOM_ACCESS_TOKEN}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Intercom-Version': '2.13'
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
        {
          name: 'export_intercom_conversations',
          description: 'Export Intercom conversations from a specific date range to CSV format',
          inputSchema: {
            type: 'object',
            properties: {
              from_date: {
                type: 'string',
                description: 'Start date in YYYY-MM-DD format',
                pattern: '^\\d{4}-\\d{2}-\\d{2}$'
              },
              to_date: {
                type: 'string',
                description: 'End date in YYYY-MM-DD format (defaults to today)',
                pattern: '^\\d{4}-\\d{2}-\\d{2}$'
              },
              output_format: {
                type: 'string',
                description: 'Output format: "csv" or "json"',
                enum: ['csv', 'json'],
                default: 'csv'
              },
              limit: {
                type: 'number',
                description: 'Maximum number of conversations to export (default: no limit)',
                minimum: 1
              },
              include_message_content: {
                type: 'boolean',
                description: 'Whether to include full message content (default: true)',
                default: true
              }
            },
            required: ['from_date'],
            additionalProperties: false
          }
        },
        {
          name: 'get_intercom_conversation_stats',
          description: 'Get statistics about conversations in a date range without full export',
          inputSchema: {
            type: 'object',
            properties: {
              from_date: {
                type: 'string',
                description: 'Start date in YYYY-MM-DD format',
                pattern: '^\\d{4}-\\d{2}-\\d{2}$'
              },
              to_date: {
                type: 'string',
                description: 'End date in YYYY-MM-DD format (defaults to today)',
                pattern: '^\\d{4}-\\d{2}-\\d{2}$'
              }
            },
            required: ['from_date'],
            additionalProperties: false
          }
        },
        {
          name: 'search_intercom_conversations',
          description: 'Search for specific conversations based on criteria',
          inputSchema: {
            type: 'object',
            properties: {
              query: {
                type: 'string',
                description: 'Search query or keywords'
              },
              from_date: {
                type: 'string',
                description: 'Start date in YYYY-MM-DD format',
                pattern: '^\\d{4}-\\d{2}-\\d{2}$'
              },
              to_date: {
                type: 'string',
                description: 'End date in YYYY-MM-DD format',
                pattern: '^\\d{4}-\\d{2}-\\d{2}$'
              },
              state: {
                type: 'string',
                description: 'Conversation state to filter by',
                enum: ['open', 'closed', 'snoozed']
              },
              limit: {
                type: 'number',
                description: 'Maximum number of results (default: 50)',
                minimum: 1,
                maximum: 150,
                default: 50
              }
            },
            additionalProperties: false
          }
        }
      ]
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          case 'export_intercom_conversations':
            return await this.exportConversations(args);
          case 'get_intercom_conversation_stats':
            return await this.getConversationStats(args);
          case 'search_intercom_conversations':
            return await this.searchConversations(args);
          default:
            throw new McpError(
              ErrorCode.MethodNotFound,
              `Unknown tool: ${name}`
            );
        }
      } catch (error) {
        if (error instanceof McpError) {
          throw error;
        }
        throw new McpError(
          ErrorCode.InternalError,
          `Tool execution failed: ${error.message}`
        );
      }
    });
  }

  // Retry mechanism for API requests
  async retryableRequest(fn, maxRetries = 3, delay = 750) {
    let lastError;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error;

        if (attempt < maxRetries) {
          if (error.response && error.response.status === 429) {
            const retryAfter = parseInt(error.response.headers['retry-after'] || '5', 10);
            const waitTime = retryAfter * 1000 || Math.min(delay * Math.pow(2, attempt), 30000);
            await new Promise(resolve => setTimeout(resolve, waitTime));
          } else {
            const waitTime = delay * Math.pow(1.5, attempt - 1);
            await new Promise(resolve => setTimeout(resolve, waitTime));
          }
        }
      }
    }

    throw lastError;
  }

  // Fetch conversation IDs for a date range
  async fetchConversationIds(fromDate, toDate, limit = null) {
    const fromTimestamp = Math.floor(new Date(fromDate).getTime() / 1000);
    const toTimestamp = Math.floor(new Date(toDate).getTime() / 1000);

    const allIds = [];
    let hasMore = true;
    const maxPerPage = 150;
    let startingAfter = null;

    while (hasMore && (limit === null || allIds.length < limit)) {
      try {
        const searchQuery = {
          query: {
            operator: 'AND',
            value: [
              {
                field: 'created_at',
                operator: '>=',
                value: fromTimestamp
              },
              {
                field: 'created_at',
                operator: '<=',
                value: toTimestamp
              }
            ]
          },
          pagination: {
            per_page: Math.min(maxPerPage, limit ? limit - allIds.length : maxPerPage)
          }
        };

        if (startingAfter) {
          searchQuery.pagination.starting_after = startingAfter;
        }

        const response = await this.retryableRequest(async () => {
          return await this.intercomApi.post('/conversations/search', searchQuery);
        });

        const conversations = response.data.conversations || [];

        if (conversations.length === 0) {
          hasMore = false;
          continue;
        }

        const ids = conversations.map(c => c.id);
        allIds.push(...ids);

        if (!response.data.pages.next || !response.data.pages.next.starting_after) {
          hasMore = false;
        } else {
          startingAfter = response.data.pages.next.starting_after;
        }

        if (limit && allIds.length >= limit) {
          hasMore = false;
        }
      } catch (error) {
        throw new Error(`Failed to fetch conversation IDs: ${error.message}`);
      }
    }

    return allIds.slice(0, limit || allIds.length);
  }

  // Get detailed conversation data
  async getConversationDetails(conversationId) {
    try {
      return await this.retryableRequest(async () => {
        const response = await this.intercomApi.get(`/conversations/${conversationId}`);
        return response.data;
      });
    } catch (error) {
      throw new Error(`Failed to get conversation ${conversationId}: ${error.message}`);
    }
  }

  // Process conversation to extract structured data
  async processConversation(conversation, includeContent = true) {
    if (!conversation) return [];

    const conversationId = conversation.id;
    const createdAt = conversation.created_at ? new Date(conversation.created_at * 1000).toISOString() : '';
    const updatedAt = conversation.updated_at ? new Date(conversation.updated_at * 1000).toISOString() : '';
    const state = conversation.state || '';
    const read = conversation.read !== undefined ? conversation.read.toString() : '';

    let ownerName = '';
    if (conversation.admin_assignee_id && conversation.teammates && conversation.teammates.admins) {
      const admin = conversation.teammates.admins.find(a => a.id === conversation.admin_assignee_id.toString());
      if (admin && admin.name) {
        ownerName = admin.name;
      }
    }

    let userId = '';
    let companyId = '';
    if (conversation.contacts && conversation.contacts.contacts && conversation.contacts.contacts.length > 0) {
      const contact = conversation.contacts.contacts[0];
      userId = contact.id || '';
      if (contact.companies && contact.companies.length > 0) {
        companyId = contact.companies[0].id;
      }
    }

    const rows = [];

    // Process main conversation message
    if (conversation.source) {
      const mainRow = {
        conversation_id: conversationId,
        created_at: createdAt,
        updated_at: updatedAt,
        message_id: conversation.source.id || '',
        message_body: includeContent ? (conversation.source.body || '') : '[CONTENT_HIDDEN]',
        part_type: 'conversation',
        author_type: conversation.source.author ? conversation.source.author.type : '',
        author_id: conversation.source.author ? conversation.source.author.id : '',
        author_name: conversation.source.author ? conversation.source.author.name : '',
        owner_name: ownerName,
        user_id: userId,
        company_id: companyId,
        state: state,
        read: read
      };
      rows.push(mainRow);
    }

    // Process conversation parts (replies)
    if (conversation.conversation_parts && conversation.conversation_parts.conversation_parts) {
      for (const part of conversation.conversation_parts.conversation_parts) {
        const partRow = {
          conversation_id: conversationId,
          created_at: part.created_at ? new Date(part.created_at * 1000).toISOString() : '',
          updated_at: part.updated_at ? new Date(part.updated_at * 1000).toISOString() : '',
          message_id: part.id || '',
          message_body: includeContent ? (part.body || '') : '[CONTENT_HIDDEN]',
          part_type: part.part_type || 'comment',
          author_type: part.author ? part.author.type : '',
          author_id: part.author ? part.author.id : '',
          author_name: part.author ? part.author.name : '',
          owner_name: ownerName,
          user_id: userId,
          company_id: companyId,
          state: state,
          read: read
        };
        rows.push(partRow);
      }
    }

    return rows;
  }

  // Tool: Export conversations
  async exportConversations(args) {
    const {
      from_date,
      to_date = new Date().toISOString().split('T')[0],
      output_format = 'csv',
      limit,
      include_message_content = true
    } = args;

    try {
      // Validate API token
      if (!process.env.INTERCOM_ACCESS_TOKEN) {
        throw new Error('INTERCOM_ACCESS_TOKEN not found in environment variables');
      }

      // Fetch conversation IDs
      const conversationIds = await this.fetchConversationIds(from_date, to_date, limit);

      if (conversationIds.length === 0) {
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              message: 'No conversations found in the specified date range',
              date_range: { from: from_date, to: to_date },
              total_conversations: 0,
              data: []
            }, null, 2)
          }]
        };
      }

      // Process conversations with concurrency control
      const maxConcurrent = 10; // Reduced for MCP to avoid overwhelming
      const allRows = [];
      const processedConversations = [];

      for (let i = 0; i < conversationIds.length; i += maxConcurrent) {
        const batch = conversationIds.slice(i, i + maxConcurrent);
        const batchPromises = batch.map(async (id) => {
          try {
            const conversation = await this.getConversationDetails(id);
            const rows = await this.processConversation(conversation, include_message_content);
            return { id, rows, conversation };
          } catch (error) {
            return { id, error: error.message, rows: [] };
          }
        });

        const batchResults = await Promise.all(batchPromises);
        
        for (const result of batchResults) {
          if (result.rows.length > 0) {
            allRows.push(...result.rows);
          }
          if (result.conversation) {
            processedConversations.push({
              id: result.id,
              created_at: result.conversation.created_at,
              state: result.conversation.state,
              message_count: result.rows.length
            });
          }
        }
      }

      const responseData = {
        success: true,
        date_range: { from: from_date, to: to_date },
        total_conversations: conversationIds.length,
        total_messages: allRows.length,
        output_format,
        include_message_content,
        conversations_summary: processedConversations,
        data: output_format === 'csv' ? this.convertToCSV(allRows) : allRows
      };

      return {
        content: [{
          type: 'text',
          text: JSON.stringify(responseData, null, 2)
        }]
      };

    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Export failed: ${error.message}`
      );
    }
  }

  // Tool: Get conversation statistics
  async getConversationStats(args) {
    const {
      from_date,
      to_date = new Date().toISOString().split('T')[0]
    } = args;

    try {
      const conversationIds = await this.fetchConversationIds(from_date, to_date, 100);
      
      // Get sample of conversations for stats
      const sampleSize = Math.min(20, conversationIds.length);
      const sampleIds = conversationIds.slice(0, sampleSize);
      
      const statsPromises = sampleIds.map(async (id) => {
        try {
          const conversation = await this.getConversationDetails(id);
          return {
            id,
            state: conversation.state,
            created_at: conversation.created_at,
            parts_count: conversation.conversation_parts ? conversation.conversation_parts.conversation_parts.length : 0,
            has_admin_assignee: !!conversation.admin_assignee_id
          };
        } catch (error) {
          return null;
        }
      });

      const sampleStats = (await Promise.all(statsPromises)).filter(Boolean);

      const stats = {
        success: true,
        date_range: { from: from_date, to: to_date },
        total_conversations_found: conversationIds.length,
        sample_size: sampleStats.length,
        statistics: {
          states: this.groupBy(sampleStats, 'state'),
          avg_parts_per_conversation: sampleStats.reduce((sum, s) => sum + s.parts_count, 0) / sampleStats.length,
          assigned_conversations: sampleStats.filter(s => s.has_admin_assignee).length,
          assignment_rate: sampleStats.filter(s => s.has_admin_assignee).length / sampleStats.length
        }
      };

      return {
        content: [{
          type: 'text',
          text: JSON.stringify(stats, null, 2)
        }]
      };

    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Stats retrieval failed: ${error.message}`
      );
    }
  }

  // Tool: Search conversations
  async searchConversations(args) {
    const {
      query,
      from_date,
      to_date = new Date().toISOString().split('T')[0],
      state,
      limit = 50
    } = args;

    try {
      const searchQuery = {
        query: {
          operator: 'AND',
          value: []
        },
        pagination: {
          per_page: Math.min(limit, 150)
        }
      };

      // Add date filters if provided
      if (from_date) {
        const fromTimestamp = Math.floor(new Date(from_date).getTime() / 1000);
        searchQuery.query.value.push({
          field: 'created_at',
          operator: '>=',
          value: fromTimestamp
        });
      }

      if (to_date) {
        const toTimestamp = Math.floor(new Date(to_date).getTime() / 1000);
        searchQuery.query.value.push({
          field: 'created_at',
          operator: '<=',
          value: toTimestamp
        });
      }

      // Add state filter if provided
      if (state) {
        searchQuery.query.value.push({
          field: 'state',
          operator: '=',
          value: state
        });
      }

      const response = await this.retryableRequest(async () => {
        return await this.intercomApi.post('/conversations/search', searchQuery);
      });

      const conversations = response.data.conversations || [];
      
      // Filter by query if provided (simple text search in source body)
      let filteredConversations = conversations;
      if (query) {
        filteredConversations = conversations.filter(conv => {
          const body = conv.source?.body?.toLowerCase() || '';
          return body.includes(query.toLowerCase());
        });
      }

      const results = {
        success: true,
        search_criteria: { query, from_date, to_date, state, limit },
        total_found: filteredConversations.length,
        conversations: filteredConversations.map(conv => ({
          id: conv.id,
          created_at: conv.created_at ? new Date(conv.created_at * 1000).toISOString() : '',
          state: conv.state,
          source_body_preview: conv.source?.body?.substring(0, 200) || '',
          admin_assignee_id: conv.admin_assignee_id,
          contact_count: conv.contacts?.contacts?.length || 0
        }))
      };

      return {
        content: [{
          type: 'text',
          text: JSON.stringify(results, null, 2)
        }]
      };

    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Search failed: ${error.message}`
      );
    }
  }

  // Utility: Convert data to CSV format
  convertToCSV(rows) {
    if (rows.length === 0) return '';

    const headers = Object.keys(rows[0]);
    const csvRows = [
      headers.map(h => `"${h}"`).join(','),
      ...rows.map(row => 
        headers.map(h => `"${String(row[h] || '').replace(/"/g, '""')}"`).join(',')
      )
    ];

    return csvRows.join('\n');
  }

  // Utility: Group array by property
  groupBy(array, property) {
    return array.reduce((groups, item) => {
      const key = item[property];
      groups[key] = (groups[key] || 0) + 1;
      return groups;
    }, {});
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Intercom MCP server running on stdio');
  }
}

const server = new IntercomMCPServer();
server.run().catch(console.error); 