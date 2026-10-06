import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, rename, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { request as httpRequest } from 'node:http';
import { createHash } from 'node:crypto';
import { createApp } from '../server/index.mjs';
import { demoUsers } from '../server/identity.mjs';
import { demoConnections } from '../server/social.mjs';
import { beginDemoReset, recoverDemoReset } from '../server/demo-reset.mjs';
import { arcadeProposal } from '../server/arcade/index.mjs';
import { meta as arcadeMeta } from '../server/arcade/page.mjs';
import { pacmanGame } from '../server/arcade/pacman.mjs';
import { invadersGame } from '../server/arcade/invaders.mjs';
import { snakeGame } from '../server/arcade/snake.mjs';
import { tetrisGame } from '../server/arcade/tetris.mjs';
import { communityBoardSource } from '../server/community-board.mjs';

const source = `export const meta={title:'Prepared garden',subtitle:'',layout:'canvas',accent:'#687957'};
export function render(state,actor){return '<main>Prepared garden. A place for notes.</main>'}
export function reduce(state,action,actor){
 if(action.type!=='leave'||typeof action.text!=='string'||!action.text.trim()||action.text.length>80)throw Error('Invalid note');
 state.extras.notes=state.extras.notes||{};
 state.extras.notes[actor.id]={actorId:actor.id,text:action.text.trim()};return state;
}`;
const checks = `export function runTests(api){
 const actor={id:'test-new-person',name:'Test person'};
 const next=api.reduce(api.initialState,{type:'leave',text:'A little wonder'},actor);
 let blocked=false;try{api.reduce(api.initialState,{type:'leave',text:''},actor)}catch{blocked=true}
 return [
 {name:'Visitors can leave a note',ok:next.extras.notes[actor.id].text==='A little wonder'},
 {name:'Empty notes are refused',ok:blocked},
 {name:'Other notes remain intact',ok:Object.entries(api.initialState.extras.notes||{}).every(([id,note])=>JSON.stringify(next.extras.notes[id])===JSON.stringify(note))},
 {name:'Current data renders',ok:api.render(api.initialState,actor).includes('notes')}
 ];
}`;
const defaultIds = demoUsers.map(person => person.id);
const adapter = { keyAvailable: true, model: 'test-model', tier: 'ultrafast', respond: async () => ({ output: [] }) };
const seedOverride = { source, tests: checks, state: { projects: [], contributions: [], extras: {} } };
const readJson = async filename => JSON.parse(await readFile(filename, 'utf8'));
const post = { confirmation: 'reset-demo' };

async function start(dataDir, options = {}) {
  const instance = await createApp({ dataDir, adapter, seedOverride, ...options });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { token, json, headers, ...rest } = {}) => fetch(`${base}${path}`, {
    method: json === undefined ? 'GET' : 'POST', ...rest,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json', Origin: base }), ...headers },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }),
  });
  const signIn = async input => {
    const response = await request('/api/auth/sign-in', { json: input });
    assert.equal(response.status, 200, await response.clone().text());
    return response.json();
  };
  return { instance, base, request, signIn, async stop() {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await instance.close();
  } };
}

async function fixture(t, options) {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-reset-'));
  const dataDir = join(parent, 'data');
  const running = await start(dataDir, options);
  t.after(async () => { await running.stop(); await rm(parent, { recursive: true, force: true }); });
  return { ...running, dataDir };
}

async function legacyBaseline(running, size = 5) {
  assert.equal((await running.request('/api/demo/reset', { json: post })).status, 200);
  const filename = join(`${running.dataDir}-reset-history`, 'baseline.json');
  const baseline = await readJson(filename);
  const originalIds = defaultIds.slice(0, size);
  baseline.users = baseline.users.filter(person => originalIds.includes(person.id));
  for (const id of defaultIds.slice(size)) {
    delete baseline.spaces[id];
    delete baseline.prepared[id];
  }
  await writeFile(filename, JSON.stringify(baseline));
  return { baseline, filename };
}

