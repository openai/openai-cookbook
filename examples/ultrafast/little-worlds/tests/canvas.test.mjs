import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { compileModule, reduceModule, verifyModule, projectStateForPublication } from '../server/runtime.mjs';
import { renderDraftSource } from '../server/draft-preview.mjs';
import { createSpaceService, instructionsForSpace } from '../server/harness.mjs';
import { initialState, actors, seedSource, seedTests } from '../server/seed.mjs';
import { devDayDesignInstructions } from '../server/devday-theme.mjs';

const fourth = { id: 'glasshouse', title: 'Glasshouse', description: 'A place for tender things.', color: '#76916a' };
const botanical = { ...initialState.projects[0], title: 'A living herbarium', description: 'Leaves, light and patient observation.' };
const catalog = [botanical, ...initialState.projects.slice(1), fourth];
const source = (projects = catalog, canvas = true) => `export const meta={title:'A living garden',subtitle:'Watch good things grow.',accent:'#76916a',budget:3${canvas ? ",layout:'canvas',projects:" + JSON.stringify(projects) : ''}};
export function render(state,actor){return '<main>'+state.projects.map(p=>'<article>'+p.title+'</article>').join('')+'<p>'+state.contributions.length+' contributions</p></main>'}
export function reduce(state,action,actor){
 if(action.type!=='support'||!state.projects.some(p=>p.id===action.projectId))throw Error('Unknown action');
 if(state.contributions.filter(c=>c.actorId===actor.id).reduce((s,c)=>s+c.points,0)>=meta.budget)throw Error('All points spent');
 const found=state.contributions.find(c=>c.actorId===actor.id&&c.projectId===action.projectId);
 if(found)found.points++;else state.contributions.push({id:actor.id+':'+action.projectId,actorId:actor.id,projectId:action.projectId,points:1});
 return state;
}`;
const behavior = `export function runTests(api){
 const actor={id:'canvas-test',name:'Garden guest'};
 const last=api.initialState.projects[api.initialState.projects.length-1];
 const next=api.reduce(api.initialState,{type:'support',projectId:last.id},actor);
 let blocked=false;try{api.reduce(api.initialState,{type:'support',projectId:'missing'},actor)}catch{blocked=true}
 return [
 {name:'Current catalog is visible',ok:api.initialState.projects.every(p=>api.render(api.initialState,actor).includes(p.title))},
 {name:'Newest tile can be supported',ok:next.contributions.some(c=>c.actorId===actor.id&&c.projectId===last.id)},
 {name:'Invalid projects are refused',ok:blocked},
 {name:'Saved contributions survive',ok:api.initialState.contributions.every(c=>next.contributions.some(n=>JSON.stringify(n)===JSON.stringify(c)))}
 ];
}`;
const call = (name, args, id = name) => ({ type: 'function_call', name, arguments: JSON.stringify(args), call_id: id });
const apply = (moduleSource = source(), id = 'apply') => ({ output: [call('apply_change', { source: moduleSource, tests: behavior, summary: 'A growing garden' }, id)] });
const fake = respond => ({ keyAvailable: true, model: 'test-model', tier: 'ultrafast', respond });
const gate = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { resolve, promise }; };
async function setup(t, respond) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-canvas-'));
  const service = await createSpaceService({ dataDir, adapter: fake(respond), seedOverride: { state: structuredClone(initialState), source: seedSource, tests: seedTests } });
  t.after(async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  return { service, dataDir };
}

test('owner catalog projection updates and adds tiles without deleting data or omitted projects', () => {
  const state = structuredClone(initialState);
  state.projects[0].legacyTag = 'preserve this too';
  state.contributions.push({ id: 'leo-pick', actorId: 'leo', projectId: 'smallhours', points: 1 });
  state.extras.notes = { leo: { actorId: 'leo', text: 'Still here' } };
  const before = structuredClone(state);
  const next = projectStateForPublication({ title: 'Garden', subtitle: '', accent: '#76916a', layout: 'canvas', projects: [botanical, fourth] }, state);
  assert.equal(next.projects.length, 4);
  assert.equal(next.projects[0].title, botanical.title);
  assert.equal(next.projects[0].legacyTag, 'preserve this too');
  assert.ok(next.projects.some(p => p.id === 'smallhours'));
  assert.deepEqual(next.contributions, before.contributions);
  assert.deepEqual(next.extras, before.extras);
  assert.deepEqual(state, before, 'projection never mutates its live input');
});

test('preview and behavioral verification receive the same projected fourth tile', async () => {
  const before = structuredClone(initialState);
  const preview = await renderDraftSource(source(), initialState, actors.mira);
  assert.equal(preview.layout, 'canvas');
  assert.match(preview.html, /Glasshouse/);
  const result = await verifyModule(source(), behavior, initialState, { projectCatalog: true });
  assert.equal(result.ok, true, JSON.stringify(result.checks));
  assert.equal(result.candidateState.projects.length, 4);
  assert.deepEqual(initialState, before);
});

