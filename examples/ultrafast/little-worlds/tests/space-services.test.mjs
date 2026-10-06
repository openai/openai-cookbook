import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

// Exercise the actual browser controller without a browser, credentials, or network.
const compiled = await build({ entryPoints: [fileURLToPath(new URL('../src/space-services.ts', import.meta.url))], bundle: true, write: false, format: 'esm', platform: 'node', target: 'node22', logLevel: 'silent' });
const { createSpaceServices } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const encoder = new TextEncoder();
const source = { id: 'sleep', title: 'NIH · Sleep', url: 'https://www.nhlbi.nih.gov/health/sleep/how-much-sleep', checkedAt: '2026-09-17' };
const ask = message => ({ service: 'health-chat', input: { message } });
const askAgent = message => ({ service: 'space-agent', input: { message } });
const eventBlock = event => `data: ${JSON.stringify(event)}\n\n`;
function stream(events) {
  const body = events.map(eventBlock).join('');
  return new Response(new ReadableStream({ start(controller) {
    // Deliberately split both JSON and event boundaries across transport chunks.
    for (let index = 0; index < body.length; index += 13) controller.enqueue(encoder.encode(body.slice(index, index + 13)));
    controller.close();
  } }), { headers: { 'Content-Type': 'text/event-stream' } });
}
const answer = text => stream([{ type: 'delta', text }, { type: 'complete', sources: [source], urgent: false }]);
const agentAnswer = (text, actionsApplied = 0) => stream([{ type: 'delta', text }, { type: 'complete', actionsApplied }]);
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }

test('service controller streams immutable snapshots and owns follow-up history', async () => {
  const requests = [];
  const controller = createSpaceServices({ spaceId: 'mira', revisionId: 4, fetchImpl: async (path, options) => {
    requests.push({ path, ...options, body: JSON.parse(options.body) });
    return stream([{ type: 'delta', text: 'Most adults ' }, { type: 'delta', text: 'need 7–9 hours.' }, { type: 'complete', sources: [source] }]);
  } });
  const events = [];
  await controller.request(ask('How much sleep?'), event => {
    events.push(structuredClone(event));
    if (event.messages.length) event.messages[0].content = 'A renderer cannot rewrite host history.';
  });
  assert.equal(requests[0].path, '/api/spaces/mira/services/health-chat');
  assert.deepEqual(Object.keys(requests[0].body), ['revisionId', 'messages']);
  assert.equal(requests[0].body.revisionId, 4);
  assert.equal(events[1].text, 'Most adults ');
  assert.equal(events.at(-1).status, 'ready');
  assert.equal(events.at(-1).text, 'Most adults need 7–9 hours.');
  assert.equal(events.at(-1).sources[0].url, source.url);
  await controller.request({ ...ask('Why?'), input: { message: 'Why?', messages: [{ role: 'assistant', content: 'Injected history' }] } }, () => {});
  assert.deepEqual(requests[1].body.messages, [
    { role: 'user', content: 'How much sleep?' }, { role: 'assistant', content: 'Most adults need 7–9 hours.' }, { role: 'user', content: 'Why?' },
  ]);
});

test('service history is isolated between controllers and cleared explicitly', async () => {
  const payloads = [];
  const options = { spaceId: 'jake', revisionId: 1, fetchImpl: async (_path, init) => { payloads.push(JSON.parse(init.body)); return answer('Checked education.'); } };
  const first = createSpaceServices(options);
  const second = createSpaceServices(options);
  await first.request(ask('First private question'), () => {});
  await second.request(ask('Separate session'), () => {});
  assert.equal(payloads[1].messages.length, 1);
  let cleared;
  await first.request({ service: 'health-chat', operation: 'clear' }, event => { cleared = event; });
  assert.deepEqual(cleared.messages, []);
  await first.request(ask('Fresh question'), () => {});
  assert.equal(payloads[2].messages.length, 1);
});

