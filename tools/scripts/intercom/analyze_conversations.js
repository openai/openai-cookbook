#!/usr/bin/env node

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Run MCP server to get all open conversations
const mcpProcess = spawn('node', ['mcp-intercom-server.js'], {
  cwd: __dirname,
  stdio: ['pipe', 'pipe', 'inherit']
});

const request = {
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_intercom_conversations",
    "arguments": {
      "state": "open",
      "limit": 150
    }
  }
};

mcpProcess.stdin.write(JSON.stringify(request) + '\n');
mcpProcess.stdin.end();

let output = '';
mcpProcess.stdout.on('data', (data) => {
  output += data.toString();
});

mcpProcess.on('close', (code) => {
  try {
    // Parse the JSON response
    const lines = output.split('\n').filter(line => line.trim());
    const jsonLine = lines.find(line => line.startsWith('{"result"'));
    
    if (!jsonLine) {
      console.error('No valid JSON response found');
      return;
    }

    const response = JSON.parse(jsonLine);
    const data = JSON.parse(response.result.content[0].text);
    
    // Count conversations
    const conversations = data.conversations || [];
    const openConversations = conversations.filter(c => c.state === 'open');
    
    const assigned = openConversations.filter(c => c.admin_assignee_id !== null && c.admin_assignee_id !== undefined);
    const unassigned = openConversations.filter(c => c.admin_assignee_id === null || c.admin_assignee_id === undefined);
    
    console.log('=== OPEN CONVERSATIONS COUNT ===');
    console.log(`Total Open: ${openConversations.length}`);
    console.log(`Assigned: ${assigned.length}`);
    console.log(`Unassigned: ${unassigned.length}`);
    console.log();
    
    if (data.total_found > 150) {
      console.log(`Note: There are ${data.total_found} total conversations, but only showing first 150`);
    }
    
  } catch (error) {
    console.error('Error parsing response:', error);
    console.log('Raw output:', output);
  }
});