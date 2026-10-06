import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createSpaceDirectory, demoUsers } from '../server/identity.mjs';
import { beginDemoReset } from '../server/demo-reset.mjs';
import { verifyModule } from '../server/runtime.mjs';
import { upgradePainting, parsePaintingUpgradeArgs, assertPaintingServerStopped } from '../scripts/upgrade-painting.mjs';

const hash = value => createHash('sha256').update(value).digest('hex');
const revisionHash = revision => hash(`${revision.source}\n${revision.tests}`);
const json = async filename => JSON.parse(await readFile(filename, 'utf8'));
const writeJson = (filename, value) => writeFile(filename, JSON.stringify(value));
const pathFor = (dataDir, id) => id === 'mira' ? join(dataDir, 'space.json') : join(dataDir, 'spaces', id, 'space.json');
const noModel = { keyAvailable: false, respond() { assert.fail('An installer fixture must never call a model'); } };
const source = version => `export const meta = { title: 'Shared canvas ${version}', subtitle: 'Paint together', accent: '#04b84c', layout: 'canvas' };
export function render() { return '<main><h1>Shared canvas ${version}</h1><p>Paint together</p></main>'; }
export function reduce() { throw Error('Unknown action'); }
`;
const tests = `export function runTests(api) {
  const before=JSON.stringify(api.initialState), html=api.render(api.initialState,{id:'test-painter',name:'Painter'});
  let refused=false;try { api.reduce(api.initialState,{type:'unknown'},{id:'test-painter',name:'Painter'}); } catch { refused=true; }
  return [{name:'Canvas title renders',ok:html.includes('Shared canvas')},{name:'Painting instruction renders',ok:html.includes('Paint together')},
    {name:'Unknown actions refused',ok:refused},{name:'Rendering preserves state',ok:before===JSON.stringify(api.initialState)}];
}
`;
const proposal = { source: source('new'), tests, summary: 'Upgrade the shared painting canvas while preserving all artwork' };

async function fixture(t, { initialBaseline = false } = {}) {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-painting-upgrade-'));
  t.after(() => rm(parent, { recursive: true, force: true }));
  const dataDir = join(parent, 'data');
  const directory = await createSpaceDirectory({ dataDir, adapter: noModel });
  const spaces = {};
  for (const person of demoUsers) spaces[person.id] = (await directory.serviceFor(person.id)).store.read();
  await directory.close();
  const originalState = { projects: [], contributions: [], extras: { canvas: { iris: { actorId: 'iris', color: 1, marks: { 0: [1, 1] } } } } };
  const checked = await verifyModule(source('old'), tests, originalState);
  assert.equal(checked.ok, true);
  const old = { ...spaces.iris.revisions[0], source: source('old'), tests, meta: checked.meta, checks: checked.checks };
  spaces.iris = { ...spaces.iris, state: originalState, revisions: [old], icon: { status: 'ready', source: 'upload', data: 'dGVzdA==', mimeType: 'image/webp', version: 'preserve-icon' } };
  const live = structuredClone(spaces.iris);
  live.state.extras.canvas.visitor = { actorId: 'visitor', color: 2, marks: { 52: [2, 2] } };
  live.state.extras.unrelated = { visitor: { actorId: 'visitor', text: 'Keep this note' } };
  if (initialBaseline) live.initialBaseline = { revision: old, state: originalState, icon: spaces.iris.icon };
  const storeFile = pathFor(dataDir, 'iris');
  await writeJson(storeFile, live);
  const historyDir = `${dataDir}-reset-history`;
  await mkdir(historyDir);
  const baselineFile = join(historyDir, 'baseline.json');
  const baseline = { version: 1, createdAt: 'original-date', users: demoUsers, spaces,
    prepared: { iris: { revisionId: 1, sourceHash: revisionHash(old), turnId: 'old-turn', sessionId: live.session.id }, mira: { unchanged: true } } };
  await writeJson(baselineFile, baseline);
  const markerFile = join(dataDir, 'painting-upgrade.json');
  return { dataDir, storeFile, historyDir, baselineFile, markerFile, live, baseline,
    run: options => upgradePainting({ dataDir, proposalFactory: async () => proposal, allowedSourceHashes: [hash(source('old'))],
      probeServer: async () => {}, log() {}, ...options }) };
}

