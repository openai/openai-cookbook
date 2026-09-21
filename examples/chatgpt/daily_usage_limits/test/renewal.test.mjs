import test from 'node:test';
import assert from 'node:assert/strict';
import { captureRenewal } from '../src/renewal.mjs';
import { captureEnrollment, approveEnrollment, enrollmentHash } from '../src/enrollment.mjs';
import { createExecutionContext, execute } from '../src/controller.mjs';
import { settingsEquivalent } from '../src/admin-api.mjs';
import { configDigest, digest } from '../src/policy.mjs';
import { exampleConfig, createSyntheticApi, MemoryStore } from '../src/synthetic.mjs';

const FIRST_NOW = '2030-01-02T00:00:00.000Z';
const NEXT_NOW = '2030-02-01T00:00:00.000Z';
const NEXT_PERIOD = Object.freeze({
  kind: 'calendar_month', start: NEXT_NOW, end: '2030-03-01T00:00:00.000Z',
  verifiedAt: NEXT_NOW, evidence: 'Fictional February counter period independently confirmed.',
  counterScopeConfirmed: true,
});
const clone = value => structuredClone(value);

// Models the store's atomic archive-and-replace contract. An ordinary putState
// cannot make a previous enrollment's ownership available to a new enrollment.
class RenewalStore extends MemoryStore {
  archives = [];
  failTransition = false;
  async transitionState(key, { previous, next }) {
    await this.assertLock(key);
    assert.equal(digest(await this.getState(key)), digest(previous), 'transition must compare the exact previous state');
    if (this.failTransition) throw Object.assign(new Error('SIMULATED_ARCHIVE_FAILURE'), { code: 'SIMULATED_ARCHIVE_FAILURE' });
    this.archives.push({ key, previous: clone(previous), next: clone(next) });
    this.states.set(key, clone(next));
  }
}

function applySettings(user, settings) {
  user.settings = clone(settings);
  const effective = settings.effective;
  const rule = effective?.limit;
  user.cap = rule ? {
    type: rule.type, unit: user.unit, source: effective.source.kind,
    ...(rule.type === 'limited' ? { amount: String(rule.limit_amount.amount) } : {}),
    ...(rule.limit_expires_at ? { expiresAt: rule.limit_expires_at } : {}),
  } : { type: 'unset', unit: user.unit };
}

async function fixture({ original = 'group', cohort = 'selected', selectors,
  intervalHours = 168, initialReviewMaxAgeMinutes = 15 } = {}) {
  let now = FIRST_NOW;
  const config = exampleConfig({ now, intervalHours, cohort });
  config.allowInitialReduction = true;
  config.initialReviewMaxAgeMinutes = initialReviewMaxAgeMinutes;
  if (selectors) config.cohort = clone(selectors);
  const api = createSyntheticApi({ config, clock: () => now });
  const fallback = {
    limit: { type: 'limited', limit_amount: { amount: '4000', unit: 'credit' } },
    source: { kind: 'group_default', group_id: 'fictional-usage-group' },
  };
  for (const user of Object.values(api.users)) {
    user.usage = '123';
    if (original === 'unset') applySettings(user, { override: null, effective: null, inherited: null });
    else if (original === 'group') applySettings(user, { override: null, effective: fallback, inherited: null });
    else {
      const rule = { type: 'limited', limit_amount: { amount: '1500', unit: 'credit' },
        ...(original === 'temporary' ? { limit_expires_at: config.period.end } : {}) };
      applySettings(user, { override: [rule], effective: { limit: rule, source: { kind: 'individual_override' } }, inherited: fallback });
    }
  }
  // The public API may expose a no-override group rule as effective with a null
  // inherited field, then expose that same rule as inherited after a PATCH.
  const setCap = api.setCap.bind(api);
  api.setCap = async (id, target) => {
    const before = clone(api.users[id].settings);
    await setCap(id, target);
    api.users[id].settings.inherited = before.override?.length ? before.inherited : before.effective;
  };
  const captured = await captureEnrollment({ config, api, now });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
  const store = new RenewalStore();
  const first = await execute({ config, enrollment, api, store, now, apply: true });
  assert.equal(first.ok, true, JSON.stringify(first.results));
  const ids = enrollment.members.map(member => member.userId);
  const key = id => `${config.workspaceId}:${id}`;
  return {
    config, enrollment, api, store, ids, key, fallback,
    get now() { return now; },
    setTime(value) { now = value; },
    enterNextPeriod() {
      now = NEXT_NOW;
      for (const id of ids) {
        const user = api.users[id];
        assert.equal(user.cap.expiresAt, config.period.end);
        // Simulate server expiry and a new monthly counter. This is an explicit
        // fixture event, never a period inferred from a decreasing counter.
        applySettings(user, { override: null, effective: user.settings.inherited, inherited: null });
        user.usage = '2';
      }
    },
    capture: (extra = {}) => captureRenewal({ previousConfig: config, previousEnrollment: enrollment,
      period: clone(NEXT_PERIOD), api, store, now, ...extra }),
    run: (renewed, extra = {}) => execute({ config: renewed.config, enrollment: renewed.enrollment,
      api, store, now, apply: true, ...extra }),
  };
}

