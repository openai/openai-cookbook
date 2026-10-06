import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createApp } from '../server/index.mjs';

const source = `export const meta={title:'A little notebook',subtitle:'',accent:'#687957'};
export function render(){return '<p>A little notebook for shared thoughts.</p>'}
export function reduce(state,action,actor){
 if(action.type!=='note'||typeof action.text!=='string'||!action.text.trim())throw Error('Invalid note');
 state.extras.notes=state.extras.notes||{};
 state.extras.notes[actor.id]={actorId:actor.id,text:action.text.trim()};return state;
}`;
const checks = `export function runTests(api){
 const actor={id:'test-activity-person',name:'Test guest'};
 const next=api.reduce(api.initialState,{type:'note',text:'Hello'},actor);
 return [
 {name:'A person can leave a note',ok:next.extras.notes[actor.id].text==='Hello'},
 {name:'Existing notes survive',ok:Object.entries(api.initialState.extras.notes||{}).every(([id,note])=>JSON.stringify(next.extras.notes[id])===JSON.stringify(note))},
 {name:'The notebook renders',ok:api.render(next,actor).includes('notebook')}
 ];
}`;
const seedOverride = { source, tests: checks, state: { projects: [], contributions: [], extras: {} } };
const endpoint = (spaceId = 'mira') => `/api/spaces/${spaceId}/activity`;
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};

async function streamBuild({ onEvent }, pause = async () => {}) {
  const message = { type: 'message', id: 'message-1', role: 'assistant', content: [{ type: 'output_text', text: 'Making your notebook.' }] };
  const call = { type: 'function_call', id: 'call-item-1', call_id: 'call-1', name: 'apply_change', arguments: JSON.stringify({ source, tests: checks, summary: 'A little notebook' }) };
  const reasoning = { type: 'reasoning', id: 'reasoning-1', encrypted_content: 'PRIVATE_ENCRYPTED_REASONING', summary: [{ type: 'summary_text', text: 'PRIVATE_REASONING_SUMMARY' }] };
  await onEvent({ type: 'response.created', response: { id: 'provider-response', input: [{ role: 'system', content: 'PRIVATE_PROVIDER_INPUT' }], metadata: { authorization: 'PRIVATE_PROVIDER_CREDENTIAL' } } });
  await onEvent({ type: 'response.output_item.added', output_index: 0, item: { ...message, content: [] } });
  await onEvent({ type: 'response.output_text.delta', output_index: 0, item_id: message.id, content_index: 0, delta: 'Making your ' });
  await pause();
  await onEvent({ type: 'response.output_text.delta', output_index: 0, item_id: message.id, content_index: 0, delta: 'notebook.' });
  await onEvent({ type: 'response.output_text.done', output_index: 0, item_id: message.id, content_index: 0, text: message.content[0].text });
  await onEvent({ type: 'response.output_item.done', output_index: 0, item: message });
  await onEvent({ type: 'response.output_item.added', output_index: 1, item: reasoning });
  await onEvent({ type: 'response.reasoning_summary_text.delta', output_index: 1, delta: 'PRIVATE_REASONING_DELTA' });
  await onEvent({ type: 'response.output_item.done', output_index: 1, item: reasoning });
  await onEvent({ type: 'response.output_item.added', output_index: 2, item: { ...call, arguments: '' } });
  const middle = Math.floor(call.arguments.length / 2);
  for (const delta of [call.arguments.slice(0, middle), call.arguments.slice(middle)]) {
    await onEvent({ type: 'response.function_call_arguments.delta', output_index: 2, item_id: call.id, delta });
  }
  await onEvent({ type: 'response.function_call_arguments.done', output_index: 2, item_id: call.id, arguments: call.arguments });
  await onEvent({ type: 'response.output_item.done', output_index: 2, item: call });
  const response = { status: 'completed', output: [message, reasoning, call], model: 'activity-fixture', service_tier: 'ultrafast' };
  await onEvent({ type: 'response.completed', response });
  return { ...response, metrics: { durationMs: 12, ttftMs: 1, outputTokens: 40, servedTier: 'ultrafast' } };
}