test('painting dry run performs real verification and changes no files or live/baseline state', async t => {
  const f = await fixture(t);
  const files = [f.storeFile, f.baselineFile, join(f.dataDir, 'identities.json'), join(f.dataDir, 'community.json')];
  const before = await Promise.all(files.map(file => readFile(file, 'utf8')));
  let seen = [];
  const result = await f.run({ updateBaseline: true, probeServer() { assert.fail('Dry run must not require shutting down the app'); },
    verify: async (source, tests, state, options) => { seen.push(structuredClone(state)); return verifyModule(source, tests, state, options); } });
  assert.deepEqual(result, { applied: false, publication: true, baseline: true });
  assert.equal(seen.length, 2);
  assert.deepEqual(seen[0], f.live.state);
  assert.deepEqual(seen[1], f.baseline.spaces.iris.state);
  assert.equal(seen[1].extras.canvas.visitor, undefined, 'Original reset state is verified, not live visitor artwork');
  assert.deepEqual(await Promise.all(files.map(file => readFile(file, 'utf8'))), before);
  assert.deepEqual(await readdir(f.historyDir), ['baseline.json']);
  await assert.rejects(readFile(f.markerFile), { code: 'ENOENT' });
});

test('explicit painting install publishes through owner verification, backs up the original and keeps all participation', async t => {
  const f = await fixture(t);
  const before = await readFile(f.storeFile, 'utf8');
  const otherFiles = [f.baselineFile, join(f.dataDir, 'identities.json'), join(f.dataDir, 'community.json'),
    ...demoUsers.filter(person => person.id !== 'iris').map(person => pathFor(f.dataDir, person.id))];
  const othersBefore = await Promise.all(otherFiles.map(file => readFile(file, 'utf8')));
  let probes = 0;
  const result = await f.run({ apply: true, probeServer: async () => { probes++; } });
  assert.equal(probes, 2);
  assert.equal(result.applied, true);
  assert.equal(result.baseline, false);
  assert.equal(result.revisionId, 2);
  const after = await json(f.storeFile);
  assert.deepEqual(after.state, f.live.state);
  assert.deepEqual(after.icon, f.live.icon);
  assert.deepEqual(after.revisions[0], f.live.revisions[0]);
  assert.equal(after.revisions[1].source, proposal.source);
  assert.ok(after.revisions[1].checks.length >= 4);
  assert.ok(after.revisions[1].checks.every(check => check.ok));
  assert.equal(after.session.lastOutcome, 'completed');
  assert.ok(after.events.some(event => event.type === 'revision.published'));
  assert.ok(after.events.some(event => event.type === 'tool.completed' && event.data?.tool === 'verify_workspace'));
  assert.deepEqual(await Promise.all(otherFiles.map(file => readFile(file, 'utf8'))), othersBefore);
  const manifest = await json(join(result.backupDirectory, 'manifest.json'));
  const storeBackup = manifest.files.find(file => file.filename === f.storeFile);
  assert.equal(await readFile(join(result.backupDirectory, storeBackup.backup), 'utf8'), before);
  assert.equal(storeBackup.sha256, hash(before));
  assert.equal((await json(f.markerFile)).revisionId, 2);
  await assert.rejects(readFile(join(f.dataDir, '.upgrade-painting.lock')), { code: 'ENOENT' });
  const installed = await readFile(f.storeFile, 'utf8');
  assert.deepEqual(await f.run({ apply: true }), { applied: false, publication: false, baseline: false });
  assert.equal(await readFile(f.storeFile, 'utf8'), installed);
});

