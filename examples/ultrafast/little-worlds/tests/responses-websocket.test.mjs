import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';
import { createResponsesAdapter } from '../server/responses.mjs';
import { agentTools } from '../server/harness.mjs';

function fakeSockets({ connect, send } = {}) {
  return class FakeSocket extends EventEmitter {
    static instances = [];
    constructor(url, options) {
      super(); this.url = url; this.options = options; this.readyState = 0; this.sent = []; this.terminated = false;
      FakeSocket.instances.push(this);
      queueMicrotask(() => {
        if (this.terminated) return;
        if (connect) connect(this);
        else { this.readyState = 1; this.emit('open'); }
      });
    }
    send(raw, callback) { this.sent.push(JSON.parse(raw)); callback?.(); send?.(this, this.sent.at(-1)); }
    frame(event) { this.emit('message', Buffer.from(JSON.stringify(event)), false); }
    terminate() { this.terminated = true; this.readyState = 3; queueMicrotask(() => this.emit('close')); }
  };
}
const completed = { type: 'response.completed', response: {
  status: 'completed', output: [], service_tier: 'ultrafast',
  usage: { input_tokens: 1024, output_tokens: 25, input_tokens_details: { cached_tokens: 1000 }, output_tokens_details: { reasoning_tokens: 0 } },
} };
const args = { input: [{ role: 'user', content: 'Make it blue' }], instructions: 'Test', tools: [], cacheKey: 'little-worlds:test-thread' };
function adapter(t, WebSocketImpl, options = {}) {
  const instance = createResponsesAdapter({ apiKey: 'test-only', transport: 'auto', WebSocketImpl, websocketOptions: { proxyUrl: null, ...options.websocketOptions }, ...options });
  t.after(() => instance.close());
  return instance;
}

test('WebSocket round-trips native custom patches and replays their outputs unchanged', async t => {
  const input = '*** Begin Patch\n*** Update File: space.js\n@@\n-red\n+blue\n*** End Patch\n';
  const call = { type: 'custom_tool_call', id: 'ctc-ws', call_id: 'patch-ws', name: 'apply_patch', input };
  const events = [
    { type: 'response.output_item.added', output_index: 0, item: { ...call, input: '' } },
    { type: 'response.custom_tool_call_input.delta', output_index: 0, delta: input },
    { type: 'response.custom_tool_call_input.done', output_index: 0, input },
    { type: 'response.completed', response: { status: 'completed', output: [call] } },
  ];
  const WebSocketImpl = fakeSockets({ send(socket) { for (const event of events) socket.frame(event); } });
  const instance = adapter(t, WebSocketImpl);
  const received = [];
  const first = await instance.respond({ ...args, tools: agentTools, onEvent: event => received.push(event) });
  const history = [...args.input, ...first.output, { type: 'custom_tool_call_output', call_id: call.call_id, output: '{"ok":true}' }];
  await instance.respond({ ...args, tools: agentTools, input: history });
  const socket = WebSocketImpl.instances[0];
  assert.equal(WebSocketImpl.instances.length, 1);
  assert.deepEqual(received, events);
  assert.deepEqual(socket.sent[1].input, history);
  assert.deepEqual(socket.sent[0].tools, agentTools);
  assert.equal(socket.sent[0].tools.find(tool => tool.name === 'apply_patch').type, 'custom');
});

test('persistent WebSocket sends full independent input and waits for ordered progress callbacks', async t => {
  const WebSocketImpl = fakeSockets({ send(socket) {
    socket.frame({ type: 'response.custom_tool_call_input.delta', delta: 'patch' }); socket.frame(completed);
  } });
  const instance = adapter(t, WebSocketImpl, { maxOutputTokens: 16000 });
  const order = [];
  const first = await instance.respond({ ...args, onEvent: async event => {
    if (event.type.endsWith('.delta')) { await delay(5); order.push('delta'); }
    else order.push('completed');
  } });
  const secondInput = [...args.input, { role: 'user', content: 'Now green' }];
  const second = await instance.respond({ ...args, input: secondInput });
  assert.deepEqual(order, ['delta', 'completed']);
  assert.equal(WebSocketImpl.instances.length, 1);
  const socket = WebSocketImpl.instances[0];
  assert.equal(socket.options.headers.Authorization, 'Bearer test-only');
  assert.equal(socket.options.headers['OpenAI-Service-Tier'], undefined);
  assert.equal(socket.options.headers['OpenAI-Beta'], undefined);
  assert.equal(socket.sent[0].type, 'response.create');
  assert.equal(socket.sent[0].service_tier, 'ultrafast');
  assert.equal(socket.sent[0].stream, undefined);
  assert.equal(socket.sent[0].previous_response_id, undefined);
  assert.equal(socket.sent[0].store, false);
  assert.equal(socket.sent[0].max_output_tokens, 16000);
  assert.equal(socket.sent[0].prompt_cache_key, args.cacheKey);
  assert.deepEqual(socket.sent[1].input, secondInput);
  assert.equal(first.metrics.transport, 'websocket');
  assert.equal(first.metrics.connectionReused, false);
  assert.equal(second.metrics.connectionReused, true);
  assert.equal(second.metrics.cachedInputTokens, 1000);
  assert.equal(second.metrics.reasoningTokens, 0);
  assert.ok(first.metrics.ttftMs >= 0);
});