async function fixture(t, respond = streamBuild, options = {}) {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-activity-http-'));
  const instance = await createApp({ dataDir: join(parent, 'data'), seedOverride,
    adapter: { keyAvailable: true, model: 'activity-fixture', tier: 'ultrafast', respond }, ...options });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { token, json, headers, signal = AbortSignal.timeout(5000) } = {}) => fetch(`${base}${path}`, {
    method: json === undefined ? 'GET' : 'POST', signal,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json', Origin: base }), ...headers },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }),
  });
  const signIn = async (userId = 'mira') => {
    const response = await request('/api/auth/sign-in', { json: { userId } });
    assert.equal(response.status, 200);
    return response.json();
  };
  const signOut = async token => assert.equal((await request('/api/auth/sign-out', { token, json: {} })).status, 200);
  const build = async (token, spaceId = 'mira', message = 'Make an inviting notebook') => {
    const response = await request(`/api/spaces/${spaceId}/turn`, { token, json: { message } });
    assert.equal(response.status, 202);
    const result = await response.json();
    const service = await instance.directory.serviceFor(spaceId);
    await service.waitForIdle();
    assert.equal(service.store.read().session.lastOutcome, 'completed');
    return result;
  };
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await instance.close();
    await rm(parent, { recursive: true, force: true });
  });
  return { instance, request, signIn, signOut, build };
}

function parseEvents(text) {
  return text.split(/\r?\n\r?\n/).flatMap(block => {
    const data = block.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    return data ? [JSON.parse(data)] : [];
  });
}

function openStream(response) {
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /text\/event-stream/);
  assert.match(response.headers.get('cache-control'), /no-store/);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = '';
  return {
    get events() { return parseEvents(text.slice(0, text.lastIndexOf('\n\n') + 2)); },
    async until(predicate) {
      while (!predicate(this.events)) {
        const chunk = await reader.read();
        assert.equal(chunk.done, false, 'The stream ended before the expected activity arrived');
        text += decoder.decode(chunk.value, { stream: true });
      }
      return this.events;
    },
    async end() {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) return parseEvents(text + decoder.decode());
        text += decoder.decode(chunk.value, { stream: true });
      }
    },
  };
}

const entries = events => events.filter(event => event.type === 'activity.entry');
const latestEntries = events => [...new Map(entries(events).map(event => [event.data.entryId, event])).values()];

test('activity requires a bearer identity and only the selected space owner can read it', async t => {
  const { request, signIn, signOut, build } = await fixture(t);
  for (const path of [endpoint(), '/api/activity']) assert.equal((await request(path)).status, 401);
  assert.equal((await request(endpoint(), { token: 'invalid-token' })).status, 401);
  const mira = await signIn();
  const leo = await signIn('leo');
  await build(mira.token, 'mira', 'MIRA_PRIVATE_REQUEST');
  await build(leo.token, 'leo', 'LEO_PRIVATE_REQUEST');
  assert.equal((await request(endpoint(), { token: leo.token })).status, 403);
  assert.equal((await request(`${endpoint()}?actor=mira`, { token: leo.token })).status, 403);
  assert.equal((await request(endpoint('unknown'), { token: mira.token })).status, 404);
  const own = openStream(await request('/api/activity?spaceId=mira&actor=mira', { token: leo.token }));
  await signOut(leo.token);
  const text = JSON.stringify(await own.end());
  assert.match(text, /LEO_PRIVATE_REQUEST/);
  assert.doesNotMatch(text, /MIRA_PRIVATE_REQUEST/);
});

