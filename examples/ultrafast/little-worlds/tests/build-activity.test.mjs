import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { transform } from 'esbuild';

const { code } = await transform(await readFile(new URL('../src/build-activity.ts', import.meta.url), 'utf8'), { loader: 'ts', format: 'esm' });
const { mergeActivityEvents, parseActivityArguments, activityCode, ACTIVITY_MAX_ENTRIES, ACTIVITY_MAX_FIELD, ACTIVITY_MAX_CONTENT } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

const time = '2026-09-21T12:00:00.000Z';
const event = (entryId, properties = {}, overrides = {}) => ({ id: '1', type: 'activity.entry', time, turnId: 'turn-1', title: 'Writing the page', data: { entryId, kind: 'tool', tool: 'apply_change', status: 'running', ...properties }, ...overrides });
const entry = (tool, arguments_) => ({ id: 'tool-1', kind: 'tool', time, title: tool, tool, arguments: arguments_ });

test('cumulative updates preserve row order and time without appending duplicate text', () => {
  const initial = mergeActivityEvents([], [event('first', { arguments: '{"source":"a' }), event('second', { kind: 'message', text: 'Hello' })]);
  const updated = mergeActivityEvents(initial, [event('first', { arguments: '{"source":"ab"}', status: 'completed', durationMs: 450 }, { id: '3', time: '2026-09-21T12:01:00.000Z' })]);
  assert.deepEqual(updated.map(value => value.id), ['first', 'second']);
  assert.equal(updated[0].time, time);
  assert.equal(updated[0].arguments, '{"source":"ab"}');
  assert.equal(updated[0].status, 'completed');
  assert.equal(updated[0].durationMs, 450);
  assert.equal(initial[0].arguments, '{"source":"a', 'prior snapshots stay immutable');
  assert.equal(initial[1], updated[1], 'untouched rows keep identity');
  assert.equal(mergeActivityEvents(updated, [event('first', { arguments: '{"source":"ab"}', status: 'completed', durationMs: 450 })]), updated, 'an identical replay does not render again');
});

test('connection replay resets previous entries even when transport ids repeat or decrease', () => {
  const previous = mergeActivityEvents([], [event('old-account', { arguments: 'private' }, { id: '999' })]);
  const next = mergeActivityEvents(previous, [
    { id: '0', type: 'activity.reset', data: { reason: 'replay' } },
    event('current', { arguments: 'current' }, { id: '1' }),
    event('current', { arguments: 'current complete' }, { id: '2' }),
  ]);
  assert.equal(next.length, 1);
  assert.equal(next[0].id, 'current');
  assert.equal(next[0].arguments, 'current complete');
  assert.deepEqual(mergeActivityEvents(next, [{ type: 'activity.reset' }]), []);
});

test('numeric output telemetry survives replay without mutating or duplicating the model row', () => {
  const throughput = { tokens: 1400, durationMs: 2000, rate: 900, sampledAt: 50_000, lastDeltaAt: 49_980, state: 'streaming', estimated: true };
  const incoming = event('model', { kind: 'event', eventType: 'model.started', throughput });
  const current = mergeActivityEvents([], [incoming]);
  assert.deepEqual(current[0].throughput, throughput);
  assert.equal(mergeActivityEvents(current, [structuredClone(incoming)]), current);
  const updated = mergeActivityEvents(current, [event('model', { kind: 'event', eventType: 'model.started', throughput: { ...throughput, rate: 1000 } })]);
  assert.equal(updated.length, 1);
  assert.equal(updated[0].throughput.rate, 1000);
  assert.equal(current[0].throughput.rate, 900);
  for (const corrupt of [{ ...throughput, rate: Infinity }, { ...throughput, tokens: -1 }, { ...throughput, tokens: 1e100 }, { ...throughput, state: 'injected' }, { ...throughput, estimated: false }, { ...throughput, lastDeltaAt: 'now' }]) {
    assert.equal(mergeActivityEvents([], [event('bad', { eventType: 'model.started', throughput: corrupt })])[0].throughput, undefined);
  }
});

test('malformed events and unexpected values cannot become activity rows', () => {
  const current = mergeActivityEvents([], [event('valid')]);
  assert.equal(mergeActivityEvents(current, [null, [], 'text', {}, { type: 'activity.entry', data: null }, event('', {}), event('bad', { kind: 'reasoning' }), { type: 'revision.published' }]), current);
  const [normalized] = mergeActivityEvents([], [event('odd', { status: 'unexpected', durationMs: Infinity, text: { injected: true }, result: '<script>not executed</script>' })]);
  assert.equal(normalized.status, undefined);
  assert.equal(normalized.durationMs, undefined);
  assert.equal(normalized.text, undefined);
  assert.equal(normalized.result, '<script>not executed</script>');
});

test('entry count and total text are bounded, retaining the newest activity', () => {
  const many = mergeActivityEvents([], Array.from({ length: ACTIVITY_MAX_ENTRIES + 10 }, (_, index) => event(`e${index}`)));
  assert.equal(many.length, ACTIVITY_MAX_ENTRIES);
  assert.equal(many[0].id, 'e10');
  const full = 'a'.repeat(ACTIVITY_MAX_FIELD);
  const large = mergeActivityEvents([], Array.from({ length: 20 }, (_, index) => event(`e${index}`, { text: full, arguments: full, result: full })));
  assert.ok(large.reduce((total, row) => total + row.text.length + row.arguments.length + row.result.length, 0) <= ACTIVITY_MAX_CONTENT);
  assert.equal(large.at(-1).id, 'e19');
});

