import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createSocialGraph } from '../server/social.mjs';

const ids = ['mira', 'james', 'jake', 'erica', 'leo'];
const status = (expected) => (error) => error.status === expected;
async function fixture(t, options = {}) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-social-'));
  const graph = await createSocialGraph({ dataDir, hasPerson: (id) => ids.includes(id), ...options });
  t.after(async () => { await graph.close(); await rm(dataDir, { recursive: true, force: true }); });
  return { graph, dataDir };
}

test('the sample graph exposes symmetric accepted edges and leaves Mira-James available for a real request', async (t) => {
  const { graph } = await fixture(t);
  const mira = graph.snapshot('mira');
  assert.equal(mira.connections.length, 4);
  assert.ok(mira.connections.every((edge) => edge.source < edge.target));
  assert.equal(mira.connections.some((edge) => [edge.source, edge.target].includes('mira') && [edge.source, edge.target].includes('james')), false);
  assert.deepEqual(graph.snapshot('james').connections, mira.connections);
  assert.deepEqual(mira.requests, { incoming: [], outgoing: [] });
  mira.connections.length = 0;
  assert.equal(graph.snapshot('mira').connections.length, 4, 'callers cannot mutate the graph through its snapshot');
});

test('a fresh nine-person community preserves the example connections and leaves new friendships available', async (t) => {
  const people = [...ids, 'iris', 'luca', 'karen', 'nora'];
  const { graph } = await fixture(t, { hasPerson: (id) => people.includes(id) });
  const expected = [
    'friend:erica:mira', 'friend:erica:james', 'friend:erica:jake', 'friend:jake:james',
    'friend:iris:mira', 'friend:iris:luca', 'friend:erica:luca',
  ].sort();
  assert.deepEqual(graph.snapshot('iris').connections.map((edge) => edge.id).sort(), expected);
  assert.deepEqual(graph.snapshot('luca').connections, graph.snapshot('iris').connections);
  assert.ok(graph.snapshot('leo').connections.every((edge) => edge.source !== 'leo' && edge.target !== 'leo'));
  assert.deepEqual(graph.snapshot('luca').requests, { incoming: [], outgoing: [] });
  assert.deepEqual(graph.snapshot('karen').connections, graph.snapshot('iris').connections);
  assert.deepEqual(graph.snapshot('karen').requests, { incoming: [], outgoing: [] });
  assert.deepEqual(graph.snapshot('nora').connections, graph.snapshot('iris').connections);
  assert.deepEqual(graph.snapshot('nora').requests, { incoming: [], outgoing: [] });
});

test('adding example identities never adds or restores edges in a saved community', async (t) => {
  const { graph, dataDir } = await fixture(t);
  await graph.removeFriend('mira', 'erica');
  const pending = await graph.requestFriend('mira', 'james');
  const before = graph.snapshot('mira');
  const filename = join(dataDir, 'community.json');
  const saved = await readFile(filename, 'utf8');
  await graph.close();

  const people = [...ids, 'iris', 'luca', 'karen', 'nora'];
  const reopened = await createSocialGraph({ dataDir, hasPerson: (id) => people.includes(id) });
  t.after(() => reopened.close());
  assert.equal(await readFile(filename, 'utf8'), saved, 'existing community data is not rewritten');
  assert.deepEqual(reopened.snapshot('mira'), before);
  assert.equal(reopened.snapshot('james').requests.incoming[0].id, pending.id);
  for (const person of ['iris', 'luca', 'karen', 'nora']) {
    assert.deepEqual(reopened.snapshot(person), { connections: before.connections, requests: { incoming: [], outgoing: [] } });
    assert.ok(before.connections.every((edge) => edge.source !== person && edge.target !== person));
  }
});

