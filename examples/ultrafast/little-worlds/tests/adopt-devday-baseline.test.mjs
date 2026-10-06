import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { demoUsers } from '../server/identity.mjs';
import { beginDemoReset } from '../server/demo-reset.mjs';
import { DEV_DAY_THEME_VERSION } from '../server/devday-theme.mjs';
import { devdayRestyleVersion } from '../scripts/retheme-devday.mjs';
import { adoptDevdayBaseline, assertBaselineServerStopped, parseBaselineArgs } from '../scripts/adopt-devday-baseline.mjs';

const hash = text => createHash('sha256').update(text).digest('hex');
const sourceHash = revision => hash(`${revision.source}\n${revision.tests}`);
const checks = [{ name: 'Preserves original behavior', ok: true }];
const pathFor = (directory, id) => id === 'mira' ? join(directory, 'space.json') : join(directory, 'spaces', id, 'space.json');
const json = async filename => JSON.parse(await readFile(filename, 'utf8'));
const writeJson = (filename, value) => writeFile(filename, JSON.stringify(value));
const revision = (id, color) => {
  const meta = { title: 'A useful world', subtitle: 'Original subtitle', layout: 'canvas', accent: color, projects: [{ id: 'tile', title: 'Original tile', description: 'Keep me', color }] };
  return { id, meta, checks, createdAt: 'keep revision date',
    source: `export const meta=${JSON.stringify(meta)}; export function render(state){return '<main style="color:${color}">Original tile</main>';} export function reduce(){throw Error('Unknown action');}`,
    tests: `export function runTests(api){return [{name:'Original tile remains',ok:api.render(api.initialState,{id:'check',name:'Check'}).includes('Original tile')},{name:'Same catalog',ok:api.initialState.projects[0].id==='tile'}];}` };
};

async function fixture(t) {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-baseline-adopt-'));
  t.after(() => rm(parent, { recursive: true, force: true }));
  const dataDir = join(parent, 'data');
  const history = `${dataDir}-reset-history`;
  await mkdir(dataDir); await mkdir(history);
  await writeJson(join(dataDir, 'identities.json'), { version: 1, users: demoUsers });
  const baseline = { version: 1, createdAt: 'keep baseline date', users: demoUsers.slice(0, 8), spaces: {}, prepared: {} };
  const ledger = { version: 1, theme: devdayRestyleVersion, worlds: {} };
  const before = {};
  for (const person of demoUsers) {
    const old = revision(1, '#567764'), current = revision(2, '#04b84c');
    const state = { projects: old.meta.projects, contributions: [{ id: 'vote', actorId: 'mira', projectId: 'tile', points: 1 }], extras: { notes: { mira: { actorId: 'mira', text: 'Baseline note' } } } };
    const initial = { revision: old, state, icon: { data: 'old', version: 'old' } };
    const saved = { version: 1, ownerId: person.id, kind: person.kind, currentRevisionId: 2, revisions: [old, current], state: { ...state, extras: { notes: { mira: { actorId: 'mira', text: 'Later live note' } } } },
      session: { id: `session-${person.id}`, status: 'idle', turns: [{ id: 'keep-turn', message: 'Original request' }], items: [{ role: 'user', content: 'Original context' }] }, events: [{ id: 'keep-event' }], sequence: 9,
      icon: { status: 'ready', source: 'generated', version: `icon-${person.id}`, mimeType: 'image/webp', data: 'dGVzdA==', themeVersion: DEV_DAY_THEME_VERSION, fingerprint: hash(`${DEV_DAY_THEME_VERSION}\0${current.source}`) },
      ...(person.id === 'nora' ? { initialBaseline: initial } : {}),
    };
    if (person.id !== 'mira') await mkdir(join(dataDir, 'spaces', person.id), { recursive: true });
    await writeJson(pathFor(dataDir, person.id), saved);
    before[person.id] = structuredClone(saved);
    if (person.id !== 'nora') baseline.spaces[person.id] = { ...saved, state, currentRevisionId: 1, revisions: [old] };
    if (person.id !== 'leo') ledger.worlds[person.id] = { status: 'complete', sessionId: saved.session.id, revisionId: 2, sourceHash: sourceHash(current), iconStatus: 'complete', iconVersion: saved.icon.version };
  }
  baseline.prepared.mira = { revisionId: 1, sourceHash: sourceHash(baseline.spaces.mira.revisions[0]), turnId: 'keep-turn', sessionId: 'session-mira' };
  const baselineFile = join(history, 'baseline.json'), markerFile = join(dataDir, 'devday-restyle.json');
  await writeJson(baselineFile, baseline); await writeJson(markerFile, ledger);
  return { dataDir, history, baseline, baselineFile, markerFile, ledger, before,
    run: options => adoptDevdayBaseline({ dataDir, probeServer: async () => {}, verify: async () => ({ ok: true, checks }), log() {}, ...options }),
  };
}

