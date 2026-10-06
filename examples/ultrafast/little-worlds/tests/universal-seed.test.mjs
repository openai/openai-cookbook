import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createSpaceDirectory } from '../server/identity.mjs';
import { blankInitialState, blankSeedSource, blankSeedTests, seedFor } from '../server/seed.mjs';
import { communityBoardSource, communityBoardTests } from '../server/community-board.mjs';

const demoIds = ['mira', 'james', 'jake', 'erica', 'leo', 'iris', 'luca', 'karen', 'nora'];
const emptyState = { projects: [], contributions: [], extras: {} };
const noModel = {
  keyAvailable: false,
  respond() { assert.fail('Opening or resetting a space must not call a model.'); },
};

// Deliberately valid without layout metadata, as an older saved module might be.
// Opening a directory must not replace it with an identity-specific template.
const savedSource = `export const meta={title:'My own observatory',subtitle:'A saved personal canvas',accent:'#687957'};
export function render(state,actor){return '<main><h1>My own observatory</h1><p>'+Object.keys(state.extras.notes||{}).length+' saved notes</p></main>'}
export function reduce(state,action,actor){
  if(action.type!=='note'||typeof action.text!=='string'||!action.text.trim()||action.text.length>80)throw Error('Invalid note');
  state.extras.notes=state.extras.notes||{};
  state.extras.notes[actor.id]={actorId:actor.id,text:action.text.trim()};
  return state;
}`;
const savedTests = `export function runTests(api){
  const actor={id:'universal-seed-check',name:'A visitor'};
  const next=api.reduce(api.initialState,{type:'note',text:'Keep looking up'},actor);
  let blocked=false;try{api.reduce(api.initialState,{type:'unknown'},actor)}catch{blocked=true}
  return [
    {name:'The saved canvas renders',ok:api.render(api.initialState,actor).includes('My own observatory')},
    {name:'A visitor can keep a note',ok:next.extras.notes[actor.id].text==='Keep looking up'},
    {name:'Unknown actions are refused',ok:blocked},
    {name:'Other visitors keep their notes',ok:Object.entries(api.initialState.extras.notes||{}).every(([id,note])=>JSON.stringify(next.extras.notes[id])===JSON.stringify(note))}
  ];
}`;
function publishingAdapter() {
  let calls = 0;
  return {
    keyAvailable: true,
    model: 'test-model',
    tier: 'ultrafast',
    get calls() { return calls; },
    async respond() {
      return { metrics: { durationMs: 1 }, output: [{ type: 'function_call', call_id: `universal-seed-${++calls}`, name: 'apply_change',
        arguments: JSON.stringify({ source: savedSource, tests: savedTests, summary: 'My own observatory' }) }] };
    },
  };
}
async function fixture(t, adapter = noModel) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-universal-seed-'));
  let directory = await createSpaceDirectory({ dataDir, adapter });
  t.after(async () => { await directory.close(); await rm(dataDir, { recursive: true, force: true }); });
  return {
    dataDir,
    get directory() { return directory; },
    async reopen() {
      await directory.close();
      directory = await createSpaceDirectory({ dataDir, adapter });
      return directory;
    },
  };
}
const current = data => data.revisions.find(revision => revision.id === data.currentRevisionId);
const savedPath = (dataDir, spaceId) => spaceId === 'mira'
  ? join(dataDir, 'space.json') : join(dataDir, 'spaces', spaceId, 'space.json');

function assertEmpty(data, context) {
  assert.deepEqual(data.state, emptyState, context);
  assert.equal(data.currentRevisionId, 1, context);
  assert.equal(data.revisions.length, 1, context);
  assert.equal(current(data).source, blankSeedSource, context);
  assert.equal(current(data).tests, blankSeedTests, context);
  assert.deepEqual(data.session.items, [], context);
  assert.deepEqual(data.session.turns, [], context);
}

test('legacy studio and blank kinds use the same empty canvas seed', () => {
  assert.deepEqual(blankInitialState, emptyState);
  const expected = { state: emptyState, source: blankSeedSource, tests: blankSeedTests };
  assert.deepEqual(seedFor('studio'), expected);
  assert.deepEqual(seedFor('blank'), expected);
  assert.deepEqual(seedFor(), expected);
});

test('a persisted pre-DevDay blank remains unbuilt without replacing its source', async t => {
  // Literal historical source, independent of the current seed export. Its
  // unused accent is not a reason to generate an icon or declare a built page.
  const historicalBlank = `export const meta = {
  title: "A space for your next idea",
  subtitle: "",
  accent: "#687957"
};
export function render(state, actor) { return ''; }
export function reduce(state, action, actor) {
  throw new Error("Your space is ready for its first idea.");
}
`;
  const state = await fixture(t);
  const service = await state.directory.serviceFor('leo');
  await service.store.transact(data => { current(data).source = historicalBlank; });
  await state.reopen();
  const reopened = await state.directory.serviceFor('leo');
  assert.equal(current(reopened.store.read()).source, historicalBlank);
  assert.equal((await state.directory.metadata('leo')).hasBuilt, false);
  assert.equal((await reopened.snapshot()).html, '');
});

