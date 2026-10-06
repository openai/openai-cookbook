import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import sharp from 'sharp';
import { createSpaceDirectory, demoUsers } from '../server/identity.mjs';
import { normalizeSpaceIcon } from '../server/space-icon-image.mjs';
import { prepareArcade, parseArcadeArgs, assertServerStopped } from '../scripts/prepare-arcade.mjs';

const gameIds = ['pacman', 'space-invaders', 'snake', 'tetris'];
const controls = gameIds.map(id => `<section data-game="${id}" tabindex="0"><canvas data-game-canvas></canvas><button data-game-command="start">Start ${id}</button><button data-game-action='{"type":"right"}'>Right ${id}</button><span data-game-runtime-status></span><span data-game-value="score">0</span></section>`).join('');
const proposal = {
  source: `
    export const meta={title:'Test arcade',subtitle:'Four games',accent:'#7843ba',layout:'canvas',games:${JSON.stringify(gameIds.map((id, index) => ({ id, exportName: `game${index}`, tickMs: 50 })))} };
    ${gameIds.map((_, index) => `export const game${index}={
      init(saved,actor){return {actorId:actor.id,x:1,score:0};},
      step(state,action){if(action.type==='tick'||action.type==='right'){state.x=(state.x+1)%20;state.score++;}return state;},
      view(state){return {width:100,height:100,background:'#111',objects:[{id:'player',type:'rect',x:state.x,y:10,width:5,height:5,fill:'#fff'}],values:{score:state.score}};}
    };`).join('\n')}
    export function render(){return ${JSON.stringify(`<main><h1>Test arcade</h1>${controls}</main>`)};}
    export function reduce(){throw Error('Unknown action');}
  `,
  tests: `export function runTests(api){
    const actor={id:'arcade-check',name:'Test'};let blocked=false;
    try{api.reduce(api.initialState,{type:'unknown'},actor)}catch{blocked=true}
    const first=api.games.pacman.init(null,actor);
    const next=api.games.pacman.step(first,{type:'tick',deltaMs:50},actor);
    return [{name:'Four games are playable',ok:Object.keys(api.games).length===4},
      {name:'The game advances',ok:next.score===1},
      {name:'Unknown actions are rejected',ok:blocked},
      {name:'All games render',ok:api.render(api.initialState,actor).includes('space-invaders')}];
  }`,
  summary: 'Prepare four playable test arcade games',
};
const noModel = { keyAvailable: false, respond() { assert.fail('Preparing fixtures never calls a model.'); } };
const readJson = async filename => JSON.parse(await readFile(filename, 'utf8'));
const pathFor = (dataDir, id) => id === 'mira' ? join(dataDir, 'space.json') : join(dataDir, 'spaces', id, 'space.json');

async function fixture(t) {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-curated-arcade-'));
  const dataDir = join(parent, 'data');
  const directory = await createSpaceDirectory({ dataDir, adapter: noModel });
  const added = await directory.signIn({ name: 'Existing person' });
  for (const person of directory.people()) {
    const service = await directory.serviceFor(person.ownSpaceId);
    await service.store.transact(data => {
      data.state.extras.notes = { [person.id]: { actorId: person.id, text: 'Keep this contribution' } };
    });
  }
  await directory.requestFriend(added.user.id, 'james');
  const spaces = Object.fromEntries(await Promise.all(demoUsers.slice(0, 7).map(async person => [person.id, (await directory.serviceFor(person.id)).store.read()])));
  await directory.close();
  const markerFile = join(dataDir, 'demo-preparation.json');
  await writeFile(markerFile, JSON.stringify({ version: 1, prepared: { mira: { keep: 'Existing preparation marker' } } }));
  const historyDir = `${dataDir}-reset-history`;
  await mkdir(historyDir);
  const baselineFile = join(historyDir, 'baseline.json');
  await writeFile(baselineFile, JSON.stringify({ version: 1, createdAt: 'original-date', users: demoUsers.slice(0, 7), spaces, prepared: { mira: { keep: 'Baseline marker' } } }));
  const iconFile = join(parent, 'finance.webp');
  await sharp({ create: { width: 32, height: 32, channels: 3, background: '#102435' } }).webp().toFile(iconFile);
  t.after(() => rm(parent, { recursive: true, force: true }));
  return { parent, dataDir, markerFile, baselineFile, iconFile, added,
    run: options => prepareArcade({ dataDir, iconFile, proposalFactory: async () => proposal, probeServer: async () => {}, log() {}, ...options }) };
}

