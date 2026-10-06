import test from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import { buildProgressContext, createBuildProgressEstimator, estimateBuildProgress, fallbackBuildOutputTokens, validBuildOutputTokens } from '../server/build-progress-estimate.mjs';
import { createBuildComparison } from '../server/build-comparison.mjs';

const snapshot = () => ({ currentRevisionId: 2, revisions: [{ id: 2, source: 'export const meta = {};', tests: 'export function runTests() {}' }], state: { projects: [{ title: 'PRIVATE_PROJECT' }], contributions: [{ actorId: 'PRIVATE_ACTOR' }], extras: { notes: { user: { text: 'PRIVATE_RECORD' } } } }, session: { items: [{ content: 'PRIVATE_TOOL_OUTPUT' }], turns: [{ message: 'Add a garden' }] } });
const context = () => buildProgressContext({ snapshot: snapshot(), message: 'Make the flowers move smoothly', model: 'gpt-6-astra' });
const completion = value => ({ status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text: JSON.stringify(value) }] }] });

test('estimator uses one structured HTTP request with no tools, reasoning, routing override or retained state', async () => {
  const calls = [];
  const estimator = createBuildProgressEstimator({ apiKey: 'test-key', fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return Response.json(completion({ expectedOutputTokens: 4200 }));
  } });
  const result = await estimateBuildProgress({ estimator, context: context() });
  assert.deepEqual(result, { status: 'ready', expectedOutputTokens: 4200 });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://api.openai.com/v1/responses');
  const { headers, body } = calls[0].options;
  assert.equal(headers.Authorization, 'Bearer test-key');
  assert.equal(headers['OpenAI-Service-Tier'], undefined);
  const request = JSON.parse(body);
  assert.equal(request.model, 'gpt-6-sol');
  assert.deepEqual(request.reasoning, { effort: 'none' });
  assert.equal(request.service_tier, 'default');
  assert.equal(request.store, false);
  assert.equal(request.stream, false);
  assert.equal(request.max_output_tokens, 128);
  assert.equal(request.tools, undefined);
  assert.equal(request.text.format.type, 'json_schema');
  assert.equal(request.text.format.strict, true);
  assert.equal(request.text.format.schema.additionalProperties, false);
  assert.deepEqual(request.text.format.schema.properties.expectedOutputTokens, { type: 'integer', minimum: 128, maximum: 128_000 });
  assert.match(request.instructions, /untrusted task data/);
  assert.deepEqual(JSON.parse(request.input[0].content), context());
});

test('context bounds code and recent requests while excluding participant data and tool history', () => {
  const data = snapshot();
  data.revisions[0].source = 'a'.repeat(100_000);
  data.revisions[0].tests = 'b'.repeat(30_000);
  data.session.turns = Array.from({ length: 5 }, (_, i) => ({ message: `${i}:${'request'.repeat(400)}` }));
  const projected = buildProgressContext({ snapshot: data, message: 'Add physics', model: 'gpt-6-astra' });
  assert.equal(projected.workspace.source.characters, 100_000);
  assert.equal(projected.workspace.source.truncated, true);
  assert.ok(projected.workspace.source.sample.length < 18_100);
  assert.ok(projected.workspace.tests.sample.length < 6_100);
  assert.equal(projected.recentOwnerRequests.length, 3);
  assert.ok(projected.recentOwnerRequests.every(text => text.length <= 600));
  assert.match(projected.recentOwnerRequests[0], /^2:/);
  assert.deepEqual(projected.workspace.state, { projectCount: 1, contributionCount: 1, extraFeatureCount: 1, extraRecordCount: 1 });
  assert.doesNotMatch(JSON.stringify(projected), /PRIVATE_/);
  assert.equal(projected.builder.maxRounds, 8);
  assert.equal(projected.builder.maxOutputTokensPerRound, 16_000);
  assert.match(projected.builder.requirements, /each capped at 16,000 output tokens/);
  assert.equal(projected.builder.reasoningEffort, 'low');
  assert.match(projected.builder.requirements, /Exclude hidden reasoning tokens/);
  assert.match(projected.builder.requirements, /test code, repair attempts/);
});

