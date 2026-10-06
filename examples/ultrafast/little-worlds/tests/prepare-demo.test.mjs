import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { prepareDemo, parsePreparationArgs } from '../scripts/prepare-demo.mjs';
import { blankSeedSource, blankSeedTests } from '../server/seed.mjs';
import { demoPrompts } from '../server/demo-prompts.mjs';

const clone = value => structuredClone(value);
const brief = (id, requiredCapabilities = []) => ({ id, name: id, prompt: `Create ${id}'s own working canvas.`, requiredCapabilities });
const blankRevision = () => ({ id: 1, source: blankSeedSource, tests: blankSeedTests, meta: {}, checks: [{ name: 'Empty seed', ok: true }] });
const response = data => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });

function simulatedApi(prompts) {
  const accounts = new Map(prompts.map(person => [person.id, {
    id: person.id, sessionId: `thread-${person.id}`, turns: [], events: [], revisions: [blankRevision()],
    currentRevisionId: 1, html: '', pending: null, outcome: 'success', capabilities: person.requiredCapabilities,
    actions: (person.requiredAgentActions || []).map(name => ({ name })),
    games: (person.requiredGames || []).map(id => ({ id })),
  }]));
  const tokens = new Map();
  const requests = [];
  let nextToken = 0;
  let nextTurn = 0;
  let active = 0;
  let peak = 0;

  function finish(account) {
    const turn = account.pending.turn;
    account.pending = null;
    active--;
    if (account.outcome === 'failed') {
      turn.status = 'failed';
      account.events.push({ type: 'turn.failed', turnId: turn.id, detail: 'The generated code did not pass.' });
      return;
    }
    const revisionId = Math.max(...account.revisions.map(revision => revision.id)) + 1;
    const revision = {
      id: revisionId,
      source: `export const meta={title:'${account.id}',layout:'canvas'}; /* generated revision ${revisionId} */`,
      tests: 'export function runTests(){return [{name:"Generated behavior",ok:true}]}',
      meta: { layout: 'canvas', capabilities: [...account.capabilities], agent: { actions: account.actions }, games: account.games },
      checks: [{ name: 'Generated behavior', ok: true }, { name: 'Host isolation', ok: true }],
    };
    if (account.outcome === 'bad-checks') revision.checks[0].ok = false;
    if (account.outcome === 'blank-source') revision.source = blankSeedSource;
    if (account.outcome === 'missing-layout') delete revision.meta.layout;
    if (account.outcome === 'missing-capability') revision.meta.capabilities = [];
    if (account.outcome === 'missing-action') revision.meta.agent.actions = [];
    if (account.outcome === 'missing-game') revision.meta.games = account.games.slice(0, -1);
    account.revisions.push(revision);
    account.currentRevisionId = revisionId;
    account.html = account.outcome === 'empty-html' ? '' : `<main>${account.id}'s generated page</main>`;
    turn.status = 'completed';
    // Production snapshots omit revisionId on turns; the completion event is
    // the normal recovery path used by preparation after a process restart.
    account.events.push({ type: 'turn.completed', turnId: turn.id, data: { revisionId } });
  }
  function begin(account, prompt) {
    const turn = { id: `turn-${++nextTurn}`, message: prompt, status: 'running' };
    account.turns.push(turn);
    account.pending = { turn, polls: 0 };
    peak = Math.max(peak, ++active);
    return turn;
  }
  function snapshot(account) {
    if (account.pending && ++account.pending.polls >= 2) finish(account);
    return clone({
      session: { id: account.sessionId, status: account.pending ? 'running' : 'idle', turns: account.turns },
      revision: account.revisions.find(revision => revision.id === account.currentRevisionId),
      html: account.html, events: account.events,
    });
  }
  const fetchImpl = async (url, options) => {
    const path = new URL(url).pathname;
    const body = options.body === undefined ? undefined : JSON.parse(options.body);
    requests.push({ path, method: options.method, body });
    assert.equal(options.method, body === undefined ? 'GET' : 'POST');
    if (body !== undefined) assert.equal(options.headers['Content-Type'], 'application/json');
    assert.ok(options.signal instanceof AbortSignal);
    if (path === '/api/auth/sign-in') {
      assert.equal(options.headers.Authorization, undefined);
      assert.deepEqual(Object.keys(body), ['userId']);
      assert.ok(accounts.has(body.userId));
      const token = `test-token-${++nextToken}`;
      tokens.set(token, body.userId);
      return response({ token, ownSpaceId: body.userId, user: { id: body.userId } });
    }
    const token = options.headers.Authorization?.replace(/^Bearer /, '');
    const id = tokens.get(token);
    assert.ok(id, 'Every non-login request uses the selected person’s bearer identity.');
    if (path === '/api/auth/sign-out') {
      tokens.delete(token);
      assert.deepEqual(body, {});
      return response({ ok: true });
    }
    const match = /^\/api\/spaces\/([^/]+)(?:\/(turn|revisions))?$/.exec(path);
    assert.ok(match, `Unexpected preparation route: ${path}`);
    assert.equal(decodeURIComponent(match[1]), id, 'Preparation can only address its signed-in person’s own space.');
    const account = accounts.get(id);
    if (match[2] === 'turn') {
      assert.equal(options.method, 'POST');
      assert.deepEqual(Object.keys(body), ['message'], 'Only an ordinary creative request is submitted, never source or seed state.');
      assert.equal(account.pending, null);
      return response({ turnId: begin(account, body.message).id, steering: false });
    }
    assert.equal(options.method, 'GET');
    return response(match[2] === 'revisions' ? clone(account.revisions) : snapshot(account));
  };
  return {
    accounts, requests, fetchImpl,
    get turnRequests() { return requests.filter(request => request.path.endsWith('/turn')); },
    get peak() { return peak; },
    get signedInCount() { return tokens.size; },
    seedRunning(id, prompt) { return begin(accounts.get(id), prompt); },
    seedCompleted(id, prompt) { const turn = begin(accounts.get(id), prompt); finish(accounts.get(id)); return turn; },
    addCurrentEdit(id) {
      const account = accounts.get(id);
      const revision = { ...clone(account.revisions.at(-1)), id: account.currentRevisionId + 1, source: 'A later owner-authored change' };
      account.revisions.push(revision);
      account.currentRevisionId = revision.id;
      account.html = '<main>A later owner-authored change</main>';
    },
    reset(id) {
      const account = accounts.get(id);
      assert.equal(account.pending, null);
      Object.assign(account, { sessionId: `${account.sessionId}-reset`, turns: [], events: [], revisions: [blankRevision()], currentRevisionId: 1, html: '' });
    },
  };
}