test('activity streams partial assistant text while a build is still running, then tools and final results', async t => {
  const began = deferred();
  const release = deferred();
  const { instance, request, signIn, signOut } = await fixture(t, args => streamBuild(args, async () => { began.resolve(); await release.promise; }));
  const { token } = await signIn();
  const stream = openStream(await request(endpoint(), { token }));
  try {
    const started = await request('/api/spaces/mira/turn', { token, json: { message: 'A live notebook' } });
    assert.equal(started.status, 202);
    const { turnId } = await started.json();
    await began.promise;
    const partial = await stream.until(events => entries(events).some(event => event.data.kind === 'message' && event.data.text === 'Making your '));
    assert.equal(instance.service.busy, true);
    assert.ok(entries(partial).some(event => event.turnId === turnId));
    release.resolve();
    await instance.service.waitForIdle();
    await signOut(token);
    const all = await stream.end();
    const latest = latestEntries(all);
    const message = latest.find(event => event.data.kind === 'message');
    assert.equal(message.data.text, 'Making your notebook.');
    const tool = latest.find(event => event.data.kind === 'tool' && event.data.arguments?.includes('export const meta'));
    assert.ok(tool, 'The code written by the tool is visible');
    assert.equal(JSON.parse(tool.data.arguments).source, source);
    assert.ok(tool.data.result, 'The executed tool result is visible');
    assert.ok(latest.some(event => event.data.kind === 'event' && /checks passed/.test(event.title)));
    assert.equal(instance.service.store.read().session.lastOutcome, 'completed');
  } finally { release.resolve(); }
});

test('reconnect replays cumulative entries despite an old cursor, without private provider context or reasoning', async t => {
  const { instance, request, signIn, signOut, build } = await fixture(t);
  const { token } = await signIn();
  await build(token);
  const expected = instance.service.activity.read();
  assert.ok(expected.length > 0);
  const current = openStream(await request(endpoint(), { token }));
  const reconnect = openStream(await request(endpoint(), { token, headers: { 'Last-Event-ID': '999999999' } }));
  await signOut(token);
  const first = await current.end();
  const replay = await reconnect.end();
  assert.equal(first[0].type, 'activity.reset');
  assert.equal(first[0].data.reason, 'replay');
  assert.deepEqual(entries(first), expected);
  assert.equal(replay[0].type, 'activity.reset');
  assert.equal(replay[0].data.reason, 'replay');
  assert.deepEqual(entries(replay), entries(first));
  assert.equal(new Set(entries(replay).map(event => event.data.entryId)).size, expected.length, 'Replay contains one cumulative value per entry');
  // A row's notification ID changes as it streams. Replay retains original
  // creation order instead of moving a completed tool below the next event.
  const times = entries(replay).map(event => event.time);
  assert.deepEqual(times, [...times].sort());
  const wire = JSON.stringify(replay);
  for (const privateText of ['PRIVATE_ENCRYPTED_REASONING', 'PRIVATE_REASONING_SUMMARY', 'PRIVATE_REASONING_DELTA', 'PRIVATE_PROVIDER_INPUT', 'PRIVATE_PROVIDER_CREDENTIAL', 'encrypted_content']) {
    assert.ok(!wire.includes(privateText), privateText);
  }
  assert.match(wire, /Making your notebook\./);
  assert.match(wire, /apply_change/);
});

test('sign-out promptly closes activity while the already accepted build can finish safely', async t => {
  const began = deferred();
  const release = deferred();
  const { instance, request, signIn, signOut } = await fixture(t, args => streamBuild(args, async () => { began.resolve(); await release.promise; }));
  const { token } = await signIn();
  const stream = openStream(await request(endpoint(), { token }));
  try {
    assert.equal((await request('/api/spaces/mira/turn', { token, json: { message: 'Keep this accepted build' } })).status, 202);
    await began.promise;
    await stream.until(events => entries(events).some(event => event.data.kind === 'message'));
    await signOut(token);
    const ended = await stream.end();
    assert.ok(entries(ended).length > 0);
    assert.equal(instance.service.busy, true);
    assert.equal((await request(endpoint(), { token })).status, 401);
    release.resolve();
    await instance.service.waitForIdle();
    assert.equal(instance.service.store.read().session.lastOutcome, 'completed');
  } finally { release.resolve(); }
});

