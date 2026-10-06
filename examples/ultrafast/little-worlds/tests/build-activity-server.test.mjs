import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createBuildActivity } from '../server/build-activity.mjs';
import { createSpaceService } from '../server/harness.mjs';
import { blankSeedSource, blankSeedTests } from '../server/seed.mjs';

function fixture(t, options = {}) {
  const feed = createBuildActivity({ intervalMs: 60_000, ...options });
  t.after(() => feed.close());
  return feed;
}
const message = text => ({ type: 'response.output_text.delta', output_index: 0, content_index: 0, delta: text });
const call = { type: 'function_call', call_id: 'write-1', name: 'apply_change', arguments: '{"source":"actual code"}' };

test('token bursts coalesce without awaiting subscribers and keep a stable entry identity/time', t => {
  let time = 1000;
  const feed = fixture(t, { now: () => time });
  const observed = [];
  feed.subscribe(event => observed.push(event));
  for (let index = 0; index < 1000; index++) assert.equal(feed.providerEvent('turn', 0, message('x')), undefined);
  assert.equal(observed.length, 0, 'no synchronous per-token notification');
  feed.flush();
  assert.equal(observed.length, 1);
  assert.equal(observed[0].data.text, 'x'.repeat(1000));
  time = 5000;
  feed.providerEvent('turn', 0, message('!')); feed.flush();
  assert.equal(observed.length, 2);
  assert.equal(observed[1].data.text, 'x'.repeat(1000) + '!');
  assert.equal(observed[1].time, observed[0].time);
  assert.equal(observed[1].data.entryId, observed[0].data.entryId);
  assert.notEqual(observed[1].id, observed[0].id);
});

test('completed output fills non-streaming adapters and does not duplicate streamed text or tools', t => {
  const feed = fixture(t);
  feed.providerEvent('turn', 0, message('Partial'));
  feed.providerEvent('turn', 0, { type: 'response.output_item.added', output_index: 1, item: { ...call, arguments: '' } });
  feed.providerEvent('turn', 0, { type: 'response.function_call_arguments.delta', output_index: 1, delta: '{"source":' });
  feed.providerOutput('turn', 0, [{ type: 'message', content: [{ type: 'output_text', text: 'Complete message' }] }, call]);
  let entries = feed.read();
  assert.equal(entries.length, 2);
  assert.equal(entries[0].data.text, 'Complete message');
  assert.equal(entries[0].data.status, 'completed');
  assert.equal(entries[1].data.arguments, call.arguments);
  feed.toolStarted('turn', call); feed.toolFinished('turn', call, { ok: true, revisionId: 2 }, 17);
  entries = feed.read();
  assert.equal(entries.length, 2);
  assert.equal(entries[1].data.status, 'completed');
  assert.equal(entries[1].data.durationMs, 17);
  assert.deepEqual(JSON.parse(entries[1].data.result), { ok: true, revisionId: 2 });
  feed.providerOutput('turn', 1, [{ type: 'message', content: [{ type: 'output_text', text: 'Fallback-only reply' }] }]);
  assert.equal(feed.read().at(-1).data.text, 'Fallback-only reply');
});