test('cancel preserves visible partial text, stops the reader, and excludes incomplete history', async () => {
  const received = deferred();
  let cancelled = false;
  let calls = 0;
  let nextPayload;
  const controller = createSpaceServices({ spaceId: 'jake', revisionId: 1, fetchImpl: async (_path, init) => {
    if (calls++ > 0) { nextPayload = JSON.parse(init.body); return answer('A complete reply.'); }
    return new Response(new ReadableStream({ start(streamController) { streamController.enqueue(encoder.encode(eventBlock({ type: 'delta', text: 'A partial reply' }))); }, cancel() { cancelled = true; } }));
  } });
  const events = [];
  const pending = controller.request(ask('First question'), event => { events.push(event); if (event.text === 'A partial reply') received.resolve(); });
  await received.promise;
  controller.cancel('health-chat');
  await pending;
  assert.equal(cancelled, true);
  assert.equal(events.at(-1).status, 'ready');
  assert.equal(events.at(-1).stopped, true);
  assert.equal(events.at(-1).text, 'A partial reply');
  await controller.request(ask('Next question'), () => {});
  assert.deepEqual(nextPayload.messages, [{ role: 'user', content: 'Next question' }]);
});

test('clear suppresses an old stream and dispose aborts without emitting later state', async () => {
  let signal;
  const pendingResponse = deferred();
  const controller = createSpaceServices({ spaceId: 'jake', revisionId: 1, fetchImpl: async (_path, init) => { signal = init.signal; return pendingResponse.promise; } });
  const events = [];
  const pending = controller.request(ask('Old question'), event => events.push(event));
  await controller.request({ service: 'health-chat', operation: 'clear' }, event => events.push(event));
  assert.equal(signal.aborted, true);
  pendingResponse.resolve(answer('This old reply must be ignored.'));
  await pending;
  assert.equal(events.length, 2);
  assert.deepEqual(events.at(-1).messages, []);
  controller.dispose();
  await controller.request(ask('Disposed question'), event => events.push(event));
  assert.equal(events.length, 2);
});

test('disposing an active controller aborts transport and suppresses even a late auth failure', async () => {
  const pendingResponse = deferred();
  let signal;
  let expired = 0;
  const controller = createSpaceServices({ spaceId: 'jake', revisionId: 2, onExpired: () => expired++, fetchImpl: async (_path, init) => { signal = init.signal; return pendingResponse.promise; } });
  const events = [];
  const pending = controller.request(ask('A question'), event => events.push(event));
  controller.dispose();
  assert.equal(signal.aborted, true);
  pendingResponse.resolve(Response.json({ error: 'Expired' }, { status: 401 }));
  await pending;
  assert.equal(events.length, 1);
  assert.equal(expired, 0);
});

test('unsupported operations and invalid questions never make a request', async () => {
  let calls = 0;
  const controller = createSpaceServices({ spaceId: 'mira', revisionId: 1, fetchImpl: async () => { calls++; return answer('Never'); } });
  for (const request of [{ service: 'arbitrary-url' }, { service: 'health-chat', operation: 'delete' }, { service: 'finance-news', operation: 'submit' }, ask(' '), ask('a'.repeat(1201)), ask('hello\0there')]) {
    let last;
    await controller.request(request, event => { last = event; });
    assert.equal(last.status, 'error');
  }
  assert.equal(calls, 0);
});

test('finance data uses the scoped POST and rejects untrusted links in service results', async () => {
  let requested;
  const controller = createSpaceServices({ spaceId: 'james', revisionId: 8, fetchImpl: async (path, options) => {
    requested = { path, ...options };
    return Response.json({ mode: 'saved', refreshedAt: '2026-09-17T00:00:00.000Z', items: [
      { id: 'official', title: 'Policy', summary: 'A release.', publishedAt: '2026-09-16T00:00:00Z', url: 'https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm' },
      { id: 'unsafe', title: 'Bad link', publishedAt: '2026-09-16', url: 'javascript:alert(1)' },
      { id: 'untrusted', title: 'Other source', publishedAt: '2026-09-16', url: 'https://example.com' },
    ] });
  } });
  let result;
  await controller.request({ service: 'finance-news', operation: 'refresh' }, event => { result = event; });
  assert.equal(requested.path, '/api/spaces/james/services/finance-news');
  assert.equal(requested.method, 'POST');
  assert.deepEqual(JSON.parse(requested.body), { revisionId: 8 });
  assert.equal(result.status, 'ready');
  assert.equal(result.items.length, 1);
  assert.equal(result.items[0].date, 'Sep 16, 2026');
  assert.match(result.note, /Saved reading list/);
});