test('upgrade failure falls back before sending and avoids repeated failed upgrades', async t => {
  let httpCalls = 0;
  const WebSocketImpl = fakeSockets({ connect(socket) { socket.emit('unexpected-response', {}, { statusCode: 403, resume() {} }); } });
  const instance = adapter(t, WebSocketImpl, { fetchImpl: async () => { httpCalls++; return new Response(`data: ${JSON.stringify(completed)}\n\n`); } });
  const result = await instance.respond(args);
  await instance.respond(args);
  assert.equal(result.metrics.transport, 'http'); assert.equal(result.metrics.transportFallback, true);
  assert.equal(httpCalls, 2); assert.equal(WebSocketImpl.instances.length, 1);
  assert.equal(WebSocketImpl.instances[0].sent.length, 0); assert.equal(WebSocketImpl.instances[0].terminated, true);
});

test('errors after send are never replayed over HTTP; the next request reconnects', async t => {
  let httpCalls = 0, attempts = 0;
  const WebSocketImpl = fakeSockets({ send(socket) {
    if (++attempts === 1) socket.frame({ type: 'response.failed', response: { error: { message: 'Failed sk-privateTEST' } } });
    else socket.frame(completed);
  } });
  const instance = adapter(t, WebSocketImpl, { fetchImpl: async () => { httpCalls++; return new Response(); } });
  await assert.rejects(instance.respond(args), /Failed \[redacted\]/);
  const result = await instance.respond(args);
  assert.equal(result.metrics.transport, 'websocket');
  assert.equal(httpCalls, 0); assert.equal(WebSocketImpl.instances.length, 2);
  assert.equal(WebSocketImpl.instances[0].terminated, true);
});

test('aborting during streamed output closes the connection without retrying', async t => {
  let httpCalls = 0;
  const controller = new AbortController();
  const WebSocketImpl = fakeSockets({ send(socket) { socket.frame({ type: 'response.output_text.delta', delta: 'hello' }); socket.frame(completed); } });
  const instance = adapter(t, WebSocketImpl, { fetchImpl: async () => { httpCalls++; return new Response(); } });
  await assert.rejects(instance.respond({ ...args, signal: controller.signal, onEvent: event => {
    if (event.type.endsWith('.delta')) controller.abort(new Error('Stop this request'));
  } }), /Stop this request/);
  assert.equal(httpCalls, 0); assert.equal(WebSocketImpl.instances[0].terminated, true);
});

test('a concurrent request cannot replace or share the pending space request', async t => {
  const WebSocketImpl = fakeSockets();
  const instance = adapter(t, WebSocketImpl);
  const first = instance.respond(args);
  await delay(0);
  await assert.rejects(instance.respond({ ...args, cacheKey: 'different-space' }), /already running/);
  assert.equal(WebSocketImpl.instances.length, 1);
  WebSocketImpl.instances[0].frame(completed);
  await first;
});

test('idle sockets close and a subsequent request opens a fresh connection', async t => {
  const WebSocketImpl = fakeSockets({ send(socket) { socket.frame(completed); } });
  const instance = adapter(t, WebSocketImpl, { websocketOptions: { proxyUrl: null, idleTimeoutMs: 10 } });
  await instance.respond(args);
  await delay(35);
  assert.equal(WebSocketImpl.instances[0].terminated, true);
  const result = await instance.respond(args);
  assert.equal(WebSocketImpl.instances.length, 2); assert.equal(result.metrics.connectionReused, false);
});

test('a stalled response times out and is not resent over HTTP', async t => {
  let httpCalls = 0;
  const WebSocketImpl = fakeSockets();
  const instance = adapter(t, WebSocketImpl, { websocketOptions: { proxyUrl: null, responseTimeoutMs: 10 }, fetchImpl: async () => { httpCalls++; return new Response(); } });
  await assert.rejects(instance.respond(args), /request timed out/);
  assert.equal(httpCalls, 0); assert.equal(WebSocketImpl.instances[0].terminated, true);
});

test('a stalled handshake can fall back before any request is sent', async t => {
  const WebSocketImpl = fakeSockets({ connect() {} });
  const instance = adapter(t, WebSocketImpl, { websocketOptions: { proxyUrl: null, handshakeTimeoutMs: 10 }, fetchImpl: async () => new Response(`data: ${JSON.stringify(completed)}\n\n`) });
  const result = await instance.respond(args);
  assert.equal(result.metrics.transportFallback, true); assert.equal(WebSocketImpl.instances[0].sent.length, 0);
});

test('injected fetch defaults to HTTP without constructing a WebSocket', async t => {
  const instance = createResponsesAdapter({ apiKey: 'test-only', WebSocketImpl: class { constructor() { throw new Error('Must not construct'); } }, fetchImpl: async () => new Response(`data: ${JSON.stringify(completed)}\n\n`) });
  t.after(() => instance.close());
  assert.equal((await instance.respond(args)).metrics.transport, 'http');
});

test('the configured HTTPS proxy is passed only to the socket client', async t => {
  const WebSocketImpl = fakeSockets({ send(socket) { socket.frame(completed); } });
  const instance = adapter(t, WebSocketImpl, { websocketOptions: { proxyUrl: 'http://127.0.0.1:8080' } });
  await instance.respond(args);
  assert.equal(WebSocketImpl.instances[0].options.agent.constructor.name, 'HttpsProxyAgent');
  assert.equal(WebSocketImpl.instances[0].sent[0].proxy, undefined);
});