test('resetting one space clears its replay and notifies its open activity connection', async t => {
  const { instance, request, signIn, signOut, build } = await fixture(t);
  const { token } = await signIn();
  await build(token, 'mira', 'BEFORE_SPACE_RESET');
  const stream = openStream(await request(endpoint(), { token }));
  await stream.until(events => entries(events).some(event => event.data.kind === 'request'));
  assert.equal((await request('/api/spaces/mira/reset', { token, json: {} })).status, 200);
  await stream.until(events => events.some(event => event.type === 'activity.reset' && event.data.reason === 'space-reset'));
  assert.deepEqual(instance.service.activity.read(), []);
  const replay = openStream(await request(endpoint(), { token, headers: { 'Last-Event-ID': '999999999' } }));
  await signOut(token);
  const fresh = await replay.end();
  assert.equal(fresh[0].type, 'activity.reset');
  assert.deepEqual(entries(fresh), []);
  assert.doesNotMatch(JSON.stringify(fresh), /BEFORE_SPACE_RESET/);
  await stream.end();
});

test('demo reset closes existing activity streams, invalidates old identities, and starts with an empty feed', async t => {
  const { instance, request, signIn, signOut, build } = await fixture(t);
  const { token } = await signIn();
  await build(token, 'mira', 'BEFORE_DEMO_RESET');
  const previousService = instance.service;
  const stream = openStream(await request(endpoint(), { token }));
  await stream.until(events => entries(events).length > 0);
  assert.equal((await request('/api/demo/reset', { json: { confirmation: 'reset-demo' } })).status, 200);
  await stream.end();
  assert.equal((await request(endpoint(), { token })).status, 401);
  assert.notEqual(instance.service, previousService);
  assert.deepEqual(instance.service.activity.read(), []);
  const fresh = await signIn();
  const replay = openStream(await request(endpoint(), { token: fresh.token }));
  await signOut(fresh.token);
  assert.deepEqual(entries(await replay.end()), []);
});

test('a healthy reader receives a large replay in full across socket backpressure', async t => {
  const { instance, request, signIn, signOut } = await fixture(t);
  const { token } = await signIn();
  // Exercise the same bounded public-output projection used by the adapter,
  // without asking the model to write or publish a large synthetic module.
  instance.service.activity.providerOutput('large-replay', 0, Array.from({ length: 24 }, (_, index) => ({
    type: 'message', id: `large-${index}`, role: 'assistant',
    content: [{ type: 'output_text', text: `Message ${index}: ${'notebook '.repeat(5000)} END ${index}` }],
  })));
  const expected = instance.service.activity.read();
  assert.equal(expected.length, 24);
  assert.ok(JSON.stringify(expected).length > 1_000_000);
  const stream = openStream(await request(endpoint(), { token }));
  const received = await stream.until(events => entries(events).length === expected.length);
  assert.deepEqual(entries(received), expected);
  await signOut(token);
  assert.deepEqual(entries(await stream.end()), expected);
});

test('opening activity during a pending update replays the request before the newer output', async t => {
  const { instance, request, signIn, signOut } = await fixture(t);
  const { token } = await signIn();
  const feed = instance.service.activity;
  feed.lifecycle({ id: '1', turnId: 'pending-replay', type: 'turn.started', title: 'First request', detail: 'Make a notebook' });
  feed.flush();
  const read = feed.read.bind(feed);
  // Insert a pending delta immediately before snapshot creation, independent
  // of network timing and the feed's real coalescing timer.
  t.mock.method(feed, 'read', () => {
    feed.providerEvent('pending-replay', 0, { type: 'response.output_text.delta', output_index: 0, content_index: 0, delta: 'Newer output' });
    return read();
  });
  const stream = openStream(await request(endpoint(), { token }));
  const received = await stream.until(events => entries(events).some(event => event.data.kind === 'message'));
  assert.deepEqual(entries(received).map(event => event.data.kind), ['request', 'message']);
  await signOut(token); await stream.end();
});
