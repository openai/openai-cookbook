import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { blankSeedSource } from '../server/seed.mjs';
import { devdayRestylePrompt, logicDependencyFingerprint, parseRethemeArgs, preservationFingerprints, rethemeDevday } from '../scripts/retheme-devday.mjs';

const clone = value => structuredClone(value);
const reply = data => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
const source = color => `export const meta={title:'A working world',layout:'canvas',accent:'${color}'};export function render(){return '<main style="color:${color}">A working world</main>'} export function reduce(state,action,actor){return state;}`;
function revision(id = 1) { return { id, source: source(id === 1 ? '#ffffff' : '#04b84c'), tests: 'original tests', meta: { title: 'A working world', layout: 'canvas', accent: '#ffffff', capabilities: [], projects: [{ id: 'tile', title: 'Same tile', description: 'Same description', color: '#ffffff' }] }, checks: [{ name: 'Works', ok: true }] }; }
function mockApi(ids = ['mira', 'james', 'leo']) {
  const accounts = new Map(ids.map(id => [id, {
    user: { id, name: id, ownSpaceId: `space-${id}` }, revisions: [revision()], session: { id: `session-${id}`, turns: [], status: 'idle' },
    state: { projects: [{ id: 'tile', title: 'Same tile', description: 'Same description', color: '#ffffff' }], contributions: [{ id: 'v1', projectId: 'tile', actorId: 'mira', points: 2 }], extras: {} },
    html: '<main>Works</main>', pending: null, outcome: 'success', icon: { status: 'ready', version: 'old', dataUrl: 'test-image' }, iconPolls: 0,
  }]));
  const tokens = new Map();
  const requests = [];
  let active = 0, peak = 0, nextTurn = 0;
  const begin = (account, message) => {
    const turn = { id: `turn-${++nextTurn}`, message, status: 'running' };
    account.session.turns.push(turn); account.session.status = 'running'; account.pending = { turn, polls: 0 };
    peak = Math.max(peak, ++active);
    return turn;
  };
  const finish = account => {
    const { turn } = account.pending;
    account.pending = null; account.session.status = 'idle'; active--;
    if (account.outcome === 'failed') { turn.status = 'failed'; return; }
    const next = revision(account.revisions.at(-1).id + 1);
    next.meta.accent = '#04b84c'; next.meta.projects[0].color = '#04b84c';
    account.state.projects[0].color = '#04b84c';
    if (account.outcome === 'state') account.state.contributions = [];
    if (account.outcome === 'metadata') next.meta.projects[0].title = 'Lost tile';
    if (account.outcome === 'reducer') next.source = next.source.replace('return state;', 'return {...state};');
    if (account.outcome === 'bad-check') next.checks[0].ok = false;
    account.revisions.push(next); turn.status = 'completed'; turn.revisionId = next.id;
  };
  const snapshot = account => {
    if (account.pending && ++account.pending.polls >= 2) finish(account);
    return clone({ state: account.state, revision: account.revisions.at(-1), html: account.html, session: account.session });
  };
  const fetchImpl = async (url, options) => {
    const path = new URL(url).pathname, body = options.body ? JSON.parse(options.body) : undefined;
    requests.push({ path, body });
    if (path === '/api/auth/people') return reply({ users: [...accounts.values()].map(account => account.user) });
    if (path === '/api/auth/sign-in') {
      assert.deepEqual(Object.keys(body), ['userId']);
      const account = accounts.get(body.userId);
      const token = `token-${body.userId}`; tokens.set(token, account);
      return reply({ token, user: { id: body.userId }, ownSpaceId: account.user.ownSpaceId });
    }
    const account = tokens.get(options.headers.Authorization?.replace('Bearer ', ''));
    assert.ok(account, 'Authenticated owner requests are required');
    if (path === '/api/auth/sign-out') { tokens.delete(`token-${account.user.id}`); return reply({ ok: true }); }
    const prefix = `/api/spaces/${account.user.ownSpaceId}`;
    assert.ok(path.startsWith(prefix), 'Only the selected owner world is addressed');
    if (path === `${prefix}/turn`) {
      assert.deepEqual(Object.keys(body), ['message']);
      return reply({ turnId: begin(account, body.message).id });
    }
    if (path === `${prefix}/revisions`) return reply(account.revisions);
    if (path === `${prefix}/icon/generate`) { assert.deepEqual(body, {}); account.icon.status = 'generating'; return reply({ icon: account.icon }); }
    if (path === `${prefix}/icon`) {
      if (account.icon.status === 'generating' && ++account.iconPolls === 2) account.icon = { status: 'ready', version: 'new', dataUrl: 'new-test-image' };
      return reply({ icon: account.icon });
    }
    assert.equal(path, prefix, 'No reset or arbitrary write route is allowed');
    return reply(snapshot(account));
  };
  return { accounts, requests, fetchImpl, begin, get peak() { return peak; }, get signedIn() { return tokens.size; } };
}
async function fixture(t, ids) {
  const directory = await mkdtemp(join(tmpdir(), 'little-worlds-retheme-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const markerFile = join(directory, 'devday-restyle.json');
  const api = mockApi(ids);
  const validations = [];
  return {
    api, markerFile, validations,
    ledger: async () => JSON.parse(await readFile(markerFile, 'utf8')),
    run: options => rethemeDevday({ markerFile, fetchImpl: api.fetchImpl, pollMs: 0, timeoutMs: 1000, log() {},
      verify: async (source, tests, state, actors) => { validations.push({ source, tests, state, actors }); return { ok: true, checks: [{ name: 'Original behavior', ok: true }] }; }, ...options }),
  };
}

test('retheme uses authenticated ordinary turns, discovers all worlds and preserves genuine legacy blank canvases', async t => {
  const f = await fixture(t);
  const leo = f.api.accounts.get('leo');
  leo.state = { projects: [], contributions: [], extras: {} }; leo.html = ''; leo.revisions[0].source = blankSeedSource;
  const results = await f.run({ icons: true });
  assert.deepEqual(results.map(result => result.status), ['restyled', 'restyled', 'blank']);
  assert.equal(f.api.peak, 2); assert.equal(f.api.signedIn, 0);
  assert.equal(f.validations.length, 2); assert.ok(f.validations.every(call => call.tests === 'original tests'));
  assert.equal(f.api.requests.filter(r => r.path.endsWith('/turn')).length, 2);
  assert.equal(f.api.requests.filter(r => r.path.endsWith('/icon/generate')).length, 2);
  assert.ok(f.api.requests.filter(r => r.path.endsWith('/turn')).every(r => r.body.message.includes(devdayRestylePrompt)));
  const ledger = await f.ledger();
  assert.deepEqual(Object.keys(ledger.worlds), ['mira', 'james']);
  assert.equal(ledger.worlds.mira.status, 'complete'); assert.equal(ledger.worlds.mira.iconStatus, 'complete');
  assert.ok(!JSON.stringify(ledger).includes('original tests'), 'The ledger contains hashes, never source or visitor state');
  await assert.rejects(readFile(`${f.markerFile}.lock`), { code: 'ENOENT' });
});

test('successful rerun does not recreate worlds or icons and preserves later owner changes', async t => {
  const f = await fixture(t, ['mira']);
  await f.run({ icons: true });
  f.api.accounts.get('mira').revisions.push({ ...revision(3), source: source('#006aff') });
  const before = clone(f.api.accounts.get('mira'));
  const result = await f.run({ icons: true });
  assert.equal(result[0].status, 'skipped'); assert.deepEqual(f.api.accounts.get('mira'), before);
  assert.equal(f.api.requests.filter(r => r.path.endsWith('/turn')).length, 1);
  assert.equal(f.api.requests.filter(r => r.path.endsWith('/icon/generate')).length, 1);
});

for (const outcome of ['state', 'metadata', 'reducer', 'bad-check', 'failed']) {
  test(`${outcome} drift is reported rather than accepted, and no icon request follows`, async t => {
    const f = await fixture(t, ['mira']); f.api.accounts.get('mira').outcome = outcome;
    const result = await f.run({ icons: true });
    assert.equal(result[0].status, 'failed');
    assert.notEqual((await f.ledger()).worlds.mira.status, 'complete');
    assert.equal(f.api.requests.filter(r => r.path.endsWith('/icon/generate')).length, 0);
    assert.equal(f.api.signedIn, 0);
    const repeated = await f.run(); assert.equal(repeated[0].status, 'failed');
    assert.equal(f.api.requests.filter(r => r.path.endsWith('/turn')).length, 1, 'A failed verification never silently submits another paid turn');
  });
}

test('failure of the original test suite prevents successful marking even when new tests pass', async t => {
  const f = await fixture(t, ['mira']);
  const results = await f.run({ verify: async () => ({ ok: false, checks: [{ name: 'Lost behavior', ok: false }] }) });
  assert.equal(results[0].status, 'failed'); assert.match(results[0].error, /ORIGINAL feature tests/);
  assert.notEqual((await f.ledger()).worlds.mira.status, 'complete');
});

test('an unrelated active edit remains untouched', async t => {
  const f = await fixture(t, ['mira']); f.api.begin(f.api.accounts.get('mira'), 'Some other edit');
  const result = await f.run(); assert.equal(result[0].status, 'failed'); assert.match(result[0].error, /unrelated edit/);
  assert.equal(f.api.requests.filter(r => r.path.endsWith('/turn')).length, 0);
  await assert.rejects(readFile(f.markerFile), { code: 'ENOENT' });
});

test('resume after network failure recovers the exact existing turn instead of paying twice', async t => {
  const f = await fixture(t, ['mira']);
  let interrupted = false;
  const fetchImpl = async (url, options) => {
    const answer = await f.api.fetchImpl(url, options);
    if (url.endsWith('/turn') && !interrupted) { interrupted = true; throw new Error('Connection interrupted after POST'); }
    return answer;
  };
  assert.equal((await f.run({ fetchImpl }))[0].status, 'failed');
  assert.equal((await f.run())[0].status, 'restyled');
  assert.equal(f.api.requests.filter(r => r.path.endsWith('/turn')).length, 1);
});

test('only selector accepts discovered custom owners, and unknown selections stop before any model request', async t => {
  const f = await fixture(t, ['person-custom', 'mira']);
  assert.equal((await f.run({ only: ['space-person-custom'] }))[0].id, 'person-custom');
  await assert.rejects(f.run({ only: ['nonexistent'] }), /do not match/);
  assert.equal(f.api.requests.filter(r => r.path.endsWith('/turn')).length, 1);
});

test('fingerprints permit color and formatting changes but retain game mechanics and action metadata', () => {
  const current = { state: { projects: [], contributions: [], extras: {} }, revision: revision() };
  current.revision.meta.games = [{ id: 'snake', exportName: 'snakeGame', tickMs: 50, saveAction: 'save_snake' }];
  current.revision.source += 'export const snakeGame={init(saved){return saved||{score:0}},step(state,action){return state},view(state){return {objects:[]}}};';
  const next = clone(current); next.revision.source = next.revision.source.replaceAll(';', ';\n');
  next.revision.source = next.revision.source.replace('objects:[]', 'objects:[{fill:"#04b84c"}]');
  next.revision.meta.accent = '#04b84c';
  assert.deepEqual(preservationFingerprints(current), preservationFingerprints(next));
  next.revision.source = next.revision.source.replace('score:0', 'score:10');
  assert.notEqual(preservationFingerprints(current).gameLogic, preservationFingerprints(next).gameLogic);
});

test('transitive helper bodies and constants are included without changing the direct reducer hash', () => {
  const current = { state: { projects: [], contributions: [], extras: {} }, revision: revision() };
  current.revision.source = `const maxPoints=3;
    function permitted(n){return bounded(n);}
    function bounded(n){return n<=maxPoints;}
    export function reduce(state,action){return permitted(action.points)?state:{...state};}`;
  const before = preservationFingerprints(current);
  for (const changed of [current.revision.source.replace('maxPoints=3', 'maxPoints=300'), current.revision.source.replace('n<=maxPoints', 'n>=maxPoints')]) {
    const after = preservationFingerprints({ ...current, revision: { ...current.revision, source: changed } });
    assert.equal(before.reducer, after.reducer);
    assert.notEqual(before.logicDependencies, after.logicDependencies);
  }
});

test('dependency closure respects lexical shadowing and isolates unused drawing helpers', () => {
  const before = `const maxPoints=3; const palette=['#fff','#000'];
    const helpers={permitted(n){return n<=3;},draw(){return palette;}};
    export function reduce(state,action){const maxPoints=2;return helpers.permitted(action.points)&&maxPoints?state:{...state};}
    export function render(){return maxPoints+helpers.draw();}`;
  const after = before.replace('maxPoints=3', 'maxPoints=300').replace("'#fff'", "'#04b84c'").replace('return palette;', 'return palette.join();');
  assert.equal(logicDependencyFingerprint(before), logicDependencyFingerprint(after));
  assert.notEqual(logicDependencyFingerprint(before), logicDependencyFingerprint(before.replace('n<=3', 'n<=300')));
});

test('single-game custom export protects transitive mechanics while excluding view palette dependencies', () => {
  const current = { state: { projects: [], contributions: [], extras: {} }, revision: revision() };
  current.revision.meta.game = { id: 'snake', exportName: 'customSnake', tickMs: 50, saveAction: 'save_snake' };
  current.revision.source = `const speed=2;const palette=['#fff','#000'];
    function advance(state){return {...state,x:state.x+speed};}
    export const customSnake={init(){return {x:0};},step(state){return advance(state);},view(){return palette;}};
    export function reduce(state){customSnake.view();return state;}`;
  const before = preservationFingerprints(current);
  const recolored = { ...current, revision: { ...current.revision, source: current.revision.source.replace("'#fff'", "'#04b84c'") } };
  assert.deepEqual(before, preservationFingerprints(recolored));
  const spedUp = { ...current, revision: { ...current.revision, source: current.revision.source.replace('speed=2', 'speed=20') } };
  assert.notEqual(before.logicDependencies, preservationFingerprints(spedUp).logicDependencies);
});

test('render size checks and indirect game-view validation remain presentation boundaries', () => {
  const meta = { games: [{ id: 'game', exportName: 'testGame' }] };
  const before = `const palette=['#fff'];
    export const testGame={init(){return {};},step(s){return s;},view(){return palette;}};
    function definitions(){return [{game:testGame}];}
    export function render(){return '<main>old colors</main>';}
    export function reduce(state){definitions()[0].game.view(state);if(render().length>160000)throw Error();return state;}`;
  const after = before.replace("'#fff'", "'#04b84c'").replace('old colors', 'DevDay').replace('return palette;', 'return palette.map(x=>x);');
  assert.equal(logicDependencyFingerprint(before, meta), logicDependencyFingerprint(after, meta));
});

test('catalog-like dependency colors may change while identities and validation values remain protected', () => {
  const source = `const topics=[{id:'ideas',color:'#fff',maxPoints:3}];
    function topicFor(id){return topics.find(topic=>topic.id===id);}
    export function reduce(state,action){if(!topicFor(action.topicId))throw Error();return state;}`;
  assert.equal(logicDependencyFingerprint(source), logicDependencyFingerprint(source.replace("color:'#fff'", "color:'#04b84c'")));
  assert.notEqual(logicDependencyFingerprint(source), logicDependencyFingerprint(source.replace("id:'ideas'", "id:'deleted'")));
  assert.notEqual(logicDependencyFingerprint(source), logicDependencyFingerprint(source.replace('maxPoints:3', 'maxPoints:300')));
});

test('an older in-flight ledger derives the new dependency baseline from the original revision', async t => {
  const f = await fixture(t, ['mira']);
  let interrupted = false;
  const fetchImpl = async (url, options) => {
    const answer = await f.api.fetchImpl(url, options);
    if (url.endsWith('/turn') && !interrupted) { interrupted = true; throw new Error('Interrupted after POST'); }
    return answer;
  };
  assert.equal((await f.run({ fetchImpl }))[0].status, 'failed');
  const ledger = await f.ledger(); delete ledger.worlds.mira.fingerprints.logicDependencies;
  await writeFile(f.markerFile, JSON.stringify(ledger));
  assert.equal((await f.run())[0].status, 'restyled');
  assert.ok((await f.ledger()).worlds.mira.fingerprints.logicDependencies);
  assert.equal(f.api.requests.filter(request => request.path.endsWith('/turn')).length, 1);
});

test('an older accepted ledger checks dependencies without regenerating or rewriting its record', async t => {
  const f = await fixture(t, ['mira']); await f.run({ icons: true });
  const ledger = await f.ledger(); delete ledger.worlds.mira.fingerprints.logicDependencies;
  const originalRecord = JSON.stringify(ledger); await writeFile(f.markerFile, originalRecord);
  assert.equal((await f.run({ icons: true }))[0].status, 'skipped');
  assert.equal(await readFile(f.markerFile, 'utf8'), originalRecord);
  assert.equal(f.api.requests.filter(request => request.path.endsWith('/turn')).length, 1);
  assert.equal(f.api.requests.filter(request => request.path.endsWith('/icon/generate')).length, 1);
});

for (const interruptedStage of ['prepared', 'running']) {
  test(`an icon interrupted while ${interruptedStage} is resubmitted when no server job is active`, async t => {
    const f = await fixture(t, ['mira']); await f.run();
    const ledger = await f.ledger();
    Object.assign(ledger.worlds.mira, { iconStatus: interruptedStage, originalIconVersion: 'old' });
    await writeFile(f.markerFile, JSON.stringify(ledger));
    assert.equal((await f.run({ icons: true }))[0].iconStatus, 'complete');
    assert.equal(f.api.requests.filter(request => request.path.endsWith('/icon/generate')).length, 1);
    assert.equal(f.api.requests.filter(request => request.path.endsWith('/turn')).length, 1);
  });
}

test('an active icon job resumes polling without a duplicate image request', async t => {
  const f = await fixture(t, ['mira']); await f.run();
  const ledger = await f.ledger();
  Object.assign(ledger.worlds.mira, { iconStatus: 'running', originalIconVersion: 'old' });
  await writeFile(f.markerFile, JSON.stringify(ledger));
  f.api.accounts.get('mira').icon.status = 'generating';
  assert.equal((await f.run({ icons: true }))[0].iconStatus, 'complete');
  assert.equal(f.api.requests.filter(request => request.path.endsWith('/icon/generate')).length, 0);
});

test('an explicitly selected repair is verified against the original pre-restyle baseline', async t => {
  const f = await fixture(t, ['mira']);
  const account = f.api.accounts.get('mira');
  account.outcome = 'reducer';
  assert.equal((await f.run())[0].status, 'failed');
  account.outcome = 'success';
  f.api.begin(account, 'Restore the exact original reducer while retaining DevDay colors.');
  // Two ordinary reads finish the simulated manual repair.
  await f.api.fetchImpl('http://127.0.0.1/api/auth/sign-in', { method: 'POST', body: JSON.stringify({userId:'mira'}), headers:{} });
  for (let i=0;i<2;i++) await f.api.fetchImpl('http://127.0.0.1/api/spaces/space-mira', {method:'GET',headers:{Authorization:'Bearer token-mira'}});
  const result = await f.run({ verifyRepair: true });
  assert.equal(result[0].status, 'restyled');
  const entry = (await f.ledger()).worlds.mira;
  assert.equal(entry.baselineRevisionId, 1); assert.equal(entry.revisionId, 3);
  assert.equal(entry.originalTurnId, 'turn-1'); assert.equal(entry.turnId, 'turn-2');
  assert.equal(f.api.requests.filter(r=>r.path.endsWith('/turn')).length, 1, 'Repair verification itself makes no model call');
});

test('CLI accepts explicit local settings and rejects duplicate or malformed options', () => {
  assert.deepEqual(parseRethemeArgs(['--only', 'mira,space-custom', '--icons']), { only: ['mira', 'space-custom'], icons: true });
  assert.equal(parseRethemeArgs(['--api-url', 'http://127.0.0.1:4318']).baseUrl, 'http://127.0.0.1:4318');
  assert.ok(parseRethemeArgs(['--data-dir', '/tmp/example']).markerFile.endsWith('/tmp/example/devday-restyle.json'));
  for (const args of [['--only'], ['--only', 'mira,mira'], ['--icons', '--icons'], ['--unknown'], ['--api-url', 'https://example.com'], ['--data-dir', '--icons']]) assert.throws(() => parseRethemeArgs(args));
  assert.ok(devdayRestylePrompt.length < 3800, 'The request plus migration tag fits the turn endpoint limit');
});
