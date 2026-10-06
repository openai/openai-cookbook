import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const compiled = await build({ entryPoints: [new URL('../src/api.ts', import.meta.url).pathname], bundle: true, write: false, format: 'esm' });
const { api, setSessionToken, watchEvents } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const encoder = new TextEncoder();
const settle = () => new Promise(resolve => setImmediate(resolve));
function globalFixture(t, name, value) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
  t.after(() => { if (previous) Object.defineProperty(globalThis, name, previous); else delete globalThis[name]; });
}
function timersFixture(t) {
  const timers = new Map(); let serial = 0;
  t.mock.method(globalThis, 'setTimeout', (callback, delay) => { const id = ++serial; timers.set(id, { callback, delay }); return id; });
  t.mock.method(globalThis, 'clearTimeout', id => timers.delete(id));
  return { timers, run(delay) {
    const found = [...timers].find(([, value]) => value.delay === delay);
    assert.ok(found, `Expected a ${delay}ms timer`);
    timers.delete(found[0]); found[1].callback();
  } };
}

test('SSE batches replay, handles split UTF-8/CRLF, and reconnects after the last valid event', async t => {
  const first = { id: '1', type: 'turn.started', title: 'Mira’s space 🌱' };
  const second = { id: '2', type: 'draft.preview', title: 'A new page' };
  const third = { id: '3', type: 'revision.published', title: 'Ready' };
  const text = `: connected\r\n\r\nid: 1\r\ndata: ${JSON.stringify(first)}\r\n\r\nid: 2\r\ndata: ${JSON.stringify(second)}\r\n\r\nid: 99\ndata: invalid json\n\n`;
  const bytes = encoder.encode(text);
  const split = bytes.indexOf(0xf0) + 2;
  const requests = []; const batches = []; const connections = [];
  let reconnect; let disconnected; let received;
  const ended = new Promise(resolve => { disconnected = resolve; });
  const resumed = new Promise(resolve => { received = resolve; });
  t.mock.method(globalThis, 'setTimeout', callback => { reconnect = callback; return 1; });
  t.mock.method(globalThis, 'clearTimeout', () => {});
  t.mock.method(globalThis, 'fetch', async (_url, init) => {
    requests.push(init);
    return new Response(new ReadableStream({ start(controller) {
      if (requests.length === 1) {
        controller.enqueue(bytes.slice(0, split));
        controller.enqueue(bytes.slice(split));
        controller.close();
      } else {
        controller.enqueue(encoder.encode(`id: 3\ndata: ${JSON.stringify(third)}\n\n`));
        init.signal.addEventListener('abort', () => controller.error(new Error('aborted')), { once: true });
      }
    } }));
  });
  setSessionToken('test-session');
  const stop = watchEvents('/test/events', events => { batches.push(events); if (events.some(event => event.id === '3')) received(); }, connected => { connections.push(connected); if (!connected) disconnected(); }, () => assert.fail('not expired'));
  t.after(() => { stop(); setSessionToken(null); });
  await ended;
  assert.deepEqual(batches, [[first, second]], 'the replay batch updates the UI once');
  assert.deepEqual(connections, [true, false]);
  setSessionToken('a-different-account');
  reconnect(); await resumed;
  assert.equal(requests[1].headers['Last-Event-ID'], '2');
  assert.equal(requests[1].headers.Authorization, 'Bearer test-session', 'an existing stream must not adopt another account on reconnect');
  assert.deepEqual(batches[1], [third]);
  assert.deepEqual(connections, [true, false, true]);
});

