import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { transform } from 'esbuild';

const { code } = await transform(await readFile(new URL('../src/build-throughput.ts', import.meta.url), 'utf8'), { loader: 'ts', format: 'esm' });
const { buildThroughput } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const sample = (overrides = {}) => ({ eventType: 'model.started', throughput: { tokens: 800, durationMs: 1000, rate: 800, sampledAt: 5000, lastDeltaAt: 5000, state: 'streaming', estimated: true, ...overrides } });

test('the speedometer follows fresh server rates and decays to zero without more output', () => {
  const rows = [sample()];
  assert.deepEqual(buildThroughput(rows, 5100, true, true), { rate: 800, mode: 'streaming' });
  assert.deepEqual(buildThroughput(rows, 5750, true, true), { rate: 400, mode: 'streaming' });
  assert.deepEqual(buildThroughput(rows, 6250, true, true), { rate: 0, mode: 'paused' });
  assert.equal(buildThroughput([sample({ rate: 200 })], 5100, true, true).rate, 200);
});

test('replaying old text never produces a fresh speed burst', () => {
  assert.deepEqual(buildThroughput([sample()], 50_000, true, true), { rate: 0, mode: 'paused' });
  assert.deepEqual(buildThroughput([{ kind: 'tool', arguments: 'x'.repeat(100_000) }], 50_000, true, true), { rate: null, mode: 'unavailable' });
});

test('waiting, tool execution, retries, and disconnection do not carry a previous generation speed', () => {
  const completed = sample({ state: 'complete' });
  assert.deepEqual(buildThroughput([completed], 5100, true, true), { rate: 0, mode: 'paused' });
  assert.deepEqual(buildThroughput([completed, sample({ tokens: 0, durationMs: 0, rate: 0, state: 'waiting', lastDeltaAt: null })], 5100, true, true), { rate: 0, mode: 'waiting' });
  assert.deepEqual(buildThroughput([sample()], 5100, true, false), { rate: null, mode: 'disconnected' });
});

test('a finished request shows a duration-weighted average across its streamed responses', () => {
  const rows = [{ eventType: 'turn.started' }, sample({ state: 'complete', tokens: 500, durationMs: 1000 }), sample({ state: 'complete', tokens: 4000, durationMs: 2000 })];
  assert.deepEqual(buildThroughput(rows, 50_000, false, true), { rate: 1500, mode: 'complete' });
  assert.deepEqual(buildThroughput(rows, 50_000, false, false), { rate: 1500, mode: 'complete' }, 'stored readings do not depend on a live connection');
  assert.equal(buildThroughput([...rows, { eventType: 'model.started' }], 50_000, false, true).rate, null);
  assert.equal(buildThroughput(rows.slice(1), 50_000, false, true).rate, null, 'an evicted beginning cannot provide a complete average');
  assert.equal(buildThroughput([sample({ state: 'complete', tokens: 0, durationMs: 0 })], 50_000, false, true).rate, null);
});