test('invalid, refused, incomplete and oversized estimates fail open without a retry', async () => {
  const invalid = [
    completion({ expectedOutputTokens: '4200' }), completion({ expectedOutputTokens: 1 }),
    completion({ expectedOutputTokens: 128_001 }), completion({ expectedOutputTokens: 4200.5 }),
    completion({ expectedOutputTokens: 4200, secret: 'private' }),
    { ...completion({ expectedOutputTokens: 4200 }), status: 'incomplete' },
    { status: 'completed', output: [{ type: 'message', content: [{ type: 'refusal', refusal: 'no' }] }] },
    { ...completion({ expectedOutputTokens: 4200 }), unused: 'x'.repeat(17_000) },
  ];
  for (const payload of invalid) {
    let count = 0;
    const estimator = createBuildProgressEstimator({ apiKey: 'test', fetchImpl: async () => { count++; return Response.json(payload); } });
    assert.deepEqual(await estimateBuildProgress({ estimator, context: context() }), { status: 'fallback', expectedOutputTokens: fallbackBuildOutputTokens(context()) });
    assert.equal(count, 1);
  }
  assert.equal(createBuildProgressEstimator({ apiKey: '' }), null);
  assert.ok(validBuildOutputTokens((await estimateBuildProgress({ estimator: null, context: context() })).expectedOutputTokens));
});

test('HTTP failures cancel the unread body and never expose server details', async () => {
  let cancelled = false;
  const estimator = createBuildProgressEstimator({ apiKey: 'test', fetchImpl: async () => new Response(new ReadableStream({ cancel() { cancelled = true; } }), { status: 403 }) });
  const result = await estimateBuildProgress({ estimator, context: context() });
  assert.equal(cancelled, true);
  assert.deepEqual(Object.keys(result).sort(), ['expectedOutputTokens', 'status']);
  assert.equal(result.status, 'fallback');
});

test('deadline aborts the request and freezes fallback even when estimator ignores abort', async () => {
  let signal, resolve;
  const pending = new Promise(done => { resolve = done; });
  const resultPromise = estimateBuildProgress({ context: context(), timeoutMs: 15, estimator: async options => { signal = options.signal; return pending; } });
  await delay(30);
  const result = await resultPromise;
  assert.equal(result.status, 'fallback');
  assert.equal(signal.aborted, true);
  resolve({ expectedOutputTokens: 9000 });
  await delay(0);
  assert.equal(result.expectedOutputTokens, fallbackBuildOutputTokens(context()));
});

test('external cancellation rejects rather than publishing a fallback estimate', async () => {
  const controller = new AbortController();
  let calls = 0;
  const result = estimateBuildProgress({ context: context(), signal: controller.signal, estimator: () => { calls++; return new Promise(() => {}); } });
  controller.abort();
  await assert.rejects(result, { name: 'AbortError' });
  assert.equal(calls, 0, 'Cancellation before the scheduled request must not dispatch it');
});

test('comparison projection accepts one validated budget and rejects stale, terminal and private fields', t => {
  const feed = createBuildComparison();
  t.after(() => feed.close());
  const begin = () => feed.begin({ model: 'test', primaryTurnId: 'uf', standardTurnId: 'std' });
  const first = begin();
  assert.deepEqual(first.progress, { status: 'pending' });
  for (const value of [-1, NaN, Infinity, '3000', 1.5, 128_001]) feed.progress(first.id, { status: 'ready', expectedOutputTokens: value });
  assert.deepEqual(feed.read().progress, { status: 'pending' });
  feed.progress(first.id, { status: 'ready', expectedOutputTokens: 3000, secret: 'PRIVATE' });
  feed.progress(first.id, { status: 'fallback', expectedOutputTokens: 7000 });
  assert.deepEqual(feed.read().progress, { status: 'ready', expectedOutputTokens: 3000 });
  assert.doesNotMatch(JSON.stringify(feed.snapshot()), /PRIVATE/);
  const second = begin();
  feed.progress(first.id, { status: 'ready', expectedOutputTokens: 6000 });
  assert.deepEqual(feed.read().progress, { status: 'pending' });
  feed.fail(second.id, 'ultrafast', 'uf', 'failed');
  feed.fail(second.id, 'standard', 'std', 'failed');
  feed.progress(second.id, { status: 'ready', expectedOutputTokens: 6000 });
  assert.deepEqual(feed.read().progress, { status: 'pending' });
  const third = begin();
  feed.finish(third.id);
  feed.progress(third.id, { status: 'fallback', expectedOutputTokens: 6000 });
  assert.deepEqual(feed.read().progress, { status: 'pending' });
});