function approve(renewed, now = NEXT_NOW) {
  return { ...renewed, enrollment: approveEnrollment(renewed.enrollment, renewed.hash, now) };
}

async function assertCaptureBlocked(s, extra) {
  const writes = s.api.writes.length;
  const states = clone([...s.store.states]);
  await assert.rejects(s.capture(extra));
  assert.equal(s.api.writes.length, writes, 'capture cannot change a cap');
  assert.deepEqual([...s.store.states], states, 'failed capture cannot change ownership');
  assert.equal(s.store.archives.length, 0);
}

test('two reviewed adjacent periods retain the policy, cohort and original restoration settings', async () => {
  const s = await fixture();
  const oldConfig = clone(s.config), oldEnrollment = clone(s.enrollment);
  const priorStates = new Map(await Promise.all(s.ids.map(async id => [id, await s.store.getState(s.key(id))])));
  s.enterNextPeriod();
  const writes = s.api.writes.length;
  const captured = await s.capture();
  assert.deepEqual(s.config, oldConfig);
  assert.deepEqual(s.enrollment, oldEnrollment);
  assert.deepEqual(captured.config.period, NEXT_PERIOD);
  assert.equal(captured.config.liveWrites, false);
  assert.deepEqual(captured.config.cohort, s.config.cohort);
  const { anchor: oldAnchor, ...oldPolicy } = s.config.policy;
  const { anchor: newAnchor, ...newPolicy } = captured.config.policy;
  assert.deepEqual(newPolicy, oldPolicy);
  assert.equal(newAnchor, NEXT_PERIOD.start);
  assert.notEqual(newAnchor, oldAnchor);
  assert.deepEqual(captured.enrollment.selection, s.enrollment.selection);
  assert.deepEqual(captured.enrollment.members.map(member => member.userId), s.ids);
  assert.equal(captured.hash, enrollmentHash(captured.enrollment));
  assert.notEqual(captured.hash, enrollmentHash(s.enrollment));
  assert.equal(captured.enrollment.approval, undefined);
  assert.deepEqual(captured.enrollment.renewal, {
    version: 1, previousConfigDigest: configDigest(s.config),
    previousEnrollmentHash: enrollmentHash(s.enrollment), previousPeriodEnd: s.config.period.end,
  });
  for (const member of captured.enrollment.members) {
    assert.equal(member.before.usage, '2');
    assert.equal(member.plan.slot, 0);
    assert.equal(member.plan.amount, '500');
    assert.equal(member.renewal.priorStateDigest, digest(priorStates.get(member.userId)));
    assert.ok(settingsEquivalent(member.renewal.original.settings,
      priorStates.get(member.userId).original.settings, s.config.unit));
  }
  assert.equal(s.api.writes.length, writes);
  assert.equal(s.store.archives.length, 0);
  assert.deepEqual([...s.store.states], [...priorStates].map(([id, state]) => [s.key(id), state]));
  await assert.rejects(s.run(captured), { code: 'ENROLLMENT_APPROVAL_REQUIRED' });

  const renewed = approve(captured);
  assert.equal((await s.run(renewed)).ok, true);
  assert.equal(s.store.archives.length, s.ids.length);
  for (const id of s.ids) {
    assert.equal(s.api.users[id].cap.amount, '500');
    assert.equal(s.api.users[id].cap.expiresAt, NEXT_PERIOD.end);
    const state = await s.store.getState(s.key(id));
    assert.equal(state.enrollmentHash, renewed.hash);
    assert.equal(state.lastUsage, '2', 'a reviewed new period permits the verified counter reset');
    assert.ok(settingsEquivalent(state.original.settings, priorStates.get(id).original.settings, s.config.unit));
    assert.deepEqual(s.store.archives.find(item => item.key === s.key(id)).previous, priorStates.get(id));
  }
  assert.equal((await s.run(renewed, { restore: true })).ok, true);
  for (const id of s.ids) assert.ok(settingsEquivalent(s.api.users[id].settings, priorStates.get(id).original.settings, s.config.unit));
});

