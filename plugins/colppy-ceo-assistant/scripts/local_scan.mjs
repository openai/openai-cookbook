#!/usr/bin/env node

/**
 * Local keyword scan for Intercom developer/API research.
 * Re-runs keyword matching on cached conversation data without API calls.
 *
 * Usage:
 *   node scripts/local_scan.js --cache skills/intercom-developer-api-research/cache/conversations.json --keywords skills/intercom-developer-api-research/keywords.json
 *
 * First run scan_full_text with save_cache to create the cache file.
 */

import fs from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PLUGIN_ROOT = join(__dirname, '..');

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { cache: null, keywords: null, output: null, fullContext: false, report: null };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--cache' && args[i + 1]) opts.cache = args[++i];
    else if (args[i] === '--keywords' && args[i + 1]) opts.keywords = args[++i];
    else if (args[i] === '--output' && args[i + 1]) opts.output = args[++i];
    else if (args[i] === '--full-context') opts.fullContext = true;
    else if (args[i] === '--report' && args[i + 1]) opts.report = args[++i];
  }
  return opts;
}

function resolvePath(p) {
  if (!p) return null;
  if (p.startsWith('/')) return p;
  return join(PLUGIN_ROOT, p);
}

function runLocalScan(cachePath, keywordsPath, outputPath, opts = {}) {
  const { fullContext = false } = opts;
  const cache = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
  const config = JSON.parse(fs.readFileSync(keywordsPath, 'utf8'));

  const keywords = (config.keywords || []).map((k) => k.toLowerCase());
  const excludeIfOnly = new Set((config.exclude_if_only || []).map((k) => k.toLowerCase()));
  const topic = config.topic || cache.topic || 'Colppy API integration';

  if (keywords.length === 0) {
    console.error('No keywords in config. Check keywords.json.');
    process.exit(1);
  }

  const matches = [];
  for (const conv of cache.conversations || []) {
    const parts = conv.parts || [];
    const matchedParts = [];

    for (const p of parts) {
      const body = p.body || '';
      const bodyLower = body.toLowerCase();
      const matchedKw = keywords.filter((kw) => bodyLower.includes(kw));
      if (matchedKw.length > 0) {
        const part = {
          author_type: p.author_type || 'unknown',
          matched_keywords: matchedKw,
          excerpt: body.substring(0, 200) + (body.length > 200 ? '…' : ''),
          created_at: p.created_at || null,
        };
        if (fullContext) part.full_body = body;
        matchedParts.push(part);
      }
    }

    if (matchedParts.length === 0) continue;

    const allMatched = new Set(
      matchedParts.flatMap((mp) => (mp.matched_keywords || []).map((k) => k.toLowerCase()))
    );
    if (excludeIfOnly.size > 0 && allMatched.size > 0) {
      const onlyExcluded = [...allMatched].every((kw) => excludeIfOnly.has(kw));
      if (onlyExcluded) continue;
    }

    const match = {
      conversation_id: conv.conversation_id,
      created_at: conv.created_at || '',
      state: conv.state || '',
      tags: conv.tags || [],
      match_reason: `Found in ${matchedParts.length} message(s)`,
      matched_in: matchedParts,
      admin_assignee_id: null,
      contact_count: null,
    };
    if (fullContext) {
      const matchedByKey = new Map();
      for (const mp of matchedParts) {
        const key = `${mp.created_at || ''}|${mp.author_type || ''}`;
        if (!matchedByKey.has(key)) matchedByKey.set(key, []);
        matchedByKey.get(key).push(...(mp.matched_keywords || []));
      }
      match.conversation_thread = parts.map((p) => {
        const key = `${p.created_at || ''}|${p.author_type || 'unknown'}`;
        const kw = matchedByKey.get(key);
        return {
          author_type: p.author_type || 'unknown',
          body: p.body || '',
          created_at: p.created_at || null,
          matched_keywords: kw ? [...new Set(kw)] : undefined,
        };
      });
    }
    matches.push(match);
  }

  const result = {
    success: true,
    source: 'local_scan',
    research_topic: topic,
    search_criteria: {
      keywords,
      from_date: cache.from_date,
      to_date: cache.to_date,
      state: cache.state,
      exclude_if_only: config.exclude_if_only || [],
    },
    conversations_scanned: (cache.conversations || []).length,
    matches_found: matches.length,
    matches,
  };

  const json = JSON.stringify(result, null, 2);
  if (outputPath) {
    fs.writeFileSync(outputPath, json, 'utf8');
    console.log(`Wrote ${matches.length} matches to ${outputPath}`);
  } else {
    console.log(json);
  }
  return result;
}

