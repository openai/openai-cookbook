import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createSpaceDirectory } from '../server/identity.mjs';
import { compileModule, renderModule, reduceModule, verifyModule } from '../server/runtime.mjs';
import { blankSeedSource } from '../server/seed.mjs';
import { communityBoardSource, communityBoardTests, communityBoardSeed } from '../server/community-board.mjs';

const mira = { id: 'mira', name: 'Mira' };
const james = { id: 'james', name: 'James' };
const empty = () => ({ projects: [], contributions: [], extras: {} });
const compiled = compileModule(communityBoardSource);
const apply = async (state, action, actor = mira) => reduceModule((await compiled).bundle, state, action, actor);
const render = async (state, actor = mira) => renderModule((await compiled).bundle, state, actor);
const messages = state => Object.entries(state.extras.boardMessages || {});
const current = data => data.revisions.find(revision => revision.id === data.currentRevisionId);

async function fixture(t, options = {}) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-community-board-'));
  const adapter = { keyAvailable: false, respond() { assert.fail('The preloaded board must not call a model.'); } };
  let directory = await createSpaceDirectory({ dataDir, adapter, ...options });
  t.after(async () => { await directory.close(); await rm(dataDir, { recursive: true, force: true }); });
  return {
    dataDir,
    get directory() { return directory; },
    async reopen() {
      await directory.close();
      directory = await createSpaceDirectory({ dataDir, adapter, ...options });
      return directory;
    },
  };
}

test('the preloaded board passes ordinary owner and visitor verification without adding fake posts', async () => {
  assert.deepEqual(communityBoardSeed.state, empty());
  assert.equal(communityBoardSeed.source, communityBoardSource);
  assert.equal(communityBoardSeed.tests, communityBoardTests);
  const state = empty();
  state.extras.notes = { james: { actorId: 'james', text: 'Keep this unrelated note.' } };
  const before = structuredClone(state);
  const result = await verifyModule(communityBoardSource, communityBoardTests, state, {
    owner: { id: 'nora', name: 'Nora' }, visitor: mira,
  });
  assert.equal(result.ok, true, JSON.stringify(result.checks.filter(check => !check.ok)));
  assert.deepEqual(state, before);
  assert.equal(result.meta.layout, 'canvas');
  const html = await render(state);
  for (const topic of ['Introductions', 'Ideas', 'Questions', 'Recommendations']) assert.ok(html.includes(topic), topic);
  assert.match(html, /<form\b/);
  assert.match(html, /<textarea\b/);
});

test('different participants post to one shared board with trusted attribution and distinct persistent IDs', async () => {
  const original = empty();
  original.extras.notes = { james: { actorId: 'james', text: 'Preserve this data.' } };
  const first = await apply(original, {
    type: 'post_message', topicId: 'introductions', body: '  Hello from Mira.  ',
    actorId: james.id, authorName: james.name, sequence: -100, messageId: 'stolen-id',
  });
  const [[firstId, firstMessage]] = messages(first);
  assert.equal(firstMessage.body, 'Hello from Mira.');
  assert.equal(firstMessage.actorId, mira.id);
  assert.equal(firstMessage.authorName, mira.name);
  assert.equal(firstMessage.topicId, 'introductions');
  assert.ok(Number.isSafeInteger(firstMessage.sequence) && firstMessage.sequence > 0);
  assert.notEqual(firstId, 'stolen-id');
  const second = await apply(first, { type: 'post_message', topicId: 'ideas', body: 'A shared star map.' }, james);
  const third = await apply(second, { type: 'post_message', topicId: 'questions', body: 'Who wants to explore?' });
  assert.equal(messages(third).length, 3);
  assert.equal(new Set(messages(third).map(([id]) => id)).size, 3);
  assert.deepEqual(third.extras.boardMessages[firstId], firstMessage);
  assert.deepEqual(third.extras.notes, original.extras.notes);
  assert.deepEqual(original.extras, { notes: { james: { actorId: 'james', text: 'Preserve this data.' } } });
  for (const actor of [mira, james]) {
    const html = await render(await apply(third, { type: 'select_topic', topicId: 'all' }, actor), actor);
    for (const body of ['Hello from Mira.', 'A shared star map.', 'Who wants to explore?']) assert.ok(html.includes(body), body);
  }
});