async function fixture(t, prompts = [brief('mira')]) {
  const directory = await mkdtemp(join(tmpdir(), 'little-worlds-prepare-test-'));
  const markerFile = join(directory, 'preparation.json');
  t.after(() => rm(directory, { recursive: true, force: true }));
  const api = simulatedApi(prompts);
  return {
    ...api,
    api, markerFile,
    run: options => prepareDemo({ markerFile, prompts, version: 'test-preparation-v1', fetchImpl: api.fetchImpl, pollMs: 0, timeoutMs: 5000, log() {}, ...options }),
    ledger: async () => JSON.parse(await readFile(markerFile, 'utf8')),
  };
}

test('preparation submits normal authenticated turns, limits concurrency to two and marks verified revisions', async t => {
  const james = parsePreparationArgs(['--only', 'james']).prompts[0];
  const prompts = [brief('mira'), james, brief('jake', ['health-chat']), brief('erica')];
  const state = await fixture(t, prompts);
  const result = await state.run();
  assert.deepEqual(result.map(item => item.status), ['generated', 'generated', 'generated', 'generated']);
  assert.equal(state.api.peak, 2);
  assert.equal(state.api.turnRequests.length, prompts.length);
  assert.deepEqual(state.api.turnRequests.map(request => request.body.message).sort(), prompts.map(person => person.prompt).sort());
  assert.deepEqual(state.api.accounts.get('james').revisions.at(-1).meta.capabilities, [], 'James can be prepared without a news service.');
  const ledger = await state.ledger();
  assert.deepEqual(Object.keys(ledger.prepared).sort(), prompts.map(person => person.id).sort());
  for (const person of prompts) {
    const marker = ledger.prepared[person.id];
    assert.equal(marker.sessionId, `thread-${person.id}`);
    assert.equal(marker.revisionId, 2);
    assert.match(marker.sourceHash, /^[a-f0-9]{64}$/);
    assert.match(marker.promptHash, /^[a-f0-9]{64}$/);
    assert.equal(marker.preparationVersion, 'test-preparation-v1');
    assert.ok(marker.turnId);
  }
  assert.equal(state.api.signedInCount, 0, 'Every temporary preparation identity is signed out.');
  await assert.rejects(readFile(`${state.markerFile}.lock`), { code: 'ENOENT' });
});

