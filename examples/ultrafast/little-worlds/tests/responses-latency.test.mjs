import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createResponsesAdapter } from '../server/responses.mjs';
import { agentTools, createSpaceService } from '../server/harness.mjs';
import { createSpaceAgent } from '../server/space-agent.mjs';

const eventBlock = event => `data: ${JSON.stringify(event)}\n\n`;
const encodeEvents = events => new TextEncoder().encode(events.map(eventBlock).join(''));
const complete = output => ({ type: 'response.completed', response: { status: 'completed', output } });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

test('HTTP finishes on the terminal event without waiting for EOF or transport cancellation', { timeout: 5000 }, async t => {
  let cancelled = 0;
  const events = [{ type: 'response.output_text.delta', delta: 'Done.' }, complete([])];
  const received = [];
  const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async () => new Response(new ReadableStream({
    start(controller) { controller.enqueue(encodeEvents(events)); },
    cancel() { cancelled++; return new Promise(() => {}); },
  })) });
  t.after(() => adapter.close());
  const result = await adapter.respond({ input: [], tools: [], onEvent: event => received.push(event) });
  assert.equal(result.status, 'completed');
  assert.deepEqual(received, events);
  assert.equal(cancelled, 1, 'release the body even when its cancellation cannot finish');
});

test('completed HTTP tool calls advance through painting batches while their sockets remain open', { timeout: 5000 }, async t => {
  const action = { name: 'paint', description: 'Paint one cell.', parameters: {
    type: 'object', properties: { cell: { type: 'integer', minimum: 0, maximum: 100 } }, required: ['cell'], additionalProperties: false,
  } };
  const saved = { currentRevisionId: 1, revisions: [{ id: 1, meta: { title: 'Canvas', capabilities: ['space-agent'], agent: { instructions: 'Paint the requested cells.', actions: [action] } } }], state: { extras: {} } };
  const applied = [], requests = [];
  let cancelled = 0;
  const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async (_url, request) => {
    requests.push(JSON.parse(request.body));
    const round = requests.length;
    const output = round < 3
      ? [{ type: 'function_call', name: 'paint', call_id: `paint-${round}`, arguments: JSON.stringify({ cell: round }) }]
      : [{ type: 'message', content: [{ type: 'output_text', text: 'Painted both cells.' }] }];
    return new Response(new ReadableStream({
      start(controller) { controller.enqueue(encodeEvents([complete(output)])); },
      cancel() { cancelled++; return new Promise(() => {}); },
    }));
  } });
  const runtime = createSpaceAgent({ adapter });
  t.after(() => runtime.close());
  const result = await runtime.run({
    service: { owner: { id: 'iris' }, store: { read: () => structuredClone(saved) }, action: async args => { applied.push(args.action); } },
    actorId: 'iris', revisionId: 1, messages: [{ role: 'user', content: 'Paint cells one and two.' }],
  });
  assert.deepEqual(applied, [{ cell: 1, type: 'paint' }, { cell: 2, type: 'paint' }]);
  assert.equal(result.actionsApplied, 2);
  assert.equal(result.text, 'Painted both cells.');
  assert.equal(requests.length, 3);
  assert.equal(cancelled, 3);
  assert.equal(requests[1].input.at(-1).type, 'function_call_output');
});

test('a nonterminal event leaves HTTP inference pending until confirmed completion', { timeout: 5000 }, async t => {
  let streamController, settled = false;
  const received = deferred();
  const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async () => new Response(new ReadableStream({
    start(controller) { streamController = controller; controller.enqueue(encodeEvents([{ type: 'response.output_text.delta', delta: 'Still working.' }])); },
  })) });
  t.after(() => adapter.close());
  const pending = adapter.respond({ input: [], tools: [], onEvent: () => received.resolve() }).finally(() => { settled = true; });
  await received.promise;
  assert.equal(settled, false);
  streamController.enqueue(encodeEvents([complete([])]));
  assert.equal((await pending).status, 'completed');
});

test('HTTP abort interrupts a silent read even if the mocked transport ignores the request signal', { timeout: 5000 }, async t => {
  let cancelled = 0;
  const started = deferred();
  const controller = new AbortController();
  const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async () => new Response(new ReadableStream({
    start() { started.resolve(); },
    cancel() { cancelled++; return new Promise(() => {}); },
  })) });
  t.after(() => adapter.close());
  const pending = adapter.respond({ input: [], tools: [], signal: controller.signal });
  await started.promise;
  await new Promise(resolve => setImmediate(resolve));
  const reason = new DOMException('Stopped painting.', 'AbortError');
  controller.abort(reason);
  await assert.rejects(pending, error => error === reason);
  assert.equal(cancelled, 1);
});

test('HTTP errors, incomplete output, invalid completion and truncated streams remain failures', async t => {
  const cases = [
    ['provider error', [{ type: 'error', message: 'Provider failed.' }], /Provider failed/],
    ['failed response', [{ type: 'response.failed', response: { error: { message: 'Inference failed.' } } }], /Inference failed/],
    ['incomplete response', [{ type: 'response.incomplete' }], /output limit/],
    ['invalid completion', [{ type: 'response.completed', response: { status: 'in_progress' } }], /invalid completed response/],
    ['missing completion payload', [{ type: 'response.completed' }], /invalid completed response/],
    ['truncated stream', [{ type: 'response.output_text.delta', delta: 'Partial' }], /connection ended before the model finished/],
  ];
  for (const [name, events, expected] of cases) await t.test(name, async t => {
    const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async () => new Response(encodeEvents(events)) });
    t.after(() => adapter.close());
    await assert.rejects(adapter.respond({ input: [], tools: [] }), expected);
  });
});