test('accounts begin with empty code and state except for the explicitly preloaded shared board', async t => {
  const { directory } = await fixture(t);
  assert.deepEqual(directory.people().map(person => person.id), demoIds);
  const newcomer = await directory.signIn({ name: 'Rowan' });
  const people = directory.people();
  assert.equal(people.at(-1).id, newcomer.user.id);
  const sessionIds = new Set();
  for (const person of people) {
    const service = await directory.serviceFor(person.ownSpaceId);
    const saved = service.store.read();
    if (person.id === 'nora') {
      assert.equal(current(saved).source, communityBoardSource);
      assert.equal(current(saved).tests, communityBoardTests);
      assert.deepEqual(saved.state, emptyState);
      assert.deepEqual(saved.session.turns, []);
      assert.ok((await service.snapshot(person.id)).html);
    } else {
      assertEmpty(saved, person.name);
      assert.equal((await service.snapshot(person.id)).html, '', person.name);
    }
    assert.equal(saved.ownerId, person.id);
    assert.equal((await directory.metadata(person.ownSpaceId)).hasBuilt, person.id === 'nora', person.name);
    sessionIds.add(saved.session.id);
  }
  assert.equal(sessionIds.size, people.length, 'Each identical blank canvas has its own persistent thread.');
});

test('opening the directory again never upgrades blank pages into persona templates', async t => {
  const state = await fixture(t);
  await state.directory.signIn({ name: 'Rowan' });
  const before = new Map();
  for (const person of state.directory.people()) {
    const saved = (await state.directory.serviceFor(person.ownSpaceId)).store.read();
    if (person.id !== 'nora') assertEmpty(saved, person.name);
    before.set(person.ownSpaceId, {
      saved, disk: await readFile(savedPath(state.dataDir, person.ownSpaceId), 'utf8'),
    });
  }
  for (let restart = 0; restart < 2; restart++) {
    const directory = await state.reopen();
    const community = await directory.community('mira');
    assert.ok(community.spaces.every(space => space.hasBuilt === (space.id === 'nora')));
    for (const [spaceId, original] of before) {
      assert.deepEqual((await directory.serviceFor(spaceId)).store.read(), original.saved, spaceId);
      assert.equal(await readFile(savedPath(state.dataDir, spaceId), 'utf8'), original.disk, spaceId);
    }
  }
});

test('saved Mira, another default persona and a new account retain their code, data and full thread on reopen', async t => {
  const adapter = publishingAdapter();
  const state = await fixture(t, adapter);
  const newcomer = await state.directory.signIn({ name: 'Rowan' });
  const before = new Map();
  for (const spaceId of ['mira', 'erica', newcomer.ownSpaceId]) {
    const service = await state.directory.serviceFor(spaceId);
    await service.submit('Build my own observatory');
    await service.waitForIdle();
    assert.equal(service.store.read().session.lastOutcome, 'completed', spaceId);
    await service.action({ actor: 'leo', revisionId: 2, action: { type: 'note', text: 'A note worth keeping' } });
    // Include representative older data that no new default may erase or rename.
    await service.store.transact(data => {
      data.state.projects.push({ id: 'original-project', title: 'Original project', description: 'Keep this exact catalog.', color: '#687957' });
      data.state.contributions.push({ id: 'original-vote', actorId: 'leo', projectId: 'original-project', points: 2 });
      data.state.extras.oldMetadata = { label: 'An older non-collection feature' };
    });
    await service.submit('Continue from the same thread');
    await service.waitForIdle();
    const saved = service.store.read();
    assert.equal(saved.currentRevisionId, 3, spaceId);
    assert.equal(saved.session.turns.length, 2, spaceId);
    assert.equal(saved.session.lastOutcome, 'completed', spaceId);
    assert.equal(current(saved).source, savedSource);
    assert.equal(current(saved).tests, savedTests);
    assert.equal(current(saved).meta.layout, undefined, 'An older layout remains valid saved source.');
    before.set(spaceId, { saved, disk: await readFile(savedPath(state.dataDir, spaceId), 'utf8') });
  }
  assert.equal(adapter.calls, 6, 'Only the six explicit owner requests call the model stub.');
  for (let restart = 0; restart < 2; restart++) {
    const directory = await state.reopen();
    await directory.list();
    for (const [spaceId, original] of before) {
      const service = await directory.serviceFor(spaceId);
      assert.deepEqual(service.store.read(), original.saved, spaceId);
      assert.equal(await readFile(savedPath(state.dataDir, spaceId), 'utf8'), original.disk, spaceId);
      assert.equal((await directory.metadata(spaceId)).hasBuilt, true, spaceId);
      assert.match((await service.snapshot('leo')).html, /1 saved notes/);
    }
  }
  assert.equal(adapter.calls, 6, 'Restoring saved canvases never generates replacement content.');
});

test('resetting any default person or new account returns to the same empty canvas', async t => {
  const adapter = publishingAdapter();
  const { directory } = await fixture(t, adapter);
  await directory.signIn({ name: 'Rowan' });
  for (const person of directory.people()) {
    const service = await directory.serviceFor(person.ownSpaceId);
    await service.submit('Make an observatory');
    await service.waitForIdle();
    assert.equal((await directory.metadata(person.ownSpaceId)).hasBuilt, true, person.name);
    const oldThread = service.store.read().session.id;
    await service.reset();
    const reset = service.store.read();
    assertEmpty(reset, person.name);
    assert.notEqual(reset.session.id, oldThread, 'Reset begins a new thread.');
    assert.equal((await directory.metadata(person.ownSpaceId)).hasBuilt, false, person.name);
    assert.equal((await service.snapshot(person.id)).html, '', person.name);
  }
  assert.equal(adapter.calls, directory.people().length, 'Reset itself requires no model call.');
});
