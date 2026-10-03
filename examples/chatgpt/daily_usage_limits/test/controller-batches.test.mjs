import test from 'node:test';
import assert from 'node:assert/strict';
import { exampleConfig, createSyntheticApi, MemoryStore } from '../src/synthetic.mjs';
import { captureEnrollment, approveEnrollment, enrollmentHash } from '../src/enrollment.mjs';
import { execute, createExecutionContext } from '../src/controller.mjs';

const START = '2030-01-02T00:00:00.000Z';
async function setup(count = 3, overrides = {}) {
  let now = START;
  const config = Object.assign(exampleConfig({ now, cohort: 'all', intervalHours: 168 }),
    { allowInitialReduction: true, captureConcurrency: 8 }, overrides);
  const sample = createSyntheticApi({ config, clock: () => now }).users['synthetic-user-a'];
  const saved = Object.fromEntries(Array.from({ length: count }, (_, i) => {
    const userId = `synthetic-person-${i}`;
    return [userId, { ...structuredClone(sample), userId, email: `${userId}@example.invalid` }];
  }));
  const api = createSyntheticApi({ config, saved, clock: () => now });
  const captured = await captureEnrollment({ config, api, now });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
  const executionContext = createExecutionContext({ config, enrollment, now });
  const store = new MemoryStore();
  return { config, enrollment, api, store, executionContext, setTime(value) { now = value; },
    run: (memberIds, extra = {}) => execute({ executionContext, memberIds, api, store, now, apply: true, ...extra }) };
}

test('1,200 reviewed members complete batches, replay, next release and restore without a roster scan per member', async () => {
  const s = await setup(1200);
  const ids = s.enrollment.members.map(member => member.userId);
  s.api.listMembers = () => assert.fail('queued workers must use point membership checks');
  for (let offset = 0; offset < ids.length; offset += 37) {
    const batch = ids.slice(offset, offset + 37);
    assert.equal((await s.run(batch)).ok, true);
    assert.ok((await s.run(batch)).results.every(row => row.status === 'duplicate_slot'));
  }
  assert.equal(s.api.writes.length, 1200);
  for (const id of [ids[0], ids[600], ids.at(-1)]) {
    assert.equal((await s.store.getState(`${s.config.workspaceId}:${id}`)).enrollmentHash, enrollmentHash(s.enrollment));
  }
  s.setTime('2030-01-09T00:00:00.000Z');
  for (let offset = 0; offset < ids.length; offset += 37) assert.equal((await s.run(ids.slice(offset, offset + 37))).ok, true);
  assert.ok(Object.values(s.api.users).every(user => user.cap.amount === '1000'));
  for (let offset = 0; offset < ids.length; offset += 37) assert.equal((await s.run(ids.slice(offset, offset + 37), { restore: true })).ok, true);
  assert.ok(Object.values(s.api.users).every(user => user.cap.amount === '2000' && user.cap.source === 'workspace_default'));
});

test('queued batches reject unreviewed IDs, duplicates, forged contexts and missing point checks before API use', async () => {
  const s = await setup();
  s.api.readSnapshot = () => assert.fail('no API reads expected');
  await assert.rejects(s.run(['unreviewed-person']), { code: 'BATCH_MEMBER_NOT_REVIEWED' });
  await assert.rejects(s.run(['synthetic-person-0', 'synthetic-person-0']), { code: 'BATCH_MEMBER_NOT_REVIEWED' });
  await assert.rejects(s.run([]), { code: 'BATCH_MEMBER_NOT_REVIEWED' });
  await assert.rejects(s.run(['synthetic-person-0'], { executionContext: { config: s.config, enrollment: s.enrollment } }), { code: 'UNVERIFIED_EXECUTION_CONTEXT' });
  await assert.rejects(execute({ config: s.config, enrollment: s.enrollment, api: s.api, store: s.store, now: START, memberIds: ['synthetic-person-0'] }), { code: 'BATCH_REQUIRES_VERIFIED_CONTEXT' });
  delete s.api.assertMemberActive;
  await assert.rejects(s.run(['synthetic-person-0']), { code: 'BATCH_REQUIRES_POINT_MEMBERSHIP_CHECK' });
});

test('cached execution context is immutable and checks period boundaries on every invocation', async () => {
  const s = await setup();
  assert.throws(() => { s.executionContext.config.policy.ceiling = '999999'; }, TypeError);
  assert.throws(() => { s.executionContext.enrollment.members[0].plan.amount = '999999'; }, TypeError);
  s.config.policy.ceiling = '999999';
  assert.equal(s.executionContext.config.policy.ceiling, '2000');
  s.setTime('2030-02-01T00:00:00.000Z');
  await assert.rejects(s.run(['synthetic-person-0']), { code: 'OUTSIDE_VERIFIED_PERIOD' });
  assert.equal(s.api.writes.length, 0);
});