test('custom patch input streams verbatim and retains one row through completion and execution', t => {
  const feed = fixture(t);
  const input = '*** Begin Patch\n*** Update File: space.js\n@@\n-const color = "red";\n+const color = "blue";\n*** End Patch';
  const custom = { type: 'custom_tool_call', call_id: 'patch-1', name: 'apply_patch', input };
  feed.providerEvent('turn', 0, { type: 'response.output_item.added', output_index: 0, item: { ...custom, input: '' } });
  for (const delta of [input.slice(0, 36), input.slice(36, 70), input.slice(70)]) {
    feed.providerEvent('turn', 0, { type: 'response.custom_tool_call_input.delta', output_index: 0, delta });
  }
  feed.providerEvent('turn', 0, { type: 'response.function_call_arguments.delta', output_index: 0, delta: 'WRONG_EVENT_FAMILY' });
  const streamed = feed.read()[0];
  assert.equal(streamed.data.arguments, input);
  assert.equal(streamed.data.inputFormat, 'patch');
  assert.equal(streamed.data.status, 'running');
  feed.providerEvent('turn', 0, { type: 'response.custom_tool_call_input.done', output_index: 0, input });
  feed.providerEvent('turn', 0, { type: 'response.output_item.done', output_index: 0, item: custom });
  feed.providerOutput('turn', 0, [custom]);
  feed.toolStarted('turn', custom);
  feed.toolFinished('turn', custom, { ok: true, files: ['space.js'] }, 12);
  const entries = feed.read();
  assert.equal(entries.length, 1);
  assert.equal(entries[0].data.entryId, streamed.data.entryId);
  assert.equal(entries[0].data.arguments, input);
  assert.equal(entries[0].data.status, 'completed');
  assert.equal(entries[0].data.durationMs, 12);
});

test('custom patch failures and cancellation retain their input without exposing unrelated custom calls', t => {
  const feed = fixture(t);
  const custom = { type: 'custom_tool_call', call_id: 'patch-1', name: 'apply_patch', input: '*** Begin Patch\n*** Add File: space.js\n+partial' };
  feed.providerOutput('failed', 0, [custom]);
  feed.toolFinished('failed', custom, { error: 'The patch is incomplete' }, 1);
  feed.providerOutput('cancelled', 0, [custom, { ...custom, call_id: 'unknown', name: 'shell', input: 'PRIVATE_UNKNOWN_TOOL' }]);
  feed.lifecycle({ id: 'done', type: 'turn.cancelled', turnId: 'cancelled', title: 'Stopped' });
  const entries = feed.read();
  assert.equal(entries.find(entry => entry.turnId === 'failed').data.status, 'failed');
  assert.equal(entries.find(entry => entry.turnId === 'cancelled').data.status, 'cancelled');
  assert.equal(entries.find(entry => entry.turnId === 'cancelled').data.arguments, custom.input);
  assert.doesNotMatch(JSON.stringify(entries), /PRIVATE_UNKNOWN_TOOL/);
});

test('the feed exposes only visible text and known tools, never private provider context or reasoning', t => {
  const feed = fixture(t); const secret = 'PRIVATE_SECRET';
  feed.providerEvent('turn', 0, { type: 'response.created', response: { instructions: secret, input: secret, headers: secret } });
  for (const type of ['response.reasoning_text.delta', 'response.reasoning_summary_text.delta']) feed.providerEvent('turn', 0, { type, output_index: 0, delta: secret });
  feed.providerOutput('turn', 0, [
    { type: 'reasoning', encrypted_content: secret, summary: [{ text: secret }] },
    { type: 'message', headers: secret, content: [{ type: 'reasoning_text', text: secret }, { type: 'output_text', text: 'A visible answer' }] },
    { type: 'function_call', call_id: 'unknown', name: 'unknown', arguments: secret },
  ]);
  feed.lifecycle({ id: '1', type: 'model.completed', title: 'Finished', data: { model: 'test-model', outputTokens: 12, reasoningTokens: 3, headers: secret, instructions: secret, encrypted_content: secret } });
  const text = JSON.stringify(feed.read());
  assert.match(text, /A visible answer/); assert.match(text, /outputTokens/);
  assert.doesNotMatch(text, /PRIVATE_SECRET|encrypted_content|headers|instructions/);
});

test('credential-shaped strings are redacted even when split across stream chunks', t => {
  const feed = fixture(t);
  feed.providerEvent('turn', 0, message('Unexpected sk-proj-')); feed.flush();
  feed.providerEvent('turn', 0, message('sensitivecredential and Bearer token-value'));
  assert.equal(feed.read()[0].data.text, 'Unexpected [redacted] and Bearer [redacted]');
});

