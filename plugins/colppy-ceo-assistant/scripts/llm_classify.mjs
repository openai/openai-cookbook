#!/usr/bin/env node

/**
 * LLM-based classifier for Intercom conversation scan results.
 *
 * Takes keyword-scan results + conversation cache and runs each match through
 * GPT-4o-mini to classify whether it's a true developer/API conversation.
 *
 * Architecture (follows Intercom Topics Explorer pattern):
 *   1. Keyword scan = cheap pre-filter (1455 convos → ~37 candidates)
 *   2. LLM classifier = semantic post-filter (~37 → true matches)
 *
 * Usage:
 *   node scripts/llm_classify.mjs \
 *     --cache skills/intercom-developer-api-research/cache/conversations_2025-01-21_2025-02-05.json \
 *     --results skills/intercom-developer-api-research/cache/local_scan_results_v3.json \
 *     [--output skills/intercom-developer-api-research/cache/llm_classified.json] \
 *     [--report skills/intercom-developer-api-research/cache/llm_report.md] \
 *     [--model gpt-4o-mini] \
 *     [--concurrency 5] \
 *     [--keywords skills/intercom-developer-api-research/keywords.json]
 *
 * Requires OPENAI_API_KEY in environment or in root .env file.
 */

import fs from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import OpenAI from 'openai';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PLUGIN_ROOT = join(__dirname, '..');
const REPO_ROOT = join(PLUGIN_ROOT, '..', '..');

// ── .env loader ──────────────────────────────────────────────────────────

function loadEnv() {
  // Check common .env locations
  const candidates = [
    join(REPO_ROOT, '.env'),
    join(PLUGIN_ROOT, '.env'),
  ];
  for (const envPath of candidates) {
    if (fs.existsSync(envPath)) {
      const content = fs.readFileSync(envPath, 'utf8');
      for (const line of content.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const eqIdx = trimmed.indexOf('=');
        if (eqIdx === -1) continue;
        const key = trimmed.slice(0, eqIdx).trim();
        const raw = trimmed.slice(eqIdx + 1).trim();
        // Strip surrounding quotes (single or double)
        const val = raw.replace(/^(['"])(.*)\1$/, '$2');
        // Don't override existing env vars
        if (!process.env[key]) {
          process.env[key] = val;
        }
      }
    }
  }
}

// ── Auth helper ──────────────────────────────────────────────────────────

function getOpenAIClient() {
  if (!process.env.OPENAI_API_KEY) {
    throw new Error(
      'OPENAI_API_KEY not found. Set it in environment or in .env file at repo root.'
    );
  }
  return new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
}

// ── CLI args ─────────────────────────────────────────────────────────────

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    cache: null,
    results: null,
    output: null,
    report: null,
    model: 'gpt-4o-mini',
    concurrency: 5,
    keywords: null,
  };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--cache' && args[i + 1]) opts.cache = args[++i];
    else if (args[i] === '--results' && args[i + 1]) opts.results = args[++i];
    else if (args[i] === '--output' && args[i + 1]) opts.output = args[++i];
    else if (args[i] === '--report' && args[i + 1]) opts.report = args[++i];
    else if (args[i] === '--model' && args[i + 1]) opts.model = args[++i];
    else if (args[i] === '--concurrency' && args[i + 1]) opts.concurrency = parseInt(args[++i], 10);
    else if (args[i] === '--keywords' && args[i + 1]) opts.keywords = args[++i];
  }
  if (isNaN(opts.concurrency) || opts.concurrency < 1) {
    console.error('--concurrency must be a positive integer');
    process.exit(1);
  }
  return opts;
}

function resolvePath(p) {
  if (!p) return null;
  if (p.startsWith('/')) return p;
  return join(PLUGIN_ROOT, p);
}

// ── Classification prompt ────────────────────────────────────────────────

function buildClassificationPrompt(definition) {
  return `You are classifying Intercom support conversations for a B2B SaaS company called Colppy (Argentine accounting software).

<definition>
${definition}
</definition>

<context>
Colppy has these features that generate FALSE POSITIVE matches:
- "Mercado Pago" integration: end-users configure this from the UI (not API work)
- "Conecta tu banco" (bank connection): uses a third-party integrator called Paybook. Users get "error 500" and need to re-enter "credenciales" (bank login). This is NOT developer/API work.
- "Staging" environment (app.stg.colppy.com): sometimes appears in internal Jira tickets or login issues
- "Tiendanube" / "Producteca": e-commerce integrations that Colppy supports natively. Users asking about these as features (not building API integrations) are NOT developer conversations.
- XML files: users upload SIRADIG XML files for payroll (eSueldos module). This is NOT API work.
- Bot messages often contain marketing text like "Automatizar facturación" — this is NOT a developer request.

TRUE POSITIVE signals:
- Someone is writing code against the Colppy API (mentions endpoints, JSON responses, request/response debugging)
- A "desarrollador" or "programador" is building a custom integration with Colppy
- References to dev.colppy.com, API credentials, provisions, operations
- Debugging API errors with technical detail (HTTP status codes in API context, malformed responses)
- Third-party software company asking about API capabilities for their product
</context>

Classify the conversation below. Respond in this exact JSON format:
{
  "is_developer_api": true/false,
  "confidence": 0.0-1.0,
  "category": "one of: api_integration | api_bug | api_inquiry | feature_config | bank_connection | sales_inquiry | internal | payroll | other",
  "reasoning": "1-2 sentence explanation"
}`;
}

