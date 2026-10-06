import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/activity-history.ts', import.meta.url).pathname],
  bundle: true, write: false, platform: 'node', format: 'esm',
});
const { savedActivityForTurn } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const time = '2026-09-21T12:00:00.000Z';
const turn = { id: 'old-turn', message: 'Make the tile blue', startedAt: time, status: 'completed' };
const event = (id, type, overrides = {}) => ({ id, type, turnId: turn.id, time, title: type, ...overrides });

test('saved activity recovers only matching lifecycle facts and synthesizes the preserved request', () => {
  const result = savedActivityForTurn(turn, [
    event('other', 'turn.started', { turnId: 'another-turn', detail: 'Private other request' }),
    event('state', 'space.updated', { detail: 'Unrelated live state' }),
    event('inspect', 'tool.completed', { data: { tool: 'inspect_space', revisionId: 9 } }),
    event('finished', 'turn.completed', { durationMs: 3500 }),
  ]);
  assert.equal(result.hasSavedEvents, true);
  assert.equal(result.entries.length, 3);
  assert.deepEqual(result.entries.map(entry => entry.id), ['saved-request:old-turn', 'saved-event:inspect', 'saved-event:finished']);
  assert.equal(result.entries[0].text, turn.message);
  assert.equal(result.entries[0].time, turn.startedAt);
  assert.equal(result.entries[2].durationMs, 3500);
  assert.deepEqual(JSON.parse(result.entries[1].result), { tool: 'inspect_space', revisionId: 9 });
});

test('saved projection excludes source, HTML, raw inputs, nested secrets, and unrecognized output fields', () => {
  const result = savedActivityForTurn(turn, [event('preview', 'draft.preview', {
    title: 'Preview sk-secret123', detail: 'Token Bearer private-token',
    data: {
      html: '<script>unsafe()</script>', source: 'private source', apiKey: 'secret', headers: { authorization: 'secret' },
      sourceCharacters: 1200, tool: 'verify_workspace',
      checks: [{ name: 'render', ok: true, message: 'Checked sk-anotherSecret', source: 'hidden', headers: { authorization: 'hidden' } }],
      files: ['space.js', { apiKey: 'nested secret' }],
      model: { apiKey: 'nested secret' },
    },
  })]);
  const preview = result.entries[1];
  assert.equal(preview.title, 'Preview [redacted]');
  assert.equal(preview.text, 'Token Bearer [redacted]');
  assert.deepEqual(JSON.parse(preview.result), {
    tool: 'verify_workspace', sourceCharacters: 1200,
    files: ['space.js'], checks: [{ name: 'render', ok: true, message: 'Checked [redacted]' }],
  });
  assert.equal(preview.arguments, undefined, 'persisted lifecycle events cannot fabricate generated code');
  assert.doesNotMatch(JSON.stringify(result), /private source|unsafe\(\)|nested secret|anotherSecret|secret123|private-token/);
});

test('saved lifecycle spans resolve their status when tools and the request finish', () => {
  const result = savedActivityForTurn(turn, [
    event('request', 'turn.started', { detail: turn.message }),
    event('model', 'model.started'),
    event('model-end', 'model.completed'),
    event('check', 'tool.started', { data: { tool: 'verify_workspace' } }),
    event('check-end', 'tool.failed', { data: { tool: 'verify_workspace' } }),
    event('publish', 'tool.started', { data: { tool: 'publish_revision' } }),
    event('done', 'turn.completed'),
  ]);
  assert.equal(result.entries.filter(entry => entry.kind === 'request').length, 1, 'the actual request event is retained without a duplicate');
  assert.equal(result.entries.find(entry => entry.id === 'saved-event:model').status, 'completed');
  assert.equal(result.entries.find(entry => entry.id === 'saved-event:check').status, 'failed');
  assert.equal(result.entries.find(entry => entry.id === 'saved-event:publish').status, 'completed');
  assert.ok(result.entries.every(entry => entry.status !== 'running'));
});

test('missing activity remains explicitly unavailable, with only the saved request recovered', () => {
  const result = savedActivityForTurn(turn, []);
  assert.equal(result.hasSavedEvents, false);
  assert.equal(result.entries.length, 1);
  assert.equal(result.entries[0].text, turn.message);
  assert.equal(result.entries[0].kind, 'request');
  assert.equal(result.entries[0].result, undefined);
});
