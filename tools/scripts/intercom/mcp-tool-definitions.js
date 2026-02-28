/**
 * MCP tool definitions (JSON Schema) for the Intercom MCP server.
 * Each entry is registered in the ListToolsRequestSchema handler.
 */

export const TOOL_DEFINITIONS = [
  {
    name: 'export_intercom_conversations',
    description: 'Export Intercom conversations from a specific date range to CSV format',
    inputSchema: {
      type: 'object',
      properties: {
        from_date: { type: 'string', description: 'Start date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        to_date: { type: 'string', description: 'End date YYYY-MM-DD (defaults to today)', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        output_format: { type: 'string', description: 'Output format', enum: ['csv', 'json'], default: 'csv' },
        limit: { type: 'number', description: 'Max conversations to export', minimum: 1 },
        include_message_content: { type: 'boolean', description: 'Include full message content', default: true },
      },
      required: ['from_date'],
      additionalProperties: false,
    },
  },
  {
    name: 'count_intercom_conversations',
    description: 'Count conversations matching optional filters (date range, state) with full pagination',
    inputSchema: {
      type: 'object',
      properties: {
        from_date: { type: 'string', description: 'Start date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        to_date: { type: 'string', description: 'End date YYYY-MM-DD (defaults to today)', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        state: { type: 'string', description: 'Conversation state', enum: ['open', 'closed', 'snoozed'] },
      },
      additionalProperties: false,
    },
  },
  {
    name: 'get_intercom_conversation_stats',
    description: 'Get statistics about conversations in a date range without full export',
    inputSchema: {
      type: 'object',
      properties: {
        from_date: { type: 'string', description: 'Start date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        to_date: { type: 'string', description: 'End date YYYY-MM-DD (defaults to today)', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
      },
      required: ['from_date'],
      additionalProperties: false,
    },
  },
  {
    name: 'search_intercom_conversations',
    description: 'Search for specific conversations based on criteria',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query or keywords' },
        from_date: { type: 'string', description: 'Start date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        to_date: { type: 'string', description: 'End date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        state: { type: 'string', description: 'Conversation state', enum: ['open', 'closed', 'snoozed'] },
        limit: { type: 'number', description: 'Max results (default 50)', minimum: 1, maximum: 150, default: 50 },
      },
      additionalProperties: false,
    },
  },

  // ── Customer Research tools ──────────────────────────────────────────

  {
    name: 'scan_customer_feedback',
    description:
      'Quick scan: search Intercom conversations for a specific topic, feature, or keyword. ' +
      'Filters by date range, Intercom tags, and/or keywords in the first message body. ' +
      'Returns conversation previews with match reasons so you can pick which ones to deep-dive. ' +
      'Use get_conversation_feedback afterwards to read full conversation content.',
    inputSchema: {
      type: 'object',
      properties: {
        topic: {
          type: 'string',
          description: 'Feature or topic to research, e.g. "conciliación bancaria", "factura electrónica", "importación de items"',
        },
        keywords: {
          type: 'array',
          items: { type: 'string' },
          description: 'Additional keywords to match in conversation body. If omitted, the topic is split into keywords automatically.',
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
          description: 'Filter to conversations that have any of these Intercom tags (case-insensitive partial match)',
        },
        from_date: {
          type: 'string',
          description: 'Start date YYYY-MM-DD',
          pattern: '^\\d{4}-\\d{2}-\\d{2}$',
        },
        to_date: {
          type: 'string',
          description: 'End date YYYY-MM-DD (defaults to today)',
          pattern: '^\\d{4}-\\d{2}-\\d{2}$',
        },
        state: {
          type: 'string',
          description: 'Conversation state filter',
          enum: ['open', 'closed', 'snoozed'],
        },
        limit: {
          type: 'number',
          description: 'Max matching conversations to return (default 30)',
          minimum: 1,
          maximum: 100,
          default: 30,
        },
      },
      required: ['topic', 'from_date'],
      additionalProperties: false,
    },
  },
  {
    name: 'scan_full_text',
    description:
      'Full-text scan: search ALL messages in conversations (not just the first) for a topic or keyword. ' +
      'Fetches full conversation content and filters client-side. Use when the topic may appear in replies (e.g. Mercado Pago). ' +
      'Slower than scan_customer_feedback but finds matches in any message. Use get_conversation_feedback afterwards to read full content.',
    inputSchema: {
      type: 'object',
      properties: {
        topic: {
          type: 'string',
          description: 'Topic or keyword to search, e.g. "mercado pago", "mercadopago", "factura electronica"',
        },
        keywords: {
          type: 'array',
          items: { type: 'string' },
          description: 'Additional keywords. If omitted, topic is split into keywords. Include variations like "mercadopago" and "mercado pago".',
        },
        from_date: {
          type: 'string',
          description: 'Start date YYYY-MM-DD',
          pattern: '^\\d{4}-\\d{2}-\\d{2}$',
        },
        to_date: {
          type: 'string',
          description: 'End date YYYY-MM-DD (defaults to today)',
          pattern: '^\\d{4}-\\d{2}-\\d{2}$',
        },
        state: {
          type: 'string',
          description: 'Conversation state filter',
          enum: ['open', 'closed', 'snoozed'],
        },
        limit: {
          type: 'number',
          description: 'Deprecated. No longer used — all matches are returned. Kept for backwards compatibility.',
          minimum: 1,
          maximum: 100,
          default: 30,
        },
        max_scan: {
          type: 'number',
          description: 'Max conversations to fetch (default: all in range). Ignored when confirm_large_scan is used.',
          minimum: 10,
          maximum: 2000,
          default: 200,
        },
        confirm_large_scan: {
          type: 'boolean',
          description: 'Set to true to confirm scanning when the date range exceeds large_scan_threshold. The tool will first return a confirmation_required response; re-call with confirm_large_scan: true to proceed.',
          default: false,
        },
        large_scan_threshold: {
          type: 'number',
          description: 'When conversations in range exceed this count, the tool returns confirmation_required. User must re-call with confirm_large_scan: true. Default 500.',
          minimum: 50,
          maximum: 2000,
          default: 500,
        },
        exclude_if_only: {
          type: 'array',
          items: { type: 'string' },
          description: 'Exclude matches where the ONLY matched keywords are in this list (e.g. false positives: colppy.com in signatures, request in rating prompts, rest in resto).',
        },
        save_cache: {
          type: 'string',
          description: 'Path to save raw conversation data for local iteration. Relative to plugins/colppy-ceo-assistant. E.g. skills/intercom-developer-api-research/cache/conversations_2025-01-21.json',
        },
      },
      required: ['topic', 'from_date'],
      additionalProperties: false,
    },
  },
  {
    name: 'get_conversation_feedback',
    description:
      'Deep dive: fetch full conversation content for specific conversation IDs and extract customer feedback. ' +
      'Returns the full conversation timeline (user + admin + bot messages), participant breakdown, tags, ' +
      'and feedback snippets matching the topic. Use after scan_customer_feedback or scan_full_text to read the actual conversations.',
    inputSchema: {
      type: 'object',
      properties: {
        conversation_ids: {
          type: 'array',
          items: { type: 'string' },
          description: 'Conversation IDs to fetch (max 10). Get these from scan_customer_feedback results.',
          minItems: 1,
          maxItems: 10,
        },
        topic: {
          type: 'string',
          description: 'Topic or feature name to highlight matching feedback snippets within the conversation',
        },
        excerpt_length: {
          type: 'number',
          description: 'Max characters per conversation excerpt (default 1500)',
          minimum: 200,
          maximum: 5000,
          default: 1500,
        },
      },
      required: ['conversation_ids'],
      additionalProperties: false,
    },
  },
];