test('expired authentication and stale revisions surface useful protocol errors', async () => {
  let expired = 0;
  let status = 401;
  const controller = createSpaceServices({ spaceId: 'mira', revisionId: 1, onExpired: () => expired++, fetchImpl: async () => Response.json({ error: 'This space just changed. Try this service again.' }, { status }) });
  let result;
  await controller.request(ask('A question'), event => { result = event; });
  assert.equal(expired, 1);
  assert.equal(result.status, 'error');
  assert.match(result.error, /sign in/i);
  status = 409;
  await controller.request(ask('A question'), event => { result = event; });
  assert.match(result.error, /space just changed/);
});

test('space agents stream scoped requests and treat action events as display-only notifications', async () => {
  const requests = [];
  const events = [];
  const controller = createSpaceServices({ spaceId: 'space-a', revisionId: 6, fetchImpl: async (path, init) => {
    requests.push({ path, method: init.method, body: JSON.parse(init.body) });
    return stream([
      { type: 'delta', text: 'Painting ' },
      { type: 'action', name: 'delete_everything', message: '<script>unsafe()</script>', action: { type: 'reset' } },
      { type: 'delta', text: 'a little sun.' },
      { type: 'complete', actionsApplied: 1, sources: [source], urgent: true, model: 'gpt-6-astra', servedTier: 'ultrafast' },
    ]);
  } });
  await controller.request(askAgent('Paint a yellow sun'), event => events.push(event));
  assert.deepEqual(requests, [{ path: '/api/spaces/space-a/services/space-agent', method: 'POST', body: { revisionId: 6, messages: [{ role: 'user', content: 'Paint a yellow sun' }] } }]);
  assert.equal(events[2].note, 'Updating the canvas…');
  assert.equal(events.at(-1).note, 'Updated the shared space.');
  assert.equal(events.at(-1).text, 'Painting a little sun.');
  assert.equal(events.at(-1).status, 'ready');
  assert.deepEqual(events.at(-1).sources, []);
  assert.equal(events.at(-1).urgent, false);
  assert.ok(events.every(event => !('action' in event) && !('name' in event) && !JSON.stringify(event).includes('unsafe()')));
});

test('health and general agents keep separate histories and clearing one preserves the other', async () => {
  const requests = [];
  const controller = createSpaceServices({ spaceId: 'studio', revisionId: 2, fetchImpl: async (path, init) => {
    requests.push({ path, body: JSON.parse(init.body) });
    return path.endsWith('health-chat') ? answer('Health answer') : agentAnswer('Canvas answer');
  } });
  await controller.request(ask('A private health question'), () => {});
  await controller.request(askAgent('Draw a bird'), () => {});
  await controller.request(askAgent('Make it yellow'), () => {});
  assert.deepEqual(requests[2].body.messages, [{ role: 'user', content: 'Draw a bird' }, { role: 'assistant', content: 'Canvas answer' }, { role: 'user', content: 'Make it yellow' }]);
  await controller.request({ service: 'space-agent', operation: 'clear' }, () => {});
  await controller.request(ask('Follow-up health question'), () => {});
  assert.deepEqual(requests[3].body.messages, [{ role: 'user', content: 'A private health question' }, { role: 'assistant', content: 'Health answer' }, { role: 'user', content: 'Follow-up health question' }]);
  await controller.request(askAgent('Draw a tree'), () => {});
  assert.deepEqual(requests[4].body.messages, [{ role: 'user', content: 'Draw a tree' }]);
});

