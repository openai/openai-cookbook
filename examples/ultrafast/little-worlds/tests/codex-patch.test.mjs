import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { applyCodexPatch, applyCodexPatchOperations, CODEX_PATCH_GRAMMAR, parseCodexPatch, parseCodexPatchPrefix } from '../server/codex-patch.mjs';

const wrap = (body) => `*** Begin Patch\n${body}\n*** End Patch`;
const workspace = (source = 'foo\nbar\nbaz\nqux\n') => ({ source, tests: 'assert(true);\n' });
const update = (body) => wrap(`*** Update File: space.js\n${body}`);

test('custom-tool grammar is byte-identical to the inspected Codex grammar', () => {
  // core/assets/tools/apply_patch.lark at codex-internal 747129bb21401.
  assert.equal(createHash('sha256').update(CODEX_PATCH_GRAMMAR).digest('hex'), 'd6367f4826ed608c424b0a308f3d6163527df63c22513d089b91863552f8bfeb');
});

// The first five fixtures preserve the examples and expected contents in
// upstream apply-patch/src/file_update_tests.rs (paths adapted to this app).
const fixtures = [
  ['upstream separated chunks', 'foo\nbar\nbaz\nqux\n', '@@\n foo\n-bar\n+BAR\n@@\n baz\n-qux\n+QUX', 'foo\nBAR\nbaz\nQUX\n'],
  ['upstream first line', 'foo\nbar\nbaz\n', '@@\n-foo\n+FOO\n bar\n', 'FOO\nbar\nbaz\n'],
  ['upstream last line', 'foo\nbar\nbaz\n', '@@\n foo\n bar\n-baz\n+BAZ\n', 'foo\nbar\nBAZ\n'],
  ['upstream EOF insertion', 'foo\nbar\nbaz\n', '@@\n+quux\n*** End of File\n', 'foo\nbar\nbaz\nquux\n'],
  ['upstream interleaved changes', 'a\nb\nc\nd\ne\nf\n', '@@\n a\n-b\n+B\n@@\n d\n-e\n+E\n@@\n f\n+g\n*** End of File', 'a\nB\nc\nd\nE\nf\ng\n'],
  ['optional first context marker', 'foo\nbar\nbaz\n', ' foo\n-bar\n+BAR', 'foo\nBAR\nbaz\n'],
  ['named context skips to following lines', 'first\nfoo\nsecond\nfoo\n', '@@ second\n-foo\n+changed', 'first\nfoo\nsecond\nchanged\n'],
  ['repeated lines choose first exact occurrence', 'foo\nrepeat\nfoo\nrepeat\n', '@@\n-foo\n+first', 'first\nrepeat\nfoo\nrepeat\n'],
  ['exact match wins over earlier whitespace match', 'foo  \nrepeat\nfoo\nrepeat\n', '@@\n-foo\n+exact', 'foo  \nrepeat\nexact\nrepeat\n'],
  ['trailing whitespace match', 'foo\nbar  \nbaz\n', '@@\n-bar\n+BAR', 'foo\nBAR\nbaz\n'],
  ['trim both sides match', 'foo\n  bar  \nbaz\n', '@@\n-bar\n+BAR', 'foo\nBAR\nbaz\n'],
  ['Unicode punctuation and spaces match', 'foo\n“hello”\u00a0—\u2009‘there’\nbaz\n', '@@\n-"hello" - \'there\'\n+changed', 'foo\nchanged\nbaz\n'],
  ['Rust Unicode whitespace semantics include NEL', 'foo\n\u0085bar\u0085\nbaz\n', '@@\n-bar\n+BAR', 'foo\nBAR\nbaz\n'],
  ['missing terminal newline is supplied', 'foo\nbar\nbaz', '@@\n-bar\n+BAR', 'foo\nBAR\nbaz\n'],
  ['CRLF source follows default Codex normalization', 'foo\r\nbar\r\nbaz\r\n', '@@\n foo\n-bar\n+BAR', 'foo\nBAR\nbaz\r\n'],
  ['EOF chooses last repeated occurrence', 'foo\nrepeat\nfoo\n', '@@\n-foo\n+last\n*** End of File', 'foo\nrepeat\nlast\n'],
  ['trailing empty context retries without sentinel', 'foo\nbar\nbaz\n', '@@\n-baz\n+BAZ\n ', 'foo\nbar\nBAZ\n'],
  ['pure insertion appends even with a named context', 'foo\nbar\nbaz\n', '@@ foo\n+new', 'foo\nbar\nbaz\nnew\n'],
];