test('all DevDay briefs fit real turn limits and retain their required interactive capabilities', async t => {
  const state = await fixture(t, demoPrompts);
  for (const person of demoPrompts) {
    assert.ok(person.prompt.length <= 4000, `${person.id} must fit the builder turn limit.`);
    assert.match(person.prompt, /OpenAI DevDay 2026/);
    assert.doesNotMatch(person.prompt, /warm ivory|warm paper|editorial serif|expressive serif|warm pixel cream/i);
  }
  const result = await state.run();
  assert.ok(result.every(person => person.status === 'generated'), JSON.stringify(result));
  assert.equal(state.api.turnRequests.length, 7);
  assert.equal(state.api.signedInCount, 0);
  assert.deepEqual(demoPrompts.find(person => person.id === 'jake').requiredCapabilities, ['health-chat']);
  assert.deepEqual(demoPrompts.find(person => person.id === 'iris').requiredAgentActions, ['paint_pixels', 'fill_canvas', 'paint_shapes', 'flood_fill']);
  assert.deepEqual(demoPrompts.find(person => person.id === 'luca').requiredCapabilities, ['space-agent']);
  assert.deepEqual(demoPrompts.find(person => person.id === 'karen').requiredGames, ['pacman', 'space-invaders', 'snake', 'tetris']);
});

test('a second run makes no new builder calls and preserves later current edits', async t => {
  const state = await fixture(t);
  await state.run();
  const markerBefore = await readFile(state.markerFile, 'utf8');
  state.api.addCurrentEdit('mira');
  const before = clone(state.api.accounts.get('mira'));
  const result = await state.run();
  assert.deepEqual(result, [{ id: 'mira', status: 'skipped', revisionId: 2 }]);
  assert.equal(state.api.turnRequests.length, 1);
  assert.deepEqual(state.api.accounts.get('mira'), before);
  assert.equal(await readFile(state.markerFile, 'utf8'), markerBefore);
  assert.equal(state.api.signedInCount, 0);
});

test('rebuild explicitly submits another normal turn and updates the successful marker', async t => {
  const state = await fixture(t);
  await state.run();
  const previous = (await state.ledger()).prepared.mira;
  const result = await state.run({ rebuild: true });
  assert.deepEqual(result, [{ id: 'mira', status: 'generated', revisionId: 3 }]);
  assert.equal(state.api.turnRequests.length, 2);
  const current = (await state.ledger()).prepared.mira;
  assert.notEqual(current.turnId, previous.turnId);
  assert.notEqual(current.sourceHash, previous.sourceHash);
  assert.equal(current.sessionId, previous.sessionId);
});

test('a matching running turn is resumed without a duplicate submission', async t => {
  const person = brief('mira');
  const state = await fixture(t, [person]);
  const turn = state.api.seedRunning('mira', person.prompt);
  const result = await state.run();
  assert.deepEqual(result, [{ id: 'mira', status: 'generated', revisionId: 2 }]);
  assert.equal(state.api.turnRequests.length, 0);
  assert.equal((await state.ledger()).prepared.mira.turnId, turn.id);
  assert.equal(state.api.signedInCount, 0);
});

test('a completed matching turn is recovered without a marker and preserves a later owner edit', async t => {
  const person = brief('mira');
  const state = await fixture(t, [person]);
  const turn = state.api.seedCompleted('mira', person.prompt);
  state.api.addCurrentEdit('mira');
  const before = clone(state.api.accounts.get('mira'));
  const result = await state.run();
  assert.deepEqual(result, [{ id: 'mira', status: 'generated', revisionId: 2 }]);
  assert.equal(state.api.turnRequests.length, 0);
  assert.deepEqual(state.api.accounts.get('mira'), before);
  assert.equal((await state.ledger()).prepared.mira.turnId, turn.id);
});

test('resetting the thread invalidates its old marker and builds the new empty session', async t => {
  const state = await fixture(t);
  await state.run();
  const previous = (await state.ledger()).prepared.mira;
  state.api.reset('mira');
  const result = await state.run();
  assert.deepEqual(result, [{ id: 'mira', status: 'generated', revisionId: 2 }]);
  assert.equal(state.api.turnRequests.length, 2);
  const current = (await state.ledger()).prepared.mira;
  assert.notEqual(current.sessionId, previous.sessionId);
  assert.notEqual(current.turnId, previous.turnId);
});

for (const outcome of ['failed', 'missing-capability', 'bad-checks', 'blank-source', 'missing-layout', 'empty-html']) {
  test(`${outcome} cannot create a successful preparation marker`, async t => {
    const state = await fixture(t, [brief('jake', ['health-chat'])]);
    state.api.accounts.get('jake').outcome = outcome;
    const result = await state.run();
    assert.equal(result[0].status, 'failed');
    assert.ok(result[0].error);
    assert.equal(state.api.turnRequests.length, 1);
    await assert.rejects(readFile(state.markerFile), { code: 'ENOENT' });
    await assert.rejects(readFile(`${state.markerFile}.lock`), { code: 'ENOENT' });
    assert.equal(state.api.signedInCount, 0);
  });
}

