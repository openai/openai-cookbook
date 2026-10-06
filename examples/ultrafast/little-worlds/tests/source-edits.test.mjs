import test from 'node:test';
import assert from 'node:assert/strict';
import { applySourceEdits } from '../server/source-edits.mjs';

const workspace = { source: 'const color = "red"; const size = 3;', tests: 'assert(color === "red")' };
const edit = (search, replace, path = 'space.js') => ({ path, search, replace });

test('exact edits are ordered and retain all untouched source and tests', () => {
  assert.deepEqual(applySourceEdits(workspace, [edit('"red"', '"blue"')]), { ...workspace, source: 'const color = "blue"; const size = 3;' });
  assert.deepEqual(applySourceEdits(workspace, [edit('"red"', '"blue"'), edit('"blue"', '"cyan"'), edit('"red"', '"cyan"', 'tests.js')]), { source: 'const color = "cyan"; const size = 3;', tests: 'assert(color === "cyan")' });
  assert.equal(workspace.source, 'const color = "red"; const size = 3;');
});

test('missing or ambiguous matches reject the complete edit batch without mutation', () => {
  const before = structuredClone(workspace);
  assert.throws(() => applySourceEdits(workspace, [edit('"red"', '"blue"'), edit('missing', 'something')]), /did not match/);
  assert.throws(() => applySourceEdits(workspace, [edit('const', 'let')]), /more than once/);
  assert.deepEqual(workspace, before);
});

test('edits cannot address arbitrary files, use empty searches, or exceed limits', () => {
  assert.throws(() => applySourceEdits(workspace, [edit('red', 'blue', '../.env')]), /Only space.js/);
  assert.throws(() => applySourceEdits(workspace, [edit('', 'blue')]), /nonempty/);
  assert.throws(() => applySourceEdits(workspace, []), /between 1 and 24/);
  assert.throws(() => applySourceEdits(workspace, Array(25).fill(edit('red', 'blue'))), /between 1 and 24/);
  assert.throws(() => applySourceEdits(workspace, [edit('red', '🛰'.repeat(30_000))]), /source limit/);
  assert.throws(() => applySourceEdits({ source: 'x'.repeat(79_999), tests: '' }, [edit('x'.repeat(79_999), 'y'.repeat(80_001))]), /source limit/);
});