test('reset restores the default neighborhood, removes added accounts and records, and backs up the whole prior demo', async t => {
  const { instance, request, signIn, dataDir } = await fixture(t);
  const mira = await signIn({ userId: 'mira' });
  const added = await signIn({ name: 'New explorer' });
  const beforeId = instance.service.store.read().session.id;
  for (const person of [mira, added]) {
    const result = await request('/api/spaces/mira/action', { token: person.token, json: { revisionId: 1, action: { type: 'leave', text: person.user.name } } });
    assert.equal(result.status, 200);
  }
  await request('/api/friends/request', { token: added.token, json: { targetId: 'mira' } });
  const pending = await (await request('/api/community', { token: mira.token })).json();
  await request('/api/friends/respond', { token: mira.token, json: { requestId: pending.requests.incoming[0].id, decision: 'accept' } });
  await request('/api/friends/request', { token: mira.token, json: { targetId: 'james' } });
  await writeFile(join(dataDir, 'custom-debug-file.txt'), 'Preserve all old data in the backup.');

  const result = await request('/api/demo/reset', { json: post });
  assert.equal(result.status, 200, await result.clone().text());
  assert.deepEqual((await result.json()).users.map(person => person.id), defaultIds);
  assert.equal((await request('/api/auth/session', { token: mira.token })).status, 401);
  assert.equal((await request('/api/auth/session', { token: added.token })).status, 401);
  assert.equal((await request('/api/auth/sign-in', { json: { userId: added.user.id } })).status, 404);
  const fresh = await signIn({ userId: 'mira' });
  const snapshot = await (await request('/api/spaces/mira', { token: fresh.token })).json();
  assert.equal(snapshot.revision.source, source);
  assert.notEqual(snapshot.session.id, beforeId);
  assert.deepEqual(snapshot.state.extras.notes, { mira: { actorId: 'mira', text: 'Mira' } });
  const community = await (await request('/api/community', { token: fresh.token })).json();
  assert.deepEqual(community.connections.map(edge => [edge.source, edge.target]).sort(), demoConnections.map(pair => [...pair].sort()).sort());
  assert.deepEqual(community.requests, { incoming: [], outgoing: [] });
  assert.deepEqual((await readdir(join(dataDir, 'spaces'))).sort(), defaultIds.filter(id => id !== 'mira').sort());
  const backups = await readdir(join(`${dataDir}-reset-history`, 'backups'));
  assert.equal(backups.length, 1);
  const backup = join(`${dataDir}-reset-history`, 'backups', backups[0]);
  assert.equal((await readJson(join(backup, 'identities.json'))).users.length, defaultIds.length + 1);
  assert.equal(await readFile(join(backup, 'custom-debug-file.txt'), 'utf8'), 'Preserve all old data in the backup.');
  assert.ok((await readJson(join(backup, 'space.json'))).state.extras.notes[added.user.id]);
});

test('prepared revisions and their matching thread are restored instead of later edits or blank seeds', async t => {
  const { instance, request, signIn, dataDir } = await fixture(t);
  const person = await signIn({ userId: 'james' });
  const service = await instance.directory.serviceFor('james');
  const preparedTurn = { id: 'prepared-turn', message: 'Build the garden', status: 'completed', revisionId: 2 };
  const laterTurn = { id: 'later-turn', message: 'Make everything purple', status: 'completed', revisionId: 3 };
  await service.store.transact(data => {
    const base = data.revisions[0];
    data.revisions.push({ ...base, id: 2, source: source.replaceAll('Prepared garden', 'Generated garden') }, { ...base, id: 3, source: source.replaceAll('Prepared garden', 'Later edit') });
    data.currentRevisionId = 3;
    data.session.turns = [preparedTurn, laterTurn];
    data.session.items = [
      { role: 'user', content: `Owner's request: ${preparedTurn.message}\n\nCurrent workspace and live state (authoritative for this turn):\n${JSON.stringify({ state: data.state })}` },
      { type: 'function_call', call_id: 'call-prepared', name: 'apply_change', arguments: '{}' },
      { type: 'function_call_output', call_id: 'call-prepared', output: '{"ok":true}' },
      { role: 'user', content: `Owner's request: ${laterTurn.message}\n\nCurrent workspace and live state (authoritative for this turn):\n${JSON.stringify({ state: data.state })}` },
    ];
  });
  const data = service.store.read();
  const prepared = data.revisions.find(revision => revision.id === 2);
  await writeFile(join(dataDir, 'demo-preparation.json'), JSON.stringify({ version: 1, prepared: { james: {
    sessionId: data.session.id, turnId: preparedTurn.id, revisionId: 2,
    sourceHash: createHash('sha256').update(`${prepared.source}\n${prepared.tests}`).digest('hex'),
  } } }));
  assert.equal((await request('/api/demo/reset', { json: post })).status, 200);
  const restored = (await instance.directory.serviceFor('james')).store.read();
  assert.equal(restored.currentRevisionId, 2);
  assert.equal(restored.revisions.at(-1).source, prepared.source);
  assert.deepEqual(restored.session.turns, [preparedTurn]);
  assert.equal(restored.session.items.length, 3);
  assert.equal(JSON.stringify(restored).includes(laterTurn.message), false);
  assert.equal((await request('/api/auth/session', { token: person.token })).status, 401);
  assert.equal((await readJson(join(dataDir, 'demo-preparation.json'))).prepared.james.sessionId, restored.session.id);
});

