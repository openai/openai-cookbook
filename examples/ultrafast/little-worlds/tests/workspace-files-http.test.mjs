import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createApp } from '../server/index.mjs';

const sourceFor = title => `export const meta={title:${JSON.stringify(title)},subtitle:'',accent:'#687957'};
export function render(){return '<p>A notebook for shared thoughts.</p>'}
export function reduce(state,action,actor){
 if(action.type!=='note'||typeof action.text!=='string'||!action.text.trim())throw Error('Invalid note');
 state.extras.notes=state.extras.notes||{};
 state.extras.notes[actor.id]={actorId:actor.id,text:action.text.trim()};return state;
}`;
const seedSource = sourceFor('The original notebook');
const updatedSource = sourceFor('The updated notebook');
const checks = `export function runTests(api){
 const actor={id:'test-files-person',name:'Test guest'};
 const next=api.reduce(api.initialState,{type:'note',text:'Hello'},actor);
 return [
 {name:'A person can leave a note',ok:next.extras.notes[actor.id].text==='Hello'},
 {name:'Existing notes survive',ok:Object.entries(api.initialState.extras.notes||{}).every(([id,note])=>JSON.stringify(next.extras.notes[id])===JSON.stringify(note))},
 {name:'The notebook renders',ok:api.render(next,actor).includes('notebook')}
 ];
}`;
const seedOverride = { source: seedSource, tests: checks, state: { projects: [], contributions: [], extras: {} } };
const endpoint = (spaceId = 'mira') => `/api/spaces/${spaceId}/files`;
const responseFor = (source = updatedSource) => ({
  status: 'completed',
  output: [{ type: 'function_call', id: 'file-call-item', call_id: 'file-call', name: 'apply_change',
    arguments: JSON.stringify({ source, tests: checks, summary: 'Update the notebook' }) }],
  metrics: { durationMs: 12, ttftMs: 1, outputTokens: 40, servedTier: 'ultrafast' },
});
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};

