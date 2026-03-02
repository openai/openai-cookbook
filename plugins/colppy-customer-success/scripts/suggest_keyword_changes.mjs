#!/usr/bin/env node

/**
 * Analyze scan_feedback.json + local_scan_results.json to suggest keyword improvements.
 * Helps improve precision by learning from true/false positive labels.
 *
 * Usage:
 *   node scripts/suggest_keyword_changes.mjs [--feedback path] [--results path] [--keywords path]
 */

import fs from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PLUGIN_ROOT = join(__dirname, '..');
const SKILL_CACHE = join(PLUGIN_ROOT, 'skills', 'intercom-developer-api-research', 'cache');

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    feedback: null,
    results: null,
    keywords: null,
  };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--feedback' && args[i + 1]) opts.feedback = args[++i];
    else if (args[i] === '--results' && args[i + 1]) opts.results = args[++i];
    else if (args[i] === '--keywords' && args[i + 1]) opts.keywords = args[++i];
  }
  return opts;
}

function resolvePath(p, defaultPath) {
  if (!p) return defaultPath;
  if (p.startsWith('/')) return p;
  return join(PLUGIN_ROOT, p);
}

function getMatchedKeywords(match) {
  const kw = new Set();
  for (const m of match.matched_in || []) {
    for (const k of m.matched_keywords || []) kw.add(k.toLowerCase());
  }
  return kw;
}

function main() {
  const opts = parseArgs();
  const feedbackPath = resolvePath(opts.feedback, join(SKILL_CACHE, 'scan_feedback.json'));
  const resultsPath = resolvePath(opts.results, join(SKILL_CACHE, 'local_scan_results.json'));
  const keywordsPath = resolvePath(opts.keywords, join(PLUGIN_ROOT, 'skills', 'intercom-developer-api-research', 'keywords.json'));

  if (!fs.existsSync(feedbackPath)) {
    console.error('Feedback file not found:', feedbackPath);
    console.error('Edit scan_feedback.json with true_positives and false_positives, then re-run.');
    process.exit(1);
  }
  if (!fs.existsSync(resultsPath)) {
    console.error('Scan results not found:', resultsPath);
    console.error('Run local_scan.mjs first with --output.');
    process.exit(1);
  }

  const feedback = JSON.parse(fs.readFileSync(feedbackPath, 'utf8'));
  const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));
  const config = JSON.parse(fs.readFileSync(keywordsPath, 'utf8'));
  const excludeIfOnly = new Set((config.exclude_if_only || []).map((k) => k.toLowerCase()));

  const tpIds = new Set((feedback.true_positives || []).map(String));
  const fpIds = new Set((feedback.false_positives || []).map(String));

  const matchById = new Map();
  for (const m of results.matches || []) {
    matchById.set(String(m.conversation_id), m);
  }

  const fpKeywords = new Map(); // convId -> Set of keywords
  const tpKeywords = new Map();
  for (const id of fpIds) {
    const m = matchById.get(id);
    if (m) fpKeywords.set(id, getMatchedKeywords(m));
  }
  for (const id of tpIds) {
    const m = matchById.get(id);
    if (m) tpKeywords.set(id, getMatchedKeywords(m));
  }

  const allFpKw = new Set();
  for (const s of fpKeywords.values()) for (const k of s) allFpKw.add(k);
  const allTpKw = new Set();
  for (const s of tpKeywords.values()) for (const k of s) allTpKw.add(k);

  const inFpNotTp = [...allFpKw].filter((k) => !allTpKw.has(k));
  const inBoth = [...allFpKw].filter((k) => allTpKw.has(k));
  const inFpNotExcluded = [...allFpKw].filter((k) => !excludeIfOnly.has(k));

  console.log('\n=== Keyword Improvement Analysis ===\n');
  console.log(`Feedback: ${tpIds.size} true positives, ${fpIds.size} false positives`);
  console.log('');

  if (fpIds.size === 0) {
    console.log('No false positives marked. Add conversation IDs to false_positives in scan_feedback.json to get suggestions.');
    return;
  }

  console.log('--- False positives: matched keywords ---');
  for (const id of fpIds) {
    const kw = fpKeywords.get(id);
    const excluded = kw ? [...kw].filter((k) => excludeIfOnly.has(k)).sort() : [];
    const notExcluded = kw ? [...kw].filter((k) => !excludeIfOnly.has(k)).sort() : [];
    console.log(`  ${id}: ${kw ? [...kw].sort().join(', ') : '?'}`);
    if (notExcluded.length > 0) {
      console.log(`    → Not yet in exclude_if_only: ${notExcluded.join(', ')}`);
    }
  }
  console.log('');

  console.log('--- Keywords in FPs but NOT in TPs (safer to add to exclude_if_only) ---');
  if (inFpNotTp.length === 0) {
    console.log('  (none)');
  } else {
    const notYetExcluded = inFpNotTp.filter((k) => !excludeIfOnly.has(k));
    if (notYetExcluded.length > 0) {
      console.log(`  Consider adding: ${notYetExcluded.join(', ')}`);
      console.log('  → These appear only in false positives; adding them reduces noise without hurting true positives.');
    } else {
      console.log('  All such keywords are already in exclude_if_only.');
    }
  }
  console.log('');

  console.log('--- Keywords in BOTH FPs and TPs (review manually) ---');
  if (inBoth.length === 0) {
    console.log('  (none)');
  } else {
    const notYetExcluded = inBoth.filter((k) => !excludeIfOnly.has(k));
    console.log(`  ${inBoth.join(', ')}`);
    if (notYetExcluded.length > 0) {
      console.log(`  → Adding these to exclude_if_only could exclude true positives.`);
      console.log('  → Only add if the FP context is clearly different (e.g. bot vs user).');
    }
  }
  console.log('');

  console.log('--- FPs that would be excluded if we added their missing keywords ---');
  for (const id of fpIds) {
    const kw = fpKeywords.get(id);
    if (!kw || kw.size === 0) continue;
    const missing = [...kw].filter((k) => !excludeIfOnly.has(k));
    if (missing.length === 0) {
      console.log(`  ${id}: already fully covered by exclude_if_only (should be excluded - check scan logic)`);
    } else {
      const wouldExcludeTp = [...tpKeywords.values()].some((tpSet) => {
        const tpMissing = [...tpSet].filter((k) => !excludeIfOnly.has(k));
        return tpMissing.length <= 1 && (tpMissing.length === 0 || missing.some((m) => tpSet.has(m)));
      });
      if (wouldExcludeTp) {
        console.log(`  ${id}: add [${missing.join(', ')}] → ⚠️  Risk: might exclude a true positive`);
      } else {
        console.log(`  ${id}: add [${missing.join(', ')}] → ✓ Safe (no TP has same pattern)`);
      }
    }
  }
  console.log('');
  console.log('--- Next steps ---');
  console.log('1. Apply suggested changes to keywords.json (exclude_if_only array)');
  console.log('2. Re-run: node scripts/local_scan.mjs --cache ... --output ... --report ...');
  console.log('3. Review new report, update scan_feedback.json');
  console.log('4. Repeat until precision is satisfactory');
  console.log('');
}

main();
