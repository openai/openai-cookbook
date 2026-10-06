import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { getQuickJS } from 'quickjs-emscripten';
import { createApp } from '../server/index.mjs';

const endpoint = (spaceId = 'mira') => `/api/spaces/${spaceId}/game`;
const config = { id: 'arcade', tickMs: 50, saveAction: 'save_game' };
const privateMarkers = ['PRIVATE_RENDER_IMPLEMENTATION', 'PRIVATE_REDUCER_IMPLEMENTATION', 'PRIVATE_FEATURE_TEST', 'PRIVATE_BUILDER_REQUEST'];
const source = ({ enabled = true, version = 1, checkpointMutation = '' } = {}) => `
export const meta=${JSON.stringify({ title: 'A little arcade', subtitle: '', accent: '#687957' })};
${enabled ? `meta.game=${JSON.stringify(config)};` : ''}
function privateRender(){return 'PRIVATE_RENDER_IMPLEMENTATION'}
function privateSave(action,actor){
  if(!action.game||action.game.actorId!==actor.id||!Number.isInteger(action.game.score)||action.game.score<0)throw Error('PRIVATE_REDUCER_IMPLEMENTATION');
  const record={actorId:actor.id,score:action.game.score,...(typeof action.game.board==='string'?{board:action.game.board}:{})};
  ${checkpointMutation ? `if(action.game.score===99){${checkpointMutation}}` : ''}
  return record;
}
export function render(){return '<section data-game="arcade" aria-label="Arcade">'+privateRender()+'<canvas data-game-canvas></canvas><button data-game-command="start">Start game</button></section>'}
export function reduce(state,action,actor){
  if(action.type==='save_game'){
    const record=privateSave(action,actor);
    state.extras.arcade=state.extras.arcade||{};state.extras.arcade[actor.id]=record;return state;
  }
  if(action.type==='save_note'){
    state.extras.notes=state.extras.notes||{};state.extras.notes[actor.id]={actorId:actor.id,text:String(action.text)};return state;
  }
  throw Error('Unknown action');
}
${enabled ? `
function publicPlayer(saved,actor){return {actorId:actor.id,score:saved?saved.score:0,...(typeof saved?.board==='string'?{board:saved.board}:{})}}
export const game={
  init(saved,actor){return publicPlayer(saved,actor)},
  step(state,action){return {...state,score:state.score+(action.type==='tick'?${version}:0)}},
  view(state){return {width:200,height:120,objects:[{id:'player',type:'circle',x:20,y:20,radius:8,fill:'#687957'}],values:{score:state.score,status:'public-game-version-${version}'}}}
};` : ''}`;
const checks = `export function runTests(api){
  const actor={id:'game-test-visitor',name:'Game visitor'};
  const saved=api.reduce(api.initialState,{type:'save_game',game:{actorId:actor.id,score:7}},actor);
  const results=[
    {name:'PRIVATE_FEATURE_TEST: checkpoint belongs to visitor',ok:saved.extras.arcade[actor.id].score===7},
    {name:'The arcade renders',ok:api.render(saved,actor).includes('Start game')}
  ];
  if(api.meta.game){
    const state=api.gameInit(null,actor);
    const next=api.gameStep(state,{type:'tick',deltaMs:50},actor);
    results.push({name:'A local game advances and renders',ok:next.score>state.score&&api.gameView(next,actor).values.score===next.score});
  }
  return results;
}`;

async function fixture(t) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-game-http-'));
  let nextSource = source();
  let buildCalls = 0;
  const instance = await createApp({
    dataDir,
    adapter: { keyAvailable: true, model: 'game-http-fixture', tier: 'ultrafast', respond: async () => ({ output: [{
      type: 'function_call', call_id: `game-build-${++buildCalls}`, name: 'apply_change',
      arguments: JSON.stringify({ source: nextSource, tests: checks, summary: 'A little arcade' }),
    }] }) },
  });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { token, json } = {}) => fetch(base + path, {
    method: json === undefined ? 'GET' : 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: json === undefined ? undefined : JSON.stringify(json),
  });
  const signIn = async (userId = 'leo') => {
    const response = await request('/api/auth/sign-in', { json: { userId } });
    assert.equal(response.status, 200);
    return response.json();
  };
  const publish = async (options, spaceId = 'mira') => {
    nextSource = source(options);
    const service = await instance.directory.serviceFor(spaceId);
    const previous = service.store.read().currentRevisionId;
    await service.submit('PRIVATE_BUILDER_REQUEST: build a playable arcade');
    await service.waitForIdle();
    const data = service.store.read();
    const failures = data.events.filter(event => event.type === 'tool.failed' || event.type === 'turn.failed').map(event => event.detail);
    assert.equal(data.currentRevisionId, previous + 1, failures.join('\n') || 'The fixture did not publish a new revision');
    return data.currentRevisionId;
  };
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await instance.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  return { request, signIn, publish, dataDir, directory: instance.directory, buildCalls: () => buildCalls };
}

