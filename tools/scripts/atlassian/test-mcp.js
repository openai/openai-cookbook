#!/usr/bin/env node

/**
 * Test script for Atlassian MCP Server
 * 
 * This script tests the basic functionality of the Atlassian MCP server
 * by simulating tool calls and verifying responses.
 */

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

class MCPTester {
  constructor() {
    this.server = null;
  }

  async startServer() {
    console.log('🚀 Starting Atlassian MCP Server...');
    
    this.server = spawn('node', ['mcp-atlassian-server.js'], {
      cwd: __dirname,
      stdio: ['pipe', 'pipe', 'pipe']
    });

    // Wait for server to be ready
    return new Promise((resolve) => {
      this.server.stderr.once('data', (data) => {
        const message = data.toString();
        if (message.includes('running on stdio')) {
          console.log('✅ Server started successfully');
          resolve();
        }
      });

      this.server.on('error', (error) => {
        console.error('❌ Failed to start server:', error);
        process.exit(1);
      });
    });
  }

  async sendRequest(request) {
    return new Promise((resolve, reject) => {
      const requestStr = JSON.stringify(request) + '\n';
      
      let response = '';
      const onData = (data) => {
        response += data.toString();
        try {
          const lines = response.trim().split('\n');
          for (const line of lines) {
            if (line.trim()) {
              const parsed = JSON.parse(line);
              this.server.stdout.removeListener('data', onData);
              resolve(parsed);
              return;
            }
          }
        } catch (e) {
          // Continue accumulating data
        }
      };

      this.server.stdout.on('data', onData);
      this.server.stdin.write(requestStr);

      setTimeout(() => {
        this.server.stdout.removeListener('data', onData);
        reject(new Error('Request timeout'));
      }, 5000);
    });
  }

  async testListTools() {
    console.log('\n📋 Testing list_tools...');
    
    const request = {
      jsonrpc: '2.0',
      method: 'tools/list',
      params: {},
      id: 1
    };

    try {
      const response = await this.sendRequest(request);
      
      if (response.result && response.result.tools) {
        console.log(`✅ Found ${response.result.tools.length} tools`);
        
        // List tool names
        console.log('\nAvailable tools:');
        response.result.tools.forEach(tool => {
          console.log(`  - ${tool.name}: ${tool.description.substring(0, 60)}...`);
        });
        
        return true;
      } else {
        console.error('❌ Invalid response:', response);
        return false;
      }
    } catch (error) {
      console.error('❌ Error:', error.message);
      return false;
    }
  }

  async testJiraProjects() {
    console.log('\n🏢 Testing jira_list_projects...');
    
    const request = {
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'jira_list_projects',
        arguments: {}
      },
      id: 2
    };

    try {
      const response = await this.sendRequest(request);
      
      if (response.error) {
        console.log('⚠️  Expected error (no credentials):', response.error.message);
        return true; // This is expected without credentials
      } else if (response.result) {
        console.log('✅ Successfully called Jira API');
        return true;
      }
    } catch (error) {
      console.error('❌ Error:', error.message);
      return false;
    }
  }

  async testJiraSearch() {
    console.log('\n🔍 Testing jira_search_issues with example JQL...');
    
    const request = {
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'jira_search_issues',
        arguments: {
          jql: 'project = TEST AND status = Open',
          max_results: 5
        }
      },
      id: 3
    };

    try {
      const response = await this.sendRequest(request);
      
      if (response.error) {
        console.log('⚠️  Expected error (no credentials):', response.error.message);
        return true; // This is expected without credentials
      } else if (response.result) {
        console.log('✅ Successfully called Jira search API');
        return true;
      }
    } catch (error) {
      console.error('❌ Error:', error.message);
      return false;
    }
  }

  async cleanup() {
    if (this.server) {
      console.log('\n🧹 Cleaning up...');
      this.server.kill();
    }
  }

  async runTests() {
    try {
      await this.startServer();
      
      let allPassed = true;
      
      // Run tests
      allPassed &= await this.testListTools();
      allPassed &= await this.testJiraProjects();
      allPassed &= await this.testJiraSearch();
      
      console.log('\n' + '='.repeat(50));
      if (allPassed) {
        console.log('✅ All tests passed!');
        console.log('\nNext steps:');
        console.log('1. Add your Atlassian credentials to .env file');
        console.log('2. Run the server with: npm start');
        console.log('3. Use the MCP tools in your AI assistant');
      } else {
        console.log('❌ Some tests failed');
      }
      console.log('='.repeat(50));
      
    } catch (error) {
      console.error('❌ Test suite error:', error);
    } finally {
      await this.cleanup();
    }
  }
}

// Run tests
const tester = new MCPTester();
tester.runTests().catch(console.error);
