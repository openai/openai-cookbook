import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createApp } from '../server/index.mjs';

const source = `export const meta={title:'A shared guestbook',subtitle:'',accent:'#687957'};
export function render(state,actor){return '<p>A place to leave a thought.</p>'}
export function reduce(state,action,actor){
 if(action.type!=='leave'||typeof action.text!=='string'||!action.text.trim()||action.text.length>80)throw Error('Invalid thought');
 state.extras.guestbook=state.extras.guestbook||{};
 state.extras.guestbook[actor.id]={actorId:actor.id,text:action.text.trim()};return state;
}`;
const checks = `export function runTests(api){
 const actor={id:'test-fresh-person',name:'Test guest'};
 const next=api.reduce(api.initialState,{type:'leave',text:'A little wonder'},actor);
 let blocked=false;try{api.reduce(api.initialState,{type:'leave',text:''},actor)}catch{blocked=true}
 return [
 {name:'Visitors can leave a thought',ok:next.extras.guestbook[actor.id].text==='A little wonder'},
 {name:'Empty thoughts are refused',ok:blocked},
 {name:'Other records remain intact',ok:Object.entries(api.initialState.extras.guestbook||{}).every(([id,record])=>JSON.stringify(next.extras.guestbook[id])===JSON.stringify(record))},
 {name:'Current data renders',ok:api.render(api.initialState,actor).includes('thought')}
 ];
}`;
let callSequence = 0;
const output = () => ({ model: 'test-model', service_tier: 'ultrafast', output: [
  { type: 'function_call', call_id: `auth-call-${++callSequence}`, name: 'apply_change', arguments: JSON.stringify({ source, tests: checks, summary: 'A shared guestbook' }) },
], metrics: { durationMs: 5, ttftMs: 1, outputTokens: 10, servedTier: 'ultrafast' } });
const adapter = (respond = async () => output()) => ({ keyAvailable: true, model: 'test-model', tier: 'ultrafast', respond });

async function start(dataDir, options = {}) {
  const instance = await createApp({ dataDir, adapter: adapter(), ...options });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { token, json, method, headers, ...rest } = {}) => fetch(`${base}${path}`, {
    method: method || (json === undefined ? 'GET' : 'POST'), ...rest,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json' }), ...headers },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }),
  });
  const signIn = async (input) => {
    const response = await request('/api/auth/sign-in', { json: input });
    assert.equal(response.status, 200);
    return response.json();
  };
  return { ...instance, base, request, signIn, async stop() {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    await instance.close();
  } };
}
async function fixture(t, options) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-auth-'));
  const instance = await start(dataDir, options);
  t.after(async () => { await instance.stop(); await rm(dataDir, { recursive: true, force: true }); });
  return { ...instance, dataDir };
}

test('every space route requires a bearer identity, including old API aliases', async (t) => {
  const { request, signIn } = await fixture(t);
  assert.equal((await request('/api/auth/people')).status, 200);
  const paths = ['/api/space', '/api/events', '/api/revisions', '/api/spaces', '/api/spaces/mira', '/api/spaces/mira/events', '/api/spaces/mira/revisions'];
  for (const path of paths) assert.equal((await request(path)).status, 401, path);
  for (const path of ['/api/turn', '/api/action', '/api/reset', '/api/restore', '/api/cancel', '/api/spaces/mira/turn']) {
    assert.equal((await request(path, { json: {} })).status, 401, path);
  }
  assert.equal((await request('/api/space', { token: 'a'.repeat(43) })).status, 401);
  assert.equal((await request('/api/auth/sign-in', { json: { userId: '../../escape' } })).status, 404);
  assert.equal((await request('/api/auth/sign-in', { json: { name: '<script>' } })).status, 400);
  const mira = await signIn({ userId: 'mira' });
  assert.equal(mira.simulated, true);
  assert.match(mira.token, /^[A-Za-z0-9_-]{43}$/);
  const verified = await request('/api/auth/session', { token: mira.token });
  assert.deepEqual((await verified.json()).user, { id: 'mira', name: 'Mira' });
  assert.equal((await request('/api/spaces/mira/reset', { token: mira.token, json: {}, headers: { Origin: 'https://attacker.example' } })).status, 403);
  assert.equal((await request('/api/spaces/%2E%2E%2Fsecret', { token: mira.token })).status, 404);
});