test('renewal requires explicit confirmed period bounds and an unchanged approved previous document', async () => {
  const s = await fixture();
  s.enterNextPeriod();
  for (const period of [undefined, null,
    { ...NEXT_PERIOD, start: '2030-01-01T00:00:00.000Z' },
    { ...NEXT_PERIOD, counterScopeConfirmed: false },
    { ...NEXT_PERIOD, evidence: '' },
    { ...NEXT_PERIOD, verifiedAt: '2030-02-02T00:00:00.000Z' }]) await assertCaptureBlocked(s, { period });
  const changed = clone(s.config);
  changed.policy.ceiling = '3000';
  await assertCaptureBlocked(s, { previousConfig: changed });
  const unapproved = clone(s.enrollment);
  delete unapproved.approval;
  await assertCaptureBlocked(s, { previousEnrollment: unapproved });
});

test('renewal rejects pending, halted, missing or differently owned prior state without changing caps', async () => {
  for (const variant of ['pending', 'halted', 'missing', 'config-owner', 'enrollment-owner']) {
    const s = await fixture();
    s.enterNextPeriod();
    const key = s.key(s.ids[0]);
    const state = s.store.states.get(key);
    if (variant === 'pending') state.pending = { kind: 'cap', amount: '1000', slot: 1, before: clone(state.last) };
    if (variant === 'halted') state.halted = true;
    if (variant === 'missing') s.store.states.delete(key);
    if (variant === 'config-owner') state.configDigest = '0'.repeat(64);
    if (variant === 'enrollment-owner') state.enrollmentHash = '0'.repeat(64);
    await assertCaptureBlocked(s);
  }
});

test('expired controller caps require the exact known inherited fallback', async () => {
  for (const variant of ['amount', 'source-id', 'removed-fallback', 'new-override']) {
    const s = await fixture();
    s.enterNextPeriod();
    const user = s.api.users[s.ids[0]];
    const settings = clone(user.settings);
    if (variant === 'amount') settings.effective.limit.limit_amount.amount = '3999';
    if (variant === 'source-id') settings.effective.source.group_id = 'another-group';
    if (variant === 'removed-fallback') settings.effective = null;
    if (variant === 'new-override') {
      const rule = { type: 'limited', limit_amount: { amount: '600', unit: 'credit' } };
      settings.override = [rule]; settings.effective = { limit: rule, source: { kind: 'individual_override' } };
      settings.inherited = s.fallback;
    }
    applySettings(user, settings);
    await assertCaptureBlocked(s);
  }
});

test('a lingering temporary override is not treated as expired', async () => {
  const s = await fixture();
  const lingering = clone(s.api.users[s.ids[0]]);
  s.enterNextPeriod();
  s.api.users[s.ids[0]] = { ...lingering, usage: '2' };
  await assertCaptureBlocked(s);
});

test('renewal keeps the exact resolved cohort and detects changed group bindings', async () => {
  const all = await fixture({ cohort: 'all' });
  all.enterNextPeriod();
  const added = clone(all.api.users[all.ids[0]]);
  added.userId = 'new-unreviewed-person'; added.email = 'new-unreviewed-person@example.invalid';
  all.api.users[added.userId] = added;
  await assertCaptureBlocked(all);

  const selected = await fixture();
  selected.enterNextPeriod();
  delete selected.api.users[selected.ids[0]];
  await assertCaptureBlocked(selected);

  const group = await fixture({ selectors: { mode: 'selected',
    userIds: ['synthetic-user-a', 'synthetic-user-b'], groupIds: ['synthetic-group-a'] } });
  group.enterNextPeriod();
  group.api.groups['synthetic-group-a'] = ['synthetic-user-a'];
  // The union still has both people, but the reviewed group binding changed.
  await assertCaptureBlocked(group);
});