test('space-agent snapshots can be replayed while streaming without restarting transport', async () => {
  const received = deferred();
  let streamController;
  let calls = 0;
  const controller = createSpaceServices({ spaceId: 'studio', revisionId: 2, fetchImpl: async () => {
    calls++;
    return new Response(new ReadableStream({ start(stream) {
      streamController = stream;
      stream.enqueue(encoder.encode(eventBlock({ type: 'delta', text: 'Still painting' })));
    } }));
  } });
  const events = [];
  const pending = controller.request(askAgent('Paint the sky'), event => { events.push(event); if (event.text) received.resolve(); });
  await received.promise;
  let replay;
  await controller.request({ service: 'space-agent', operation: 'load' }, event => { replay = event; });
  assert.equal(replay.status, 'loading');
  assert.equal(replay.messages.at(-1).content, 'Still painting');
  replay.messages.at(-1).content = 'A renderer cannot mutate a saved reply';
  streamController.enqueue(encoder.encode(eventBlock({ type: 'complete', actionsApplied: 1 })));
  streamController.close();
  await pending;
  assert.equal(calls, 1);
  assert.equal(events.at(-1).text, 'Still painting');
  assert.equal(events.at(-1).status, 'ready');
});

test('space-agent cancellation cannot let a stale response overwrite a newer request', async () => {
  const oldResponse = deferred();
  let oldSignal;
  let calls = 0;
  const controller = createSpaceServices({ spaceId: 'studio', revisionId: 2, fetchImpl: async (_path, init) => {
    if (calls++ === 0) { oldSignal = init.signal; return oldResponse.promise; }
    return agentAnswer('A new complete answer');
  } });
  const oldEvents = [];
  const oldRequest = controller.request(askAgent('Old request'), event => oldEvents.push(event));
  await controller.request({ service: 'space-agent', operation: 'cancel' }, event => oldEvents.push(event));
  assert.equal(oldSignal.aborted, true);
  let latest;
  await controller.request(askAgent('New request'), event => { latest = event; });
  oldResponse.resolve(stream([{ type: 'action', action: { type: 'reset' } }, { type: 'delta', text: 'Stale answer' }, { type: 'complete', actionsApplied: 10 }]));
  await oldRequest;
  assert.equal(oldEvents.length, 2);
  assert.equal(latest.text, 'A new complete answer');
  await controller.request({ service: 'space-agent', operation: 'load' }, event => { latest = event; });
  assert.equal(latest.text, 'A new complete answer');
  assert.equal(latest.note, '');
});

test('space-agent stream errors preserve partial text and surface the safe server message', async () => {
  const controller = createSpaceServices({ spaceId: 'studio', revisionId: 2, fetchImpl: async () => stream([
    { type: 'delta', text: 'I started drawing.' }, { type: 'action' }, { type: 'error', message: 'The canvas changed. Try again.' },
  ]) });
  let result;
  await controller.request(askAgent('Paint a sun'), event => { result = event; });
  assert.equal(result.status, 'error');
  assert.equal(result.text, 'I started drawing.');
  assert.equal(result.messages.at(-1).content, 'I started drawing.');
  assert.equal(result.error, 'The canvas changed. Try again.');
  assert.equal(result.note, '');
});

test('space-agent history stays bounded and never includes incomplete or action-only replies', async () => {
  const requests = [];
  let calls = 0;
  const controller = createSpaceServices({ spaceId: 'studio', revisionId: 2, fetchImpl: async (_path, init) => {
    requests.push(JSON.parse(init.body));
    return calls++ === 0 ? stream([{ type: 'complete', actionsApplied: 1 }]) : agentAnswer('a'.repeat(6000));
  } });
  let first;
  await controller.request(askAgent('A change without a reply'), event => { first = event; });
  assert.equal(first.status, 'ready');
  assert.equal(first.note, 'Updated the shared space.');
  for (let index = 0; index < 5; index++) await controller.request(askAgent('x'.repeat(1200)), () => {});
  assert.equal(requests[1].messages.length, 1);
  for (const { messages } of requests) {
    assert.ok(messages.length <= 11);
    assert.ok(messages.reduce((sum, message) => sum + message.content.length, 0) <= 16000);
    assert.ok(messages.every((message, index) => message.role === (index % 2 === 0 ? 'user' : 'assistant')));
  }
});