test('opt-in baseline update preserves its original artwork and metadata and is used by a later reset', async t => {
  const f = await fixture(t, { initialBaseline: true });
  const baselineBefore = await readFile(f.baselineFile, 'utf8');
  const result = await f.run({ apply: true, updateBaseline: true });
  const saved = await json(f.storeFile), baseline = await json(f.baselineFile);
  assert.deepEqual(saved.state, f.live.state);
  assert.deepEqual(saved.initialBaseline.state, f.live.initialBaseline.state);
  assert.equal(saved.initialBaseline.revision.source, proposal.source);
  assert.deepEqual(baseline.spaces.iris.state, f.baseline.spaces.iris.state);
  assert.equal(baseline.spaces.iris.currentRevisionId, 1);
  assert.equal(baseline.spaces.iris.revisions[0].source, proposal.source);
  assert.equal(baseline.spaces.iris.revisions[0].createdAt, f.baseline.spaces.iris.revisions[0].createdAt);
  assert.deepEqual(baseline.spaces.iris.session, f.baseline.spaces.iris.session);
  assert.deepEqual(baseline.spaces.iris.events, f.baseline.spaces.iris.events);
  assert.deepEqual(baseline.spaces.iris.icon, f.baseline.spaces.iris.icon);
  assert.equal(baseline.createdAt, 'original-date');
  for (const person of demoUsers.filter(person => person.id !== 'iris')) assert.deepEqual(baseline.spaces[person.id], f.baseline.spaces[person.id]);
  assert.equal(baseline.prepared.iris.sourceHash, revisionHash(baseline.spaces.iris.revisions[0]));
  assert.equal(baseline.prepared.iris.turnId, 'old-turn');
  assert.deepEqual(baseline.prepared.mira, f.baseline.prepared.mira);
  const manifest = await json(join(result.backupDirectory, 'manifest.json'));
  assert.equal(await readFile(join(result.backupDirectory, manifest.files.find(file => file.filename === f.baselineFile).backup), 'utf8'), baselineBefore);
  assert.deepEqual(await f.run({ apply: true, updateBaseline: true }), { applied: false, publication: false, baseline: false });
  const reset = await beginDemoReset(f.dataDir);
  await reset.commit();
  const resetWorld = await json(f.storeFile);
  assert.equal(resetWorld.revisions.find(revision => revision.id === resetWorld.currentRevisionId).source, proposal.source);
  assert.deepEqual(resetWorld.state, f.baseline.spaces.iris.state);
  assert.equal(resetWorld.state.extras.canvas.visitor, undefined);
});

test('unknown owner edits and changed original baselines are refused before mutation', async t => {
  const f = await fixture(t);
  for (const target of ['live', 'baseline']) {
    const filename = target === 'live' ? f.storeFile : f.baselineFile;
    const original = await readFile(filename, 'utf8');
    const data = JSON.parse(original);
    (target === 'live' ? data : data.spaces.iris).revisions[0].source += '// Later authored content\n';
    await writeJson(filename, data);
    const changed = await readFile(filename, 'utf8');
    await assert.rejects(f.run({ apply: true, updateBaseline: true }), /later or unrecognized owner edits/);
    assert.equal(await readFile(filename, 'utf8'), changed);
    await writeFile(filename, original);
  }
  assert.deepEqual(await readdir(f.historyDir), ['baseline.json']);
  await assert.rejects(readFile(f.markerFile), { code: 'ENOENT' });
});

test('a failed proposal or candidate-state change cannot publish or change the baseline', async t => {
  const f = await fixture(t);
  const before = await readFile(f.storeFile, 'utf8'), baseline = await readFile(f.baselineFile, 'utf8');
  await assert.rejects(f.run({ apply: true, updateBaseline: true, proposalFactory: async () => ({ ...proposal, source: 'invalid javascript' }) }), /failed painting verification/);
  await assert.rejects(f.run({ apply: true, verify: async () => ({ ok: true, checks: [], candidateState: { ...f.live.state, extras: {} } }) }), /would change saved participation/);
  await assert.rejects(f.run({ apply: true, verify: async (source, tests, state) => state.extras.canvas.visitor
    ? verifyModule(source, tests, state) : { ok: false, checks: [] }, updateBaseline: true }), /ORIGINAL reset baseline.*failed painting verification/);
  assert.equal(await readFile(f.storeFile, 'utf8'), before);
  assert.equal(await readFile(f.baselineFile, 'utf8'), baseline);
  assert.deepEqual(await readdir(f.historyDir), ['baseline.json']);
});

test('the normal owner builder independently rejects invalid code and retains the original backup', async t => {
  const f = await fixture(t);
  const before = await readFile(f.storeFile, 'utf8');
  const baselineBefore = await readFile(f.baselineFile, 'utf8');
  // Passing preflight in this fixture must not bypass the ordinary publication
  // boundary, whose actual sandbox verification still rejects invalid source.
  await assert.rejects(f.run({ apply: true, updateBaseline: true,
    proposalFactory: async () => ({ ...proposal, source: 'invalid javascript' }),
    verify: async (_source, _tests, state) => ({ ok: true, checks: [{ name: 'Fixture preflight', ok: true }], meta: {}, candidateState: state }),
  }), /did not publish successfully/);
  const saved = await json(f.storeFile);
  assert.equal(saved.currentRevisionId, f.live.currentRevisionId);
  assert.deepEqual(saved.revisions, f.live.revisions);
  assert.deepEqual(saved.state, f.live.state);
  assert.equal(saved.session.lastOutcome, 'failed');
  assert.equal(await readFile(f.baselineFile, 'utf8'), baselineBefore);
  await assert.rejects(readFile(f.markerFile), { code: 'ENOENT' });
  const backups = join(f.historyDir, 'painting-upgrade-backups');
  const [backupId] = await readdir(backups);
  const manifest = await json(join(backups, backupId, 'manifest.json'));
  const original = manifest.files.find(file => file.filename === f.storeFile);
  assert.equal(await readFile(join(backups, backupId, original.backup), 'utf8'), before);
  await assert.rejects(readFile(join(f.dataDir, '.upgrade-painting.lock')), { code: 'ENOENT' });
});