test('requests are private to both people, duplicates are idempotent, and crossing requests do not auto-accept', async (t) => {
  const { graph } = await fixture(t, { initialConnections: [] });
  const [first, repeated, crossing] = await Promise.all([
    graph.requestFriend('mira', 'james'), graph.requestFriend('mira', 'james'), graph.requestFriend('james', 'mira'),
  ]);
  assert.equal(repeated.id, first.id);
  assert.equal(crossing.id, first.id);
  assert.equal(graph.snapshot('mira').requests.outgoing.length, 1);
  assert.equal(graph.snapshot('james').requests.incoming[0].fromId, 'mira');
  assert.deepEqual(graph.snapshot('leo').requests, { incoming: [], outgoing: [] });
  assert.equal(graph.snapshot('mira').connections.length, 0);
  await assert.rejects(() => graph.respondFriend('mira', first.id, 'accept'), status(403));
  await assert.rejects(() => graph.respondFriend('leo', first.id, 'accept'), status(404));
  await graph.respondFriend('james', first.id, 'accept');
  await graph.respondFriend('james', first.id, 'accept');
  assert.deepEqual(graph.snapshot('mira').connections, [{ id: 'friend:james:mira', source: 'james', target: 'mira' }]);
  assert.deepEqual(graph.snapshot('mira').requests, { incoming: [], outgoing: [] });
  assert.deepEqual(await graph.requestFriend('mira', 'james'), { status: 'connected' });
  assert.equal(graph.snapshot('james').connections.length, 1);
});

test('only recipients decline, only senders cancel, and a resolved request can be retried as a new request', async (t) => {
  const { graph } = await fixture(t, { initialConnections: [] });
  const first = await graph.requestFriend('mira', 'jake');
  await assert.rejects(() => graph.respondFriend('mira', first.id, 'decline'), status(403));
  await assert.rejects(() => graph.respondFriend('jake', first.id, 'cancel'), status(403));
  await graph.respondFriend('jake', first.id, 'decline');
  await graph.respondFriend('jake', first.id, 'decline');
  await assert.rejects(() => graph.respondFriend('jake', first.id, 'accept'), status(409));
  assert.deepEqual(graph.snapshot('mira').requests, { incoming: [], outgoing: [] });
  const next = await graph.requestFriend('mira', 'jake');
  assert.notEqual(next.id, first.id);
  await graph.respondFriend('mira', next.id, 'cancel');
  await graph.respondFriend('mira', next.id, 'cancel');
  assert.deepEqual(graph.snapshot('jake').requests, { incoming: [], outgoing: [] });
  assert.equal(graph.snapshot('jake').connections.length, 0);
});

test('invalid identities, self-connections, unknown request IDs and unknown decisions are refused', async (t) => {
  const { graph } = await fixture(t);
  await assert.rejects(async () => graph.requestFriend('mira', 'mira'), status(400));
  await assert.rejects(async () => graph.requestFriend('unknown', 'mira'), status(401));
  for (const target of ['unknown', '../mira', '__proto__', 'constructor', null, ['james'], { id: 'james' }]) {
    await assert.rejects(async () => graph.requestFriend('mira', target), status(404));
  }
  await assert.rejects(async () => graph.respondFriend('mira', 'unknown', 'accept'), status(404));
  await assert.rejects(async () => graph.respondFriend('mira', 'unknown', 'autoaccept'), status(400));
  assert.throws(() => graph.snapshot('unknown'), status(401));
  assert.equal(graph.snapshot('mira').connections.length, 4);
});

test('concurrent acceptance, cancellation and retries cannot duplicate or resurrect an edge', async (t) => {
  const { graph } = await fixture(t, { initialConnections: [] });
  const requests = await Promise.all(Array.from({ length: 20 }, (_, index) => index % 2 ? graph.requestFriend('james', 'mira') : graph.requestFriend('mira', 'james')));
  assert.equal(new Set(requests.map(request => request.id)).size, 1);
  const request = requests[0];
  const results = await Promise.allSettled([
    graph.respondFriend('james', request.id, 'accept'),
    graph.respondFriend('mira', request.id, 'cancel'),
    graph.respondFriend('james', request.id, 'accept'),
  ]);
  assert.equal(results[0].status, 'fulfilled');
  assert.equal(results[1].status, 'rejected');
  assert.equal(results[1].reason.status, 409);
  assert.equal(results[2].status, 'fulfilled');
  assert.equal(graph.snapshot('mira').connections.length, 1);
  await graph.removeFriend('mira', 'james');
  await graph.respondFriend('james', request.id, 'accept');
  assert.equal(graph.snapshot('mira').connections.length, 0, 'replaying an old acceptance never reconnects someone');
  const fresh = await graph.requestFriend('mira', 'james');
  assert.notEqual(fresh.id, request.id);
  assert.equal(graph.snapshot('mira').connections.length, 0, 'reconnecting requires new acceptance');
});