test('unset originals remain unset after two periods and an explicit restore', async () => {
  const s = await fixture({ original: 'unset' });
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  for (const member of renewed.enrollment.members) {
    assert.deepEqual(member.before.cap, { type: 'unset', unit: 'credit' });
    assert.deepEqual(member.renewal.original.settings, { override: null, effective: null, inherited: null });
    assert.equal(member.plan.wouldRestrict, true);
  }
  assert.equal((await s.run(renewed)).ok, true);
  assert.equal((await s.run(renewed, { restore: true })).ok, true);
  for (const id of s.ids) {
    assert.deepEqual(s.api.users[id].cap, { type: 'unset', unit: 'credit' });
    assert.deepEqual(s.api.users[id].settings, { override: null, effective: null, inherited: null });
  }
});

test('renewal carries a permanent original override across the period boundary', async () => {
  const s = await fixture({ original: 'persistent' });
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  assert.equal((await s.run(renewed)).ok, true);
  assert.equal((await s.run(renewed, { restore: true })).ok, true);
  for (const id of s.ids) {
    assert.equal(s.api.users[id].cap.source, 'individual_override');
    assert.equal(s.api.users[id].cap.amount, '1500');
    assert.equal(s.api.users[id].cap.expiresAt, undefined);
    assert.equal(s.api.users[id].settings.override.length, 1);
  }
});

test('an expired original temporary override projects to its verified fallback without recreating the old rule', async () => {
  const s = await fixture({ original: 'temporary' });
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  for (const member of renewed.enrollment.members) {
    assert.equal(member.renewal.original.settings.override, null);
    assert.deepEqual(member.renewal.original.settings.effective, s.fallback);
    assert.equal(member.renewal.original.cap.expiresAt, undefined);
  }
  assert.equal((await s.run(renewed)).ok, true);
  for (const archive of s.store.archives) assert.equal(archive.previous.original.cap.expiresAt, s.config.period.end);
  assert.equal((await s.run(renewed, { restore: true })).ok, true);
  for (const id of s.ids) {
    assert.equal(s.api.users[id].settings.override, null);
    assert.deepEqual(s.api.users[id].settings.effective, s.fallback);
    assert.equal(s.api.users[id].cap.expiresAt, undefined);
  }
});

test('partially activated renewal resumes from the same reviewed file and does not write twice', async () => {
  const s = await fixture();
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  const context = createExecutionContext({ config: renewed.config, enrollment: renewed.enrollment, now: s.now });
  const first = await s.run(renewed, { executionContext: context, memberIds: [s.ids[0]] });
  assert.equal(first.ok, true);
  assert.equal(s.store.archives.length, 1);
  const writes = s.api.writes.length;
  const resumed = await s.run(renewed);
  assert.equal(resumed.ok, true);
  assert.equal(resumed.results.find(row => row.userId === s.ids[0]).status, 'duplicate_slot');
  assert.equal(s.api.writes.length, writes + s.ids.length - 1);
  assert.equal(s.store.archives.length, s.ids.length);
  const replay = await s.run(renewed);
  assert.ok(replay.results.every(row => row.status === 'duplicate_slot'));
  assert.equal(s.api.writes.length, writes + s.ids.length - 1);
  assert.equal(s.store.archives.length, s.ids.length);
});

