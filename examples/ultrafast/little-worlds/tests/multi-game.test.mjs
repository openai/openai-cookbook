import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { gameConfigs } from '../shared/game-schema.mjs';
import { compileModule, gameInit, gameStep, gameView, validateGameBindings, verifyModule } from '../server/runtime.mjs';
import { createApp } from '../server/index.mjs';

const actor = { id: 'mira', name: 'Mira' };
const configs = ['pacman', 'space-invaders', 'snake', 'tetris'].map((id, index) => ({ id, exportName: `game${index}`, tickMs: 50, saveAction: `save_${index}` }));
const markup = config => `<section data-game="${config.id}" aria-label="${config.id}"><canvas data-game-canvas></canvas><button data-game-command="start">Start ${config.id}</button><button data-game-action='{"type":"score"}'>Score ${config.id}</button></section>`;
const source = (mutation = '') => `
export const meta = ${JSON.stringify({ title: 'Four games', subtitle: '', accent: '#554488', games: configs })};
const privateCopy = 'PRIVATE_ARCADE_PAGE';
export function render() { return ${JSON.stringify(configs.map(markup).join(''))} + privateCopy; }
export function reduce(state, action, actor) {
  const config = meta.games.find(config => config.saveAction === action.type);
  if(!config || action.game.actorId !== actor.id) throw Error('PRIVATE_ARCADE_REDUCER');
  const next = {...state,extras:{...state.extras,[config.id]:{...state.extras[config.id],[actor.id]:action.game}}};
  ${mutation}
  return next;
}
${configs.map((config, index) => `
export const ${config.exportName} = {
  init(saved,actor) { return saved ? {...saved} : {actorId:actor.id,points:0}; },
  step(state,action) { if(!['tick','score'].includes(action.type)) throw Error('Invalid game control'); return {...state,points:state.points+${index + 1}}; },
  view(state) { return {width:200,height:160,objects:[{id:'player',type:'circle',x:state.points,y:40,radius:8}],values:{points:state.points,game:'PUBLIC_GAME_${index}'}}; }
};`).join('\n')}
`;
const featureTests = `export function runTests(api) {
  const actor={id:'game-test',name:'Player'};
  return api.meta.games.flatMap(config => {
    const game=api.games[config.id];
    const initial=game.init(null,actor);
    const next=game.step(initial,{type:'tick',deltaMs:50},actor);
    const view=game.view(next,actor);
    const saved=api.reduce(api.initialState,{type:config.saveAction,game:next},actor);
    return [
      {name:config.id+' advances and draws',ok:next.points>0 && initial.points===0 && view.objects[0].x===next.points},
      {name:config.id+' exposes only its controls',ok:game.actions.length===1 && game.actions[0].label==='Score '+config.id},
      {name:config.id+' saves independently',ok:saved.extras[config.id][actor.id].points===next.points},
      {name:config.id+' resumes its saved game',ok:game.init(saved.extras[config.id][actor.id],actor).points===next.points}
    ];
  });
}`;
const liveState = () => ({ projects: [], contributions: [], extras: Object.fromEntries([
  ...configs.map(config => [config.id, { mira: { actorId: 'mira', points: 8 }, leo: { actorId: 'leo', points: 3 } }]),
  ['notes', { mira: { actorId: 'mira', text: 'Keep every game and this note.' } }],
]) });

test('multi-game metadata is bounded, unambiguous, and compatible with legacy single-game metadata', () => {
  assert.deepEqual(gameConfigs(undefined), []);
  assert.deepEqual(gameConfigs({}), []);
  assert.deepEqual(gameConfigs({ games: configs }), configs);
  assert.deepEqual(gameConfigs({ game: { id: 'old-game' } }), [{ id: 'old-game' }]);
  for (const meta of [
    { games: [] }, { games: [...configs, { ...configs[0], id: 'fifth' }] },
    { game: { id: 'old-game' }, games: configs },
    { games: [{ id: 'snake' }] },
    { games: [configs[0], { ...configs[1], id: configs[0].id }] },
    { games: [configs[0], { ...configs[1], saveAction: configs[0].saveAction }] },
    { games: [{ ...configs[0], exportName: 'a.b' }] },
    { games: [{ ...configs[0], exportName: '__proto__' }] },
    { games: [{ ...configs[0], id: 'constructor' }] },
  ]) assert.throws(() => gameConfigs(meta), /game|Game|exportName/);
});