test('an original initial baseline can be updated without inventing a reset baseline or capturing visitor artwork', async t => {
  const f = await fixture(t, { initialBaseline: true });
  await rm(f.baselineFile);
  await f.run({ apply: true, updateBaseline: true });
  const saved = await json(f.storeFile);
  assert.deepEqual(saved.state, f.live.state);
  assert.deepEqual(saved.initialBaseline.state, f.live.initialBaseline.state);
  assert.equal(saved.initialBaseline.revision.source, proposal.source);
  await assert.rejects(readFile(f.baselineFile), { code: 'ENOENT' });
});

test('the bundled painting proposal publishes against legacy layers without rewriting a single record', async t => {
  const f = await fixture(t);
  const { paintingProposal } = await import('../server/painting/index.mjs');
  const bundled = await paintingProposal();
  const result = await f.run({ apply: true, updateBaseline: true, proposalFactory: undefined });
  assert.equal(result.applied, true);
  const saved = await json(f.storeFile);
  assert.equal(saved.revisions.at(-1).source, bundled.source);
  assert.deepEqual(saved.state, f.live.state);
  assert.deepEqual((await json(f.baselineFile)).spaces.iris.state, f.baseline.spaces.iris.state);
});

test('running edits, active services, missing baselines, and operation locks are refused', async t => {
  const f = await fixture(t);
  const before = await readFile(f.storeFile, 'utf8');
  await assert.rejects(f.run({ apply: true, probeServer: async () => { throw Error('Stop the server'); } }), /Stop the server/);
  await writeJson(f.storeFile, { ...f.live, session: { ...f.live.session, status: 'running' } });
  await assert.rejects(f.run({ apply: true }), /unfinished edit/);
  await writeFile(f.storeFile, before);
  for (const lock of [join(f.dataDir, '.upgrade-painting.lock'), join(f.dataDir, 'demo-preparation.json.lock'), join(f.historyDir, 'transaction.json')]) {
    await writeFile(lock, '{}');
    await assert.rejects(f.run({ apply: true }), /locked|lock is present/);
    await rm(lock);
  }
  await rm(f.baselineFile);
  await assert.rejects(f.run({ apply: true, updateBaseline: true }), /No original Iris reset or initial baseline/);
  assert.equal(await readFile(f.storeFile, 'utf8'), before);
});

test('concurrent changes during preflight are preserved and block installation', async t => {
  const f = await fixture(t);
  const before = await readFile(f.storeFile, 'utf8');
  let changed = false;
  await assert.rejects(f.run({ apply: true, verify: async (source, tests, state, options) => {
    if (!changed) { changed = true; await writeJson(f.markerFile, { version: 1, changedConcurrently: true }); }
    return verifyModule(source, tests, state, options);
  } }), /Saved data changed/);
  assert.equal(await readFile(f.storeFile, 'utf8'), before);
  assert.equal((await json(f.markerFile)).changedConcurrently, true);
});

test('the CLI exposes only explicit offline options and detects a listening API', async t => {
  assert.deepEqual(parsePaintingUpgradeArgs([]), {});
  assert.deepEqual(parsePaintingUpgradeArgs(['--apply', '--update-baseline', '--port', '4320', '--data-dir', '/tmp/painting-test']),
    { apply: true, updateBaseline: true, port: 4320, dataDir: resolve('/tmp/painting-test') });
  for (const args of [['--apply', '--apply'], ['--force'], ['--data-dir'], ['--allowed-source-hash', 'abc'], ['--port', '0'], ['--port', '65536'], ['--port', 'x']]) {
    assert.throws(() => parsePaintingUpgradeArgs(args));
  }
  const server = createServer(); server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const port = server.address().port;
  t.after(() => { if (server.listening) server.close(); });
  await assert.rejects(assertPaintingServerStopped(port), /Stop the Little Worlds server/);
  await new Promise(resolve => server.close(resolve));
  await assertPaintingServerStopped(port);
  assert.throws(() => assertPaintingServerStopped(0), /valid local API port/);
});
