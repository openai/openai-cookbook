import test from 'node:test';
import assert from 'node:assert/strict';
import { exampleConfig, createSyntheticApi } from '../src/synthetic.mjs';
import { captureEnrollment, approveEnrollment, enrollmentHash, validateEnrollment } from '../src/enrollment.mjs';
import { validateConfig, deriveStartingCap, validateInitialHeadroom, planTarget } from '../src/policy.mjs';

const START = '2030-01-02T00:00:00.000Z';
const A = 'synthetic-user-a', B = 'synthetic-user-b', C = 'synthetic-user-c';
function configFor({ unit = 'credit', intervalHours = 24, cohort = 'selected' } = {}) {
  const config = exampleConfig({ now: START, unit, intervalHours, cohort });
  config.policy = {
    pattern: 'individual_staircase', anchor: START, intervalHours,
    initialHeadroom: unit === 'credit' ? '500' : '5',
    minimumInitialHeadroom: unit === 'credit' ? '100' : '1',
    increment: unit === 'credit' ? '500' : '5', ceiling: unit === 'credit' ? '5000' : '50',
  };
  return config;
}
const snapshot = (usage, unit = 'credit') => ({ unit, usage, userId: A,
  cap: { type: 'limited', amount: unit === 'credit' ? '2000' : '20', unit } });

test('individual starting caps round observed usage upward to the workspace cap quantum', () => {
  const credit = configFor(), usd = configFor({ unit: 'usd' });
  validateConfig(credit, START); validateConfig(usd, START);
  for (const [used, expected] of [['0', '500'], ['206', '706'], ['3490.01', '3991'], ['3490.000001', '3991']]) {
    assert.equal(deriveStartingCap(credit, snapshot(used)), expected);
  }
  for (const [used, expected] of [['0', '5'], ['2.001', '7.01'], ['2.01', '7.01'], ['2.010001', '7.02']]) {
    assert.equal(deriveStartingCap(usd, snapshot(used, 'usd')), expected);
  }
});

test('the monthly ceiling bounds the seed while the minimum uses actual observed usage', () => {
  const config = configFor();
  assert.equal(deriveStartingCap(config, snapshot('4700')), '5000');
  assert.equal(deriveStartingCap(config, snapshot('4900')), '5000');
  assert.throws(() => deriveStartingCap(config, snapshot('4900.000001')), { code: 'INITIAL_HEADROOM_TOO_LOW_RECAPTURE' });
  assert.throws(() => deriveStartingCap(config, snapshot('5000')), { code: 'INITIAL_HEADROOM_TOO_LOW_RECAPTURE' });
  validateInitialHeadroom(config, snapshot('600'), '700');
  assert.throws(() => validateInitialHeadroom(config, snapshot('600.000001'), '700'), { code: 'INITIAL_HEADROOM_TOO_LOW_RECAPTURE' });
  assert.throws(() => deriveStartingCap(config, snapshot('0', 'usd')), { code: 'UNIT_TRANSITION_REQUIRES_REENROLLMENT' });
});

test('configuration rejects ambiguous personal maps and invalid or unrepresentable headroom', () => {
  for (const change of [
    policy => { policy.startCap = '500'; },
    policy => { policy.startCaps = { [A]: '500' }; },
    policy => { delete policy.initialHeadroom; },
    policy => { delete policy.minimumInitialHeadroom; },
    policy => { policy.initialHeadroom = '0'; },
    policy => { policy.minimumInitialHeadroom = '0'; },
    policy => { policy.minimumInitialHeadroom = '501'; },
    policy => { policy.initialHeadroom = '500.5'; },
    policy => { policy.minimumInitialHeadroom = '0.1'; },
    policy => { policy.increment = '0'; },
    policy => { policy.ceiling = '99'; },
  ]) {
    const config = configFor(); change(config.policy);
    assert.throws(() => validateConfig(config, START));
  }
  const usd = configFor({ unit: 'usd' });
  usd.policy.minimumInitialHeadroom = '0.001';
  assert.throws(() => validateConfig(usd, START), { code: 'CAP_PRECISION_INVALID' });
});