function buildConversationText(parts) {
  const lines = [];
  for (const p of parts) {
    const role = p.author_type === 'user' ? 'Customer'
      : p.author_type === 'admin' ? 'Agent'
      : p.author_type === 'lead' ? 'Lead'
      : 'Bot';
    const ts = p.created_at ? ` (${p.created_at})` : '';
    lines.push(`[${role}${ts}]: ${p.body}`);
  }
  return lines.join('\n\n');
}

// ── LLM call ─────────────────────────────────────────────────────────────

async function classifyConversation(client, model, systemPrompt, conversationText, matchedKeywords) {
  const userMessage = `<matched_keywords>${matchedKeywords.join(', ')}</matched_keywords>

<conversation>
${conversationText}
</conversation>

Classify this conversation. Return only the JSON object.`;

  const response = await client.chat.completions.create({
    model,
    max_tokens: 256,
    temperature: 0,
    response_format: { type: 'json_object' },
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage },
    ],
  });

  const text = response.choices[0]?.message?.content || '';
  try {
    return JSON.parse(text);
  } catch {
    // Fallback: extract JSON from markdown code blocks
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try { return JSON.parse(jsonMatch[0]); } catch { /* fall through */ }
    }
    return { is_developer_api: false, confidence: 0, category: 'parse_error', reasoning: `Invalid JSON: ${text.substring(0, 100)}` };
  }
}

// ── Concurrency helper ───────────────────────────────────────────────────