test('configured initial review window preserves freshness and exact before-state checks', async () => {
  const s = await setup(3, { initialReviewMaxAgeMinutes: 60 });
  s.setTime('2030-01-02T00:30:00.000Z');
  assert.equal((await s.run(['synthetic-person-0'])).ok, true);
  s.api.users['synthetic-person-1'].usage = '1';
  assert.equal((await s.run(['synthetic-person-1'])).results[0].code, 'RESTRICTION_USAGE_CHANGED_RECAPTURE');
  s.setTime('2030-01-02T01:01:00.000Z');
  assert.equal((await s.run(['synthetic-person-2'])).results[0].code, 'INITIAL_PREVIEW_EXPIRED_RECAPTURE');
  assert.equal((await s.run(['synthetic-person-2'], { restore: true })).results[0].status, 'nothing_owned');
});

test('new initial intents use the current clock after slow roster reads and before the first PATCH', async () => {
  for (const slowStage of ['roster', 'final-read']) {
    let now = START;
    const config = exampleConfig({ now, intervalHours: 168 });
    const api = createSyntheticApi({ config, clock: () => now, initialCap: '10' });
    const captured = await captureEnrollment({ config, api, now });
    const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
    const store = new MemoryStore();
    if (slowStage === 'roster') {
      const original = api.listMembers;
      api.listMembers = async () => { now = '2030-01-02T00:16:00.000Z'; return original(); };
    } else {
      const original = api.readSnapshot;
      let reads = 0;
      api.readSnapshot = async id => { if (++reads === 2) now = '2030-01-02T00:16:00.000Z'; return original(id); };
    }
    const result = await execute({ config, enrollment, api, store, clock: () => now, apply: true });
    assert.equal(result.results[0].code, 'INITIAL_PREVIEW_EXPIRED_RECAPTURE');
    assert.equal(api.writes.length, 0);
  }
});

test('saved-ID recovery remains available after group selection drift', async () => {
  const config = exampleConfig({ now: START, intervalHours: 168 });
  config.cohort = { mode: 'selected', groupIds: ['synthetic-group-a'] };
  const api = createSyntheticApi({ config, clock: () => START, initialCap: '10' });
  const captured = await captureEnrollment({ config, api, now: START });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, START);
  const store = new MemoryStore();
  const run = extra => execute({ config, enrollment, api, store, now: START, apply: true, ...extra });
  api.injectFault({ userId: 'synthetic-user-a', type: 'before', status: 403 });
  assert.equal((await run()).results[0].code, 'SIMULATED_WRITE_FAILURE');
  api.groups['synthetic-group-a'].push('synthetic-user-c');
  await assert.rejects(run(), { code: 'COHORT_SELECTION_CHANGED' });
  assert.equal((await run({ apply: false, resumeAuth: true })).results[0].status, 'auth_resumed');
  assert.equal((await run({ apply: false, cancelInitial: true })).results[0].status, 'initial_intent_cancelled');
  assert.equal((await run({ restore: true })).ok, true);
});

test('queue retry metadata preserves API delay and pending absolute intent', async () => {
  const s = await setup();
  s.api.injectFault({ userId: 'synthetic-person-0', type: 'before', status: 429, retryAfterMs: 30_000 });
  const first = (await s.run(['synthetic-person-0'])).results[0];
  assert.equal(first.retryable, true); assert.equal(first.retryAfterMs, 30_000);
  s.setTime('2030-01-02T00:00:10.000Z');
  const second = (await s.run(['synthetic-person-0'])).results[0];
  assert.equal(second.code, 'RETRY_AFTER_NOT_REACHED'); assert.equal(second.retryable, true); assert.equal(second.retryAfterMs, 20_000);
  assert.equal(s.api.writes.length, 0);
  s.setTime('2030-01-02T00:00:31.000Z');
  assert.equal((await s.run(['synthetic-person-0'])).ok, true);
  assert.equal(s.api.writes.length, 1);
});

test('transient reads, busy leases and deferred work remain retryable', async () => {
  const s = await setup();
  const original = s.api.readSnapshot;
  s.api.readSnapshot = async () => { throw Object.assign(new Error('API_READ_TRANSPORT_FAILED'), { code: 'API_READ_TRANSPORT_FAILED', retryable: true, retryAfterMs: 50_000 }); };
  const read = (await s.run(['synthetic-person-0'])).results[0];
  assert.equal(read.retryable, true); assert.equal(read.retryAfterMs, 50_000);
  s.api.readSnapshot = original;
  const busy = (await s.run(['synthetic-person-0'], { store: { withLock: async () => { throw new Error('LEASE_BUSY'); } } })).results[0];
  assert.equal(busy.retryable, true); assert.equal(busy.code, 'LEASE_BUSY');
  const deferred = (await s.run(['synthetic-person-0'], { shouldContinue: () => false })).results[0];
  assert.equal(deferred.retryable, true); assert.equal(deferred.status, 'deferred');
});