test('calendar progression uses the reviewed individual seed and never rebases on subsequent usage', () => {
  const config = configFor();
  const before = snapshot('206');
  const startCap = deriveStartingCap(config, before);
  assert.equal(startCap, '706');
  const plan = now => planTarget(config, { ...before, usage: '4000' }, now, undefined, { startCap });
  assert.equal(plan('2030-01-02T23:59:59.000Z').amount, '706');
  assert.equal(plan('2030-01-03T00:00:00.000Z').amount, '1206');
  assert.equal(plan('2030-01-06T00:00:00.000Z').amount, '2706');
  assert.equal(plan('2030-01-12T00:00:00.000Z').amount, '5000');
  assert.equal(plan('2030-01-12T00:00:00.000Z').startCap, '706');
  assert.throws(() => planTarget(config, before, START), { code: 'INDIVIDUAL_START_CAP_REQUIRED' });
  assert.throws(() => planTarget(config, before, START, undefined, { startCap: '5001' }), { code: 'RELEASE_BOUNDS_INVALID' });
  assert.throws(() => planTarget(config, before, START, undefined, { startCap: '706.1' }), { code: 'CAP_PRECISION_INVALID' });
});

test('hourly and weekly cadences use elapsed slots independently of polling frequency', () => {
  for (const [intervalHours, beforeBoundary, boundary] of [
    [1, '2030-01-02T00:59:59.000Z', '2030-01-02T01:00:00.000Z'],
    [168, '2030-01-08T23:59:59.000Z', '2030-01-09T00:00:00.000Z'],
  ]) {
    const config = configFor({ intervalHours });
    assert.equal(planTarget(config, snapshot('206'), beforeBoundary, undefined, { startCap: '706' }).amount, '706');
    assert.equal(planTarget(config, snapshot('206'), boundary, undefined, { startCap: '706' }).amount, '1206');
  }
});

test('all members and mixed ID, email and group selectors derive one reviewed seed per resolved person', async () => {
  for (const cohort of [{ mode: 'all' }, { mode: 'selected', userIds: [A],
    emails: [`${B}@example.invalid`], groupIds: ['synthetic-group-b'] }]) {
    const config = configFor(); config.cohort = cohort;
    const api = createSyntheticApi({ config, clock: () => START });
    api.users[A].usage = '0'; api.users[B].usage = '206'; api.users[C].usage = '3490.01';
    const captured = await captureEnrollment({ config, api, now: START });
    assert.deepEqual(captured.enrollment.members.map(member => [member.userId, member.startCap]),
      [[A, '500'], [B, '706'], [C, '3991']]);
    assert.ok(captured.enrollment.members.every(member => member.plan.amount === member.startCap));
    validateEnrollment(config, approveEnrollment(captured.enrollment, captured.hash, START), START, true);
    assert.equal(api.writes.length, 0);
  }
});

test('capture fails without writing if any selected person lacks the required initial headroom', async () => {
  const config = configFor();
  const api = createSyntheticApi({ config, clock: () => START });
  api.users[B].usage = '4900.000001';
  await assert.rejects(captureEnrollment({ config, api, now: START }), { code: 'INITIAL_HEADROOM_TOO_LOW_RECAPTURE' });
  assert.equal(api.writes.length, 0);
});

test('reapproval cannot validate a missing, edited or inconsistent individual seed or initial plan', async () => {
  const config = configFor();
  const api = createSyntheticApi({ config, clock: () => START });
  const captured = await captureEnrollment({ config, api, now: START });
  for (const change of [
    member => { delete member.startCap; },
    member => { member.startCap = '501'; },
    member => { member.plan.amount = '1000'; },
    member => { member.plan.slot = 1; },
    member => { member.plan.wouldRestrict = false; },
    member => { member.plan.startCap = '1000'; },
    member => { member.before.userId = B; },
  ]) {
    const edited = structuredClone(captured.enrollment);
    change(edited.members[0]);
    const reapproved = approveEnrollment(edited, enrollmentHash(edited), START);
    assert.throws(() => validateEnrollment(config, reapproved, START, true));
  }
  const persisted = JSON.parse(JSON.stringify(approveEnrollment(captured.enrollment, captured.hash, START)));
  validateEnrollment(config, persisted, START, true);
});

test('a later-slot capture freezes its seed separately from the first planned cumulative target', async () => {
  const config = configFor();
  const now = '2030-01-04T00:00:00.000Z';
  const api = createSyntheticApi({ config, clock: () => now });
  api.users[A].usage = '206';
  const captured = await captureEnrollment({ config, api, now });
  const member = captured.enrollment.members.find(member => member.userId === A);
  assert.equal(member.startCap, '706');
  assert.equal(member.plan.slot, 2);
  assert.equal(member.plan.amount, '1706');
  validateEnrollment(config, approveEnrollment(captured.enrollment, captured.hash, now), now, true);
});

test('the initial headroom helper does not change the existing policy patterns', () => {
  for (const pattern of ['fixed_release', 'observed_headroom']) {
    const config = exampleConfig({ now: START, pattern });
    assert.doesNotThrow(() => validateInitialHeadroom(config, snapshot('1000'), '1'));
  }
});