test('new people receive genuinely blank isolated spaces while the original studio stays intact', async (t) => {
  const { request, signIn, directory, service, dataDir } = await fixture(t);
  const original = service.store.read();
  const person = await signIn({ name: '  Nova  ' });
  assert.equal(person.user.name, 'Nova');
  assert.match(person.ownSpaceId, /^space_[a-f0-9-]{36}$/);
  const response = await request(`/api/spaces/${person.ownSpaceId}`, { token: person.token });
  const blank = await response.json();
  assert.deepEqual(blank.state, { projects: [], contributions: [], extras: {} });
  assert.equal(blank.html, '');
  assert.equal(blank.space.kind, 'blank');
  assert.equal(blank.permissions.canEdit, true);
  assert.notEqual(blank.session.id, original.session.id);
  const newService = await directory.serviceFor(person.ownSpaceId);
  const turn = await request(`/api/spaces/${person.ownSpaceId}/turn`, { token: person.token, json: { message: 'Make a guestbook' } });
  assert.equal(turn.status, 202);
  await newService.waitForIdle();
  assert.equal(newService.store.read().currentRevisionId, 2);
  assert.deepEqual(service.store.read(), original);
  const disk = JSON.parse(await readFile(join(dataDir, 'spaces', person.ownSpaceId, 'space.json'), 'utf8'));
  assert.equal(disk.session.turns[0].message, 'Make a guestbook');
  assert.equal(JSON.parse(await readFile(join(dataDir, 'space.json'), 'utf8')).session.id, original.session.id);
  const catalog = await (await request('/api/spaces', { token: person.token })).json();
  assert.equal(catalog.spaces.find((space) => space.id === person.ownSpaceId).hasBuilt, true);
  assert.equal(catalog.spaces.find((space) => space.id === 'leo').kind, 'blank');
});

test('visitors cannot edit another space or read its private runtime, and actions use the verified actor', async (t) => {
  const { request, signIn, service } = await fixture(t);
  const mira = await signIn({ userId: 'mira' });
  const leo = await signIn({ userId: 'leo' });
  await service.submit('A private owner prompt'); await service.waitForIdle();
  for (const path of ['turn', 'cancel', 'reset', 'restore']) {
    const response = await request(`/api/spaces/mira/${path}`, { token: leo.token, json: { message: 'Forged', revisionId: 1, actor: 'mira' } });
    assert.equal(response.status, 403, path);
  }
  assert.equal((await request('/api/spaces/mira/revisions', { token: leo.token })).status, 403);
  const owner = await (await request('/api/spaces/mira', { token: mira.token })).json();
  assert.equal(owner.session.turnCount, 1);
  assert.equal(owner.session.lastMessage, 'A private owner prompt');
  assert.equal(owner.revision.source, source);
  const publicSpace = await (await request('/api/spaces/mira?actor=mira', { token: leo.token })).json();
  assert.equal(publicSpace.actor.id, 'leo');
  assert.equal(publicSpace.permissions.canEdit, false);
  for (const key of ['source', 'tests', 'checks']) assert.equal(publicSpace.revision[key], undefined);
  for (const key of ['id', 'turns', 'turnCount', 'lastMessage']) assert.equal(publicSpace.session[key], undefined);
  assert.ok(publicSpace.events.every((event) => ['space.updated', 'revision.published', 'space.reset'].includes(event.type)));
  assert.ok(!JSON.stringify(publicSpace).includes('A private owner prompt'));
  const action = await request('/api/spaces/mira/action', { token: leo.token, json: {
    actor: 'mira', revisionId: 2, action: { type: 'leave', actorId: 'mira', text: 'A visitor joined' },
  } });
  assert.equal(action.status, 200);
  const state = (await action.json()).state;
  assert.deepEqual(state.extras.guestbook.leo, { actorId: 'leo', text: 'A visitor joined' });
  assert.equal(state.extras.guestbook.mira, undefined);
  assert.equal((await (await request('/api/space?actor=mira', { token: leo.token })).json()).space.id, 'leo');
});