test('baseline adoption is read-only by default and verifies saved baseline records, not current participation', async t => {
  const f = await fixture(t); const seen = [];
  const result = await f.run({ probeServer() { assert.fail('Dry run does not require stopping the app'); }, verify: async (source, tests, state, options) => {
    seen.push(state); assert.equal(options.projectCatalog, false); return { ok: true, checks };
  } });
  assert.equal(result.applied, false); assert.equal(result.files, 2); assert.equal(result.worlds.length, 8);
  assert.ok(seen.every(state => state.extras.notes.mira.text === 'Baseline note'));
  assert.ok(seen.every(state => state.projects[0].color === '#04b84c'));
  assert.deepEqual(await json(f.baselineFile), f.baseline);
  assert.deepEqual(await readdir(f.history), ['baseline.json']);
  for (const person of demoUsers) assert.deepEqual(await json(pathFor(f.dataDir, person.id)), f.before[person.id]);
});

test('offline adoption preserves baseline state, history, earlier revisions, and blank Leo; backs up exact original files', async t => {
  const f = await fixture(t); let probes = 0;
  const result = await f.run({ apply: true, probeServer: async () => { probes++; } });
  assert.equal(result.applied, true); assert.equal(result.files, 2); assert.equal(probes, 2);
  const adopted = await json(f.baselineFile);
  assert.equal(adopted.createdAt, f.baseline.createdAt);
  assert.deepEqual(adopted.users, f.baseline.users); assert.equal(adopted.spaces.nora, undefined);
  assert.deepEqual(adopted.spaces.leo, f.baseline.spaces.leo);
  for (const person of demoUsers.slice(0, 8).filter(person => person.id !== 'leo')) {
    const original = f.baseline.spaces[person.id], next = adopted.spaces[person.id];
    assert.deepEqual(next.state, { ...original.state, projects: original.state.projects.map(project => ({ ...project, color: '#04b84c' })) });
    assert.deepEqual(next.session, original.session); assert.deepEqual(next.events, original.events); assert.equal(next.sequence, original.sequence);
    assert.equal(next.currentRevisionId, 1); assert.equal(next.revisions[0].id, 1); assert.equal(next.revisions[0].createdAt, original.revisions[0].createdAt);
    assert.equal(next.revisions[0].source, f.before[person.id].revisions[1].source);
    assert.deepEqual(next.icon, f.before[person.id].icon);
  }
  assert.equal(adopted.prepared.mira.sourceHash, sourceHash(adopted.spaces.mira.revisions[0]));
  assert.equal(adopted.prepared.mira.turnId, 'keep-turn');
  for (const person of demoUsers) {
    const current = await json(pathFor(f.dataDir, person.id));
    if (person.id !== 'nora') assert.deepEqual(current, f.before[person.id]);
    else {
      assert.equal(current.initialBaseline.revision.source, current.revisions[1].source);
      assert.equal(current.initialBaseline.state.extras.notes.mira.text, 'Baseline note');
      delete current.initialBaseline; const original = structuredClone(f.before.nora); delete original.initialBaseline;
      assert.deepEqual(current, original);
    }
  }
  const manifest = await json(join(result.backupDirectory, 'manifest.json'));
  for (const item of manifest.files) assert.equal(hash(await readFile(join(result.backupDirectory, item.backup), 'utf8')), item.sha256);
  assert.deepEqual(await json(join(result.backupDirectory, manifest.files.find(item => item.filename === f.baselineFile).backup)), f.baseline);
  assert.equal((await f.run({ apply: true })).files, 0, 'Repeated adoption is idempotent');
});

