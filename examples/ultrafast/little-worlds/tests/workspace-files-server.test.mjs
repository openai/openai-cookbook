import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createWorkspaceFiles } from '../server/workspace-files.mjs';
import { createSpaceService } from '../server/harness.mjs';
import { blankSeedSource, blankSeedTests } from '../server/seed.mjs';

const getFile = (feed, path = 'space.js') => feed.read().data.files.find(file => file.path === path);
const add = (feed, name, index = 0, args = '') => feed.providerEvent({ type: 'response.output_item.added', output_index: index, item: { type: 'function_call', name, arguments: args } });
const delta = (feed, text, index = 0) => feed.providerEvent({ type: 'response.function_call_arguments.delta', output_index: index, delta: text });
const addCustom = (feed, input = '', index = 0) => feed.providerEvent({ type: 'response.output_item.added', output_index: index, item: { type: 'custom_tool_call', name: 'apply_patch', input } });
const customDelta = (feed, text, index = 0) => feed.providerEvent({ type: 'response.custom_tool_call_input.delta', output_index: index, delta: text });
function fixture(t, overrides = {}) {
  const published = { sessionId: 'session', revisionId: 1, source: 'const original = "before";', tests: 'export function runTests() {}', ...overrides };
  const feed = createWorkspaceFiles({ getPublished: () => ({ ...published }), intervalMs: 60_000 });
  t.after(() => feed.close());
  return { feed, published };
}

test('initial and accepted working files are complete bounded snapshots, isolated from viewer mutation', t => {
  const source = 's'.repeat(80_000), tests = 't'.repeat(80_000);
  const { feed } = fixture(t, { source, tests });
  assert.deepEqual(feed.read().data.files.map(file => [file.path, file.content]), [['space.js', source], ['tests.js', tests]]);
  assert.equal(feed.read().data.status, 'published');
  const snapshot = feed.read(); snapshot.data.files[0].content = 'tampered';
  assert.equal(getFile(feed).content, source);
  feed.begin('turn'); feed.working({ source: source.slice(1), tests });
  assert.equal(getFile(feed).content.length, 79_999);
  assert.equal(feed.read().data.status, 'working');
  assert.equal(feed.read().data.turnId, 'turn');
});

test('partial source and tests decode as they stream, including escapes across chunks', t => {
  const { feed } = fixture(t); feed.begin('turn'); add(feed, 'apply_change');
  delta(feed, '{"source":"line one\\nquote: \\"');
  assert.equal(getFile(feed).content, 'line one\nquote: "');
  assert.equal(getFile(feed).status, 'streaming');
  delta(feed, ' \\u2');
  assert.equal(getFile(feed).content, 'line one\nquote: " ');
  delta(feed, '603", "tests":"fresh');
  assert.equal(getFile(feed).content, 'line one\nquote: " ☃');
  assert.equal(getFile(feed, 'tests.js').content, 'fresh');
  delta(feed, ' checks", "summary":"a finished draft"}');
  assert.equal(getFile(feed, 'tests.js').content, 'fresh checks');
  assert.equal(feed.read().data.revisionId, 1, 'A preview is not a publication');
});

test('whitespace at chunk boundaries retains completed file content and patch edits', t => {
  const { feed } = fixture(t); feed.begin('turn'); add(feed, 'apply_change');
  for (const part of ['{"source":"new source"', ', ', '"tests":"new tests"', ', ', '"summary":"done"}']) {
    delta(feed, part);
    assert.equal(getFile(feed).content, 'new source');
  }
  feed.beginResponse(); add(feed, 'apply_patch');
  for (const part of ['{"edits":[{"path":"space.js","search":"before","replace":"after"}', ', ', '{"path":"tests.js","search":"runTests","replace":"newTests"}', ' ], ']) {
    delta(feed, part);
    assert.equal(getFile(feed).content, 'const original = "after";');
  }
});

test('write_file requires a complete allowlisted path and ignores text shaped like another property', t => {
  const { feed } = fixture(t); feed.begin('turn'); add(feed, 'write_file');
  delta(feed, '{"content":"before \\"source\\": \\"false\\"", "path":"space.');
  assert.equal(getFile(feed).status, 'working');
  delta(feed, 'js"}');
  assert.equal(getFile(feed).content, 'before "source": "false"');
  feed.beginResponse(); add(feed, 'write_file', 0, '{"path":"../.env","content":"PRIVATE_HOST_FILE"}');
  assert.equal(getFile(feed).content, 'const original = "before";');
  assert.doesNotMatch(JSON.stringify(feed.read()), /PRIVATE_HOST_FILE|\.env/);
});