test('offline preparation publishes only the blank arcade, updates the portrait and narrowly backs up its reset baseline', async t => {
  const state = await fixture(t);
  const before = new Map(await Promise.all([...demoUsers.map(person => person.id), state.added.ownSpaceId].map(async id => [id, await readFile(pathFor(state.dataDir, id), 'utf8')])));
  const graph = await readFile(join(state.dataDir, 'community.json'), 'utf8');
  const identities = await readFile(join(state.dataDir, 'identities.json'), 'utf8');
  const baselineBefore = await readFile(state.baselineFile, 'utf8');
  const result = await state.run();
  assert.equal(result.arcade, 'prepared');
  assert.equal(result.jamesPortrait, 'updated');
  const karen = await readJson(pathFor(state.dataDir, 'karen'));
  assert.equal(karen.currentRevisionId, 2);
  assert.deepEqual(karen.revisions.at(-1).meta.games.map(game => game.id), gameIds);
  assert.deepEqual(karen.state, JSON.parse(before.get('karen')).state);
  const james = await readJson(pathFor(state.dataDir, 'james'));
  const originalJames = JSON.parse(before.get('james'));
  assert.deepEqual(james.state, originalJames.state);
  assert.deepEqual(james.revisions, originalJames.revisions);
  assert.deepEqual(james.session, originalJames.session);
  const expected = await normalizeSpaceIcon(await readFile(state.iconFile));
  assert.equal(james.icon.data, expected.data);
  assert.equal(james.icon.source, 'upload');
  for (const [id, old] of before) if (!['james', 'karen'].includes(id)) assert.equal(await readFile(pathFor(state.dataDir, id), 'utf8'), old, id);
  assert.equal(await readFile(join(state.dataDir, 'community.json'), 'utf8'), graph);
  assert.equal(await readFile(join(state.dataDir, 'identities.json'), 'utf8'), identities);
  const marker = await readJson(state.markerFile);
  assert.deepEqual(marker.prepared.mira, { keep: 'Existing preparation marker' });
  assert.equal(marker.prepared.karen.revisionId, 2);
  assert.equal(marker.prepared.karen.sessionId, karen.session.id);
  const baseline = await readJson(state.baselineFile);
  const originalBaseline = JSON.parse(baselineBefore);
  originalBaseline.spaces.james.icon = james.icon;
  assert.deepEqual(baseline, originalBaseline, 'No baseline canvas, history, person or marker is recaptured.');
  assert.equal(await readFile(result.baselineBackup, 'utf8'), baselineBefore);
  await assert.rejects(readFile(join(state.dataDir, '.prepare-arcade.lock')), { code: 'ENOENT' });
});

test('repeated preparation is idempotent and preserves later authored changes', async t => {
  const state = await fixture(t);
  await state.run();
  const files = [pathFor(state.dataDir, 'karen'), pathFor(state.dataDir, 'james'), state.markerFile, state.baselineFile];
  const before = await Promise.all(files.map(file => readFile(file, 'utf8')));
  assert.deepEqual(await state.run(), { arcade: 'preserved', jamesPortrait: 'unchanged' });
  assert.deepEqual(await Promise.all(files.map(file => readFile(file, 'utf8'))), before);
  const directory = await createSpaceDirectory({ dataDir: state.dataDir, adapter: noModel });
  const karen = await directory.serviceFor('karen');
  await karen.store.transact(data => {
    data.revisions.push({ ...data.revisions.at(-1), id: 3, source: proposal.source.replaceAll('Test arcade', 'My later arcade edit') });
    data.currentRevisionId = 3;
  });
  await directory.close();
  const later = await readFile(pathFor(state.dataDir, 'karen'), 'utf8');
  assert.deepEqual(await state.run(), { arcade: 'preserved', jamesPortrait: 'unchanged' });
  assert.equal(await readFile(pathFor(state.dataDir, 'karen'), 'utf8'), later);
  assert.equal((await readJson(state.markerFile)).prepared.karen.revisionId, 2);
  const ledger = await readJson(state.markerFile);
  delete ledger.prepared.karen;
  await writeFile(state.markerFile, JSON.stringify(ledger));
  assert.deepEqual(await state.run(), { arcade: 'preserved', jamesPortrait: 'unchanged' });
  assert.equal(await readFile(pathFor(state.dataDir, 'karen'), 'utf8'), later, 'Recovering a missing preparation marker never republishes over a later edit.');
  assert.equal((await readJson(state.markerFile)).prepared.karen.revisionId, 2);
  assert.equal((await readdir(`${state.dataDir}-reset-history`)).filter(file => file.startsWith('baseline-before-arcade-')).length, 1);
});