async function mapConcurrent(items, fn, concurrency) {
  const results = new Array(items.length);
  let idx = 0;
  async function worker() {
    while (idx < items.length) {
      const i = idx++;
      results[i] = await fn(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => worker()));
  return results;
}

// ── Report writer ────────────────────────────────────────────────────────

function writeReport(classified, reportPath, meta) {
  const tp = classified.filter(c => c.llm.is_developer_api);
  const fp = classified.filter(c => !c.llm.is_developer_api);

  const lines = [
    `# Developer/API Research – LLM-Classified Report`,
    ``,
    `**Date range:** ${meta.from_date} → ${meta.to_date}`,
    `**Keyword matches:** ${classified.length}`,
    `**LLM true positives:** ${tp.length}`,
    `**LLM false positives:** ${fp.length}`,
    `**Precision (LLM):** ${classified.length > 0 ? Math.round(tp.length / classified.length * 100) : 0}%`,
    `**Model:** ${meta.model}`,
    ``,
    `---`,
    ``,
  ];

  // Summary table
  lines.push(`## Summary`);
  lines.push(``);
  lines.push(`| # | Conv ID | LLM Verdict | Confidence | Category | Reasoning |`);
  lines.push(`|---|---------|-------------|------------|----------|-----------|`);
  for (let i = 0; i < classified.length; i++) {
    const c = classified[i];
    const verdict = c.llm.is_developer_api ? '✅ Developer' : '❌ Not developer';
    const conf = `${Math.round((c.llm.confidence || 0) * 100)}%`;
    lines.push(`| ${i + 1} | ${c.conversation_id} | ${verdict} | ${conf} | ${c.llm.category || '-'} | ${c.llm.reasoning || '-'} |`);
  }
  lines.push(``);
  lines.push(`---`);
  lines.push(``);

  // True positives detail
  if (tp.length > 0) {
    lines.push(`## True Positives (Developer/API Conversations)`);
    lines.push(``);
    for (const c of tp) {
      lines.push(`### Conv ${c.conversation_id}`);
      lines.push(``);
      lines.push(`- **Created:** ${c.created_at}`);
      lines.push(`- **Tags:** ${(c.tags || []).join(', ') || '(none)'}`);
      lines.push(`- **Keyword matches:** ${c.matched_keywords.join(', ')}`);
      lines.push(`- **LLM category:** ${c.llm.category}`);
      lines.push(`- **LLM confidence:** ${Math.round((c.llm.confidence || 0) * 100)}%`);
      lines.push(`- **LLM reasoning:** ${c.llm.reasoning}`);
      lines.push(``);
      lines.push(`<details><summary>Full conversation</summary>`);
      lines.push(``);
      lines.push('```');
      lines.push(c.conversation_text.substring(0, 3000));
      if (c.conversation_text.length > 3000) lines.push('... (truncated)');
      lines.push('```');
      lines.push(``);
      lines.push(`</details>`);
      lines.push(``);
    }
    lines.push(`---`);
    lines.push(``);
  }

  // False positives summary
  if (fp.length > 0) {
    lines.push(`## Filtered Out (Not Developer/API)`);
    lines.push(``);
    for (const c of fp) {
      lines.push(`- **${c.conversation_id}** — ${c.llm.category}: ${c.llm.reasoning}`);
    }
    lines.push(``);
  }

  fs.writeFileSync(reportPath, lines.join('\n'), 'utf8');
  console.log(`Wrote report to ${reportPath}`);
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  loadEnv();
  const opts = parseArgs();

  const cachePath = resolvePath(opts.cache);
  const resultsPath = resolvePath(opts.results);
  const outputPath = opts.output ? resolvePath(opts.output) : null;
  const reportPath = opts.report ? resolvePath(opts.report) : null;
  const keywordsPath = resolvePath(opts.keywords || 'skills/intercom-developer-api-research/keywords.json');

  if (!cachePath || !fs.existsSync(cachePath)) {
    console.error('Cache file not found. Use --cache <path>');
    process.exit(1);
  }
  if (!resultsPath || !fs.existsSync(resultsPath)) {
    console.error('Scan results not found. Use --results <path>');
    process.exit(1);
  }

  const cache = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
  const scanResults = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));
  const config = JSON.parse(fs.readFileSync(keywordsPath, 'utf8'));

  // Build conversation lookup
  const convById = new Map();
  for (const conv of cache.conversations || []) {
    convById.set(String(conv.conversation_id), conv);
  }

  // Prepare items to classify (skip conversations not in cache)
  const toClassify = [];
  for (const match of scanResults.matches) {
    const conv = convById.get(String(match.conversation_id));
    if (!conv) {
      console.warn(`  WARNING: conversation ${match.conversation_id} not found in cache, skipping`);
      continue;
    }
    const conversationText = buildConversationText(conv.parts || []);
    if (!conversationText) {
      console.warn(`  WARNING: conversation ${match.conversation_id} has no text, skipping`);
      continue;
    }
    const matchedKeywords = [...new Set(
      (match.matched_in || []).flatMap(m => m.matched_keywords || [])
    )];
    toClassify.push({
      conversation_id: match.conversation_id,
      created_at: match.created_at,
      state: match.state,
      tags: match.tags,
      matched_keywords: matchedKeywords,
      conversation_text: conversationText,
    });
  }

  console.log(`Classifying ${toClassify.length} keyword matches with ${opts.model}...`);

  if (!config.definition) {
    console.error('keywords.json is missing the "definition" field (used as the LLM classification prompt).');
    process.exit(1);
  }

  const client = getOpenAIClient();
  const systemPrompt = buildClassificationPrompt(config.definition);

  const classified = await mapConcurrent(
    toClassify,
    async (item, i) => {
      try {
        const llm = await classifyConversation(
          client,
          opts.model,
          systemPrompt,
          item.conversation_text,
          item.matched_keywords
        );
        const verdict = llm.is_developer_api ? '✅' : '❌';
        console.log(`  [${i + 1}/${toClassify.length}] ${item.conversation_id} ${verdict} ${llm.category} (${Math.round((llm.confidence || 0) * 100)}%)`);
        return { ...item, llm };
      } catch (err) {
        console.log(`  [${i + 1}/${toClassify.length}] ${item.conversation_id} ⚠️  ERROR: ${err.message}`);
        return { ...item, llm: { is_developer_api: false, confidence: 0, category: 'api_error', reasoning: err.message } };
      }
    },
    opts.concurrency,
  );

  // Summary
  const tp = classified.filter(c => c.llm.is_developer_api);
  const fp = classified.filter(c => !c.llm.is_developer_api);
  console.log(`\nResults: ${tp.length} developer conversations, ${fp.length} filtered out`);
  console.log(`Precision: ${classified.length > 0 ? Math.round(tp.length / classified.length * 100) : 0}%`);

  // Output JSON
  const result = {
    source: 'llm_classify',
    model: opts.model,
    keyword_matches: scanResults.matches_found,
    llm_true_positives: tp.length,
    llm_false_positives: fp.length,
    precision_pct: classified.length > 0 ? Math.round(tp.length / classified.length * 100) : 0,
    from_date: scanResults.search_criteria?.from_date,
    to_date: scanResults.search_criteria?.to_date,
    classified,
  };

  if (outputPath) {
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8');
    console.log(`Wrote ${classified.length} classified results to ${outputPath}`);
  }

  if (reportPath) {
    writeReport(classified, reportPath, {
      from_date: scanResults.search_criteria?.from_date,
      to_date: scanResults.search_criteria?.to_date,
      model: opts.model,
    });
  }
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