test('patch streams replacement text only after its path and exact search are complete', t => {
  const { feed } = fixture(t); feed.begin('turn'); add(feed, 'apply_patch');
  delta(feed, '{"edits":[{"path":"space.js","search":"befo');
  assert.equal(getFile(feed).content, 'const original = "before";');
  delta(feed, 're","replace":"a');
  assert.equal(getFile(feed).content, 'const original = "a";');
  delta(feed, 'fter"},{"path":"tests.js","search":"runTests","replace":"updated');
  assert.equal(getFile(feed).content, 'const original = "after";');
  assert.equal(getFile(feed, 'tests.js').content, 'export function updated() {}');
  delta(feed, 'Tests"}],"summary":"Updated both"}');
  assert.equal(getFile(feed, 'tests.js').content, 'export function updatedTests() {}');
});

test('Codex additions stream raw source and tests including unfinished long lines', t => {
  const { feed, published } = fixture(t); feed.begin('turn'); addCustom(feed);
  customDelta(feed, '*** Begin Patch\n*** Add File: space.');
  assert.equal(getFile(feed).content, published.source, 'An unfinished path cannot choose a file');
  customDelta(feed, 'js\n+const greeting = "hel');
  assert.equal(getFile(feed).content, 'const greeting = "hel');
  assert.equal(getFile(feed).status, 'streaming');
  customDelta(feed, 'lo 🌱";\n*** Add File: tests.js\n+export function run');
  assert.equal(getFile(feed).content, 'const greeting = "hello 🌱";\n');
  assert.equal(getFile(feed, 'tests.js').content, 'export function run');
  customDelta(feed, 'Tests() {}\n*** End Patch');
  const input = '*** Begin Patch\n*** Add File: space.js\n+const greeting = "hello 🌱";\n*** Add File: tests.js\n+export function runTests() {}\n*** End Patch';
  feed.providerEvent({ type: 'response.custom_tool_call_input.done', output_index: 0, input });
  assert.equal(getFile(feed, 'tests.js').content, 'export function runTests() {}\n');
  assert.equal(feed.read().data.revisionId, 1, 'Streaming never publishes');
});

test('Codex update prefixes replace only the located lines and retain surrounding source', t => {
  const source = 'const before = true;\nconst label = "old";\nconst after = true;\n';
  const { feed, published } = fixture(t, { source }); feed.begin('turn'); addCustom(feed);
  const prefix = '*** Begin Patch\n*** Update File: space.js\n@@\n const before = true;\n-const label = "old";\n+const label = "';
  customDelta(feed, prefix);
  assert.equal(getFile(feed).content, 'const before = true;\nconst label = "\nconst after = true;\n');
  customDelta(feed, 'new live text');
  assert.equal(getFile(feed).content, 'const before = true;\nconst label = "new live text\nconst after = true;\n');
  assert.equal(getFile(feed, 'tests.js').content, published.tests);
  customDelta(feed, '";\n const after = true;\n*** End Patch\n');
  assert.equal(getFile(feed).content, source.replace('"old"', '"new live text"'));
  delta(feed, 'IGNORED_WRONG_EVENT_FAMILY');
  assert.doesNotMatch(getFile(feed).content, /IGNORED/);
});

test('Codex partial control lines cannot normalize files, choose unsafe paths, or leak surrogate halves', t => {
  const { feed, published } = fixture(t); feed.begin('turn');
  addCustom(feed, '*** Begin Patch\n*** Update File: space.js\n@@\n');
  assert.equal(getFile(feed).content, published.source, 'A header is not an edit');
  feed.beginResponse(); addCustom(feed, '*** Begin Patch\n*** Add File: space.js\n+const icon = "\uD83C');
  assert.equal(getFile(feed).content, 'const icon = "');
  customDelta(feed, '\uDF31";\n*** Add File: ../.env\n');
  assert.equal(getFile(feed).content, published.source, 'A complete unsafe header invalidates the whole proposal before completion');
});

test('Codex multifile patches and mixed legacy calls project in order without duplicate application', t => {
  const source = 'const original = "before";\n';
  const { feed } = fixture(t, { source }); feed.begin('turn');
  const input = '*** Begin Patch\n*** Update File: space.js\n@@\n-const original = "before";\n+const original = "middle";\n*** Update File: tests.js\n@@\n-export function runTests() {}\n+export function runTests() { return []; }\n*** End Patch';
  feed.providerOutput([
    { type: 'custom_tool_call', name: 'apply_patch', input },
    { type: 'function_call', name: 'apply_patch', arguments: JSON.stringify({ edits: [{ path: 'space.js', search: 'middle', replace: 'after' }] }) },
  ]);
  assert.equal(getFile(feed).content, 'const original = "after";\n');
  assert.equal(getFile(feed, 'tests.js').content, 'export function runTests() { return []; }\n');
  const accepted = { source: getFile(feed).content, tests: getFile(feed, 'tests.js').content };
  feed.working(accepted);
  assert.equal(getFile(feed).content, accepted.source);
  assert.equal(getFile(feed).status, 'working');
});