test('topic selection belongs to each participant and filters only their view', async () => {
  let state = await apply(empty(), { type: 'post_message', topicId: 'ideas', body: 'A moon garden.' });
  assert.equal(state.extras.boardPreferences.mira.topicId, 'ideas', 'Posting reveals the new message in its topic.');
  state = await apply(state, { type: 'post_message', topicId: 'questions', body: 'When do the stars appear?' }, james);
  const jamesPreference = structuredClone(state.extras.boardPreferences.james);
  state = await apply(state, { type: 'select_topic', topicId: 'ideas', actorId: james.id });
  const selected = structuredClone(state.extras.boardPreferences.mira);
  assert.equal(selected.actorId, mira.id);
  assert.equal(selected.topicId, 'ideas');
  assert.deepEqual(state.extras.boardPreferences.james, jamesPreference);
  state = await apply(state, { type: 'select_topic', topicId: 'questions' }, james);
  assert.deepEqual(state.extras.boardPreferences.mira, selected);
  const miraHtml = await render(state, mira);
  const jamesHtml = await render(state, james);
  assert.ok(miraHtml.includes('A moon garden.'));
  assert.ok(!miraHtml.includes('When do the stars appear?'));
  assert.ok(jamesHtml.includes('When do the stars appear?'));
  assert.ok(!jamesHtml.includes('A moon garden.'));
  const all = await apply(state, { type: 'select_topic', topicId: 'all' });
  assert.equal(messages(all).length, 2);
  assert.ok((await render(all)).includes('When do the stars appear?'));
});

test('participants can remove their own messages but cannot remove someone else’s', async () => {
  const first = await apply(empty(), { type: 'post_message', topicId: 'recommendations', body: 'Visit the observatory.' });
  const [[firstId, firstMessage]] = messages(first);
  const second = await apply(first, { type: 'post_message', topicId: 'recommendations', body: 'Visit the arcade.' }, james);
  await assert.rejects(apply(second, { type: 'delete_message', messageId: firstId, actorId: mira.id }, james));
  const removed = await apply(second, { type: 'delete_message', messageId: firstId });
  assert.equal(removed.extras.boardMessages[firstId], undefined);
  assert.equal(messages(removed).length, 1);
  assert.equal(messages(removed)[0][1].actorId, james.id);
  assert.deepEqual(second.extras.boardMessages[firstId], firstMessage);
});

test('deleted message IDs are never reused after topic changes, so stale deletes cannot remove new posts', async () => {
  const first = await apply(empty(), { type: 'post_message', topicId: 'introductions', body: 'The original note.' });
  const [[firstId, firstMessage]] = messages(first);
  const removed = await apply(first, { type: 'delete_message', messageId: firstId });
  const switched = await apply(removed, { type: 'select_topic', topicId: 'ideas' });
  const posted = await apply(switched, { type: 'post_message', topicId: 'ideas', body: 'A new note to keep.' });
  const [[newId, newMessage]] = messages(posted);
  assert.notEqual(newId, firstId);
  assert.ok(newMessage.sequence > firstMessage.sequence);
  const before = structuredClone(posted);
  await assert.rejects(apply(posted, { type: 'delete_message', messageId: firstId }));
  assert.deepEqual(posted, before);
  assert.equal(posted.extras.boardMessages[newId].body, 'A new note to keep.');
});