test('partial renewal can restore every original after the initial review window or release slot expires', async () => {
  for (const restoreAt of ['2030-02-01T00:16:00.000Z', '2030-02-08T00:00:00.000Z']) {
    const s = await fixture({ original: 'persistent' });
    s.enterNextPeriod();
    const renewed = approve(await s.capture());
    const context = createExecutionContext({ config: renewed.config, enrollment: renewed.enrollment, now: s.now });
    assert.equal((await s.run(renewed, { executionContext: context, memberIds: [s.ids[0]] })).ok, true);
    assert.equal(s.api.users[s.ids[0]].cap.amount, '500');
    assert.equal(s.api.users[s.ids[1]].cap.amount, '4000');
    const grants = s.api.writes.filter(write => !write.restore).length;
    s.setTime(restoreAt);

    const restored = await s.run(renewed, { restore: true });
    assert.equal(restored.ok, true, JSON.stringify(restored.results));
    assert.ok(restored.results.every(row => row.status === 'restored'));
    assert.equal(s.api.writes.filter(write => !write.restore).length, grants, 'restore must not grant another release');
    assert.equal(s.api.writes.filter(write => write.restore).length, s.ids.length);
    assert.equal(s.store.archives.length, s.ids.length);
    for (const member of renewed.enrollment.members) {
      assert.ok(settingsEquivalent(s.api.users[member.userId].settings, member.renewal.original.settings, 'credit'));
      assert.equal(s.api.users[member.userId].cap.amount, '1500');
      assert.equal(s.api.users[member.userId].cap.expiresAt, undefined);
      const state = await s.store.getState(s.key(member.userId));
      assert.equal(state.restored, true);
      assert.equal(state.pending, null);
    }
  }
});

test('late restore of an untransitioned member still requires the exact reviewed live settings', async () => {
  const s = await fixture({ original: 'persistent' });
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  const context = createExecutionContext({ config: renewed.config, enrollment: renewed.enrollment, now: s.now });
  assert.equal((await s.run(renewed, { executionContext: context, memberIds: [s.ids[0]] })).ok, true);
  s.setTime('2030-02-08T00:00:00.000Z');
  const id = s.ids[1], previousState = await s.store.getState(s.key(id));
  const settings = clone(s.api.users[id].settings);
  settings.effective.limit.limit_amount.amount = '3999';
  applySettings(s.api.users[id], settings);
  const writes = s.api.writes.length;

  const result = await s.run(renewed, { restore: true, executionContext: context, memberIds: [id] });
  assert.equal(result.ok, false);
  assert.equal(result.results[0].code, 'ENROLLMENT_BEFORE_STATE_CHANGED');
  assert.equal(s.api.writes.length, writes);
  assert.deepEqual(await s.store.getState(s.key(id)), previousState);
  assert.equal(s.store.archives.length, 1);
});

test('late partial restore preserves its pending intent until exact readback is reconciled', async () => {
  const s = await fixture({ original: 'persistent' });
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  const context = createExecutionContext({ config: renewed.config, enrollment: renewed.enrollment, now: s.now });
  assert.equal((await s.run(renewed, { executionContext: context, memberIds: [s.ids[0]] })).ok, true);
  s.setTime('2030-02-08T00:00:00.000Z');
  const id = s.ids[1], restore = s.api.restore.bind(s.api), readSnapshot = s.api.readSnapshot.bind(s.api);
  let staleReadback;
  s.api.restore = async (userId, target) => {
    const before = await readSnapshot(userId);
    await restore(userId, target);
    if (userId === id) staleReadback = before;
  };
  s.api.readSnapshot = async userId => {
    if (userId === id && staleReadback) {
      const before = staleReadback;
      staleReadback = undefined;
      return before;
    }
    return readSnapshot(userId);
  };
  const grants = s.api.writes.filter(write => !write.restore).length;
  const first = await s.run(renewed, { restore: true });
  assert.equal(first.ok, false);
  assert.equal(first.results.find(row => row.userId === id).code, 'WRITE_READBACK_MISMATCH');
  assert.equal((await s.store.getState(s.key(id))).pending.kind, 'restore');
  assert.notEqual((await s.store.getState(s.key(id))).restored, true);
  const writes = s.api.writes.length;

  const reconciled = await s.run(renewed, { restore: true });
  assert.equal(reconciled.ok, true);
  assert.equal(reconciled.results.find(row => row.userId === id).status, 'reconciled');
  assert.equal(s.api.writes.length, writes, 'successful readback must reconcile without another PATCH');
  assert.equal(s.api.writes.filter(write => !write.restore).length, grants);
  for (const member of renewed.enrollment.members) {
    assert.ok(settingsEquivalent(s.api.users[member.userId].settings, member.renewal.original.settings, 'credit'));
    assert.equal((await s.store.getState(s.key(member.userId))).restored, true);
  }
});

