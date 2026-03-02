import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { buildSearchQuery, fetchConversationIds } from '../intercom-api-helpers.js';
import { extractUserTypeAttributes } from '../export_cache_for_local_scan.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..', '..', '..', '..');

test('buildSearchQuery uses inclusive end-of-day timestamp for to_date', () => {
  const query = buildSearchQuery({
    from_date: '2026-02-13',
    to_date: '2026-02-13',
    state: 'closed',
    team_assignee_id: '2334166',
  });
  const createdAtGte = query.query.value.find(v => v.field === 'created_at' && v.operator === '>=');
  const createdAtLte = query.query.value.find(v => v.field === 'created_at' && v.operator === '<=');
  assert.equal(createdAtGte.value, Math.floor(Date.parse('2026-02-13T00:00:00Z') / 1000));
  assert.equal(createdAtLte.value, Math.floor(Date.parse('2026-02-13T23:59:59Z') / 1000));
});

test('fetchConversationIds sends inclusive end-of-day timestamp in search payload', async () => {
  let payload;
  const intercomApi = {
    post: async (_url, body) => {
      payload = body;
      return { data: { conversations: [], pages: {} } };
    },
  };

  const ids = await fetchConversationIds(
    intercomApi,
    '2026-02-13',
    '2026-02-13',
    null,
    null,
    '2334166'
  );

  assert.deepEqual(ids, []);
  const createdAtLte = payload.query.value.find(v => v.field === 'created_at' && v.operator === '<=');
  assert.equal(createdAtLte.value, Math.floor(Date.parse('2026-02-13T23:59:59Z') / 1000));
});

test('extractUserTypeAttributes supports legacy and current Intercom custom-attribute keys', () => {
  const attrs = extractUserTypeAttributes({
    'Es Contador': 'true',
    '¿Cuál es tu rol? wizard': 'contador',
  });
  assert.equal(attrs.es_contador, 'true');
  assert.equal(attrs.rol_wizard, 'contador');
});

test('llm_classify apply-review promotes only reviewed examples and keeps corrected match/category consistent', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'llm-review-regression-'));
  const topicPath = path.join(tempDir, 'topic.json');
  const reviewPath = path.join(tempDir, 'review.json');
  const scriptPath = path.join(repoRoot, 'plugins', 'colppy-customer-success', 'scripts', 'llm_classify.mjs');

  const topic = {
    topic_name: 'Setup / Onboarding',
    match_field: 'is_setup_onboarding',
    definition: 'Test definition.',
    categories: ['company_setup', 'other'],
    few_shot_examples: [],
  };
  fs.writeFileSync(topicPath, JSON.stringify(topic, null, 2), 'utf8');

  const review = {
    topic: 'Setup / Onboarding',
    match_field: 'is_setup_onboarding',
    model: 'test',
    classified_at: new Date().toISOString(),
    total_classified: 3,
    matches: 1,
    reviews: [
      {
        conversation_id: 'conv-1',
        snippet: 'conversation one',
        matched_keywords: [],
        llm_result: {
          is_setup_onboarding: false,
          category: 'other',
          confidence: 0.2,
          reasoning: 'wrong',
        },
        correct: false,
        override_category: 'company_setup',
        override_match: null,
        promote_to_example: true,
      },
      {
        conversation_id: 'conv-2',
        snippet: 'conversation two',
        matched_keywords: [],
        llm_result: {
          is_setup_onboarding: true,
          category: 'company_setup',
          confidence: 0.8,
          reasoning: 'unreviewed',
        },
        correct: null,
        override_category: null,
        override_match: null,
        promote_to_example: true,
      },
      {
        conversation_id: 'conv-3',
        snippet: 'conversation three',
        matched_keywords: [],
        llm_result: {
          is_setup_onboarding: true,
          category: 'company_setup',
          confidence: 0.9,
          reasoning: 'good',
        },
        correct: true,
        override_category: null,
        override_match: null,
        promote_to_example: true,
      },
    ],
  };
  fs.writeFileSync(reviewPath, JSON.stringify(review, null, 2), 'utf8');

  const proc = spawnSync(
    'node',
    [scriptPath, '--apply-review', reviewPath, '--topic', topicPath],
    { cwd: repoRoot, encoding: 'utf8' }
  );
  assert.equal(proc.status, 0, proc.stderr || proc.stdout);

  const updatedTopic = JSON.parse(fs.readFileSync(topicPath, 'utf8'));
  assert.equal(updatedTopic.few_shot_examples.length, 2);

  const corrected = updatedTopic.few_shot_examples.find(e => e.conversation_snippet === 'conversation one');
  assert.ok(corrected, 'corrected reviewed example should be promoted');
  assert.equal(corrected.classification.category, 'company_setup');
  assert.equal(corrected.classification.is_setup_onboarding, true);

  const unreviewed = updatedTopic.few_shot_examples.find(e => e.conversation_snippet === 'conversation two');
  assert.equal(unreviewed, undefined, 'unreviewed promoted example must be skipped');
});

test('README examples are aligned with supported CLI usage', () => {
  const pluginReadme = fs.readFileSync(
    path.join(repoRoot, 'plugins', 'colppy-customer-success', 'README.md'),
    'utf8'
  );
  const onboardingReadme = fs.readFileSync(
    path.join(repoRoot, 'plugins', 'colppy-customer-success', 'skills', 'intercom-onboarding-setup', 'README.md'),
    'utf8'
  );

  assert.match(
    pluginReadme,
    /--cache plugins\/colppy-customer-success\/skills\/intercom-developer-api-research\/cache\/conversations_YYYY-MM-DD_YYYY-MM-DD_team2334166\.json/
  );
  assert.ok(!onboardingReadme.includes('--segment '), 'README should not reference unsupported --segment flag');
});