test('byte limits preserve a Unicode prefix and explicitly report every omitted byte', t => {
  const feed = fixture(t, { maxTextBytes: 9 });
  feed.providerEvent('turn', 0, message('😀😀😀')); feed.providerEvent('turn', 0, message('more'));
  const entry = feed.read()[0];
  assert.equal(entry.data.text, '😀😀');
  assert.equal(Buffer.byteLength(entry.data.text), 8);
  assert.equal(entry.data.truncated, true); assert.equal(entry.data.omittedBytes, 8);
  assert.doesNotMatch(entry.data.text, /�/);
});

test('entry and total content limits evict oldest rows while retaining bounded recent snapshots', t => {
  const feed = fixture(t, { maxEntries: 3, maxTextBytes: 100, maxBytes: 12 });
  for (let index = 0; index < 4; index++) feed.providerEvent(`turn${index}`, 0, message('test'));
  assert.deepEqual(feed.read().map(entry => entry.turnId), ['turn1', 'turn2', 'turn3']);
  feed.providerEvent('turn3', 0, message('more'));
  const entries = feed.read();
  assert.deepEqual(entries.map(entry => entry.turnId), ['turn2', 'turn3']);
  assert.equal(entries.reduce((sum, entry) => sum + Buffer.byteLength(entry.data.text), 0), 12);
});

test('different turns never alias identical provider call ids or tool results', t => {
  const feed = fixture(t);
  feed.providerOutput('first', 0, [call]); feed.toolStarted('first', call); feed.toolFinished('first', call, { ok: true }, 1);
  feed.providerOutput('second', 0, [call]); feed.toolStarted('second', call); feed.toolFinished('second', call, { ok: false, error: 'A check failed' }, 2);
  const entries = feed.read();
  assert.equal(entries.length, 2); assert.notEqual(entries[0].data.entryId, entries[1].data.entryId);
  assert.equal(entries[0].data.status, 'completed'); assert.equal(entries[1].data.status, 'failed');
});

test('terminal lifecycle events settle unfinished rows and preserve real verification failures', t => {
  const feed = fixture(t);
  feed.providerEvent('turn', 0, message('Working')); feed.providerOutput('turn', 0, [call]);
  feed.lifecycle({ id: '1', turnId: 'turn', type: 'tool.failed', title: 'A check needs a correction', data: { tool: 'verify_workspace', checks: [{ name: 'Keep data', ok: false }] } });
  feed.lifecycle({ id: '2', turnId: 'turn', type: 'turn.cancelled', title: 'Change stopped' });
  const entries = feed.read();
  assert.equal(entries.find(entry => entry.data.kind === 'tool').data.status, 'cancelled');
  assert.equal(entries.find(entry => entry.data.kind === 'message').data.status, 'cancelled');
  assert.equal(JSON.parse(entries.find(entry => entry.data.eventType === 'tool.failed').data.result).checks[0].ok, false);
});

test('reset clears pending/replay data and close disposes subscribers and timers idempotently', t => {
  const feed = fixture(t); const observed = []; let closed = 0;
  feed.subscribe(event => observed.push(event), () => closed++);
  feed.providerEvent('turn', 0, message('Old text'));
  feed.lifecycle({ id: '3', type: 'space.updated', title: 'A fresh space', data: { reset: true } }); feed.flush();
  assert.deepEqual(feed.read(), []); assert.deepEqual(observed.map(event => event.type), ['activity.reset']);
  feed.close(); feed.close(); assert.equal(closed, 1);
  feed.providerEvent('turn', 0, message('After close')); feed.flush();
  assert.deepEqual(feed.read(), []); assert.equal(observed.length, 1);
});