test('an unrelated active edit is preserved without submitting or marking preparation', async t => {
  const state = await fixture(t);
  state.api.seedRunning('mira', 'An owner is currently editing the page.');
  const result = await state.run();
  assert.equal(result[0].status, 'failed');
  assert.match(result[0].error, /already has an active edit/);
  assert.equal(state.api.turnRequests.length, 0);
  assert.equal(state.api.accounts.get('mira').turns[0].status, 'running');
  await assert.rejects(readFile(state.markerFile), { code: 'ENOENT' });
  assert.equal(state.api.signedInCount, 0);
});

test('invalid concurrency is rejected before any request or marker write', async t => {
  const state = await fixture(t);
  await assert.rejects(state.run({ concurrency: 3 }), /one or two concurrent builds/);
  assert.equal(state.api.requests.length, 0);
  await assert.rejects(readFile(state.markerFile), { code: 'ENOENT' });
});

test('selected preparation builds only Iris and Luca while preserving existing markers and pages', async t => {
  const options = parsePreparationArgs(['--only', 'iris,luca']);
  const prompts = [brief('mira'), ...options.prompts];
  const state = await fixture(t, prompts);
  await state.run({ prompts: [prompts[0]] });
  const before = clone(state.api.accounts.get('mira'));
  const marker = (await state.ledger()).prepared.mira;
  const result = await state.run(options);
  assert.deepEqual(result.map(item => [item.id, item.status]), [['iris', 'generated'], ['luca', 'generated']]);
  assert.deepEqual(state.api.accounts.get('mira'), before);
  assert.deepEqual((await state.ledger()).prepared.mira, marker);
  assert.equal(state.api.signedInCount, 0);
});

test('a shared canvas without its real painting action cannot be marked prepared', async t => {
  const { prompts } = parsePreparationArgs(['--only', 'iris']);
  const state = await fixture(t, prompts);
  state.api.accounts.get('iris').outcome = 'missing-action';
  const result = await state.run();
  assert.equal(result[0].status, 'failed');
  assert.match(result[0].error, /required agent action/);
  await assert.rejects(readFile(state.markerFile), { code: 'ENOENT' });
});

test('selected arcade preparation builds only Karen and preserves the existing prepared neighborhood', async t => {
  const options = parsePreparationArgs(['--only', 'karen']);
  const karen = options.prompts[0];
  assert.deepEqual(karen.requiredGames, ['pacman', 'space-invaders', 'snake', 'tetris']);
  const state = await fixture(t, [brief('mira'), karen]);
  await state.run({ prompts: [brief('mira')] });
  const before = clone(state.api.accounts.get('mira'));
  const marker = (await state.ledger()).prepared.mira;
  const result = await state.run(options);
  assert.deepEqual(result.map(item => [item.id, item.status]), [['karen', 'generated']]);
  assert.deepEqual(state.api.accounts.get('mira'), before);
  assert.deepEqual((await state.ledger()).prepared.mira, marker);
  assert.equal(state.api.signedInCount, 0);
  const requestCount = state.api.turnRequests.length;
  assert.deepEqual(await state.run(options), [{ id: 'karen', status: 'skipped', revisionId: 2 }]);
  assert.equal(state.api.turnRequests.length, requestCount, 'A prepared arcade is not regenerated on a repeated request.');
});

test('an arcade missing any requested game cannot be marked prepared', async t => {
  const { prompts } = parsePreparationArgs(['--only', 'karen']);
  const state = await fixture(t, prompts);
  state.api.accounts.get('karen').outcome = 'missing-game';
  const result = await state.run();
  assert.equal(result[0].status, 'failed');
  assert.match(result[0].error, /required playable game/);
  await assert.rejects(readFile(state.markerFile), { code: 'ENOENT' });
  assert.equal(state.api.signedInCount, 0);
});

test('preparation CLI rejects unknown or ambiguous selections before model requests', () => {
  for (const args of [['--only'], ['--only', ''], ['--only', 'leo'], ['--only', 'iris,iris'], ['--only', 'iris', '--only', 'luca'], ['--rebuild', '--rebuild'], ['--unknown']]) {
    assert.throws(() => parsePreparationArgs(args), /Usage:/);
  }
  assert.deepEqual(parsePreparationArgs([]).prompts.map(person => person.id), ['mira', 'james', 'jake', 'erica', 'iris', 'luca', 'karen']);
  assert.equal(parsePreparationArgs(['--rebuild', '--only', 'luca']).rebuild, true);
});
