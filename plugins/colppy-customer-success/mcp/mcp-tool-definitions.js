/**
 * MCP tool definitions (JSON Schema) for the Intercom MCP server.
 * Each entry is registered in the ListToolsRequestSchema handler.
 */

export const TOOL_DEFINITIONS = [
  {
    name: 'export_intercom_conversations',
    description: 'Export Intercom conversations from a date range to CSV/JSON. Use team_assignee_id to filter by team inbox (e.g. 2334166 = Primeros 90 días) — inboxes align with user lifecycle/cycle time for faster, focused exports.',
    inputSchema: {
      type: 'object',
      properties: {
        from_date: { type: 'string', description: 'Start date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        to_date: { type: 'string', description: 'End date YYYY-MM-DD (defaults to today)', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        team_assignee_id: { type: 'string', description: 'Team inbox ID (e.g. 2334166 for Primeros 90 días). From URL: inbox/team/TEAM_ID' },
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
    description: 'Count conversations matching optional filters (date range, state, team inbox). Use team_assignee_id to filter by inbox (e.g. 2334166 = Primeros 90 días) for cycle-time analysis.',
    inputSchema: {
      type: 'object',
      properties: {
        from_date: { type: 'string', description: 'Start date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        to_date: { type: 'string', description: 'End date YYYY-MM-DD (defaults to today)', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        state: { type: 'string', description: 'Conversation state', enum: ['open', 'closed', 'snoozed'] },
        team_assignee_id: { type: 'string', description: 'Team inbox ID (e.g. 2334166 for Primeros 90 días)' },
      },
      additionalProperties: false,
    },
  },
  {
    name: 'get_intercom_conversation_stats',
    description: 'Get statistics about conversations in a date range without full export. Use team_assignee_id to filter by team inbox (e.g. 2334166 = Primeros 90 días) for cycle-time focus.',
    inputSchema: {
      type: 'object',
      properties: {
        from_date: { type: 'string', description: 'Start date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        to_date: { type: 'string', description: 'End date YYYY-MM-DD (defaults to today)', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        team_assignee_id: { type: 'string', description: 'Team inbox ID (e.g. 2334166 for Primeros 90 días)' },
      },
      required: ['from_date'],
      additionalProperties: false,
    },
  },
  {
    name: 'search_intercom_conversations',
    description: 'Search conversations by criteria. Use team_assignee_id to filter by team inbox (e.g. 2334166 = Primeros 90 días) for cycle-time focus.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query or keywords' },
        from_date: { type: 'string', description: 'Start date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        to_date: { type: 'string', description: 'End date YYYY-MM-DD', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
        state: { type: 'string', description: 'Conversation state', enum: ['open', 'closed', 'snoozed'] },
        team_assignee_id: { type: 'string', description: 'Team inbox ID (e.g. 2334166 for Primeros 90 días)' },
        limit: { type: 'number', description: 'Max results (default 50)', minimum: 1, maximum: 150, default: 50 },
      },
      additionalProperties: false,
    },
  },

  // ── Customer Research tools ──────────────────────────────────────────

  {
    name: 'scan_customer_feedback',
    description:
      'Quick scan: search Intercom conversations for a topic, feature, or keyword. ' +
      'Filters by date range, Intercom tags, keywords, and optionally team inbox (team_assignee_id). ' +
      'Use team_assignee_id for cycle-time focus (e.g. 2334166 = Primeros 90 días). ' +
      'Returns conversation previews with match reasons. Use get_conversation_feedback afterwards to read full content.',
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
        team_assignee_id: {
          type: 'string',
          description: 'Team inbox ID (e.g. 2334166 for Primeros 90 días)',
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
      'Use team_assignee_id to filter by team inbox (e.g. 2334166 = Primeros 90 días) for cycle-time focus. ' +
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
        team_assignee_id: {
          type: 'string',
          description: 'Team inbox ID (e.g. 2334166 for Primeros 90 días)',
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
          description: 'Path to save raw conversation data for local iteration. Use with local_scan.js to re-run keyword matching without API calls. E.g. skills/intercom-developer-api-research/cache/conversations_2025-01-21.json',
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

  // ── Onboarding analysis (segmented by user type) ────────────────────────

  {
    name: 'analyze_onboarding_first_invoice',
    description:
      'Analyze onboarding conversations (Primeros 90 días) segmented by user type: accountant vs SMB vs all. ' +
      'Default: keyword matching for first-invoice topics. Set use_llm=true for LLM classification. ' +
      'Use topic to switch classifier: topic_first_invoice.json (default, invoice-specific) or ' +
      'topic.json (broader onboarding: account_registration, company_setup, iva_afip_config, etc.). ' +
      'Requires cache from export_cache_for_local_scan.mjs --team 2334166.',
    inputSchema: {
      type: 'object',
      properties: {
        cache_path: {
          type: 'string',
          description:
            'Path to Intercom cache JSON (with contact_email). E.g. plugins/colppy-customer-success/skills/intercom-developer-api-research/cache/conversations_2026-02-01_2026-02-28_team2334166.json',
        },
        user_type: {
          type: 'string',
          description: 'Filter by user type',
          enum: ['accountant', 'smb', 'all'],
          default: 'accountant',
        },
        use_llm: {
          type: 'boolean',
          description: 'Run LLM classifier on filtered conversations (requires OPENAI_API_KEY)',
          default: false,
        },
        topic: {
          type: 'string',
          description:
            'Topic config JSON for LLM classifier. Default: topic_first_invoice.json (invoice-specific). ' +
            'Use plugins/colppy-customer-success/skills/intercom-onboarding-setup/topic.json for broader onboarding analysis.',
        },
      },
      required: ['cache_path'],
      additionalProperties: false,
    },
  },
];