test('a disconnected or throwing observer cannot interrupt a build or mutate retained entries', t => {
  const feed = fixture(t);
  const stop = feed.subscribe(() => assert.fail('disconnected observer')); stop();
  feed.subscribe(() => { throw new Error('broken viewer'); });
  feed.subscribe(event => { event.data.text = 'tampered'; });
  feed.providerEvent('turn', 0, message('Original'));
  assert.equal(feed.read()[0].data.text, 'Original');
});

test('streaming adds no persistent writes and cancellation retains accepted requests without late output', async t => {
  const dataDir = await mkdtemp(join(tmpdir(), 'living-activity-persistence-'));
  let entered; const ready = new Promise(resolve => { entered = resolve; });
  let release; const pending = new Promise(resolve => { release = resolve; });
  let streamEvent;
  const service = await createSpaceService({ dataDir, adapter: { keyAvailable: true, model: 'fixture', respond: async ({ onEvent }) => {
    streamEvent = onEvent; entered(); await pending;
    return { output: [{ type: 'function_call', name: 'apply_change', call_id: 'apply', arguments: JSON.stringify({ source: blankSeedSource, tests: blankSeedTests, summary: 'Kept intact' }) }] };
  } } });
  t.after(async () => { release(); await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  const { turnId } = await service.submit('The first request'); await ready;
  const before = await readFile(join(dataDir, 'space.json'), 'utf8');
  for (let index = 0; index < 500; index++) streamEvent(message('x'));
  service.activity.flush();
  assert.equal(await readFile(join(dataDir, 'space.json'), 'utf8'), before);
  await service.submit('Keep the old data too'); await service.cancel();
  streamEvent(message('MUST_NOT_APPEAR')); release(); await service.waitForIdle();
  const entries = service.activity.read();
  assert.ok(entries.some(entry => entry.turnId === turnId && entry.data.kind === 'request' && entry.data.text === 'The first request'));
  assert.ok(entries.some(entry => entry.data.kind === 'request' && entry.data.text === 'Keep the old data too'));
  assert.equal(entries.find(entry => entry.data.kind === 'message').data.status, 'cancelled');
  assert.doesNotMatch(JSON.stringify(entries), /MUST_NOT_APPEAR/); assert.equal(service.store.read().currentRevisionId, 1);
});

test('model rows carry estimated throughput for actual visible deltas, not snapshots or unknown tools', t => {
  let time = 1000, tokenizations = 0;
  const feed = fixture(t, { now: () => time, countTokens: text => { tokenizations++; return text.length; } });
  feed.lifecycle({ id: 'model', turnId: 'turn', type: 'model.started', title: 'Writing', data: { iteration: 1 } });
  const initial = feed.read().find(entry => entry.data.eventType === 'model.started');
  assert.equal(initial.data.throughput.state, 'waiting');
  assert.equal(initial.data.throughput.lastDeltaAt, null);
  assert.equal(tokenizations, 0);
  const custom = { type: 'custom_tool_call', call_id: 'patch-1', name: 'apply_patch', input: '' };
  feed.providerEvent('turn', 0, { type: 'response.output_item.added', output_index: 1, item: custom });
  feed.providerEvent('turn', 0, message('hi'));
  time = 1500;
  feed.providerEvent('turn', 0, { type: 'response.custom_tool_call_input.delta', output_index: 1, delta: 'patch' });
  feed.providerEvent('turn', 0, { type: 'response.function_call_arguments.delta', output_index: 1, delta: 'WRONG_FAMILY' });
  feed.providerEvent('turn', 0, { type: 'response.output_item.added', output_index: 2, item: { ...custom, name: 'shell' } });
  feed.providerEvent('turn', 0, { type: 'response.custom_tool_call_input.delta', output_index: 2, delta: 'UNKNOWN_TOOL' });
  feed.providerEvent('turn', 0, { type: 'response.reasoning_text.delta', output_index: 3, delta: 'PRIVATE' });
  assert.equal(tokenizations, 0, 'ordinary deltas are counted only when the feed flushes');
  const streaming = feed.read().find(entry => entry.data.eventType === 'model.started');
  assert.equal(streaming.data.entryId, initial.data.entryId);
  assert.equal(streaming.time, initial.time);
  assert.deepEqual(streaming.data.throughput, { tokens: 7, durationMs: 500, rate: 14, sampledAt: 1500, lastDeltaAt: 1500, state: 'streaming', estimated: true });
  feed.providerEvent('turn', 0, { type: 'response.output_text.done', output_index: 0, content_index: 0, text: 'hi' });
  feed.providerEvent('turn', 0, { type: 'response.custom_tool_call_input.done', output_index: 1, input: 'patch' });
  feed.providerOutput('turn', 0, [{ type: 'message', content: [{ type: 'output_text', text: 'hi' }] }, { ...custom, input: 'patch' }]);
  time = 1600;
  feed.lifecycle({ id: 'finished', turnId: 'turn', type: 'model.completed', title: 'Written', data: { outputTokens: 9999, reasoningTokens: 7777 } });
  const completed = feed.read().find(entry => entry.data.eventType === 'model.started');
  assert.equal(completed.data.throughput.tokens, 7);
  assert.equal(completed.data.throughput.durationMs, 500);
  assert.equal(completed.data.throughput.rate, 0);
  assert.equal(completed.data.throughput.state, 'complete');
  const callsAfterCompletion = tokenizations;
  time = 4000;
  assert.deepEqual(feed.read().find(entry => entry.data.eventType === 'model.started'), completed, 'replay never recounts old output or refreshes its arrival timestamps');
  assert.equal(tokenizations, callsAfterCompletion);
});

test('throughput is scoped to response iterations and settles on cancellation and failure', t => {
  let time = 1000;
  const feed = fixture(t, { now: () => time, countTokens: text => text.length });
  feed.lifecycle({ id: 'first', turnId: 'turn', type: 'model.started', title: 'First', data: { iteration: 1 } });
  feed.providerEvent('turn', 0, message('first'));
  feed.lifecycle({ id: 'first-done', turnId: 'turn', type: 'model.completed', title: 'Done' });
  time = 2000;
  feed.lifecycle({ id: 'second', turnId: 'turn', type: 'model.started', title: 'Second', data: { iteration: 2 } });
  feed.providerEvent('turn', 1, message('second'));
  feed.lifecycle({ id: 'cancelled', turnId: 'turn', type: 'turn.cancelled', title: 'Stopped' });
  const modelRows = feed.read().filter(entry => entry.data.eventType === 'model.started');
  assert.deepEqual(modelRows.map(entry => [entry.data.throughput.tokens, entry.data.throughput.state]), [[5, 'complete'], [6, 'complete']]);
  feed.lifecycle({ id: 'next', turnId: 'next-turn', type: 'model.started', title: 'Next', data: { iteration: 1 } });
  feed.providerEvent('next-turn', 0, message('next'));
  feed.lifecycle({ id: 'failed', turnId: 'next-turn', type: 'turn.failed', title: 'Failed' });
  assert.equal(feed.read().find(entry => entry.turnId === 'next-turn' && entry.data.eventType === 'model.started').data.throughput.state, 'complete');
});

test('absent or evicted model lifecycle rows cannot add hidden throughput state or extra rows', t => {
  let tokenizations = 0;
  const feed = fixture(t, { maxEntries: 1, countTokens: text => { tokenizations++; return text.length; } });
  feed.providerEvent('without-lifecycle', 0, message('first'));
  assert.equal(feed.read().length, 1);
  feed.lifecycle({ id: 'model', turnId: 'turn', type: 'model.started', title: 'Writing', data: { iteration: 1 } });
  feed.providerEvent('turn', 0, message('evicts-model'));
  const entries = feed.read();
  assert.equal(entries.length, 1);
  assert.equal(entries[0].data.kind, 'message');
  assert.equal(tokenizations, 0);
  assert.equal(entries[0].data.throughput, undefined);
});
