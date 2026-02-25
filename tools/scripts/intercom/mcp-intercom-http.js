#!/usr/bin/env node

/**
 * Intercom MCP Server — Remote HTTP Transport
 *
 * Exposes the same MCP tools as mcp-intercom-server.js but over HTTP
 * using Streamable HTTP transport. Deploy to Cloud Run, Koyeb, or any
 * Node.js host so team members can connect without local setup.
 *
 * Usage:
 *   node mcp-intercom-http.js                     # port 3000
 *   PORT=8080 node mcp-intercom-http.js           # custom port
 *
 * Env vars:
 *   INTERCOM_ACCESS_TOKEN  — Required. Intercom API token.
 *   PORT                   — HTTP port (default 3000).
 *   MCP_API_KEY            — Optional. If set, every request must
 *                            include header "x-api-key: <value>".
 */

import express from 'express';
import crypto from 'crypto';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { IntercomMCPServer } from './mcp-intercom-server.js';

const PORT = parseInt(process.env.PORT || '3000', 10);
const API_KEY = process.env.MCP_API_KEY || null;

const app = express();
app.use(express.json());

app.use((_req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  next();
});

if (API_KEY) {
  app.use('/mcp', (req, res, next) => {
    const provided = req.headers['x-api-key'];
    if (provided !== API_KEY) {
      return res.status(401).json({ error: 'Invalid or missing x-api-key header' });
    }
    next();
  });
}

const activeSessions = new Map();

function getOrCreateSession(sessionId) {
  if (sessionId && activeSessions.has(sessionId)) {
    return activeSessions.get(sessionId);
  }

  const newSessionId = sessionId || crypto.randomUUID();
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: () => newSessionId,
  });
  const mcpServer = new IntercomMCPServer();
  mcpServer.connectTransport(transport);

  activeSessions.set(newSessionId, { transport, mcpServer });

  transport.onclose = () => {
    activeSessions.delete(newSessionId);
  };

  return { transport, mcpServer };
}

app.post('/mcp', async (req, res) => {
  try {
    const sessionId = req.headers['mcp-session-id'];
    const { transport } = getOrCreateSession(sessionId);
    await transport.handleRequest(req, res, req.body);
  } catch (error) {
    console.error('[HTTP POST /mcp] Error:', error.message);
    if (!res.headersSent) {
      res.status(500).json({ error: 'Internal server error' });
    }
  }
});

app.get('/mcp', async (req, res) => {
  const sessionId = req.headers['mcp-session-id'];
  if (!sessionId || !activeSessions.has(sessionId)) {
    return res.status(400).json({ error: 'Missing or invalid mcp-session-id header. Send a POST /mcp first to start a session.' });
  }
  const { transport } = activeSessions.get(sessionId);
  await transport.handleRequest(req, res);
});

app.delete('/mcp', async (req, res) => {
  const sessionId = req.headers['mcp-session-id'];
  if (sessionId && activeSessions.has(sessionId)) {
    const { transport } = activeSessions.get(sessionId);
    await transport.close();
    activeSessions.delete(sessionId);
  }
  res.status(200).json({ success: true });
});

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    server: 'intercom-mcp',
    version: '2.0.0',
    active_sessions: activeSessions.size,
    has_token: !!process.env.INTERCOM_ACCESS_TOKEN,
  });
});

app.listen(PORT, () => {
  console.log(`Intercom MCP HTTP server listening on port ${PORT}`);
  console.log(`  MCP endpoint:  http://localhost:${PORT}/mcp`);
  console.log(`  Health check:  http://localhost:${PORT}/health`);
  console.log(`  API key auth:  ${API_KEY ? 'ENABLED' : 'disabled (set MCP_API_KEY to enable)'}`);
});