test('message ordering keeps advancing after every participant clears their posts and changes topics', async () => {
  let state = await apply(empty(), { type: 'post_message', topicId: 'ideas', body: 'The first idea.' });
  state = await apply(state, { type: 'post_message', topicId: 'questions', body: 'The later question.' }, james);
  const priorMessages = messages(state);
  const lastSequence = Math.max(...priorMessages.map(([, message]) => message.sequence));
  for (const [id, message] of priorMessages) {
    state = await apply(state, { type: 'delete_message', messageId: id }, message.actorId === mira.id ? mira : james);
  }
  assert.equal(messages(state).length, 0);
  for (const actor of [mira, james]) state = await apply(state, { type: 'select_topic', topicId: 'all' }, actor);
  state = await apply(state, { type: 'post_message', topicId: 'introductions', body: 'A fresh conversation.' });
  const [[id, message]] = messages(state);
  assert.ok(message.sequence > lastSequence);
  assert.ok(priorMessages.every(([oldId]) => oldId !== id));
  for (const [oldId, oldMessage] of priorMessages) {
    await assert.rejects(apply(state, { type: 'delete_message', messageId: oldId }, oldMessage.actorId === mira.id ? mira : james));
  }
  assert.equal(state.extras.boardMessages[id].body, 'A fresh conversation.');
});

test('the board rejects invalid actions and message inputs while accepting its documented length limit', async () => {
  const state = empty();
  const invalid = [
    { type: 'unknown' },
    { type: 'select_topic', topicId: 'made-up' },
    { type: 'select_topic', topicId: '__proto__' },
    { type: 'post_message', topicId: 'all', body: 'No all-topic posts.' },
    { type: 'post_message', topicId: 'made-up', body: 'No unknown topics.' },
    { type: 'post_message', topicId: 'ideas', body: '' },
    { type: 'post_message', topicId: 'ideas', body: ' \n\t ' },
    { type: 'post_message', topicId: 'ideas', body: 42 },
    { type: 'post_message', topicId: 'ideas', body: 'a'.repeat(601) },
    { type: 'delete_message', messageId: 'not-a-real-message' },
  ];
  for (const action of invalid) await assert.rejects(apply(state, action), JSON.stringify(action));
  assert.equal(messages(await apply(state, { type: 'post_message', topicId: 'ideas', body: 'a'.repeat(600) }))[0][1].body.length, 600);
  assert.deepEqual(state, empty());
});