test('a second reset uses the immutable baseline and a restarted server keeps the reset result', async t => {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-reset-restart-'));
  const dataDir = join(parent, 'data');
  let running = await start(dataDir);
  t.after(async () => { await running.stop(); await rm(parent, { recursive: true, force: true }); });
  await running.signIn({ name: 'First visitor' });
  assert.equal((await running.request('/api/demo/reset', { json: post })).status, 200);
  const baselineBefore = await readFile(join(`${dataDir}-reset-history`, 'baseline.json'), 'utf8');
  const firstThread = running.instance.service.store.read().session.id;
  await running.instance.service.store.transact(data => {
    data.revisions[0].source = source.replaceAll('Prepared garden', 'Changed garden');
    data.state.extras.notes = { mira: { actorId: 'mira', text: 'A later interaction' } };
  });
  await running.signIn({ name: 'Another visitor' });
  assert.equal((await running.request('/api/demo/reset', { json: post })).status, 200);
  assert.equal(await readFile(join(`${dataDir}-reset-history`, 'baseline.json'), 'utf8'), baselineBefore);
  assert.equal(running.instance.service.store.read().revisions[0].source, source);
  assert.notEqual(running.instance.service.store.read().session.id, firstThread);
  assert.deepEqual(running.instance.service.store.read().state.extras, {});
  await running.stop();
  running = await start(dataDir);
  assert.deepEqual(running.instance.directory.people().map(person => person.id), defaultIds);
  assert.equal(running.instance.service.store.read().revisions[0].source, source);
  assert.equal((await readdir(join(`${dataDir}-reset-history`, 'backups'))).length, 2);
});

