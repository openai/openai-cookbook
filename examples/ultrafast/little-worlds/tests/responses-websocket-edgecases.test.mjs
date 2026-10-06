import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { setImmediate as nextTurn } from 'node:timers/promises';
import { createResponsesWebSocket } from '../server/responses-websocket.mjs';
import { createResponsesAdapter } from '../server/responses.mjs';

function fakeSockets() {
  const sockets = [];
  class FakeSocket extends EventEmitter {
    constructor(url, options) {
      super();
      this.url = url;
      this.options = options;
      this.readyState = 0;
      this.sent = [];
      this.terminations = 0;
      sockets.push(this);
    }
    open() { this.readyState = 1; this.emit('open'); }
    send(payload, callback) { this.sent.push(JSON.parse(payload)); callback?.(); }
    frame(event) { this.emit('message', Buffer.from(JSON.stringify(event)), false); }
    end() { this.readyState = 3; this.emit('close'); }
    terminate() {
      this.terminations++;
      if (this.readyState !== 3) this.end();
    }
  }
  return { sockets, FakeSocket };
}

const completed = (id = 'test-response') => ({ type: 'response.completed', response: { id, status: 'completed', output: [] } });
const body = { model: 'test', input: [{ role: 'user', content: 'Test' }], stream: true, store: false };
const request = (cacheKey = 'space-one') => ({ input: body.input, instructions: 'Test', tools: [], cacheKey });

function rawTransport(t, options = {}) {
  const { sockets, FakeSocket } = fakeSockets();
  const adapter = createResponsesWebSocket({ apiKey: 'test-only', tier: 'ultrafast', WebSocketImpl: FakeSocket, proxyUrl: null, ...options });
  t.after(() => adapter.close());
  return { adapter, sockets };
}

test('an already aborted WebSocket request opens no connection', async t => {
  const { adapter, sockets } = rawTransport(t);
  const controller = new AbortController();
  controller.abort(new Error('Test cancelled'));
  await assert.rejects(adapter.respond({ body, signal: controller.signal }), /Test cancelled/);
  assert.equal(sockets.length, 0);
});

test('aborting during the upgrade tears down the pending socket and its request listeners', async t => {
  const { adapter, sockets } = rawTransport(t);
  const controller = new AbortController();
  const pending = adapter.respond({ body, signal: controller.signal });
  const rejected = assert.rejects(pending, /Test cancelled/);
  const socket = sockets[0];
  controller.abort(new Error('Test cancelled'));
  await rejected;
  assert.equal(socket.terminations, 1);
  assert.equal(socket.sent.length, 0);
  assert.equal(socket.listenerCount('open'), 0);
  assert.equal(socket.listenerCount('unexpected-response'), 0);
  assert.equal(socket.listenerCount('message'), 0);
  assert.equal(socket.listenerCount('error'), 1, 'Only the defensive post-termination error listener remains.');
  assert.equal(socket.listenerCount('close'), 1, 'Only the connection reference cleanup listener remains.');
});

test('closing the adapter during upgrade rejects without falling back to HTTP', async t => {
  const { sockets, FakeSocket } = fakeSockets();
  let httpCalls = 0;
  const adapter = createResponsesAdapter({ apiKey: 'test-only', transport: 'auto', WebSocketImpl: FakeSocket, websocketOptions: { proxyUrl: null }, fetchImpl: async () => { httpCalls++; throw new Error('Unexpected HTTP'); } });
  t.after(() => adapter.close());
  const pending = adapter.respond(request());
  const rejected = assert.rejects(pending, /adapter was closed/);
  adapter.close();
  await rejected;
  assert.equal(sockets[0].sent.length, 0);
  assert.equal(sockets[0].readyState, 3);
  assert.equal(httpCalls, 0);
  await assert.rejects(adapter.respond(request()), /adapter was closed/);
});

test('a completion followed by a peer close still waits for the final asynchronous callback', async t => {
  const { adapter, sockets } = rawTransport(t);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const events = [];
  let finished = false;
  const pending = adapter.respond({ body, onEvent: async event => { events.push(event.type); await gate; } });
  pending.then(() => { finished = true; });
  const socket = sockets[0];
  socket.open();
  await nextTurn();
  socket.frame(completed());
  socket.end();
  await nextTurn();
  assert.equal(finished, false);
  release();
  const result = await pending;
  assert.equal(result.response.id, 'test-response');
  assert.deepEqual(events, ['response.completed']);
  assert.equal(socket.listenerCount('message'), 0);
});

