import test from 'node:test';
import assert from 'node:assert/strict';
import { execute } from '../src/controller.mjs';
import { captureEnrollment, approveEnrollment } from '../src/enrollment.mjs';
import { exampleConfig, createSyntheticApi, MemoryStore } from '../src/synthetic.mjs';

async function fixture() {
  let now = '2030-01-02T00:00:00.000Z';
  const config = exampleConfig({ now, pattern: 'individual_staircase', intervalHours: 24 });
  Object.assign(config.policy, { initialHeadroom: '500', minimumInitialHeadroom: '100', increment: '500', ceiling: '5000' });
  const api = createSyntheticApi({ config, clock: () => now, initialCap: '100' });
  const captured = await captureEnrollment({ config, api, now });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
  const store = new MemoryStore();
  return { config, api, enrollment, store, setTime: value => { now = value; },
    run: extra => execute({ config, api, enrollment, store, now, apply: true, ...extra }) };
}

test('initial individual release rechecks available headroom immediately before a write', async () => {
  const s = await fixture();
  const id = s.enrollment.members[0].userId;
  const read = s.api.readSnapshot.bind(s.api);
  let reads = 0;
  s.api.readSnapshot = async userId => {
    if (userId === id && ++reads === 2) s.api.users[id].usage = '451';
    return read(userId);
  };
  const result = await s.run();
  assert.equal(result.results[0].ok, false);
  assert.equal(s.api.writes.some(write => write.userId === id), false);
  assert.ok((await s.store.getState(`${s.config.workspaceId}:${id}`)).pending);
  const retry = await s.run();
  assert.equal(retry.results[0].ok, false);
  assert.equal(s.api.writes.some(write => write.userId === id), false);
});

test('an initial individual increase retains its review deadline across retry', async () => {
  const s = await fixture();
  const id = s.enrollment.members[0].userId;
  s.api.injectFault({ type: 'before', userId: id, status: 503 });
  const first = await s.run();
  assert.equal(first.results[0].ok, false);
  assert.equal(first.results[0].retryable, true);
  assert.equal((await s.store.getState(`${s.config.workspaceId}:${id}`)).pending.plan.wouldRestrict, false);
  s.setTime('2030-01-02T00:16:00.000Z');
  const retry = await s.run();
  assert.equal(retry.results[0].ok, false);
  assert.equal(retry.results[0].code, 'INITIAL_RESTRICTION_PREVIEW_EXPIRED_CANCEL_AND_REVIEW');
  assert.equal(s.api.writes.some(write => write.userId === id), false);
});

test('individual initial writes carry the final observed usage and review deadline to the adapter', async () => {
  const s = await fixture();
  assert.equal((await s.run()).ok, true);
  for (const write of s.api.writes) {
    assert.equal(write.expectedUsage, '0');
    assert.equal(write.notAfter, '2030-01-02T00:15:00.000Z');
  }
  s.setTime('2030-01-03T00:00:00.000Z');
  assert.equal((await s.run()).ok, true);
  assert.deepEqual(s.enrollment.members.map(member => s.api.users[member.userId].cap.amount), ['1000', '1000']);
});

test('counter decreases before first apply or an initial retry require period review', async () => {
  for (const pending of [false, true]) {
    let now = '2030-01-02T00:00:00.000Z';
    const config = exampleConfig({ now, pattern: 'individual_staircase' });
    Object.assign(config.policy, { initialHeadroom: '500', minimumInitialHeadroom: '100', ceiling: '5000' });
    const api = createSyntheticApi({ config, clock: () => now, initialCap: '100' });
    const id = config.cohort.userIds[0];
    api.users[id].usage = '1000';
    const captured = await captureEnrollment({ config, api, now });
    const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
    const store = new MemoryStore();
    if (pending) {
      api.injectFault({ type: 'before', userId: id, status: 503 });
      const first = await execute({ config, enrollment, api, store, now, apply: true });
      assert.equal(first.results[0].ok, false);
      assert.ok((await store.getState(`${config.workspaceId}:${id}`)).pending);
    }
    api.users[id].usage = '0';
    const result = await execute({ config, enrollment, api, store, now, apply: true });
    assert.equal(result.results[0].code, 'COUNTER_DECREASE_REQUIRES_PERIOD_REVIEW');
    assert.equal(api.writes.some(write => write.userId === id), false);
    if (pending) assert.ok((await store.getState(`${config.workspaceId}:${id}`)).pending);
  }
});