test('a five-person baseline adds verified new defaults without recapturing established spaces or their history', async t => {
  const running = await fixture(t);
  const { baseline: original, filename } = await legacyBaseline(running);
  const { instance, request, signIn, dataDir } = running;
  const newcomer = await signIn({ name: 'A visiting painter' });
  await instance.service.store.transact(data => {
    data.revisions[0].source = source.replaceAll('Prepared garden', 'A later Mira edit');
    data.state.extras.notes = { mira: { actorId: 'mira', text: 'Do not replace the original baseline.' } };
  });
  const iris = await instance.directory.serviceFor('iris');
  const preparedTurn = { id: 'iris-prepared', message: 'Build a shared canvas', status: 'completed', revisionId: 2 };
  const laterTurn = { id: 'iris-later', message: 'A later painting edit', status: 'completed', revisionId: 3 };
  await iris.store.transact(data => {
    const base = data.revisions[0];
    data.revisions.push({ ...base, id: 2, source: source.replaceAll('Prepared garden', 'Shared canvas') },
      { ...base, id: 3, source: source.replaceAll('Prepared garden', 'Later canvas edit') });
    data.currentRevisionId = 3;
    data.state.extras.notes = { iris: { actorId: 'iris', text: 'An original painted mark' },
      [newcomer.user.id]: { actorId: newcomer.user.id, text: 'A visitor mark' } };
    data.session.turns = [preparedTurn, laterTurn];
    data.session.items = [
      { role: 'user', content: `Owner's request: ${preparedTurn.message}\n\nCurrent workspace and live state (authoritative for this turn):\n${JSON.stringify({ state: data.state })}` },
      { type: 'function_call', call_id: 'iris-publish', name: 'apply_change', arguments: '{}' },
      { type: 'function_call_output', call_id: 'iris-publish', output: '{"ok":true}' },
      { role: 'user', content: `Owner's request: ${laterTurn.message}\n\nCurrent workspace and live state (authoritative for this turn):\n${JSON.stringify({ state: data.state })}` },
    ];
  });
  const irisData = iris.store.read();
  const prepared = irisData.revisions.find(revision => revision.id === 2);
  const marker = { sessionId: irisData.session.id, turnId: preparedTurn.id, revisionId: 2,
    sourceHash: createHash('sha256').update(`${prepared.source}\n${prepared.tests}`).digest('hex') };
  await writeFile(join(dataDir, 'demo-preparation.json'), JSON.stringify({ version: 1, prepared: { iris: marker } }));
  const luca = await instance.directory.serviceFor('luca');
  const lucaTurn = { id: 'luca-built', message: 'Build a Spanish adventure', status: 'completed', revisionId: 2 };
  await luca.store.transact(data => {
    data.revisions.push({ ...data.revisions[0], id: 2, source: source.replaceAll('Prepared garden', 'Spanish adventure') });
    data.currentRevisionId = 2;
    data.session.turns = [lucaTurn];
    data.session.items = [{ role: 'user', content: `Owner's request: ${lucaTurn.message}\n\n` }];
  });

  const result = await request('/api/demo/reset', { json: post });
  assert.equal(result.status, 200, await result.clone().text());
  const upgraded = await readJson(filename);
  assert.equal(upgraded.createdAt, original.createdAt);
  assert.deepEqual(upgraded.users, demoUsers);
  for (const person of original.users) {
    assert.deepEqual(upgraded.spaces[person.id], original.spaces[person.id], person.name);
    assert.deepEqual(upgraded.prepared[person.id], original.prepared[person.id], person.name);
  }
  assert.equal(instance.service.store.read().revisions[0].source, source);
  const restoredIris = (await instance.directory.serviceFor('iris')).store.read();
  assert.equal(restoredIris.currentRevisionId, 2);
  assert.equal(restoredIris.revisions.at(-1).source, prepared.source);
  assert.deepEqual(restoredIris.session.turns, [preparedTurn]);
  assert.equal(restoredIris.session.items.length, 3);
  assert.deepEqual(restoredIris.state.extras.notes, { iris: { actorId: 'iris', text: 'An original painted mark' } });
  assert.equal(JSON.stringify(restoredIris).includes(newcomer.user.id), false);
  assert.deepEqual(upgraded.prepared.iris, marker);
  assert.equal((await readJson(join(dataDir, 'demo-preparation.json'))).prepared.iris.sessionId, restoredIris.session.id);
  const restoredLuca = (await instance.directory.serviceFor('luca')).store.read();
  assert.equal(restoredLuca.currentRevisionId, 2);
  assert.deepEqual(restoredLuca.session.turns, [lucaTurn]);
  assert.match(restoredLuca.revisions.at(-1).source, /Spanish adventure/);
  const afterUpgrade = await readFile(filename, 'utf8');
  assert.equal((await request('/api/demo/reset', { json: post })).status, 200);
  assert.equal(await readFile(filename, 'utf8'), afterUpgrade, 'The extended baseline becomes immutable too.');
});

test('a seven-person baseline adds Karen without recapturing existing spaces or their preparation markers', async t => {
  const running = await fixture(t);
  const { baseline: original, filename } = await legacyBaseline(running, 7);
  for (const person of original.users) {
    const service = await running.instance.directory.serviceFor(person.ownSpaceId);
    await service.store.transact(data => { data.revisions[0].source = source.replaceAll('Prepared garden', `Later ${person.name} edit`); });
  }
  const service = await running.instance.directory.serviceFor('karen');
  const preparedTurn = { id: 'karen-prepared', message: 'Build four arcade games', status: 'completed', revisionId: 2 };
  await service.store.transact(data => {
    data.revisions.push({ ...data.revisions[0], id: 2, source: source.replaceAll('Prepared garden', 'Four-game arcade') });
    data.currentRevisionId = 2;
    data.session.turns = [preparedTurn];
    data.session.items = [{ role: 'user', content: `Owner's request: ${preparedTurn.message}\n\n` }];
  });
  const data = service.store.read();
  const revision = data.revisions.at(-1);
  const marker = { sessionId: data.session.id, turnId: preparedTurn.id, revisionId: 2,
    sourceHash: createHash('sha256').update(`${revision.source}\n${revision.tests}`).digest('hex') };
  await writeFile(join(running.dataDir, 'demo-preparation.json'), JSON.stringify({ version: 1, prepared: { karen: marker } }));
  const result = await running.request('/api/demo/reset', { json: post });
  assert.equal(result.status, 200, await result.clone().text());
  const upgraded = await readJson(filename);
  assert.deepEqual(upgraded.users, demoUsers);
  for (const person of original.users) {
    assert.deepEqual(upgraded.spaces[person.id], original.spaces[person.id], person.name);
    assert.deepEqual(upgraded.prepared[person.id], original.prepared[person.id], person.name);
  }
  const restored = (await running.instance.directory.serviceFor('karen')).store.read();
  assert.equal(restored.currentRevisionId, 2);
  assert.equal(restored.revisions.at(-1).source, revision.source);
  assert.deepEqual(restored.session.turns, [preparedTurn]);
  assert.deepEqual(upgraded.prepared.karen, marker);
  const afterUpgrade = await readFile(filename, 'utf8');
  assert.equal((await running.request('/api/demo/reset', { json: post })).status, 200);
  assert.equal(await readFile(filename, 'utf8'), afterUpgrade, 'The complete baseline remains immutable.');
});