test('posted content and saved display names are rendered as text, never executable markup', async () => {
  const text = '<script>alert("hello")</script> & <img src=x onerror="alert(1)">';
  const state = await apply(empty(), { type: 'post_message', topicId: 'ideas', body: text });
  messages(state)[0][1].authorName = '<b>A name & more</b>';
  const html = await render(state);
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(html.includes('&lt;img'));
  assert.ok(html.includes('&lt;b&gt;A name &amp; more&lt;/b&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('<img src=x'));
  assert.equal(messages(state)[0][1].body, text);
});

test('the capacity guard keeps a heavily escaped board readable without losing existing messages', async () => {
  let state = empty();
  let full = false;
  for (let index = 0; index <= 120; index++) {
    const before = structuredClone(state);
    try {
      state = await apply(state, { type: 'post_message', topicId: 'ideas', body: '&'.repeat(600) });
    } catch (error) {
      assert.match(error.message, /board is full/i);
      assert.deepEqual(state, before, 'A rejected post leaves every earlier post intact.');
      full = true;
      break;
    }
  }
  assert.equal(full, true, 'The board must stop accepting posts before exhausting its render budget.');
  const retained = messages(state);
  assert.ok(retained.length > 1 && retained.length <= 120);
  for (const actor of [{ id: 'nora', name: 'Nora' }, mira]) {
    const allTopics = await apply(state, { type: 'select_topic', topicId: 'all' }, actor);
    const html = await render(allTopics, actor);
    assert.ok(html.length < 180_000, `${actor.name} can open the complete board.`);
    assert.equal((html.match(/class="message-body"/g) || []).length, retained.length);
    assert.deepEqual(messages(allTopics), retained);
  }
});

test('the ready bundled Nora icon does not call the configured image generator', async t => {
  let calls = 0;
  const fixtureState = await fixture(t, { iconGenerator: async () => { calls++; throw new Error('Unexpected image generation.'); } });
  const metadata = await fixtureState.directory.metadata('nora');
  assert.equal(metadata.icon.status, 'ready');
  assert.equal(metadata.icon.dataUrl, `data:image/webp;base64,${communityBoardSeed.icon.data}`);
  assert.equal(calls, 0);
  await fixtureState.reopen();
  assert.deepEqual((await fixtureState.directory.metadata('nora')).icon, metadata.icon);
  assert.equal(calls, 0);
});

test('a fresh directory exposes Nora’s ready board and shares saved messages across visits and restart', async t => {
  const fixtureState = await fixture(t);
  const nora = fixtureState.directory.people().find(person => person.id === 'nora');
  assert.equal(nora.name, 'Nora');
  assert.equal((await fixtureState.directory.metadata('nora')).hasBuilt, true);
  const service = await fixtureState.directory.serviceFor('nora');
  assert.equal(current(service.store.read()).source, communityBoardSource);
  assert.deepEqual(service.store.read().state, empty());
  assert.equal(service.store.read().session.turns.length, 0);
  const revisionId = service.store.read().currentRevisionId;
  await service.action({ actor: mira.id, revisionId, action: { type: 'post_message', topicId: 'introductions', body: 'Hello from a returning visitor.' } });
  await service.action({ actor: james.id, revisionId, action: { type: 'post_message', topicId: 'ideas', body: 'A neighborhood book swap.' } });
  for (const actor of [mira, james]) await service.action({ actor: actor.id, revisionId, action: { type: 'select_topic', topicId: 'all' } });
  const before = service.store.read();
  const directory = await fixtureState.reopen();
  const reopened = await directory.serviceFor('nora');
  assert.deepEqual(reopened.store.read(), before);
  assert.ok((await reopened.snapshot(mira.id)).html.includes('A neighborhood book swap.'));
  assert.ok((await reopened.snapshot(james.id)).html.includes('Hello from a returning visitor.'));
});

test('opening an existing board preserves owner edits, records and its builder conversation', async t => {
  const fixtureState = await fixture(t);
  const service = await fixtureState.directory.serviceFor('nora');
  await service.action({ actor: mira.id, revisionId: service.store.read().currentRevisionId, action: { type: 'post_message', topicId: 'ideas', body: 'Keep this shared idea.' } });
  await service.store.transact(data => {
    const revision = current(data);
    data.revisions.push({ ...revision, id: revision.id + 1, source: `${revision.source}\n// The owner keeps this edit.\n` });
    data.currentRevisionId++;
    data.session.turns = [{ id: 'owner-edit', message: 'Keep my own version', status: 'completed', revisionId: data.currentRevisionId }];
    data.session.items = [{ role: 'user', content: 'Keep my own version' }];
  });
  const before = service.store.read();
  const savedFile = join(fixtureState.dataDir, 'spaces', 'nora', 'space.json');
  const disk = await readFile(savedFile, 'utf8');
  await fixtureState.reopen();
  assert.deepEqual((await fixtureState.directory.serviceFor('nora')).store.read(), before);
  assert.equal(await readFile(savedFile, 'utf8'), disk);
});

test('an explicit owner reset stays blank after reopening instead of re-installing the example', async t => {
  const fixtureState = await fixture(t);
  const service = await fixtureState.directory.serviceFor('nora');
  await service.reset();
  assert.equal(current(service.store.read()).source, blankSeedSource);
  assert.deepEqual(service.store.read().state, empty());
  await fixtureState.reopen();
  const reopened = await fixtureState.directory.serviceFor('nora');
  assert.equal(current(reopened.store.read()).source, blankSeedSource);
  assert.equal((await fixtureState.directory.metadata('nora')).hasBuilt, false);
});
