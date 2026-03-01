#!/usr/bin/env node

/**
 * Topic-agnostic LLM classifier for Intercom conversations.
 *
 * Classifies conversations against any topic defined in a topic config JSON file.
 * The config file must contain a "definition" and "system_prompt" (or it falls back
 * to a default developer/API prompt built from the definition).
 *
 * Usage:
 *   # Full scan — classify every conversation in cache against a topic:
 *   node scripts/llm_classify.mjs \
 *     --cache <conversations_cache.json> \
 *     --topic <topic_config.json> \
 *     --all \
 *     [--output results.json] [--report report.md] \
 *     [--model gpt-4o-mini] [--concurrency 3]
 *
 *   # Keyword-filtered mode — classify only pre-filtered matches:
 *   node scripts/llm_classify.mjs \
 *     --cache <conversations_cache.json> \
 *     --topic <topic_config.json> \
 *     --results <scan_results.json> \
 *     [--output results.json] [--report report.md]
 *
 * Topic config JSON format:
 *   {
 *     "topic_name": "Developer/API Conversations",
 *     "match_field": "is_developer_api",
 *     "definition": "...",
 *     "system_prompt": "full system prompt (optional, overrides default)",
 *     "categories": ["api_integration", "api_bug", ...],
 *     "keywords": [...],
 *     "exclude_if_only": [...]
 *   }
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
    concurrency: 10,
    keywords: null,
    all: false,
  };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--cache' && args[i + 1]) opts.cache = args[++i];
    else if (args[i] === '--results' && args[i + 1]) opts.results = args[++i];
    else if (args[i] === '--output' && args[i + 1]) opts.output = args[++i];
    else if (args[i] === '--report' && args[i + 1]) opts.report = args[++i];
    else if (args[i] === '--model' && args[i + 1]) opts.model = args[++i];
    else if (args[i] === '--concurrency' && args[i + 1]) opts.concurrency = parseInt(args[++i], 10);
    else if ((args[i] === '--keywords' || args[i] === '--topic') && args[i + 1]) opts.keywords = args[++i];
    else if (args[i] === '--all') opts.all = true;
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

function buildClassificationPrompt(config) {
  // If the config provides a full system_prompt, use it directly
  if (config.system_prompt) {
    return config.system_prompt;
  }

  // Otherwise, build a generic prompt from the config fields
  const matchField = config.match_field || 'is_match';
  const topicName = config.topic_name || 'the specified topic';
  const categories = config.categories
    ? config.categories.join(' | ')
    : 'match | other';

  let prompt = `You are classifying Intercom support conversations for a B2B SaaS company called Colppy (Argentine accounting software).

<topic>
${topicName}
</topic>

<definition>
${config.definition}
</definition>`;

  if (config.false_positives || config.true_positives) {
    prompt += `\n\n<context>`;
    if (config.false_positives) {
      prompt += `\nFALSE POSITIVE signals (do NOT match these):\n${config.false_positives.map(fp => `- ${fp}`).join('\n')}`;
    }
    if (config.true_positives) {
      prompt += `\n\nTRUE POSITIVE signals:\n${config.true_positives.map(tp => `- ${tp}`).join('\n')}`;
    }
    prompt += `\n</context>`;
  }

  prompt += `

Classify the conversation below. Respond in this exact JSON format:
{
  "${matchField}": true/false,
  "confidence": 0.0-1.0,
  "category": "one of: ${categories}",
  "reasoning": "1-2 sentence explanation"
}`;

  return prompt;
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

// ── Retry helper ─────────────────────────────────────────────────────────

async function withRetry(fn, { maxRetries = 3, baseDelay = 1000 } = {}) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      const isRateLimit = err.status === 429 || err.code === 'rate_limit_exceeded';
      if (!isRateLimit || attempt === maxRetries) throw err;
      // Parse retry-after from error or use exponential backoff
      const retryAfter = err.headers?.['retry-after'];
      const delay = retryAfter ? parseFloat(retryAfter) * 1000 : baseDelay * Math.pow(2, attempt);
      await new Promise(r => setTimeout(r, delay));
    }
  }
}

// ── LLM call ─────────────────────────────────────────────────────────────

async function classifyConversation(client, model, systemPrompt, conversationText, matchedKeywords) {
  const userMessage = `<matched_keywords>${matchedKeywords.join(', ')}</matched_keywords>

<conversation>
${conversationText}
</conversation>

Classify this conversation. Return only the JSON object.`;

  const response = await withRetry(() => client.chat.completions.create({
    model,
    max_tokens: 256,
    temperature: 0,
    response_format: { type: 'json_object' },
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage },
    ],
  }));

  const text = response.choices[0]?.message?.content || '';
  try {
    return JSON.parse(text);
  } catch {
    // Fallback: extract JSON from markdown code blocks
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try { return JSON.parse(jsonMatch[0]); } catch { /* fall through */ }
    }
    return { is_match: false, confidence: 0, category: 'parse_error', reasoning: `Invalid JSON: ${text.substring(0, 100)}` };
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
  const topicLabel = meta.topic || 'Topic';
  const tp = classified.filter(c => c.llm.is_match);
  const fp = classified.filter(c => !c.llm.is_match);

  const lines = [
    `# ${topicLabel} – LLM-Classified Report`,
    ``,
    `**Date range:** ${meta.from_date} → ${meta.to_date}`,
    `**Total classified:** ${classified.length}`,
    `**Matches:** ${tp.length}`,
    `**Filtered out:** ${fp.length}`,
    `**Hit rate:** ${classified.length > 0 ? Math.round(tp.length / classified.length * 100) : 0}%`,
    `**Model:** ${meta.model}`,
    ``,
    `---`,
    ``,
  ];

  // Summary table
  lines.push(`## Summary`);
  lines.push(``);
  lines.push(`| # | Conv ID | Verdict | Confidence | Category | Reasoning |`);
  lines.push(`|---|---------|---------|------------|----------|-----------|`);
  for (let i = 0; i < classified.length; i++) {
    const c = classified[i];
    const verdict = c.llm.is_match ? '✅ Match' : '❌ No match';
    const conf = `${Math.round((c.llm.confidence || 0) * 100)}%`;
    lines.push(`| ${i + 1} | ${c.conversation_id} | ${verdict} | ${conf} | ${c.llm.category || '-'} | ${c.llm.reasoning || '-'} |`);
  }
  lines.push(``);
  lines.push(`---`);
  lines.push(``);

  // Matches detail
  if (tp.length > 0) {
    lines.push(`## Matches (${topicLabel})`);
    lines.push(``);
    for (const c of tp) {
      lines.push(`### Conv ${c.conversation_id}`);
      lines.push(``);
      lines.push(`- **Created:** ${c.created_at}`);
      lines.push(`- **Tags:** ${(c.tags || []).join(', ') || '(none)'}`);
      lines.push(`- **Keyword matches:** ${(c.matched_keywords || []).join(', ') || '(full scan)'}`);
      lines.push(`- **Category:** ${c.llm.category}`);
      lines.push(`- **Confidence:** ${Math.round((c.llm.confidence || 0) * 100)}%`);
      lines.push(`- **Reasoning:** ${c.llm.reasoning}`);
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

  // Filtered out summary
  if (fp.length > 0 && !meta.all_mode) {
    lines.push(`## Filtered Out`);
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
  if (!opts.all && (!resultsPath || !fs.existsSync(resultsPath))) {
    console.error('Scan results not found. Use --results <path> or --all to classify entire cache');
    process.exit(1);
  }

  const cache = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
  const scanResults = opts.all ? null : JSON.parse(fs.readFileSync(resultsPath, 'utf8'));
  const config = JSON.parse(fs.readFileSync(keywordsPath, 'utf8'));

  // Prepare items to classify
  const toClassify = [];

  if (opts.all) {
    // --all mode: classify every conversation in the cache
    for (const conv of cache.conversations || []) {
      const conversationText = buildConversationText(conv.parts || []);
      if (!conversationText) continue;
      toClassify.push({
        conversation_id: conv.conversation_id,
        created_at: conv.created_at,
        state: conv.state,
        tags: conv.tags || [],
        matched_keywords: [],
        conversation_text: conversationText,
      });
    }
  } else {
    // Normal mode: classify keyword matches only
    const convById = new Map();
    for (const conv of cache.conversations || []) {
      convById.set(String(conv.conversation_id), conv);
    }
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
  }

  const classifyLabel = opts.all ? 'conversations' : 'keyword matches';
  console.log(`Classifying ${toClassify.length} ${classifyLabel} with ${opts.model}...`);

  if (!config.definition && !config.system_prompt) {
    console.error('Topic config is missing "definition" or "system_prompt" field.');
    process.exit(1);
  }

  const matchField = config.match_field || 'is_developer_api';
  const topicName = config.topic_name || 'Developer/API';

  const client = getOpenAIClient();
  const systemPrompt = buildClassificationPrompt(config);

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
        // Normalize: ensure is_match field exists (maps from whatever match_field the LLM returns)
        llm.is_match = llm[matchField] ?? llm.is_match ?? false;
        const verdict = llm.is_match ? '✅' : '❌';
        console.log(`  [${i + 1}/${toClassify.length}] ${item.conversation_id} ${verdict} ${llm.category} (${Math.round((llm.confidence || 0) * 100)}%)`);
        return { ...item, llm };
      } catch (err) {
        console.log(`  [${i + 1}/${toClassify.length}] ${item.conversation_id} ⚠️  ERROR: ${err.message}`);
        return { ...item, llm: { is_match: false, confidence: 0, category: 'api_error', reasoning: err.message } };
      }
    },
    opts.concurrency,
  );

  // Summary
  const tp = classified.filter(c => c.llm.is_match);
  const fp = classified.filter(c => !c.llm.is_match);
  console.log(`\nResults: ${tp.length} ${topicName} conversations, ${fp.length} filtered out`);
  console.log(`Hit rate: ${classified.length > 0 ? Math.round(tp.length / classified.length * 100) : 0}%`);

  // Output JSON
  const classifiedOutput = opts.all ? classified.filter(c => c.llm.is_match) : classified;
  const result = {
    source: 'llm_classify',
    topic: topicName,
    mode: opts.all ? 'all' : 'keyword_matches',
    model: opts.model,
    total_classified: classified.length,
    matches: tp.length,
    hit_rate_pct: classified.length > 0 ? Math.round(tp.length / classified.length * 100) : 0,
    from_date: opts.all ? cache.from_date : scanResults.search_criteria?.from_date,
    to_date: opts.all ? cache.to_date : scanResults.search_criteria?.to_date,
    classified: classifiedOutput,
  };

  if (outputPath) {
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8');
    const writtenCount = result.classified.length;
    const writtenMsg = opts.all && writtenCount !== classified.length
      ? `Wrote ${writtenCount} developer-api conversations (of ${classified.length} classified) to ${outputPath}`
      : `Wrote ${writtenCount} classified results to ${outputPath}`;
    console.log(writtenMsg);
  }

  if (reportPath) {
    writeReport(classified, reportPath, {
      topic: topicName,
      from_date: opts.all ? cache.from_date : scanResults.search_criteria?.from_date,
      to_date: opts.all ? cache.to_date : scanResults.search_criteria?.to_date,
      model: opts.model,
      all_mode: opts.all,
    });
  }
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