test('a failed progress callback rejects the request without replaying it over HTTP', async t => {
  const { sockets, FakeSocket } = fakeSockets();
  let httpCalls = 0;
  const adapter = createResponsesAdapter({ apiKey: 'test-only', transport: 'auto', WebSocketImpl: FakeSocket, websocketOptions: { proxyUrl: null }, fetchImpl: async () => { httpCalls++; throw new Error('Unexpected HTTP'); } });
  t.after(() => adapter.close());
  const seen = [];
  const pending = adapter.respond({ ...request(), onEvent: event => { seen.push(event.type); throw new Error('Preview callback failed'); } });
  const rejected = assert.rejects(pending, /Preview callback failed/);
  const socket = sockets[0];
  socket.open();
  await nextTurn();
  socket.frame({ type: 'response.output_text.delta', delta: 'partial' });
  socket.frame(completed());
  await rejected;
  await nextTurn();
  assert.deepEqual(seen, ['response.output_text.delta']);
  assert.equal(socket.sent.length, 1);
  assert.equal(socket.readyState, 3);
  assert.equal(httpCalls, 0);
});

test('a stalled callback cannot prevent timeout and queued frames stay discarded afterward', async t => {
  const { adapter, sockets } = rawTransport(t, { responseTimeoutMs: 100 });
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  t.after(() => release());
  const seen = [];
  const pending = adapter.respond({ body, onEvent: async event => { seen.push(event.type); await gate; } });
  const rejected = assert.rejects(pending, /request timed out/);
  const socket = sockets[0];
  socket.open();
  await nextTurn();
  socket.frame({ type: 'response.output_text.delta', delta: 'partial' });
  socket.frame(completed());
  await rejected;
  release();
  await nextTurn();
  assert.deepEqual(seen, ['response.output_text.delta']);
  assert.equal(socket.readyState, 3);
  assert.equal(socket.listenerCount('message'), 0);
});

test('changing space affinity creates a fresh connection while overlapping requests cannot steal it', async t => {
  const { sockets, FakeSocket } = fakeSockets();
  const adapter = createResponsesAdapter({ apiKey: 'test-only', transport: 'auto', WebSocketImpl: FakeSocket, websocketOptions: { proxyUrl: null } });
  t.after(() => adapter.close());
  const first = adapter.respond(request('space-one'));
  sockets[0].open();
  await nextTurn();
  await assert.rejects(adapter.respond(request('space-two')), /already running/);
  assert.equal(sockets.length, 1);
  assert.equal(sockets[0].readyState, 1);
  sockets[0].frame(completed('first'));
  await first;
  const secondInput = [{ role: 'user', content: 'Different owner, different input' }];
  const second = adapter.respond({ ...request('space-two'), input: secondInput });
  assert.equal(sockets[0].readyState, 3);
  assert.equal(sockets.length, 2);
  sockets[1].open();
  await nextTurn();
  assert.deepEqual(sockets[1].sent[0].input, secondInput);
  assert.equal(sockets[1].sent[0].prompt_cache_key, 'space-two');
  assert.equal(sockets[1].sent[0].previous_response_id, undefined);
  sockets[1].frame(completed('second'));
  const result = await second;
  assert.equal(result.id, 'second');
  assert.equal(result.metrics.connectionReused, false);
});

test('auto transport keeps unaffiliated concurrent services on independent HTTP requests', async t => {
  const { sockets, FakeSocket } = fakeSockets();
  const inputs = [];
  const adapter = createResponsesAdapter({ apiKey: 'test-only', transport: 'auto', WebSocketImpl: FakeSocket, websocketOptions: { proxyUrl: null }, fetchImpl: async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    await nextTurn();
    return new Response(`data: ${JSON.stringify(completed())}\n\n`);
  } });
  t.after(() => adapter.close());
  const first = [{ role: 'user', content: 'Viewer one' }];
  const second = [{ role: 'user', content: 'Viewer two' }];
  const results = await Promise.all([adapter.respond({ input: first }), adapter.respond({ input: second })]);
  assert.deepEqual(inputs, [first, second]);
  assert.equal(sockets.length, 0);
  assert.ok(results.every(result => result.metrics.transport === 'http'));
});

test('closing the adapter also aborts a pending HTTP request', async t => {
  const adapter = createResponsesAdapter({ apiKey: 'test-only', fetchImpl: async (_url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
  }) });
  t.after(() => adapter.close());
  const pending = adapter.respond(request());
  const rejected = assert.rejects(pending, /adapter was closed/);
  adapter.close();
  await rejected;
});
