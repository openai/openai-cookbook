import test from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import { createBuildComparison } from '../server/build-comparison.mjs';

function fixture(t) {
  const feed = createBuildComparison({ intervalMs: 1 });
  t.after(() => feed.close());
  const events = [];
  feed.subscribe(event => events.push(event));
  const state = feed.begin({ model: 'test-model', primaryTurnId: 'fast-turn', standardTurnId: 'standard-turn' });
  return { feed, events, state };
}

test('comparison telemetry omits unchanged previews while GET and replay keep complete state', async t => {
  const { feed, events, state } = fixture(t);
  feed.html(state.id, 'ultrafast', 'fast-turn', '<p>Fast preview</p>');
  feed.html(state.id, 'standard', 'standard-turn', '<p>Standard preview</p>');
  await delay(5);
  assert.equal(events.at(-1).data.retainPreviews, undefined);
  assert.equal(events.at(-1).data.comparison.ultrafast.html, '<p>Fast preview</p>');
  feed.activity(state.id, 'standard', { type: 'activity.entry', turnId: 'standard-turn', data: { entryId: 'response-1', throughput: { tokens: 50 } } });
  await delay(5);
  const compact = events.at(-1);
  assert.equal(compact.data.retainPreviews, true);
  assert.equal(compact.data.comparison.standard.outputTokens, 50);
  assert.equal(Object.hasOwn(compact.data.comparison.ultrafast, 'html'), false);
  assert.equal(Object.hasOwn(compact.data.comparison.standard, 'html'), false);
  const replay = feed.snapshot();
  assert.equal(replay.data.retainPreviews, undefined);
  assert.equal(replay.data.comparison.standard.html, '<p>Standard preview</p>');
  assert.equal(feed.read().ultrafast.html, '<p>Fast preview</p>');
});

test('failed or cancelled lanes explicitly clear their preview in a full replacement event', async t => {
  const { feed, events, state } = fixture(t);
  feed.html(state.id, 'ultrafast', 'fast-turn', '<p>Not published</p>');
  feed.html(state.id, 'standard', 'standard-turn', '<p>Still running</p>');
  await delay(5);
  feed.fail(state.id, 'ultrafast', 'fast-turn', new Error('Stopped'), true);
  const failed = events.at(-1);
  assert.equal(failed.data.retainPreviews, undefined);
  assert.equal(failed.data.comparison.ultrafast.html, undefined);
  assert.equal(failed.data.comparison.ultrafast.status, 'cancelled');
  assert.equal(failed.data.comparison.standard.html, '<p>Still running</p>');
  feed.html(state.id, 'ultrafast', 'fast-turn', '<p>Late stale frame</p>');
  assert.equal(feed.read().ultrafast.html, undefined);
});

test('a new comparison and reset discard previous previews rather than retaining them', async t => {
  const { feed, events, state } = fixture(t);
  feed.html(state.id, 'ultrafast', 'fast-turn', '<p>Previous world</p>');
  await delay(5);
  const next = feed.begin({ model: 'test-model', primaryTurnId: 'next-fast', standardTurnId: 'next-standard' });
  assert.notEqual(next.id, state.id);
  assert.equal(events.at(-1).data.retainPreviews, undefined);
  assert.equal(events.at(-1).data.comparison.ultrafast.html, undefined);
  feed.html(state.id, 'standard', 'standard-turn', '<p>Previous late result</p>');
  assert.equal(feed.read().standard.html, undefined);
  feed.reset();
  assert.equal(events.at(-1).data.comparison, null);
  assert.equal(events.at(-1).data.retainPreviews, undefined);
});

test('replayed per-response output cannot reduce totals and late final counts remain eligible', t => {
  const { feed, state } = fixture(t);
  const output = (entryId, count, id = state.id, turnId = 'fast-turn') => feed.activity(id, 'ultrafast', {
    type: 'activity.entry', turnId, data: { entryId, throughput: { tokens: count } },
  });
  output('response-1', 200);
  output('response-2', 100);
  output('response-1', 20);
  output('response-2', -1);
  assert.equal(feed.read().ultrafast.outputTokens, 300);
  feed.lifecycle(state.id, 'ultrafast', { type: 'turn.completed', turnId: 'fast-turn' });
  output('response-2', 180);
  assert.equal(feed.read().ultrafast.outputTokens, 380);
  assert.equal(feed.read().ultrafast.status, 'completed');
  for (const invalid of [NaN, Infinity, -Infinity]) output('response-2', invalid);
  output('response-1', 5000, 'old-comparison');
  output('response-1', 5000, state.id, 'old-turn');
  assert.equal(feed.read().ultrafast.outputTokens, 380);
  const next = feed.begin({ model: 'test-model', primaryTurnId: 'next-fast', standardTurnId: 'next-standard' });
  output('response-1', 5, next.id, 'next-fast');
  assert.equal(feed.read().ultrafast.outputTokens, 5, 'new comparisons reset cumulative response counts');
});

test('late starts cannot reopen any terminal lane or replace its final outcome', t => {
  for (const status of ['completed', 'failed', 'cancelled']) {
    const { feed, state } = fixture(t);
    const endedAt = '2026-09-25T12:00:03Z';
    feed.lifecycle(state.id, 'standard', { type: `turn.${status}`, turnId: 'standard-turn', time: endedAt, detail: 'Final outcome' });
    const finished = feed.read().standard;
    for (const type of ['turn.started', 'model.started']) {
      feed.lifecycle(state.id, 'standard', { type, turnId: 'standard-turn' });
      assert.deepEqual(feed.read().standard, finished);
    }
    feed.lifecycle(state.id, 'standard', { type: 'model.completed', turnId: 'standard-turn', data: { servedTier: 'default' } });
    assert.equal(feed.read().standard.status, status);
    assert.equal(feed.read().standard.endedAt, endedAt);
    assert.equal(feed.read().standard.servedTier, 'default', 'late model metadata remains eligible');
  }
});