test('a returning account resumes its persistent thread after sign-out and a server restart', async (t) => {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-return-'));
  let active = await start(dataDir);
  t.after(async () => { await active.stop(); await rm(dataDir, { recursive: true, force: true }); });
  const first = await active.signIn({ name: 'Returning person' });
  const space = await active.directory.serviceFor(first.ownSpaceId);
  await space.submit('Build my own guestbook'); await space.waitForIdle();
  const sessionId = space.store.read().session.id;
  assert.equal((await active.request('/api/auth/sign-out', { token: first.token, json: {} })).status, 200);
  assert.equal((await active.request('/api/auth/session', { token: first.token })).status, 401);
  await active.stop();
  active = await start(dataDir);
  assert.equal((await active.request('/api/auth/session', { token: first.token })).status, 401);
  const second = await active.signIn({ userId: first.user.id });
  assert.equal(second.ownSpaceId, first.ownSpaceId);
  const restored = await (await active.request(`/api/spaces/${second.ownSpaceId}`, { token: second.token })).json();
  assert.equal(restored.session.id, sessionId);
  assert.equal(restored.revision.id, 2);
  assert.equal(restored.session.turnCount, 1);
  const resumed = await active.directory.serviceFor(second.ownSpaceId);
  await resumed.submit('Keep evolving it'); await resumed.waitForIdle();
  assert.equal(resumed.store.read().session.id, sessionId);
  assert.equal(resumed.store.read().session.turns.length, 2);
});

test('visitor event streams redact private events and sign-out immediately closes their connection', async (t) => {
  const { request, signIn, service } = await fixture(t);
  const leo = await signIn({ userId: 'leo' });
  await service.store.emit({ type: 'model.delta', turnId: 'private-thread', title: 'Private thinking', data: { sourcePreview: 'secret source' } });
  await service.store.emit({ type: 'revision.published', turnId: 'private-thread', title: 'A private owner prompt', data: { revisionId: 2, source: 'secret source' } });
  const stream = await request('/api/spaces/mira/events', { token: leo.token, signal: AbortSignal.timeout(3000) });
  assert.equal(stream.status, 200);
  const reader = stream.body.getReader();
  let received = '';
  while (!received.includes('revision.published')) received += new TextDecoder().decode((await reader.read()).value);
  assert.ok(received.includes(': connected'));
  assert.ok(!/private-thread|secret source|Private thinking|private owner prompt/.test(received));
  await request('/api/auth/sign-out', { token: leo.token, json: {} });
  assert.equal((await reader.read()).done, true);
  assert.equal((await request('/api/spaces/mira', { token: leo.token })).status, 401);
});

test('expired identities close event streams and sign-out leaves in-flight work running', async (t) => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const { request, signIn, service } = await fixture(t, { sessionTtlMs: 400, adapter: adapter(async () => { await gate; return output(); }) });
  const mira = await signIn({ userId: 'mira' });
  const stream = await request('/api/spaces/mira/events', { token: mira.token, signal: AbortSignal.timeout(3000) });
  const reader = stream.body.getReader();
  assert.match(new TextDecoder().decode((await reader.read()).value), /connected/);
  assert.equal((await reader.read()).done, true);
  assert.equal((await request('/api/auth/session', { token: mira.token })).status, 401);
  const fresh = await signIn({ userId: 'mira' });
  assert.equal((await request('/api/spaces/mira/turn', { token: fresh.token, json: { message: 'Build while I am away' } })).status, 202);
  await request('/api/auth/sign-out', { token: fresh.token, json: {} });
  assert.equal(service.busy, true);
  release(); await service.waitForIdle();
  assert.equal(service.store.read().currentRevisionId, 2);
});
