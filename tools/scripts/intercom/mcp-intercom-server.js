#!/usr/bin/env node

/**
 * Intercom MCP Server
 *
 * Provides Model Context Protocol (MCP) tools for Intercom data export,
 * analysis, and customer feedback research.
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

import {
  retryableRequest,
  fetchConversationIds,
  getConversationDetails,
  processConversation,
  convertToCSV,
  groupBy,
  stripHtml,
  extractTags,
  buildConversationText,
  buildSearchQuery,
} from './intercom-api-helpers.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
dotenv.config({ path: join(__dirname, '../../../.env') });

import { TOOL_DEFINITIONS } from './mcp-tool-definitions.js';

class IntercomMCPServer {
  constructor() {
    this.server = new Server(
      { name: 'intercom-export-server', version: '2.0.0' },
      { capabilities: { tools: {} } },
    );
    this.setupErrorHandling();
    this.setupToolHandlers();

    this.intercomApi = axios.create({
      baseURL: 'https://api.intercom.io',
      headers: {
        'Authorization': `Bearer ${process.env.INTERCOM_ACCESS_TOKEN}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Intercom-Version': '2.13',
      },
      timeout: 30000,
    });
  }

  setupErrorHandling() {
    this.server.onerror = (error) => console.error('[MCP Error]', error);
    process.on('SIGINT', async () => { await this.server.close(); process.exit(0); });
  }

  setupToolHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: TOOL_DEFINITIONS,
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;
      try {
        switch (name) {
          case 'export_intercom_conversations': return await this.exportConversations(args);
          case 'count_intercom_conversations': return await this.countConversations(args);
          case 'get_intercom_conversation_stats': return await this.getConversationStats(args);
          case 'search_intercom_conversations': return await this.searchConversations(args);
          case 'scan_customer_feedback': return await this.scanCustomerFeedback(args);
          case 'scan_full_text': return await this.scanFullText(args);
          case 'get_conversation_feedback': return await this.getConversationFeedback(args);
          default:
            throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
        }
      } catch (error) {
        if (error instanceof McpError) throw error;
        throw new McpError(ErrorCode.InternalError, `Tool execution failed: ${error.message}`);
      }
    });
  }

  // ── Existing tools ────────────────────────────────────────────────────

  async countConversations(args) {
    const { from_date, to_date = new Date().toISOString().split('T')[0], state } = args;
    try {
      const searchQuery = buildSearchQuery({ from_date, to_date, state });
      let total = 0;
      let startingAfter = null;
      let hasMore = true;
      while (hasMore) {
        if (startingAfter) searchQuery.pagination.starting_after = startingAfter;
        else delete searchQuery.pagination.starting_after;
        const response = await retryableRequest(() => this.intercomApi.post('/conversations/search', searchQuery));
        total += (response.data.conversations || []).length;
        const next = response.data.pages?.next?.starting_after;
        hasMore = !!next;
        startingAfter = next;
      }
      return this._json({ success: true, date_range: { from: from_date || null, to: to_date }, state: state || null, total_count: total });
    } catch (error) {
      throw new McpError(ErrorCode.InternalError, `Count failed: ${error.message}`);
    }
  }

  async exportConversations(args) {
    const { from_date, to_date = new Date().toISOString().split('T')[0], output_format = 'csv', limit, include_message_content = true } = args;
    try {
      if (!process.env.INTERCOM_ACCESS_TOKEN) throw new Error('INTERCOM_ACCESS_TOKEN not found');
      const conversationIds = await fetchConversationIds(this.intercomApi, from_date, to_date, limit);
      if (conversationIds.length === 0) {
        return this._json({ success: true, message: 'No conversations found', date_range: { from: from_date, to: to_date }, total_conversations: 0, data: [] });
      }
      const maxConcurrent = 10;
      const allRows = [];
      const summary = [];
      for (let i = 0; i < conversationIds.length; i += maxConcurrent) {
        const batch = conversationIds.slice(i, i + maxConcurrent);
        const results = await Promise.all(batch.map(async (id) => {
          try {
            const conv = await getConversationDetails(this.intercomApi, id);
            const rows = processConversation(conv, include_message_content);
            return { id, rows, conv };
          } catch { return { id, rows: [] }; }
        }));
        for (const r of results) {
          if (r.rows.length > 0) allRows.push(...r.rows);
          if (r.conv) summary.push({ id: r.id, created_at: r.conv.created_at, state: r.conv.state, message_count: r.rows.length });
        }
      }
      return this._json({
        success: true, date_range: { from: from_date, to: to_date },
        total_conversations: conversationIds.length, total_messages: allRows.length,
        output_format, include_message_content, conversations_summary: summary,
        data: output_format === 'csv' ? convertToCSV(allRows) : allRows,
      });
    } catch (error) {
      throw new McpError(ErrorCode.InternalError, `Export failed: ${error.message}`);
    }
  }

  async getConversationStats(args) {
    const { from_date, to_date = new Date().toISOString().split('T')[0] } = args;
    try {
      const ids = await fetchConversationIds(this.intercomApi, from_date, to_date, 100);
      const sampleIds = ids.slice(0, Math.min(20, ids.length));
      const sampleStats = (await Promise.all(sampleIds.map(async (id) => {
        try {
          const conv = await getConversationDetails(this.intercomApi, id);
          return { id, state: conv.state, created_at: conv.created_at, parts_count: conv.conversation_parts?.conversation_parts?.length || 0, has_admin_assignee: !!conv.admin_assignee_id };
        } catch { return null; }
      }))).filter(Boolean);
      return this._json({
        success: true, date_range: { from: from_date, to: to_date },
        total_conversations_found: ids.length, sample_size: sampleStats.length,
        statistics: {
          states: groupBy(sampleStats, 'state'),
          avg_parts_per_conversation: sampleStats.reduce((s, x) => s + x.parts_count, 0) / (sampleStats.length || 1),
          assigned_conversations: sampleStats.filter(s => s.has_admin_assignee).length,
          assignment_rate: sampleStats.filter(s => s.has_admin_assignee).length / (sampleStats.length || 1),
        },
      });
    } catch (error) {
      throw new McpError(ErrorCode.InternalError, `Stats failed: ${error.message}`);
    }
  }

  async searchConversations(args) {
    const { query, from_date, to_date = new Date().toISOString().split('T')[0], state, limit = 50 } = args;
    try {
      const searchQuery = buildSearchQuery({ from_date, to_date, state, per_page: Math.min(limit, 150) });
      const response = await retryableRequest(() => this.intercomApi.post('/conversations/search', searchQuery));
      let convs = response.data.conversations || [];
      if (query) {
        const q = query.toLowerCase();
        convs = convs.filter(c => (c.source?.body?.toLowerCase() || '').includes(q));
      }
      return this._json({
        success: true, search_criteria: { query, from_date, to_date, state, limit },
        total_found: convs.length,
        conversations: convs.map(c => ({
          id: c.id, created_at: c.created_at ? new Date(c.created_at * 1000).toISOString() : '',
          state: c.state, source_body_preview: c.source?.body?.substring(0, 200) || '',
          admin_assignee_id: c.admin_assignee_id, contact_count: c.contacts?.contacts?.length || 0,
        })),
      });
    } catch (error) {
      throw new McpError(ErrorCode.InternalError, `Search failed: ${error.message}`);
    }
  }

  // ── New: Customer Research tools ──────────────────────────────────────

  async scanCustomerFeedback(args) {
    const {
      topic,
      keywords: userKeywords,
      tags: tagFilter,
      from_date,
      to_date = new Date().toISOString().split('T')[0],
      state,
      limit = 30,
    } = args;

    try {
      const keywords = (userKeywords && userKeywords.length > 0)
        ? userKeywords.map(k => k.toLowerCase())
        : topic.toLowerCase().split(/\s+/).filter(w => w.length > 2);

      const tagFilterLower = (tagFilter || []).map(t => t.toLowerCase());

      const searchQuery = buildSearchQuery({ from_date, to_date, state });
      const matches = [];
      let startingAfter = null;
      let scannedCount = 0;
      const MAX_SCAN = 500;

      while (scannedCount < MAX_SCAN && matches.length < limit) {
        if (startingAfter) searchQuery.pagination.starting_after = startingAfter;
        else delete searchQuery.pagination.starting_after;

        const response = await retryableRequest(() => this.intercomApi.post('/conversations/search', searchQuery));
        const convs = response.data.conversations || [];
        if (convs.length === 0) break;
        scannedCount += convs.length;

        for (const conv of convs) {
          if (matches.length >= limit) break;
          const convTags = extractTags(conv);
          const body = stripHtml(conv.source?.body || '').toLowerCase();
          const matchReasons = [];

          if (tagFilterLower.length > 0) {
            const matched = convTags.filter(t => tagFilterLower.some(f => t.toLowerCase().includes(f)));
            if (matched.length > 0) matchReasons.push(`tag: ${matched.join(', ')}`);
          }

          const matchedKw = keywords.filter(kw => body.includes(kw));
          if (matchedKw.length > 0) matchReasons.push(`keyword: ${matchedKw.join(', ')}`);

          if (matchReasons.length === 0) continue;

          matches.push({
            conversation_id: conv.id,
            created_at: conv.created_at ? new Date(conv.created_at * 1000).toISOString() : '',
            state: conv.state,
            tags: convTags,
            source_preview: stripHtml(conv.source?.body || '').substring(0, 300),
            match_reason: matchReasons.join(' + '),
            admin_assignee_id: conv.admin_assignee_id || null,
            contact_count: conv.contacts?.contacts?.length || 0,
          });
        }

        const next = response.data.pages?.next?.starting_after;
        if (!next) break;
        startingAfter = next;
      }

      return this._json({
        success: true,
        research_topic: topic,
        search_criteria: { keywords, tags: tagFilter || [], from_date, to_date, state: state || null },
        conversations_scanned: scannedCount,
        matches_found: matches.length,
        matches,
      });
    } catch (error) {
      throw new McpError(ErrorCode.InternalError, `Scan failed: ${error.message}`);
    }
  }

  /**
   * Full-text scan: search ALL messages (source + conversation_parts) for keywords.
   * Fetches full conversation for each, so more API calls than scan_customer_feedback.
   * When >500 conversations in range: returns confirmation_required; user must re-call with confirm_large_scan: true.
   */
  async scanFullText(args) {
    const {
      topic,
      keywords: userKeywords,
      from_date,
      to_date = new Date().toISOString().split('T')[0],
      state,
      limit = 30,
      max_scan = 200,
      confirm_large_scan = false,
      large_scan_threshold = 500,
      exclude_if_only = [],
      save_cache,
    } = args;

    const LARGE_SCAN_THRESHOLD = Math.max(50, Math.min(2000, large_scan_threshold));

    try {
      const keywords = (userKeywords && userKeywords.length > 0)
        ? userKeywords.map(k => k.toLowerCase())
        : topic.toLowerCase().split(/\s+/).filter(w => w.length > 2);

      // Check how many conversations in range (fetch up to threshold+1 to detect overflow)
      const probeIds = await fetchConversationIds(this.intercomApi, from_date, to_date, LARGE_SCAN_THRESHOLD + 1, state);
      const totalInRange = probeIds.length;

      if (totalInRange > LARGE_SCAN_THRESHOLD && !confirm_large_scan) {
        return this._json({
          success: false,
          confirmation_required: true,
          total_conversations_at_least: totalInRange,
          message: `This date range has more than ${LARGE_SCAN_THRESHOLD} conversations (at least ${totalInRange}). Full scan would make ~${totalInRange}+ API calls. Set confirm_large_scan: true to proceed with the full scan.`,
          search_criteria: { topic, from_date, to_date, state: state || null },
        });
      }

      // Proceed: fetch all IDs when confirmed (or when under threshold)
      const scanLimit = confirm_large_scan ? null : Math.min(max_scan, totalInRange);
      const conversationIds = confirm_large_scan
        ? await fetchConversationIds(this.intercomApi, from_date, to_date, null, state)
        : probeIds.slice(0, scanLimit);
      const matches = [];
      const cacheConversations = save_cache ? [] : null;
      const maxConcurrent = 5;

      for (let i = 0; i < conversationIds.length; i += maxConcurrent) {
        const batch = conversationIds.slice(i, i + maxConcurrent);
        const batchResults = await Promise.all(batch.map(async (id) => {
          try {
            const conv = await getConversationDetails(this.intercomApi, id);
            const tags = extractTags(conv);
            const { parts } = buildConversationText(conv);

            if (cacheConversations) {
              cacheConversations.push({
                conversation_id: id,
                created_at: conv.created_at ? new Date(conv.created_at * 1000).toISOString() : '',
                state: conv.state,
                tags,
                parts: parts.map((p) => ({
                  author_type: p.author_type,
                  body: p.body,
                  created_at: p.created_at ? new Date(p.created_at * 1000).toISOString() : null,
                })),
              });
            }

            const matchedParts = [];
            for (const p of parts) {
              const bodyLower = p.body.toLowerCase();
              const matchedKw = keywords.filter(kw => bodyLower.includes(kw));
              if (matchedKw.length > 0) {
                matchedParts.push({
                  author_type: p.author_type,
                  matched_keywords: matchedKw,
                  excerpt: p.body.substring(0, 200) + (p.body.length > 200 ? '…' : ''),
                  created_at: p.created_at ? new Date(p.created_at * 1000).toISOString() : null,
                });
              }
            }

            if (matchedParts.length === 0) return null;

            return {
              conversation_id: id,
              created_at: conv.created_at ? new Date(conv.created_at * 1000).toISOString() : '',
              state: conv.state,
              tags,
              match_reason: `Found in ${matchedParts.length} message(s)`,
              matched_in: matchedParts,
              admin_assignee_id: conv.admin_assignee_id || null,
              contact_count: conv.contacts?.contacts?.length || 0,
            };
          } catch (error) {
            return null;
          }
        }));

        for (const r of batchResults) {
          if (r) matches.push(r);
        }
      }

      let cachePathResolved = null;
      if (save_cache && cacheConversations && cacheConversations.length > 0) {
        const pluginRoot = join(process.cwd(), 'plugins', 'colppy-customer-success');
        cachePathResolved = save_cache.startsWith('/') ? save_cache : join(pluginRoot, save_cache);
        const cacheDir = join(cachePathResolved, '..');
        if (!fs.existsSync(cacheDir)) fs.mkdirSync(cacheDir, { recursive: true });
        fs.writeFileSync(cachePathResolved, JSON.stringify({
          from_date,
          to_date,
          state: state || null,
          topic,
          saved_at: new Date().toISOString(),
          conversations: cacheConversations,
        }, null, 2), 'utf8');
      }

      // Filter: exclude matches where the ONLY matched keywords are in exclude_if_only
      const excludeSet = new Set((exclude_if_only || []).map(k => k.toLowerCase()));
      let filteredMatches = matches;
      if (excludeSet.size > 0) {
        filteredMatches = matches.filter((m) => {
          const allMatched = new Set(
            (m.matched_in || []).flatMap((p) => (p.matched_keywords || []).map(k => k.toLowerCase()))
          );
          if (allMatched.size === 0) return true;
          const onlyExcluded = [...allMatched].every((kw) => excludeSet.has(kw));
          return !onlyExcluded;
        });
      }

      const result = {
        success: true,
        research_topic: topic,
        search_criteria: {
          keywords,
          from_date,
          to_date,
          state: state || null,
          confirm_large_scan: confirm_large_scan || undefined,
          exclude_if_only: exclude_if_only?.length ? exclude_if_only : undefined,
        },
        conversations_scanned: conversationIds.length,
        matches_found: filteredMatches.length,
        matches_excluded_by_filter: excludeSet.size > 0 ? matches.length - filteredMatches.length : undefined,
        matches: filteredMatches,
      };
      if (cachePathResolved) {
        result.cache_saved = cachePathResolved;
        result.cache_conversations = cacheConversations.length;
      }
      return this._json(result);
    } catch (error) {
      throw new McpError(ErrorCode.InternalError, `Full-text scan failed: ${error.message}`);
    }
  }

  async getConversationFeedback(args) {
    const {
      conversation_ids,
      topic,
      excerpt_length = 1500,
    } = args;

    try {
      const ids = conversation_ids.slice(0, 10);
      const topicKeywords = topic
        ? topic.toLowerCase().split(/\s+/).filter(w => w.length > 2)
        : [];

      const maxConcurrent = 5;
      const results = [];

      for (let i = 0; i < ids.length; i += maxConcurrent) {
        const batch = ids.slice(i, i + maxConcurrent);
        const batchResults = await Promise.all(batch.map(async (id) => {
          try {
            const conv = await getConversationDetails(this.intercomApi, id);
            const tags = extractTags(conv);
            const { fullText, parts } = buildConversationText(conv);

            let nUser = 0, nAdmin = 0, nBot = 0;
            for (const p of parts) {
              if (p.author_type === 'user' || p.author_type === 'lead') nUser++;
              else if (p.author_type === 'admin') nAdmin++;
              else if (p.author_type === 'bot') nBot++;
            }

            const timeline = parts.map(p => `[${p.author_type}] ${p.body}`).join('\n');
            const excerpt = timeline.length > excerpt_length
              ? timeline.substring(0, excerpt_length) + '…'
              : timeline;

            let feedbackSnippets = [];
            if (topicKeywords.length > 0) {
              for (const p of parts) {
                const bodyLower = p.body.toLowerCase();
                if (topicKeywords.some(kw => bodyLower.includes(kw))) {
                  feedbackSnippets.push({
                    author_type: p.author_type,
                    text: p.body.substring(0, 500),
                    created_at: p.created_at ? new Date(p.created_at * 1000).toISOString() : null,
                  });
                }
              }
            }

            return {
              conversation_id: id,
              created_at: conv.created_at ? new Date(conv.created_at * 1000).toISOString() : '',
              state: conv.state,
              tags,
              participants: { user_messages: nUser, admin_messages: nAdmin, bot_messages: nBot, total: parts.length },
              conversation_text: excerpt,
              feedback_snippets: feedbackSnippets,
              intercom_url: `https://app.intercom.com/a/apps/${process.env.INTERCOM_APP_ID || '_'}/inbox/inbox/conversation/${id}`,
            };
          } catch (error) {
            return { conversation_id: id, error: error.message };
          }
        }));
        results.push(...batchResults);
      }

      return this._json({
        success: true,
        topic: topic || null,
        conversations_requested: ids.length,
        conversations_retrieved: results.filter(r => !r.error).length,
        results,
      });
    } catch (error) {
      throw new McpError(ErrorCode.InternalError, `Feedback retrieval failed: ${error.message}`);
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────

  _json(data) {
    return { content: [{ type: 'text', text: JSON.stringify(data, null, 2) }] };
  }

  async connectTransport(transport) {
    await this.server.connect(transport);
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.connectTransport(transport);
    console.error('Intercom MCP server running on stdio');
  }
}

export { IntercomMCPServer };

const isDirectRun = process.argv[1] &&
  fileURLToPath(import.meta.url).endsWith(process.argv[1].replace(/^.*[\\/]/, ''));

if (isDirectRun) {
  const server = new IntercomMCPServer();
  server.run().catch(console.error);
}