test('catalog metadata cannot grant visitor reducers authority to alter any project', async () => {
  for (const mutation of ["state.projects[0].title='Hijacked';", 'state.projects.push(meta.projects[3]);']) {
    const evil = source().slice(0, source().indexOf('export function reduce')) + `export function reduce(state){${mutation}return state}`;
    const { bundle } = await compileModule(evil);
    await assert.rejects(reduceModule(bundle, initialState, { type: 'support' }, actors.leo), /projects must be preserved/);
  }
});

test('invalid catalog declarations and non-canvas catalogs fail before preview or publication', async () => {
  const bad = [
    source([fourth, fourth]),
    source([{ ...fourth, id: '../escape' }]),
    source([{ ...fourth, color: 'url(secret)' }]),
    source([{ ...fourth, actorId: 'leo' }]),
    source().replace("layout:'canvas',", ''),
  ];
  for (const moduleSource of bad) {
    assert.equal((await verifyModule(moduleSource, behavior, initialState, { projectCatalog: true })).ok, false);
    assert.equal(await renderDraftSource(moduleSource, initialState, actors.mira), null);
  }
});

test('fourth tile publishes atomically and incorporates participation arriving after verification', async t => {
  const verified = gate(); const publishNow = gate(); let calls = 0;
  const { service } = await setup(t, async () => {
    calls++;
    if (calls === 1) return apply(source(initialState.projects, false), 'legacy-vote');
    if (calls === 2) return { output: [
      call('write_file', { path: 'space.js', content: source() }, 'write-source'),
      call('write_file', { path: 'tests.js', content: behavior }, 'write-tests'),
      call('verify_workspace', {}, 'verify-fourth'),
    ] };
    verified.resolve(); await publishNow.promise;
    return { output: [call('publish_revision', { summary: 'A fourth tile' }, 'publish-fourth')] };
  });
  await service.submit('Allow voting'); await service.waitForIdle();
  await service.store.transact(data => { data.state.extras.notes = { leo: { actorId: 'leo', text: 'Keep this note' } }; });
  await service.submit('Add a fourth tile'); await verified.promise;
  const during = await service.snapshot('leo');
  assert.equal(during.state.projects.length, 3, 'verification cannot change the published catalog');
  await service.action({ actor: 'leo', revisionId: during.revision.id, action: { type: 'support', projectId: 'smallhours' } });
  const newest = (await service.snapshot('leo')).state;
  publishNow.resolve(); await service.waitForIdle();
  const after = await service.snapshot('leo');
  assert.equal(after.revision.id, during.revision.id + 1);
  assert.equal(after.state.projects.length, 4);
  assert.match(after.html, /Glasshouse/);
  assert.deepEqual(after.state.contributions, newest.contributions);
  assert.deepEqual(after.state.extras, newest.extras);
  await service.action({ actor: 'leo', revisionId: after.revision.id, action: { type: 'support', projectId: 'glasshouse' } });
  assert.ok((await service.snapshot()).state.contributions.some(c => c.projectId === 'glasshouse'));
});

test('a failed catalog change retains the last live revision and all data', async t => {
  const { service } = await setup(t, async () => ({ output: [call('apply_change', { source: source(), tests: 'export function runTests(){return [{name:"Broken",ok:false}]}', summary: 'Broken fourth tile' })] }));
  const before = await service.snapshot();
  await service.submit('Add fourth tile'); await service.waitForIdle();
  const after = await service.snapshot();
  assert.equal(after.session.lastOutcome, 'failed');
  assert.deepEqual(after.state, before.state);
  assert.equal(after.revision.id, before.revision.id);
});

test('restoring an earlier canvas never deletes later tiles or their contributions', async t => {
  let calls = 0;
  const { service } = await setup(t, async () => apply(source(++calls === 1 ? initialState.projects : catalog), `canvas-${calls}`));
  await service.submit('Own the full canvas'); await service.waitForIdle();
  await service.submit('Add fourth tile'); await service.waitForIdle();
  await service.action({ actor: 'leo', revisionId: 3, action: { type: 'support', projectId: 'glasshouse' } });
  const before = await service.snapshot();
  await service.restore(2);
  const restored = await service.snapshot();
  assert.equal(restored.revision.id, 4);
  assert.equal(restored.state.projects.length, 4);
  assert.deepEqual(restored.state.contributions, before.state.contributions);
  assert.match(restored.html, /Glasshouse/);
});

