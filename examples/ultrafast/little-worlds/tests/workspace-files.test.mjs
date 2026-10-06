import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { transform } from 'esbuild';

const { code } = await transform(await readFile(new URL('../src/workspace-files.ts', import.meta.url), 'utf8'), { loader: 'ts', format: 'esm' });
const { parseWorkspaceFilesEvent, mergeWorkspaceFilesEvents, changedFileLines, changedFileRanges, WORKSPACE_FILE_MAX_BYTES } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

const time = '2026-09-21T12:00:00.000Z';
const file = (path, content = '', overrides = {}) => ({ path, content, language: 'javascript', status: 'published', updatedAt: time, ...overrides });
const event = (overrides = {}) => ({ type: 'files.snapshot', data: { sessionId: 'session-1', revisionId: 4, status: 'published', files: [file('space.js', 'export function render() {}'), file('tests.js', 'assert.ok(true);')], ...overrides } });

test('snapshots contain exactly the two generated files in a stable tree order', () => {
  const input = event({ files: [file('tests.js', 'tests'), file('space.js', 'source', { extra: 'discarded' })], extra: 'discarded' });
  const snapshot = parseWorkspaceFilesEvent(input);
  assert.deepEqual(snapshot, {
    sessionId: 'session-1', revisionId: 4, status: 'published',
    files: [file('space.js', 'source'), file('tests.js', 'tests')],
  });
  assert.notEqual(snapshot.files[0], input.data.files[1]);
});

test('unexpected paths, missing files, and duplicate paths cannot enter the file tree', () => {
  for (const path of ['.env', '../space.js', '/space.js', 'src/space.js', 'SPACE.JS', 'README.md', '', null]) {
    assert.equal(parseWorkspaceFilesEvent(event({ files: [file(path), file('tests.js')] })), null, `reject ${String(path)}`);
  }
  for (const files of [[], [file('space.js')], [file('space.js'), file('space.js')], [file('tests.js'), file('tests.js')], [file('space.js'), file('tests.js'), file('.env')]]) {
    assert.equal(parseWorkspaceFilesEvent(event({ files })), null);
  }
});

test('the content limit is 80,000 UTF-8 bytes and accepts the exact boundary', () => {
  assert.equal(WORKSPACE_FILE_MAX_BYTES, 80_000);
  for (const content of ['a'.repeat(80_000), 'é'.repeat(40_000), '🌱'.repeat(20_000)]) {
    assert.equal(Buffer.byteLength(content, 'utf8'), 80_000);
    assert.equal(parseWorkspaceFilesEvent(event({ files: [file('space.js', content), file('tests.js')] })).files[0].content, content);
    assert.equal(parseWorkspaceFilesEvent(event({ files: [file('space.js', content + 'a'), file('tests.js')] })), null);
  }
  const oversizedUnicode = '🌱'.repeat(20_001);
  assert.ok(oversizedUnicode.length < 80_000, 'character count alone would accept this payload');
  assert.equal(parseWorkspaceFilesEvent(event({ files: [file('space.js'), file('tests.js', oversizedUnicode)] })), null);
});

test('malformed envelopes and snapshot identity fields are rejected', () => {
  for (const input of [null, [], 'files.snapshot', {}, { type: 'activity.entry', data: event().data }, { type: 'files.snapshot', data: null }, { type: 'files.snapshot', data: [] }]) {
    assert.equal(parseWorkspaceFilesEvent(input), null);
  }
  for (const overrides of [
    { sessionId: '' }, { sessionId: 12 }, { sessionId: 's'.repeat(257) },
    { revisionId: 0 }, { revisionId: -1 }, { revisionId: 1.5 }, { revisionId: Infinity }, { revisionId: Number.MAX_SAFE_INTEGER + 1 }, { revisionId: '4' },
    { turnId: '' }, { turnId: null }, { turnId: [] }, { turnId: 't'.repeat(257) },
    { status: 'complete' }, { status: null }, { files: null }, { files: {} },
  ]) assert.equal(parseWorkspaceFilesEvent(event(overrides)), null, JSON.stringify(overrides));
});

test('malformed individual files reject the whole snapshot instead of hiding one file', () => {
  for (const overrides of [
    { content: null }, { content: {} }, { content: ['source'] }, { language: 'html' },
    { status: 'complete' }, { status: null }, { updatedAt: null }, { updatedAt: '' },
    { updatedAt: 'not a date' }, { updatedAt: time + ' '.repeat(81) },
  ]) {
    assert.equal(parseWorkspaceFilesEvent(event({ files: [file('space.js'), file('tests.js', '', overrides)] })), null, JSON.stringify(overrides));
  }
  assert.equal(parseWorkspaceFilesEvent(event({ files: [file('space.js'), null] })), null);
});