test('hidden tabs release streams and resume from their cursor with the original identity', async t => {
  const document = new EventTarget(); document.hidden = true;
  globalFixture(t, 'document', document);
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (_path, init) => {
    requests.push(init);
    return new Response(new ReadableStream({ start(controller) {
      controller.enqueue(encoder.encode(`id: ${requests.length}\ndata: ${JSON.stringify({ id: String(requests.length), type: 'draft.preview' })}\n\n`));
      init.signal.addEventListener('abort', () => controller.error(new Error('aborted')), { once: true });
    } }));
  });
  setSessionToken('owner-before-navigation');
  const events = [];
  const stop = watchEvents('/test/events', batch => events.push(...batch), () => {}, () => assert.fail('not expired'));
  t.after(() => { stop(); setSessionToken(null); });
  await settle();
  assert.equal(requests.length, 0, 'Background tabs must not reserve HTTP connections');
  document.hidden = false; document.dispatchEvent(new Event('visibilitychange'));
  await settle();
  assert.equal(events.length, 1);
  document.hidden = true; document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(requests[0].signal.aborted, true);
  setSessionToken('newly-selected-account');
  document.hidden = false; document.dispatchEvent(new Event('visibilitychange'));
  await settle();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].headers['Last-Event-ID'], '1');
  assert.equal(requests[1].headers.Authorization, 'Bearer owner-before-navigation');
  assert.deepEqual(events.map(event => event.id), ['1', '2']);
  stop();
  document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(requests.length, 2, 'Unmounted subscriptions never resume');
});

test('a queued Finish request borrows stream connections without replaying the mutation or losing stream cursors', async t => {
  const timers = timersFixture(t);
  let open = 0; let finishCalls = 0; let queued;
  const streamRequests = [];
  t.mock.method(globalThis, 'fetch', (path, init) => {
    if (path === '/test/finish') {
      finishCalls++;
      assert.equal(open, 6, 'The test starts with the entire HTTP/1 pool occupied');
      return new Promise(resolve => { queued = () => resolve(Response.json({ ok: true })); });
    }
    open++; streamRequests.push(init);
    return Promise.resolve(new Response(new ReadableStream({ start(controller) {
      controller.enqueue(encoder.encode('id: 7\ndata: {"id":"7","type":"draft.preview"}\n\n'));
      init.signal.addEventListener('abort', () => {
        open--; controller.error(new Error('aborted'));
        queued?.(); queued = null;
      }, { once: true });
    } })));
  });
  const stops = Array.from({ length: 6 }, (_, i) => watchEvents(`/test/${i}/events`, () => {}, () => {}, () => assert.fail('not expired')));
  t.after(() => stops.forEach(stop => stop()));
  await settle();
  const finish = api('/test/finish', {});
  timers.run(500);
  assert.deepEqual(await finish, { ok: true });
  assert.equal(finishCalls, 1, 'The queued POST is allowed through, never resent');
  assert.equal(open, 0);
  timers.run(1000);
  await settle();
  assert.equal(open, 6);
  assert.equal(streamRequests.length, 12);
  assert.ok(streamRequests.slice(6).every(request => request.headers['Last-Event-ID'] === '7'));
});

test('fast API responses do not interrupt real-time streams', async t => {
  const { timers } = timersFixture(t);
  let streamSignal;
  t.mock.method(globalThis, 'fetch', async (path, init) => {
    if (path === '/test/snapshot') return Response.json({ revision: 2 });
    streamSignal = init.signal;
    return new Response(new ReadableStream({ start(controller) {
      init.signal.addEventListener('abort', () => controller.error(new Error('aborted')), { once: true });
    } }));
  });
  const stop = watchEvents('/test/events', () => {}, () => {}, () => {});
  t.after(stop);
  await settle();
  assert.deepEqual(await api('/test/snapshot'), { revision: 2 });
  assert.equal(streamSignal.aborted, false);
  assert.equal(timers.size, 0);
});

test('a request in another visible window can release origin-wide stream slots without sharing credentials', async t => {
  const timers = timersFixture(t);
  globalFixture(t, 'window', {});
  const channels = [];
  globalFixture(t, 'BroadcastChannel', class {
    constructor(name) { this.name = name; this.closed = false; channels.push(this); }
    close() { this.closed = true; }
  });
  const signals = [];
  t.mock.method(globalThis, 'fetch', async (_path, init) => {
    signals.push(init.signal);
    return new Response(new ReadableStream({ start(controller) {
      init.signal.addEventListener('abort', () => controller.error(new Error('aborted')), { once: true });
    } }));
  });
  const stop = watchEvents('/test/events', () => {}, () => {}, () => {});
  t.after(stop);
  await settle();
  assert.equal(channels.length, 1);
  channels[0].onmessage({ data: 'yield-streams' });
  assert.equal(signals[0].aborted, true);
  timers.run(1000);
  await settle();
  assert.equal(signals.length, 2);
  stop();
  assert.equal(channels[0].closed, true);
});