test('a stored legacy page changes only through a normal builder turn, preserving its thread and records', async t => {
  const { service, dataDir } = await setup(t, async () => apply(source(initialState.projects, false)));
  await service.submit('Keep our shared picks'); await service.waitForIdle();
  await service.action({ actor: 'leo', revisionId: 2, action: { type: 'support', projectId: 'smallhours' } });
  await service.store.transact(data => { data.state.extras.notes = { leo: { actorId: 'leo', text: 'An old note' } }; });
  const before = service.store.read();
  await service.close();
  const seedOverride = { source: source(initialState.projects), tests: behavior, state: structuredClone(initialState), version: 'personas-v1' };
  const migrated = await createSpaceService({ dataDir, adapter: fake(async () => apply()), seedOverride });
  assert.deepEqual(migrated.store.read(), JSON.parse(JSON.stringify(before)), 'opening a workspace never silently replaces the owner’s page');
  await migrated.submit('Make the entire garden editable, including a fourth tile');
  await migrated.waitForIdle();
  const after = migrated.store.read();
  assert.equal(after.currentRevisionId, before.currentRevisionId + 1);
  assert.equal(after.revisions.at(-1).meta.layout, 'canvas');
  assert.deepEqual(after.revisions.slice(0, -1), before.revisions);
  assert.deepEqual(after.session.turns.slice(0, -1), before.session.turns);
  assert.equal(after.session.turns.at(-1).status, 'completed');
  assert.equal(after.session.turns.at(-1).revisionId, after.currentRevisionId);
  assert.deepEqual(after.state.contributions, before.state.contributions);
  assert.deepEqual(after.state.extras, before.state.extras);
  await migrated.restore(2);
  const restoredRevision = migrated.store.read().currentRevisionId;
  await migrated.close();
  const restarted = await createSpaceService({ dataDir, adapter: fake(async () => apply()), seedOverride });
  assert.equal(restarted.store.read().currentRevisionId, restoredRevision, 'a later restore is not overwritten on restart');
  await restarted.close();
});

test('builder instructions allow the entire canvas and explain the catalog ownership seam', () => {
  assert.equal(instructionsForSpace('studio'), instructionsForSpace('blank'));
  for (const kind of ['studio', 'blank']) {
    const instructions = instructionsForSpace(kind);
    assert.match(instructions, /ENTIRE (PERSONAL )?SPACE BODY/);
    assert.match(instructions, /meta\.projects/);
    assert.match(instructions, /Never write state\.projects in reduce/);
    assert.doesNotMatch(instructions, /sits DIRECTLY BELOW|three fixed|3 equal grid columns/);
  }
});

test('every ordinary builder turn carries the DevDay contract separately from owner content', async t => {
  const requests = [];
  const { service } = await setup(t, async request => {
    requests.push(request);
    return apply();
  });
  const firstRequest = 'Build a botanical garden with a yellow sunflower.';
  const secondRequest = 'Add a fourth tile and keep the existing votes.';
  await service.submit(firstRequest);
  await service.waitForIdle();
  const before = service.store.read().state;
  await service.submit(secondRequest);
  await service.waitForIdle();

  assert.equal(requests.length, 2);
  for (const request of requests) {
    assert.ok(request.instructions.includes(devDayDesignInstructions), 'Generation and later edits both receive the shared creative contract.');
    assert.match(request.instructions, /Never recolor stored artwork or reinterpret existing palette indexes/);
    assert.match(request.instructions, /retain every existing tile title and stable project ID/);
    assert.doesNotMatch(request.instructions, /Warm paper #f5f2e9|use Georgia for/);
  }
  assert.doesNotMatch(requests[0].instructions, /yellow sunflower/, 'Owner requests remain data in their own conversation messages.');
  assert.match(JSON.stringify(requests[0].input), /yellow sunflower/);
  assert.match(JSON.stringify(requests[1].input), /Add a fourth tile/);
  assert.equal(service.store.read().session.lastOutcome, 'completed');
  assert.deepEqual(service.store.read().state.contributions, before.contributions);
  assert.deepEqual(service.store.read().state.extras, before.extras);
});

test('only named platform capabilities can be published, with bounded editable suggestions', () => {
  const meta = { title: 'Open room', subtitle: '', accent: '#76916a', layout: 'canvas' };
  for (const capabilities of [['fetch'], ['health-chat', 'health-chat'], 'health-chat', [null]]) {
    assert.throws(() => projectStateForPublication({ ...meta, capabilities }, initialState), /capabilities/);
  }
  assert.doesNotThrow(() => projectStateForPublication({ ...meta, capabilities: ['health-chat', 'finance-news'], suggestions: [{ label: 'An idea', prompt: 'Add a useful feature' }] }, initialState));
  assert.throws(() => projectStateForPublication({ ...meta, suggestions: [{ label: 'x', prompt: '' }] }, initialState), /suggestions/);
});
