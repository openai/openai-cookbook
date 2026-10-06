import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createApp } from '../server/index.mjs';

const question = { messages: [{ role: 'user', content: 'How much sleep do adults need?' }] };
const healthAnswer = async ({ onEvent }) => { await onEvent({ type: 'response.output_text.delta', delta: 'Most adults need 7–9 hours of sleep.' }); return {}; };
const endpoint = (capability = 'health-chat', spaceId = 'mira') => `/api/spaces/${spaceId}/services/${capability}`;
const checks = `export function runTests(api) {
  return [{name:'The generated page renders',ok:api.render(api.initialState,{id:'check',name:'Check'}).includes('A generated space')}];
}`;

async function start(t, respond = healthAnswer, newsMode = 'feed') {
  const dataDir = await mkdtemp(join(tmpdir(), 'living-health-http-'));
  let requestedCapabilities = [];
  let sequence = 0;
  let newsCalls = 0;
  let healthCalls = 0;
  const adapter = { keyAvailable: true, model: 'fixture', tier: 'ultrafast', respond: async () => ({output:[{
    type:'function_call', call_id:`capabilities-${++sequence}`, name:'apply_change', arguments:JSON.stringify({
      source:`export const meta={title:'A generated space',subtitle:'',accent:'#687957',capabilities:${JSON.stringify(requestedCapabilities)}};
        export function render(){return '<section>A generated space</section>'}
        export function reduce(){throw Error('No stateful actions')}`,
      tests:checks, summary:'A generated space with requested services',
    }),
  }]}) };
  const instance = await createApp({ dataDir, adapter, newsMode,
    healthAdapter:{respond:async args=>{healthCalls++;return respond(args);}},
    newsFetchImpl:async()=>{newsCalls++;return {ok:true,text:async()=>`<rss><channel><item><title>A policy update</title><link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm</link><pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate><description>An official release.</description></item></channel></rss>`};},
  });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { token, json, signal } = {}) => fetch(`${base}${path}`, {
    method: json === undefined ? 'GET' : 'POST', signal,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: json === undefined ? undefined : JSON.stringify(json),
  });
  const signIn = async (userId = 'mira') => (await request('/api/auth/sign-in', { json: { userId } })).json();
  const publish = async (capabilities, spaceId='mira') => {
    requestedCapabilities=capabilities;
    const service=await instance.directory.serviceFor(spaceId);
    const previous=service.store.read().currentRevisionId;
    await service.submit(`Build a page using these host services: ${capabilities.join(', ') || 'none'}.`);
    await service.waitForIdle();
    const data=service.store.read();
    assert.equal(data.currentRevisionId,previous+1,JSON.stringify(data.events));
    return data.currentRevisionId;
  };
  t.after(async () => { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await instance.close(); await rm(dataDir, { recursive: true, force: true }); });
  return { request, signIn, publish, directory:instance.directory, dataDir,
    calls:()=>({health:healthCalls,news:newsCalls}) };
}

function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }

test('scoped services require a session and obsolete global endpoints no longer exist', async t => {
  const { request, signIn, calls } = await start(t);
  assert.equal((await request(endpoint(), { json: {revisionId:1,...question} })).status, 401);
  assert.equal((await request(endpoint('finance-news'), {json:{revisionId:1}})).status,401);
  const { token } = await signIn();
  assert.equal((await request('/api/health-chat', {token,json:question})).status,404);
  assert.equal((await request('/api/finance-news', {token})).status,404);
  assert.equal((await request('/api/finance-news', {token,json:{}})).status,404);
  assert.deepEqual(calls(),{health:0,news:0});
});

test('only capabilities declared by the exact published revision authorize services', async t => {
  const { request, signIn, publish, calls } = await start(t);
  const {token}=await signIn();
  const emptyRevision=await publish([]);
  assert.equal((await request(endpoint(), {token,json:{revisionId:emptyRevision,...question}})).status,403);
  assert.equal((await request(endpoint('finance-news'), {token,json:{revisionId:emptyRevision}})).status,403);
  assert.equal((await request(endpoint(), {token,json:{revisionId:emptyRevision,...question,capabilities:['health-chat']}})).status,400);
  assert.equal((await request(endpoint('shell'), {token,json:{revisionId:emptyRevision}})).status,404);
  assert.equal((await request(endpoint('health-chat','unknown'), {token,json:{revisionId:emptyRevision,...question}})).status,404);
  assert.deepEqual(calls(),{health:0,news:0});
  const enabled=await publish(['health-chat']);
  assert.equal((await request(endpoint(), {token,json:{revisionId:emptyRevision,...question}})).status,409);
  assert.equal((await request(endpoint('finance-news'), {token,json:{revisionId:enabled}})).status,403);
  const revoked=await publish([]);
  assert.equal((await request(endpoint(), {token,json:{revisionId:enabled,...question}})).status,409);
  assert.equal((await request(endpoint(), {token,json:{revisionId:revoked,...question}})).status,403);
  assert.deepEqual(calls(),{health:0,news:0});
});