test('new sessions and reset snapshots replace both files without retaining previous content', () => {
  const prior = parseWorkspaceFilesEvent(event({ turnId: 'old-turn' }));
  Object.freeze(prior.files[0]);
  Object.freeze(prior.files[1]);
  Object.freeze(prior.files);
  Object.freeze(prior);
  const reset = event({ sessionId: 'session-2', revisionId: 1, files: [file('space.js', 'fresh source'), file('tests.js', '')] });
  const next = mergeWorkspaceFilesEvents(prior, [{ type: 'activity.reset' }, reset]);
  assert.equal(next.sessionId, 'session-2');
  assert.equal(next.revisionId, 1);
  assert.equal(next.turnId, undefined);
  assert.deepEqual(next.files.map(value => value.content), ['fresh source', '']);
  assert.deepEqual(prior.files.map(value => value.content), ['export function render() {}', 'assert.ok(true);']);
  assert.notEqual(next.files, prior.files);
  assert.notEqual(next.files[0], reset.data.files[0]);
});

test('a restore or reset can publish a lower revision within the same session', () => {
  const prior = parseWorkspaceFilesEvent(event({ revisionId: 12, turnId: 'turn-12' }));
  const next = mergeWorkspaceFilesEvents(prior, [event({ revisionId: 1, files: [file('space.js', 'restored'), file('tests.js', '')] })]);
  assert.equal(next.sessionId, prior.sessionId);
  assert.equal(next.revisionId, 1);
  assert.equal(next.turnId, undefined);
  assert.deepEqual(next.files.map(value => value.content), ['restored', '']);
  assert.equal(prior.revisionId, 12);
});

test('identical replay preserves snapshot identity even when file order differs', () => {
  const initial = event({ status: 'streaming', turnId: 'turn-1', files: [file('space.js', 'partial', { status: 'streaming' }), file('tests.js')] });
  const current = mergeWorkspaceFilesEvents(null, [initial]);
  const replay = { ...initial, data: { ...initial.data, files: [...initial.data.files].reverse() } };
  assert.equal(mergeWorkspaceFilesEvents(current, [replay]), current);
  assert.equal(mergeWorkspaceFilesEvents(current, [null, { type: 'activity.reset' }, event({ files: [] })]), current);
  assert.equal(mergeWorkspaceFilesEvents(null, [null]), null);
});

test('same-revision streaming updates replace content, metadata, and statuses immutably', () => {
  const initial = event({ status: 'streaming', turnId: 'turn-1', files: [file('space.js', 'a', { status: 'streaming' }), file('tests.js', '')] });
  const prior = mergeWorkspaceFilesEvents(null, [initial]);
  const nextTime = '2026-09-21T12:00:01.000Z';
  const next = mergeWorkspaceFilesEvents(prior, [event({ status: 'working', turnId: 'turn-1', files: [file('space.js', 'ab', { status: 'working', updatedAt: nextTime }), file('tests.js', 'new tests')] })]);
  assert.notEqual(next, prior);
  assert.equal(next.revisionId, prior.revisionId);
  assert.equal(next.status, 'working');
  assert.equal(next.files[0].status, 'working');
  assert.equal(next.files[0].updatedAt, nextTime);
  assert.deepEqual(next.files.map(value => value.content), ['ab', 'new tests']);
  assert.equal(prior.files[0].content, 'a');
  assert.equal(initial.data.files[0].content, 'a');
});

test('batched events use the last valid snapshot without mixing files across snapshots', () => {
  const next = mergeWorkspaceFilesEvents(null, [
    event(), event({ revisionId: 5, files: [file('space.js', 'five'), file('tests.js', '')] }),
    event({ revisionId: 6, files: [file('space.js', 'invalid partial')] }),
  ]);
  assert.equal(next.revisionId, 5);
  assert.deepEqual(next.files.map(value => value.content), ['five', '']);
});

test('changed lines locate appended text and newly appended lines', () => {
  assert.deepEqual(changedFileLines('one\ntwo', 'one\ntwo more'), { start: 2, end: 2 });
  assert.deepEqual(changedFileLines('one\n', 'one\ntwo\nthree'), { start: 2, end: 3 });
  assert.deepEqual(changedFileLines('', 'first\nsecond'), { start: 1, end: 2 });
});

test('changed lines locate a middle patch while leaving the unchanged suffix out', () => {
  assert.deepEqual(changedFileLines('header\nold\nfooter\n', 'header\nnew one\nnew two\nfooter\n'), { start: 2, end: 3 });
  assert.deepEqual(changedFileLines('one\nsame value\nthree', 'one\nsame VALUE\nthree'), { start: 2, end: 2 });
});

test('pure deletions keep a valid anchor in the remaining file', () => {
  assert.deepEqual(changedFileLines('one\ntwo\nthree', 'one\nthree'), { start: 2, end: 2 });
  assert.deepEqual(changedFileLines('one\ntwo\nthree', 'one\ntwo'), { start: 2, end: 2 });
  assert.deepEqual(changedFileLines('everything', ''), { start: 1, end: 1 });
});