test('newly registered identities can join the graph without opening cross-person mutation permissions', async (t) => {
  const people = new Set(ids);
  const { graph } = await fixture(t, { hasPerson: id => people.has(id), initialConnections: [] });
  const personId = 'person_5ce2fc82-2f51-4a15-8c17-19b0b5b97703';
  people.add(personId);
  const request = await graph.requestFriend(personId, 'mira');
  await graph.respondFriend('mira', request.id, 'accept');
  assert.equal(graph.snapshot(personId).connections.length, 1);
  await graph.removeFriend('leo', 'mira');
  assert.equal(graph.snapshot(personId).connections.length, 1, 'a third person can only remove their own edges');
  await graph.removeFriend(personId, 'mira');
  assert.equal(graph.snapshot('mira').connections.length, 0);
});

test('acceptance, pending requests and removal survive restart without restoring removed sample edges', async (t) => {
  const { graph, dataDir } = await fixture(t);
  const request = await graph.requestFriend('mira', 'james');
  await graph.respondFriend('james', request.id, 'accept');
  const pending = await graph.requestFriend('leo', 'jake');
  await graph.removeFriend('mira', 'erica');
  const before = graph.snapshot('leo');
  await graph.close();
  const reopened = await createSocialGraph({ dataDir, hasPerson: (id) => ids.includes(id) });
  t.after(() => reopened.close());
  assert.deepEqual(reopened.snapshot('leo'), before);
  assert.equal(reopened.snapshot('jake').requests.incoming[0].id, pending.id);
  assert.equal(reopened.snapshot('mira').connections.some((edge) => edge.id === 'friend:erica:mira'), false);
  assert.equal(reopened.snapshot('james').connections.some((edge) => edge.id === 'friend:james:mira'), true);
  await reopened.removeFriend('james', 'mira');
  assert.equal(reopened.snapshot('mira').connections.some((edge) => edge.id === 'friend:james:mira'), false);
  await assert.rejects(() => graph.requestFriend('leo', 'mira'), status(503));
});