test('malformed, unbounded, and unfinished completed Codex calls cannot affect the file view', t => {
  const { feed, published } = fixture(t); feed.begin('turn');
  const prefix = '*** Begin Patch\n*** Add File: space.js\n+const replacement = true;\n';
  for (const input of [
    `${prefix}*** Add File: ../.env\n+PRIVATE_HOST_FILE\n*** End Patch`,
    `${prefix}*** Update File: tests.js\n*** Move to: /tmp/escape.js\n@@\n-export function runTests() {}\n+export function runTests() {}\n*** End Patch`,
    `${prefix}malformed input\n*** End Patch`,
    `${prefix}*** Add File: tests.js\n+${'x'.repeat(80_001)}\n*** End Patch`,
    prefix,
  ]) {
    feed.beginResponse(); addCustom(feed, prefix);
    assert.equal(getFile(feed).content, 'const replacement = true;\n');
    feed.providerEvent({ type: 'response.custom_tool_call_input.done', output_index: 0, input });
    assert.equal(getFile(feed).content, published.source);
    assert.equal(getFile(feed, 'tests.js').content, published.tests);
    assert.doesNotMatch(JSON.stringify(feed.read()), /PRIVATE_HOST_FILE|escape\.js/);
  }
});

test('settling custom patches restores published files and ignores late custom deltas', t => {
  const { feed, published } = fixture(t); feed.begin('turn');
  addCustom(feed, '*** Begin Patch\n*** Add File: space.js\n+const draft = true;');
  assert.equal(getFile(feed).content, 'const draft = true;');
  feed.published();
  customDelta(feed, '\n+const late = true;\n*** End Patch');
  assert.equal(getFile(feed).content, published.source);
  assert.equal(feed.read().data.status, 'published');
});

test('ambiguous, invalid, and oversized patches never change the file view', t => {
  const { feed, published } = fixture(t, { source: 'same same' }); feed.begin('turn');
  const preview = edits => { feed.beginResponse(); add(feed, 'apply_patch', 0, JSON.stringify({ edits, summary: 'Preview' })); return getFile(feed).content; };
  for (const edit of [
    { path: 'space.js', search: 'same', replace: 'new' },
    { path: 'space.js', search: 'absent', replace: 'new' },
    { path: '../../.env', search: 'same same', replace: 'new' },
    { path: 'space.js', search: 'same same', replace: 'x'.repeat(80_001) },
  ]) assert.equal(preview([edit]), published.source);
  feed.beginResponse(); add(feed, 'apply_change', 0, JSON.stringify({ source: '☃'.repeat(26_667), tests: published.tests }));
  assert.equal(getFile(feed).content, published.source, 'The limit measures UTF-8 bytes');
});

test('multiple proposals apply in order, while accepted writes replace transient previews', t => {
  const { feed } = fixture(t); feed.begin('turn');
  feed.providerOutput([
    { type: 'function_call', name: 'apply_patch', arguments: JSON.stringify({ edits: [{ path: 'space.js', search: 'before', replace: 'middle' }] }) },
    { type: 'function_call', name: 'apply_patch', arguments: JSON.stringify({ edits: [{ path: 'space.js', search: 'middle', replace: 'after' }] }) },
  ]);
  assert.equal(getFile(feed).content, 'const original = "after";');
  feed.working({ source: 'accepted source', tests: 'accepted tests' });
  assert.equal(getFile(feed).content, 'accepted source');
  assert.equal(getFile(feed).status, 'working');
  feed.beginResponse(); add(feed, 'write_file', 0, '{"path":"space.js","content":"next proposal');
  assert.equal(getFile(feed).content, 'next proposal');
  feed.beginResponse();
  assert.equal(getFile(feed).content, 'accepted source');
});

test('settling or resetting discards drafts, adopts the current revision, and rejects late provider output', t => {
  const { feed, published } = fixture(t); feed.begin('turn');
  add(feed, 'write_file', 0, '{"path":"space.js","content":"a provisional file');
  assert.equal(getFile(feed).content, 'a provisional file');
  feed.published();
  assert.equal(getFile(feed).content, published.source);
  assert.equal(feed.read().data.turnId, undefined);
  delta(feed, 'late ignored text');
  assert.equal(getFile(feed).content, published.source);
  published.sessionId = 'reset-session'; published.revisionId = 2; published.source = 'published after reset';
  feed.published();
  assert.equal(feed.read().data.sessionId, 'reset-session');
  assert.equal(feed.read().data.revisionId, 2);
  assert.equal(getFile(feed).content, published.source);
});

