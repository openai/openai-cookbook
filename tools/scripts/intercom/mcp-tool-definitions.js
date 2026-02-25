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
    name: 'get_conversation_feedback',
    description:
      'Deep dive: fetch full conversation content for specific conversation IDs and extract customer feedback. ' +
      'Returns the full conversation timeline (user + admin + bot messages), participant breakdown, tags, ' +
      'and feedback snippets matching the topic. Use after scan_customer_feedback to read the actual conversations.',
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