for (const [name, source, body, expected] of fixtures) test(`Codex patch parity: ${name}`, () => {
  assert.deepEqual(applyCodexPatch(workspace(source), update(body)), { ...workspace(), source: expected });
});

test('Add File supports full writes to existing source and tests with a terminal newline', () => {
  assert.deepEqual(applyCodexPatch(workspace(), wrap('*** Add File: space.js\n+export const value = 2;\n+\n*** Add File: tests.js\n+assert(value === 2);')), {
    source: 'export const value = 2;\n\n', tests: 'assert(value === 2);\n',
  });
});

test('repeated file blocks apply sequentially and reset the location search', () => {
  const input = wrap('*** Update File: space.js\n@@\n-baz\n+BAZ\n*** Update File: space.js\n@@\n-foo\n+FOO\n*** Update File: space.js\n@@\n-BAZ\n+last');
  assert.equal(applyCodexPatch(workspace(), input).source, 'FOO\nbar\nlast\nqux\n');
});

test('multiple insertion chunks keep patch order at the same insertion position', () => {
  assert.equal(applyCodexPatch(workspace(), update('@@\n+one\n@@\n+two')).source, 'foo\nbar\nbaz\nqux\none\ntwo\n');
});

test('delete and recreate, or move and restore, retain both required files', () => {
  assert.equal(applyCodexPatch(workspace(), wrap('*** Delete File: space.js\n*** Add File: space.js\n+export const value = 2;')).source, 'export const value = 2;\n');
  assert.deepEqual(applyCodexPatch(workspace(), wrap('*** Update File: space.js\n*** Move to: tests.js\n@@\n-foo\n+FOO\n*** Add File: space.js\n+export const value = 2;')), {
    source: 'export const value = 2;\n', tests: 'FOO\nbar\nbaz\nqux\n',
  });
  assert.throws(() => applyCodexPatch(workspace(), wrap('*** Delete File: space.js')), /retain space.js/);
  assert.throws(() => applyCodexPatch(workspace(), wrap('*** Update File: space.js\n*** Move to: tests.js\n@@\n-foo\n+FOO')), /retain space.js/);
});

test('missing files cannot be updated or deleted after a preceding delete', () => {
  assert.throws(() => applyCodexPatch(workspace(), wrap('*** Delete File: space.js\n*** Update File: space.js\n@@\n+something new')), /retain space.js/);
  assert.throws(() => applyCodexPatch(workspace(), wrap('*** Delete File: space.js\n*** Delete File: space.js\n*** Add File: space.js\n+some replacement')), /delete missing file/);
});

test('failed matching, EOF matching, and oversized changes are atomic', () => {
  const original = Object.freeze(workspace());
  const changedThenFailed = wrap('*** Update File: tests.js\n@@\n-assert(true);\n+assert(false);\n*** Update File: space.js\n@@\n-missing line\n+replacement');
  assert.throws(() => applyCodexPatch(original, changedThenFailed), /Failed to find expected lines/);
  assert.throws(() => applyCodexPatch(original, update('@@\n-foo\n+changed\n*** End of File')), /Failed to find expected lines/);
  assert.throws(() => applyCodexPatch(original, wrap(`*** Add File: space.js\n+${'x'.repeat(80_000)}`)), /80,000 bytes/);
  assert.deepEqual(original, workspace());
});

test('the complete parser accepts Codex marker whitespace, CRLF patches, and literal heredocs', () => {
  const plain = update('@@\n-bar\n+BAR');
  const expected = applyCodexPatch(workspace(), plain);
  for (const input of [plain.replaceAll('\n', '\r\n'), `  ${plain.replace('*** End Patch', '  *** End Patch  ')}\n`, `<<EOF\n${plain}\nEOF\n`, `<<'EOF'\n${plain}\nEOF\n`, `<<"EOF"\n${plain}\nEOF\n`]) {
    assert.deepEqual(applyCodexPatch(workspace(), input), expected);
  }
});

test('empty patch parses upstream-style but application requires a file operation', () => {
  assert.deepEqual(parseCodexPatch('*** Begin Patch\n*** End Patch'), []);
  assert.throws(() => applyCodexPatch(workspace(), '*** Begin Patch\n*** End Patch'), /No files were modified/);
  assert.deepEqual(applyCodexPatchOperations(workspace(), [], { preview: true }), workspace());
});