test('an eight-person baseline gains the verified shared board and future resets retain that baseline', async t => {
  const running = await fixture(t, { seedOverride: undefined });
  const { baseline: original, filename } = await legacyBaseline(running, 8);
  const laterVisitor = await running.signIn({ name: 'A new board visitor' });
  const first = await running.request('/api/demo/reset', { json: post });
  assert.equal(first.status, 200, await first.clone().text());
  const upgraded = await readJson(filename);
  assert.deepEqual(upgraded.users, demoUsers);
  assert.equal(upgraded.createdAt, original.createdAt);
  for (const person of original.users) {
    assert.deepEqual(upgraded.spaces[person.id], original.spaces[person.id], person.name);
    assert.deepEqual(upgraded.prepared[person.id], original.prepared[person.id], person.name);
  }
  const board = await running.instance.directory.serviceFor('nora');
  const saved = board.store.read();
  const current = data => data.revisions.find(revision => revision.id === data.currentRevisionId);
  assert.equal(current(saved).source, communityBoardSource);
  assert.ok(current(saved).checks.every(check => check.ok));
  assert.deepEqual(saved.state, { projects: [], contributions: [], extras: {} });
  assert.equal(running.instance.directory.people().some(person => person.id === laterVisitor.user.id), false);
  const baselineText = await readFile(filename, 'utf8');
  await board.reset();
  assert.notEqual(current(board.store.read()).source, communityBoardSource);
  const second = await running.request('/api/demo/reset', { json: post });
  assert.equal(second.status, 200, await second.clone().text());
  assert.equal(current((await running.instance.directory.serviceFor('nora')).store.read()).source, communityBoardSource);
  assert.equal(await readFile(filename, 'utf8'), baselineText);
});

test('the first full demo reset restores the bundled board even after messages and an individual owner reset', async t => {
  const running = await fixture(t, { seedOverride: undefined });
  const visitor = await running.signIn({ name: 'A board contributor' });
  const board = await running.instance.directory.serviceFor('nora');
  const current = data => data.revisions.find(revision => revision.id === data.currentRevisionId);
  const revisionId = board.store.read().currentRevisionId;
  for (const actor of ['mira', visitor.user.id]) {
    await board.action({ actor, revisionId, action: { type: 'post_message', topicId: 'ideas', body: 'A message before reset.' } });
  }
  assert.equal(Object.keys(board.store.read().state.extras.boardMessages).length, 2);
  await board.reset();
  assert.notEqual(current(board.store.read()).source, communityBoardSource);
  for (let reset = 0; reset < 2; reset++) {
    const result = await running.request('/api/demo/reset', { json: post });
    assert.equal(result.status, 200, await result.clone().text());
    const restored = (await running.instance.directory.serviceFor('nora')).store.read();
    assert.equal(current(restored).source, communityBoardSource);
    assert.deepEqual(restored.state, { projects: [], contributions: [], extras: {} });
    assert.deepEqual(restored.session.turns, []);
    assert.ok(current(restored).checks.every(check => check.ok));
  }
});