test('four named game exports compile to isolated public bundles with separate simulations', async () => {
  const compiled = await compileModule(source());
  assert.equal(compiled.gameBundle, undefined);
  assert.deepEqual(Object.keys(compiled.gameBundles), configs.map(config => config.id));
  for (const [index, config] of configs.entries()) {
    const bundle = compiled.gameBundles[config.id];
    assert.doesNotMatch(bundle, /PRIVATE_ARCADE|save_0|data-game-command/);
    for (let other = 0; other < 4; other++) if (other !== index) assert.ok(!bundle.includes(`PUBLIC_GAME_${other}`));
    const state = await gameInit(bundle, null, actor);
    const next = await gameStep(bundle, state, { type: 'tick', deltaMs: 50 }, actor);
    assert.equal(next.points, index + 1);
    assert.equal((await gameView(bundle, next, actor)).values.game, `PUBLIC_GAME_${index}`);
  }
});

test('named export aliases work and missing or malformed named games cannot publish', async () => {
  const aliased = source().replace('export const game0 =', 'const firstGame =') + '\nexport {firstGame as game0};';
  assert.ok((await compileModule(aliased)).gameBundles.pacman);
  for (const broken of [
    source().replace('export const game0 =', 'const game0 ='),
    source().replace('export const game2 = {', 'export const game2 = {init:undefined,broken:true};const invalidUnused = {'),
    source().replace('"exportName":"game0"', '"exportName":"missingGame"'),
  ]) await assert.rejects(compileModule(broken), /game|export/i);
});

test('separate games can share deferred helpers without leaking other games or accepting external mutation', async () => {
  const shared = `const shared = {step:1}; function advance(value){return value+shared.step;}\n`
    + source().replaceAll(/state.points\+[1-4]/g, 'advance(state.points)');
  const compiled = await compileModule(shared);
  for (const [index, config] of configs.entries()) {
    assert.equal((await gameStep(compiled.gameBundles[config.id], { actorId: actor.id, points: 4 }, { type: 'tick' }, actor)).points, 5);
    for (let other = 0; other < 4; other++) if (other !== index) assert.ok(!compiled.gameBundles[config.id].includes(`PUBLIC_GAME_${other}`));
  }
  for (const outside of [
    'const unused={value:(()=>{shared.step=2;return 1})()};',
    'const unused={change(){shared.step=2;}};unused.change();',
    'const unused={change(){shared.step=2;}}.change();',
    'const unused={value:{change(){shared.step=2;}}.change()};',
  ]) await assert.rejects(compileModule(shared + outside), /inside their declarations|outside initializers|separate module statements/);
});

test('multi-game bindings scope each action to its tile and reject unknown, orphan, duplicate, or nested roots', () => {
  const html = configs.map(markup).join('');
  for (const config of configs) assert.deepEqual(validateGameBindings(html, config, configs).actions, [{ action: { type: 'score' }, label: `Score ${config.id}` }]);
  for (const bad of [
    html + markup({ id: 'unknown' }),
    html.replace('data-game="snake"', 'data-game="pacman"'),
    html + '<button data-game-command="start">Orphan</button>',
    `<section data-game="pacman">${configs.slice(1).map(markup).join('')}<canvas data-game-canvas></canvas><button data-game-command="start">Start</button></section>`,
  ]) assert.throws(() => { for (const config of configs) validateGameBindings(bad, config, configs); }, /root|orphan|container/);
});

test('publication verifies every game and exposes scoped feature-test APIs without changing live data', async () => {
  const state = liveState(), before = structuredClone(state);
  const result = await verifyModule(source(), featureTests, state);
  assert.equal(result.ok, true, JSON.stringify(result.checks));
  for (const config of configs) {
    assert.ok(result.checks.some(check => check.name === `Owner ${config.id} game initializes, advances, and renders safely` && check.ok));
    assert.ok(result.checks.some(check => check.name === `Visitor ${config.id} game checkpoints preserve progress and unrelated data` && check.ok));
  }
  assert.deepEqual(state, before);
});

test('one invalid game blocks the entire arcade even when authored tests claim success', async () => {
  const broken = source().replace("game:'PUBLIC_GAME_2'", "game:'PUBLIC_GAME_2',invalid:{not:'a display value'}");
  const result = await verifyModule(broken, 'export function runTests(){return [{name:"Claim",ok:true}]}', liveState());
  assert.equal(result.ok, false);
  assert.ok(result.checks.some(check => /snake game initializes/.test(check.name) && !check.ok));
});