test('unchanged files have no changed range', () => {
  assert.equal(changedFileLines('', ''), null);
  assert.equal(changedFileLines('one\n🌱\n', 'one\n🌱\n'), null);
});

test('changed character ranges follow only newly streamed text', () => {
  assert.deepEqual(changedFileRanges('one\ntwo', 'one\ntwo more\nthree'), [{ start: 7, end: 18 }]);
  assert.deepEqual(changedFileRanges('', 'first\nsecond'), [{ start: 0, end: 12 }]);
  assert.deepEqual(changedFileRanges('one\n🌱\n', 'one\n🌱\n'), []);
});

test('a middle edit on a long line highlights the edited value rather than the whole line', () => {
  const prefix = `const scene = { ${'padding: true, '.repeat(400)}`;
  const suffix = `, ${'border: false, '.repeat(400)} }`;
  const previous = `${prefix}color: 'red'${suffix}`;
  const current = `${prefix}color: 'blue'${suffix}`;
  const start = current.indexOf('blue');
  assert.deepEqual(changedFileRanges(previous, current), [{ start, end: start + 4 }]);
});

test('separate patches leave unchanged middle lines unhighlighted', () => {
  const previous = "const color = 'red';\nrenderUnchanged();\nconst speed = 1;\n";
  const current = "const color = 'blue';\nrenderUnchanged();\nconst speed = 3;\n";
  assert.deepEqual(changedFileRanges(previous, current), [
    { start: current.indexOf('blue'), end: current.indexOf('blue') + 4 },
    { start: current.indexOf('3'), end: current.indexOf('3') + 1 },
  ]);
});

test('deletions retain zero-width anchors in the new file', () => {
  assert.deepEqual(changedFileRanges('one\ntwo\nthree', 'one\nthree'), [{ start: 4, end: 4 }]);
  assert.deepEqual(changedFileRanges('one\ntwo\nthree', 'one\ntwo'), [{ start: 7, end: 7 }]);
  assert.deepEqual(changedFileRanges('everything', ''), [{ start: 0, end: 0 }]);
  assert.deepEqual(changedFileRanges('remove();\nkeep();\nold();', 'keep();\nnew();'), [
    { start: 0, end: 0 }, { start: 8, end: 11 },
  ]);
  assert.deepEqual(changedFileRanges('one\ntwo\nthree\nsame\nold', 'one\nthree\nsame\nnew'), [
    { start: 4, end: 4 }, { start: 15, end: 18 },
  ]);
});

test('changed offsets never split a Unicode surrogate pair', () => {
  for (const [previous, current, expected] of [
    ['a🌱b', 'a🌲b', [{ start: 1, end: 3 }]],
    ['🌱unchanged\nold😀end', '🌱unchanged\nnew😃end', [{ start: 12, end: 17 }]],
    ['before', 'before🌱', [{ start: 6, end: 8 }]],
    ['a\ud83cb', 'a🌱b', [{ start: 1, end: 3 }]],
  ]) {
    const actual = changedFileRanges(previous, current);
    assert.deepEqual(actual, expected);
    for (const range of actual) {
      assert.ok(range.start >= 0 && range.start <= range.end && range.end <= current.length);
      assert.equal(current.slice(range.start, range.end).isWellFormed(), true);
    }
  }
});

test('repeated unchanged lines still separate edits', () => {
  const previous = 'start\noldOne\n}\n}\noldTwo\nend';
  const current = 'start\nnewOne\n}\n}\nnewTwo\nend';
  assert.deepEqual(changedFileRanges(previous, current), [
    { start: 6, end: 9 }, { start: 17, end: 20 },
  ]);
});

test('large streaming files use correct offsets across successive appends', () => {
  const body = 'const x = 1;\n'.repeat(6_000);
  let current = body;
  for (const chunk of ['function update() {\n', '  move(1);\n', '  paint("🌱");\n', '}\n']) {
    const previous = current;
    current += chunk;
    assert.deepEqual(changedFileRanges(previous, current), [{ start: previous.length, end: current.length }]);
  }
  assert.ok(current.length < WORKSPACE_FILE_MAX_BYTES);
});

test('large rewrites preserve unchanged unique anchors when the edit bound is exceeded', () => {
  const previous = Array.from({ length: 250 }, (_, index) => `old${index}\nkeep${index}\n`).join('');
  const current = previous.replaceAll('old', 'new');
  const ranges = changedFileRanges(previous, current);
  assert.equal(ranges.length, 250);
  for (const range of ranges) assert.equal(current.slice(range.start, range.end), 'new');
});

test('an entirely rewritten 80 KB file stays bounded and returns valid ranges', () => {
  const previous = 'old\n'.repeat(20_000);
  const current = 'new\n'.repeat(20_000);
  assert.deepEqual(changedFileRanges(previous, current), [{ start: 0, end: current.length - 1 }]);
});