test('reset verifies the full four-game arcade with saved progress and keeps its captured baseline after later edits', async t => {
  const running = await fixture(t);
  const { baseline: original, filename } = await legacyBaseline(running, 7);
  const visitor = await running.signIn({ name: 'Arcade visitor' });
  const james = { id: 'james', name: 'James' };
  const games = { pacman: pacmanGame, 'space-invaders': invadersGame, snake: snakeGame, tetris: tetrisGame };
  const progress = actor => Object.fromEntries(Object.entries(games).map(([id, game]) => [id, game.step(game.init(null, actor), { type: 'tick', deltaMs: 50 }, actor)]));
  const savedJames = progress(james), savedVisitor = progress(visitor.user);
  const expectedExtras = Object.fromEntries(Object.keys(games).map(id => [id, { james: savedJames[id] }]));
  const proposal = await arcadeProposal();
  const preparedTurn = { id: 'complete-arcade', message: 'Build four playable arcade games', status: 'completed', revisionId: 2 };
  const karen = await running.instance.directory.serviceFor('karen');
  await karen.store.transact(data => {
    data.revisions.push({ ...data.revisions[0], id: 2, source: proposal.source, tests: proposal.tests, meta: arcadeMeta });
    data.currentRevisionId = 2;
    data.state.extras = Object.fromEntries(Object.keys(games).map(id => [id, { james: savedJames[id], [visitor.user.id]: savedVisitor[id] }]));
    data.session.turns = [preparedTurn];
    data.session.items = [{ role: 'user', content: `Owner's request: ${preparedTurn.message}\n\n` }];
  });
  const prepared = karen.store.read();
  const marker = { sessionId: prepared.session.id, turnId: preparedTurn.id, revisionId: 2,
    sourceHash: createHash('sha256').update(`${proposal.source}\n${proposal.tests}`).digest('hex') };
  await writeFile(join(running.dataDir, 'demo-preparation.json'), JSON.stringify({ version: 1, prepared: { karen: marker } }));

  const firstReset = await running.request('/api/demo/reset', { json: post });
  assert.equal(firstReset.status, 200, await firstReset.clone().text());
  const captured = await readJson(filename);
  for (const person of original.users) {
    assert.deepEqual(captured.spaces[person.id], original.spaces[person.id], person.name);
  }
  const restored = (await running.instance.directory.serviceFor('karen')).store.read();
  assert.equal(restored.revisions.at(-1).source, proposal.source);
  assert.equal(restored.revisions.at(-1).tests, proposal.tests);
  assert.equal(restored.revisions.at(-1).checks.every(check => check.ok), true);
  assert.deepEqual(restored.state.extras, expectedExtras);
  assert.equal(running.instance.directory.people().some(person => person.id === visitor.user.id), false);
  const baselineText = await readFile(filename, 'utf8');

  const laterVisitor = await running.signIn({ name: 'Later arcade visitor' });
  const edited = await running.instance.directory.serviceFor('karen');
  await edited.store.transact(data => {
    data.revisions.push({ ...data.revisions[0], id: 3, source: source.replaceAll('Prepared garden', 'A later arcade edit') });
    data.currentRevisionId = 3;
    data.state.extras = { notes: { [laterVisitor.user.id]: { actorId: laterVisitor.user.id, text: 'Later progress' } } };
  });
  const secondReset = await running.request('/api/demo/reset', { json: post });
  assert.equal(secondReset.status, 200, await secondReset.clone().text());
  const restoredAgain = (await running.instance.directory.serviceFor('karen')).store.read();
  assert.equal(restoredAgain.currentRevisionId, 2);
  assert.equal(restoredAgain.revisions.at(-1).source, proposal.source);
  assert.deepEqual(restoredAgain.state.extras, expectedExtras);
  assert.equal(running.instance.directory.people().some(person => person.id === laterVisitor.user.id), false);
  assert.equal(await readFile(filename, 'utf8'), baselineText);
});

for (const [baselineSize, failedId] of [[5, 'luca'], [7, 'karen'], [8, 'nora']]) test(`a failed new-default check preserves the ${baselineSize}-person baseline and the entire live neighborhood`, async t => {
  const running = await fixture(t);
  const { filename } = await legacyBaseline(running, baselineSize);
  const before = await readFile(filename, 'utf8');
  const newcomer = await running.signIn({ name: 'Keep this visitor' });
  const failed = await running.instance.directory.serviceFor(failedId);
  await failed.store.transact(data => { data.revisions[0].tests = 'not valid javascript'; });
  const live = await readFile(join(running.dataDir, 'spaces', failedId, 'space.json'), 'utf8');
  const backups = await readdir(join(`${running.dataDir}-reset-history`, 'backups'));
  const response = await running.request('/api/demo/reset', { json: post });
  assert.equal(response.status, 400);
  assert.match((await response.json()).error, new RegExp(`${demoUsers.find(person => person.id === failedId).name} canvas did not pass its checks`));
  assert.equal(await readFile(filename, 'utf8'), before);
  assert.equal(await readFile(join(running.dataDir, 'spaces', failedId, 'space.json'), 'utf8'), live);
  assert.deepEqual(await readdir(join(`${running.dataDir}-reset-history`, 'backups')), backups);
  assert.equal(running.instance.directory.people().some(person => person.id === newcomer.user.id), true);
  assert.equal((await running.request('/api/auth/sign-in', { json: { userId: newcomer.user.id } })).status, 200);
});