async function fixture(t, respond = async () => responseFor()) {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-files-http-'));
  const instance = await createApp({ dataDir: join(parent, 'data'), seedOverride,
    adapter: { keyAvailable: true, model: 'files-fixture', tier: 'ultrafast', respond } });
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
  const build = async (token, spaceId = 'mira') => {
    const response = await request(`/api/spaces/${spaceId}/turn`, { token, json: { message: 'Update my notebook' } });
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
        assert.equal(chunk.done, false, 'The stream ended before the expected files arrived');
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

const snapshots = events => events.filter(event => event.type === 'files.snapshot');
const file = (snapshot, path) => snapshot.data.files.find(value => value.path === path);
function assertSnapshot(snapshot, source, status = 'published') {
  assert.equal(snapshot.type, 'files.snapshot');
  assert.ok(snapshot.id);
  assert.ok(Number.isFinite(Date.parse(snapshot.time)));
  assert.ok(snapshot.data.sessionId);
  assert.equal(snapshot.data.status, status);
  assert.deepEqual(snapshot.data.files.map(value => value.path).sort(), ['space.js', 'tests.js']);
  assert.equal(file(snapshot, 'space.js').content, source);
  assert.equal(file(snapshot, 'tests.js').content, checks);
  for (const item of snapshot.data.files) {
    assert.equal(item.language, 'javascript');
    assert.equal(item.status, status);
    assert.ok(Number.isFinite(Date.parse(item.updatedAt)));
  }
}

test('files require the space owner and the own-space alias ignores spoofed query identities', async t => {
  const miraSource = sourceFor('MIRA_PRIVATE_SOURCE');
  const leoSource = sourceFor('LEO_PRIVATE_SOURCE');
  let calls = 0;
  const { request, signIn, signOut, build } = await fixture(t, async () => responseFor(calls++ ? leoSource : miraSource));
  for (const path of [endpoint(), '/api/files']) assert.equal((await request(path)).status, 401);
  assert.equal((await request(endpoint(), { token: 'invalid-token' })).status, 401);
  const mira = await signIn();
  const leo = await signIn('leo');
  await build(mira.token);
  await build(leo.token, 'leo');
  assert.equal((await request(endpoint(), { token: leo.token })).status, 403);
  assert.equal((await request(`${endpoint()}?actor=mira&owner=mira`, { token: leo.token })).status, 403);
  assert.equal((await request(endpoint('unknown'), { token: mira.token })).status, 404);
  const own = openStream(await request('/api/files?spaceId=mira&actor=mira', { token: leo.token }));
  await signOut(leo.token);
  const events = await own.end();
  assertSnapshot(snapshots(events).at(-1), leoSource);
  assert.doesNotMatch(JSON.stringify(events), /MIRA_PRIVATE_SOURCE/);
});

test('files immediately provide complete published source and tests on initial connection and reconnect', async t => {
  const { instance, request, signIn, signOut } = await fixture(t);
  const { token } = await signIn();
  const initial = openStream(await request(endpoint(), { token }));
  const initialEvents = await initial.until(events => snapshots(events).length > 0);
  const first = snapshots(initialEvents)[0];
  assertSnapshot(first, seedSource);
  assert.equal(first.data.revisionId, instance.service.store.read().currentRevisionId);
  const reconnect = openStream(await request(`${endpoint()}?since=999999999`, { token, headers: { 'Last-Event-ID': '999999999' } }));
  await signOut(token);
  const repeated = snapshots(await reconnect.end());
  assert.equal(repeated.length, 1);
  assertSnapshot(repeated[0], seedSource);
  assert.equal(repeated[0].data.sessionId, first.data.sessionId);
  assert.equal(repeated[0].data.revisionId, first.data.revisionId);
  await initial.end();
});

test('an open files connection receives the newly published files without reconnecting', async t => {
  const { instance, request, signIn, signOut, build } = await fixture(t);
  const { token } = await signIn();
  const stream = openStream(await request(endpoint(), { token }));
  const initial = snapshots(await stream.until(events => snapshots(events).length > 0))[0];
  await build(token);
  const all = await stream.until(events => snapshots(events).some(event => event.data.status === 'published' && file(event, 'space.js')?.content === updatedSource));
  const published = snapshots(all).at(-1);
  assertSnapshot(published, updatedSource);
  assert.equal(published.data.sessionId, initial.data.sessionId);
  assert.equal(published.data.revisionId, instance.service.store.read().currentRevisionId);
  assert.ok(published.data.revisionId > initial.data.revisionId);
  await signOut(token);
  await stream.end();
});

test('sign-out closes files immediately while an already accepted build finishes safely', async t => {
  const began = deferred();
  const release = deferred();
  const { instance, request, signIn, signOut } = await fixture(t, async () => {
    began.resolve(); await release.promise; return responseFor();
  });
  const { token } = await signIn();
  const stream = openStream(await request(endpoint(), { token }));
  try {
    await stream.until(events => snapshots(events).length > 0);
    assert.equal((await request('/api/spaces/mira/turn', { token, json: { message: 'Keep this accepted build' } })).status, 202);
    await began.promise;
    await signOut(token);
    assert.ok(snapshots(await stream.end()).length > 0);
    assert.equal(instance.service.busy, true);
    assert.equal((await request(endpoint(), { token })).status, 401);
    release.resolve();
    await instance.service.waitForIdle();
    assert.equal(instance.service.store.read().session.lastOutcome, 'completed');
  } finally { release.resolve(); }
});

test('resetting a space replaces open and reconnected file views with seed files from a fresh session', async t => {
  const { request, signIn, signOut, build } = await fixture(t);
  const { token } = await signIn();
  await build(token);
  const stream = openStream(await request(endpoint(), { token }));
  const original = snapshots(await stream.until(events => snapshots(events).length > 0))[0];
  assertSnapshot(original, updatedSource);
  assert.equal((await request('/api/spaces/mira/reset', { token, json: {} })).status, 200);
  const next = snapshots(await stream.until(events => snapshots(events).some(event => event.data.sessionId !== original.data.sessionId))).at(-1);
  assertSnapshot(next, seedSource);
  assert.notEqual(next.data.sessionId, original.data.sessionId);
  const reconnect = openStream(await request(endpoint(), { token, headers: { 'Last-Event-ID': '999999999' } }));
  await signOut(token);
  const replay = snapshots(await reconnect.end());
  assert.equal(replay.length, 1);
  assertSnapshot(replay[0], seedSource);
  assert.equal(replay[0].data.sessionId, next.data.sessionId);
  assert.doesNotMatch(JSON.stringify(replay), /The updated notebook/);
  await stream.end();
});

test('demo reset closes old files streams and revoked identities cannot reopen them', async t => {
  const { request, signIn, signOut, build } = await fixture(t);
  const { token } = await signIn();
  await build(token);
  const stream = openStream(await request(endpoint(), { token }));
  const original = snapshots(await stream.until(events => snapshots(events).length > 0))[0];
  assertSnapshot(original, updatedSource);
  assert.equal((await request('/api/demo/reset', { json: { confirmation: 'reset-demo' } })).status, 200);
  await stream.end();
  assert.equal((await request(endpoint(), { token })).status, 401);
  const fresh = await signIn();
  const replay = openStream(await request(endpoint(), { token: fresh.token }));
  await signOut(fresh.token);
  const snapshot = snapshots(await replay.end()).at(-1);
  // The first demo reset captures the verified current page as its reusable
  // baseline; the owner reset above is the operation that restores the seed.
  assertSnapshot(snapshot, updatedSource);
  assert.notEqual(snapshot.data.sessionId, original.data.sessionId);
});