test('identity migration adds demo people without changing generated accounts or existing identity records', async (t) => {
  const { createSpaceDirectory } = await import('../server/identity.mjs');
  const { createSpaceService } = await import('../server/harness.mjs');
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-personas-'));
  let close = async () => {};
  t.after(async () => { await close(); await rm(dataDir, { recursive: true, force: true }); });
  const prior = { version: 1, users: [
    { id: 'mira', name: 'Mira', ownSpaceId: 'mira', kind: 'studio' },
    { id: 'leo', name: 'Leo', ownSpaceId: 'leo', kind: 'blank' },
    { id: 'person_5ce2fc82-2f51-4a15-8c17-19b0b5b97703', name: 'Iris', ownSpaceId: 'space_2813702b-11d1-4b59-ac27-a481cd834026', kind: 'blank' },
  ] };
  await writeFile(join(dataDir, 'identities.json'), JSON.stringify(prior));
  const existingOwner = prior.users[2];
  const savedSource = `export const meta={title:'Iris saved garden',subtitle:'A place to grow',accent:'#687957',layout:'canvas'};
    export function render(){return '<p>Iris saved garden</p>'}
    export function reduce(){throw Error('Unknown action')}`;
  const savedTests = `export function runTests(api){
    const actor={id:'saved-garden-test',name:'A visitor'};
    let blocked=false;try{api.reduce(api.initialState,{type:'unknown'},actor)}catch{blocked=true}
    return [{name:'Saved page renders',ok:api.render(api.initialState,actor).includes('saved garden')},
      {name:'Unknown actions are blocked',ok:blocked},
      {name:'Blank catalog remains valid',ok:api.initialState.projects.length===0},
      {name:'Title remains intact',ok:api.meta.title==='Iris saved garden'}]}`;
  const existing = await createSpaceService({ dataDir: join(dataDir, 'spaces', existingOwner.ownSpaceId),
    owner: { id: existingOwner.id, name: existingOwner.name }, kind: 'blank', adapter: { keyAvailable: true,
      respond: async () => ({ output: [{ type: 'function_call', call_id: 'save-iris', name: 'apply_change',
        arguments: JSON.stringify({ source: savedSource, tests: savedTests, summary: 'Iris saved garden' }) }] }) } });
  close = () => existing.close();
  await existing.submit('Keep my own garden'); await existing.waitForIdle();
  const savedGarden = JSON.parse(JSON.stringify(existing.store.read()));
  assert.equal(savedGarden.currentRevisionId, 2);
  await existing.close();
  const directory = await createSpaceDirectory({ dataDir, adapter: { keyAvailable: false, respond: () => { throw Error('No model calls in identity tests'); } } });
  close = () => directory.close();
  const disk = JSON.parse(await readFile(join(dataDir, 'identities.json'), 'utf8'));
  assert.deepEqual(disk.users.slice(0, 3), prior.users);
  assert.deepEqual(disk.users.slice(3).map((person) => person.id), ['james', 'jake', 'erica', 'iris', 'luca', 'karen', 'nora']);
  assert.deepEqual(directory.people().map((person) => person.id), ['mira', 'james', 'jake', 'erica', 'leo', 'iris', 'luca', 'karen', 'nora', prior.users[2].id]);
  assert.equal(directory.people().find((person) => person.id === 'jake').profile.role, 'Nurse');
  assert.equal(directory.people().find((person) => person.id === 'iris').profile.role, 'Painter');
  assert.equal(directory.people().find((person) => person.id === 'luca').profile.role, 'Language teacher');
  assert.equal(directory.people().filter(person => person.name === 'Iris').length, 2, 'The default painter never replaces a person who already uses the same display name.');
  const leo = await directory.serviceFor('leo');
  assert.deepEqual(leo.store.read().state, { projects: [], contributions: [], extras: {} });
  const generated = await directory.serviceFor(prior.users[2].ownSpaceId);
  assert.deepEqual(generated.store.read(), savedGarden, 'adding personas preserves a generated canvas and its entire builder history');
  assert.equal(leo.store.read().ownerId, 'leo');
  assert.equal(generated.store.read().ownerId, prior.users[2].id);
});