test('an unrecognized partial baseline is rejected without changing current spaces or adding a backup', async t => {
  const running = await fixture(t);
  const { filename } = await legacyBaseline(running, 6);
  const before = await readFile(filename, 'utf8');
  const live = await readFile(join(running.dataDir, 'space.json'), 'utf8');
  const backups = await readdir(join(`${running.dataDir}-reset-history`, 'backups'));
  const result = await running.request('/api/demo/reset', { json: post });
  assert.equal(result.status, 400);
  assert.match((await result.json()).error, /baseline is invalid/);
  assert.equal(await readFile(filename, 'utf8'), before);
  assert.equal(await readFile(join(running.dataDir, 'space.json'), 'utf8'), live);
  assert.deepEqual(await readdir(join(`${running.dataDir}-reset-history`, 'backups')), backups);
  assert.deepEqual(running.instance.directory.people().map(person => person.id), defaultIds);
});

test('reset requires an explicit same-origin JSON confirmation and blocks cross-site or ambiguous requests', async t => {
  const { request, base, signIn, instance } = await fixture(t);
  await signIn({ name: 'Keep this person' });
  for (const json of [{}, { confirmation: true }, { confirmation: 'reset-demo', extra: true }, ['reset-demo']]) {
    assert.equal((await request('/api/demo/reset', { json })).status, 400);
  }
  for (const headers of [
    { Origin: 'https://attacker.example' }, { Origin: 'http://127.0.0.1:1' }, { Origin: '' },
    { Origin: base, 'Sec-Fetch-Site': 'cross-site' },
  ]) assert.equal((await request('/api/demo/reset', { json: post, headers })).status, 403, JSON.stringify(headers));
  const invalidHost = await new Promise((resolve, reject) => {
    const request = httpRequest(`${base}/api/demo/reset`, { method: 'POST', headers: { Host: 'attacker.example', Origin: base, 'Content-Type': 'application/json' } }, response => {
      response.resume(); response.on('end', () => resolve(response.statusCode));
    });
    request.on('error', reject); request.end(JSON.stringify(post));
  });
  assert.equal(invalidHost, 403);
  assert.equal((await request('/api/demo/reset', { json: post, headers: { 'Content-Type': 'text/plain' } })).status, 415);
  assert.equal(instance.directory.people().length, defaultIds.length + 1);
  assert.equal((await request('/api/demo/reset', { json: post, headers: { Origin: '', Referer: `${base}/` } })).status, 200);
});

test('reset cancels active edits, drains them, rejects concurrent writes, and invalidates all old capabilities', async t => {
  let notifyAbort;
  const aborted = new Promise(resolve => { notifyAbort = resolve; });
  let release;
  const released = new Promise(resolve => { release = resolve; });
  const slowAdapter = { ...adapter, respond: async ({ signal }) => {
    if (!signal.aborted) await new Promise(resolve => signal.addEventListener('abort', resolve, { once: true }));
    notifyAbort(); await released;
    signal.throwIfAborted();
  } };
  const { instance, request, signIn } = await fixture(t, { adapter: slowAdapter });
  const added = await signIn({ name: 'Active visitor' });
  const previousDirectory = instance.directory;
  const previousService = await previousDirectory.serviceFor(added.ownSpaceId);
  await previousService.submit('Start a long edit');
  const resetting = request('/api/demo/reset', { json: post });
  await aborted;
  assert.equal((await request('/api/demo/reset', { json: post })).status, 409);
  assert.equal((await request('/api/auth/sign-in', { json: { name: 'Race visitor' } })).status, 503);
  await assert.rejects(previousDirectory.signIn({ name: 'Direct race' }), error => error.status === 503);
  await assert.rejects(previousService.submit('Late edit'), error => error.status === 503);
  await assert.rejects(previousService.action({ actor: added.user.id, revisionId: 1, action: { type: 'leave', text: 'Late write' } }), error => error.status === 503);
  release();
  assert.equal((await resetting).status, 200);
  assert.deepEqual(instance.directory.people().map(person => person.id), defaultIds);
  assert.equal((await request('/api/auth/session', { token: added.token })).status, 401);
  await assert.rejects(previousService.reset(), error => error.status === 503);
  await assert.rejects(previousService.restore(1), error => error.status === 503);
});