test('coalesced notifications expose only file content, keep subscriber failures isolated, and close idempotently', t => {
  const { feed } = fixture(t); feed.begin('turn');
  const received = []; let closed = 0;
  feed.subscribe(() => { throw Error('Disconnected viewer'); });
  feed.subscribe(event => { received.push(event); event.data.files[0].content = 'changed by viewer'; }, () => closed++);
  add(feed, 'write_file', 0, '{"path":"space.js","content":"');
  for (let i = 0; i < 1000; i++) delta(feed, 'a');
  feed.providerEvent({ type: 'response.created', response: { input: 'PRIVATE_INPUT', headers: { Authorization: 'PRIVATE_KEY' } } });
  feed.providerEvent({ type: 'response.reasoning_text.delta', output_index: 4, delta: 'PRIVATE_REASONING' });
  assert.equal(received.length, 0);
  feed.flush();
  assert.equal(received.length, 1);
  assert.equal(getFile(feed).content, 'a'.repeat(1000));
  assert.doesNotMatch(JSON.stringify(feed.read()), /PRIVATE_/);
  feed.close(); feed.close(); assert.equal(closed, 1);
});

test('the harness streams drafts without persistent writes and rolls back on cancellation', async t => {
  const dataDir = await mkdtemp(join(tmpdir(), 'living-files-persistence-'));
  let entered, release, onEvent;
  const ready = new Promise(resolve => { entered = resolve; });
  const pending = new Promise(resolve => { release = resolve; });
  const service = await createSpaceService({ dataDir, adapter: { keyAvailable: true, model: 'fixture', respond: async args => {
    onEvent = args.onEvent; entered(); await pending;
    return { output: [{ type: 'function_call', name: 'apply_change', call_id: 'apply', arguments: JSON.stringify({ source: blankSeedSource, tests: blankSeedTests, summary: 'Kept intact' }) }] };
  } } });
  t.after(async () => { release(); await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  await service.submit('Make a draft'); await ready;
  const before = await readFile(join(dataDir, 'space.json'), 'utf8');
  onEvent({ type: 'response.output_item.added', output_index: 0, item: { type: 'function_call', name: 'write_file', arguments: '' } });
  onEvent({ type: 'response.function_call_arguments.delta', output_index: 0, delta: '{"path":"space.js","content":"a new draft' });
  assert.equal(getFile(service.files).content, 'a new draft');
  assert.equal(await readFile(join(dataDir, 'space.json'), 'utf8'), before);
  await service.cancel();
  assert.equal(getFile(service.files).content, blankSeedSource, 'Cancel clears the draft before the provider settles');
  onEvent({ type: 'response.function_call_arguments.delta', output_index: 0, delta: ' MUST_NOT_APPEAR' });
  assert.doesNotMatch(getFile(service.files).content, /MUST_NOT_APPEAR/);
  release(); await service.waitForIdle();
  assert.equal(getFile(service.files).content, blankSeedSource);
  assert.equal(service.files.read().data.status, 'published');
  assert.equal(service.store.read().currentRevisionId, 1);
});

test('failed verification exposes the working candidate but restores only the published files at the end', async t => {
  const dataDir = await mkdtemp(join(tmpdir(), 'living-files-verification-'));
  let iteration = 0;
  const candidate = `${blankSeedSource}\n// candidate not approved`;
  const failingTests = 'export function runTests(){return [{name:"Intentional failure",ok:false}]}';
  const service = await createSpaceService({ dataDir, adapter: { keyAvailable: true, model: 'fixture', respond: async () => ({
    output: [{ type: 'function_call', name: 'apply_change', call_id: `apply-${++iteration}`, arguments: JSON.stringify({ source: candidate, tests: failingTests, summary: 'Not approved' }) }],
  }) } });
  t.after(async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  const snapshots = [];
  service.files.subscribe(event => snapshots.push(event.data));
  await service.submit('Try a change'); await service.waitForIdle();
  assert.equal(service.store.read().session.lastOutcome, 'failed');
  assert.ok(snapshots.some(data => data.status === 'working' && data.files[0].content === candidate));
  assert.equal(getFile(service.files).content, blankSeedSource);
  assert.equal(getFile(service.files, 'tests.js').content, blankSeedTests);
  assert.equal(service.files.read().data.status, 'published');
});