test('the first renewal write rechecks prior state ownership under the stable member lock', async () => {
  const s = await fixture();
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  const id = s.ids[0], key = s.key(id);
  s.store.states.get(key).lastUsage = '124';
  const changed = clone(s.store.states.get(key));
  const writes = s.api.writes.length;
  const context = createExecutionContext({ config: renewed.config, enrollment: renewed.enrollment, now: s.now });
  const result = await s.run(renewed, { executionContext: context, memberIds: [id] });
  assert.equal(result.ok, false);
  assert.equal(s.api.writes.length, writes);
  assert.deepEqual(s.store.states.get(key), changed);
  assert.equal(s.store.archives.length, 0);
});

test('missing prior state cannot turn a reviewed renewal into a fresh enrollment', async () => {
  const s = await fixture();
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  const id = s.ids[0], key = s.key(id);
  s.store.states.delete(key);
  const writes = s.api.writes.length;
  const context = createExecutionContext({ config: renewed.config, enrollment: renewed.enrollment, now: s.now });
  const result = await s.run(renewed, { executionContext: context, memberIds: [id] });
  assert.equal(result.ok, false);
  assert.equal(s.api.writes.length, writes);
  assert.equal(await s.store.getState(key), null);
  assert.equal(s.store.archives.length, 0);
});

test('failed durable archival blocks the first renewal PATCH and preserves previous ownership', async () => {
  const s = await fixture();
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  const states = clone([...s.store.states]);
  const writes = s.api.writes.length;
  s.store.failTransition = true;
  const result = await s.run(renewed);
  assert.equal(result.ok, false);
  assert.equal(s.api.writes.length, writes);
  assert.deepEqual([...s.store.states], states);
  assert.equal(s.store.archives.length, 0);
});

test('changed live settings after renewal approval block activation before archival or PATCH', async () => {
  const s = await fixture();
  s.enterNextPeriod();
  const renewed = approve(await s.capture());
  const id = s.ids[0], key = s.key(id);
  const before = await s.store.getState(key);
  const settings = clone(s.api.users[id].settings);
  settings.effective.limit.limit_amount.amount = '3000';
  applySettings(s.api.users[id], settings);
  const writes = s.api.writes.length;
  const context = createExecutionContext({ config: renewed.config, enrollment: renewed.enrollment, now: s.now });
  const result = await s.run(renewed, { executionContext: context, memberIds: [id] });
  assert.equal(result.ok, false);
  assert.equal(s.api.writes.length, writes);
  assert.deepEqual(await s.store.getState(key), before);
  assert.equal(s.store.archives.length, 0);
});

test('even a newly approved renewal cannot replace the original baseline recorded in prior state', async () => {
  const s = await fixture();
  s.enterNextPeriod();
  const captured = await s.capture();
  const member = captured.enrollment.members[0];
  member.renewal.original.settings.effective.limit.limit_amount.amount = '3999';
  member.renewal.original.cap.amount = '3999';
  captured.hash = enrollmentHash(captured.enrollment);
  const renewed = approve(captured);
  const context = createExecutionContext({ config: renewed.config, enrollment: renewed.enrollment, now: s.now });
  const before = await s.store.getState(s.key(member.userId));
  const writes = s.api.writes.length;
  const result = await s.run(renewed, { executionContext: context, memberIds: [member.userId] });
  assert.equal(result.ok, false);
  assert.equal(s.api.writes.length, writes);
  assert.deepEqual(await s.store.getState(s.key(member.userId)), before);
  assert.equal(s.store.archives.length, 0);
});

test('slow prior-state reads cannot extend the review window or cross a release slot', async () => {
  for (const variant of ['review-window', 'release-slot']) {
    const s = await fixture(variant === 'release-slot' ? { intervalHours: 1, initialReviewMaxAgeMinutes: 120 } : {});
    s.enterNextPeriod();
    const getState = s.store.getState.bind(s.store);
    s.store.getState = async key => {
      s.setTime(variant === 'review-window' ? '2030-02-01T00:16:00.000Z' : '2030-02-01T01:00:00.000Z');
      return getState(key);
    };
    await assertCaptureBlocked(s, { now: undefined, clock: () => s.now });
  }
});