test('an invalid baseline candidate leaves original data present and the app usable', async t => {
  const { instance, request, signIn, dataDir } = await fixture(t);
  await signIn({ name: 'Preserved visitor' });
  await instance.service.store.transact(data => { data.revisions[0].tests = 'not valid javascript'; });
  const result = await request('/api/demo/reset', { json: post });
  assert.equal(result.status, 400);
  assert.match((await result.json()).error, /did not pass its checks/);
  assert.equal(instance.directory.people().length, defaultIds.length + 1);
  assert.equal((await readJson(join(dataDir, 'identities.json'))).users.length, defaultIds.length + 1);
  assert.equal((await request('/api/auth/sign-in', { json: { userId: 'mira' } })).status, 200);
  assert.deepEqual(await readdir(join(`${dataDir}-reset-history`, 'backups')), []);
});

test('a provider close failure drains every service and reopens the untouched original demo', async t => {
  let closes = 0;
  const closingAdapter = { ...adapter, async close() { if (++closes === 1) throw new Error('Simulated close failure'); } };
  const { instance, request, signIn, dataDir } = await fixture(t, { adapter: closingAdapter });
  const person = await signIn({ name: 'Keep this account' });
  const result = await request('/api/demo/reset', { json: post });
  assert.equal(result.status, 400);
  assert.equal(closes, defaultIds.length + 1, 'All opened services finish closing before reset reports failure.');
  assert.equal(instance.directory.people().length, defaultIds.length + 1);
  assert.equal((await readJson(join(dataDir, 'identities.json'))).users.length, defaultIds.length + 1);
  assert.equal((await request('/api/auth/session', { token: person.token })).status, 401);
  assert.equal((await request('/api/auth/sign-in', { json: { userId: person.user.id } })).status, 200);
});

test('closing during turn initialization drains workspace writes before reporting completion', async t => {
  let modelCalls = 0;
  const { instance, dataDir } = await fixture(t, { adapter: { ...adapter, async respond() { modelCalls++; return { output: [] }; } } });
  const service = instance.service;
  const starting = service.submit('An edit interrupted before generation');
  const closing = service.close();
  await Promise.all([starting, closing]);
  assert.equal(service.busy, false);
  assert.equal(modelCalls, 0);
  const saved = await readJson(join(dataDir, 'space.json'));
  assert.equal(saved.session.status, 'idle');
  assert.equal(saved.session.turns[0].status, 'cancelled');
  assert.deepEqual(service.store.read(), saved);
});

test('unfinished directory swaps recover consistently and retain the full original backup', async t => {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-reset-recovery-'));
  const dataDir = join(parent, 'data');
  const running = await start(dataDir);
  t.after(async () => { await rm(parent, { recursive: true, force: true }); });
  await running.signIn({ name: 'Before crash' });
  await Promise.all(demoUsers.map(person => running.instance.directory.serviceFor(person.ownSpaceId)));
  await running.stop();
  const transaction = await beginDemoReset(dataDir);
  const history = `${dataDir}-reset-history`;
  const journal = await readJson(join(history, 'transaction.json'));
  // Simulate the crash window after old -> backup but before staged -> live.
  await rename(dataDir, join(history, `staging-${journal.id}`));
  await recoverDemoReset(dataDir);
  assert.equal((await readJson(join(dataDir, 'identities.json'))).users.length, defaultIds.length);
  assert.equal((await readJson(join(transaction.backupDirectory, 'identities.json'))).users.length, defaultIds.length + 1);
  assert.equal((await readdir(history)).includes('transaction.json'), false);
  await recoverDemoReset(dataDir);
  const restarted = await start(dataDir);
  assert.deepEqual(restarted.instance.directory.people().map(person => person.id), defaultIds);
  await restarted.stop();
});

test('a failed replacement can roll back without losing the original directory', async t => {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-reset-rollback-'));
  const dataDir = join(parent, 'data');
  const running = await start(dataDir);
  t.after(async () => { await rm(parent, { recursive: true, force: true }); });
  await running.signIn({ name: 'Preserve on rollback' });
  await Promise.all(demoUsers.map(person => running.instance.directory.serviceFor(person.ownSpaceId)));
  await running.stop();
  const oldData = await readFile(join(dataDir, 'identities.json'), 'utf8');
  const transaction = await beginDemoReset(dataDir);
  await transaction.rollback();
  assert.equal(await readFile(join(dataDir, 'identities.json'), 'utf8'), oldData);
  assert.equal((await readdir(`${dataDir}-reset-history`)).includes('transaction.json'), false);
});
