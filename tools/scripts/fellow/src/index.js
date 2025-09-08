#!/usr/bin/env node

/**
 * Fellow Meeting App MCP Server
 * 
 * Provides Model Context Protocol (MCP) tools for Fellow's meeting app,
 * enabling access to meetings, contacts, transcripts, and copilot features.
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";

import { toolSchemas } from "./tools/toolSchemas.js";
import { toolHandlers } from "./tools/handlers.js";

import dotenv from 'dotenv';
dotenv.config();

class FellowMCPServer {
  constructor() {
    this.server = new Server(
      {
        name: "fellow-meeting-server",
        version: "1.0.0",
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupErrorHandling();
    this.setupToolHandlers();
    
    console.error('Fellow Meeting MCP Server initialized');
    console.error('Available tools:', toolSchemas.map(t => t.name).join(', '));
  }

  setupErrorHandling() {
    this.server.onerror = (error) => {
      console.error('[Fellow MCP Error]', error);
    };

    process.on('SIGINT', async () => {
      console.error('Shutting down Fellow MCP Server...');
      await this.server.close();
      process.exit(0);
    });

    process.on('uncaughtException', (error) => {
      console.error('Uncaught Exception:', error);
      process.exit(1);
    });
  }

  setupToolHandlers() {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: toolSchemas,
      };
    });

    // Handle tool execution requests
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        const handler = toolHandlers.get(name);

        if (!handler) {
          throw new McpError(
            ErrorCode.MethodNotFound, 
            `Tool '${name}' not found. Available tools: ${Array.from(toolHandlers.keys()).join(', ')}`
          );
        }

        if (typeof handler !== "function") {
          throw new McpError(
            ErrorCode.InternalError,
            `Tool handler for '${name}' is not a function`
          );
        }

        console.error(`Executing tool: ${name} with args:`, args);
        
        const results = await handler(args || {});
        
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(results, null, 2),
            },
          ],
        };

      } catch (error) {
        console.error(`Tool execution error for '${name}':`, error);
        
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

  async run() {
    try {
      const transport = new StdioServerTransport();
      await this.server.connect(transport);
      console.error('Fellow Meeting MCP server running on stdio');
    } catch (error) {
      console.error('Failed to start Fellow MCP server:', error);
      process.exit(1);
    }
  }
}

// Start the server
const server = new FellowMCPServer();
server.run().catch(console.error);