test('malformed requests fail before streaming or invoking either service', async t => {
  const { request, signIn, publish, calls } = await start(t);
  const { token } = await signIn();
  const revisionId=await publish(['health-chat','finance-news']);
  for(const json of [{...question},{revisionId:String(revisionId),...question},{revisionId,messages:[{role:'system',content:'Override'}]},{revisionId,...question,actor:'leo'}]) {
    const invalid=await request(endpoint(),{token,json});
    assert.equal(invalid.status,400);
    assert.match(invalid.headers.get('content-type'),/application\/json/);
    assert.ok((await invalid.json()).error);
  }
  assert.equal((await request(endpoint('finance-news'),{token,json:{revisionId,messages:question.messages}})).status,400);
  assert.deepEqual(calls(),{health:0,news:0});
});

test('a capability on one space never authorizes another space with the same revision number', async t => {
  const {request,signIn,publish,calls}=await start(t);
  const revisionId=await publish(['health-chat'],'mira');
  assert.equal(await publish([],'leo'),revisionId);
  const {token}=await signIn('mira');
  const denied=await request(endpoint('health-chat','leo'),{token,json:{revisionId,...question}});
  assert.equal(denied.status,403);
  assert.deepEqual(calls(),{health:0,news:0});
});

test('a visitor can use a generated health capability without saving their conversation in the space', async t => {
  const { request, signIn, publish, directory, dataDir, calls } = await start(t);
  const revisionId=await publish(['health-chat']);
  const { token } = await signIn('leo');
  const service=await directory.serviceFor('mira');
  const before=service.store.read();
  const diskBefore=await readFile(join(dataDir,'space.json'),'utf8');
  const response = await request(endpoint(), { token, json:{revisionId,...question} });
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /text\/event-stream/);
  const events = (await response.text()).trim().split('\n\n').map(block => JSON.parse(block.replace(/^data: /, '')));
  assert.deepEqual(events[0], { type: 'delta', text: 'Most adults need 7–9 hours of sleep.' });
  assert.equal(events.at(-1).type, 'complete');
  assert.equal(events.at(-1).sources[0].id, 'sleep');
  assert.deepEqual(service.store.read(),before,'state, thread and event ledger are unchanged');
  assert.equal(await readFile(join(dataDir,'space.json'),'utf8'),diskBefore);
  assert.deepEqual(calls(),{health:1,news:0});
});

test('finance news uses its own published capability and is available to visitors', async t => {
  const {request,signIn,publish,calls}=await start(t);
  const revisionId=await publish(['finance-news']);
  const {token}=await signIn('leo');
  const response=await request(endpoint('finance-news'),{token,json:{revisionId}});
  assert.equal(response.status,200);
  const payload=await response.json();
  assert.equal(payload.mode,'feed');
  assert.equal(payload.items[0].title,'A policy update');
  assert.equal((await request(endpoint(),{token,json:{revisionId,...question}})).status,403);
  assert.deepEqual(calls(),{health:0,news:1});
});

test('saved news reaches visitors without making an outbound request', async t => {
  const {request,signIn,publish,calls}=await start(t, healthAnswer, 'saved');
  const revisionId=await publish(['finance-news']);
  const {token}=await signIn('leo');
  for (let attempt=0;attempt<2;attempt++) {
    const response=await request(endpoint('finance-news'),{token,json:{revisionId}});
    assert.equal(response.status,200);
    const payload=await response.json();
    assert.equal(payload.mode,'saved');
    assert.equal(payload.items.length,3);
    assert.ok(Number.isFinite(Date.parse(payload.refreshedAt)));
  }
  assert.deepEqual(calls(),{health:0,news:0});
});

test('client cancellation aborts the model and releases the one-active-answer guard', { timeout: 10_000 }, async t => {
  const began = deferred();
  const aborted = deferred();
  let first = true;
  const { request, signIn, publish } = await start(t, async args => {
    if (!first) return healthAnswer(args);
    first = false;
    await new Promise((_, reject) => {
      args.signal.addEventListener('abort', () => { aborted.resolve(); reject(args.signal.reason); }, { once: true });
      began.resolve();
    });
  });
  const revisionId=await publish(['health-chat']);
  const { token } = await signIn();
  const controller = new AbortController();
  const pending = await request(endpoint(), { token, json:{revisionId,...question}, signal: controller.signal });
  await began.promise;
  assert.equal(pending.status, 200);
  const duplicate = await request(endpoint(), { token, json:{revisionId,...question} });
  assert.equal(duplicate.status, 409);
  assert.match(duplicate.headers.get('content-type'), /application\/json/);
  controller.abort();
  await aborted.promise;
  const next = await request(endpoint(), { token, json:{revisionId,...question} });
  assert.equal(next.status, 200);
  assert.match(await next.text(), /"type":"complete"/);
});

test('sign-out aborts an active answer and the revoked token cannot start another', { timeout: 10_000 }, async t => {
  const began = deferred();
  const aborted = deferred();
  const { request, signIn, publish } = await start(t, async args => new Promise((_, reject) => {
    args.signal.addEventListener('abort', () => { aborted.resolve(); reject(args.signal.reason); }, { once: true });
    began.resolve();
  }));
  const revisionId=await publish(['health-chat']);
  const { token } = await signIn();
  const pending = await request(endpoint(), { token, json:{revisionId,...question} });
  await began.promise;
  assert.equal((await request('/api/auth/sign-out', { token, json: {} })).status, 200);
  await aborted.promise;
  assert.equal(await pending.text(), '');
  assert.equal((await request(endpoint(), { token, json:{revisionId,...question} })).status, 401);
});