test('oversized fields are marked truncated without splitting Unicode characters', () => {
  const oversized = `${'a'.repeat(ACTIVITY_MAX_FIELD - 1)}🌱end`;
  const [row] = mergeActivityEvents([], [event('large', { arguments: oversized })]);
  assert.equal(row.arguments, 'a'.repeat(ACTIVITY_MAX_FIELD - 1));
  assert.equal(row.truncated, true);
});

test('partial JSON decodes quoted code, newlines, tabs and Unicode at every split', () => {
  const source = 'export function render() {\n  return "a \\ path\\n🌱 snow 雪";\n}\t';
  const raw = JSON.stringify({ source, tests: 'test("works", () => true);', summary: 'Done' });
  for (let end = 0; end <= raw.length; end++) {
    const blocks = activityCode(entry('apply_change', raw.slice(0, end)));
    const code = blocks.find(block => block.path === 'space.js')?.code;
    if (code !== undefined) assert.ok(source.startsWith(code), `prefix ${end} decoded a fabricated character`);
  }
  assert.deepEqual(activityCode(entry('apply_change', raw)), [{ path: 'space.js', code: source }, { path: 'tests.js', code: 'test("works", () => true);' }]);
});

test('incomplete JSON escapes never flash escape bytes or half a surrogate pair', () => {
  const cases = [
    ['{"source":"a\\', 'a'],
    ['{"source":"a\\n', 'a\n'],
    ['{"source":"a\\u', 'a'],
    ['{"source":"a\\u2', 'a'],
    ['{"source":"a\\u260', 'a'],
    ['{"source":"a\\u2603', 'a☃'],
    ['{"source":"a\\uD83C', 'a'],
    ['{"source":"a\\uD83C\\uD', 'a'],
    ['{"source":"a\\uD83C\\uDF31', 'a🌱'],
  ];
  for (const [raw, expected] of cases) assert.equal(activityCode(entry('apply_change', raw))[0].code, expected, raw);
});

test('nested or quoted source keys are never mistaken for the top-level source field', () => {
  const raw = JSON.stringify({ metadata: { source: 'wrong' }, source: 'const text = "source: \\"wrong\\"";', tests: '' });
  assert.equal(activityCode(entry('apply_change', raw))[0].code, JSON.parse(raw).source);
  assert.deepEqual(activityCode(entry('apply_change', '{"metadata":{"source":"wrong"}')), []);
  assert.deepEqual(activityCode(entry('apply_change', '{"source":42}')), []);
  assert.deepEqual(activityCode(entry('apply_change', '{"source":"bad\\q"}')), []);
  assert.deepEqual(activityCode(entry('apply_change', '{"source":"code"} trailing')), []);
});

test('write_file and streaming apply_patch expose only actual content or replacements', () => {
  assert.deepEqual(activityCode(entry('write_file', '{"path":"tests.js","content":"assert.equal(1, 1);"}')), [{ path: 'tests.js', code: 'assert.equal(1, 1);' }]);
  const partial = '{"edits":[{"path":"space.js","search":"old","replace":"new"},{"path":"tests.js","search":"no","replace":"yes\\n';
  assert.deepEqual(activityCode(entry('apply_patch', partial)), [
    { path: 'space.js · edit 1', code: 'new' }, { path: 'tests.js · edit 2', code: 'yes\n' },
  ]);
  assert.deepEqual(activityCode(entry('inspect_space', '{"source":"not a write"}')), []);
});

test('custom patches remain raw text while legacy function patches retain their source blocks', () => {
  const patch = '*** Begin Patch\n*** Update File: space.js\n@@\n-const label = "old";\n+const label = "new";\n*** End Patch';
  const [row] = mergeActivityEvents([], [event('patch', { tool: 'apply_patch', arguments: patch, inputFormat: 'patch' })]);
  assert.equal(row.arguments, patch);
  assert.equal(row.inputFormat, 'patch');
  assert.deepEqual(activityCode(row), [], 'The panel shows the raw patch once, not a second generated-source view');
  assert.deepEqual(activityCode(entry('apply_patch', '{"edits":[{"path":"space.js","search":"old","replace":"new"}]}')), [{ path: 'space.js · edit 1', code: 'new' }]);
  const [unrecognized] = mergeActivityEvents([], [event('unknown', { inputFormat: 'untrusted' })]);
  assert.equal(unrecognized.inputFormat, undefined);
});

test('JSON parsing is depth and size bounded and does not modify object prototypes', () => {
  assert.equal(parseActivityArguments('x'.repeat(ACTIVITY_MAX_FIELD + 1)), null);
  assert.equal(parseActivityArguments('{"a":'.repeat(18) + '0' + '}'.repeat(18)), null);
  const parsed = parseActivityArguments('{"__proto__":{"polluted":true},"source":"safe"}');
  assert.equal(Object.getPrototypeOf(parsed), null);
  assert.equal({}.polluted, undefined);
  assert.equal(parsed.source, 'safe');
});