async function runPublicBundle(payload) {
  const quickjs = await getQuickJS();
  const runtime = quickjs.newRuntime();
  runtime.setMemoryLimit(16 * 1024 * 1024);
  const deadline = Date.now() + 1000;
  runtime.setInterruptHandler(() => Date.now() > deadline);
  const context = runtime.newContext();
  try {
    const result = context.evalCode(`${payload.bundle};JSON.stringify({exports:Object.keys(GameModule),state:GameModule.game.init(${JSON.stringify(payload.saved)},${JSON.stringify(payload.actor)})})`);
    if (result.error) {
      const error = context.dump(result.error);
      result.error.dispose();
      assert.fail(`The public game artifact cannot execute independently: ${JSON.stringify(error)}`);
    }
    try { return JSON.parse(context.getString(result.value)); }
    finally { result.value.dispose(); }
  } finally { context.dispose(); runtime.dispose(); }
}

test('game artifacts require a valid session and an enabled game on the requested space', async t => {
  const app = await fixture(t);
  assert.equal((await app.request(endpoint())).status, 401);
  assert.equal((await app.request(endpoint(), { token: 'not-a-session' })).status, 401);
  const leo = await app.signIn();
  for (const spaceId of ['missing', '%2E%2E%2Fsecret']) {
    assert.equal((await app.request(endpoint(spaceId), { token: leo.token })).status, 404);
  }
  assert.equal((await app.request(endpoint(), { token: leo.token })).status, 404, 'A blank space has no game artifact');
  await app.publish({ enabled: false });
  assert.equal((await app.request(endpoint(), { token: leo.token })).status, 404, 'A published ordinary page has no game artifact');
  await app.publish();
  assert.equal((await app.request(endpoint(), { token: leo.token })).status, 200);
  assert.equal((await app.request(endpoint('leo'), { token: leo.token })).status, 404, 'A different space cannot borrow the enabled game');
  assert.equal((await app.request('/api/auth/sign-out', { token: leo.token, json: {} })).status, 200);
  assert.equal((await app.request(endpoint(), { token: leo.token })).status, 401);
});

test('owner and visitor receive only a standalone public game artifact, never the private page module or builder history', async t => {
  const app = await fixture(t);
  const revisionId = await app.publish();
  const mira = await app.signIn('mira');
  const leo = await app.signIn('leo');
  const ownerSnapshot = await (await app.request('/api/spaces/mira', { token: mira.token })).json();
  assert.match(ownerSnapshot.revision.source, /PRIVATE_RENDER_IMPLEMENTATION/);
  assert.match(ownerSnapshot.revision.source, /PRIVATE_REDUCER_IMPLEMENTATION/);
  assert.match(ownerSnapshot.revision.tests, /PRIVATE_FEATURE_TEST/);
  assert.match(ownerSnapshot.session.lastMessage, /PRIVATE_BUILDER_REQUEST/);
  for (const person of [mira, leo]) {
    const response = await app.request(endpoint(), { token: person.token });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const payload = await response.json();
    assert.deepEqual(Object.keys(payload).sort(), ['actor', 'bundle', 'config', 'revisionId', 'saved']);
    assert.equal(payload.revisionId, revisionId);
    assert.deepEqual(payload.config, config);
    assert.deepEqual(payload.actor, person.user);
    assert.equal(payload.saved, null);
    assert.equal(typeof payload.bundle, 'string');
    for (const marker of privateMarkers) assert.ok(!JSON.stringify(payload).includes(marker), `The public artifact leaked ${marker}`);
    assert.deepEqual(await runPublicBundle(payload), { exports: ['game'], state: { actorId: person.user.id, score: 0 } });
  }
  assert.equal((await app.request('/api/spaces/mira/turn', { token: leo.token, json: { message: 'Change the game' } })).status, 403);
});