test('all file operation paths and move destinations are literal and contained', () => {
  for (const path of ['../space.js', './space.js', '/tmp/space.js', 'space.js/../tests.js', 'SPACE.JS', '.env', 'space.js\0', 'space.js\\..\\tests.js']) {
    for (const input of [wrap(`*** Add File: ${path}\n+export const value = 2;`), wrap(`*** Delete File: ${path}`), wrap(`*** Update File: ${path}\n@@\n-foo\n+FOO`), wrap(`*** Update File: space.js\n*** Move to: ${path}\n@@\n-foo\n+FOO`)]) assert.throws(() => applyCodexPatch(workspace(), input), /Only space.js and tests.js/);
  }
  assert.throws(() => parseCodexPatch(wrap('*** Environment ID: host\n*** Add File: space.js\n+export const value = 2;')), /not a valid file/);
});

test('malformed and incomplete patch syntax does not reach application', () => {
  for (const input of ['@@\n-bar\n+BAR', '*** Begin Patch\n*** Add File: space.js\n+export const value = 2;', `${update('@@\n-bar\n+BAR')}\ntrailing text`, wrap('*** Update File: space.js'), update('@@'), update('@@\n@@\n+value'), update('@@\n+value\n*** End of File\n+another'), wrap('*** Add File: space.js\nnot prefixed'), wrap('*** Update File: space.js\n*** Move to: tests.js')]) assert.throws(() => applyCodexPatch(workspace(), input), /patch|hunk|line/i);
});

test('file limits use UTF-8 bytes, and total patch/operation/chunk limits are bounded', () => {
  assert.equal(applyCodexPatch(workspace(), wrap(`*** Add File: space.js\n+${'x'.repeat(79_999)}`)).source.length, 80_000);
  assert.throws(() => applyCodexPatch(workspace(), wrap('*** Add File: space.js\n+short')), /between 10/);
  assert.throws(() => applyCodexPatch(workspace(), wrap(`*** Add File: space.js\n+${'🛰'.repeat(20_000)}`)), /80,000 bytes/);
  assert.throws(() => parseCodexPatch('x'.repeat(512_001)), /512,000-byte/);
  assert.throws(() => parseCodexPatch(wrap('*** Add File: space.js\n+value\n'.repeat(65).trimEnd())), /64 file operations/);
  assert.throws(() => parseCodexPatch(update('@@\n+line\n'.repeat(257).trimEnd())), /256 update chunks/);
});

test('ambiguous pathological matching is bounded without mutating the workspace', () => {
  const original = Object.freeze(workspace(`${'a\n'.repeat(39_999)}z\n`));
  assert.throws(() => applyCodexPatch(original, update(`@@\n${'-a\n'.repeat(500)}-b\n+replacement`)), /matching exceeded the work limit/);
  assert.equal(original.source.length, 80_000);
});

test('prefix parser shares operation shapes and retains an incomplete last line separately', () => {
  const prefix = '*** Begin Patch\n*** Update File: space.js\n@@\n-bar\n+BAR\n*** Update File: tests.js\n@@\n-assert(true);\n+assert(fal';
  const parsed = parseCodexPatchPrefix(prefix);
  assert.equal(parsed.pendingLine, '+assert(fal');
  assert.equal(parsed.ended, false);
  assert.equal(parsed.operations.length, 2);
  assert.equal(parsed.operations[0].type, 'update');
  assert.deepEqual(parsed.operations[0].chunks[0], { context: null, oldLines: ['bar'], newLines: ['BAR'], contextLineIndices: [], isEndOfFile: false });
  assert.equal(applyCodexPatchOperations(workspace(), parsed.operations, { preview: true }).source, 'foo\nBAR\nbaz\nqux\n');
  assert.equal(workspace().tests, 'assert(true);\n');
});

test('inert prefix projection accepts short Add File and unfinished chunks, while execution does not', () => {
  const parsed = parseCodexPatchPrefix('*** Begin Patch\n*** Add File: space.js\n+x\n*** Update File: tests.js\n@@\n');
  assert.equal(applyCodexPatchOperations(workspace(), parsed.operations, { preview: true }).source, 'x\n');
  assert.throws(() => applyCodexPatchOperations(workspace(), parsed.operations), /hunk does not contain/);
  assert.throws(() => parseCodexPatch('*** Begin Patch\n*** Add File: space.js\n+x\n'), /last line/);
  assert.deepEqual(parseCodexPatchPrefix('*** Beg'), { operations: [], ended: false, pendingLine: '*** Beg' });
});