test('a failed arcade proposal preserves the current canvas, portrait, markers and reset baseline', async t => {
  const state = await fixture(t);
  const before = await readJson(pathFor(state.dataDir, 'karen'));
  const files = [pathFor(state.dataDir, 'james'), state.markerFile, state.baselineFile];
  const unrelated = await Promise.all(files.map(file => readFile(file, 'utf8')));
  await assert.rejects(state.run({ proposalFactory: async () => ({ ...proposal, source: 'not valid javascript' }) }), /did not pass verification/);
  const after = await readJson(pathFor(state.dataDir, 'karen'));
  assert.equal(after.currentRevisionId, before.currentRevisionId);
  assert.deepEqual(after.revisions, before.revisions);
  assert.deepEqual(after.state, before.state);
  assert.equal(after.session.lastOutcome, 'failed');
  assert.deepEqual(await Promise.all(files.map(file => readFile(file, 'utf8'))), unrelated);
  assert.equal((await readdir(`${state.dataDir}-reset-history`)).length, 1);
  await assert.rejects(readFile(join(state.dataDir, '.prepare-arcade.lock')), { code: 'ENOENT' });
});

test('an active server, unfinished target edit, or invalid baseline is refused before any preparation writes', async t => {
  const state = await fixture(t);
  const files = [pathFor(state.dataDir, 'karen'), pathFor(state.dataDir, 'james'), state.markerFile, state.baselineFile];
  const before = await Promise.all(files.map(file => readFile(file, 'utf8')));
  await assert.rejects(state.run({ probeServer: async () => { throw Error('Stop the Little Worlds server'); } }), /Stop the Little Worlds server/);
  assert.deepEqual(await Promise.all(files.map(file => readFile(file, 'utf8'))), before);
  const karen = JSON.parse(before[0]); karen.session.status = 'running';
  await writeFile(files[0], JSON.stringify(karen));
  await assert.rejects(state.run(), /unfinished edit/);
  assert.equal((await readJson(files[0])).session.status, 'running');
  await writeFile(files[0], before[0]);
  await writeFile(state.baselineFile, JSON.stringify({ version: 1, users: [], spaces: {} }));
  await assert.rejects(state.run(), /baseline is unsupported/);
  assert.equal(await readFile(files[0], 'utf8'), before[0]);
  await assert.rejects(readFile(join(state.dataDir, '.prepare-arcade.lock')), { code: 'ENOENT' });
});

test('the CLI validates its directory and checks that the local API port is closed', async t => {
  assert.deepEqual(parseArcadeArgs([]), {});
  assert.deepEqual(parseArcadeArgs(['--data-dir', '/tmp/arcade-only']), { dataDir: resolve('/tmp/arcade-only') });
  for (const args of [['--data-dir'], ['--rebuild'], ['--data-dir', '--rebuild'], ['--data-dir', 'one', '--data-dir', 'two']]) assert.throws(() => parseArcadeArgs(args), /Usage:/);
  const server = createServer();
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const port = server.address().port;
  t.after(() => { if (server.listening) server.close(); });
  await assert.rejects(assertServerStopped(port), /Stop the Little Worlds server/);
  await new Promise(resolveClose => server.close(resolveClose));
  await assertServerStopped(port);
  assert.throws(() => assertServerStopped(0), /valid local API port/);
});
