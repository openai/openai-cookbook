import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { agentTools, createSpaceService } from '../server/harness.mjs';

const noteSource = (heading = 'A little notebook') => `const heading = ${JSON.stringify(heading)};
export const meta = { title: heading, subtitle: '', accent: '#687957', layout: 'canvas' };
export function render(state, actor) {
  return '<section><h1>' + heading + '</h1><p>' + Object.keys(state.extras.notes || {}).length + ' notes</p></section>';
}
export function reduce(state, action, actor) {
  if (action.type !== 'note' || typeof action.text !== 'string' || !action.text.trim()) throw Error('Write a note first.');
  state.extras.notes = { ...(state.extras.notes || {}), [actor.id]: { actorId: actor.id, text: action.text.trim() } };
  return state;
}
`;

const noteTests = `export function runTests(api) {
  const actor = { id: 'notebook-test', name: 'Notebook visitor' };
  const next = api.reduce(api.initialState, { type: 'note', text: 'A small thought' }, actor);
  let blocked = false;
  try { api.reduce(api.initialState, { type: 'note', text: '' }, actor); } catch { blocked = true; }
  return [
    { name: 'A visitor can save a note', ok: next.extras.notes[actor.id].text === 'A small thought' },
    { name: 'Empty notes are refused', ok: blocked },
    { name: 'The current page renders', ok: api.render(api.initialState, actor).includes('notes') },
    { name: 'Existing contributions are preserved', ok: JSON.stringify(next.contributions) === JSON.stringify(api.initialState.contributions) }
  ];
}
`;

const patch = (...sections) => ['*** Begin Patch', ...sections, '*** End Patch'].join('\n');
const add = (path, content) => `*** Add File: ${path}\n${content.replace(/\n$/, '').split('\n').map(line => `+${line}`).join('\n')}`;
const update = (path, before, after) => `*** Update File: ${path}\n@@\n-${before}\n+${after}`;
const fullPatch = (source = noteSource(), tests = noteTests) => patch(add('space.js', source), add('tests.js', tests));
const customCall = (input, callId = 'patch', name = 'apply_patch') => ({ type: 'custom_tool_call', id: `ctc-${callId}`, call_id: callId, name, input });
const response = (input = fullPatch(), callId = 'patch', name = 'apply_patch') => ({ output: [customCall(input, callId, name)] });
const adapter = (respond) => ({ keyAvailable: true, model: 'test-model', tier: 'ultrafast', respond });