test('loading a game scopes saved progress to the authenticated player and leaves state, events, and disk untouched', async t => {
  const app = await fixture(t);
  const revisionId = await app.publish();
  const players = await Promise.all(['mira', 'leo', 'erica', 'james'].map(userId => app.signIn(userId)));
  for (const [index, player] of players.slice(0, 3).entries()) {
    const response = await app.request('/api/spaces/mira/action', { token: player.token, json: {
      revisionId, action: { type: 'save_game', game: { actorId: player.user.id, score: (index + 1) * 10 } },
    } });
    assert.equal(response.status, 200);
  }
  assert.equal((await app.request('/api/spaces/mira/action', { token: players[0].token, json: {
    revisionId, action: { type: 'save_note', text: 'UNRELATED_PARTICIPANT_RECORD' },
  } })).status, 200);
  const service = await app.directory.serviceFor('mira');
  const before = service.store.read();
  const diskBefore = await readFile(join(app.dataDir, 'space.json'), 'utf8');
  const callsBefore = app.buildCalls();
  const emitted = [];
  const unsubscribe = service.store.subscribe(event => emitted.push(event));
  t.after(unsubscribe);
  for (const [index, player] of players.entries()) {
    const response = await app.request(`${endpoint()}?actor=mira&actorId=mira&spaceId=leo`, { token: player.token });
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.deepEqual(payload.actor, player.user, 'Query parameters cannot impersonate another player');
    assert.deepEqual(payload.saved, index < 3 ? { actorId: player.user.id, score: (index + 1) * 10 } : null);
    assert.ok(!JSON.stringify(payload).includes('UNRELATED_PARTICIPANT_RECORD'));
    assert.deepEqual((await runPublicBundle(payload)).state, { actorId: player.user.id, score: index < 3 ? (index + 1) * 10 : 0 });
  }
  assert.deepEqual(service.store.read(), before);
  assert.equal(await readFile(join(app.dataDir, 'space.json'), 'utf8'), diskBefore);
  assert.deepEqual(emitted, []);
  assert.equal(app.buildCalls(), callsBefore, 'Loading gameplay does not invoke the builder');
});

test('the game endpoint follows the current publication and stops serving a game when the owner removes it', async t => {
  const app = await fixture(t);
  const { token } = await app.signIn();
  const firstRevision = await app.publish({ version: 1 });
  const first = await (await app.request(endpoint(), { token })).json();
  assert.equal(first.revisionId, firstRevision);
  assert.match(first.bundle, /public-game-version-1/);
  const secondRevision = await app.publish({ version: 2 });
  const second = await (await app.request(endpoint(), { token })).json();
  assert.equal(second.revisionId, secondRevision);
  assert.equal(secondRevision, firstRevision + 1);
  assert.match(second.bundle, /public-game-version-2/);
  assert.doesNotMatch(second.bundle, /public-game-version-1/);
  assert.notEqual(second.bundle, first.bundle);
  await app.publish({ enabled: false });
  const response = await app.request(endpoint(), { token });
  assert.equal(response.status, 404, 'Removed games cannot be loaded from the old artifact cache');
});