for (const baselineSize of [5, 7, 8]) test(`upgrading the ${baselineSize}-person registry adds new defaults once while retaining existing names, accounts and graph`, async t => {
  const { createSpaceDirectory, demoUsers } = await import('../server/identity.mjs');
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-new-defaults-'));
  let directory;
  t.after(async () => { await directory?.close(); await rm(dataDir, { recursive: true, force: true }); });
  const existingPerson = { id: 'person_5ce2fc82-2f51-4a15-8c17-19b0b5b97703', name: 'Karen',
    ownSpaceId: 'space_2813702b-11d1-4b59-ac27-a481cd834026', kind: 'blank' };
  const prior = { version: 1, users: [...demoUsers.slice(0, baselineSize).map(person => ({ ...person })), existingPerson] };
  prior.users[0].name = 'Mira’s saved name';
  const filename = join(dataDir, 'identities.json');
  await writeFile(filename, JSON.stringify(prior));
  const graphFile = join(dataDir, 'community.json');
  const originalGraph = JSON.stringify({ version: 1, connections: [{ id: 'friend:james:mira', source: 'james', target: 'mira' }], requests: [] });
  await writeFile(graphFile, originalGraph);
  const options = { dataDir, adapter: { keyAvailable: false, respond() { assert.fail('Identity migration does not generate pages.'); } } };
  directory = await createSpaceDirectory(options);
  const upgraded = await readFile(filename, 'utf8');
  assert.deepEqual(JSON.parse(upgraded).users, [...prior.users, ...demoUsers.slice(baselineSize)]);
  assert.equal(directory.people().filter(person => person.name === 'Karen').length, 2);
  const iris = await directory.metadata('iris');
  const luca = await directory.metadata('luca');
  assert.deepEqual(iris.owner, { id: 'iris', name: 'Iris' });
  assert.equal(iris.profile.role, 'Painter');
  assert.equal(iris.hasBuilt, false);
  assert.equal(luca.profile.role, 'Language teacher');
  assert.equal(luca.hasBuilt, false);
  const karen = await directory.metadata('karen');
  assert.equal(karen.profile.role, 'Arcade enthusiast');
  assert.equal(karen.profile.theme, 'retro-arcade');
  assert.deepEqual(karen.owner, { id: 'karen', name: 'Karen' });
  assert.equal(karen.hasBuilt, false);
  assert.equal(await readFile(graphFile, 'utf8'), originalGraph, 'Adding a demo identity does not reseed existing relationships.');
  await directory.close();
  directory = await createSpaceDirectory(options);
  assert.equal(await readFile(filename, 'utf8'), upgraded, 'Restart does not append duplicate people or rewrite saved identity data.');
  assert.equal(directory.people().find(person => person.id === 'mira').name, 'Mira’s saved name');
  assert.equal(directory.people().some(person => person.id === existingPerson.id), true);
  assert.equal(await readFile(graphFile, 'utf8'), originalGraph);
});

test('friend APIs require sign-in and derive request ownership from the bearer session', async (t) => {
  const { createApp } = await import('../server/index.mjs');
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-social-http-'));
  const instance = await createApp({ dataDir, adapter: { keyAvailable: false, respond: () => { throw Error('No model calls in social tests'); } } });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(async () => {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    await instance.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  const endpoint = `http://127.0.0.1:${server.address().port}`;
  const request = (path, token, body) => fetch(endpoint + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  assert.equal((await request('/api/community')).status, 401);
  for (const path of ['/api/friends/request', '/api/friends/respond', '/api/friends/remove']) {
    assert.equal((await request(path, null, {})).status, 401);
  }
  const mira = await (await request('/api/auth/sign-in', null, { userId: 'mira' })).json();
  const james = await (await request('/api/auth/sign-in', null, { userId: 'james' })).json();
  const leo = await (await request('/api/auth/sign-in', null, { userId: 'leo' })).json();
  const sent = await request('/api/friends/request', mira.token, { targetId: 'james', actorId: 'james', fromId: 'leo' });
  assert.equal(sent.status, 200);
  const after = await sent.json();
  const pending = after.requests.outgoing[0];
  assert.equal(pending.fromId, 'mira');
  assert.equal(pending.toId, 'james');
  assert.equal(after.spaces.find((space) => space.id === 'james').hasBuilt, false);
  assert.equal(after.spaces.find((space) => space.id === 'james').profile.role, 'Finance professional');
  const jamesView = await (await request('/api/community', james.token)).json();
  assert.equal(jamesView.requests.incoming[0].id, pending.id);
  const leoView = await (await request('/api/community', leo.token)).json();
  assert.deepEqual(leoView.requests, { incoming: [], outgoing: [] });
  assert.equal((await request('/api/friends/respond', mira.token, { requestId: pending.id, decision: 'accept', actorId: 'james' })).status, 403);
  assert.equal((await request('/api/friends/respond', leo.token, { requestId: pending.id, decision: 'accept', actorId: 'james' })).status, 404);
  const accepted = await request('/api/friends/respond', james.token, { requestId: pending.id, decision: 'accept' });
  assert.equal(accepted.status, 200);
  assert.ok((await accepted.json()).connections.some((edge) => edge.id === 'friend:james:mira'));
  const removed = await request('/api/friends/remove', mira.token, { targetId: 'james' });
  assert.equal(removed.status, 200);
  assert.equal((await removed.json()).connections.some((edge) => edge.id === 'friend:james:mira'), false);
});