test('HTTP preserves Codex custom grammar, streamed input, and native tool history', async t => {
  const input = '*** Begin Patch\n*** Add File: space.js\n+export const answer = 42;\n*** End Patch\n';
  const call = { type: 'custom_tool_call', id: 'ctc-http', call_id: 'patch-http', name: 'apply_patch', input };
  const history = [{ ...call }, { type: 'custom_tool_call_output', call_id: call.call_id, output: '{"ok":true}' }];
  let body;
  const events = [
    { type: 'response.output_item.added', output_index: 0, item: { ...call, input: '' } },
    { type: 'response.custom_tool_call_input.delta', output_index: 0, delta: input },
    { type: 'response.custom_tool_call_input.done', output_index: 0, input },
    { type: 'response.completed', response: { status: 'completed', output: [call] } },
  ];
  const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async (_url, request) => {
    body = JSON.parse(request.body);
    return new Response(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''));
  } });
  t.after(() => adapter.close());
  const received = [];
  const result = await adapter.respond({ input: history, tools: agentTools, onEvent: event => received.push(event) });
  assert.deepEqual(body.input, history);
  const patch = body.tools.find(tool => tool.name === 'apply_patch');
  assert.equal(patch.type, 'custom');
  assert.equal(patch.format.type, 'grammar');
  assert.equal(patch.format.syntax, 'lark');
  assert.match(patch.format.definition, /\*\*\* Begin Patch/);
  assert.deepEqual(received, events);
  assert.deepEqual(result.output, [call]);
  assert.ok(result.metrics.ttftMs >= 0);
});

test('Responses sends stable cache affinity and reports actual cached and reasoning tokens', async () => {
  let body;
  const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async (_url, request) => {
    body = JSON.parse(request.body);
    return new Response(`data: ${JSON.stringify({ type: 'response.completed', response: {
      status: 'completed', output: [], service_tier: 'ultrafast',
      usage: { input_tokens: 8400, output_tokens: 153, input_tokens_details: { cached_tokens: 8192 }, output_tokens_details: { reasoning_tokens: 0 } },
    } })}\n\n`, { status: 200 });
  } });
  const result = await adapter.respond({ input: [], instructions: 'Test', tools: [], signal: new AbortController().signal, cacheKey: 'little-worlds:opaque-test-session' });
  assert.equal(body.prompt_cache_key, 'little-worlds:opaque-test-session');
  assert.equal(body.store, false);
  assert.equal(body.parallel_tool_calls, false);
  assert.equal(body.reasoning.effort, 'low');
  assert.equal(body.max_output_tokens, 6000);
  assert.equal(result.metrics.cachedInputTokens, 8192);
  assert.equal(result.metrics.reasoningTokens, 0);
  assert.equal(result.metrics.servedTier, 'ultrafast');
  assert.ok(result.metrics.headersMs >= 0);
});

test('a builder can request complete game source and tests without increasing chat-service budgets', async t => {
  let body;
  const adapter = createResponsesAdapter({ apiKey: 'test-only', maxOutputTokens: 16000, fetchImpl: async (_url, request) => {
    body = JSON.parse(request.body);
    return new Response(`data: ${JSON.stringify({ type: 'response.completed', response: { status: 'completed', output: [] } })}\n\n`);
  } });
  t.after(() => adapter.close());
  await adapter.respond({ input: [], tools: [], instructions: 'Build a game' });
  assert.equal(body.max_output_tokens, 16000);
  assert.equal(body.model, 'gpt-6-astra');
  assert.equal(body.service_tier, 'ultrafast');
  assert.equal(body.reasoning.effort, 'low');
  for (const invalid of [0, 16000.5, 32001, NaN]) {
    assert.throws(() => createResponsesAdapter({ maxOutputTokens: invalid }), /maxOutputTokens/);
  }
});

test('missing usage details remain unknown rather than looking like measured cache misses', async () => {
  const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async () => new Response(`data: ${JSON.stringify({ type: 'response.completed', response: { status: 'completed', output: [] } })}\n\n`) });
  const result = await adapter.respond({ input: [], tools: [], signal: new AbortController().signal });
  assert.equal(result.metrics.cachedInputTokens, null);
  assert.equal(result.metrics.reasoningTokens, null);
});

test('cache affinity survives a server restart and changes when the space gets a fresh session', async t => {
  const dataDir = await mkdtemp(join(tmpdir(), 'living-cache-test-'));
  const keys = [];
  let calls = 0;
  const adapter = { keyAvailable: true, respond: async ({ cacheKey }) => {
    keys.push(cacheKey);
    calls++;
    const before = calls === 2 ? '#123456' : '#687957';
    return { output: [{ type: 'function_call', name: 'apply_patch', call_id: `cache-${calls}`, arguments: JSON.stringify({ edits: [{ path: 'space.js', search: before, replace: calls === 2 ? '#345678' : '#123456' }], summary: 'Test accent' }) }] };
  } };
  let service = await createSpaceService({ dataDir, adapter });
  t.after(async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  await service.submit('Change the accent'); await service.waitForIdle();
  await service.close();
  service = await createSpaceService({ dataDir, adapter });
  await service.submit('Change it again'); await service.waitForIdle();
  assert.equal(service.store.read().session.lastOutcome, 'completed');
  assert.match(keys[0], /^little-worlds:[0-9a-f-]+$/);
  assert.equal(keys[0], keys[1]);
  await service.reset();
  await service.submit('Change the accent'); await service.waitForIdle();
  assert.notEqual(keys[2], keys[0]);
});