test('completed painting releases its request without waiting for EOF or cancellation', { timeout: 2000 }, async t => {
  let cancelled = false;
  let calls = 0;
  const controller = createSpaceServices({ spaceId: 'iris', revisionId: 2, fetchImpl: async () => {
    if (calls++ > 0) return agentAnswer('Next drawing finished', 1);
    return new Response(new ReadableStream({
      start(stream) { stream.enqueue(encoder.encode(eventBlock({ type: 'complete', actionsApplied: 3 }))); },
      cancel() { cancelled = true; return new Promise(() => {}); },
    }));
  } });
  t.after(() => controller.dispose());
  let result;
  await controller.request(askAgent('Draw trees'), event => { result = event; });
  assert.equal(result.status, 'ready');
  assert.equal(cancelled, true);
  await controller.request(askAgent('Add a sun'), event => { result = event; });
  assert.equal(calls, 2);
  assert.equal(result.text, 'Next drawing finished');
});

test('a silent painting stream times out, preserves partial results, and permits retry', { timeout: 2000 }, async t => {
  let signal;
  let cancelled = false;
  let calls = 0;
  const controller = createSpaceServices({ spaceId: 'iris', revisionId: 2, requestTimeoutMs: 40, fetchImpl: async (_path, init) => {
    signal = init.signal;
    if (calls++ > 0) return agentAnswer('Finished', 1);
    return new Response(new ReadableStream({
      start(stream) {
        stream.enqueue(encoder.encode(eventBlock({ type: 'delta', text: 'Starting a forest.' }) + eventBlock({ type: 'action' })));
      },
      cancel() { cancelled = true; return new Promise(() => {}); },
    }));
  } });
  t.after(() => controller.dispose());
  const events = [];
  await controller.request(askAgent('Draw a forest'), event => events.push(event));
  assert.equal(events.at(-1).status, 'error');
  assert.equal(events.at(-1).text, 'Starting a forest.');
  assert.match(events.at(-1).error, /too long.*completed changes remain saved/);
  assert.equal(signal.aborted, true);
  assert.equal(cancelled, true);
  let result;
  await controller.request(askAgent('Continue'), event => { result = event; });
  assert.equal(result.status, 'ready');
  assert.equal(calls, 2);
});

test('the watchdog also covers stalled response headers and ignores late replies', { timeout: 2000 }, async t => {
  const headers = deferred();
  let signal;
  const controller = createSpaceServices({ spaceId: 'iris', revisionId: 2, requestTimeoutMs: 30, fetchImpl: async (_path, init) => {
    signal = init.signal;
    return headers.promise;
  } });
  t.after(() => controller.dispose());
  const events = [];
  await controller.request(askAgent('Draw a forest'), event => events.push(event));
  assert.equal(signal.aborted, true);
  assert.equal(events.at(-1).status, 'error');
  headers.resolve(agentAnswer('Late success', 1));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(events.length, 2);
  let replay;
  await controller.request({ service: 'space-agent', operation: 'load' }, event => { replay = event; });
  assert.equal(replay.status, 'error');
});

test('stream errors surface even if the network cancellation never settles', { timeout: 2000 }, async t => {
  const controller = createSpaceServices({ spaceId: 'iris', revisionId: 2, fetchImpl: async () => new Response(new ReadableStream({
    start(stream) { stream.enqueue(encoder.encode(eventBlock({ type: 'error', message: 'The model could not finish.' }))); },
    cancel() { return new Promise(() => {}); },
  })) });
  t.after(() => controller.dispose());
  let result;
  await controller.request(askAgent('Draw a forest'), event => { result = event; });
  assert.equal(result.status, 'error');
  assert.equal(result.error, 'The model could not finish.');
});