function writeMarkdownReport(result, reportPath) {
  const lines = [
    `# Developer/API Research – Scan Report`,
    ``,
    `**Date range:** ${result.search_criteria.from_date} → ${result.search_criteria.to_date}`,
    `**Conversations scanned:** ${result.conversations_scanned}`,
    `**Matches found:** ${result.matches_found}`,
    ``,
    `**Improve:** 1) Edit \`scan_feedback.json\` (true/false positives). 2) Run \`node scripts/suggest_keyword_changes.mjs\`. 3) Apply to keywords.json, re-scan.`,
    ``,
    `---`,
    ``,
  ];
  for (let i = 0; i < result.matches.length; i++) {
    const m = result.matches[i];
    lines.push(`## ${i + 1}. Conversation ${m.conversation_id}`);
    lines.push(``);
    lines.push(`- **Created:** ${m.created_at}`);
    lines.push(`- **State:** ${m.state}`);
    lines.push(`- **Tags:** ${(m.tags || []).join(', ') || '(none)'}`);
    lines.push(`- **Matched keywords:** ${m.matched_in.flatMap((p) => p.matched_keywords).filter((v, i, a) => a.indexOf(v) === i).join(', ')}`);
    lines.push(``);
    lines.push(`### Full conversation`);
    lines.push(``);
    const thread = m.conversation_thread || m.matched_in;
    for (const p of thread) {
      const label = p.author_type === 'user' ? '👤 User' : p.author_type === 'admin' ? '👔 Admin' : p.author_type === 'lead' ? '📧 Lead' : '🤖 Bot';
      const body = p.body || p.full_body || p.excerpt || '';
      const kw = p.matched_keywords?.length ? ` → **matched: ${p.matched_keywords.join(', ')}**` : '';
      lines.push(`**${label}** ${p.created_at || ''}${kw}`);
      lines.push(``);
      lines.push('```');
      lines.push(body);
      lines.push('```');
      lines.push(``);
    }
    lines.push(`---`);
    lines.push(``);
  }
  fs.writeFileSync(reportPath, lines.join('\n'), 'utf8');
  console.log(`Wrote report to ${reportPath}`);
}

const opts = parseArgs();
const cachePath = resolvePath(opts.cache);
const keywordsPath = resolvePath(opts.keywords || 'skills/intercom-developer-api-research/keywords.json');
const outputPath = opts.output ? resolvePath(opts.output) : null;
const reportPath = opts.report ? resolvePath(opts.report) : null;
const fullContext = opts.fullContext || !!opts.report;

if (!cachePath || !fs.existsSync(cachePath)) {
  console.error('Usage: node scripts/local_scan.mjs --cache <path> [--keywords <path>] [--output <path>] [--full-context] [--report <path>]');
  console.error('  --full-context   Include full message bodies and conversation thread in JSON output');
  console.error('  --report <path>  Write a Markdown report with full conversation context (implies --full-context)');
  console.error('Cache file not found. Run scan_full_text with save_cache first.');
  process.exit(1);
}

if (!keywordsPath || !fs.existsSync(keywordsPath)) {
  console.error('Keywords file not found:', keywordsPath);
  process.exit(1);
}

const result = runLocalScan(cachePath, keywordsPath, outputPath, { fullContext });
if (reportPath) {
  writeMarkdownReport(result, reportPath);
}
