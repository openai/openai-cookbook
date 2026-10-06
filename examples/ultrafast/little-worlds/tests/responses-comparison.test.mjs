import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createResponsesAdapter } from '../server/responses.mjs';
import { createResponsesWebSocket } from '../server/responses-websocket.mjs';

const args = { input: [{ role: 'user', content: 'Build a world' }], tools: [], instructions: 'Fixture', cacheKey: 'same-world' };
const completed = tier => ({ type: 'response.completed', response: { status: 'completed', output: [], service_tier: tier } });
const assertPublicHeaders = headers => {
  assert.equal(headers['OpenAI-Service-Tier'], undefined);
  assert.equal(headers['OpenAI-Beta'], undefined);
};
const httpResponse = (body, headers) => {
  assertPublicHeaders(headers);
  return new Response(`data: ${JSON.stringify(completed(body.service_tier))}\n\n`);
};

test('HTTP comparison selects tiers through the request body without changing other model settings', async t => {
  const sent = [];
  const adapter = createResponsesAdapter({ apiKey: 'test-only', model: 'comparison-model', tier: 'default', maxOutputTokens: 16000,
    fetchImpl: async (_url, request) => {
      const body = JSON.parse(request.body); sent.push({ body, headers: request.headers });
      return httpResponse(body, request.headers);
    } });
  t.after(() => adapter.close());
  await adapter.respond({ ...args, tier: 'ultrafast', timeoutMs: 300000 });
  await adapter.respond({ ...args, tier: 'default', timeoutMs: 300000 });
  assert.equal(sent[0].headers['OpenAI-Service-Tier'], undefined);
  assert.equal(sent[1].headers['OpenAI-Service-Tier'], undefined);
  assert.equal(sent[1].headers.Authorization, sent[0].headers.Authorization, 'Both tiers use the same configured key');
  const { service_tier: fast, ...left } = sent[0].body;
  const { service_tier: normal, ...right } = sent[1].body;
  assert.equal(fast, 'ultrafast'); assert.equal(normal, 'default');
  assert.deepEqual(left, right);
  assert.equal(left.max_output_tokens, 16000);
  assert.deepEqual(left.reasoning, { effort: 'low' });
});

function sockets({ waitMs = 0, rejectUpgrade = false } = {}) {
  return class Socket extends EventEmitter {
    static instances = [];
    constructor(_url, options) {
      super(); this.options = options; this.sent = []; this.readyState = 0;
      Socket.instances.push(this);
      queueMicrotask(() => {
        if (rejectUpgrade) this.emit('unexpected-response', {}, { statusCode: 503, resume() {} });
        else { this.readyState = 1; this.emit('open'); }
      });
    }
    send(raw, callback) {
      const body = JSON.parse(raw); this.sent.push(body); callback?.();
      assertPublicHeaders(this.options.headers);
      const finish = () => this.emit('message', Buffer.from(JSON.stringify(completed(body.service_tier))), false);
      if (waitMs) setTimeout(finish, waitMs); else queueMicrotask(finish);
    }
    terminate() { this.readyState = 3; queueMicrotask(() => this.emit('close')); }
  };
}

test('changing comparison tier opens a separate socket while same-tier requests reuse it', async t => {
  const WebSocketImpl = sockets();
  const adapter = createResponsesAdapter({ apiKey: 'test-only', transport: 'websocket', tier: 'default', WebSocketImpl,
    websocketOptions: { proxyUrl: null } });
  t.after(() => adapter.close());
  await adapter.respond({ ...args, tier: 'ultrafast' });
  await adapter.respond({ ...args, tier: 'ultrafast' });
  await adapter.respond({ ...args, tier: 'default' });
  assert.equal(WebSocketImpl.instances.length, 2);
  assert.equal(WebSocketImpl.instances[0].options.headers['OpenAI-Service-Tier'], undefined);
  assert.equal(WebSocketImpl.instances[0].sent.length, 2);
  assert.ok(WebSocketImpl.instances[0].sent.every(body => body.service_tier === 'ultrafast'));
  assert.equal(WebSocketImpl.instances[0].readyState, 3);
  assert.equal(WebSocketImpl.instances[1].options.headers['OpenAI-Service-Tier'], undefined);
  assert.equal(WebSocketImpl.instances[1].sent[0].service_tier, 'default');
});

test('standard comparison fallback preserves its requested tier in the HTTP body', async t => {
  const WebSocketImpl = sockets({ rejectUpgrade: true });
  const requests = [];
  const adapter = createResponsesAdapter({ apiKey: 'test-only', transport: 'auto', WebSocketImpl,
    websocketOptions: { proxyUrl: null }, fetchImpl: async (_url, request) => {
      const body = JSON.parse(request.body); requests.push({ body, headers: request.headers });
      return httpResponse(body, request.headers);
    } });
  t.after(() => adapter.close());
  const result = await adapter.respond({ ...args, tier: 'default' });
  assert.equal(result.service_tier, 'default');
  assert.equal(result.metrics.transportFallback, true);
  assert.equal(WebSocketImpl.instances[0].options.headers['OpenAI-Service-Tier'], undefined);
  assert.equal(WebSocketImpl.instances[0].sent.length, 0);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].body.service_tier, 'default');
  assert.equal(requests[0].headers['OpenAI-Service-Tier'], undefined);
});

test('configured tiers are selected only through the request body', async t => {
  for (const tier of ['ultrafast', 'default', 'auto', 'priority', 'flex']) {
    const adapter = createResponsesAdapter({ apiKey: 'test-only', tier,
      fetchImpl: async (_url, request) => httpResponse(JSON.parse(request.body), request.headers) });
    t.after(() => adapter.close());
    assert.equal((await adapter.respond(args)).service_tier, tier);
  }
});

test('a comparison request can extend the socket deadline rather than retaining its normal cutoff', async t => {
  const socket = createResponsesWebSocket({ apiKey: 'test-only', tier: 'default', WebSocketImpl: sockets({ waitMs: 30 }),
    proxyUrl: null, responseTimeoutMs: 5 });
  t.after(() => socket.close());
  const result = await socket.respond({ body: { ...args, service_tier: 'default' }, timeoutMs: 250 });
  assert.equal(result.response.status, 'completed');
});

test('resetting an idle comparison connection removes a warm socket while ordinary requests still reuse connections', async t => {
  const WebSocketImpl = sockets();
  const adapter = createResponsesAdapter({ apiKey: 'test-only', transport: 'websocket', WebSocketImpl,
    websocketOptions: { proxyUrl: null } });
  t.after(() => adapter.close());
  await adapter.respond(args);
  await adapter.respond(args);
  assert.equal(WebSocketImpl.instances.length, 1);
  adapter.resetConnection();
  assert.equal(WebSocketImpl.instances[0].readyState, 3);
  await adapter.respond({ ...args, timeoutMs: 300000 });
  assert.equal(WebSocketImpl.instances.length, 2);
  await adapter.respond(args);
  assert.equal(WebSocketImpl.instances.length, 2, 'Resetting does not disable normal connection reuse');
});

test('connection reset cannot interrupt an active model response', async t => {
  const adapter = createResponsesAdapter({ apiKey: 'test-only', transport: 'websocket', WebSocketImpl: sockets({ waitMs: 10 }),
    websocketOptions: { proxyUrl: null } });
  t.after(() => adapter.close());
  const pending = adapter.respond(args);
  assert.throws(() => adapter.resetConnection(), /active model request/);
  assert.equal((await pending).status, 'completed');
});