test('checkpoint verification rejects rewriting another game owned by the same participant', async () => {
  const mutation = "next.extras.notes={...next.extras.notes,[actor.id]:{actorId:actor.id,text:'Erased'}};";
  const result = await verifyModule(source(mutation), 'export function runTests(){return [{name:"Claim",ok:true}]}', liveState());
  assert.equal(result.ok, false);
  assert.ok(result.checks.some(check => /game checkpoints/.test(check.name) && !check.ok && /preserve every other/.test(check.message)));
});

async function fixture(t, mutation = '') {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-multi-game-'));
  const instance = await createApp({ dataDir, adapter: { keyAvailable: true, model: 'multi-game-fixture', tier: 'ultrafast', respond: async () => ({ output: [{
    type: 'function_call', call_id: 'arcade-fixture', name: 'apply_change', arguments: JSON.stringify({ source: source(mutation), tests: featureTests, summary: 'Four playable games' }),
  }] }) } });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, token, json) => fetch(base + path, {
    method: json === undefined ? 'GET' : 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: json === undefined ? undefined : JSON.stringify(json),
  });
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await instance.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  const service = await instance.directory.serviceFor('mira');
  await service.submit('PRIVATE_BUILDER_REQUEST: prepare the arcade');
  await service.waitForIdle();
  const data = service.store.read();
  assert.equal(data.currentRevisionId, 2, JSON.stringify(data.events.filter(event => /failed/.test(event.type))));
  const login = async userId => {
    const response = await request('/api/auth/sign-in', undefined, { userId });
    assert.equal(response.status, 200);
    return response.json();
  };
  return { dataDir, request, service, revisionId: data.currentRevisionId, mira: await login('mira'), leo: await login('leo') };
}

test('game HTTP selection is explicit and returns only the chosen public game and authenticated player progress', async t => {
  const app = await fixture(t);
  assert.equal((await app.request('/api/spaces/mira/game?gameId=snake')).status, 401);
  assert.equal((await app.request('/api/spaces/mira/game', app.mira.token)).status, 400);
  assert.equal((await app.request('/api/spaces/mira/game?gameId=unknown', app.mira.token)).status, 404);
  assert.equal((await app.request('/api/spaces/mira/game?gameId=snake&gameId=tetris', app.mira.token)).status, 400);
  for (const config of configs) {
    const response = await app.request(`/api/spaces/mira/game?gameId=${config.id}`, app.leo.token);
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.config.id, config.id);
    assert.equal(payload.actor.id, app.leo.user.id);
    assert.equal(payload.saved, null);
    assert.doesNotMatch(JSON.stringify(payload), /PRIVATE_ARCADE|PRIVATE_BUILDER_REQUEST/);
  }
});

test('concurrent saves preserve every tile, each visitor, and resume only the selected game', async t => {
  const app = await fixture(t);
  const saves = [app.mira, app.leo].flatMap((player, playerIndex) => configs.map((config, index) => ({ player, config, state: { actorId: player.user.id, points: 10 * playerIndex + index } })));
  const responses = await Promise.all(saves.map(({ player, config, state }) => app.request('/api/spaces/mira/action', player.token, { revisionId: app.revisionId, action: { type: config.saveAction, game: state } })));
  assert.ok(responses.every(response => response.status === 200));
  for (const { player, config, state } of saves) {
    const payload = await (await app.request(`/api/spaces/mira/game?gameId=${config.id}`, player.token)).json();
    assert.deepEqual(payload.saved, state);
    assert.deepEqual(await gameInit(payload.bundle, payload.saved, payload.actor), state);
  }
});

test('a later malicious checkpoint cannot overwrite another tile even under the same actor', async t => {
  const mutation = "if(action.game.points===99)next.extras.tetris={...next.extras.tetris,[actor.id]:{actorId:actor.id,points:999}};";
  const app = await fixture(t, mutation);
  const before = app.service.store.read();
  const diskBefore = await readFile(join(app.dataDir, 'space.json'), 'utf8');
  const response = await app.request('/api/spaces/mira/action', app.leo.token, { revisionId: app.revisionId, action: { type: configs[0].saveAction, game: { actorId: 'leo', points: 99 } } });
  assert.equal(response.status, 400);
  assert.deepEqual(app.service.store.read(), before);
  assert.equal(await readFile(join(app.dataDir, 'space.json'), 'utf8'), diskBefore);
});