test('only a declared game checkpoint accepts up to 32000 bytes and failed saves cannot alter any participant records', async t => {
  const app = await fixture(t);
  const revisionId = await app.publish();
  const mira = await app.signIn('mira');
  const leo = await app.signIn('leo');
  const ownerGame = { actorId: mira.user.id, score: 9 };
  assert.equal((await app.request('/api/spaces/mira/action', { token: mira.token, json: {
    revisionId, action: { type: 'save_game', game: ownerGame },
  } })).status, 200);
  const largeGame = { actorId: leo.user.id, score: 42, board: '' };
  largeGame.board = '.'.repeat(32_000 - Buffer.byteLength(JSON.stringify(largeGame)));
  assert.equal(Buffer.byteLength(JSON.stringify(largeGame)), 32_000);
  const checkpoint = { type: 'save_game', game: largeGame };
  assert.ok(Buffer.byteLength(JSON.stringify(checkpoint)) > 8000, 'The fixture must exercise the larger game-only action limit');
  const saved = await app.request('/api/spaces/mira/action', { token: leo.token, json: { revisionId, action: checkpoint } });
  assert.equal(saved.status, 200);
  const result = await saved.json();
  assert.deepEqual(result.state.extras.arcade, { mira: ownerGame, leo: largeGame });
  const loaded = await app.request(endpoint(), { token: leo.token });
  assert.equal(loaded.status, 200);
  const payload = await loaded.json();
  assert.deepEqual(payload.saved, largeGame, 'The complete accepted checkpoint is available on the next game load');
  assert.deepEqual((await runPublicBundle(payload)).state, largeGame);

  const service = await app.directory.serviceFor('mira');
  const unchangedAfterReject = async (action, currentRevision = revisionId) => {
    const before = service.store.read();
    const diskBefore = await readFile(join(app.dataDir, 'space.json'), 'utf8');
    const response = await app.request('/api/spaces/mira/action', { token: leo.token, json: { revisionId: currentRevision, action } });
    assert.equal(response.status, 400);
    assert.deepEqual(service.store.read(), before, 'A rejected checkpoint cannot change state, revisions, or events');
    assert.equal(await readFile(join(app.dataDir, 'space.json'), 'utf8'), diskBefore);
  };
  await unchangedAfterReject({ type: 'save_note', text: largeGame.board });
  await unchangedAfterReject({ type: 'save_game', game: { ...largeGame, board: largeGame.board + '.' } });
  await unchangedAfterReject({ type: 'save_game', game: { ...largeGame, board: largeGame.board.slice(0, -1) + '🌱' } });
  await unchangedAfterReject({ type: 'save_game', game: { ...largeGame, actorId: mira.user.id, board: largeGame.board.slice(0, -16) } });
  await unchangedAfterReject({ ...checkpoint, actorId: leo.user.id });

  const ordinaryRevision = await app.publish({ enabled: false });
  // The same reducer still accepts small saves, but the larger request allowance
  // belongs to the current published game declaration, not to the action name.
  assert.equal((await app.request('/api/spaces/mira/action', { token: leo.token, json: {
    revisionId: ordinaryRevision, action: { type: 'save_game', game: { actorId: leo.user.id, score: 43 } },
  } })).status, 200);
  await unchangedAfterReject(checkpoint, ordinaryRevision);
});

test('invalid reducer-produced checkpoints are rejected atomically and the previous game remains playable', async t => {
  const cases = [
    ['oversized saved game', "record.board='.'.repeat(33000);"],
    ['missing saved actorId', 'delete record.actorId;'],
    ['changed saved owner', "record.actorId='mira';"],
  ];
  for (const [name, checkpointMutation] of cases) await t.test(name, async subtest => {
    const app = await fixture(subtest);
    const revisionId = await app.publish({ checkpointMutation });
    const mira = await app.signIn('mira');
    const leo = await app.signIn('leo');
    const previousGames = {
      mira: { actorId: 'mira', score: 9, board: 'owner progress' },
      leo: { actorId: 'leo', score: 12, board: 'visitor progress' },
    };
    for (const player of [mira, leo]) {
      const saved = await app.request('/api/spaces/mira/action', { token: player.token, json: {
        revisionId, action: { type: 'save_game', game: previousGames[player.user.id] },
      } });
      assert.equal(saved.status, 200);
    }
    const service = await app.directory.serviceFor('mira');
    const before = service.store.read();
    const diskBefore = await readFile(join(app.dataDir, 'space.json'), 'utf8');
    // This incoming state is small and correctly owned. Only the generated
    // reducer corrupts it, so validating the request alone cannot protect it.
    const response = await app.request('/api/spaces/mira/action', { token: leo.token, json: {
      revisionId, action: { type: 'save_game', game: { actorId: 'leo', score: 99, board: 'valid incoming progress' } },
    } });
    assert.equal(response.status, 400);
    assert.deepEqual(service.store.read(), before, 'The rejected reducer result cannot publish state or events');
    assert.equal(await readFile(join(app.dataDir, 'space.json'), 'utf8'), diskBefore);
    for (const player of [mira, leo]) {
      const loaded = await app.request(endpoint(), { token: player.token });
      assert.equal(loaded.status, 200, 'An invalid save must not strand a player behind a failed game load');
      const payload = await loaded.json();
      assert.equal(payload.revisionId, revisionId);
      assert.deepEqual(payload.saved, previousGames[player.user.id]);
      assert.deepEqual((await runPublicBundle(payload)).state, previousGames[player.user.id]);
    }
  });
});