async function setup(t, respond) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-codex-patch-'));
  const services = [];
  const open = async (nextRespond = respond) => {
    const service = await createSpaceService({ dataDir, adapter: adapter(nextRespond) });
    services.push(service);
    return service;
  };
  t.after(async () => {
    for (const service of services) await service.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  return { service: await open(), dataDir, open };
}

async function turn(service, message = 'Build a notebook for visitors.') {
  await service.submit(message);
  await service.waitForIdle();
}

function resultFor(items, callId) {
  const outputs = items.filter(item => item.call_id === callId && item.type.endsWith('_output'));
  assert.equal(outputs.length, 1, `One result must match ${callId}`);
  assert.equal(outputs[0].type, 'custom_tool_call_output');
  return JSON.parse(outputs[0].output);
}

async function workingFiles(service, dataDir) {
  const turnId = service.store.read().session.turns.at(-1).id;
  const directory = join(dataDir, 'workspaces', turnId);
  return {
    source: await readFile(join(directory, 'space.js'), 'utf8'),
    tests: await readFile(join(directory, 'tests.js'), 'utf8'),
  };
}

test('the builder exposes one Codex grammar tool for full writes and patches', () => {
  assert.deepEqual(agentTools.map(tool => tool.name).sort(), ['apply_patch', 'inspect_space', 'publish_revision', 'read_file', 'verify_workspace']);
  const tool = agentTools.find(tool => tool.name === 'apply_patch');
  assert.equal(tool.type, 'custom');
  assert.equal(tool.format.type, 'grammar');
  assert.equal(tool.format.syntax, 'lark');
  for (const marker of ['*** Begin Patch', '*** End Patch', '*** Add File:', '*** Update File:', '*** Delete File:', '*** Move to:', '@@']) {
    assert.ok(tool.format.definition.includes(marker), `Grammar includes ${marker}`);
  }
  assert.equal(tool.parameters, undefined, 'Patch text is not JSON function arguments');
});

test('custom Add File patches replace the initial files and publish a verified revision once', async t => {
  let calls = 0;
  const { service, dataDir } = await setup(t, async request => {
    calls++;
    assert.deepEqual(request.tools, agentTools);
    return response(fullPatch(), 'first-full-write');
  });
  await turn(service);
  const snapshot = await service.snapshot();
  assert.equal(snapshot.session.lastOutcome, 'completed');
  assert.equal(snapshot.revision.id, 2);
  assert.equal(snapshot.revision.source, noteSource());
  assert.equal(snapshot.revision.tests, noteTests);
  assert.ok(snapshot.revision.checks.every(check => check.ok));
  assert.equal(calls, 1, 'No extra model call is required after publication');
  assert.equal(snapshot.events.filter(event => event.type === 'revision.published').length, 1);
  assert.deepEqual(await workingFiles(service, dataDir), { source: noteSource(), tests: noteTests });
  assert.equal(resultFor(service.store.read().session.items, 'first-full-write').revisionId, 2);
});

test('custom Update File preserves untouched code, tests, participant state and prior custom history', async t => {
  let calls = 0;
  const { service } = await setup(t, async ({ input }) => {
    if (++calls === 1) return response(fullPatch(), 'create');
    assert.equal(resultFor(input, 'create').revisionId, 2);
    assert.ok(input.some(item => item.type === 'custom_tool_call' && item.call_id === 'create' && item.input === fullPatch()));
    return response(patch(update('space.js', 'const heading = "A little notebook";', 'const heading = "Our shared notebook";')), 'rename');
  });
  await turn(service);
  await service.action({ actor: 'leo', revisionId: 2, action: { type: 'note', text: 'Keep this visitor thought' } });
  const before = await service.snapshot();
  await turn(service, 'Rename it Our shared notebook.');
  const after = await service.snapshot();
  assert.equal(after.revision.id, 3);
  assert.equal(after.revision.source, noteSource('Our shared notebook'));
  assert.equal(after.revision.tests, before.revision.tests);
  assert.deepEqual(after.state, before.state);
  assert.match(after.html, /Our shared notebook/);
  assert.equal(calls, 2);
  assert.equal(resultFor(service.store.read().session.items, 'rename').revisionId, 3);
});

test('one custom patch can update source and replace tests before atomic verification', async t => {
  let calls = 0;
  const changedTests = noteTests.replace("ok: api.render(api.initialState, actor).includes('notes')", "ok: api.render(api.initialState, actor).includes('A brighter notebook')");
  const { service } = await setup(t, async () => ++calls === 1 ? response(fullPatch(), 'create') : response(patch(
    update('space.js', 'const heading = "A little notebook";', 'const heading = "A brighter notebook";'),
    add('tests.js', changedTests),
  ), 'mixed'));
  await turn(service);
  await turn(service, 'Brighten the notebook and verify its heading.');
  const after = await service.snapshot();
  assert.equal(after.session.lastOutcome, 'completed');
  assert.equal(after.revision.id, 3);
  assert.equal(after.revision.source, noteSource('A brighter notebook'));
  assert.equal(after.revision.tests, changedTests);
  assert.ok(after.revision.checks.every(check => check.ok));
  assert.equal(after.events.filter(event => event.type === 'revision.published').length, 2);
  assert.equal(resultFor(service.store.read().session.items, 'mixed').revisionId, 3);
});

test('a failed custom patch returns checks and can be repaired against its working files', async t => {
  let calls = 0;
  const badTests = 'export function runTests() {\n  return [{ name: "Repair this behavior", ok: false }];\n}\n';
  const repairedTests = badTests.replace('ok: false', 'ok: true');
  const { service, dataDir } = await setup(t, async ({ input }) => {
    if (++calls === 1) return response(fullPatch(noteSource(), badTests), 'bad-check');
    const feedback = resultFor(input, 'bad-check');
    assert.equal(feedback.ok, false);
    assert.ok(feedback.checks.some(check => check.name === 'Repair this behavior' && !check.ok));
    assert.equal((await service.snapshot()).revision.id, 1, 'Failed checks cannot publish');
    assert.deepEqual(await workingFiles(service, dataDir), { source: noteSource(), tests: badTests });
    return response(patch(update('tests.js', '  return [{ name: "Repair this behavior", ok: false }];', '  return [{ name: "Repair this behavior", ok: true }];')), 'repair');
  });
  await turn(service);
  const after = await service.snapshot();
  assert.equal(after.session.lastOutcome, 'completed');
  assert.equal(after.revision.id, 2);
  assert.equal(after.revision.tests, repairedTests);
  assert.equal(calls, 2);
  assert.equal(resultFor(service.store.read().session.items, 'repair').revisionId, 2);
});

test('a later invalid hunk cannot partially apply an earlier valid file edit', async t => {
  let calls = 0;
  const { service, dataDir } = await setup(t, async ({ input }) => {
    if (++calls === 1) return response(fullPatch(), 'create');
    if (calls === 2) return response(patch(
      update('space.js', 'const heading = "A little notebook";', 'const heading = "Do not save this";'),
      update('tests.js', 'a missing line that cannot match', 'should not write this'),
    ), 'bad-match');
    assert.equal(resultFor(input, 'bad-match').ok, false);
    assert.deepEqual(await workingFiles(service, dataDir), { source: noteSource(), tests: noteTests });
    return response(patch(update('space.js', 'const heading = "A little notebook";', 'const heading = "Repaired notebook";')), 'repair-match');
  });
  await turn(service);
  await turn(service, 'Make a small edit.');
  const after = await service.snapshot();
  assert.equal(after.revision.id, 3);
  assert.equal(after.revision.source, noteSource('Repaired notebook'));
  assert.equal(after.revision.tests, noteTests);
  assert.equal(calls, 3);
});

test('custom patches cannot address paths outside the two-file workspace', async t => {
  for (const [label, destination] of [
    ['parent traversal', '../outside.js'],
    ['nested traversal', 'nested/../space.js'],
    ['dot path alias', './space.js'],
    ['host app source', 'src/App.tsx'],
    ['absolute path', null],
  ]) await t.test(label, async t => {
    let calls = 0;
    const { service, dataDir } = await setup(t, async ({ input }) => {
      if (++calls === 1) return response(patch(add('tests.js', noteTests), add(destination || join(dataDir, 'outside.js'), noteSource())), 'forbidden-path');
      const feedback = resultFor(input, 'forbidden-path');
      assert.equal(feedback.ok, false);
      assert.match(feedback.error, /space\.js|tests\.js|path|workspace/i);
      assert.deepEqual(await workingFiles(service, dataDir), original);
      assert.equal(await readFile(join(dataDir, 'outside.js'), 'utf8'), 'Untouched sentinel');
      return response(fullPatch(), 'valid-path');
    });
    await writeFile(join(dataDir, 'outside.js'), 'Untouched sentinel');
    const initial = await service.snapshot();
    const original = { source: initial.revision.source, tests: initial.revision.tests };
    await turn(service);
    assert.equal((await service.snapshot()).revision.id, 2);
    assert.equal(calls, 2);
    assert.equal(await readFile(join(dataDir, 'outside.js'), 'utf8'), 'Untouched sentinel');
  });
});

test('custom patches preserve source bounds and require a complete two-file workspace', async t => {
  for (const [label, sourceSection, error] of [
    ['UTF-8 byte limit', add('space.js', `${noteSource()}/*${'🌱'.repeat(20_001)}*/\n`), /80|large|size|bytes/i],
    ['minimum source size', add('space.js', 'x'), /10|JavaScript|small|empty/i],
    ['required source deletion', '*** Delete File: space.js', /space\.js|delete|required|workspace/i],
  ]) await t.test(label, async t => {
    let calls = 0;
    const { service, dataDir } = await setup(t, async ({ input }) => {
      if (++calls === 1) return response(patch(add('tests.js', noteTests), sourceSection), 'invalid-workspace');
      const feedback = resultFor(input, 'invalid-workspace');
      assert.equal(feedback.ok, false);
      assert.match(feedback.error, error);
      assert.deepEqual(await workingFiles(service, dataDir), original, 'Bounds failures must not write either file');
      return response(fullPatch(), 'valid-workspace');
    });
    const initial = await service.snapshot();
    const original = { source: initial.revision.source, tests: initial.revision.tests };
    await turn(service);
    assert.equal((await service.snapshot()).revision.id, 2);
    assert.equal(calls, 2);
  });
});

test('unknown custom tools are rejected with a custom result and the builder can recover', async t => {
  let calls = 0;
  const { service, dataDir } = await setup(t, async ({ input }) => {
    if (++calls === 1) return response(fullPatch(), 'unknown-call', 'write_file');
    const feedback = resultFor(input, 'unknown-call');
    assert.equal(feedback.ok, false);
    assert.match(feedback.error, /unknown|unsupported|custom/i);
    assert.deepEqual(await workingFiles(service, dataDir), original);
    return response(fullPatch(), 'known-call');
  });
  const initial = await service.snapshot();
  const original = { source: initial.revision.source, tests: initial.revision.tests };
  await turn(service);
  assert.equal((await service.snapshot()).revision.id, 2);
  assert.equal(calls, 2);
});

test('cancellation after recording a custom call closes it with the matching result type', async t => {
  const { service } = await setup(t, async () => response(fullPatch(), 'cancelled-patch'));
  const unsubscribe = service.store.subscribe(event => { if (event.type === 'model.completed') void service.cancel(); });
  t.after(unsubscribe);
  await turn(service);
  const after = await service.snapshot();
  assert.equal(after.revision.id, 1);
  assert.equal(after.session.lastOutcome, 'cancelled');
  const items = service.store.read().session.items;
  assert.ok(items.some(item => item.type === 'custom_tool_call' && item.call_id === 'cancelled-patch'));
  assert.match(resultFor(items, 'cancelled-patch').error, /cancel/i);
});

test('restart pairs unfinished custom and legacy calls without duplicating completed results', async t => {
  const { service, open } = await setup(t, async () => response(fullPatch(), 'continued'));
  const completedCall = customCall(fullPatch(), 'already-completed');
  const completedOutput = { type: 'custom_tool_call_output', call_id: completedCall.call_id, output: '{"ok":true}' };
  await service.store.transact(data => {
    data.session.status = 'running';
    data.session.items.push(
      completedCall, completedOutput,
      customCall(fullPatch(), 'abandoned-custom'),
      { type: 'function_call', id: 'fc-abandoned', call_id: 'abandoned-legacy', name: 'inspect_space', arguments: '{}' },
    );
  });
  await service.close();
  const reopened = await open(async ({ input }) => {
    assert.match(resultFor(input, 'abandoned-custom').error, /restart/i);
    assert.deepEqual(resultFor(input, 'already-completed'), { ok: true });
    assert.ok(input.some(item => item.type === 'function_call_output' && item.call_id === 'abandoned-legacy'));
    return response(fullPatch(), 'continued');
  });
  const recovered = await reopened.snapshot();
  assert.equal(recovered.session.status, 'idle');
  assert.equal(recovered.session.lastOutcome, 'interrupted');
  await turn(reopened, 'Continue with the notebook.');
  assert.equal((await reopened.snapshot()).revision.id, 2);
  assert.equal(resultFor(reopened.store.read().session.items, 'continued').revisionId, 2);
});

test('saved legacy builds and encrypted context survive a restart into custom patch turns', async t => {
  const legacyCall = { type: 'function_call', id: 'fc-legacy-create', call_id: 'legacy-create', name: 'apply_change', arguments: JSON.stringify({ source: noteSource(), tests: noteTests, summary: 'A little notebook' }) };
  const encrypted = { type: 'reasoning', id: 'legacy-reasoning', summary: [], encrypted_content: 'opaque-fixture-context' };
  const { service, open } = await setup(t, async () => ({ output: [encrypted, legacyCall] }));
  await turn(service);
  await service.action({ actor: 'leo', revisionId: 2, action: { type: 'note', text: 'Saved before the migration' } });
  const before = await service.snapshot();
  await service.close();
  const reopened = await open(async ({ input }) => {
    assert.ok(input.some(item => item.type === 'function_call' && item.arguments === legacyCall.arguments));
    assert.ok(input.some(item => item.type === 'function_call_output' && item.call_id === 'legacy-create' && JSON.parse(item.output).revisionId === 2));
    assert.ok(input.some(item => item.encrypted_content === encrypted.encrypted_content));
    return response(patch(update('space.js', 'const heading = "A little notebook";', 'const heading = "A continuing notebook";')), 'new-format');
  });
  await turn(reopened, 'Continue the same notebook.');
  const after = await reopened.snapshot();
  assert.equal(after.revision.id, 3);
  assert.equal(after.revision.source, noteSource('A continuing notebook'));
  assert.deepEqual(after.state, before.state);
  assert.equal(after.session.id, before.session.id);
  assert.equal(after.session.turnCount, 2);
  assert.equal(resultFor(reopened.store.read().session.items, 'new-format').revisionId, 3);
});