for (const drift of ['incomplete', 'old-icon', 'new-owner-edit', 'running']) {
  test(`${drift} stops adoption before any write`, async t => {
    const f = await fixture(t);
    if (drift === 'incomplete') { f.ledger.worlds.james.status = 'running'; await writeJson(f.markerFile, f.ledger); }
    else {
      const filename = pathFor(f.dataDir, 'james'), data = await json(filename);
      if (drift === 'old-icon') data.icon.themeVersion = 'old-theme';
      if (drift === 'new-owner-edit') data.revisions[1].source += '\n// a later edit';
      if (drift === 'running') data.session.status = 'running';
      await writeJson(filename, data);
    }
    await assert.rejects(f.run({ apply: true }), /James:/);
    assert.deepEqual(await json(f.baselineFile), f.baseline); assert.deepEqual(await readdir(f.history), ['baseline.json']);
  });
}

test('original-state verification failure does not change any file', async t => {
  const f = await fixture(t);
  await assert.rejects(f.run({ apply: true, verify: async () => ({ ok: false, checks: [] }) }), /ORIGINAL reset baseline state/);
  assert.deepEqual(await json(f.baselineFile), f.baseline);
});

test('real sandbox verification accepts the themed fixture against its older saved baseline state', async t => {
  const f = await fixture(t);
  const result = await f.run({ verify: undefined });
  assert.equal(result.worlds.length, 8); assert.equal(result.applied, false);
});

test('a later normal reset uses adopted designs and appends Nora from the updated initial baseline', async t => {
  const f = await fixture(t);
  await f.run({ apply: true, verify: undefined });
  const reset = await beginDemoReset(f.dataDir);
  await reset.commit();
  for (const person of demoUsers.filter(person => person.id !== 'leo')) {
    const saved = await json(pathFor(f.dataDir, person.id));
    assert.equal(saved.revisions.find(revision => revision.id === saved.currentRevisionId).source, f.before[person.id].revisions[1].source);
    assert.equal(saved.icon.version, f.before[person.id].icon.version);
    assert.equal(saved.state.extras.notes.mira.text, 'Baseline note');
  }
  assert.deepEqual((await json(f.baselineFile)).users, demoUsers);
});

test('concurrent saved-file changes and active preparation locks prevent any adoption writes', async t => {
  const f = await fixture(t); let changed = false;
  await assert.rejects(f.run({ apply: true, verify: async () => {
    if (!changed) { changed = true; await writeJson(f.markerFile, { ...f.ledger, addedConcurrently: true }); }
    return { ok: true, checks };
  } }), /Saved data changed/);
  assert.deepEqual(await json(f.baselineFile), f.baseline);
  await writeFile(`${f.markerFile}.lock`, 'preparing');
  await assert.rejects(f.run({ apply: true }), /preparation lock/);
  assert.deepEqual(await readdir(f.history), ['baseline.json']);
});

test('adoption refuses a running server and parses only explicit offline options', async t => {
  const server = createServer(); server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  await assert.rejects(assertBaselineServerStopped(server.address().port), /Stop the Little Worlds server/);
  assert.deepEqual(parseBaselineArgs([]), {});
  assert.deepEqual(parseBaselineArgs(['--apply', '--port', '4320']), { apply: true, port: 4320 });
  for (const args of [['--apply', '--apply'], ['--reset'], ['--data-dir'], ['--port', '0'], ['--port', '65536'], ['--port', 'x']]) assert.throws(() => parseBaselineArgs(args));
});
